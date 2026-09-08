"""Every solid in the OM10 STEP, extracted and catalogued.

    python tools/om10_extract_all.py     # -> captures/om10/all/*.step + catalogue.json

WHY A SECOND EXTRACTOR. om10_extract.py takes a curated list of 23 parts, the
ones the aperture showed, and names them. That was right while the face was a
picture of an escapement. The direction of travel now is an object that could
be made and that keeps its own time, which needs the barrel and its bridge,
the keyless works, the motion works and the stem - and it needs them without
anybody guessing which OM10-xxxxx is which. So this writes all 166 solids out
by their source id, world-placed, with a catalogue of where each sits: its
turning axis in the plate's plane, its height range, its bounding box and
volume. Naming is done afterwards, in the catalogue, against the release
notes (OM10_Release_notes.pdf names the parts in French) and the geometry.

THE FRAME, measured off the file rather than assumed: the plate lies in the
CAD's (x, z) plane and y is its thickness. +y is the DIAL side - the date
plate (00217) and hour wheel (00206) sit at +y, the balance cock (00196) at
-y. The stem (00225) runs along -z from the plate's rim, so with the crown at
the wearer's right, -z is three o'clock and -x is twelve. The balance at
(-8.06, +3.51) is therefore under eleven o'clock, and the seconds wheel at
(0, +8) is at nine. The original file is at
captures/om10/om10-00001_20220701_va_01_3.stp (gitignored, 18.8 MB), copied
from the owner's OneDrive on 2026-09-08.
"""

import json
import os

from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDF import TDF_LabelSequence, TDF_Label
from OCP.TDataStd import TDataStd_Name
from OCP.TopLoc import TopLoc_Location
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STEP = os.path.join(ROOT, "captures", "om10", "om10-00001_20220701_va_01_3.stp")
OUT = os.path.join(ROOT, "captures", "om10", "all")


def load(step):
    doc = TDocStd_Document(TCollection_ExtendedString("om10"))
    rd = STEPCAFControl_Reader()
    rd.SetNameMode(True)
    rd.ReadFile(step)
    rd.Transfer(doc)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    free = TDF_LabelSequence()
    tool.GetFreeShapes(free)

    def name_of(label):
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
        name = name_of(label)
        seen[name] = seen.get(name, 0) + 1
        tag = name if seen[name] == 1 else "%s#%d" % (name, seen[name])
        found[tag] = shp.Moved(loc)

    for i in range(1, free.Length() + 1):
        visit(free.Value(i), TopLoc_Location())
    return found


def main():
    if not os.path.exists(STEP):
        raise SystemExit("missing %s - copy the OM10 STEP there first" % STEP)
    os.makedirs(OUT, exist_ok=True)
    found = load(STEP)
    print("assembly holds %d solids" % len(found))

    catalogue = {}
    for tag, shape in sorted(found.items()):
        box = Bnd_Box()
        BRepBndLib.Add_s(shape, box)
        x0, y0, z0, x1, y1, z1 = box.Get()
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, props)
        c = props.CentreOfMass()
        catalogue[tag] = {
            # The turning axis, for a round part: the bounding box centre in
            # the plate's plane. For an eccentric part it is only its middle.
            "axis": [round((x0 + x1) / 2, 3), round((z0 + z1) / 2, 3)],
            "y": [round(y0, 3), round(y1, 3)],
            "bbox": [round(v, 3) for v in (x0, y0, z0, x1, y1, z1)],
            "volume": round(props.Mass(), 3),
            "centroid": [round(c.X(), 3), round(c.Y(), 3), round(c.Z(), 3)],
        }
        safe = tag.replace("#", "_")
        writer = STEPControl_Writer()
        writer.Transfer(shape, STEPControl_AsIs)
        writer.Write(os.path.join(OUT, safe + ".step"))

    with open(os.path.join(OUT, "catalogue.json"), "w") as f:
        json.dump(catalogue, f, indent=1)
    print("wrote %d parts and catalogue.json to %s" % (len(catalogue), OUT))


if __name__ == "__main__":
    main()
