"""The OM10 drawn assembled, in plan, with every solid labelled where it sits.

    .venv-cad\Scripts\python.exe tools/om10_plan.py [zmin zmax]

The contact sheet says what each part looks like; this says where it is and what
it touches. Between them the escapement identifies itself: the escape wheel is
the small toothed thing the lever's stones reach, the lever is the only part in
a watch shaped like a lever, and both sit between the balance and the train.

The optional bounds select a slice through the movement's thickness (its axis is
Y in this export), which is how to see the escapement without the plates and
bridges on top of it.
"""

import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PolyCollection

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

YMIN = float(sys.argv[1]) if len(sys.argv) > 2 else -99.0
YMAX = float(sys.argv[2]) if len(sys.argv) > 2 else 99.0
TAG = sys.argv[3] if len(sys.argv) > 3 else "plan"
# Optional plan window: x0 x1 z0 z1. Parts outside it are dropped entirely, so
# the mainplate stops covering the thing being looked at.
WIN = [float(v) for v in sys.argv[4:8]] if len(sys.argv) > 7 else None
MAXD = float(sys.argv[8]) if len(sys.argv) > 8 else 99.0


def tris_of(shape, deflection=0.012):
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
        # Keep a part if any of it lies in the slice.
        if y1 < YMIN or y0 > YMAX:
            return
        if max(x1 - x0, z1 - z0) > MAXD:
            return
        if WIN and not (x1 > WIN[0] and x0 < WIN[1] and z1 > WIN[2] and z0 < WIN[3]):
            return
        name = nm(label)
        seen[name] = seen.get(name, 0) + 1
        tag = name if seen[name] == 1 else "%s#%d" % (name, seen[name])
        items.append((tag, max(x1 - x0, z1 - z0), (y0 + y1) / 2, tris_of(shp)))

    for i in range(1, free.Length() + 1):
        visit(free.Value(i), TopLoc_Location())

    # Big things first so small ones land on top of them.
    items.sort(key=lambda it: -it[1])
    print("plotting %d solids in y [%.2f, %.2f]" % (len(items), YMIN, YMAX), flush=True)

    fig, ax = plt.subplots(figsize=(17, 17))
    ax.set_facecolor("#14141a")
    cmap = plt.get_cmap("turbo")
    for k, (tag, dia, ymid, tris) in enumerate(items):
        if not tris:
            continue
        col = cmap((k * 0.137) % 1.0)
        ax.add_collection(PolyCollection(tris, facecolors=[col], edgecolors="none",
                                         alpha=0.40, linewidths=0))
        pts = np.array([p for t in tris for p in t])
        cx, cz = pts[:, 0].mean(), pts[:, 1].mean()
        ax.annotate("%s\n%.1fmm y%.1f" % (tag, dia, ymid), (cx, cz),
                    fontsize=7.0, color="white", ha="center", va="center",
                    bbox=dict(boxstyle="round,pad=0.12", fc="#000000a0", ec="none"))

    if WIN:
        ax.set_xlim(WIN[0], WIN[1])
        ax.set_ylim(WIN[2], WIN[3])
    else:
        ax.set_xlim(-17, 17)
        ax.set_ylim(-17, 17)
    ax.set_aspect("equal")
    ax.set_title("OM10 plan, y slice [%.2f, %.2f]" % (YMIN, YMAX), color="white")
    ax.tick_params(colors="#888")
    path = os.path.join(OUT, "%s.png" % TAG)
    fig.savefig(path, dpi=110, facecolor="#14141a", bbox_inches="tight")
    print("wrote %s" % path, flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
