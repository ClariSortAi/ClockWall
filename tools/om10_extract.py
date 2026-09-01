"""Lifts the parts we need out of the OM10 assembly, into the render's frame.

    .venv-cad\\Scripts\\python.exe tools/om10_extract.py

SOURCE. openmovement.org's OM10, the first open-source mechanical Swiss
movement. Real B-rep out of Inventor, so these are not meshes of a photograph of
a watch - they are the solids a watch would be cut from, with the chamfers and
the turned steps actually present. That is the whole reason to use them. A
straight-down camera can only shade an interior wall or a chamfer, and every one
of ours was invented; these are measured.

FRAMES. OM10 lies down: its movement plane is XZ and its axis is Y, with more
negative Y further toward the back of the watch. Everything here comes out in
the render's frame instead - plane XY, thickness up in +Z - and centred on the
part's OWN AXIS OF ROTATION rather than on its bounding box. That distinction is
the entire point of the AXES table below. A wheel's bounding box centre is not
its pivot, because club teeth lean forward, so hanging a wheel on its bbox
centre bakes a half-tooth wobble into something that should run perfectly true.

WHAT COMES OUT. One binary STL and one STEP per part in captures/om10/parts/,
each about its own axis with its underside on z=0, plus manifest.json carrying
the real millimetre radius, thickness and tooth count. Nothing here knows about
the face layout - cad_parts.py does the scaling and the placing.

RUN om10_check.py AFTER THIS, ALWAYS. The tooth counts written here are
PROVISIONAL. They come off raw triangulation vertices, which cluster wherever
the tessellator chose and leave angular gaps that read as gullets, so this
undercounts and often gives up entirely - it scores the escape wheel as having
no teeth at all. om10_check.py recounts by sampling the surface uniformly by
AREA and overwrites them. Re-running this script therefore puts the bad numbers
back, which is a quiet way to end up with a train ratio of zero.
"""

import json
import math
import os
import sys

import numpy as np
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_LabelSequence, TDF_Label
from OCP.TDataStd import TDataStd_Name
from OCP.TopLoc import TopLoc_Location
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.gp import gp_Trsf, gp_Vec
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool
from OCP.StlAPI import StlAPI_Writer
from OCP.STEPControl import STEPControl_Writer, STEPControl_StepModelType
from OCP.Interface import Interface_Static

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEP = r"C:\Users\jason\Downloads\om10-00001_20220701_va_01_3.stp"
OUT = os.path.join(ROOT, "captures", "om10", "parts")

# The arbors, read off the assembly. A part is centred on the axis it turns
# about, not on the middle of its own bounding box. Balance, pallet staff and
# escape wheel are collinear here, with the staff at the midpoint - which is
# what a Swiss lever escapement is, and is not what our own layout assumed.
AXES = {
    "balance": (-8.06, 3.51),
    "pallet": (-5.87, 5.71),
    "escape": (-3.68, 7.90),
}

# solid -> (output name, the arbor it turns about or None to keep its own centre)
WANTED = [
    ("OM10-00113", "balance", "balance"),      # balance wheel
    ("OM10-00115", "hairspring", "balance"),   # the spiral
    ("OM10-00110", "roller", "balance"),       # roller table
    ("OM10-00112", "staff", "balance"),        # balance staff
    ("OM10-00116", "collet", "balance"),       # hairspring collet
    ("OM10-00104", "lever", "pallet"),         # pallet fork
    ("OM10-00106", "stone_a", None),           # entry pallet jewel
    ("OM10-00106#2", "stone_b", None),         # exit pallet jewel
    ("OM10-00105", "guard", None),             # guard dart at the fork end
    ("OM00-00101", "escape", "escape"),        # escape wheel
    ("OM10-00146", "epinion", "escape"),       # escape pinion
    ("OM10-00196", "cock", None),              # balance cock
    ("OM10-00150", "wheel_a", None),           # train wheel, 6 crossings
    ("OM10-00162", "wheel_b", None),           # train wheel, 5 crossings
    ("OM10-00165", "wheel_c", None),           # train wheel, 5 crossings
    ("OM10-00152", "pinion_a", None),
    ("OM10-00164", "pinion_b", None),
    ("OM00-00106", "screw_a", None),           # screw, 1.60 x 1.96
    ("OM00-00107", "screw_b", None),
    ("OM00-00111", "screw_c", None),
    ("OM00-00124", "jewel", None),             # jewel, 1.01 x 0.26
    ("OM10-00214", "mainplate", None),
    ("OM10-00184", "bridge", None),            # train bridge, for its anglage
]


def tris_of(shape, deflection=0.004):
    """Triangles of a shape, world coordinates, as a list of 3x3 tuples."""
    BRepMesh_IncrementalMesh(shape, deflection, False, 0.12, True)
    out = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None:
            t = loc.Transformation()
            nd = [tri.Node(i + 1).Transformed(t) for i in range(tri.NbNodes())]
            for i in range(tri.NbTriangles()):
                a, b, c = tri.Triangle(i + 1).Get()
                out.append([(nd[a - 1].X(), nd[a - 1].Y(), nd[a - 1].Z()),
                            (nd[b - 1].X(), nd[b - 1].Y(), nd[b - 1].Z()),
                            (nd[c - 1].X(), nd[c - 1].Y(), nd[c - 1].Z())])
        exp.Next()
    return out


def teeth_of(pts, bins=3600):
    """
    Tooth count of a wheel already centred on its own axis, in the XY plane.

    Outer radius as a function of angle is a near-square wave whose period IS
    the tooth pitch, so its Fourier transform has one unmistakable peak. What
    makes the answer trustworthy rather than a guess is the margin: the peak has
    to stand well clear of the rest of the band, with its own harmonics masked
    out of the comparison. A smooth rim - a balance - produces no peak, and
    correctly answers zero rather than answering noise.
    """
    r = np.hypot(pts[:, 0], pts[:, 1])
    if len(r) < 64 or r.max() <= 0:
        return 0, 0.0
    a = (np.arctan2(pts[:, 1], pts[:, 0]) + 2 * math.pi) % (2 * math.pi)
    idx = np.minimum((a / (2 * math.pi) * bins).astype(int), bins - 1)
    prof = np.zeros(bins)
    np.maximum.at(prof, idx, r)
    ok = prof > 0
    if ok.sum() < bins * 0.6:
        return 0, 0.0
    prof = np.interp(np.arange(bins), np.flatnonzero(ok), prof[ok], period=bins)

    spec = np.abs(np.fft.rfft(prof - prof.mean()))
    lo, hi = 6, 200
    band = spec[lo:hi]
    k = lo + int(np.argmax(band))
    peak = band.max()
    mask = np.ones_like(band, dtype=bool)
    for h in range(1, 5):
        c = h * k - lo
        if 0 <= c < len(band):
            mask[max(0, c - 2):c + 3] = False
    floor = np.median(band[mask]) if mask.any() else 1.0
    return int(k), float(peak / max(floor, 1e-9))


def main():
    os.makedirs(OUT, exist_ok=True)
    print("reading OM10 (%.1f MB)" % (os.path.getsize(STEP) / 1e6), flush=True)
    doc = TDocStd_Document(TCollection_ExtendedString("om10"))
    rd = STEPCAFControl_Reader()
    rd.SetNameMode(True)
    rd.ReadFile(STEP)
    rd.Transfer(doc)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    free = TDF_LabelSequence()
    tool.GetFreeShapes(free)

    def nm(label):
        a = TDataStd_Name()
        if label.FindAttribute(TDataStd_Name.GetID_s(), a):
            return a.Get().ToExtString()
        return "?"

    found, seen = {}, {}

    def visit(label, loc):
        if tool.IsAssembly_s(label):
            comps = TDF_LabelSequence()
            tool.GetComponents_s(label, comps)
            for i in range(1, comps.Length() + 1):
                c = comps.Value(i)
                sub = loc * tool.GetLocation_s(c)
                ref = TDF_Label()
                if tool.GetReferredShape_s(c, ref):
                    visit(ref, sub)
                else:
                    take(c, sub)
        else:
            take(label, loc)

    def take(label, loc):
        shp = tool.GetShape_s(label)
        if shp.IsNull():
            return
        name = nm(label)
        seen[name] = seen.get(name, 0) + 1
        tag = name if seen[name] == 1 else "%s#%d" % (name, seen[name])
        found[tag] = shp.Moved(loc)

    for i in range(1, free.Length() + 1):
        visit(free.Value(i), TopLoc_Location())

    print("assembly holds %d solids\n" % len(found), flush=True)

    manifest = {}
    writer = StlAPI_Writer()
    writer.ASCIIMode = False

    for src, out_name, arbor in WANTED:
        if src not in found:
            print("  MISSING %s" % src, flush=True)
            continue
        shape = found[src]
        box = Bnd_Box()
        BRepBndLib.Add_s(shape, box)
        x0, y0, z0, x1, y1, z1 = box.Get()

        if arbor:
            ax, az = AXES[arbor]
        else:
            ax, az = (x0 + x1) / 2, (z0 + z1) / 2

        # OM10 (x, y, z) -> render (x - ax, z - az, -y): the movement plane
        # becomes XY, thickness runs up in +Z, and the part sits on its axis.
        t = gp_Trsf()
        t.SetValues(1, 0, 0, -ax,
                    0, 0, 1, -az,
                    0, -1, 0, 0)
        moved = BRepBuilderAPI_Transform(shape, t, True).Shape()

        nbox = Bnd_Box()
        BRepBndLib.Add_s(moved, nbox)
        nx0, ny0, nz0, nx1, ny1, nz1 = nbox.Get()

        # Keep where this part really sits through the movement's thickness
        # BEFORE flattening it, because the stacking order is not ours to
        # invent: OM10 puts the hairspring above the balance and the lever
        # below the escape wheel, and those are the heights that make the
        # assembly possible rather than merely tidy.
        z_lo, z_hi = nz0, nz1

        # Drop it onto z = 0, so a stack is built by adding thicknesses.
        t2 = gp_Trsf()
        t2.SetTranslation(gp_Vec(0, 0, -nz0))
        moved = BRepBuilderAPI_Transform(moved, t2, True).Shape()

        tris = tris_of(moved)
        pts = np.array([p for tri in tris for p in tri]) if tris else np.zeros((1, 3))
        teeth, conf = teeth_of(pts[:, :2])
        radius = float(np.hypot(pts[:, 0], pts[:, 1]).max())

        path = os.path.join(OUT, "%s.stl" % out_name)
        writer.Write(moved, path)

        # And the same solid as STEP. The STL is for the renderer, which wants
        # triangles; the STEP keeps the B-rep, which is what lets the assembly
        # be checked for real interference later instead of for overlapping
        # footprints. A mesh cannot answer "do these two solids share space".
        swriter = STEPControl_Writer()
        Interface_Static.SetCVal_s("write.step.unit", "MM")
        swriter.Transfer(moved, STEPControl_StepModelType.STEPControl_AsIs)
        swriter.Write(os.path.join(OUT, "%s.step" % out_name))

        manifest[out_name] = dict(
            source=src, radius=radius,
            dx=nx1 - nx0, dy=ny1 - ny0, thickness=nz1 - nz0,
            z_lo=z_lo, z_hi=z_hi,          # where it really sits, in mm
            axis=list(AXES[arbor]) if arbor else [(x0 + x1) / 2, (z0 + z1) / 2],
            teeth=teeth if conf > 6.0 else 0, tooth_conf=round(conf, 1),
            tris=len(tris), stl="%s.stl" % out_name)
        print("  %-11s <- %-12s r %6.3f  thick %5.3f  teeth %3d (x%6.1f)  %6d tris"
              % (out_name, src, radius, nz1 - nz0,
                 manifest[out_name]["teeth"], conf, len(tris)), flush=True)

    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print("\nwrote %s" % os.path.join(OUT, "manifest.json"), flush=True)
    sys.stdout.flush()
    os._exit(0)          # OCCT segfaults on teardown; the files are already written.


if __name__ == "__main__":
    main()
