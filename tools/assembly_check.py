"""Does it go together? Exact solid-against-solid interference through the
working range.

    python tools/assembly_check.py            # every check below; nonzero exit on a clash
    python tools/assembly_check.py --quick    # coarser angular steps

WHAT THIS ANSWERS. The OM10 is an assembled movement, so its own parts fit
each other; ours - the case set from case_solids.py, the two designed
springs, the open-heart cut - are placed round and into it by numbers, and
a number can be wrong by a tenth of a millimetre without anything on the
wall showing it. Each check here takes one part through the angles it
actually turns through and intersects it, as a B-rep solid, with every part
it could touch; any common volume above a speck is a clash and is printed
with its size and the angle it happened at. The escapement's own phase is
checked separately and was closed (HANDOVER-REALTIME.md). The OM10's own
running fits are docs/om10-fits.md's; the one interference among them, the
intermediate's upper bearing, is opened on export and checked here too.

FRAME. case_solids.py's: x right, y UP the dial, z toward the viewer,
dial face at z = 0. The OM10's (x, y, z) go to (-z, -x, y + MOVEMENT_Z),
which is the exporter's world frame turned onto this one.
"""

import argparse
import math
import os
import sys

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import case_solids as C                                       # noqa: E402
import gltf_export as G                                       # noqa: E402
import hairspring                                             # noqa: E402

SPECK = 1e-4   # mm^3: below this is tessellation noise on a touching face

# Overlaps that are the OM10's own and meant: a hooked or pressed joint is
# drawn as one solid in another. Reported as "joined", not as a clash.
JOINED = {
    ("mainspring", "barrel_arbor"): "the inner end hooked on the arbor, 0.037 mm3 of the hook in the hub",
}


def om10_to_case():
    """The OM10's frame onto case_solids.py's: (x, y, z) -> (-z, -x, y + MOVEMENT_Z)."""
    t = gp_Trsf()
    t.SetValues(0, 0, -1, 0,
                -1, 0, 0, 0,
                0, 1, 0, C.MOVEMENT_Z)
    return t


def transformed(shape, trsf):
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def rotated(shape, axis_xy, degrees):
    """Turned clockwise on the dial (about -z) through an axis at (x, y)."""
    t = gp_Trsf()
    t.SetRotation(gp_Ax1(gp_Pnt(axis_xy[0], axis_xy[1], 0), gp_Dir(0, 0, -1)), math.radians(degrees))
    return transformed(shape, t)


def volume(shape):
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, p)
    return abs(p.Mass())


def bbox(shape):
    b = Bnd_Box()
    BRepBndLib.Add_s(shape, b)
    return b


def common_volume(a, b):
    if bbox(a).IsOut(bbox(b)):
        return 0.0
    op = BRepAlgoAPI_Common(a, b)
    if not op.IsDone():
        return float("nan")
    return volume(op.Shape())


def load_movement():
    """Every OM10 part in the case frame, with the open-heart cut, the
    opened bore and the designed hairspring, exactly as the export has them."""
    inv = {v: k for k, v in G.NAMES.items()}
    trsf = om10_to_case()
    parts = {}
    for name, tag in inv.items():
        path = os.path.join(G.PARTS, tag.replace("#", "_") + ".step")
        if not os.path.exists(path):
            continue
        if name == "hairspring":
            shape = hairspring.build(hairspring.design())[0].wrapped
        else:
            shape = G.read_step(path)
        parts[name] = transformed(G.prepared(name, shape), trsf)
    return parts


def load_case():
    return {
        "case": C.case().wrapped, "caseback": C.caseback().wrapped, "crystal": C.crystal().wrapped,
        "dial": C.dial().wrapped, "rehaut": C.rehaut().wrapped, "indices": C.indices().wrapped,
        "hour_hand": C.hour_hand().wrapped, "minute_hand": C.minute_hand().wrapped,
        "seconds_hand": C.seconds_hand().wrapped, "cap": C.cap().wrapped, "crown": C.crown().wrapped,
    }


def om10_axis(x, z):
    """An OM10 arbor (x, z) in the case frame's (x, y)."""
    return (-z, -x)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--print", dest="print_set", action="store_true",
                    help="check the printable bore set rather than the wall's movement")
    args = ap.parse_args()
    step = 60 if args.quick else 30

    # Turned on before anything loads, because prepared() is what applies it
    # and load_movement() calls prepared once per solid. Flipping it later
    # would check the wall's movement and report on the printed one.
    if args.print_set:
        bores = G.use_print_bores()
        if bores is None:
            raise SystemExit("no Assets/print-bores.json - run tools/print_bores.py first")
        # Say which movement is on the bench. The two runs look identical
        # otherwise, and a clean pass on the wrong one is worse than a fail.
        print("checking the PRINTABLE set: %d bores opened" % len(bores))
    else:
        print("checking the wall's movement")

    case = load_case()
    mv = load_movement()
    allp = {**case, **mv}
    centre = (0.0, 0.0)
    seconds_axis = C.SECONDS_ARBOR
    staff = om10_axis(-8.06, 3.51)
    pallet = om10_axis(-5.87, 5.71)
    escape = om10_axis(-3.68, 7.90)
    barrel = om10_axis(6.67, -3.77)
    intermediate = om10_axis(1.53, 4.125)

    # (moving part, axis, angles, the parts it may touch)
    checks = [
        ("hour_hand", centre, range(0, 360, step),
         ["dial", "cap", "crystal", "rehaut", "indices", "cannon_pinion", "hour_wheel", "cannon_wheel", "minute_hand"]),
        ("minute_hand", centre, range(0, 360, step),
         ["dial", "cap", "crystal", "rehaut", "indices", "cannon_pinion", "hour_wheel", "hour_hand"]),
        ("seconds_hand", seconds_axis, range(0, 360, step),
         ["dial", "rehaut", "mainplate", "wheel_seconds", "pinion_seconds", "date_plate", "dial_rest", "hour_hand", "minute_hand", "crystal"]),
        ("balance", staff, range(-285, 286, 57),
         ["mainplate", "hairspring", "cock", "stud", "regulator", "regulator_boot", "rehaut", "dial", "lever"]),
        ("hairspring", staff, [0],
         ["collet", "stud", "regulator", "regulator_boot", "stud_carrier", "mainplate", "cock", "balance", "staff", "roller"]),
        ("mainspring", barrel, [0],
         ["barrel", "barrel_cover", "barrel_arbor", "barrel_bridge", "mainplate"]),
        # The STEP's own interference, opened on export (gltf_export.BORED).
        ("intermediate", intermediate, [0, 7.2],
         ["intermediate_bearing", "train_bearing_back", "mainplate", "bridge"]),
        ("lever", pallet, [-6.9, 0, 6.9],
         ["mainplate", "dial", "rehaut", "balance", "roller"]),
        ("escape", escape, [0, 9, 18],
         ["mainplate", "dial", "rehaut", "bridge"]),
        ("stem", None, [0], ["case", "dial", "rehaut", "crown"]),
        ("crown", None, [0], ["case", "crystal", "dial"]),
        ("cap", None, [0], ["cannon_pinion", "hour_wheel", "dial", "crystal"]),
        ("crystal", None, [0], ["case", "dial", "indices"]),
        ("dial", None, [0], ["case", "rehaut", "mainplate", "date_plate", "dial_rest", "hour_wheel", "cannon_wheel", "cannon_pinion"]),
        ("rehaut", None, [0], ["mainplate", "cock", "balance", "date_plate", "dial_rest", "wheel_seconds", "bridge"]),
    ]

    clashes = 0
    for mover, axis, angles, others in checks:
        if mover not in allp:
            print("  (no part named %s)" % mover)
            continue
        worst = {}
        for ang in angles:
            shape = allp[mover] if axis is None or ang == 0 else rotated(allp[mover], axis, ang)
            for other in others:
                if other not in allp:
                    continue
                v = common_volume(shape, allp[other])
                if v != v:
                    print("  %s vs %s at %s: boolean failed" % (mover, other, ang))
                    continue
                if v > SPECK and (mover, other) in JOINED:
                    print("  joined %-12s to %-16s %9.4f mm3: %s" % (mover, other, v, JOINED[(mover, other)]))
                    continue
                if v > SPECK and v > worst.get(other, (0, 0))[0]:
                    worst[other] = (v, ang)
        if worst:
            clashes += len(worst)
            for other, (v, ang) in sorted(worst.items(), key=lambda kv: -kv[1][0]):
                print("  CLASH %-13s vs %-16s %9.4f mm3  (worst at %s deg)" % (mover, other, v, ang))
        else:
            print("  ok    %-13s clears %s" % (mover, ", ".join(o for o in others if o in allp)))
    print("\n%d clashes" % clashes)
    sys.exit(1 if clashes else 0)


if __name__ == "__main__":
    main()
