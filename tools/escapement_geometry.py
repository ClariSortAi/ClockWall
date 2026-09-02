"""Generates the escapement profiles for Controls/OpenworkedFace.xaml.

WHY THIS EXISTS, AND WHY IT USES A GEOMETRY KERNEL. The parts in that aperture
are drawings of real components. Hand-tracing their outlines as closed polygons
produced a wagon wheel and a saw blade, and it produced them twice, because
tracing an outline is the wrong operation: these parts are made by SUBTRACTION.
An escape wheel is a disc with fifteen teeth grown on it and four crossings cut
out of it. A balance is a ring with a bar across it. Say that to a boolean
kernel and the holes, the winding order and the self-intersections all come out
right; say it as a list of points and every point is a chance to be wrong.

Two proportions carry most of the realism, and both were out by more than 3x in
the hand-traced version:
  * an escape wheel tooth stands about 11% of the wheel radius proud, not 50%
  * a balance is a RING with two arms, not a spoked disc, and it needs its
    hairspring - without which it is an anonymous circle

    python tools/escapement_geometry.py          # render previews, then LOOK
    python tools/escapement_geometry.py --emit   # XAML path data

Face space throughout: 640x640, centre (320,320), degrees clockwise from twelve,
screen y (down is positive, as in XAML).
"""

import json
import math
import os
import sys

import om10_layout as _om10
from shapely import affinity
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ------------------------------------------------------------------ placement
#
# EVERY PLACEMENT IS DERIVED FROM THE APERTURE, never written out. The opening
# was enlarged once already and hand-editing six coordinate pairs to match it is
# exactly the kind of arithmetic that silently leaves one part behind. Move the
# aperture and the movement follows it.
#
# The opening grew from r=90 to r=126 for a reason that is not aesthetic. This
# view is orthographic and straight down, so nothing here has a visible SIDE -
# every depth cue is an interior wall, a chamfer or a contact shadow, and all
# three are features a few units wide. At r=90 they were landing on one pixel
# and the parts rendered as flat stickers. Pixels are the raw material.
APERTURE = (320.0, 450.0, 126.0)   # cx, cy, r

# Offsets are fractions of the aperture radius, so the layout is a shape rather
# than a list of numbers. The balance is the hero and gets the room; the escape
# wheel is set clear of it by more than the width of the fork between them.
_AX, _AY, _AR = APERTURE

# HOW MUCH OF THE WINDOW THE MOVEMENT IS ALLOWED TO FILL, and it is the one
# number that decides whether this reads as calm or as crowded.
#
# It used to be all of it. The balance came within 18 units of the rim, the
# escape wheel within 4, and the train wheel ran straight off the edge and had
# to be clipped - three wheels packed corner to corner in an opening with no
# quiet anywhere in it. Every reference on open-heart design says the opposite:
# the balance never fills its aperture, and most of what you see through the
# window is meant to be still. Margin is not wasted space, it is the thing that
# lets one moving part be the subject instead of five competing.
#
# Applied to the whole assembly at once, so every mechanical relation settled so
# far - the pallet spread, the train mesh, the fork's reach - is preserved
# exactly. This scales the drawing, it does not re-lay it out.
MOVEMENT_FILL = 0.85
_MR = _AR * MOVEMENT_FILL


def _at(fx, fy, fr=None):
    """A placement given as fractions of the aperture: centre, then radius."""
    p = (_AX + fx * _MR, _AY + fy * _MR)
    return p if fr is None else (p[0], p[1], fr * _MR)


BALANCE = _at(-0.222, 0.133, 0.600)   # cx, cy, rim outer radius

# EVERYTHING BELOW THE BALANCE IS NOW MEASURED, NOT CHOSEN.
#
# The escapement is openmovement.org's OM10 - a real Swiss movement - placed by
# one similarity transform in om10_layout. So the escape wheel's radius, its
# distance from the balance, where the pallet staff sits between them and where
# the fourth wheel meshes are all the real movement's numbers, scaled. They are
# no longer fractions somebody picked and then defended.
#
# Two things stay ours, because they are framing rather than mechanism: where
# the balance sits in the window (above) and which way the movement runs from it
# (ESCAPE_BEARING). That bearing is the one the old layout already had, so the
# composition is preserved while the mechanics underneath it are replaced.
ESCAPE_BEARING = 51.53                # degrees clockwise from twelve

_PLACE = _om10.make((BALANCE[0], BALANCE[1]), BALANCE[2], ESCAPE_BEARING)
SCALE = _PLACE.SCALE                  # face units per real millimetre

ESCAPE = _PLACE.axis_face("escape") + (_om10.OM10_MM["escape_r"] * SCALE,)
# THE LINE OF CENTRES, no longer argued for - just inherited.
#
# In a Swiss club-tooth lever escapement the escape arbor, the pallet arbor and
# the balance staff lie on ONE STRAIGHT LINE; the BHI course text names it "the
# line of centres". This drawing had it 22 degrees bent, which is not a rounding
# error but a different escapement, and then had it straight with the staff at a
# fraction of 0.591 reverse-engineered from where the stones happened to mesh.
#
# The OM10 answers it outright: 0.5006. The staff sits at the midpoint, and it
# does so because the two arms of a pallet lever are the same length. Taking the
# fraction from the real movement removes the last hand-fitted number from the
# escapement's geometry.
PALLET_FRACTION = _om10.PALLET_FRACTION
STAFF = _PLACE.axis_face("pallet")

# COUNTED OFF THE REAL WHEELS, not chosen to look busy. tools/om10_check.py
# recovers each count from the outline's dominant angular period, which for a
# toothed wheel is unambiguous. The previous figures - 15 teeth, 7 leaves, 64 -
# were invented, and they set the beat and every rotation rate downstream.
ESCAPE_TEETH = _om10.ESCAPE_TEETH                     # 20
ESCAPE_PINION_LEAVES = _om10.ESCAPE_PINION_LEAVES     # 8
TRAIN_TEETH = _om10.FOURTH_TEETH                      # 84
EPINION_R = ESCAPE[2] * 0.40

# The fourth wheel, in mesh with the escape pinion because that is where the
# OM10 has it - no longer a bearing and a derived centre distance, just the
# real position carried through the same transform as everything else.
TRAIN = _PLACE.axis_face("fourth") + (_om10.OM10_MM["fourth_r"] * SCALE,)

# 84 teeth driving 8 leaves: the escape wheel turns 10.5 times for every turn of
# the fourth wheel, and OpenworkedFace reads that straight off this constant.
TRAIN_RATIO = TRAIN_TEETH / ESCAPE_PINION_LEAVES

# THE BEAT, and it must match Services/Caliber.cs - which is the authority for
# the running app, while this is the authority for everything rendered offline.
# Two languages cannot share a constant, so they share a derivation instead:
# both compute the rate from the same measured tooth counts.
#
#     the fourth wheel carries the seconds, so it turns once a minute
#     escape turns per hour = 60 * TRAIN_TEETH / ESCAPE_PINION_LEAVES = 630
#     VPH = 2 * ESCAPE_TEETH * 630                                    = 25200
#
# smear.py used to restate VPH and ESCAPE_TEETH as its own literals, and when
# the tooth counts became real it went on computing blur for a 15-tooth wheel
# beating at 28,800. Nothing errored; the smears were simply for a different
# watch. They are read from profiles.json now.
VPH = int(2 * ESCAPE_TEETH * 60 * TRAIN_TEETH / ESCAPE_PINION_LEAVES)
BALANCE_AMPLITUDE = 285.0

# The hole the balance bridge is screwed down through, in the OM10's own plane.
# Read out of the OM10 cock's projected outline, and it lands exactly on
# OM00-00106 #9 in the assembly.
#
# There were two. The other, at (-10.09, -5.80), places at face (259.9, 570.4),
# which is 134.6 units from the aperture centre against an aperture radius of
# 126 - so it was always behind the dial and never once rendered. Keeping it
# only forced the bridge over the balance to be wide enough to reach two feet.
# See models/step/movement.step.py's _balance_bridge.
COCK_SCREWS = [(-13.67, -0.98)]

# The parts that are not circles - the lever, the cock, the jewel settings - are
# drawn from absolute dimensions rather than fractions, because a lever is a
# shape and not a proportion. U rescales all of them together when the aperture
# changes, so nothing gets left at its old size. It is 1.0 at the r=90 opening
# these dimensions were originally drawn against.
U = _MR / 90.0

# THE ROLLER, WHICH IS THE PART THAT MAKES THIS AN ESCAPEMENT AT ALL.
#
# A lever escapement does exactly one thing: a jewelled pin on the balance staff
# enters the slot in the fork, unlocks it, takes an impulse and leaves. That pin
# is the entire mechanical connection between the balance and the rest of the
# watch. Without it the two halves are unrelated mechanisms bolted to the same
# plate - which is what this drawing was. The fork had a slot cut in it, the
# balance had a plain hub, and between the horns and the hub sat fifteen units
# of nothing.
#
# The size is not invented. The fork was already drawn long enough to reach
# within 14.6 units of the balance axis, and a pin orbiting at that radius is
# 0.23 of the balance radius, implying a roller table about 0.15 of the balance
# DIAMETER - which is what a real one is. So the drawing had always implied a
# roller of the right size; nobody had drawn it. FORK_LENGTH is now derived from
# the pin's orbit rather than left as a number that happened to work, so the two
# cannot drift apart again.
# Proportions from Headrick's worked construction, which gives a complete
# trig-checked lever-and-double-roller: impulse roller radius 0.479 of the
# pallet-to-balance span, and a safety roller 58% of that. Cross-checked against
# the independent estimate that a roller table is about a fifth of the balance
# DIAMETER - 0.44 of the radius is 0.22 of the diameter, so the two agree.
#
# The first attempt at this back-derived the roller from wherever the fork
# happened to end, which got a table barely half the size it should be. Deriving
# it the other way round - real roller, then a fork long enough to reach the
# jewel's orbit - is what a watchmaker does, and it means the fork length is now
# a consequence rather than a number that happened to look right.
ROLLER_R = 0.44             # impulse roller radius, as a fraction of balance R
SAFETY_R = 0.58 * ROLLER_R  # the safety roller under it
IMPULSE_ORBIT = 0.37        # the jewel, set near the impulse roller's rim
IMPULSE_R = 0.052           # the jewel itself

_D_BALANCE = math.hypot(BALANCE[0] - STAFF[0], BALANCE[1] - STAFF[1])
FORK_LENGTH = (_D_BALANCE - IMPULSE_ORBIT * BALANCE[2]) / U


# HOW FAR APART THE TWO PALLET STONES SIT, and it is not a free parameter.
#
# The wheel advances exactly HALF a tooth-space per beat - that is what two
# beats per tooth means. So for the second stone to meet a tooth after the
# first one lets go, the separation between them has to be an ODD number of
# half-spaces: 12, 36, 60, 84 degrees on a fifteen-tooth wheel and nothing in
# between. At anything else the wheel arrives with a tooth tip pointing at the
# gap between the stones and the escapement simply cannot alternate.
#
# It was 42 degrees - three and a half half-spaces, so a tooth landed halfway
# every time. Nothing about that is visible in a still frame, because a still
# frame of a lever mid-beat looks like a lever mid-beat. It is only visible in
# MOTION, as a fork that keeps missing a wheel it is supposedly driven by.
#
# Five half-spaces - two and a half tooth-spaces - is the ordinary Swiss lever
# figure, and the one that leaves room for the fork to pass under the wheel.
# Where the wheel sits at rest, relative to the stones.
#
# Free, in the sense that a stopped watch stopped wherever it stopped - but not
# arbitrary, because the drawing has to show a tooth actually LOCKED on a stone
# with the other stone clear. Moving the pallet staff onto the line of centres
# rotated the stone pair against the tooth pattern and left both stones fouling
# teeth at once, which is a jammed escapement rather than a locked one.
#
# Solved rather than eyeballed: swept in quarter degrees for the phase that
# maximises the locking stone's engagement while driving the other stone's to
# zero. It finds 11.75, and there the locked stone overlaps by 21.3 units and
# the free one by nothing at all - the drop clearance a real escapement has.
ESCAPE_PHASE = 11.75

# Where the hairspring's coil STARTS, chosen so that where it ENDS is somewhere
# it can be held.
#
# A hairspring's outer end is pinned to a stud carried on the cock. That fixed
# end is the whole reason the spring can do anything: the inner end turns with
# the staff, the outer end does not, and the coil between them winds and unwinds.
# A spiral with both ends free is a decorative spring and controls nothing.
#
# This one ended 20 units clear of the cock, anchored to nothing at all. Since
# the wind is 6.5 turns, the outer end lands wherever the inner end started plus
# half a turn - so the start angle is free, and solving it for "outer end lands
# under the cock" costs nothing and fixes the part. 284 degrees puts it there.
SPRING_PHASE = 284.0

# MEASURED OFF THE OM10, and it settles an argument this file already had.
#
# The reasoning above is right: the separation has to be an ODD number of half
# tooth-spaces or the wheel arrives with a tooth pointing at the gap between the
# stones and the escapement cannot alternate. The number chosen to satisfy it
# was 5. The real movement uses 7.
#
# Taken from the placed solids: the two stones bear 202.0 and 264.1 degrees from
# the escape arbor, 62.08 degrees apart, which on a 20-tooth wheel (9 degree
# half-spaces) is 6.90 of them. That is 7 within the tessellation error, and 7
# is odd, so the rule holds and the count was simply low.
#
# Both stones reach 0.16 mm inside the tooth-tip circle, and the two agree to
# two thousandths of a millimetre. Equal lock on entry and exit is what a
# correctly set escapement has, and it is not something a drawing gets by luck.
PALLET_HALF_SPACES = 7
_TOOTH_PITCH = 360.0 / ESCAPE_TEETH
PALLET_SPREAD = PALLET_HALF_SPACES * _TOOTH_PITCH / 4.0
assert PALLET_HALF_SPACES % 2 == 1, "an even count cannot alternate"



def polar(cx, cy, deg, r):
    """A point `deg` clockwise from twelve at radius `r`. Screen coordinates,
    so twelve is up and up is negative y."""
    a = math.radians(deg)
    return (cx + r * math.sin(a), cy - r * math.cos(a))


def disc(cx, cy, r, steps=180):
    return Polygon([polar(cx, cy, i * 360.0 / steps, r) for i in range(steps)])


def ring_sector(cx, cy, a0, a1, r_in, r_out, steps=24):
    """An annular sector - the shape of a crossing cutter and of an inertia
    block both."""
    pts = [polar(cx, cy, a0 + (a1 - a0) * i / steps, r_out) for i in range(steps + 1)]
    pts += [polar(cx, cy, a1 + (a0 - a1) * i / steps, r_in) for i in range(steps + 1)]
    return Polygon(pts)


def heading(frm, to):
    """Degrees clockwise from twelve, pointing from one place to another."""
    return math.degrees(math.atan2(to[0] - frm[0], frm[1] - to[1])) % 360.0


# --------------------------------------------------------------- escape wheel

# One club tooth, as (degrees ahead of the tooth's base angle, radius as a
# fraction of the tip radius). Read it in the direction of travel - the wheel
# turns clockwise, so angle increases the way the wheel moves.
#
#   * a thin NECK rises off the rim, leaning forward into the direction of
#     travel. Leaning is not stylistic; it is what makes the tooth able to hand
#     its energy sideways to a pallet instead of just shoving it outward.
#   * the CLUB is the little head on top. Its outer edge, flat and out at full
#     radius, is the IMPULSE PLANE - the surface that actually does the work.
#   * a short, steep LOCKING FACE drops off the leading side. This is what a
#     tooth rests against for the 100-odd milliseconds between beats.
#   * everything from there to the next tooth is open GULLET. Escape wheel
#     gullets are wide. That openness, more than the teeth, is what stops the
#     wheel reading as a saw blade.
#
# The profile dips below the root circle at both ends so the tooth unions
# cleanly onto the rim disc with no hairline seam.
CLUB_TOOTH = [
    (-9.0, 0.868),
    (-7.0, 0.915),
    (-3.2, 0.968),
    (-1.6, 1.000),   # club heel
    (1.9, 1.000),    # club tip; the edge back to the heel is the impulse plane
    (2.3, 0.958),    # locking corner
    (0.9, 0.950),    # undercut beneath the club
    (0.2, 0.912),
    (-0.4, 0.868),
]


def escape_wheel(cx, cy, R, teeth=ESCAPE_TEETH, phase=0.0, root=0.885,
                 hub=0.17, rim_inner=0.74, crossings=4, spoke_half_deg=7.5):
    """A Swiss club-tooth escape wheel: rim disc, plus teeth, minus crossings."""
    body = disc(cx, cy, R * root)

    tooth_shapes = []
    for i in range(teeth):
        base = i * 360.0 / teeth + phase
        tooth_shapes.append(Polygon(
            [polar(cx, cy, base + da, R * fr) for da, fr in CLUB_TOOTH]))

    wheel = unary_union([body] + tooth_shapes)

    # Crossings: cut the sectors away and the spokes are what is left, which is
    # how they are actually machined - you do not add a spoke, you remove
    # everything that is not one.
    step = 360.0 / crossings
    cutters = [ring_sector(cx, cy,
                           i * step + spoke_half_deg,
                           (i + 1) * step - spoke_half_deg,
                           R * hub, R * rim_inner)
               for i in range(crossings)]
    return wheel.difference(unary_union(cutters))


# -------------------------------------------------------------- balance wheel

def balance(cx, cy, R, band=0.135, arm=0.062, hub=0.17,
            blocks=4, block_deg=10.0, block_out=1.02, block_in=0.855):
    """
    A modern free-sprung balance: an annular rim, ONE bar straight through the
    centre (so, two arms), a hub, and four inertia blocks set in the rim.

    The first two attempts drew six spokes and six dots and got a bicycle wheel.
    A balance is not a gear. It carries no teeth, it is deliberately the
    heaviest thing in the movement for its size, and nearly all of that mass is
    parked out at the rim where it does the most good. Two arms and four
    adjusters is what that intent looks like.
    """
    rim = disc(cx, cy, R).difference(disc(cx, cy, R * (1 - band)))

    # The bar swells slightly where it meets the rim, the way a real arm is
    # filleted in: a parallel bar butting against a ring reads as two parts
    # stuck together rather than one turned from a single blank.
    w, wf = R * arm, R * arm * 1.9
    inner = R * (1 - band) + 0.5
    bar = Polygon([(cx - wf, cy - R), (cx - w, cy - R * 0.62),
                   (cx - w, cy + R * 0.62), (cx - wf, cy + R),
                   (cx + wf, cy + R), (cx + w, cy + R * 0.62),
                   (cx + w, cy - R * 0.62), (cx + wf, cy - R)])
    bar = bar.intersection(disc(cx, cy, inner))

    parts = [rim, bar, disc(cx, cy, R * hub)]
    for i in range(blocks):
        a = i * (360.0 / blocks) + 45.0
        parts.append(ring_sector(cx, cy, a - block_deg / 2, a + block_deg / 2,
                                 R * block_in, R * block_out, steps=10))
    return unary_union(parts)


def roller_table(cx, cy, R, to_fork):
    """The double roller: the impulse table that carries the jewel, and the
    smaller safety roller under it with the crescent the fork's guard pin rides
    in. Two concentric circles and a notch is exactly what it looks like from
    above, and the notch is the detail that says which one is which."""
    table = disc(cx, cy, R * ROLLER_R, 64)
    safety = disc(cx, cy, R * SAFETY_R, 48)
    # The crescent, cut on the side facing the lever - it can only be passed
    # when the impulse pin is in the slot, which is the whole point of it.
    notch = disc(*polar(cx, cy, to_fork, R * SAFETY_R * 1.06), R * SAFETY_R * 0.62)
    return unary_union([table, safety.difference(notch)])


def impulse_pin(cx, cy, R, to_fork):
    """The jewel, pointing at the fork.

    Drawn AT the fork because the whole assembly is drawn at rest, and rest is
    the centre of the swing - which is the exact instant the pin is inside the
    slot unlocking the lever. So this is not a placement choice, it is a
    consequence of when the drawing is taken, and it doubles as a check: if the
    pin does not land between the horns at angle zero, the layout is wrong.
    """
    px, py = polar(cx, cy, to_fork, R * IMPULSE_ORBIT)
    return disc(px, py, R * IMPULSE_R, 24)


def hairspring(cx, cy, R, r0=0.17, r1=0.56, coils=6.5, steps=560, phase=0.0):
    """
    The balance spring: a flat Archimedean spiral.

    Its absence was most of why the balance read as a gear. A balance wheel on
    its own is a ring; the spring coiled beneath it is what says oscillator, and
    it is the most recognisable object in a movement.

    Returned as an open curve to be STROKED, not as a filled ribbon. Buffering
    it into a shape doubled the point count for a part one pixel wide - 40KB of
    path data to draw a hairline.
    """
    return LineString([polar(cx, cy, phase + (i / steps) * coils * 360.0,
                             R * (r0 + (r1 - r0) * i / steps))
                       for i in range(steps + 1)])


# ---------------------------------------------------------------- pallet fork

def pallet_fork(sx, sy, to_escape, to_balance, length=40.0, reach=None,
                half=None, pin=2.0):
    """
    The lever. Built along the +x axis in its own frame and then swung into
    place, because a lever is a straight thing and reasoning about it in face
    coordinates is how the last attempt ended up as a paper dart.

    +x runs toward the balance (the long arm), -x toward the escape wheel (the
    short pallet end). The FORK itself - two horns with a slot between them - is
    the point of the part: the balance's impulse jewel passes through that slot
    once a beat, and it is the single detail that separates a lever from a
    stick. It is cut, not drawn, for the same reason as everything else here.
    """
    L = length

    # The neck: the long slender run from the staff out to the fork. This is
    # most of the part and it is THIN - a lever is a few tenths of a millimetre
    # of steel doing nothing but carrying an impulse from one end to the other.
    neck = Polygon([
        (-6, -4.5),
        (L - 15, -2.1), (L - 4, -6.2), (L, -6.6),   # out to the first horn
        (L, 6.6), (L - 4, 6.2), (L - 15, 2.1),      # across the tip to the second
        (-6, 4.5),
    ])

    # The pallet head: a wedge with a V taken out of the middle, which leaves
    # TWO ARMS. That is the part the last pass got wrong - it drew the wedge and
    # stopped, and a solid paddle is not a pallet. The arms have to be separate
    # because each carries its own stone and each has to be adjusted alone.
    head = Polygon([(-4, -4.0), (-18, -9.2), (-20, -6.0),
                    (-20, 6.0), (-18, 9.2), (-4, 4.0)])
    vee = Polygon([(-7, 0.0), (-23, -5.0), (-23, 5.0)])

    # ...and it has to REACH the stones, which are placed off the WHEEL and know
    # nothing about this drawing. Scaling the head to them keeps one number in
    # charge: widen PALLET_SPREAD and the arms follow instead of leaving two
    # jewels floating off the ends of a lever that no longer gets to them.
    if reach is not None:
        head = affinity.scale(head, reach / (18.0 * U), half / (9.2 * U), origin=(0, 0))
        vee = affinity.scale(vee, reach / (18.0 * U), half / (9.2 * U), origin=(0, 0))

    # The slot between the horns, cut in rather than drawn around. The balance's
    # impulse jewel passes through here once a beat; it is the one detail that
    # separates a lever from a stick - and it has to be WIDER THAN THE JEWEL,
    # which is not something the drawing could get right while no jewel existed.
    # It was 4 units across against a 6.7 unit pin, so the pin fouled the horns
    # instead of entering between them. Derived from the pin now, with the
    # clearance a real slot carries.
    # Depth from the pin too, not a fixed 11. A slot cut that deep with a jewel
    # this size ran back past the point where the neck narrows and sawed the
    # lever clean in half - it stopped being one part. Two pin-diameters deep is
    # enough to swallow the jewel and stays inside the flare of the horns.
    w = pin * 1.35
    slot = Polygon([(L - 2.0 * pin, -w), (L + 2, -w), (L + 2, w), (L - 2.0 * pin, w)])

    # The counterpoise: the stub that balances the lever on its staff. Real, and
    # it is what stops the silhouette reading as an arrow.
    tail = Polygon([(-7, -3.2), (5, -3.2), (5.6, -11.0), (-1.5, -11.8)])

    lever = unary_union([neck, head.difference(vee), tail]).difference(slot)

    # Drawn at the scale the aperture used to be, then grown. Scaling in the
    # lever's OWN frame - before the rotate and the translate - is what keeps
    # this a one-line change instead of thirty retuned coordinates.
    lever = affinity.scale(lever, U, U, origin=(0, 0))

    # Local +x points at the balance; rotate so it does in face space too.
    # shapely rotates counter-clockwise in maths convention, and face angles are
    # clockwise from twelve, so the conversion is (90 - heading).
    lever = affinity.rotate(lever, to_balance - 90.0, origin=(0, 0), use_radians=False)
    return affinity.translate(lever, sx, sy)


def pallet_stones(ex, ey, eR, sx, sy, spread=PALLET_SPREAD, w=3.2 * U, h=7.6 * U):
    """
    The two jewels, entry and exit, straddling the escape wheel two and a half
    tooth-spaces apart. Positioned off the WHEEL rather than off the fork,
    because that is what fixes them in a real movement - they have to sit where
    the teeth arrive, and where the teeth arrive is set by PALLET_SPREAD, which
    is arithmetic rather than taste.
    """
    mid = heading((ex, ey), (sx, sy))
    out = []
    for sign in (-1, 1):
        a = mid + sign * spread
        cx, cy = polar(ex, ey, a, eR * 0.99)
        t = math.radians(a)
        pts = []
        for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
            pts.append((cx + dx * math.cos(t) - dy * math.sin(t),
                        cy + dx * math.sin(t) + dy * math.cos(t)))
        out.append(Polygon(pts))
    return unary_union(out)


def _pallet_reach(ex, ey, eR, sx, sy):
    """How far from the staff a stone sits - the triangle staff/wheel/stone,
    solved rather than measured off the drawing."""
    d = math.hypot(ex - sx, ey - sy)
    r = eR * 0.99
    return math.sqrt(d * d + r * r - 2 * d * r * math.cos(math.radians(PALLET_SPREAD)))


# ------------------------------------------------------------------- assembly

def build():
    bx, by, bR = BALANCE
    ex, ey, eR = ESCAPE
    tx, ty, tR = TRAIN
    sx, sy = STAFF
    return {
        # --- the plate and what is under it -------------------------------
        # The floor is not decoration. The plate is drilled right through, and
        # a bore over nothing renders as a black disc; a bore over a floor
        # three units down renders as a bore.
        "floor": disc(_AX, _AY, _AR - 1.0, 320),
        "plate": mainplate(),

        # --- pinions: the depth cue that costs nothing ---------------------
        # Each sits below its wheel and turns with it, seen through the
        # crossings. One object plainly underneath another is the only depth
        # cue a straight-down camera cannot argue with.
        "epinion": pinion(ex, ey, eR * 0.40, leaves=7),
        "tpinion": pinion(tx, ty, tR * 0.26, leaves=8),

        # --- the going train ----------------------------------------------
        "train": crossed_wheel(tx, ty, tR, teeth=64),
        "tcollet": collet(tx, ty, tR * 0.15),

        # --- the escapement -----------------------------------------------
        "escape": escape_wheel(ex, ey, eR, phase=ESCAPE_PHASE),
        "ecollet": collet(ex, ey, eR * 0.19),
        "balance": balance(bx, by, bR),
        "roller": roller_table(bx, by, bR, heading((bx, by), (sx, sy))),
        "impulse": impulse_pin(bx, by, bR, heading((bx, by), (sx, sy))),
        "bscrews": balance_screws(bx, by, bR),
        "spring": hairspring(bx, by, bR, phase=SPRING_PHASE),
        "stud": stud(bx, by, bR, SPRING_PHASE),
        # The stones are placed off the WHEEL; the lever's arms are then sized
        # to reach them, rather than both being drawn to a remembered number.
        "fork": pallet_fork(sx, sy, heading((sx, sy), (ex, ey)),
                            heading((sx, sy), (bx, by)),
                            length=FORK_LENGTH,
                            pin=IMPULSE_R * bR / U,
                            reach=_pallet_reach(ex, ey, eR, sx, sy),
                            half=eR * 0.99 * math.sin(math.radians(PALLET_SPREAD))),
        "stones": pallet_stones(ex, ey, eR, sx, sy),
        "cock": balance_cock(bx, by, *APERTURE),
    }


# ------------------------------------------------------------------- emission

def rings(geom):
    """Every ring of a (Multi)Polygon, outers and holes alike. XAML fills them
    with EvenOdd, so a hole needs no special treatment - only to be present."""
    out = []
    polys = getattr(geom, "geoms", [geom])
    for p in polys:
        out.append(list(p.exterior.coords))
        out.extend(list(h.coords) for h in p.interiors)
    return out


# Circles arrive here sampled at a couple of pixels per segment, which is finer
# than a 640px dial can show and far finer than a XAML attribute wants to carry.
# A tenth of a pixel is well under one screen pixel at the size this renders.
SIMPLIFY = 0.1


def data(geom):
    """XAML path mini-language. Open geometries are stroked, so they are not
    closed with Z; everything else is a filled figure."""
    geom = geom.simplify(SIMPLIFY, preserve_topology=True)

    if geom.geom_type == "LineString":
        return "M" + " L".join("%.1f,%.1f" % (x, y) for x, y in geom.coords)

    return " ".join(
        "M" + " L".join("%.1f,%.1f" % (x, y) for x, y in r[:-1]) + " Z"
        for r in rings(geom))


# -------------------------------------------------------------------- preview

def preview(parts, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, PathPatch
    from matplotlib.path import Path as MplPath

    def patch(ax, geom, colour):
        verts, codes = [], []
        for r in rings(geom):
            verts += r
            codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(r) - 1)
        ax.add_patch(PathPatch(MplPath(verts, codes), facecolor=colour,
                               edgecolor="none", fill=True))

    fig, axes = plt.subplots(1, 3, figsize=(21, 7.6), dpi=120)
    fig.patch.set_facecolor("#13131a")

    # (title, xmin, xmax, ytop, ybottom) - y is screen-down, so the axis is
    # set inverted. Getting these wrong once already cost a whole render pass.
    views = [("assembly", 208, 432, 358, 584),
             ("escape wheel", 344, 408, 388, 456),
             ("fork + balance", 234, 402, 398, 548)]

    for ax, (title, xmin, xmax, ytop, ybot) in zip(axes, views):
        ax.set_facecolor("#13131a")
        ax.add_patch(Circle(APERTURE[:2], APERTURE[2], facecolor="#07070a",
                            edgecolor="#b9bdc6", lw=2.4, zorder=0))
        sp = parts["spring"]
        ax.plot([p[0] for p in sp.coords], [p[1] for p in sp.coords],
                color="#5d6270", lw=1.0, zorder=1)
        patch(ax, parts["escape"], "#767b88")
        patch(ax, parts["balance"], "#8b909d")
        patch(ax, parts["fork"], "#a3a9b5")
        patch(ax, parts["stones"], "#c4485c")
        ax.add_patch(Circle(BALANCE[:2], 4.5, facecolor="#c4485c"))
        ax.add_patch(Circle(ESCAPE[:2], 4.0, facecolor="#c4485c"))
        ax.add_patch(Circle(STAFF, 3.2, facecolor="#c4485c"))
        ax.set_xlim(xmin, xmax); ax.set_ylim(ybot, ytop)
        ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(title, color="#8b909d", fontsize=11)

    fig.tight_layout()
    fig.savefig(path, facecolor=fig.get_facecolor())
    print("wrote", path)


if __name__ == "__main__":
    parts = build()
    if "--emit" in sys.argv:
        for key in ("escape", "balance", "spring", "fork", "stones", "cock"):
            print("### " + key)
            print(data(parts[key]))
            print()
    else:
        preview(parts, "captures/geom/escapement.png")


# ----------------------------------------------------------------- balance cock

def stud(cx, cy, R, phase, coils=6.5):
    """The block on the cock that the hairspring's outer end is pinned into.

    Small, and it has to exist. Without it the spring has no fixed end and the
    balance has nothing to oscillate against - the difference between an
    oscillator and a curl of wire.
    """
    end = polar(cx, cy, phase + coils * 360.0, R * 0.56)
    return disc(end[0], end[1], R * 0.062, 24)


def balance_cock(bx, by, ax, ay, ar, anchor_deg=116.0,
                 boss=13.5 * U, foot=11.0 * U, screw=2.4 * U):
    """
    The bridge that carries the top pivot of the balance staff.

    It is here for two reasons and both are honest. It is what is actually
    there - the balance hangs from it, and a balance drawn without one is
    floating. And the aperture had a large empty quadrant on the far side of the
    wheel, which is exactly the space a cock occupies: it is anchored out at the
    edge of the plate and reaches in over the balance.

    Drawn OVER the wheel, because that is where it sits. The balance turns
    underneath it and is partly hidden by it, which is what you see through the
    back of any watch.
    """
    # Anchored on an EXPLICIT bearing, not simply opposite the balance: the
    # far side of the balance is where the escape wheel lives, and the first cut
    # ran the bridge straight across it. A cock is routed around the train, not
    # over it.
    anchor = polar(bx, by, anchor_deg, ar * 0.86)
    ang = anchor_deg

    # A tapering arm from the anchor in to a round boss over the staff.
    n = polar(0.0, 0.0, anchor_deg + 90.0, 1.0)
    mid = ((anchor[0] + bx) / 2.0, (anchor[1] + by) / 2.0)
    waist = foot * 0.68
    arm = Polygon([
        (anchor[0] + n[0] * foot, anchor[1] + n[1] * foot),
        (mid[0] + n[0] * waist, mid[1] + n[1] * waist),
        (bx + n[0] * boss * 0.5, by + n[1] * boss * 0.5),
        (bx - n[0] * boss * 0.5, by - n[1] * boss * 0.5),
        (mid[0] - n[0] * waist, mid[1] - n[1] * waist),
        (anchor[0] - n[0] * foot, anchor[1] - n[1] * foot),
    ])
    cock = unary_union([arm, disc(bx, by, boss, 72), disc(anchor[0], anchor[1], foot, 48)])
    # Waisted between the boss and the foot, then softened: a bridge is milled
    # from a block and every edge on it is chamfered, so nothing on its outline
    # is a sharp corner.
    cock = rounded(cock, 2.6 * U)

    # The two screws that hold it down, and the hole the staff runs in. Openings
    # in a bridge are most of what makes it read as a machined part rather than
    # a spatula.
    holes = [disc(bx, by, screw * 0.9, 32)]
    for s in (-1, 1):
        p = (anchor[0] + n[0] * foot * 0.52 * s, anchor[1] + n[1] * foot * 0.52 * s)
        holes.append(disc(p[0], p[1], screw, 32))
    return cock.difference(unary_union(holes))


# ------------------------------------------------------- corrections from life
# Everything below came from looking at photographs of real movements rather
# than from reasoning about them, after three attempts that reasoned. What the
# reference showed, in order of how wrong the guess had been:
#
#   1. The wheels are BRASS. Only the escape wheel, the lever and the springs
#      are steel. Gold wheels against a white plate is most of the picture, and
#      rendering the lot in silver threw away the movement's only colour.
#   2. Crossings are shaped, not cut. Their openings are rounded teardrops with
#      fillets into rim and hub - a straight-sided sector reads as a stamping.
#   3. Jewels sit in polished CHATONS: a ruby pressed into a steel collar,
#      countersunk. A bare red dot is not a jewel.
#   4. Screws are BLUED. Two spots of deep blue is the accent the whole plate
#      is arranged around.
#   5. The balance carries timing screws around the outside of its rim.

def rounded(geom, radius=1.8):
    """Rounds a shape's convex corners. Erode-then-dilate with round joins,
    which is the cheap way to get the fillets that make a machined part look
    turned rather than punched."""
    return geom.buffer(-radius, join_style=1).buffer(radius, join_style=1)


def crossed_wheel(cx, cy, R, teeth, root=0.93, tooth_deg=2.4,
                  hub=0.17, rim_inner=0.74, crossings=5, spoke_half_deg=6.0):
    """
    A going-train wheel: brass, many fine teeth, five shaped crossings.

    The teeth are the correction that matters. A train wheel carries sixty or
    eighty of them and they are SHALLOW and pointed - at a glance the rim reads
    as a serrated edge, not as a row of blocks. Fifteen chunky teeth is an
    escape wheel, and only an escape wheel.
    """
    body = disc(cx, cy, R * root, 240)
    pitch = 360.0 / teeth
    shapes = [body]
    for i in range(teeth):
        a = i * pitch
        shapes.append(Polygon([
            polar(cx, cy, a - tooth_deg, R * root * 0.99),
            polar(cx, cy, a - tooth_deg * 0.35, R),
            polar(cx, cy, a + tooth_deg * 0.35, R),
            polar(cx, cy, a + tooth_deg, R * root * 0.99),
        ]))
    wheel = unary_union(shapes)

    step = 360.0 / crossings
    cutters = [rounded(ring_sector(cx, cy, i * step + spoke_half_deg,
                                   (i + 1) * step - spoke_half_deg,
                                   R * hub, R * rim_inner, steps=32), R * 0.10)
               for i in range(crossings)]
    return wheel.difference(unary_union(cutters))


def collars(jewel_r):
    """
    The steel chatons, each one sized to the bore the OM10 actually drilled.

    A chaton is the setting a jewel is pressed into when the hole is wider than
    the stone, so the ring is exactly the gap between the two - and where the
    plate drilled the hole to the stone's own diameter there is NO chaton,
    because the stone goes straight into the plate. That is a real distinction
    and the measured bores make it for us: 11.06 units at the balance against a
    5.91-unit jewel is a setting, 5.77 at the escape and the pallet is an
    interference fit, 6.35 at the fourth wheel is a whisker of clearance.

    The radii used to be four multiples of U picked to look right, and they
    made four identical rings around four holes drilled to match them.
    """
    rings = []
    for _arbor, (cx, cy, bore_r, _d) in drilling()["bores"].items():
        # A ring thinner than this is under a pixel and a half on the wall, so
        # it is noise rather than a setting. The escape and pallet bores are
        # the stone's own diameter and the fourth's clears it by 0.44 units;
        # only the balance has a hole a chaton could actually be made for.
        if bore_r <= jewel_r + 1.0:
            continue                       # the stone IS the bearing here
        rings.append(disc(cx, cy, bore_r, 48).difference(
            disc(cx, cy, jewel_r, 40)))
    return unary_union(rings)


def balance_screws(cx, cy, R, count=8, r=1.9 * U):
    """Timing screws set around the outside of the balance rim. The reference
    shows them proud of the rim, evenly spaced - and they are what makes the
    swing readable, because a plain hoop turning about its own centre shows
    nothing at all."""
    return unary_union([disc(*polar(cx, cy, i * 360.0 / count + 22.5, R * 1.005),
                             r, 24) for i in range(count)])


# ------------------------------------------------------------------ real depth
#
# WHY THIS SECTION EXISTS. The camera is orthographic and points straight down,
# which means no part in this scene has a visible side. A flat top face under a
# distant lamp renders as ONE uniform tone - correctly, and forever. So the
# first three passes produced flat stickers not because the shader was wrong but
# because the model contained nothing that could shade.
#
# In a top-down view depth comes from exactly four places, and everything below
# is here to manufacture one of them:
#
#   1. INTERIOR WALLS. The inside of a bore, a jewel sink, the wall of the
#      balance rim. A vertical surface lit obliquely has a bright side and a
#      dark side, and that is the whole of the depth cue.
#   2. CHAMFERS wide enough to see. Handled in the render, not here.
#   3. TIGHT CONTACT SHADOWS - small and close, so a part sits ON the plate
#      rather than hovering above it. Also the render.
#   4. SOMETHING VISIBLY BELOW SOMETHING ELSE. A pinion seen through the
#      crossings of the wheel it drives. That is what the rest of this is.


def pinion(cx, cy, R, leaves=8, root=0.60, leaf=0.30, pitch=0.72):
    """
    The steel pinion a wheel is riveted to, sitting below it and turning with
    it. Seen through the wheel's crossings, and that glimpse is the single
    cheapest piece of real depth available here - it is one object plainly
    underneath another, which no amount of shading can fake.

    A watch pinion has FEW leaves and they are FAT and round-topped: six to
    twelve, cut to an epicycloidal profile that is almost circular at the tip.
    Approximating each leaf as a disc is close enough at this size and gets the
    important thing right, which is that a pinion looks like a flower and not
    like a small gear.
    """
    parts = [disc(cx, cy, R * root, 96)]
    for i in range(leaves):
        p = polar(cx, cy, i * 360.0 / leaves, R * pitch)
        parts.append(disc(p[0], p[1], R * leaf, 28))
    return unary_union(parts)


def collet(cx, cy, r):
    """The turned boss a wheel is riveted onto. A step at the centre of every
    wheel, and one more edge to catch a chamfer highlight."""
    return disc(cx, cy, r, 64)


def drilling():
    """
    The OM10 mainplate's own holes, in face coordinates.

    Written by tools/cad_parts.py, because reading them off the real solid
    needs trimesh and this module has to run under the system interpreter that
    render.ps1 uses. See `mainplate_drilling` there for the whole argument;
    the short version is that the plate and the parts are placed by the SAME
    similarity transform, so the bores arrive under the pivots rather than
    being aimed at them.
    """
    with open(os.path.join(_ROOT, "captures", "cad", "manifest.json")) as f:
        payload = json.load(f)
    if "mainplate" not in payload:
        raise SystemExit(
            "captures/cad/manifest.json has no mainplate drilling. Re-run\n"
            "    .venv-cad\\Scripts\\python.exe tools/cad_parts.py")
    return payload["mainplate"]


def plate_openings():
    """
    Every hole in the mainplate, as one shape to subtract.

    This is the most valuable geometry in the file. A hole is an interior wall,
    an interior wall is the only thing in a straight-down view that can shade,
    and there was previously not one hole anywhere in the scene. The bores also
    put the jewels where jewels actually are - COUNTERSUNK into the plate rather
    than stuck on top of it.

    The plate is drilled through and a darker floor sits below it, so a bore
    reads as a bore: a lit wall on one side, a shadowed wall on the other, and
    something further away at the bottom.

    THESE ARE NOW THE REAL PLATE'S HOLES, and that is the difference between a
    plate and a disc with six holes punched in it. Forty of them, twenty inside
    the opening, and four land on the four pivots to within 0.05 face units -
    which is not luck. The plate came out of the same movement as the parts and
    went through the same transform, so the hole the escape wheel's pivot runs
    in is the hole the escape wheel's pivot runs in. The bore at the escape
    arbor measures 5.77 units against a jewel of 5.91: the OM10 drilled it as
    an interference fit for that stone, and it still is one here.

    What was here before was six discs at radii chosen to suit the chatons
    drawn around them - correct-looking, and describing no watch.
    """
    return unary_union([Polygon(ring) for ring in drilling()["holes"]])


def mainplate():
    """
    The plate, drilled. Everything else in the aperture sits on this.

    The DISC is still ours and the drilling is not, and that split is a framing
    decision rather than a shortcut. The real plate is 366 face units across
    with its centre 92 units from a 252-unit opening, so it covers 88 per cent
    of the window and stops; what is on show is a REGION of a real mainplate,
    which is exactly what an open-heart aperture shows of one. Filling the last
    crescent with plate rather than leaving a gap is what the dial would be
    covering if the case were a real one, and because the two are coplanar and
    the same material the join has no edge to see.
    """
    ax, ay, ar = APERTURE
    return disc(ax, ay, ar - 1.0, 320).difference(plate_openings())
