"""The centre-seconds conversion: an indirect sweep-seconds module on the
back of the OM10, as solids, plus the four OM10 parts it modifies.

    python tools/sweep_seconds.py        # prints the design and writes models/step/sweep-seconds.step
    (tools/gltf_export.py adds the module to Assets/movement.glb and applies the modifications)

WHY. The OM10 is a small-seconds calibre: nothing at the dial's centre turns
once a minute, and the cannon pinion turns on a solid post. The owner wants
a centre seconds hand. The way that has been done to small-seconds
movements for a century is an INDIRECT centre seconds: a transfer wheel on
a lengthened fourth-wheel pivot, an idler, and a centre wheel of the same
count on a long thin arbor up through the middle, with a friction spring so
the hand does not flutter in the backlash. Two meshes keep the direction;
equal counts keep the rate: one turn a minute, the fourth wheel's own.

WHERE. Measured off the solids (scratch scripts, 2026-09-09): the dial side
is crowded to the centre by the motion works and the cannon pinion's pipe
is blind; the back is open - below the barrel bridge and train bridge
(back faces at cad y -2.30) everything is free down to the caseback. So
the module lives at y -2.4 to -3.6 on the back, and the caseback moves
back half a millimetre (case_solids.CASEBACK_Z).

THE PARTS (cad frame: x, z on the plate, y the thickness, dial side +y):
  sweep_transfer   40 t, m 0.11, on the fourth pinion's lengthened pivot at (0, 8)
  sweep_idler      40 t, on a stud at (-1.83, 4.0): 4.40 from each neighbour
  sweep_wheel      40 t, pressed on the arbor at the centre
  sweep_arbor      dia 0.30, from its lower pivot in the cock up through the
                   barrel bridge, the centre post and the cannon pinion to
                   the hand, cad y 6.35 (world 1.54)
  sweep_stud       the idler's post, pressed into the cock
  sweep_cock       the bridge that carries it all, 0.40 thick, two screws
  sweep_jewel, _2  hole jewels in the cock for the arbor and the fourth pivot
  sweep_screw, _2  into the barrel bridge at (2.9, 0.5) and the train bridge at (1.4, 5.3)
  sweep_spring     the friction spring, a blade under a screw head, bearing
                   on the centre wheel's hub

THE OM10 PARTS IT MODIFIES (gltf_export.MODIFIED applies these on export
and the assembly check sees the same; recorded in ATTRIBUTION.md):
  pinion_seconds   back pivot lengthened: dia 0.19 through the bearing,
                   then a dia 0.40 seat for the transfer wheel, then a
                   dia 0.19 pivot for the cock's jewel
  barrel_bridge    bored dia 0.36 at the centre for the arbor
  centre_post      bored dia 0.36: a tube with a 0.17 mm wall, as centre
                   tubes are
  cannon_pinion    its blind pipe drilled through, dia 0.36, from y 2.9 up

Teeth are involute, 20 degrees, module 0.11 - the OM10's own module (third
wheel 72 into seconds pinion 9 at 4.455 mm) - generated here; the OM10's
own teeth are whatever its maker cut, and a module made to fit a movement
is cut to the movement's module.
"""

import math
import os
import sys

from build123d import Circle, Compound, Cylinder, Location, Polyline, export_step, extrude, make_face

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

MODULE = 0.11
TEETH = 40
PRESSURE_DEG = 20.0

FOURTH = (0.0, 8.0)            # cad (x, z): the fourth wheel's arbor
CENTRE = (0.0, 0.0)
IDLER = (-1.83, 4.0)           # 4.40 from each: r 2.2 + r 2.2

WHEEL_TOP = -2.48              # cad y: the three wheels' faces
WHEEL_T = 0.22
HUB_R = 0.55
COCK_TOP = -3.00
COCK_T = 0.40
ARBOR_R = 0.15
ARBOR_TOP = 6.35               # cad y: world 1.54, the hand's pipe seat
PIVOT_R = 0.095                # dia 0.19, as the OM10's train pivots after the 2021 note
BORE_R = 0.18                  # dia 0.36 through the bridge, the post and the cannon pinion
STUD_R = 0.18
SCREWS = ((0.5, -3.0), (1.4, 5.3))   # the first was at (2.9, 0.5) and found the ratchet wheel's recess, not bridge metal
BACKLASH = 0.02                       # mm on the tooth thickness: gears meshed at their exact centre distance bound
CASEBACK_CLEAR = 0.5


def gear(z, m, thickness, y_top, pressure_deg=PRESSURE_DEG, steps=8):
    """An involute spur gear as a solid, axis along y, face at y_top."""
    r = m * z / 2
    ra, rf = r + m, r - 1.25 * m
    alpha = math.radians(pressure_deg)
    rb = r * math.cos(alpha)
    inv = lambda a: math.tan(a) - a
    half_pitch = math.pi / (2 * z) + inv(alpha) - BACKLASH / (2 * r)   # half tooth angle at the base circle, less the backlash

    def half_angle(rad):
        a = math.acos(min(1.0, rb / rad))
        return half_pitch - inv(a)

    pts = []
    tmax = math.sqrt((ra / rb) ** 2 - 1)
    for k in range(z):
        beta = 2 * math.pi * k / z
        flank = [rb * math.sqrt(1 + t * t) for t in [tmax * i / steps for i in range(steps + 1)]]
        root_half = math.pi / z - 0.35 * (math.pi / z - half_angle(rb))
        pts.append((rf, beta - root_half))
        for rad in flank:
            pts.append((rad, beta - half_angle(rad)))
        for rad in reversed(flank):
            pts.append((rad, beta + half_angle(rad)))
        pts.append((rf, beta + root_half))
    xy = [(rad * math.cos(a), rad * math.sin(a)) for rad, a in pts]
    face = make_face(Polyline(*xy, xy[0]))
    # built in the XY plane along Z; turned so the axis is Y (cad thickness):
    # a -90 turn about X sends +Z to +Y, so the solid rises from where it is
    # put. Put at the face minus the thickness, it ends at the face.
    return extrude(face, thickness).moved(Location((0, 0, 0), (-90, 0, 0))).moved(Location((0, y_top - thickness, 0)))


def at(shape, xz):
    return shape.moved(Location((xz[0], 0, xz[1])))


def cyl_y(r, y_lo, y_hi, xz=(0.0, 0.0)):
    """A cylinder along cad y between two heights."""
    return Cylinder(r, y_hi - y_lo, align=(None, None, None)).moved(Location((0, 0, 0), (-90, 0, 0))).moved(Location((xz[0], y_lo, xz[1])))


def sweep_transfer():
    g = gear(TEETH, MODULE, WHEEL_T, WHEEL_TOP)
    hub = cyl_y(HUB_R, WHEEL_TOP - WHEEL_T - 0.05, WHEEL_TOP + 0.03)
    bore = cyl_y(0.20, WHEEL_TOP - WHEEL_T - 0.2, WHEEL_TOP + 0.2)
    return at((g + hub) - bore, FOURTH)


def sweep_idler():
    g = gear(TEETH, MODULE, WHEEL_T, WHEEL_TOP)
    hub = cyl_y(HUB_R, WHEEL_TOP - WHEEL_T - 0.05, WHEEL_TOP + 0.03)
    bore = cyl_y(STUD_R + 0.02, WHEEL_TOP - WHEEL_T - 0.2, WHEEL_TOP + 0.2)
    return at((g + hub) - bore, IDLER)


def sweep_wheel():
    g = gear(TEETH, MODULE, WHEEL_T, WHEEL_TOP)
    hub = cyl_y(HUB_R, WHEEL_TOP - WHEEL_T - 0.10, WHEEL_TOP + 0.03)
    bore = cyl_y(ARBOR_R, WHEEL_TOP - WHEEL_T - 0.3, WHEEL_TOP + 0.2)
    return at((g + hub) - bore, CENTRE)


def sweep_arbor():
    """The long arbor: a lower pivot in the cock's jewel, the body, the top
    the hand presses on. One turned part."""
    pivot = cyl_y(PIVOT_R, COCK_TOP - COCK_T + 0.15, COCK_TOP + 0.02)
    body = cyl_y(ARBOR_R, COCK_TOP, ARBOR_TOP)
    return at(pivot + body, CENTRE)


def sweep_stud():
    return at(cyl_y(STUD_R, COCK_TOP - COCK_T + 0.1, WHEEL_TOP + 0.10), IDLER)


def sweep_cock():
    """A Y-shaped bridge under the three wheels: a lobe at each pivot,
    bars between, two feet with screw holes. Jewel holes at the arbor and
    the fourth pivot, a press hole for the stud."""
    lobe = 1.3
    body = None
    for p in (CENTRE, IDLER, FOURTH, SCREWS[0], SCREWS[1]):
        c = Circle(lobe if p in (CENTRE, IDLER, FOURTH) else 0.9).moved(Location(p))
        body = c if body is None else body + c

    def bar(p, q, w=2.0):
        dx, dz = q[0] - p[0], q[1] - p[1]
        L = math.hypot(dx, dz)
        ux, uz = dx / L, dz / L
        nx, nz = -uz * w / 2, ux * w / 2
        return make_face(Polyline((p[0] + nx, p[1] + nz), (q[0] + nx, q[1] + nz), (q[0] - nx, q[1] - nz), (p[0] - nx, p[1] - nz), (p[0] + nx, p[1] + nz)))

    for p, q in ((CENTRE, IDLER), (IDLER, FOURTH), (CENTRE, SCREWS[0]), (FOURTH, SCREWS[1])):
        body = body + bar(p, q)
    plate = extrude(body, COCK_T).moved(Location((0, 0, 0), (-90, 0, 0))).moved(Location((0, COCK_TOP - COCK_T, 0)))
    for p in (CENTRE, FOURTH):
        plate = plate - cyl_y(0.42, COCK_TOP - COCK_T - 0.1, COCK_TOP + 0.1, p)     # jewel seats
    plate = plate - cyl_y(STUD_R - 0.01, COCK_TOP - COCK_T - 0.1, COCK_TOP + 0.1, IDLER)   # the stud's press hole
    for p in SCREWS:
        plate = plate - cyl_y(0.19, COCK_TOP - COCK_T - 0.1, COCK_TOP + 0.1, p)
    return plate


def sweep_jewel(which):
    p = CENTRE if which == 1 else FOURTH
    ring = cyl_y(0.40, COCK_TOP - COCK_T + 0.02, COCK_TOP - 0.02, p) - cyl_y(PIVOT_R + 0.006, COCK_TOP - COCK_T - 0.1, COCK_TOP + 0.1, p)
    return ring


def sweep_screw(which):
    p = SCREWS[which - 1]
    shank = cyl_y(0.17, COCK_TOP - 0.05, COCK_TOP + 1.0, p)          # 1.0 mm into the bridge above
    head = cyl_y(0.42, COCK_TOP - COCK_T - 0.30, COCK_TOP - COCK_T, p)
    slot = make_face(Polyline((-0.5, -0.05), (0.5, -0.05), (0.5, 0.05), (-0.5, 0.05), (-0.5, -0.05)))
    slot = extrude(slot, 0.12).moved(Location((0, 0, 0), (-90, 0, 0))).moved(Location((p[0], COCK_TOP - COCK_T - 0.30, p[1])))
    return (shank + head) - slot


def sweep_spring():
    """The friction spring: a blade 0.06 thick clamped under the first
    screw's head, reaching to the centre wheel's hub and pressing on its
    face. What keeps a sweep hand from fluttering."""
    p = SCREWS[0]
    x0, z0 = p
    x1, z1 = HUB_R + 0.05, 0.0
    pts = [(x0 + 0.35, z0 + 0.2), (x0 - 0.35, z0 + 0.2), (x1, z1 + 0.25), (x1, z1 - 0.25), (x0 - 0.35, z0 - 0.2), (x0 + 0.35, z0 - 0.2)]
    blade = make_face(Polyline(*pts, pts[0]))
    # Bearing on the centre wheel's hub, whose underside is at the wheel
    # face minus its thickness minus its hub's 0.10: the blade's top touches it.
    blade = extrude(blade, 0.06).moved(Location((0, 0, 0), (-90, 0, 0))).moved(Location((0, WHEEL_TOP - WHEEL_T - 0.10 - 0.06, 0)))
    return blade - cyl_y(0.19, COCK_TOP - 1, COCK_TOP + 1, p)


def parts():
    """(name, build123d solid) for every part of the module, cad frame."""
    return [
        ("sweep_transfer", sweep_transfer()),
        ("sweep_idler", sweep_idler()),
        ("sweep_wheel", sweep_wheel()),
        ("sweep_arbor", sweep_arbor()),
        ("sweep_stud", sweep_stud()),
        ("sweep_cock", sweep_cock()),
        ("sweep_jewel", sweep_jewel(1)),
        ("sweep_jewel_2", sweep_jewel(2)),
        ("sweep_screw", sweep_screw(1)),
        ("sweep_screw_2", sweep_screw(2)),
        ("sweep_spring", sweep_spring()),
    ]


# ---- the OM10 parts the conversion modifies, as OCP shape -> OCP shape
def _cut(shape, tool):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    return BRepAlgoAPI_Cut(shape, tool.wrapped).Shape()


def _fuse(shape, tool):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    return BRepAlgoAPI_Fuse(shape, tool.wrapped).Shape()


def modify_pinion_seconds(shape):
    ext = cyl_y(PIVOT_R, -2.36, -2.10, FOURTH)                     # through the bearing, dia 0.19
    seat = cyl_y(0.20, -2.95, -2.36, FOURTH)                       # the transfer wheel's seat, dia 0.40
    pivot = cyl_y(PIVOT_R, COCK_TOP - COCK_T + 0.15, -2.95, FOURTH)  # into the cock's jewel
    return _fuse(_fuse(_fuse(shape, ext), seat), pivot)


def modify_barrel_bridge(shape):
    return _cut(shape, cyl_y(BORE_R, -2.6, 0.0, CENTRE))


def modify_centre_post(shape):
    return _cut(shape, cyl_y(BORE_R, -0.2, 2.8, CENTRE))


def modify_cannon_pinion(shape):
    return _cut(shape, cyl_y(BORE_R, 2.5, 4.4, CENTRE))


MODIFIED = {
    "pinion_seconds": modify_pinion_seconds,
    "barrel_bridge": modify_barrel_bridge,
    "centre_post": modify_centre_post,
    "cannon_pinion": modify_cannon_pinion,
}


def main():
    r = MODULE * TEETH / 2
    print("  wheels: %d teeth, module %.2f, pitch r %.2f, tip r %.2f; centres %.2f apart" % (
        TEETH, MODULE, r, r + MODULE, math.hypot(IDLER[0] - FOURTH[0], IDLER[1] - FOURTH[1])))
    ps = parts()
    for name, solid in ps:
        if not solid.is_valid:
            raise SystemExit(name + " is not a valid solid")
        bb = solid.bounding_box()
        print("  %-16s volume %7.3f mm3  y %+.2f..%+.2f" % (name, solid.volume, bb.min.Y, bb.max.Y))
    out = os.path.join(ROOT, "models", "step", "sweep-seconds.step")
    export_step(Compound(children=[p[1] for p in ps]), out)
    print("  wrote", out)


if __name__ == "__main__":
    main()
