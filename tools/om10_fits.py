"""The OM10's running fits, measured where each pivot actually turns.

    python tools/om10_fits.py                 # the table
    python tools/om10_fits.py --json out.json # the same numbers, machine readable

WHY. tools/print_scale.py needed one number it could not get off the file:
the clearance between a pivot and its bearing. It assumed 0.010 mm from
watchmaking practice and said so, and since the whole print study is a
division by that number, an assumption was the wrong thing for it to be.
This measures it instead, at all nine arbors, and print_scale.py reads the
result.

THE CLAIM THAT TURNED OUT TO BE FALSE. "Nominal CAD carries no clearance,
pivot and jewel are drawn the same size." That is what print_scale.py says
in its own comments and it is wrong about this file: the OM10's STEP carries
real fits, different at every arbor, and they can be read straight out of it.

HOW. For each bearing - a jewel, a bush, or a shock setting's hole jewel -
find the part turning in it: the one on the same arbor whose height range
contains the bearing's own mid-height. Section BOTH with a horizontal plane
at that height and measure radially from the arbor. The bearing's section is
an annulus, so its smallest radius is the bore. The pivot's section is a
disc, so its largest radius is the pivot. The difference is the fit.

WHY B-REP SECTIONS RATHER THAN A MESH. Because these are the smallest
features in the watch and a mesh lies about them. A pivot is 0.1 mm across;
tessellate it at any deflection you would use for rendering and its radius
moves by more than the clearance being measured. BRepAlgoAPI_Section against
the exact surfaces, sampled through BRepAdaptor_Curve on the exact curves,
has no such error - the numbers below are the file's, to the digit.

WHERE ALONG THE HOLE, AND WHY NOT THE MIDDLE. The first version of this
measured at each bearing's mid-height, on the reasoning that a jewel hole is
olive-shaped and narrowest in the middle. The file says otherwise. Scan the
escapement jewel down its height and the bore runs 0.101, 0.109, 0.196,
0.311, 0.387, 0.445: it is a parallel hole with an oil sink opening out on
one side, and its middle is already inside the sink. Measuring there read
the escape pinion as having a 0.218 mm clearance, twenty times its real one.

So the bore is scanned over the bearing's whole height and the NARROWEST
section wins, with the pivot measured at that same height. That is the point
the pivot actually runs in; everything above it is the oil reservoir.
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from om10_extract_all import STEP, load

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PARTS = os.path.join(ROOT, "Assets", "movement-parts.json")
OUT = os.path.join(ROOT, "Assets", "om10-fits.json")

# What counts as a bearing. The catalogue names them three ways because the
# OM10 uses three kinds: pierced jewels at the escapement, plain bushes in
# the plate for the train, and a sprung shock setting at the balance.
BEARINGS = ("bearing", "jewel")

# The shock settings' block and spring are not bearings; only the hole jewel
# inside them is. Named out rather than pattern-matched, because
# shock_jewel_cock reads like a bearing and shock_capstone_cock does not,
# and the difference is which one the pivot turns in.
NOT_BEARINGS = ("shock_block", "shock_spring", "shock_setting", "shock_capstone")

# Two parts sit on the same arbor without one running in the other: a wheel
# beside its bearing, a barrel and its cover, a screw through the middle of
# both. The pivot is picked as the largest thing that still passes through
# the bore, and this is how far OVER the bore a candidate may measure and
# still be taken as the pivot rather than as something standing beside it.
#
# It is not zero, and that is deliberate. Set to zero, a bearing whose bore
# is modelled tighter than its own pivot reports "nothing turning in it",
# which is how the intermediate wheel's interference hid for a whole run.
# 0.03 mm on the radius is far below any neighbouring feature and far above
# any plausible modelling error, so a genuine interference is caught and
# reported with a negative clearance instead of vanishing.
PIVOT_TOLERANCE_MM = 0.030

# How many points to sample along each section edge. A circle comes back as
# one or two edges, so this is the angular resolution of the whole
# measurement: 128 points puts the worst-case chord error at well under a
# micron on a 0.1 mm pivot, which is two orders below the fits being read.
SAMPLES = 128

# How many heights to scan down a bearing looking for the narrowest section.
# The bores here are 0.15 to 0.35 mm deep, so 40 steps puts the scan under
# ten microns apart, and the hole is parallel over most of its depth anyway:
# what the scan has to do is stay OUT of the oil sink, not resolve a curve.
BORE_STEPS = 40

# The catalogue's "axis" is a bounding box centre, which is the turning axis
# only for a part that is round. The barrel arbor carries a hook and its box
# centre sits 0.057 mm off the arbor it turns on, so the tolerance has to be
# wider than that. Candidates are still measured about the BEARING's axis,
# and the pivot is picked by radius, so a loose tolerance costs nothing.
ARBOR_TOLERANCE_MM = 0.10


def radial_extent(shape, height, arbor, samples=SAMPLES):
    """The smallest and largest radius the solid reaches at this height,
    measured from the arbor. Returns None where the plane misses the solid,
    which is normal: most parts are nowhere near most bearings."""
    section = BRepAlgoAPI_Section(
        shape, gp_Pln(gp_Pnt(0, height, 0), gp_Dir(0, 1, 0)), False
    )
    section.Build()
    ax, az = arbor
    radii = []
    explorer = TopExp_Explorer(section.Shape(), TopAbs_EDGE)
    while explorer.More():
        curve = BRepAdaptor_Curve(TopoDS.Edge_s(explorer.Current()))
        first, last = curve.FirstParameter(), curve.LastParameter()
        for i in range(samples + 1):
            p = curve.Value(first + (last - first) * i / samples)
            radii.append(math.hypot(p.X() - ax, p.Z() - az))
        explorer.Next()
    if not radii:
        return None
    return min(radii), max(radii)


def narrowest_bore(shape, span, arbor):
    """Scan the bearing down its own height and return the tightest bore it
    has, with the height it occurs at. The ends are skipped: a section taken
    exactly on a face is degenerate, and the chamfer at the mouth is not the
    bearing."""
    y0, y1 = span
    best = None
    for i in range(1, BORE_STEPS):
        height = y0 + (y1 - y0) * i / BORE_STEPS
        extent = radial_extent(shape, height, arbor)
        if extent is None:
            continue
        if best is None or extent[0] < best[0]:
            best = (extent[0], height)
    return best


def catalogue():
    with open(PARTS) as f:
        parts = json.load(f)
    # The mainspring is designed rather than extracted and carries no
    # placement, so it has no arbor to measure against.
    return {k: v for k, v in parts.items() if "axis" in v}


def same_arbor(a, b):
    return (
        abs(a["axis"][0] - b["axis"][0]) < ARBOR_TOLERANCE_MM
        and abs(a["axis"][1] - b["axis"][1]) < ARBOR_TOLERANCE_MM
    )


def is_bearing(name):
    if any(n in name for n in NOT_BEARINGS):
        return False
    return any(b in name for b in BEARINGS)


def measure_fits(solids, parts):
    """Every bearing, the part turning in it, and the gap between them."""
    rows = []
    for name, bearing in sorted(parts.items()):
        if not is_bearing(name):
            continue
        arbor = bearing["axis"]
        bore = narrowest_bore(solids[bearing["source"]], bearing["y"], arbor)
        if bore is None:
            print("  ! %s: no section anywhere down its height" % name, file=sys.stderr)
            continue
        bore_r, height = bore

        best = None
        for other, part in parts.items():
            if other == name or not same_arbor(bearing, part):
                continue
            if not (part["y"][0] <= height <= part["y"][1]):
                continue
            extent = radial_extent(solids[part["source"]], height, arbor)
            if extent is None:
                continue
            pivot_r = extent[1]
            # The part running in the bore is the one that fits inside it.
            # A wheel crossing the same height at a larger radius is sitting
            # beside the bearing, not turning in it.
            if pivot_r > bore_r + PIVOT_TOLERANCE_MM:
                continue
            if best is None or pivot_r > best[1]:
                best = (other, pivot_r)

        if best is None:
            print("  ! %s: nothing turning in it at %.3f" % (name, height), file=sys.stderr)
            continue
        pivot, pivot_r = best
        rows.append(
            {
                "bearing": name,
                "pivot": pivot,
                # The source id as well as the name. Names move: 00107 was
                # called impulse_pin until this file's own measurements
                # showed it running in the fork's two jewels. A consumer
                # that re-resolves a NAME against a later catalogue can
                # silently pick up a different solid, so the id travels too
                # and consumers key on it.
                "bearing_source": bearing["source"],
                "pivot_source": parts[pivot]["source"],
                "arbor": [round(a, 3) for a in arbor],
                "height": round(height, 3),
                "bore_dia": 2 * bore_r,
                "pivot_dia": 2 * pivot_r,
                "clearance_dia": 2 * (bore_r - pivot_r),
                "clearance_radial": bore_r - pivot_r,
            }
        )
    return rows


def measure_pipes(solids, parts):
    """The motion works, where a pipe turns inside a wheel rather than a
    pivot inside a jewel. Same measurement, an order of magnitude looser,
    and kept apart from the pivots because mixing the two would drag the
    median fit up and flatter the print study."""
    pairs = [("cannon_pinion", "hour_wheel"), ("cannon_pinion", "cannon_wheel")]
    rows = []
    for inner, outer in pairs:
        if inner not in parts or outer not in parts:
            continue
        a, b = parts[inner], parts[outer]
        low = max(a["y"][0], b["y"][0])
        high = min(a["y"][1], b["y"][1])
        if high <= low:
            continue
        height = (low + high) / 2.0
        arbor = b["axis"]
        inner_e = radial_extent(solids[a["source"]], height, arbor)
        outer_e = radial_extent(solids[b["source"]], height, arbor)
        if inner_e is None or outer_e is None:
            continue
        rows.append(
            {
                "bearing": outer,
                "pivot": inner,
                "arbor": [round(v, 3) for v in arbor],
                "height": round(height, 3),
                "bore_dia": 2 * outer_e[0],
                "pivot_dia": 2 * inner_e[1],
                "clearance_dia": 2 * (outer_e[0] - inner_e[1]),
                "clearance_radial": outer_e[0] - inner_e[1],
            }
        )
    return rows


def main():
    ap = argparse.ArgumentParser(description="Measure the OM10's running fits.")
    ap.add_argument("--json", default=OUT, help="where to write the measurements")
    args = ap.parse_args()

    if not os.path.exists(STEP):
        raise SystemExit(
            "missing %s\n"
            "The OM10 STEP is gitignored. Copy it out of the owner's OneDrive\n"
            "3dstuff folder into captures/om10/ and run again." % STEP
        )
    parts = catalogue()
    solids = load(STEP)
    print("measuring fits across %d solids" % len(solids), file=sys.stderr)

    pivots = measure_fits(solids, parts)
    pipes = measure_pipes(solids, parts)

    print()
    print("PIVOT FITS, measured at the narrowest section of each bore (mm)")
    print(
        "%-22s %-20s %8s %8s %10s %9s"
        % ("bearing", "runs", "bore dia", "pivot", "clear dia", "at y")
    )
    print("-" * 88)
    for r in sorted(pivots, key=lambda r: r["clearance_dia"]):
        print(
            "%-22s %-20s %8.4f %8.4f %10.4f %9.3f  %s"
            % (
                r["bearing"],
                r["pivot"],
                r["bore_dia"],
                r["pivot_dia"],
                r["clearance_dia"],
                r["height"],
                "INTERFERENCE" if r["clearance_dia"] < 0 else "",
            )
        )

    if pipes:
        print()
        print("PIPE FITS, the motion works (mm)")
        for r in pipes:
            print(
                "%-22s %-20s %8.4f %8.4f %10.4f %9.3f"
                % (
                    r["bearing"],
                    r["pivot"],
                    r["bore_dia"],
                    r["pivot_dia"],
                    r["clearance_dia"],
                    r["height"],
                )
            )

    fouled = [r for r in pivots if r["clearance_dia"] < 0]
    if fouled:
        print()
        print("INTERFERENCE, where the pivot is drawn bigger than its own bore")
        for r in fouled:
            print(
                "  %-20s in %-20s by %.4f mm on the diameter"
                % (r["pivot"], r["bearing"], -r["clearance_dia"])
            )

    clearances = sorted(r["clearance_dia"] for r in pivots if r["clearance_dia"] > 0)
    if clearances:
        middle = clearances[len(clearances) // 2]
        print()
        print("THE NUMBER print_scale.py NEEDS")
        print("  tightest pivot fit   %.4f mm on the diameter" % clearances[0])
        print("  median pivot fit     %.4f mm" % middle)
        print("  loosest pivot fit    %.4f mm" % clearances[-1])
        print("  assumed before this  0.0200 mm on the diameter")
        print()
        # A printer's quoted clearance is the gap between two surfaces, so
        # the watch number it has to be compared against is the RADIAL gap,
        # which is half the diametral clearance. Getting this wrong by a
        # factor of two was the easiest available mistake here.
        print("  print_scale.py wants a surface gap, not a diameter:")
        print("  the tightest fit is a %.4f mm gap between pivot and bore." % (clearances[0] / 2))

    with open(args.json, "w") as f:
        json.dump({"pivots": pivots, "pipes": pipes}, f, indent=1)
    print("\nwrote %s" % args.json)


if __name__ == "__main__":
    main()
