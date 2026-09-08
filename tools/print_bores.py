"""The bores to open so a printed OM10 turns, and proof they break nothing.

    python tools/print_bores.py                          # MSLA at the study's 3x
    python tools/print_bores.py --printer FDM --scale 9
    python tools/print_bores.py --list                   # the machines on offer

WHY THIS EXISTS. tools/print_scale.py found that the running fits govern a
printed movement rather than the wall thickness, and by so much that no
sensible scale pays for them: the OM10's tightest fit is a 0.0031 mm gap and
a 50 um machine wants 0.20, which is 64x, a movement two metres across. The
conclusion was that a clearance is a number in the model rather than a
consequence of the scale, so the fits should be bored open before slicing
and the walls left to govern. This is that, done: for a machine and a scale,
every bearing in Assets/om10-fits.json opened until its gap at that scale is
what the machine can hold.

WHAT IT DOES NOT TOUCH. The pivots. Opening a bore costs a bearing some wall
and nothing else; turning a pivot down costs the arbor its stiffness, moves
the wheel's seat and changes the depthing. Between two ways to buy the same
clearance, take the one that only moves a hole.

THE WHOLE BORE, NOT THE NARROWEST PART. tools/om10_fits.py had to learn that
these holes are parallel with an oil sink opening out of one side, and that
measuring at the middle reads the sink instead of the bearing. The same fact
runs the other way here: opening only the narrow section would leave a
parallel hole with a step in it, which is a shoulder for the pivot to catch
on. The bore is opened over the bearing's full height, and where the sink is
already wider than the new bore, the sink survives as a chamfer.

PROVING IT. Opening a 0.10 mm hole to 0.28 mm is a big relative change and
the bearings sit inside other parts. So every opened bore is built as a
solid and intersected against all 166 solids: if the new hole breaks out
through a bearing's own wall, into the plate, or into a neighbour, this says
which and by how much. That is the check that has to pass before any of it
reaches a slicer.
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from om10_extract_all import STEP, load
from om10_fits import radial_extent
from print_scale import PRINTERS, collect, scale_for

from OCP.Bnd import Bnd_Box
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FITS = os.path.join(ROOT, "Assets", "om10-fits.json")
OUT = os.path.join(ROOT, "Assets", "print-bores.json")
PARTS = os.path.join(ROOT, "Assets", "movement-parts.json")

# How many heights to profile down a bore. The same scan om10_fits.py uses to
# find the narrowest section, run here to find where the parallel part of the
# hole STARTS and STOPS, which is what decides how far the opening runs.
BORE_STEPS = 60

# A bore counts as parallel where it is within this of its narrowest reading.
# The holes are drawn parallel, so this is tolerance for the sampling rather
# than for the geometry: a section taken a hair off a tangent point picks up
# a few tenths of a micron.
PARALLEL_TOLERANCE_MM = 0.0015

# Below this a boolean's result is numerical noise rather than a collision.
# 1e-6 mm3 is a cube a hundredth of a millimetre on a side.
CLASH_VOLUME_MM3 = 1e-6


def volume_of(shape):
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def box_of(shape):
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    return box.Get()


def boxes_miss(a, b, pad=0.0):
    """True when two bounding boxes cannot touch. Cheap, and it takes the
    166-solid clash check from thousands of booleans down to dozens."""
    return (
        a[3] + pad < b[0]
        or b[3] + pad < a[0]
        or a[4] + pad < b[1]
        or b[4] + pad < a[1]
        or a[5] + pad < b[2]
        or b[5] + pad < a[2]
    )


def bore_profile(shape, span, arbor):
    """Walk the bore and report its narrowest radius, the height that occurs
    at, the widest it opens out to (the oil sink), and the height range over
    which it is parallel."""
    y0, y1 = span
    readings = []
    for i in range(1, BORE_STEPS):
        height = y0 + (y1 - y0) * i / BORE_STEPS
        extent = radial_extent(shape, height, arbor)
        if extent is not None:
            readings.append((height, extent[0], extent[1]))
    if not readings:
        return None
    narrowest = min(r[1] for r in readings)
    at_height = next(r[0] for r in readings if r[1] == narrowest)
    widest = max(r[1] for r in readings)
    # The wall that matters is the one around the running surface, so it is
    # read at the height where the bore is narrowest. Taking the thinnest
    # outer radius anywhere down the part instead condemns every domed jewel:
    # a shock stone tapers almost to its own hole at the rim, which is a
    # chamfer rather than a wall, and reads as negative wall left.
    outer_at_bore = next(r[2] for r in readings if r[1] == narrowest)
    parallel = [r[0] for r in readings if r[1] <= narrowest + PARALLEL_TOLERANCE_MM]
    return {
        "bore_r": narrowest,
        "at": at_height,
        "sink_r": widest,
        "outer_r": outer_at_bore,
        "outer_thinnest": min(r[2] for r in readings),
        "parallel": (min(parallel), max(parallel)),
    }


def opened_bore_solid(arbor, span, radius, was, overshoot=0.05):
    """The material an opened bore actually REMOVES: the tube between the old
    hole and the new one, run past both faces so the cut leaves no skin.

    A plain cylinder of the new radius was the first version and it was
    wrong. It contains the old hole, so anything legitimately living inside
    the old hole - the barrel arbor's screw sits on the barrel's own axis -
    registers as a part the opening breaks into, when in truth the opening
    never reaches it. Only the annulus is new material."""
    y0, y1 = span
    height = (y1 - y0) + 2 * overshoot
    axis = gp_Ax2(gp_Pnt(arbor[0], y0 - overshoot, arbor[1]), gp_Dir(0, 1, 0))
    outer = BRepPrimAPI_MakeCylinder(axis, radius, height).Shape()
    if was <= 0:
        return outer
    inner = BRepPrimAPI_MakeCylinder(axis, was, height).Shape()
    cut = BRepAlgoAPI_Cut(outer, inner)
    cut.Build()
    return cut.Shape()


def clashes(cylinder, solids, allowed, boxes):
    """Everything the opened bore would eat into, other than the bearing it
    belongs to and the pivot that runs in it.

    Note what gets passed in: the tube over the bearing's EXACT height, with
    no overshoot. The cut geometry needs to run past both faces so it leaves
    no skin, but a cut only removes material from the part it is cutting,
    and an overshooting test solid reports every part merely touching the
    bearing's face. That produced two false failures on the balance, where a
    cap stone sits flat against the hole jewel it closes - which is what a
    cap stone is for, not a collision."""
    cyl_box = box_of(cylinder)
    hits = []
    for tag, shape in solids.items():
        if tag in allowed:
            continue
        if boxes_miss(cyl_box, boxes[tag]):
            continue
        common = BRepAlgoAPI_Common(cylinder, shape)
        common.Build()
        if not common.IsDone():
            continue
        overlap = volume_of(common.Shape())
        if overlap > CLASH_VOLUME_MM3:
            hits.append((tag, overlap))
    return sorted(hits, key=lambda h: -h[1])


def load_bores(path=OUT):
    """The bore table, keyed by part name, or None if nobody has built one.
    Returns None rather than raising: the wall export must not care that a
    print set exists, and a clone with no STEP cannot have made one."""
    try:
        with open(path) as f:
            payload = json.load(f)
    except (OSError, ValueError) as exc:
        print("  ! no print bores (%s)" % exc, file=sys.stderr)
        return None
    return {row["bearing"]: row for row in payload.get("bores", [])}


def apply_bore(name, shape, bores):
    """The part as it should be printed: its bearing bore opened to what the
    machine can hold, or the part untouched if it has no bore in the table.

    This is the whole consumer side, kept here so gltf_export.prepared can
    call it in one line rather than growing a copy of the geometry:

        from print_bores import load_bores, apply_bore
        shape = apply_bore(name, shape, bores) if bores else shape

    The cut runs past both faces on purpose. A cut that stops flush leaves a
    skin of numerically-zero thickness that tessellates into stray triangles
    across the mouth of the hole."""
    if not bores or name not in bores:
        return shape
    row = bores[name]
    tube = opened_bore_solid(row["arbor"], row["span"], row["bore_dia_new"] / 2.0, 0.0)
    cut = BRepAlgoAPI_Cut(shape, tube)
    cut.Build()
    if not cut.IsDone():
        # A boolean that will not run leaves the part as it was rather than
        # dropping it from the export: a movement with one unopened bore is
        # a movement that binds on one arbor, which is visible and fixable.
        # A movement missing a jewel is neither.
        print("  ! bore failed on %s; left as drawn" % name, file=sys.stderr)
        return shape
    return cut.Shape()


def pick_printer(name):
    for printer in PRINTERS:
        if name.lower() in printer["name"].lower():
            return printer
    raise SystemExit(
        "no printer matching %r. Try one of:\n  %s"
        % (name, "\n  ".join(p["name"] for p in PRINTERS))
    )


def main():
    ap = argparse.ArgumentParser(description="Open the OM10's bores for printing.")
    ap.add_argument("--printer", default="MSLA", help="substring of a name in print_scale.PRINTERS")
    ap.add_argument("--scale", type=float, help="uniform scale; defaults to the wall-governed one")
    ap.add_argument("--json", default=OUT, help="where to write the bore table")
    ap.add_argument("--list", action="store_true", help="list the machines and stop")
    args = ap.parse_args()

    if args.list:
        for printer in PRINTERS:
            print(
                "%-20s min wall %.2f  clearance %.3f  %s"
                % (printer["name"], printer["min_wall"], printer["clearance"], printer["note"])
            )
        return

    printer = pick_printer(args.printer)
    scale = args.scale
    if scale is None:
        # The wall-governed scale is the whole point: it is what the study
        # says the machine costs once the fits stop driving, so it is the
        # scale these bores are calculated to make work.
        _, _, wall_scale, _ = scale_for(printer, collect())
        scale = wall_scale

    with open(FITS) as f:
        fits = json.load(f)
    with open(PARTS) as f:
        parts = json.load(f)

    solids = load(STEP)
    boxes = {tag: box_of(shape) for tag, shape in solids.items()}

    # What the gap has to be at 1x so that, multiplied by the scale, it is
    # the gap the machine can actually hold.
    needed_gap = printer["clearance"] / scale

    print()
    print("%s at %.1fx" % (printer["name"], scale))
    print(
        "  machine holds a %.3f mm gap, so at this scale the model needs %.4f mm"
        % (printer["clearance"], needed_gap)
    )
    print()
    print(
        "%-22s %9s %9s %8s %9s  %s"
        % ("bearing", "bore now", "bore new", "opens", "wall left", "")
    )
    print("-" * 84)

    rows, failures = [], []
    for fit in fits["pivots"]:
        name = fit["bearing"]
        if name not in parts:
            continue
        bearing = parts[name]
        arbor = bearing["axis"]
        profile = bore_profile(solids[bearing["source"]], bearing["y"], arbor)
        if profile is None:
            print("  ! %s: no section down its height" % name, file=sys.stderr)
            continue

        pivot_r = fit["pivot_dia"] / 2.0
        new_r = pivot_r + needed_gap
        opens_by = 2 * (new_r - profile["bore_r"])
        wall_left = profile["outer_r"] - new_r
        wall_at_scale = wall_left * scale
        holds = wall_at_scale >= printer["min_wall"]

        allowed = {bearing["source"], parts[fit["pivot"]]["source"]}
        tube = opened_bore_solid(arbor, bearing["y"], new_r, profile["bore_r"], overshoot=0.0)
        hits = clashes(tube, solids, allowed, boxes)

        note = ""
        if not holds:
            note = "WALL %.3f < %.2f" % (wall_at_scale, printer["min_wall"])
        elif hits:
            note = "BREAKS INTO " + ", ".join(t for t, _ in hits[:2])
        elif new_r >= profile["sink_r"]:
            # Not a failure. The oil sink is a reservoir, and a printed
            # movement is not going to be oiled; losing it costs nothing but
            # is worth saying, because the part will look wrong next to the
            # original and somebody will file a bug about it.
            note = "sink gone"

        print(
            "%-22s %9.4f %9.4f %8.4f %9.3f  %s"
            % (
                name,
                2 * profile["bore_r"],
                2 * new_r,
                opens_by,
                wall_at_scale,
                note,
            )
        )

        row = {
            "bearing": name,
            "source": bearing["source"],
            "pivot": fit["pivot"],
            "arbor": [round(v, 4) for v in arbor],
            "span": [round(v, 4) for v in bearing["y"]],
            "parallel": [round(v, 4) for v in profile["parallel"]],
            "bore_dia_now": round(2 * profile["bore_r"], 4),
            "bore_dia_new": round(2 * new_r, 4),
            "opens_by": round(opens_by, 4),
            "wall_left_mm": round(wall_left, 4),
            "wall_thinnest_mm": round(profile["outer_thinnest"] - new_r, 4),
            "wall_at_scale_mm": round(wall_at_scale, 4),
            "sink_survives": bool(new_r < profile["sink_r"]),
            "clashes": [{"part": t, "mm3": round(v, 6)} for t, v in hits],
            "ok": bool(holds and not hits),
        }
        rows.append(row)
        if not row["ok"]:
            failures.append(row)

    print()
    if failures:
        print("NOT SAFE TO CUT: %d of %d" % (len(failures), len(rows)))
        for row in failures:
            if row["clashes"]:
                for clash in row["clashes"]:
                    print(
                        "  %-22s breaks into %-22s by %.5f mm3"
                        % (row["bearing"], clash["part"], clash["mm3"])
                    )
            else:
                print(
                    "  %-22s leaves %.3f mm of wall, machine needs %.2f"
                    % (row["bearing"], row["wall_at_scale_mm"], printer["min_wall"])
                )
    else:
        print("All %d bores open cleanly: wall holds, nothing broken into." % len(rows))

    payload = {
        "printer": printer["name"],
        "scale": scale,
        "machine_clearance_mm": printer["clearance"],
        "model_gap_mm": round(needed_gap, 6),
        "note": "Bores to open before slicing. Diameters at 1x; scale the whole model afterwards.",
        "bores": rows,
    }
    with open(args.json, "w") as f:
        json.dump(payload, f, indent=1)
    print("\nwrote %s" % args.json)


if __name__ == "__main__":
    main()
