"""Assembles the OM10 into one glTF binary for the real-time renderer.

    python tools/om10_extract_all.py       # once: captures/om10/all/*.step + catalogue.json
    python tools/gltf_export.py            # -> Assets/movement.glb, Assets/movement-parts.json
    python tools/gltf_export.py --deflection 0.02   # coarser tessellation

WHAT THIS IS FOR. The live face lights the movement per frame on the GPU, so
the movement has to be GEOMETRY rather than the flat PNG layers the sprite
face used. This writes every solid of the OM10 out, named, world-placed, as
one GLB the renderer keys its materials and its rotation map on.

WHICH PARTS. All of them. The first version of this file took 23 curated
parts - the ones the aperture showed - and named them by hand; the
direction of travel is now an object that could be made and that keeps its
own time, which needs the barrel, the keyless works, the motion works and the
stem too, and it needs them without anybody guessing which OM10-xxxxx is
which. So every solid in captures/om10/all goes in, under a readable name
where one is known (NAMES, from the release notes and the geometry) and its
source id otherwise. Parts under the dial cost triangles and nothing else;
the renderer draws them and the dial hides them.

THE FRAME. In the OM10's own STEP the plate lies in the (x, z) plane and y
is its thickness, +y toward the DIAL. The stem runs along -z, and with the
crown at the wearer's right that makes -z three o'clock and -x twelve. The
renderer's world is X right, Y toward the viewer, Z down the dial. So:

    world X = -cad z        (three o'clock)
    world Y =  cad y        (toward the viewer)
    world Z =  cad x        (six o'clock)

which is a proper rotation (determinant +1), applied once here. No consumer
should touch the axes; if the movement imports wrongly oriented, the
consumer is double-converting. The plate centre (0, 0) is the hands' arbor -
the cannon pinion and hour wheel sit there - and it lands at the world
origin, which is the dial centre.

NORMALS COME FROM THE SURFACE, never from the triangles. Every vertex is
handed the exact analytic normal of the CAD surface at its own UV, so
tessellation density changes the silhouette and never the shading.

UNITS ARE MILLIMETRES.
"""

import argparse
import json
import os
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
PARTS = os.path.join(ROOT, "captures", "om10", "all")
OUT = os.path.join(ROOT, "Assets", "movement.glb")

# Source id -> name. From OM10_Release_notes.pdf where it names a part, and
# from the geometry (position, size, count) where it does not. A part not
# listed keeps its id. Instances (#2, #3...) of a listed id get the name with
# the instance suffix.
NAMES = {
    "OM10-00214": "mainplate",
    "OM10-00184": "bridge",          # pont de rouage, the train bridge
    "OM10-00199": "barrel_bridge",
    "OM10-00196": "cock",            # coq, the balance cock
    "OM10-00113": "balance",
    "OM10-00115": "hairspring",
    "OM10-00110": "roller",
    "OM10-00112": "staff",
    "OM10-00116": "collet",
    "OM10-00104": "lever",           # ancre, the pallet fork
    "OM10-00106": "stone_a",         # entry pallet
    "OM10-00106#2": "stone_b",       # exit pallet
    "OM10-00105": "guard",           # dart
    "OM10-00107": "lever_staff",    # runs in the fork's own two jewels (docs/om10-fits.md); was taken for the impulse pin
    "OM10-00111": "impulse_pin",    # 0.32 across, on the roller's underside, half a millimetre off the balance axis
    "OM00-00101": "escape",
    "OM10-00146": "epinion",
    "OM10-00150": "wheel_centre",    # grande moyenne: barrel drives it, once an hour
    "OM10-00149": "pinion_centre",
    "OM10-00162": "wheel_third",
    "OM10-00161": "pinion_third",
    "OM10-00165": "wheel_seconds",   # roue de seconde: once a minute, small seconds at nine
    "OM10-00164": "pinion_seconds",
    "OM10-00152": "intermediate",    # roue intermediaire: centre wheel -> cannon pinion, 3/hour
    "OM10-00156": "intermediate_pinion",
    "OM10-00127": "cannon_pinion",   # chaussee, at the plate centre, once an hour
    "OM10-00128": "cannon_wheel",    # planche de chaussee
    "OM10-00206": "hour_wheel",
    "OM10-00159": "minute_wheel",    # planche de minuterie
    "OM10-00158": "minute_wheel_pinion",
    "OM10-00121": "barrel",
    "OM10-00120": "mainspring",      # the strip itself, 0.103 x 1.50, 11.8 coils; was taken for a drum
    "OM10-00119": "barrel_cover",
    "OM10-00118": "barrel_arbor",
    # 00197 was first taken for the mainspring. It is a 5.9 mm disc, 0.48
    # thick, on the BACK, meshing the crown wheel 00195 at 8.5 mm: the
    # ratchet wheel. The mainspring is 00120, above.
    "OM10-00197": "ratchet_wheel",
    "OM10-00225": "stem",
    "OM10-00217": "date_plate",      # plaque quantieme
    "OM10-00138": "dial_rest",       # trottoir
    "OM10-00222": "setting_lever",   # tirette
    "OM10-00306": "keyless_cover",   # couvre meca
    "OM10-00307": "keyless_bridge",  # pont de meca
    "OM10-00308": "setting_lever_screw",
    "OM00-00124": "jewel",
    "OM00-00106": "screw_a",         # 1.60 x 1.96, twelve of them
    "OM00-00107": "screw_b",
    "OM00-00111": "screw_c",
    "OM00-00108": "screw_d",
    # Each screw family has an insert sitting at the same spot: the threaded
    # bush the screw goes into. Same count, same positions.
    "OM00-00112": "insert_a",
    "OM00-00121": "insert_b",
    "OM00-00141": "insert_d",
    "OM10-00144": "washer",
    # The balance's shock settings, one each side. Dial side at y 1.0-1.6,
    # cock side at y -2.2 to -1.5; block, cap jewel, hole jewel, spring, by size.
    "OM00-00118": "shock_block_dial",
    "OM00-00116": "shock_capstone_dial",
    "OM00-00115": "shock_jewel_dial",
    "OM00-00114": "shock_spring_dial",
    "OM00-00137": "shock_block_cock",
    "OM00-00135": "shock_setting_cock",
    "OM00-00134": "shock_jewel_cock",
    "OM00-00133": "shock_capstone_cock",
    "OM00-00132": "shock_spring_cock",
    # The raquetterie on the cock, by the release notes' word and position.
    "OM00-00125": "regulator",
    "OM00-00126": "regulator_boot",
    "OM00-00129": "stud_carrier",
    "OM00-00127": "stud",            # at the hairspring's outer end, 3.1 mm from the staff
    # Bearings: thin settings at each arbor, dial side and back.
    "OM00-00120": "barrel_bearing",
    "OM00-00140": "centre_bearing",
    "OM00-00122": "train_bearing",
    "OM00-00145": "train_bearing_back",
    "OM00-00123": "intermediate_bearing",   # bored open on export: see BORED
    "OM00-00138": "centre_post",             # the cannon pinion turns on it, 0.011 clear (docs/om10-unnamed.md)
    # The keyless works and setting train, on the stem's axis and beside it.
    "OM10-00194": "winding_pinion",
    "OM10-00242": "sliding_pinion",
    "OM10-00195": "crown_wheel",     # meshes the ratchet at 8.5 mm
    "OM10-00220": "crown_wheel_core",
    "OM10-00228": "setting_wheel",
    "OM10-00235": "setting_wheel_post",
    "OM10-00229": "setting_wheel_2",
    "OM10-00230": "setting_wheel_2_upper",
    "OM10-00236": "yoke",
    "OM10-00232": "setting_lever_spring",
    "OM10-00238": "yoke_spring",
    "OM00-00109": "keyless_pin",
    # The date works on the dial side, around the hour wheel: unused by this
    # face and static, named so they are not mistaken for the going train.
    "OM10-00207": "date_wheel",
    "OM10-00212": "date_wheel_2",
    "OM10-00213": "date_wheel_3",
    "OM10-00215": "date_wheel_3_post",
    "OM10-00204": "date_jumper",
    "OM10-00209": "date_jumper_spring",
    "OM10-00210": "date_jumper_spring_2",
    "OM10-00142": "click",
    # Fixings round the rim.
    "OM00-00142": "case_clamp",
    "OM00-00139": "locating_pin",
    "OM00-00100": "pin",
    "OM00-00110": "clamp_plate",
    "OM00-00113": "clamp_post",
}


def tessellate_shape(shape, deflection=0.004, angular=0.10):
    """An OCP shape -> (vertices, normals, faces), normals off the surface.

    Shared with tools/case_solids.py, which builds the case in build123d and
    hands over `.wrapped` - so the case and the movement go through one
    tessellator and one normal rule, and a chamfer on the bezel is lit exactly
    the way a chamfer on the bridge is.
    """
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


def read_step(path):
    reader = STEPControl_Reader()
    reader.ReadFile(path)
    reader.TransferRoots()
    return reader.OneShape()


def tessellate(path, deflection, angular):
    return tessellate_shape(read_step(path), deflection, angular)


# ---------------------------------------------------------------- the open heart
#
# The OM10 is not an open-heart movement: from the dial side its balance sits
# under the plate, the date plate and the dial rest. An open heart is made by
# CUTTING those away over the balance, which is what every maker of one does
# to a stock movement, and it is done here to the copies we export rather
# than to the OM10 itself. The window is the aperture's circle, straight
# through from the dial face down to just above the balance rim.
#
# What is kept inside the window: a bar along the line of centres. The
# balance staff, the pallet staff and the escape wheel all have their
# dial-side jewels seated in the plate, and cutting the plate away would leave
# three jewels floating. The bar carries them - it is the "thin arm over the
# balance" the sprite face had for the same reason - and it runs from past
# the staff to past the escape wheel, 1.6 mm wide, as tall as the seats.
#
# Everything in the OM10's own frame: (x, z) is the plate, y the thickness.
OPEN_HEART_CENTRE = (-6.75, 4.83)      # cad (x, z): world (-4.83, -6.75)
OPEN_HEART_R = 10.75                   # case_solids.DIAL_HOLE_R: clears the well wall's outside
OPEN_HEART_FLOOR_Y = -0.05             # just above the balance rim (y -0.13)
OPEN_HEART_TOP_Y = 5.0                 # above the plate's dial face (4.41)
LINE_OF_CENTRES = ((-8.06, 3.51), (-3.68, 7.90))   # staff, escape wheel
BAR_WIDTH = 1.6
BAR_TOP_Y = 1.85                       # the jewel seats end at 1.65
BAR_CLEAR_OF_WALL = 0.60               # the well wall is 0.5 thick inside the window's edge, plus clearance
# The parts the window is cut through: the plate and the two dial-side plates
# over it. Nothing that moves, nothing that is a jewel.
OPEN_HEART_CUT = {"mainplate", "date_plate", "dial_rest"}

# Bores opened on export: a defect in the STEP itself. The 2021/02/01
# release note enlarges the seconds and intermediate pivots from 0.167 to
# 0.190; the intermediate's lower bearing was opened to match (0.2012) and
# its upper one was not (0.1812), an interference of 0.0096 mm on the
# diameter (docs/om10-fits.md). Opened here to the lower bearing's bore, on
# the intermediate's axis, CAD (x, z) with the bore along y.
BORED = {"intermediate_bearing": ((1.53, 4.125), 0.2012 / 2)}


def bore_open(shape, axis_xz, radius):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    cyl = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(axis_xz[0], -10.0, axis_xz[1]), gp_Dir(0, 1, 0)), radius, 20.0).Shape()
    return BRepAlgoAPI_Cut(shape, cyl).Shape()


def prepared(name, shape):
    """Every change made to an OM10 solid on its way out: the open-heart
    cut and the opened bore. The assembly check uses the same one."""
    if name in OPEN_HEART_CUT:
        shape = open_heart(shape)
    if name in BORED:
        shape = bore_open(shape, *BORED[name])
    return shape


def open_heart(shape):
    """The window cut into one dial-side part, keeping the bar."""
    from build123d import Axis, Box, Cylinder, Location, Part, Plane, Rotation
    import math
    part = Part(shape)
    cx, cz = OPEN_HEART_CENTRE
    height = OPEN_HEART_TOP_Y - OPEN_HEART_FLOOR_Y
    window = Cylinder(OPEN_HEART_R, height, align=(None, None, None))
    # A cylinder is built along Z; the plate's thickness is Y, so lay it on
    # its side and centre it on the window at mid height.
    window = window.moved(Location((cx, (OPEN_HEART_TOP_Y + OPEN_HEART_FLOOR_Y) / 2, cz), (90, 0, 0)))
    (x0, z0), (x1, z1) = LINE_OF_CENTRES
    length = math.hypot(x1 - x0, z1 - z0) + 2 * 2.6
    angle = math.degrees(math.atan2(z1 - z0, x1 - x0))
    bar = Box(length, BAR_TOP_Y - OPEN_HEART_FLOOR_Y, BAR_WIDTH, align=(None, None, None))
    bar = bar.moved(Location(((x0 + x1) / 2, (BAR_TOP_Y + OPEN_HEART_FLOOR_Y) / 2, (z0 + z1) / 2), (0, -angle, 0)))
    # The bar stops short of the well wall, which stands in the outer half
    # millimetre of the window; the assembly check found the bar's end
    # inside the wall.
    inside = Cylinder(OPEN_HEART_R - BAR_CLEAR_OF_WALL, height, align=(None, None, None))
    inside = inside.moved(Location((cx, (OPEN_HEART_TOP_Y + OPEN_HEART_FLOOR_Y) / 2, cz), (90, 0, 0)))
    bar = bar & inside
    return (part - (window - bar)).wrapped


def om10_to_world(verts, norms):
    """The OM10's (x, y, z) -> the renderer's (X, Y, Z) = (-z, y, x)."""
    verts = np.column_stack((-verts[:, 2], verts[:, 1], verts[:, 0]))
    norms = np.column_stack((-norms[:, 2], norms[:, 1], norms[:, 0]))
    return verts, norms


def zup_to_yup(verts, norms):
    """build123d is Z-up; glTF is Y-up. Rotate -90 about X: (x, y, z) -> (x, z, -y).
    Used by case_solids.py, whose CAD frame is x right, y up the dial."""
    verts = np.column_stack((verts[:, 0], verts[:, 2], -verts[:, 1]))
    norms = np.column_stack((norms[:, 0], norms[:, 2], -norms[:, 1]))
    return verts, norms


def write_glb(parts, out):
    """parts: list of (name, verts, norms, faces, (colour, metal, rough)) already
    in the renderer's Y-up world. One named node per part."""
    scene = trimesh.Scene()
    for name, verts, norms, faces, (colour, metal, rough) in parts:
        mesh = trimesh.Trimesh(vertices=np.asarray(verts, float), faces=faces,
                               vertex_normals=np.asarray(norms, float), process=False)
        mesh.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                name=name, baseColorFactor=[colour[0], colour[1], colour[2], 1.0],
                metallicFactor=metal, roughnessFactor=rough))
        scene.add_geometry(mesh, geom_name=name, node_name=name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    scene.export(out)
    return scene


# What the front of the watch can see: the aperture's contents and the plate
# they sit on. These get the fine tessellation; everything under the dial is
# there for the mechanism and is coarsened, which is the difference between
# a 39 MB asset and a 12 MB one at no visible cost.
VISIBLE = {
    "mainplate", "bridge", "cock", "balance", "hairspring", "roller", "staff", "collet",
    "lever", "lever_staff", "stone_a", "stone_b", "guard", "impulse_pin", "escape", "epinion",
    "wheel_seconds", "pinion_seconds", "wheel_third", "pinion_third", "jewel",
}
COARSE_FACTOR = 5.0


def name_of(tag):
    if tag in NAMES:
        return NAMES[tag]
    if "#" in tag:
        base, inst = tag.split("#")
        if base in NAMES:
            return "%s_%s" % (NAMES[base], inst)
    return tag


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--deflection", type=float, default=0.006,
                    help="linear deflection in MILLIMETRES (default 0.006)")
    ap.add_argument("--angular", type=float, default=0.12,
                    help="angular deflection in radians (default 0.12)")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    catalogue_path = os.path.join(PARTS, "catalogue.json")
    if not os.path.exists(catalogue_path):
        raise SystemExit("missing %s - run tools/om10_extract_all.py first" % catalogue_path)
    catalogue = json.load(open(catalogue_path))

    steel = ((0.680, 0.700, 0.740), 1.0, 0.16)
    parts, names = [], {}
    total = 0
    t0 = time.time()
    for tag in sorted(catalogue):
        path = os.path.join(PARTS, tag.replace("#", "_") + ".step")
        name = name_of(tag)
        fine = name in VISIBLE or name.split("_")[0] in VISIBLE
        if name == "hairspring":
            # The OM10's hairspring is a placeholder strip; ours is designed
            # for the measured balance and the train's rate. See hairspring.py.
            import hairspring
            shape = hairspring.build(hairspring.design())[0].wrapped
        else:
            shape = read_step(path)
        shape = prepared(name, shape)
        got = tessellate_shape(shape, args.deflection if fine else args.deflection * COARSE_FACTOR,
                               args.angular if fine else args.angular * 2.0)
        if got is None:
            print("  no triangles in", tag)
            continue
        verts, norms, faces = got
        verts, norms = om10_to_world(verts, norms)
        if name in names:
            raise SystemExit("duplicate name %s for %s and %s" % (name, names[name], tag))
        names[name] = tag
        parts.append((name, verts, norms, faces, steel))
        total += len(faces)

    write_glb(parts, args.out)
    print("  %d parts, %s tris in %.1fs" % (len(parts), format(total, ","), time.time() - t0))
    print("  wrote %s (%.2f MB)" % (args.out, os.path.getsize(args.out) / 1048576.0))
    # The names the renderer can key on, with where each part sits.
    with open(os.path.join(ROOT, "Assets", "movement-parts.json"), "w") as f:
        json.dump({name: ({"source": tag, **catalogue[tag]} if tag in catalogue else {"source": tag}) for name, tag in names.items()}, f, indent=1)


if __name__ == "__main__":
    main()
