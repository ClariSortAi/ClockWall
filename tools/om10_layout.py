"""Where the OM10's parts go in the face, and how big.

Imported by escapement_geometry (which owns the rest of the layout) and by
models/step/movement.step.py (which builds the assembly). One module, so the
render and the CAD cannot disagree about where the balance is.

THE ONE IDEA HERE. Every part of the escapement is placed by a SINGLE similarity
transform applied to the whole cluster - one scale, one rotation, one
translation. That is not a shortcut, it is the correctness argument: a similarity
preserves every distance ratio and every angle, so if the OM10 escapement works
(and it does, it is a real movement that has been prototyped) then the placed
copy works too. Interference, mesh, the line of centres, the pallet span, the
roller's reach - none of them can be broken by scaling. They could only be broken
by moving one part relative to another, and nothing here does that.

The previous layout placed each part from its own remembered fraction, which is
why it needed a clash checker, a mesh derivation and a pallet-phase solver to
put right one relationship at a time. Those checks all still run. They just have
nothing left to find in the escapement, because it is no longer being invented.

WHAT IS CHOSEN AND WHAT IS MEASURED. Two numbers are ours, and both are framing:
where the balance sits in the window, and which way the escapement runs from it.
Everything else - radii, centres, tooth counts, heights - is measured off the
OM10 and may not be edited here.
"""

import math

# --------------------------------------------------------------- measurements
#
# Taken from openmovement.org's OM10 STEP by tools/om10_extract.py, in
# millimetres, in the movement's own plane. Do not hand-edit: re-run the
# extractor. The arbors are the axes parts turn about, not bounding-box centres.
OM10_MM = {
    "balance_r": 5.455,
    "escape_r": 2.633,
    "lever_r": 2.643,
    "fourth_r": 3.464,
    "cock_r": 7.194,
}

# Arbor positions in the OM10's own plane (x, z of the original export).
AXIS = {
    "balance": (-8.06, 3.51),
    "pallet": (-5.87, 5.71),
    "escape": (-3.68, 7.90),
    "fourth": (0.00, 8.00),
}

# Tooth counts, counted off the solids rather than chosen. These set the beat
# and every rotation rate downstream, so they are facts, not parameters.
ESCAPE_TEETH = 20
ESCAPE_PINION_LEAVES = 8
FOURTH_TEETH = 84

# The escapement's line of centres. Measured, and it comes out straight: the
# pallet staff sits at 0.5006 of the way from balance to escape wheel. Our own
# geometry had guessed 0.591, and before that had the whole line 22 degrees bent.
PALLET_FRACTION = (
    math.hypot(AXIS["pallet"][0] - AXIS["balance"][0],
               AXIS["pallet"][1] - AXIS["balance"][1]) /
    math.hypot(AXIS["escape"][0] - AXIS["balance"][0],
               AXIS["escape"][1] - AXIS["balance"][1]))

# The real span between balance and escape arbors, in millimetres.
SPAN_MM = math.hypot(AXIS["escape"][0] - AXIS["balance"][0],
                     AXIS["escape"][1] - AXIS["balance"][1])


# ------------------------------------------------------------------- placement

def bearing_of(dx, dy):
    """Degrees clockwise from twelve, in face coordinates (y runs down)."""
    return math.degrees(math.atan2(dx, -dy)) % 360.0


def make(balance_xy, balance_r, escape_bearing):
    """
    Build the placement from the two things that are ours to choose.

    `balance_xy` and `balance_r` say where the hero sits in the window and how
    big it is; `escape_bearing` says which way the rest of the movement runs
    from it, clockwise from twelve. Everything else follows from the OM10.

    Returns an object with `to_face(u, v)` for a point in the OM10's plane,
    `to_z(mm)` for a height, and the derived centres.
    """
    scale = balance_r / OM10_MM["balance_r"]

    # The rotation that carries the OM10's own balance-to-escape direction onto
    # the bearing we want. Derived, so moving the framing cannot silently leave
    # the parts pointing the old way.
    bx, bz = AXIS["balance"]
    ex, ez = AXIS["escape"]
    native = bearing_of(ex - bx, -(ez - bz))   # OM10 plane -> face y-down
    rot = math.radians(escape_bearing - native)
    cos_r, sin_r = math.cos(rot), math.sin(rot)

    class Placement:
        SCALE = scale
        ROT_DEG = escape_bearing - native

        @staticmethod
        def to_face(u, v):
            """A point in the OM10 plane -> face coordinates."""
            # Into face orientation first (y down), then rotate, then scale.
            fx, fy = u - bx, -(v - bz)
            rx = fx * cos_r - fy * sin_r
            ry = fx * sin_r + fy * cos_r
            return (balance_xy[0] + rx * scale, balance_xy[1] + ry * scale)

        @staticmethod
        def to_z(mm, floor_mm=-0.97, plate_top=7.0):
            """
            A height in the OM10 -> height above the mainplate, in face units.

            `floor_mm` is the lowest point of the parts we show (the roller's
            underside), so the movement sits ON the plate rather than through it.
            The relative heights are untouched: the hairspring stays above the
            balance and the lever stays under the escape wheel because that is
            where OM10 puts them, and it is the only arrangement that assembles.
            """
            return (mm - floor_mm) * scale + plate_top

        @staticmethod
        def axis_face(name):
            return Placement.to_face(*AXIS[name])

    return Placement
