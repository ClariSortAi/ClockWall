"""True solid models of the parts an extruded outline cannot describe.

    .venv-cad\\Scripts\\python tools/cad_parts.py

WHY THIS EXISTS. Every part in this movement has been a flat 2D outline pushed
to a constant thickness and then given one blanket bevel. That is fine for the
parts that really are flat plates - an escape wheel is stamped, a lever is
stamped - and hopeless for the ones that are turned.

A balance wheel is the clearest case. Its rim is TALLER than its arm, chamfered
top and bottom on both the inner and the outer edge; the hub stands proud of
both; the timing screws are threaded radially into the rim, not sitting on top
of it. That is four heights and four different chamfers in one component, and an
extruded outline can express exactly one of each. Under a straight-down camera
those chamfers are most of what there is to see, because they are the only
surfaces angled toward a light.

So the turned parts are built here with a real B-rep kernel - CadQuery, which is
OpenCASCADE - where a cross-section can be REVOLVED and a chamfer can be put on
one named edge rather than on everything at once. They export as STL and the
render imports them instead of extruding a profile.

COORDINATES. Face space, and already converted for Blender: x is face x, y is
NEGATIVE face y, z is height above the plate. So a part comes in at the right
place with no transform, the same bargain the rest of the pipeline makes.

Run it with the CAD virtual environment, not the system python:
    .venv-cad\\Scripts\\python.exe tools/cad_parts.py
"""

import json
import math
import os
import sys

import cadquery as cq

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES = os.path.join(ROOT, "captures", "geom", "profiles.json")
OUT = os.path.join(ROOT, "captures", "cad")

# Enough segments that a rim edge is smooth at three pixels per face unit.
cq.exporters.export.__defaults__  # (documentation of intent; tolerance set below)
TOL = 0.05


def balance_wheel(R, band=0.135, arm=0.062, hub=0.17, blocks=4,
                  rim_h=3.6, arm_h=2.0, hub_h=4.6, chamfer=0.45):
    """
    A free-sprung balance, turned rather than cut out of sheet.

    The rim is revolved, so its chamfers run right round both edges the way a
    lathe leaves them - that is the bright line that says the part was turned.
    The arm is thinner and sits at the BOTTOM of the rim, which is why a real
    balance shows you the inside face of its rim rather than reading as a flat
    washer. The hub stands proud of both.
    """
    inner = R * (1 - band)

    # Rim: revolve a cross-section with a chamfer top and bottom, inside and out.
    rim = (cq.Workplane("XZ")
           .moveTo(inner, 0).lineTo(R, 0).lineTo(R, rim_h).lineTo(inner, rim_h)
           .close()
           .revolve(360, (0, 0, 0), (0, 1, 0)))
    rim = rim.edges("%CIRCLE").chamfer(chamfer)

    # The arm, across the middle and thinner than the rim.
    a = R * arm
    bar = (cq.Workplane("XY").box(2 * inner + 2, 2 * a, arm_h, centered=(True, True, False))
           .edges("|Z").chamfer(a * 0.35))
    bar = bar.intersect(cq.Workplane("XY").circle(inner + 0.4).extrude(arm_h))

    boss = (cq.Workplane("XY").circle(R * hub).extrude(hub_h)
            .edges(">Z").chamfer(chamfer))

    wheel = rim.union(bar).union(boss)

    # Timing screws, threaded radially INTO the rim, with their heads standing
    # proud outside it. That is what makes a free-sprung balance read as
    # adjustable rather than as a ring with beads stuck on.
    #
    # The bore has to be smaller than HALF the rim height and centred on the
    # rim's mid-plane. The first attempt used neither and cut a bore wider than
    # the rim was tall, straight through both faces, leaving four scalloped
    # notches in the top of the wheel. From directly above that looked almost
    # deliberate, which is exactly why it needed looking at from an angle.
    screw_r = min(a * 0.45, rim_h * 0.30)
    mid = rim_h / 2.0
    for i in range(blocks):
        turn = i * (360.0 / blocks) + 45.0
        bore = (cq.Workplane("YZ").workplane(offset=inner - 1.0)
                .circle(screw_r).extrude(R - inner + 2.0)
                .translate((0, 0, mid)))
        head = (cq.Workplane("YZ").workplane(offset=R - screw_r * 0.5)
                .circle(screw_r * 1.75).extrude(screw_r * 1.5)
                .translate((0, 0, mid))
                .edges("%CIRCLE").chamfer(screw_r * 0.28))
        wheel = wheel.cut(bore.rotate((0, 0, 0), (0, 0, 1), turn))
        wheel = wheel.union(head.rotate((0, 0, 0), (0, 0, 1), turn))

    return wheel


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(PROFILES) as f:
        payload = json.load(f)
    pivots = payload["pivots"]

    bx, by = pivots["balance"]
    # The balance's rim radius, taken from the geometry rather than restated.
    bR = None
    for spec in payload["parts"]:
        if spec["name"] == "balance":
            xs = [p[0] for r in spec["rings"] for p in r]
            ys = [p[1] for r in spec["rings"] for p in r]
            bR = max(max(xs) - bx, max(ys) - by)
            z, thick = spec["z"], spec["thickness"]
    print("balance R %.2f at (%.1f, %.1f), z %.1f" % (bR, bx, by, z), flush=True)

    wheel = balance_wheel(bR, rim_h=thick)
    wheel = wheel.translate((bx, -by, z))

    path = os.path.join(OUT, "balance.stl")
    cq.exporters.export(wheel, path, tolerance=TOL, angularTolerance=0.1)
    print("wrote %s (%d KB)" % (path, os.path.getsize(path) // 1024), flush=True)

    sys.stdout.flush()
    os._exit(0)          # OCCT segfaults on teardown; the file is already written.


if __name__ == "__main__":
    main()
