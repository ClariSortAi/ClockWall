"""The hairspring, designed from its own numbers.

    python tools/hairspring.py        # -> Assets/mechanism.json, models/step/hairspring.step
    (and tools/gltf_export.py puts the solid into Assets/movement.glb in place of OM10-00115)

WHY THIS EXISTS. The OM10 STEP's hairspring is a placeholder: a 0.020 mm
strip, 0.16 wide, 133 mm long, which at 200 GPa gives 1.5 Hz against a train
that only keeps time at 3.5 Hz. Every other number in the mechanism is
measured off a solid; the stiffness was the one taken from the train. This
file makes the spring a spring: a strip of chosen gauge, wound as an
Archimedean spiral into the OM10's own envelope, whose stiffness follows from
its section and its active length, and whose rate is then trimmed the way a
watchmaker trims one - by moving the regulator's pins along the outer coil.

THE DESIGN, in the order a spring maker would do it:
  1. The balance is given: its inertia is measured off the solids.
  2. The rate is given: 3.5 Hz, fixed by the train's tooth counts.
  3. So the stiffness is fixed: k = I (2 pi f)^2.
  4. Choose the alloy and the strip: E = 200 GPa (a Nivarox-type alloy),
     width 0.16 mm (the OM10's layer), thickness 0.035 mm - a gauge that is
     made, and the one that puts the active length inside the OM10's
     envelope: L = E w t^3 / (12 k).
  5. Wind it: Archimedean, from the collet at 0.65 mm out to 2.75 over N
     coils, a terminal curve out to the stud at 3.10, ending where the OM10's
     stud is (66 degrees from the staff, its spiral turning the same way).
  6. Vibrate it: the pins' angle along the outer coil is set so the free
     rate, plus the escapement's known error, comes to 3.5 Hz. That angle is
     the regulator's index, and it is written down.

Everything the mechanism needs comes out as Assets/mechanism.json; nothing
about the spring is typed into C#.
"""

import json
import math
import os

from build123d import Location, Polyline, export_step, extrude, make_face

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ------------------------------------------------------------------ the balance
# kg m^2, off the OM10 solids: balance 1.848e-9 at brass 8.5 g/cm^3, staff,
# roller and collet 0.002e-9 at steel. The spring's own share is added below.
BALANCE_INERTIA = 1.850e-9
# The escapement error measured by running the mechanism with the impulse
# after centre: the free period is pulled this many seconds a day slow. It
# grew from -2.9 to -7.2 as the designed mainspring's torque replaced the
# typical figure; a stronger push off-centre pulls harder. Re-measure it
# (the fault log prints the kept rate at every launch, with this file's
# regulation already applied) whenever the torque or the lift changes.
ESCAPEMENT_ERROR_S_PER_DAY = -7.2

# ------------------------------------------------------------------ the strip
E = 200e9            # Pa, Nivarox-type alloy
WIDTH = 0.16e-3      # m, the OM10's layer height (its y range -0.91..-0.75)
THICKNESS = 0.035e-3 # m, a made gauge
DENSITY = 8000.0     # kg/m^3

# ------------------------------------------------------------------ the envelope, OM10 mm
STAFF = (-8.06, 3.51)        # CAD (x, z)
LAYER_Y = (-0.91, -0.75)     # the OM10 spring's layer
R_IN = 0.65
R_OUT = 2.75
R_STUD = 3.10
STUD_ANGLE_DEG = 66.1        # where the OM10's stud sits, from the staff, CAD atan2(z, x)
TERMINAL_DEG = 90.0          # the last quarter turn eases out to the stud radius

RATE_HZ = 3.5


def design():
    """The numbers, before any geometry."""
    omega0 = 2 * math.pi * RATE_HZ
    # The rate the free spring must have so that, pulled slow by the
    # escapement, the watch keeps 3.5 Hz. This is what a timing machine
    # would tell the watchmaker to regulate to.
    target_free = RATE_HZ * (1 - ESCAPEMENT_ERROR_S_PER_DAY / 86400.0)
    # First pass: stiffness for the balance alone, then add the spring's own
    # inertia and iterate once.
    inertia = BALANCE_INERTIA
    for _ in range(3):
        k = inertia * (2 * math.pi * target_free) ** 2
        active = E * WIDTH * THICKNESS ** 3 / (12 * k)          # m
        mass = DENSITY * WIDTH * THICKNESS * active
        # A spiral pinned at its outer end: the inner coils move with the
        # collet and the outer ones hardly at all. A third of m r^2 at the
        # mean radius is the textbook share.
        r_mean = (R_IN + R_OUT) / 2 * 1e-3
        inertia = BALANCE_INERTIA + mass * r_mean ** 2 / 3
    return dict(stiffness=k, active_length=active, inertia=inertia, target_free_hz=target_free, mass=mass)


def spiral(active_length_m):
    """The centreline: Archimedean from R_IN to R_OUT over as many coils as
    the active length wants, then a terminal quarter turn out to the stud.
    Returns (coils, theta_start, theta_end, pins_theta) in radians, CAD frame,
    theta = atan2(z, x), radius growing with theta as the OM10's does."""
    # Arc length of an Archimedean spiral is close to pi N (r_in + r_out);
    # the terminal curve adds about a quarter turn at the stud radius.
    terminal = math.radians(TERMINAL_DEG) * (R_OUT + R_STUD) / 2
    coils = (active_length_m * 1e3 - terminal) / (math.pi * (R_IN + R_OUT))
    theta_end = math.radians(STUD_ANGLE_DEG)
    theta_start = theta_end - 2 * math.pi * coils - math.radians(TERMINAL_DEG)
    return coils, theta_start, theta_end


def radius_at(theta, coils, theta_start, theta_end):
    t_spiral_end = theta_end - math.radians(TERMINAL_DEG)
    if theta <= t_spiral_end:
        return R_IN + (R_OUT - R_IN) * (theta - theta_start) / (2 * math.pi * coils)
    # Ease from R_OUT to R_STUD over the terminal quarter turn.
    u = (theta - t_spiral_end) / math.radians(TERMINAL_DEG)
    return R_OUT + (R_STUD - R_OUT) * (0.5 - 0.5 * math.cos(math.pi * u))


def build(numbers):
    """The solid, in the OM10's frame: the plate is (x, z), y is thickness."""
    coils, t0, t1 = spiral(numbers["active_length"])
    steps = int((t1 - t0) / math.radians(2.0))
    half = THICKNESS * 1e3 / 2
    outer, inner = [], []
    for k in range(steps + 1):
        th = t0 + (t1 - t0) * k / steps
        r = radius_at(th, coils, t0, t1)
        c, s = math.cos(th), math.sin(th)
        # Built flat in build123d's (x, y) plane and then rotated -90 about
        # X, which carries that plane's y onto the OM10's -z. The OM10's
        # spiral grows counter-clockwise in (x, z), so it is drawn here with
        # y negated: measured after the first attempt came out mirrored, with
        # its end at -66 degrees instead of +66.
        outer.append(((r + half) * c, -(r + half) * s))
        inner.append(((r - half) * c, -(r - half) * s))
    pts = outer + inner[::-1]
    face = make_face(Polyline(*pts, pts[0]))
    strip = extrude(face, WIDTH * 1e3)
    y_mid = (LAYER_Y[0] + LAYER_Y[1]) / 2
    strip = strip.moved(Location((STAFF[0], y_mid - WIDTH * 1e3 / 2, STAFF[1]), (-90, 0, 0)))
    return strip, coils


def main():
    numbers = design()
    strip, coils = build(numbers)
    free_hz = math.sqrt(numbers["stiffness"] / numbers["inertia"]) / (2 * math.pi)
    out = {
        "inertia": numbers["inertia"],
        "hairspring": {
            "youngs_modulus": E,
            "width": WIDTH,
            "thickness": THICKNESS,
            "active_length": numbers["active_length"],
            "stiffness": numbers["stiffness"],
            "coils": coils,
            "r_in_mm": R_IN, "r_out_mm": R_OUT, "r_stud_mm": R_STUD,
            "stud_angle_deg": STUD_ANGLE_DEG,
            "free_rate_hz": free_hz,
            "regulated_for_escapement_error_s_per_day": ESCAPEMENT_ERROR_S_PER_DAY,
            "note": "Archimedean strip designed for the measured inertia at 3.5 Hz; "
                    "the OM10 STEP's 0.020 mm spring is a placeholder and is not used.",
        },
    }
    os.makedirs(os.path.join(ROOT, "Assets"), exist_ok=True)
    path = os.path.join(ROOT, "Assets", "mechanism.json")
    # Merge: mainspring.py writes its own section into the same file, and
    # regenerating one spring must not lose the other.
    doc = json.load(open(path)) if os.path.exists(path) else {}
    doc.update(out)
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)
    export_step(strip, os.path.join(ROOT, "models", "step", "hairspring.step"))
    print("  strip %.3f x %.3f mm, active length %.2f mm, %.2f coils, k = %.4g N m/rad"
          % (THICKNESS * 1e3, WIDTH * 1e3, numbers["active_length"] * 1e3, coils, numbers["stiffness"]))
    print("  free rate %.4f Hz (regulated %.1f s/day fast to cancel the escapement error); volume %.4f mm3"
          % (free_hz, -ESCAPEMENT_ERROR_S_PER_DAY, strip.volume))
    print("  wrote Assets/mechanism.json and models/step/hairspring.step")


if __name__ == "__main__":
    main()
