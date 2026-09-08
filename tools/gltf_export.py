"""Assembles the OM10 parts into one glTF binary for a real-time renderer.

    python tools/gltf_export.py                     # -> captures/gltf/movement.glb
    python tools/gltf_export.py --deflection 0.02   # finer tessellation

WHAT THIS IS FOR, and how it differs from everything else in tools/. The rest of
this directory renders the watch to flat PNG layers that the XAML rotates. That
pipeline cannot light anything it turns - see PIPELINE.md for the chain - so the
movement in the aperture has no form. This writes the same parts out as
GEOMETRY instead of as pictures, so that a renderer with a GPU can light them
per frame and the constraint stops applying.

WHY IT READS THE PARTS AND NOT models/step/movement.step. That file is the
merged, placed, scaled assembly and it is one anonymous blob of twenty solids.
captures/om10/parts/ is the same geometry still separated and still NAMED, and a
name is what lets a wheel be brass while the lever beside it is steel. The names
come from om10_extract.py and the numbers beside them from openmovement's own
drawings, which is why the material table below is the only invented thing here.

UNITS ARE MILLIMETRES, deliberately, and this is the one place in the repo that
is not in face units. glTF's convention is metres and every DCC tool and engine
assumes real scale for its lighting falloff and its depth precision; a movement
authored in the face's own 11.78-units-per-mm space would import 11.78x too
large and light wrongly. The face transform belongs at the other end, applied by
whatever draws this, not baked into the asset.

PLACEMENT. Each part STEP is origin-centred with its Z starting at zero. The
manifest carries where it actually goes: `axis` is the (x, y) of its arbor and
`z_lo` the underside of the part in the stack. Translating by those three
reassembles the movement, and the Z is the whole point - it is the dimension the
sprite pipeline had to throw away, and it is what a contact shadow is made of.

NORMALS COME FROM THE SURFACE, never from the triangles. Recomputing a normal by
averaging the faces around a vertex is what makes a cylinder look faceted and a
chamfer read as a black sliver, which is a defect this face already has once
(see HANDOVER-WALL-READ.md on the bezel). Every vertex here is handed the exact
analytic normal of the CAD surface at its own UV, so tessellation density
changes the silhouette and never the shading.
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import trimesh

from OCP.STEPControl import STEPControl_Reader
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from OCP.BRepGProp import BRepGProp_Face
from OCP.gp import gp_Pnt, gp_Vec

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PARTS = os.path.join(ROOT, "captures", "om10", "parts")
OUT = os.path.join(ROOT, "captures", "gltf", "movement.glb")

# The only invented content in this file. Base colour, metalness and roughness
# per part, keyed by the extractor's own names.
#
# These are first-pass values chosen to be ARGUABLE rather than tuned: a watch
# movement is nickel-plated brass, gilt wheels, hardened steel for anything that
# has to take an impact, and synthetic ruby where a pivot turns. Roughness is
# where the finishing work will land later - perlage on the plate, anglage on
# the bridge edges, a black polish on the lever - and none of that is here yet,
# because a flat roughness is honest about being a placeholder in a way that a
# guessed texture is not.
#
# glTF core cannot express anisotropy, which is what circular graining and
# straight-grained steel actually ARE. KHR_materials_anisotropy exists and the
# runtime should set it; this writer does not, and that is a known gap rather
# than an oversight.
STEEL = (0.560, 0.570, 0.580)
BRASS = (0.780, 0.630, 0.310)
NICKEL = (0.660, 0.650, 0.630)
RUBY = (0.560, 0.060, 0.090)

MATERIALS = {
    "mainplate": (NICKEL, 1.0, 0.28),
    "bridge":    (NICKEL, 1.0, 0.24),
    "cock":      (NICKEL, 1.0, 0.24),
    "wheel_a":   (BRASS,  1.0, 0.22),
    "wheel_b":   (BRASS,  1.0, 0.22),
    "wheel_c":   (BRASS,  1.0, 0.22),
    "pinion_a":  (STEEL,  1.0, 0.12),
    "pinion_b":  (STEEL,  1.0, 0.12),
    "epinion":   (STEEL,  1.0, 0.12),
    "escape":    (STEEL,  1.0, 0.14),
    "lever":     (STEEL,  1.0, 0.10),
    "guard":     (STEEL,  1.0, 0.10),
    "staff":     (STEEL,  1.0, 0.08),
    "roller":    (STEEL,  1.0, 0.10),
    "collet":    (BRASS,  1.0, 0.20),
    "balance":   (BRASS,  1.0, 0.18),
    "hairspring":(STEEL,  1.0, 0.16),
    "jewel":     (RUBY,   0.0, 0.05),
    "stone_a":   (RUBY,   0.0, 0.05),
    "stone_b":   (RUBY,   0.0, 0.05),
    "screw_a":   (STEEL,  1.0, 0.06),
    "screw_b":   (STEEL,  1.0, 0.06),
    "screw_c":   (STEEL,  1.0, 0.06),
}
FALLBACK = (STEEL, 1.0, 0.20)


def tessellate(path, deflection, angular):
    """One part STEP -> (vertices, normals, faces), normals off the surface.

    Returns None for a file that reads but carries no triangulable face, which
    is a corrupt or empty extraction rather than an error worth stopping for -
    the caller reports it and carries on with the parts that did load.
    """
    reader = STEPControl_Reader()
    reader.ReadFile(path)
    reader.TransferRoots()
    shape = reader.OneShape()
    BRepMesh_IncrementalMesh(shape, deflection, False, angular, True)

    verts, norms, faces = [], [], []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        exp.Next()
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            continue
        xf = loc.Transformation()
        reversed_ = face.Orientation() == TopAbs_REVERSED
        gface = BRepGProp_Face(face)
        base = len(verts)
        has_uv = tri.HasUVNodes()

        for i in range(1, tri.NbNodes() + 1):
            p = tri.Node(i).Transformed(xf)
            verts.append((p.X(), p.Y(), p.Z()))
            n = np.array([0.0, 0.0, 1.0])
            if has_uv:
                uv = tri.UVNode(i)
                at, vec = gp_Pnt(), gp_Vec()
                gface.Normal(uv.X(), uv.Y(), at, vec)
                cand = np.array([vec.X(), vec.Y(), vec.Z()], float)
                mag = np.linalg.norm(cand)
                if mag > 1e-12:
                    n = cand / mag
            # A REVERSED face is the same surface walked the other way: its
            # analytic normal points into the solid, so both it and the winding
            # have to flip or the part renders inside-out under a key light.
            norms.append(-n if reversed_ else n)

        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            faces.append((base + c - 1, base + b - 1, base + a - 1) if reversed_
                         else (base + a - 1, base + b - 1, base + c - 1))

    if not faces:
        return None
    return np.array(verts), np.array(norms), np.array(faces)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--deflection", type=float, default=0.004,
                    help="linear deflection in MILLIMETRES (default 0.004 = 4um)")
    ap.add_argument("--angular", type=float, default=0.10,
                    help="angular deflection in radians (default 0.10)")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    manifest_path = os.path.join(PARTS, "manifest.json")
    if not os.path.exists(manifest_path):
        raise SystemExit(
            "missing %s\n"
            "This needs the extracted OM10 parts, which are gitignored. Either run\n"
            "tools/om10_extract.py against your own copy of the openmovement STEP,\n"
            "or copy captures/om10/parts/ from a machine that has them."
            % manifest_path)
    manifest = json.load(open(manifest_path))

    scene = trimesh.Scene()
    total_t = total_v = 0
    missing, empty = [], []
    t0 = time.time()

    for name, meta in sorted(manifest.items()):
        step = os.path.join(PARTS, "%s.step" % name)
        if not os.path.exists(step):
            missing.append(name)
            continue
        got = tessellate(step, args.deflection, args.angular)
        if got is None:
            empty.append(name)
            continue
        verts, norms, faces = got

        # Reassemble: the arbor's (x, y) and the underside of the part in Z.
        ax = meta.get("axis") or [0.0, 0.0]
        verts = verts + np.array([ax[0], ax[1], meta.get("z_lo", 0.0)])

        # CAD is Z-up; glTF is Y-UP BY SPEC and every consumer believes it.
        # Emitting Z-up data makes the movement import lying on its side - which
        # is not a subtle failure, but it is a silent one, because a renderer
        # with an orbit camera just looks like it framed the shot badly. Convert
        # here, once, rather than asking each consumer to correct for us.
        # Rotate -90 about X: (x, y, z) -> (x, z, -y). Normals go with it.
        verts = np.column_stack((verts[:, 0], verts[:, 2], -verts[:, 1]))
        norms = np.column_stack((norms[:, 0], norms[:, 2], -norms[:, 1]))

        colour, metal, rough = MATERIALS.get(name, FALLBACK)
        mesh = trimesh.Trimesh(vertices=verts, faces=faces,
                               vertex_normals=norms, process=False)
        mesh.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                name=name,
                baseColorFactor=[colour[0], colour[1], colour[2], 1.0],
                metallicFactor=metal,
                roughnessFactor=rough))
        scene.add_geometry(mesh, geom_name=name)
        total_t += len(faces)
        total_v += len(verts)
        print("  %-12s %-12s %7d tris  z %+7.3f..%+7.3f mm"
              % (name, meta.get("source", "?"), len(faces),
                 meta.get("z_lo", 0.0), meta.get("z_hi", 0.0)))

    if missing:
        print("\n  no STEP for: %s" % ", ".join(missing))
    if empty:
        print("  no triangles in: %s" % ", ".join(empty))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    scene.export(args.out)
    lo, hi = scene.bounds
    print("\n  %d parts, %s tris, %s verts in %.1fs"
          % (len(scene.geometry), format(total_t, ","), format(total_v, ","),
             time.time() - t0))
    print("  extent  %.2f x %.2f x %.2f mm" % tuple(hi - lo))
    print("  wrote   %s  (%.2f MB)" % (args.out, os.path.getsize(args.out) / 1048576.0))


if __name__ == "__main__":
    main()
