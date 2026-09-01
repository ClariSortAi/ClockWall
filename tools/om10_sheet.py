"""Contact sheet of every OM10 solid, drawn as its own plan silhouette.

    .venv-cad\Scripts\python.exe tools/om10_sheet.py

Reading a table of bounding boxes to work out which solid is the escape wheel is
a good way to convince yourself of something wrong. This draws all 166 of them
at a common scale, labelled, so the balance, the lever and the escape wheel are
identified by looking at them - which for shapes this distinctive takes a second
each and is not a judgement call.
"""

import json
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_LabelSequence, TDF_Label
from OCP.TDataStd import TDataStd_Name
from OCP.TopLoc import TopLoc_Location
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location as Loc
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEP = r"C:\Users\jason\Downloads\om10-00001_20220701_va_01_3.stp"
OUT = os.path.join(ROOT, "captures", "om10")
MIN_DIA = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0


def tris_of(shape, deflection=0.01):
    BRepMesh_IncrementalMesh(shape, deflection, False, 0.2, True)
    out = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        loc = Loc()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None:
            t = loc.Transformation()
            nd = [tri.Node(i + 1).Transformed(t) for i in range(tri.NbNodes())]
            for i in range(tri.NbTriangles()):
                a, b, c = tri.Triangle(i + 1).Get()
                out.append([(nd[a - 1].X(), nd[a - 1].Z()),
                            (nd[b - 1].X(), nd[b - 1].Z()),
                            (nd[c - 1].X(), nd[c - 1].Z())])
        exp.Next()
    return out


def main():
    doc = TDocStd_Document(TCollection_ExtendedString("om10"))
    r = STEPCAFControl_Reader()
    r.SetNameMode(True)
    r.ReadFile(STEP)
    r.Transfer(doc)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    free = TDF_LabelSequence()
    tool.GetFreeShapes(free)

    def nm(label):
        a = TDataStd_Name()
        return a.Get().ToExtString() if label.FindAttribute(TDataStd_Name.GetID_s(), a) else "?"

    items, seen = [], {}

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
        shp = shp.Moved(loc)
        box = Bnd_Box()
        BRepBndLib.Add_s(shp, box)
        if box.IsVoid():
            return
        x0, y0, z0, x1, y1, z1 = box.Get()
        dia = max(x1 - x0, z1 - z0)
        if dia < MIN_DIA:
            return
        name = nm(label)
        seen[name] = seen.get(name, 0) + 1
        tag = name if seen[name] == 1 else "%s#%d" % (name, seen[name])
        items.append((tag, dia, y1 - y0, tris_of(shp)))

    for i in range(1, free.Length() + 1):
        visit(free.Value(i), TopLoc_Location())

    items.sort(key=lambda it: -it[1])
    print("drawing %d solids >= %.1f mm" % (len(items), MIN_DIA), flush=True)

    cols = 8
    rows = (len(items) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.1, rows * 2.25))
    axes = np.atleast_2d(axes)
    for ax in axes.flat:
        ax.axis("off")

    from matplotlib.collections import PolyCollection
    for k, (tag, dia, thick, tris) in enumerate(items):
        ax = axes[k // cols][k % cols]
        if not tris:
            continue
        pc = PolyCollection(tris, facecolors="#c9a227", edgecolors="none",
                            alpha=0.34, linewidths=0)
        ax.add_collection(pc)
        pts = np.array([p for t in tris for p in t])
        cx, cz = pts[:, 0].mean(), pts[:, 1].mean()
        h = dia * 0.62
        ax.set_xlim(cx - h, cx + h)
        ax.set_ylim(cz - h, cz + h)
        ax.set_aspect("equal")
        ax.set_title("%s\n%.2f x %.2f mm" % (tag, dia, thick), fontsize=6.5, pad=2)
        ax.axis("off")

    path = os.path.join(OUT, "contact-sheet.png")
    fig.tight_layout()
    fig.savefig(path, dpi=118, facecolor="#14141a")
    print("wrote %s" % path, flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
