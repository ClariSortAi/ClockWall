"""The print set: every solid as an STL at print scale, bores opened.

    python tools/print_export.py                 # -> captures/print/<scale>x/*.stl + manifest.json
    python tools/print_export.py --scale 9       # a different uniform scale
    python tools/print_export.py --only case,dial,balance

WHY. PRINT-STUDY.md settles that this movement prints at about 3.4x on a
50 um resin machine and that the running fits, not the walls, govern; so
the bearings are bored open in the model first (tools/print_bores.py ->
Assets/print-bores.json) and the whole thing scaled after. This is the
last step: the assembled set - our case parts from case_solids.py and the
OM10's from the STEP, with the open-heart cut, the opened bores and the
designed hairspring, exactly as gltf_export.prepared has them - written
one STL per part, all in ONE frame at ONE scale, so the slicer's plate
shows the watch as assembled and nothing has to be lined up by eye.

WHAT IS NOT FOR PRINTING is still written, and marked in the manifest:
the two springs (the elasticity is the part; see PRINT-STUDY.md), the
jewels and capstones (bought). They are there so the assembly can be
checked in the slicer; delete them from the plate.

FRAME. case_solids.py's, the same as assembly_check.py: x right, y up
the dial, z toward the viewer, dial face at z = 0, millimetres times the
scale. The OM10's parts go through om10_to_case first.
"""

import argparse
import json
import os
import sys
import time

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.StlAPI import StlAPI_Writer
from OCP.gp import gp_Trsf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import assembly_check as A                                    # noqa: E402
import gltf_export as G                                       # noqa: E402

BORES = os.path.join(ROOT, "Assets", "print-bores.json")
OUT = os.path.join(ROOT, "captures", "print")
DEFLECTION = 0.01   # mm at 1x: a fiftieth of the finest fit the study opens to

NOT_FOR_PRINTING = {
    "hairspring": "a 0.035 mm spring strip; the elasticity is the part",
    "mainspring": "a 0.102 mm spring strip; the elasticity is the part",
}


def bought(name):
    return any(k in name for k in ("jewel", "capstone", "stone_"))


def load_bores():
    """The bore table from tools/print_bores.py, or None: this export works
    without one, at the study's scale, and says so in the manifest."""
    try:
        import print_bores
        return print_bores.load_bores(BORES)
    except ImportError:
        return None


def apply_bores(name, shape, bores):
    if not bores:
        return shape
    import print_bores
    return print_bores.apply_bore(name, shape, bores)


def scaled(shape, factor):
    t = gp_Trsf()
    t.SetScaleFactor(factor)
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def write_stl(shape, path, factor):
    BRepMesh_IncrementalMesh(shape, DEFLECTION * factor, False, 0.2, True)
    w = StlAPI_Writer()
    w.ASCIIMode = False
    if not w.Write(shape, path):
        raise RuntimeError("could not write " + path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scale", type=float, help="uniform scale; default the bore table's, else 3.4")
    ap.add_argument("--only", help="comma-separated part names")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    bores = load_bores()
    factor = args.scale or (bores["scale"] if bores and "scale" in bores else 3.4)
    only = set(args.only.split(",")) if args.only else None
    out = os.path.join(args.out, "%gx" % round(factor, 3))
    os.makedirs(out, exist_ok=True)

    t0 = time.time()
    parts = {}
    for name, shape in A.load_case().items():
        parts[name] = ("case_solids.py", shape)
    inv = {v: k for k, v in G.NAMES.items()}
    trsf = A.om10_to_case()
    for name, tag in inv.items():
        path = os.path.join(G.PARTS, tag.replace("#", "_") + ".step")
        if not os.path.exists(path):
            continue
        if name == "hairspring":
            import hairspring
            shape = hairspring.build(hairspring.design())[0].wrapped
        else:
            shape = G.read_step(path)
        shape = apply_bores(name, G.prepared(name, shape), bores)
        parts[name] = (tag, A.transformed(shape, trsf))

    manifest = {
        "scale": factor,
        "bores": (bores.get("printer") if bores else None) or "none applied: no Assets/print-bores.json",
        "frame": "case_solids.py's, dial face at z=0, mm x scale",
        "parts": {},
    }
    n = 0
    for name, (source, shape) in sorted(parts.items()):
        if only and name not in only:
            continue
        note = NOT_FOR_PRINTING.get(name) or ("bought, not printed" if bought(name) else "prints")
        write_stl(scaled(shape, factor), os.path.join(out, name + ".stl"), factor)
        manifest["parts"][name] = {"source": source, "note": note}
        n += 1
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    skipped = sum(1 for p in manifest["parts"].values() if p["note"] != "prints")
    print("  %d STLs at %.3fx into %s in %.0fs; %d of them marked not for printing; bores: %s"
          % (n, factor, out, time.time() - t0, skipped, manifest["bores"]))


if __name__ == "__main__":
    main()
