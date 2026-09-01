"""Geometric assertions on the placed movement, checked after every placement change.

    .venv-cad\\Scripts\\python.exe tools/placement_invariants.py

WHY THIS EXISTS. A 13.2-degree rotation-sign bug sat in the placement for
hours, because nothing asserted what a correct placement actually implies:
that the cock's jewel bore sits ON the balance arbor, that the fork points at
the balance it drives, that a screw threads into the hole drilled for it, and
that the escapement can lock at all. Each of those held up as the eventual
diagnosis, but only after being run once by hand, mid-session, while chasing
a symptom. HANDOVER-REALISM.md is explicit that this is the fix: "those
assertions are three lines each ... they belong in a file that runs after
every placement change." This is that file.

A WEAK CHECK IS WORSE THAN NO CHECK. The same handover describes testing
"nearest vertex to the balance axis is 2.98 units" after placing the cock and
calling it confirmed - a test that cannot fail, because the cock's boss is
near the balance under any rotation of the cock. Every check below is instead
built to fail: it names a SPECIFIC feature (the jewel bore, not the cock's
boss; the fork's horns, not its centre of mass) and a SPECIFIC relationship
that a wrong placement would visibly break.

WHAT IT READS. captures/cad/manifest.json and the STLs beside it - the FINAL
placed movement, already scaled, rotated and translated into face coordinates
by models/step/movement.step.py via cad_parts.py. Nothing here re-derives the
placement from om10_layout; that would be a second opinion about where a part
goes, which is exactly the kind of thing the rotation bug was. It reads what
was actually written to disk and asks whether it is self-consistent - the
same reason render_lib.audit() checks the evaluated mesh instead of the code
that built it.

The one exception is the two cock screw holes: escapement_geometry.COCK_SCREWS
and movement.step.py's STACK both carry that pair of OM10-plane coordinates
as independent hand-written literals, so checking a screw against its hole
also checks that those two files still agree with each other.

RUN THIS after any change to STACK, om10_layout constants, ESCAPE_BEARING, or
anything else upstream of cad_parts.py's manifest - before spending eight
minutes on a full render to find out whether the answer changed. It runs in
about a second.

Exits 0 with everything printed "ok"; exits non-zero and lists every failing
invariant by name otherwise, each with measured vs. expected.
"""

import json
import math
import os
import sys

import numpy as np
import trimesh
from trimesh.path import polygons as tp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import escapement_geometry as eg                              # noqa: E402
import om10_layout as L                                        # noqa: E402

CAD = os.path.join(ROOT, "captures", "cad")

FAILURES = []


def check(name, ok, detail):
    print("[%-4s] %-46s %s" % ("ok" if ok else "FAIL", name, detail))
    if not ok:
        FAILURES.append(name)


def _manifest():
    with open(os.path.join(CAD, "manifest.json")) as f:
        return json.load(f)


def _placed(name):
    """
    A part's mesh, already placed, as vertices in FACE coordinates (x, y down).

    captures/cad/*.stl is exported straight from the placed build123d assembly
    in Blender's y-up convention (see cad_parts.py / movement.step.py's
    `place()`), so every y is negated on the way in - the same flip
    render_lib does on the way into Blender, undone.
    """
    mesh = trimesh.load(os.path.join(CAD, "%s.stl" % name), process=False)
    v = mesh.vertices
    return np.column_stack([v[:, 0], -v[:, 1]])


def _circle_fit(pts):
    """Kasa least-squares circle through a ring of points: (cx, cy, r)."""
    x, y = pts[:, 0], pts[:, 1]
    A = np.column_stack([x, y, np.ones_like(x)])
    b = x ** 2 + y ** 2
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = sol[0] / 2.0, sol[1] / 2.0
    r = math.sqrt(max(sol[2] + cx ** 2 + cy ** 2, 0.0))
    return cx, cy, r


def _angdiff(a, b):
    """Signed shortest angular difference a - b, in (-180, 180]."""
    return (a - b + 180.0) % 360.0 - 180.0


# ------------------------------------------------------- 1. the cock's jewel bore

def check_cock_jewel(manifest):
    """
    The cock's balance jewel bore must sit on the balance arbor.

    The cock's silhouette carries several holes - the jewel bore and two
    screw holes at least. Picking "the biggest" or "the first" would
    silently track the wrong one if the mesh ever changes, so instead every
    interior ring is circle-fit and the one whose fitted centre lands
    nearest the balance pivot is taken to be the bore. If that is wrong, the
    reported distance will be enormous rather than merely off, because no
    other hole on the cock is anywhere near the balance arbor.
    """
    balance = manifest["pivots"]["balance"]
    scale = manifest["scale"]

    poly = tp.projected(trimesh.load(os.path.join(CAD, "cock.stl"), process=False),
                        normal=[0, 0, 1])
    best = None
    for ring in poly.interiors:
        pts = np.array(ring.coords)
        face_pts = np.column_stack([pts[:, 0], -pts[:, 1]])
        cx, cy, r = _circle_fit(face_pts)
        d = math.hypot(cx - balance[0], cy - balance[1])
        if best is None or d < best[0]:
            best = (d, cx, cy, r)
    d, cx, cy, r = best

    tol_mm = 0.05
    d_mm = d / scale
    check("cock jewel bore on balance arbor",
          d_mm <= tol_mm,
          "bore centre (%.2f, %.2f) is %.4f mm from arbor (%.2f, %.2f); tolerance %.2f mm"
          % (cx, cy, d_mm, balance[0], balance[1], tol_mm))


# --------------------------------------------------- 2. the pallet fork's long axis

def check_fork_axis(manifest):
    """
    The pallet fork's long axis must point at the balance it drives.

    A lever escapement's entire mechanical connection to the balance runs
    through one point: the fork's horns cradle the roller jewel on the
    balance staff. "Long axis" is deliberately NOT a moment-of-inertia fit of
    the whole lever body - the lever carries most of its mass over the
    pallet stones, near the escape wheel, so a PCA axis leans toward the
    wrong end by about 3-4 degrees here. The fork's tip is instead the point
    of the lever mesh physically nearest the balance arbor - the horns, by
    construction - and what is checked is the bearing from the pallet arbor
    to that point against the bearing from the pallet arbor to the balance
    arbor. This is exactly the relationship the rotation-sign bug broke: it
    spun the lever about its own pivot by roughly twice the intended angle.
    """
    pallet = manifest["pivots"]["pallet"]
    balance = manifest["pivots"]["balance"]
    pts = _placed("lever")

    d = np.hypot(pts[:, 0] - balance[0], pts[:, 1] - balance[1])
    tip = pts[int(np.argmin(d))]

    bearing_tip = L.bearing_of(tip[0] - pallet[0], tip[1] - pallet[1])
    bearing_balance = L.bearing_of(balance[0] - pallet[0], balance[1] - pallet[1])
    delta = _angdiff(bearing_tip, bearing_balance)

    tol_deg = 15.0
    check("pallet fork points at the balance",
          abs(delta) <= tol_deg,
          "fork tip bears %.2f deg from the pallet arbor, balance bears %.2f deg "
          "(%.2f deg off); tolerance %.1f deg" % (bearing_tip, bearing_balance, delta, tol_deg))


# --------------------------------------------------- 3. cock screws in plate holes

def check_screws_in_holes(manifest):
    """
    Each cock screw must land inside the hole drilled for it.

    escapement_geometry.COCK_SCREWS (the plate's holes) and
    models/step/movement.step.py's STACK (the screws' own placement) are two
    independent hand-written copies of the same two OM10-plane coordinates,
    kept in agreement only by whoever edits one remembering to edit the
    other. This is the check that would catch it if they stopped agreeing -
    the earlier version of this hole was drawn from a bearing-and-radius rule
    that had nothing to do with where the real cock's screws are, and it took
    a stray render to notice the screws threaded into open plate 40 units away.
    """
    scale = manifest["scale"]
    # Face units. See escapement_geometry.plate_openings(): the cock screw
    # bores are drawn at this radius around the same COCK_SCREWS points.
    hole_r = 4.2

    for i, (sx, sz) in enumerate(eg.COCK_SCREWS, start=1):
        hole = eg._PLACE.to_face(sx, sz)
        pts = _placed("screw_%d" % i)
        cx, cy = pts[:, 0].mean(), pts[:, 1].mean()
        d = math.hypot(cx - hole[0], cy - hole[1])
        check("screw_%d inside its plate hole" % i,
              d < hole_r,
              "screw centre is %.3f face units (%.4f mm) from the hole centre "
              "(%.1f, %.1f); hole radius %.1f units"
              % (d, d / scale, hole[0], hole[1], hole_r))


# ------------------------------------------------- 4/5. the pallet stones and lock

def check_pallet_stones(manifest):
    """
    Both pallet stones must reach inside the escape wheel's tooth-tip circle,
    by nearly equal amounts, at a span that is an odd number of half
    tooth-spaces.

    REACH. Unless a stone's innermost point sits inside the circle every
    tooth tip sweeps, the wheel can complete a full turn without ever
    meeting it - there is no escapement, only two wheels sharing a plate.

    EQUAL LOCK. Near-equal reach on entry and exit is what a correctly SET
    escapement has; a stone catching much deeper than its partner is a fork
    that is not centred between its banking pins.

    ODD SPACING. escapement_geometry.py's own reasoning is that the tooth
    count between the stones must be odd or a tooth arrives pointing straight
    into the gap between them and the wheel locks against nothing, in either
    direction - it could not alternate. Rounding the measured span to the
    nearest half-tooth count and checking that count is odd is exactly that
    test, done on the placed geometry instead of assumed from the design.
    """
    scale = manifest["scale"]
    escape = manifest["pivots"]["escape"]
    teeth = manifest["teeth"]["escape"]
    half_tooth_deg = 360.0 / (2 * teeth)

    escape_pts = _placed("escape")
    tip_r = float(np.hypot(escape_pts[:, 0] - escape[0], escape_pts[:, 1] - escape[1]).max())

    locks, bearings = {}, {}
    for name in ("stone_a", "stone_b"):
        pts = _placed(name)
        d = np.hypot(pts[:, 0] - escape[0], pts[:, 1] - escape[1])
        i = int(np.argmin(d))
        locks[name] = (tip_r - d[i]) / scale
        bearings[name] = L.bearing_of(pts[i, 0] - escape[0], pts[i, 1] - escape[1])

    for name in ("stone_a", "stone_b"):
        check("%s reaches inside the escape wheel tip circle" % name,
              locks[name] > 0.0,
              "lock depth %.4f mm (must be positive to ever contact a tooth)" % locks[name])

    tol_mm = 0.05
    diff = abs(locks["stone_a"] - locks["stone_b"])
    check("pallet stones lock by nearly equal amounts",
          diff <= tol_mm,
          "stone_a %.4f mm, stone_b %.4f mm, differ by %.4f mm; tolerance %.2f mm"
          % (locks["stone_a"], locks["stone_b"], diff, tol_mm))

    span = abs(_angdiff(bearings["stone_b"], bearings["stone_a"]))
    half_spaces = span / half_tooth_deg
    nearest = round(half_spaces)
    is_odd = nearest % 2 == 1
    close = abs(half_spaces - nearest) <= 0.3
    check("stone span is an odd number of half tooth-spaces",
          is_odd and close,
          "span %.2f deg = %.2f half tooth-spaces on a %d-tooth wheel -> "
          "nearest whole count %d (%s)"
          % (span, half_spaces, teeth, nearest, "odd" if is_odd else "EVEN"))


def main():
    manifest = _manifest()
    print("placement invariants, from captures/cad/manifest.json")
    print("(scale %.4f face units/mm, rotation %.2f deg)\n"
          % (manifest["scale"], manifest["rotation"]))

    check_cock_jewel(manifest)
    check_fork_axis(manifest)
    check_screws_in_holes(manifest)
    check_pallet_stones(manifest)

    print()
    if FAILURES:
        print("%d invariant(s) failed:" % len(FAILURES))
        for f in FAILURES:
            print("  - %s" % f)
        return 1
    print("all invariants hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
