"""At what scale could the OM10 actually be printed, part by part.

    python tools/print_scale.py                  # the table and the verdict
    python tools/print_scale.py --json out.json  # the same numbers, machine readable

WHAT THIS ANSWERS. The direction of travel is an object that could be MADE.
Printing is the cheapest way to make one, so the question is what a printer
does to a movement 30.8 mm across: scale it up until its thinnest wall clears
the machine's minimum, and see what the movement has become by the time it
does. The answer has to be a single uniform scale, because a movement scaled
non-uniformly is not a movement - the wheels stop meshing.

WHERE THE NUMBERS COME FROM. Every thickness here is measured off
captures/om10/om10-00001_20220701_va_01_3.stp, the OM10's own STEP, through
om10_extract_all.load - the same loader the exporter uses, so a part is the
same solid here as it is on the wall. Nothing is read off a drawing and
nothing is guessed. The two designed springs are the exception and are read
from Assets/mechanism.json, because the STEP's hairspring is a placeholder
and it carries no mainspring at all: those two strips are tools/hairspring.py
and tools/mainspring.py's numbers, not the file's.

THE THICKNESS METRIC. A part's governing wall is taken as 2V/A, volume over
surface area - the hydraulic thickness. For a flat plate it returns the
plate's thickness exactly; for a pierced, toothed wheel it returns something
smaller than the plate, because the teeth and the spoke windows add surface
without adding volume. That bias is the useful direction: it fails safe. The
bounding box's smallest side is printed beside it as the honest upper bound,
and the mid-plane section's 2A/P as the in-plane width, so a part whose
problem is its teeth can be told apart from one whose problem is that the
whole part is a foil.

WHAT IT DOES NOT MEASURE. A true minimum inscribed sphere, which is the real
minimum-wall test a slicer applies. 2V/A is an average over the whole solid:
a part that is bulky everywhere except one 0.05 mm web reads as bulky. Every
number here is therefore a floor on the problem, never a ceiling. Section a
part before you print it.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from om10_extract_all import STEP, load

from OCP.Bnd import Bnd_Box
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Section
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PARTS = os.path.join(ROOT, "Assets", "movement-parts.json")
MECHANISM = os.path.join(ROOT, "Assets", "mechanism.json")

# The machines, and what each one can hold. min_wall is the thinnest
# self-supporting wall the process will actually give you; min_feature the
# thinnest raised detail - a tooth tip, a pin - that survives cleaning;
# clearance the gap two parts need to still move after cure or cooling.
#
# ponytail: these are published, conservative figures for a well-tuned
# machine of each class, NOT measurements from the printer this would run on.
# They are the input the whole study is most sensitive to, which is why they
# sit in one table at the top instead of scattered through the code: print a
# test comb on the actual machine, put its numbers here, re-run. Everything
# below is a division by these.
PRINTERS = [
    {
        "name": "FDM 0.4 mm nozzle",
        "note": "Prusa / Bambu class, 0.4 nozzle, 0.2 mm layer",
        "min_wall": 0.80,  # two perimeters. One perimeter is not a wall.
        "min_feature": 0.45,
        "clearance": 0.40,
        "build": (250.0, 210.0, 210.0),
    },
    {
        "name": "MSLA resin 50 um",
        "note": "consumer 4K/8K LCD, 50 um pixel, 50 um layer",
        "min_wall": 0.30,
        "min_feature": 0.20,
        "clearance": 0.20,
        "build": (218.0, 123.0, 235.0),
    },
    {
        "name": "DLP resin 35 um",
        "note": "small-format DLP, 35 um pixel, 30 um layer",
        "min_wall": 0.20,
        "min_feature": 0.12,
        "clearance": 0.12,
        "build": (128.0, 80.0, 200.0),
    },
    {
        "name": "micro-SLA 2 um",
        "note": "Boston Micro Fabrication class - a bureau service, not a desktop",
        "min_wall": 0.05,
        "min_feature": 0.025,
        "clearance": 0.020,
        "build": (50.0, 50.0, 50.0),
    },
]

# Parts nobody prints at any scale, and what you do instead. A printed
# hairspring is not a spring: the elasticity IS the part, and no photopolymer
# has it. These are excluded from the scale that governs and listed as the
# bill of things you buy or make. The reason is given per part because "too
# small" and "wrong material" are different problems and only the first one
# is fixed by scaling.
SUBSTITUTES = {
    "hairspring": "wind it. 0.035 mm blued steel or Nivarox strip; a printed spiral has no elastic limit and so no rate.",
    "mainspring": "buy it. 0.14 mm strip steel, coiled into the barrel; the energy store is the material, not the shape.",
    "staff": "turn it. The pivots are the running fit; printed, they are a rough cone sitting in a rough hole.",
    "jewel": "buy them. Synthetic ruby; the bearing is the reason a watch runs for years rather than weeks.",
    # The shock settings came out governing every machine on the first run,
    # which is the right answer to the wrong question: an Incabloc-type
    # setting is bought as an assembly - block, capstone, hole jewel and the
    # lyre spring that holds them - and nobody prints one at any scale. The
    # spring is 0.028 mm and is a spring, so it fails on material as well as
    # on size. Left in the study, it would have set the scale for the whole
    # movement on a part that is never going to come off a printer.
    "shock_spring_cock": "buy the setting. 0.028 mm lyre spring - a spring, and the thinnest thing in the watch.",
    "shock_spring_dial": "buy the setting. As above, the dial side's.",
    "shock_setting_cock": "buy the setting. It arrives as an assembly with its spring and stones.",
    "shock_setting_dial": "buy the setting. It arrives as an assembly with its spring and stones.",
    "shock_capstone_cock": "buy the setting. Ruby capstone, and the shock protection is the point of it.",
    "shock_capstone_dial": "buy the setting. Ruby capstone.",
    "shock_jewel_cock": "buy the setting. Ruby hole jewel.",
    "shock_jewel_dial": "buy the setting. Ruby hole jewel.",
}

# What the movement measures across the plate, in the exporter's own frame.
MOVEMENT_SPAN_MM = 30.78

# The gap between a pivot and its bearing, as a SURFACE gap, because a
# surface gap is what a printer's clearance figure means. It matters more
# than it looks: clearances scale with the part, so a scale chosen to fix
# the walls also has to open this gap past what the machine can hold, or
# the parts print beautifully and then seize solid.
#
# This was 0.010 mm, assumed from watchmaking practice, on the reasoning
# that nominal CAD draws a pivot and its jewel to the same size and keeps
# the clearance on the drawing. The reasoning was sound and wrong about
# this file: the OM10's STEP carries its real fits at every arbor.
# tools/om10_fits.py measures them, and the tightest is a 0.0031 mm gap,
# three times tighter than the guess, which makes this constraint three
# times worse than the first version of the study reported.
FITS = os.path.join(ROOT, "Assets", "om10-fits.json")
ASSUMED_FIT_MM = 0.010


def running_fit_mm():
    """The tightest measured pivot gap, or the old assumption if nobody has
    run the measurement yet. The tightest rather than the median, because
    the tightest fit decides whether the assembly turns at all: a movement
    with one seized arbor is a paperweight."""
    try:
        with open(FITS) as f:
            fits = json.load(f)
        gaps = [r["clearance_dia"] / 2 for r in fits["pivots"] if r["clearance_dia"] > 0]
        if gaps:
            return min(gaps), "measured"
    except (OSError, ValueError, KeyError) as exc:
        # Missing or half-written is the normal case on a fresh clone:
        # om10_fits.py needs the STEP, and the STEP is gitignored. Say which
        # number is being used and carry on rather than refusing to run.
        print(
            "  ! no measured fits (%s); assuming %.4f mm" % (exc, ASSUMED_FIT_MM),
            file=sys.stderr,
        )
    return ASSUMED_FIT_MM, "assumed"


RUNNING_FIT_MM, RUNNING_FIT_SOURCE = running_fit_mm()


def measure(shape):
    """Volume, surface area, bounding box and the mid-plane section, in mm."""
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    x0, y0, z0, x1, y1, z1 = box.Get()
    dims = (x1 - x0, y1 - y0, z1 - z0)

    vp = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, vp)
    sp = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, sp)
    volume, area = vp.Mass(), sp.Mass()
    if volume <= 0 or area <= 0:
        return None

    # The in-plane width, from a slab thin enough to read as a section but
    # thick enough for the boolean to be stable. Its area comes from the
    # slab's VOLUME over its height rather than from building faces off the
    # section wires: a wheel's section is a ring carrying teeth and spoke
    # windows, and face building on those wires is where this fell over first.
    ymid = (y0 + y1) / 2.0
    height = min(0.02, dims[1] / 10.0)
    plane_width = None
    if height > 0:
        try:
            slab = BRepPrimAPI_MakeBox(
                gp_Pnt(x0 - 1, ymid - height / 2, z0 - 1),
                dims[0] + 2,
                height,
                dims[2] + 2,
            ).Shape()
            common = BRepAlgoAPI_Common(shape, slab)
            common.Build()
            sv = GProp_GProps()
            BRepGProp.VolumeProperties_s(common.Shape(), sv)
            section_area = sv.Mass() / height

            section = BRepAlgoAPI_Section(
                shape, gp_Pln(gp_Pnt(0, ymid, 0), gp_Dir(0, 1, 0)), False
            )
            section.Build()
            lp = GProp_GProps()
            BRepGProp.LinearProperties_s(section.Shape(), lp)
            perimeter = lp.Mass()
            if perimeter > 0 and section_area > 0:
                plane_width = 2 * section_area / perimeter
        except Exception as exc:
            # A boolean that fails costs that part its in-plane number and
            # nothing else - 2V/A still governs it. This runs over 166 solids
            # unattended, so it says which one and carries on rather than
            # taking the whole study down with it.
            print("  ! section failed: %s" % exc, file=sys.stderr)

    return {
        "volume": volume,
        "area": area,
        "wall": 2 * volume / area,
        "bbox_min": min(dims),
        "bbox": dims,
        "plane_width": plane_width,
    }


def names_by_source():
    """The readable name for each source id, inverted out of the exporter's
    own catalogue so a part is called here exactly what the renderer calls
    it. Anything the catalogue could not name keeps its OM number."""
    with open(PARTS) as f:
        parts = json.load(f)
    return {info["source"]: name for name, info in parts.items()}


def designed_springs():
    """The two strips the STEP does not carry, from their own design."""
    with open(MECHANISM) as f:
        m = json.load(f)
    hair, main = m["hairspring"], m["mainspring"]
    return {
        "hairspring": {
            "wall": hair["thickness"] * 1000.0,
            "note": "%.3f mm strip, %.2f wide, %.1f long"
            % (
                hair["thickness"] * 1000.0,
                hair["width"] * 1000.0,
                hair["active_length"] * 1000.0,
            ),
        },
        "mainspring": {
            "wall": main["thickness"] * 1000.0,
            "note": "%.3f mm strip, %.2f wide, %.0f long"
            % (
                main["thickness"] * 1000.0,
                main["width"] * 1000.0,
                main["length"] * 1000.0,
            ),
        },
    }


def collect():
    """Every solid, measured once, named where a name is known."""
    if not os.path.exists(STEP):
        raise SystemExit(
            "missing %s\n"
            "The OM10 STEP is gitignored. Copy it out of the owner's OneDrive\n"
            "3dstuff folder into captures/om10/ and run again." % STEP
        )
    names = names_by_source()
    solids = load(STEP)
    print("measuring %d solids from the OM10 STEP" % len(solids), file=sys.stderr)

    rows = {}
    for tag, shape in solids.items():
        measured = measure(shape)
        if measured is None:
            continue
        # Twelve identical screws are one printing problem, not twelve, so
        # the instances of a source id fold into one row. The thinnest wins,
        # because a family prints at the scale its worst member needs.
        source = tag.split("#")[0]
        name = names.get(source, source)
        if name in rows:
            rows[name]["count"] += 1
            if measured["wall"] < rows[name]["wall"]:
                rows[name].update(measured)
        else:
            rows[name] = dict(measured, name=name, source=source, count=1)

    for name, spring in designed_springs().items():
        rows[name] = {
            "name": name,
            "source": "designed",
            "count": 1,
            "wall": spring["wall"],
            "bbox_min": spring["wall"],
            "bbox": None,
            "plane_width": None,
            "volume": None,
            "area": None,
            "note": spring["note"],
        }
    return rows


def scale_for(printer, rows):
    """The uniform scale this machine needs, and what sets it.

    Two constraints, and the bigger one wins. The WALL constraint is the
    scale at which the thinnest part you would actually print reaches the
    machine's minimum wall. The FIT constraint is the scale at which a
    running clearance opens up to the machine's resolvable gap - below it
    the wheels come off the plate fused to their bearings. They are
    different numbers and on every machine here it is the second that
    binds, which was not obvious before the study was run."""
    worst, wall_scale = None, 0.0
    for name, row in rows.items():
        if name in SUBSTITUTES:
            continue
        scale = printer["min_wall"] / row["wall"]
        if scale > wall_scale:
            wall_scale, worst = scale, name
    fit_scale = printer["clearance"] / RUNNING_FIT_MM
    if fit_scale >= wall_scale:
        return fit_scale, "the running fits", wall_scale, fit_scale
    return wall_scale, worst, wall_scale, fit_scale


def main():
    ap = argparse.ArgumentParser(description="Print-scale study for the OM10.")
    ap.add_argument("--json", help="write the measurements here as well")
    ap.add_argument("--top", type=int, default=18, help="how many of the thinnest parts to list")
    args = ap.parse_args()

    rows = collect()
    ordered = sorted(rows.values(), key=lambda r: r["wall"])
    printable = [r for r in rows.values() if r["name"] not in SUBSTITUTES]

    print()
    print("THE THINNEST PARTS, measured off the STEP (mm)")
    print("%-24s %4s %8s %9s %8s  %s" % ("part", "n", "2V/A", "bbox min", "2A/P", ""))
    print("-" * 78)
    for row in ordered[: args.top]:
        bbox_min = "%9.3f" % row["bbox_min"] if row["bbox"] else "        -"
        plane = "%8.3f" % row["plane_width"] if row["plane_width"] else "       -"
        flag = "SUBSTITUTE" if row["name"] in SUBSTITUTES else ""
        print(
            "%-24s %4d %8.3f %s %s  %s"
            % (row["name"], row["count"], row["wall"], bbox_min, plane, flag)
        )

    print()
    print("WHAT EACH MACHINE DEMANDS")
    print(
        "%-20s %9s %7s %11s %12s  %s"
        % ("printer", "min wall", "scale", "movement", "biggest part", "fits?")
    )
    print("-" * 78)
    results = []
    for printer in PRINTERS:
        scale, worst, wall_scale, fit_scale = scale_for(printer, rows)
        span = MOVEMENT_SPAN_MM * scale
        biggest = max((max(r["bbox"]) * scale for r in printable if r["bbox"]), default=0.0)
        # The movement is a disc: it needs two of the plate's three axes, and
        # the shortest of those two is what it has to fit inside.
        plate = min(sorted(printer["build"])[1:])
        fits = span <= plate
        print(
            "%-20s %9.2f %6.0fx %8.0f mm %9.0f mm  %s"
            % (printer["name"], printer["min_wall"], scale, span, biggest, "yes" if fits else "NO")
        )
        results.append(
            {
                "printer": printer["name"],
                "scale": scale,
                "governed_by": worst,
                "wall_scale": wall_scale,
                "fit_scale": fit_scale,
                "span_mm": span,
                "biggest_part_mm": biggest,
                "plate_mm": plate,
                "fits": fits,
            }
        )

    print()
    print("WHICH CONSTRAINT BINDS")
    print(
        "  running fit %.4f mm, %s%s"
        % (
            RUNNING_FIT_MM,
            RUNNING_FIT_SOURCE,
            " - run tools/om10_fits.py" if RUNNING_FIT_SOURCE == "assumed" else " off the STEP",
        )
    )
    print("%-20s %10s %10s   %s" % ("printer", "walls", "fits", "governed by"))
    print("-" * 78)
    for res in results:
        print(
            "%-20s %9.0fx %9.0fx   %s"
            % (res["printer"], res["wall_scale"], res["fit_scale"], res["governed_by"])
        )

    print()
    print("THE VERDICT")
    for printer, res in zip(PRINTERS, results):
        if res["fits"]:
            verdict = "buildable: %.0f mm movement on a %.0f mm plate" % (
                res["span_mm"],
                res["plate_mm"],
            )
        else:
            verdict = "no: a %.0f mm movement will not go on a %.0f mm plate" % (
                res["span_mm"],
                res["plate_mm"],
            )
        print("  %-20s %s" % (printer["name"], verdict))
        print("  %-20s   %s" % ("", printer["note"]))

    print()
    print("THE WAY OUT: OPEN THE FITS IN THE MODEL, NOT WITH THE SCALE")
    # The fit constraint is the one that hurts, and it is the one that does
    # not have to be paid in scale. A clearance is a number in the model:
    # bore the bearing holes oversize before you slice and the fits stop
    # driving anything, leaving the walls to govern, which is four to six
    # times cheaper in size. It costs a movement whose fits are the
    # printer's rather than the watchmaker's - it will turn, and it will not
    # keep time - which is the right trade for an object meant to be looked
    # at rather than worn.
    print("%-20s %7s %10s %11s  %s" % ("printer", "scale", "movement", "on plate", "then"))
    print("-" * 78)
    for printer, res in zip(PRINTERS, results):
        span = MOVEMENT_SPAN_MM * res["wall_scale"]
        plate = res["plate_mm"]
        if span <= plate:
            then = "prints whole"
        else:
            # The mainplate is the only part as wide as the movement, so it
            # is the only one that has to be split - pinned in sections, the
            # way a big plate is made anyway.
            then = "split the mainplate into %d" % (int(span / plate) + 1)
        print(
            "%-20s %6.0fx %8.0f mm %9.0f mm  %s"
            % (printer["name"], res["wall_scale"], span, plate, then)
        )
        res["recut_span_mm"] = span

    print()
    print("PARTS YOU MAKE INSTEAD OF PRINTING, AT ANY SCALE")
    for name, why in sorted(SUBSTITUTES.items()):
        if name in rows:
            print("  %-20s %6.3f mm  %s" % (name, rows[name]["wall"], why))

    if args.json:
        with open(args.json, "w") as f:
            json.dump(
                {
                    "parts": {
                        k: {kk: vv for kk, vv in v.items() if kk != "bbox"}
                        for k, v in rows.items()
                    },
                    "printers": results,
                },
                f,
                indent=1,
            )
        print("\nwrote %s" % args.json)


if __name__ == "__main__":
    main()
