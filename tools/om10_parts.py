"""Identifies every solid in the OM10 assembly and exports it for reuse.

    .venv-cad\Scripts\python.exe tools/om10_parts.py

The OM10 (openmovement.org) is a real open-source Swiss movement, and its STEP
export carries drawing numbers rather than names. Guessing which solid is the
escape wheel from its size is how you end up rendering the click spring as a
balance, so this identifies parts by the one property that cannot be mistaken:
ROTATIONAL SYMMETRY ORDER. Tessellate a solid, take the outline radius as a
function of angle about its own axis, and the dominant Fourier component IS the
tooth count. Fifteen is an escape wheel. Sixty-four is a train wheel. A balance
rim is smooth and answers zero, and nothing else in a watch is periodic at all.

Y is the movement's axis in this export (Inventor had it lying down), so the
watch plane is XZ. Everything here reports in that frame and the exporter
converts to the face frame on the way out.
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
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.TopLoc import TopLoc_Location
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location as Loc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEP = sys.argv[1] if len(sys.argv) > 1 else \
    r"C:\Users\jason\Downloads\om10-00001_20220701_va_01_3.stp"
OUT = os.path.join(ROOT, "captures", "om10")


def tessellate(shape, deflection=0.02):
    """Triangles of a shape, in world coordinates, as an (n,3,3) array."""
    BRepMesh_IncrementalMesh(shape, deflection, False, 0.3, True)
    tris = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        loc = Loc()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None:
            trsf = loc.Transformation()
            nodes = [tri.Node(i + 1).Transformed(trsf) for i in range(tri.NbNodes())]
            for i in range(tri.NbTriangles()):
                a, b, c = tri.Triangle(i + 1).Get()
                tris.append([[nodes[a - 1].X(), nodes[a - 1].Y(), nodes[a - 1].Z()],
                             [nodes[b - 1].X(), nodes[b - 1].Y(), nodes[b - 1].Z()],
                             [nodes[c - 1].X(), nodes[c - 1].Y(), nodes[c - 1].Z()]])
        exp.Next()
    return np.array(tris) if tris else np.zeros((0, 3, 3))


def symmetry(points, cx, cz, bins=1440):
    """
    Dominant rotational symmetry order of an outline about (cx, cz).

    The silhouette's OUTER radius per angular bin is the signal; its Fourier
    transform peaks at the tooth count. Teeth are a small ripple on a large
    mean radius, so the mean is removed first or it swamps everything.
    """
    x = points[:, 0] - cx
    z = points[:, 2] - cz
    r = np.hypot(x, z)
    if r.max() <= 0:
        return 0, 0.0
    a = (np.arctan2(z, x) + 2 * math.pi) % (2 * math.pi)
    idx = np.minimum((a / (2 * math.pi) * bins).astype(int), bins - 1)

    prof = np.zeros(bins)
    np.maximum.at(prof, idx, r)
    # Empty bins would read as deep gullets; fill them from their neighbours.
    filled = prof > 0
    if filled.sum() < bins * 0.5:
        return 0, 0.0
    prof = np.interp(np.arange(bins), np.flatnonzero(filled), prof[filled],
                     period=bins)

    spec = np.abs(np.fft.rfft(prof - prof.mean()))
    # Teeth live well above the few-fold symmetry of crossings and arms.
    lo, hi = 5, 130
    k = lo + int(np.argmax(spec[lo:hi]))
    strength = spec[k] / (len(prof) * max(prof.mean(), 1e-9) / 2)
    return k, float(strength)


def main():
    os.makedirs(OUT, exist_ok=True)
    print("reading %s (%.1f MB)" % (STEP, os.path.getsize(STEP) / 1e6), flush=True)
    doc = TDocStd_Document(TCollection_ExtendedString("om10"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.ReadFile(STEP)
    reader.Transfer(doc)

    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    free = TDF_LabelSequence()
    tool.GetFreeShapes(free)

    def name_of(label):
        attr = TDataStd_Name()
        if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
            return attr.Get().ToExtString()
        return "?"

    rows = []
    seen = {}

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
                    record(c, sub)
        else:
            record(label, loc)

    def record(label, loc):
        shape = tool.GetShape_s(label)
        if shape.IsNull():
            return
        shape = shape.Moved(loc)
        box = Bnd_Box()
        BRepBndLib.Add_s(shape, box)
        if box.IsVoid():
            return
        xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, props)
        com = props.CentreOfMass()

        nm = name_of(label)
        seen[nm] = seen.get(nm, 0) + 1
        tag = nm if seen[nm] == 1 else "%s#%d" % (nm, seen[nm])

        tris = tessellate(shape)
        pts = tris.reshape(-1, 3) if len(tris) else np.zeros((1, 3))
        cx, cz = (xmin + xmax) / 2, (zmin + zmax) / 2
        teeth, strength = symmetry(pts, cx, cz)

        rows.append(dict(
            tag=tag, part=nm,
            dia=max(xmax - xmin, zmax - zmin), thick=ymax - ymin,
            cx=cx, cy=com.Y(), cz=cz, ymin=ymin, ymax=ymax,
            vol=props.Mass(), teeth=int(teeth), sym=round(strength, 4),
            tris=len(tris)))

    for i in range(1, free.Length() + 1):
        visit(free.Value(i), TopLoc_Location())

    rows.sort(key=lambda r: -r["dia"])
    print("\n%d solids\n" % len(rows), flush=True)
    print("%-14s %7s %7s %8s %8s %8s %9s %6s %7s" %
          ("part", "dia", "thick", "cx", "cy", "cz", "vol", "teeth", "sym"))
    for r in rows:
        print("%-14s %7.2f %7.2f %8.2f %8.2f %8.2f %9.3f %6d %7.3f" %
              (r["tag"], r["dia"], r["thick"], r["cx"], r["cy"], r["cz"],
               r["vol"], r["teeth"], r["sym"]))

    with open(os.path.join(OUT, "parts.json"), "w") as f:
        json.dump(rows, f, indent=1)
    print("\nwrote %s" % os.path.join(OUT, "parts.json"))
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
