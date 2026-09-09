"""The case, dial, hands and crown as watertight solids.

    python tools/case_solids.py        # -> Assets/case.glb, models/step/case.step

WHAT THIS IS. Everything on the watch that is not the OM10 movement, modelled
in build123d as closed solids - the same kernel and the same tessellator as
the movement - rather than as the single-sided render meshes the live face was
first built with. A solid can be exported to STEP, checked for interference
against the movement, scaled and printed. A render mesh can only be looked at.

THE DIRECTION OF TRAVEL. This watch is meant to become an object that works:
every part a solid that could be made, and the time driven by the mechanism
rather than the system clock. So the hands here sit on the OM10's own arbors.
The OM10 carries its cannon pinion and hour wheel at its plate centre, which
gltf_export.py lands on the dial centre; the hour and minute hands are collars
on those. The seconds hand sits on the seconds wheel's arbor, 8 mm out at
nine o'clock, which is where the OM10 puts it. The stem is the OM10's own,
running out at three; only the crown is ours. The open heart is over the
balance, under eleven, because that is where the balance is.

WHAT IS STILL OURS AND NOT THE OM10'S: the case, crystal, dial, indices, the
hands and their collars, the crown. What is still missing: the case band has
a hole for the stem but no case tube; the hand collars are plain tubes rather
than the friction fit a real hand has.

FRAME. CAD is Z-up, millimetres, the dial's top face at z = 0. x runs to the
right of the dial and y UP the dial toward twelve, so a point that is (x, y)
on the screen with y down is (x, -y) here. tools/gltf_export.write_glb turns
this into the renderer's Y-up world, where +Z runs down the dial.
"""

import math
import os
import sys

from build123d import (Axis, Circle, Compound, Cylinder, Line, Location, Plane,
                       Polyline, Shell, Solid, ThreePointArc, chamfer, extrude,
                       make_face, offset, revolve)
from build123d import export_step

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gltf_export as G                                       # noqa: E402

U = 1.0 / 11.780018          # mm per face unit: case_geometry.py's numbers carried over

# ------------------------------------------------------------------ dimensions
# Rendering/WatchDesign.cs holds the same numbers; when the design moves, both
# move, and the STEP is the one that can be measured.
DIAL_R = 288 * U
BEZEL_IN = 289 * U
CASE_R = 314 * U
# The crystal. A box sapphire: flat underneath at CRYSTAL_UNDER, seated in
# the bezel up to CRYSTAL_SEAT, then its polished side stands PROUD of the
# bezel's ledge to CRYSTAL_SIDE, turns in through a bevel CRYSTAL_BEVEL
# wide, and domes gently to CRYSTAL_PEAK. The first crystal was a low dome
# whose side sat entirely inside the seat; optically it was a flat plate
# (0.27 px of refraction at the rim) and it never read as glass. Glass is
# read at its EDGE, where the bevel and the side bend what is behind them.
CRYSTAL_UNDER = 1.9
CRYSTAL_SEAT = 2.7
CRYSTAL_SIDE = 3.15
CRYSTAL_BEVEL = 0.55
CRYSTAL_BEVEL_TOP = 3.55
CRYSTAL_PEAK = 4.05

INDEX_IN, INDEX_OUT, INDEX_HALF_W = 246 * U, 279 * U, 7.5 * U
INDEX_H, INDEX_CHAMFER = 0.45, 0.12
TWELVE_HALF_W, TWELVE_OFFSET = 4.4 * U, 6.2 * U

# The opening, over the OM10's balance: the balance arbor is at world
# (-3.51, -8.06) - up and to the left, under eleven - and the escapement runs
# from it toward ten. The aperture is pulled 30% of the way from the balance
# toward the escape wheel and made big enough to take the seconds wheel at
# nine as well, so the one window shows the whole going end of the train:
# balance, escapement, seconds wheel with its hand. Its far edge stays inside
# the indices. All of it in this file's frame: x right, y UP the dial.
APERTURE = (-4.83, 6.75)
APERTURE_R = 10.2
REHAUT_OUT = APERTURE_R + 0.6
WELL_WALL = 0.5                      # the well wall's thickness, outside APERTURE_R
# The dial's opening clears the well wall's OUTSIDE by a twentieth; the
# rehaut's flat top covers the joint. Same for the plate's window in
# gltf_export.OPEN_HEART_R. The first cut had the wall pass through both.
DIAL_HOLE_R = APERTURE_R + WELL_WALL + 0.05
DIAL_T = 0.4
DIAL_CLEARANCE = 0.05                # the dial's edge inside the case's rehaut wall
# The balance sits 5.2 mm under the dial's face in the OM10's stack; the well
# wall drops most of that way.
WELL_DEPTH = 4.6

# The seconds wheel's arbor: the OM10's, at nine o'clock, 8 mm out.
SECONDS_ARBOR = (-8.0, 0.0)

# The OM10's dial seat (the plate's dial face, its y = 4.41) carries the
# dial's underside; the dial is 0.4 thick, so the movement's y = 0 plane is
# 4.81 below the dial's face. Heights from Assets/movement-parts.json.
MOVEMENT_Z = -4.81
CANNON_PINION_TOP = 4.15 + MOVEMENT_Z    # OM10-00127
HOUR_WHEEL_TOP = 3.60 + MOVEMENT_Z       # OM10-00206
SECONDS_PINION_TOP = 2.94 + MOVEMENT_Z   # OM10-00164
CANNON_PIPE_R = 0.60                     # the cannon pinion's pipe where the hands press on: r 0.600 up to y 4.05, measured off OM10-00127
MINUTE_COLLAR_R = 0.85                   # the minute hand's pipe, over the cannon pinion
HOUR_COLLAR_R = 1.10                     # the hour hand's pipe, over the minute hand's
DIAL_BORE_R = HOUR_COLLAR_R + 0.05       # the dial's centre hole clears the outer collar
STEM_Z = MOVEMENT_Z                      # the OM10's stem lies in its y = 0 plane

# Lowered for the centre seconds: the sweep hand rides over the minute
# hand and under the crystal's underside (1.9), and 0.3 mm to spare there
# is what a watch has.
HOUR = dict(length=150 * U, half_w=11 * U, shoulder=44 * U, tail=34 * U, base=0.75, ridge=0.19)
MINUTE = dict(length=214 * U, half_w=9 * U, shoulder=54 * U, tail=40 * U, base=1.15, ridge=0.16)
SWEEP = dict(length=270 * U, tail=95 * U, half_w=0.09, base=1.42, thick=0.10)   # the centre seconds hand
SWEEP_ARBOR_R = 0.15                     # sweep_seconds.ARBOR_R; its top at world 1.54
CAP_R = 13 * U

# ------------------------------------------------------------------ materials
# Courtesy PBR for other viewers; the renderer keys its own on the node name.
STEEL = ((0.680, 0.700, 0.740), 1.0, 0.11)
BLUED = ((0.035, 0.075, 0.300), 1.0, 0.10)
DIAL = ((0.0116, 0.0395, 0.181), 1.0, 0.40)
GLASS = ((0.9, 0.92, 1.0), 0.0, 0.02)


def profile(points_and_arcs):
    """A closed planar wire in (r, z) from a mix of points and ('arc', mid)
    markers, as a face on the XZ plane ready to revolve about Z."""
    edges = []
    prev = points_and_arcs[0]
    for item in points_and_arcs[1:]:
        if isinstance(item, tuple) and item and item[0] == "arc":
            _, mid, end = item
            edges.append(ThreePointArc(prev, mid, end))
            prev = end
        else:
            edges.append(Line(prev, item))
            prev = item
    if prev != points_and_arcs[0]:
        edges.append(Line(prev, points_and_arcs[0]))
    wire = edges[0]
    for e in edges[1:]:
        wire = wire + e
    return Plane.XZ * make_face(wire)


def case():
    """Bezel, rehaut wall, case band and the flange the dial sits on, one
    solid of revolution. Same profile the render lathe had, closed."""
    ri, ro, seat = BEZEL_IN, CASE_R, CRYSTAL_SEAT
    x0, x1 = ri + 0.9, ro - 0.55
    top = seat + 0.62
    dome_r = 22.0
    dome_c = ((x0 + x1) / 2, top - dome_r)
    def on_dome(x):
        return (x, dome_c[1] + math.sqrt(dome_r ** 2 - (x - dome_c[0]) ** 2))
    edge_r = 0.55
    edge_c = (ro - edge_r, on_dome(x1)[1] - edge_r)
    # The flange the dial rests on is at the dial's UNDERSIDE, so the dial
    # sits on it rather than in it; the assembly check found the dial
    # buried 0.35 mm into the band the first time.
    pts = [
        (ri - 0.8, -DIAL_T), (ri, -DIAL_T), (ri, seat), (ri + 0.35, seat), on_dome(x0),
        ("arc", on_dome((x0 + x1) / 2), on_dome(x1)),
        ("arc", (edge_c[0] + edge_r * math.cos(math.radians(45)), edge_c[1] + edge_r * math.sin(math.radians(45))), (ro, edge_c[1])),
        (ro, -8.3), (ro - 1.5, -8.8), (ri - 0.8, -8.8),   # deeper by 1.8 for the sweep module and a caseback that clears the bridges
    ]
    band = revolve(profile(pts), Axis.Z)
    # The stem hole: the OM10's stem (OM10-00225) runs out at three in its
    # y = 0 plane, 1.5 mm across at the case. It starts inside the flange
    # the dial sits on, which the stem crosses first; the assembly check
    # found the stem in the flange when the hole began at the band.
    hole = Cylinder(0.95, 8.0, align=(None, None, None)).moved(Location((ri - 1.5, 0, STEM_Z), (0, 90, 0)))
    return band - hole


CASEBACK_Z = -10.2                       # its outer face; inner face -8.8, 0.3 behind the sweep module's screw heads


def caseback():
    """A snap back closing the band. Not visible from the front; here so the
    case is a vessel and not a ring. It sat at -8.4 once, which put its
    inner face 0.1 mm INTO the bridges' back faces; nothing had checked it."""
    return Cylinder(BEZEL_IN - 0.8 - 0.05, 1.4, align=(None, None, None)).moved(Location((0, 0, CASEBACK_Z)))


def crystal():
    """A box sapphire: flat underneath, a polished side proud of the bezel,
    a bevel, and a gentle spherical dome. See the constants above."""
    chord = BEZEL_IN - 0.05
    inner = chord - CRYSTAL_BEVEL
    sag = CRYSTAL_PEAK - CRYSTAL_BEVEL_TOP
    sphere_r = (inner ** 2 + sag ** 2) / (2 * sag)
    cz = CRYSTAL_PEAK - sphere_r
    mid_x = inner * 0.5
    mid = (mid_x, cz + math.sqrt(sphere_r ** 2 - mid_x ** 2))
    pts = [(0, CRYSTAL_UNDER), (chord, CRYSTAL_UNDER), (chord, CRYSTAL_SIDE),
           (inner, CRYSTAL_BEVEL_TOP), ("arc", mid, (0, CRYSTAL_PEAK))]
    return revolve(profile(pts), Axis.Z)


# The opening is a keyhole: the heart round the balance, bulged out round
# the seconds arbor at nine so a real sub-dial fits there. The plate's cut
# follows it (gltf_export.SECONDS_WINDOW_R), with a bar and two bosses
# under the bulge that hold the train's bearings and carry the fixture.
SECONDS_WIN_R = 4.6
WELL_DEPTH_AT_SECONDS = 2.8              # the well wall stops above the plate's bar there (world -2.96)


def window():
    # Round again: the keyhole carried the small-seconds sub-dial, and the
    # centre seconds retired it.
    return Circle(APERTURE_R).moved(Location(APERTURE))


def dial():
    """The dial plate, 0.4 mm, with the opening and the centre bore cut clean
    through. The printing and the minute track are ink, in the shader."""
    sk = Circle(BEZEL_IN - DIAL_CLEARANCE) - Circle(DIAL_BORE_R) - offset(window(), WELL_WALL + 0.05)
    return extrude(sk, DIAL_T).moved(Location((0, 0, -DIAL_T)))


def rehaut():
    """The polished ring standing in the opening, with the well wall inside
    it. A lathe part again now the opening is round; the keyhole's
    offset-built version is in the history with the sub-dial it served."""
    ri, ro = APERTURE_R, REHAUT_OUT
    pts = [(ro, 0.0), (ro, 0.22), (ro - 0.14, 0.36), (ri + 0.16, 0.36), (ri, 0.20),
           (ri, -WELL_DEPTH), (ri + WELL_WALL, -WELL_DEPTH), (ri + WELL_WALL, 0.0)]
    return revolve(profile(pts), Axis.Z).moved(Location(APERTURE))


def baton(deg, half_w, offset):
    a = math.radians(deg)
    ux, uy = math.sin(a), math.cos(a)        # toward the rim, y up
    vx, vy = uy, -ux
    def at(r, w):
        return (ux * r + vx * (w + offset), uy * r + vy * (w + offset))
    outline = [at(INDEX_IN, -half_w), at(INDEX_OUT, -half_w), at(INDEX_OUT, half_w), at(INDEX_IN, half_w)]
    prism = extrude(make_face(Polyline(*outline, outline[0])), INDEX_H)
    top_edges = prism.edges().group_by(Axis.Z)[-1]
    return chamfer(top_edges, INDEX_CHAMFER)


def indices():
    parts = []
    for hour in range(1, 13):
        if hour == 6:
            continue
        if hour == 12:
            parts.append(baton(0, TWELVE_HALF_W, -TWELVE_OFFSET))
            parts.append(baton(0, TWELVE_HALF_W, TWELVE_OFFSET))
        else:
            parts.append(baton(hour * 30, INDEX_HALF_W, 0))
    out = parts[0]
    for p in parts[1:]:
        out = out + p
    return out


def polyhedron(faces):
    """A closed solid from planar polygon faces given as point lists."""
    shell = Shell([make_face(Polyline(*f, f[0])) for f in faces])
    solid = Solid(shell)
    if not solid.is_valid:
        raise SystemExit("polyhedron is not a valid solid")
    if solid.volume < 0:
        solid = Solid(Shell([make_face(Polyline(*reversed(f), f[-1])) for f in faces]))
    return solid


def dauphine(length, half_w, shoulder, tail, base, ridge):
    """A faceted kite, tip at +y (twelve), pivot at the origin. Two top facets
    meet at a ridge down the length; the ridge drops toward the tip because
    the facets converge before the point does."""
    z0 = base - 0.11
    tip_z = base + ridge * 0.25
    tip, lsh, rsh = (0, length), (-half_w, shoulder), (half_w, shoulder)
    ltl, rtl, ctl = (-0.34 * half_w, -tail), (0.34 * half_w, -tail), (0, -tail)
    P = lambda p, z: (p[0], p[1], z)
    faces = [
        # facets
        [P(tip, tip_z), P(lsh, base), P(ctl, base + ridge)],
        [P(lsh, base), P(ltl, base), P(ctl, base + ridge)],
        [P(tip, tip_z), P(ctl, base + ridge), P(rsh, base)],
        [P(rsh, base), P(ctl, base + ridge), P(rtl, base)],
        # walls
        [P(tip, z0), P(tip, tip_z), P(lsh, base), P(lsh, z0)],
        [P(lsh, z0), P(lsh, base), P(ltl, base), P(ltl, z0)],
        [P(ltl, z0), P(ltl, base), P(ctl, base + ridge), P(rtl, base), P(rtl, z0)],
        [P(rtl, z0), P(rtl, base), P(rsh, base), P(rsh, z0)],
        [P(rsh, z0), P(rsh, base), P(tip, tip_z), P(tip, z0)],
        # underside
        [P(tip, z0), P(rsh, z0), P(rtl, z0), P(ltl, z0), P(lsh, z0)],
    ]
    return polyhedron(faces)


def hour_hand():
    h = HOUR
    hand = dauphine(**h)
    # The hour hand's collar: a TUBE on the OM10's hour wheel, through the
    # dial, bored to clear the cannon pinion that passes up its middle. It
    # was a solid rod once and the assembly check found the pinion inside it.
    # Bored to clear the MINUTE hand's collar, which runs up its middle on
    # the cannon pinion; the assembly check found the two collars sharing
    # the same space until the bore was widened past the inner one.
    top = h["base"] + h["ridge"]
    tube = Cylinder(HOUR_COLLAR_R, top - HOUR_WHEEL_TOP, align=(None, None, None)).moved(Location((0, 0, HOUR_WHEEL_TOP)))
    bore = Cylinder(MINUTE_COLLAR_R + 0.05, top - HOUR_WHEEL_TOP + 0.2, align=(None, None, None)).moved(Location((0, 0, HOUR_WHEEL_TOP - 0.1)))
    return (hand + tube) - bore


def minute_hand():
    m = MINUTE
    hand = dauphine(**m)
    # The minute hand's collar: pressed over the OM10's cannon pinion's
    # pipe, so a tube bored to the pipe, reaching down over its top.
    top = m["base"] + m["ridge"]
    tube = Cylinder(MINUTE_COLLAR_R, top - (CANNON_PINION_TOP - 0.3), align=(None, None, None)).moved(Location((0, 0, CANNON_PINION_TOP - 0.3)))
    # Bored right through now: the sweep arbor and the seconds hand's pipe
    # pass up the middle. It was blind by 0.15 while nothing did.
    bore = Cylinder(CANNON_PIPE_R + 0.01, top + 0.2 - (CANNON_PINION_TOP - 0.4), align=(None, None, None)).moved(Location((0, 0, CANNON_PINION_TOP - 0.4)))
    return (hand + tube) - bore


# ---- the small seconds, inside the heart
# The OM10 is a small-seconds calibre: its fourth wheel's pinion comes up at
# nine and stops 1.9 mm under the dial, where a plain dial would carry a
# sunk sub-dial. The open heart takes that ground, so the seconds get what
# an open-heart watch with a small seconds gives them: a chapter ring
# floating over the movement on two posts screwed to the plate, its track
# engraved and ink-filled, and a blued hand on the pinion reading against
# it. Everything below is a solid that could be made; the ring's outer edge
# stops 0.19 mm short of the rehaut's well wall, which is what sets its
# size (the arbor sits 7.46 mm from the aperture's centre, the wall at 10.2).
SECONDS_RING_R_OUT = 4.25                # 0.35 inside the bulge's wall
SECONDS_RING_R_IN = 3.2
SECONDS_RING_TOP = -1.15                 # world z of the ring's face; the hand rides above
SECONDS_RING_T = 0.25
SECONDS_POST_R = 0.35
SECONDS_POST_AT = 3.6                    # the posts' radius from the arbor, at the ring's twelve and six: on
                                         # the plate's bar, which runs through the seconds arbor that way
SECONDS_FLOOR_Z = 1.85 + MOVEMENT_Z      # the bar's face: gltf_export.BAR_TOP_Y
TRACK_DEPTH = 0.06


def _track_grooves():
    """The sixty grooves of the seconds track, as solids about the arbor: a
    short fine one a second, a longer wider one every five."""
    grooves = None
    for i in range(60):
        five = i % 5 == 0
        w = 0.10 if five else 0.05
        r0, r1 = (3.28, 4.15) if five else (3.42, 4.02)
        box = extrude(make_face(Polyline((-w / 2, r0), (w / 2, r0), (w / 2, r1), (-w / 2, r1), (-w / 2, r0))), TRACK_DEPTH + 0.02)
        box = box.moved(Location((0, 0, SECONDS_RING_TOP - TRACK_DEPTH), (0, 0, -i * 6.0)))
        grooves = box if grooves is None else grooves + box
    return grooves


def _post_holes():
    holes = None
    for sy in (SECONDS_POST_AT, -SECONDS_POST_AT):
        h = Cylinder(SECONDS_POST_R + 0.02, SECONDS_RING_T + 0.2, align=(None, None, None)).moved(Location((0, sy, SECONDS_RING_TOP - SECONDS_RING_T - 0.1)))
        holes = h if holes is None else holes + h
    return holes


def seconds_ring():
    """The chapter ring: a white-lacquered annulus with the track cut into
    its face and two holes for the posts."""
    ring = extrude(Circle(SECONDS_RING_R_OUT) - Circle(SECONDS_RING_R_IN), SECONDS_RING_T).moved(Location((0, 0, SECONDS_RING_TOP - SECONDS_RING_T)))
    ring = ring - _track_grooves() - _post_holes()
    return ring.moved(Location(SECONDS_ARBOR))


def seconds_track():
    """The ink in the grooves: the same grooves, kept to the ring's volume,
    as their own solid so they can be black where the ring is white."""
    ring = extrude(Circle(SECONDS_RING_R_OUT) - Circle(SECONDS_RING_R_IN), SECONDS_RING_T).moved(Location((0, 0, SECONDS_RING_TOP - SECONDS_RING_T)))
    ink = (_track_grooves() & ring) - _post_holes()     # the grooves at three and nine stop at the post holes, as the ring's do
    return ink.moved(Location(SECONDS_ARBOR))


def seconds_post(sign):
    """A post from the plate's face in the window up through the ring, and
    the screw head that holds the ring down: one turned part with a slotted
    head, at the ring's twelve (sign +1) or six (sign -1)."""
    y = sign * SECONDS_POST_AT
    post = Cylinder(SECONDS_POST_R, SECONDS_RING_TOP - SECONDS_FLOOR_Z, align=(None, None, None)).moved(Location((0, y, SECONDS_FLOOR_Z)))
    head = Cylinder(0.50, 0.12, align=(None, None, None)).moved(Location((0, y, SECONDS_RING_TOP)))
    slot = extrude(make_face(Polyline((-0.6, -0.06), (0.6, -0.06), (0.6, 0.06), (-0.6, 0.06), (-0.6, -0.06))), 0.1).moved(Location((0, y, SECONDS_RING_TOP + 0.07)))
    return (post + head - slot).moved(Location(SECONDS_ARBOR))


def small_seconds_hand():
    """RETIRED with the centre-seconds conversion, kept with the fixture.
    A blued needle with a counterweight, riding 0.2 mm over the ring's
    face on a collar pressed onto the pinion's extended pivot."""
    # Bolder than a blued sliver: the well is dark and the wall is far.
    length, tail, w, z_lo, z_hi = 4.0, 1.25, 0.13, SECONDS_RING_TOP + 0.20, SECONDS_RING_TOP + 0.32
    outline = [(-0.03, length), (0.03, length), (w, 0.6), (w, -tail), (-w, -tail), (-w, 0.6)]
    needle = extrude(make_face(Polyline(*outline, outline[0])), z_hi - z_lo).moved(Location((0, 0, z_lo)))
    weight = extrude(Circle(0.42) - Circle(0.16), z_hi - z_lo).moved(Location((0, -tail - 0.1, z_lo)))
    collar = Cylinder(0.42, z_hi - (SECONDS_RING_TOP - 0.55), align=(None, None, None)).moved(Location((0, 0, SECONDS_RING_TOP - 0.55)))
    pivot = Cylinder(0.24, z_hi - SECONDS_PINION_TOP, align=(None, None, None)).moved(Location((0, 0, SECONDS_PINION_TOP)))
    return (needle + weight + collar + pivot).moved(Location(SECONDS_ARBOR))


def cap():
    """The minute hand's boss cover: a low ring now, under the sweep hand,
    with the arbor through its middle. It was a dome to the crystal when
    nothing passed through it."""
    r = CAP_R * 0.85
    base = MINUTE["base"] + MINUTE["ridge"]
    top = SWEEP["base"] - 0.06
    pts = [(0.37, base), (r, base), (r, top - 0.03), (r - 0.03, top), (0.37, top)]   # the hand's pipe (r 0.32) passes through
    return revolve(profile(pts), Axis.Z)


def seconds_hand():
    """The centre seconds: a long thin polished needle with a counterweight,
    on a pipe pressed over the sweep arbor's top, riding above the minute
    hand and under the crystal."""
    s = SWEEP
    z_lo, z_hi = s["base"], s["base"] + s["thick"]
    w = s["half_w"]
    outline = [(-0.025, s["length"]), (0.025, s["length"]), (w, 1.5), (w, -s["tail"]), (-w, -s["tail"]), (-w, 1.5)]
    needle = extrude(make_face(Polyline(*outline, outline[0])), z_hi - z_lo).moved(Location((0, 0, z_lo)))
    weight = extrude(Circle(0.55) - Circle(0.22), z_hi - z_lo).moved(Location((0, -s["tail"] - 0.15, z_lo)))
    pipe = Cylinder(0.32, 1.60 - (z_lo - 0.18), align=(None, None, None)).moved(Location((0, 0, z_lo - 0.18)))
    bore = Cylinder(SWEEP_ARBOR_R + 0.005, 1.55 - (z_lo - 0.3), align=(None, None, None)).moved(Location((0, 0, z_lo - 0.3)))
    return (needle + weight + pipe) - bore


def crown():
    """The crown, at three o'clock where the OM10's own stem comes out of
    the case band. The stem is the OM10's; this is only the crown on its end,
    with a short stub reaching in to meet it. Sixteen flutes cut round it so
    it catches light."""
    z = STEM_Z
    stem = Cylinder(0.45, 1.6, align=(None, None, None)).moved(Location((0, 0, 2.4)))
    body = Cylinder(1.65, 1.7, align=(None, None, None)).moved(Location((0, 0, 3.4)))
    body = chamfer(body.edges().group_by(Axis.Z)[-1], 0.25)
    for k in range(16):
        a = math.radians(k * 360 / 16)
        flute = Cylinder(0.22, 1.9, align=(None, None, None)).moved(Location((1.65 * math.cos(a), 1.65 * math.sin(a), 3.3)))
        body = body - flute
    part = stem + body
    # Built along +Z; lay it along +X at the rim.
    return part.moved(Location((CASE_R - 1.9, 0, z), (0, 90, 0)))


def main():
    parts = [
        ("case", case(), STEEL),
        ("caseback", caseback(), STEEL),
        ("crystal", crystal(), GLASS),
        ("dial", dial(), DIAL),
        ("rehaut", rehaut(), STEEL),
        ("indices", indices(), STEEL),
        ("hour_hand", hour_hand(), STEEL),
        ("minute_hand", minute_hand(), STEEL),
        ("seconds_hand", seconds_hand(), STEEL),
        ("cap", cap(), STEEL),
        ("crown", crown(), STEEL),
    ]
    glb_parts = []
    for name, solid, mat in parts:
        if not solid.is_valid:
            raise SystemExit(f"{name} is not a valid solid")
        solid.label = name
        got = G.tessellate_shape(solid.wrapped, 0.004, 0.10)
        if got is None:
            raise SystemExit(f"{name} has no triangles")
        verts, norms, faces = got
        verts, norms = G.zup_to_yup(verts, norms)
        glb_parts.append((name, verts, norms, faces, mat))
        print("  %-13s volume %8.2f mm3  %6d tris  z %+.2f..%+.2f" % (
            name, solid.volume, len(faces), solid.bounding_box().min.Z, solid.bounding_box().max.Z))

    out_glb = os.path.join(ROOT, "Assets", "case.glb")
    G.write_glb(glb_parts, out_glb)
    print("  wrote", out_glb, "(%.2f MB)" % (os.path.getsize(out_glb) / 1048576))

    out_step = os.path.join(ROOT, "models", "step", "case.step")
    export_step(Compound(children=[p[1] for p in parts]), out_step)
    print("  wrote", out_step)


if __name__ == "__main__":
    main()
