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

import math
import sys

from shapely import affinity
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

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


def _at(fx, fy, fr=None):
    """A placement given as fractions of the aperture: centre, then radius."""
    p = (_AX + fx * _AR, _AY + fy * _AR)
    return p if fr is None else (p[0], p[1], fr * _AR)


BALANCE = _at(-0.222, 0.133, 0.600)   # cx, cy, rim outer radius
ESCAPE = _at(0.533, -0.467, 0.256)    # cx, cy, tooth tip radius
STAFF = _at(0.289, -0.156)            # the pallet fork pivots here

# The escape wheel is riveted to a seven-leaf pinion, and that pinion is what
# the going train actually drives.
EPINION_R = ESCAPE[2] * 0.40
ESCAPE_PINION_LEAVES = 7
TRAIN_TEETH = 64

# THE TRAIN WHEEL IS PLACED IN MESH, not parked nearby. It used to sit off in a
# corner at a distance no pair of gears could ever span, which is a thing you
# cannot un-see once you have noticed it: two wheels turning in sympathy with a
# visible gap between them. Deriving its centre from the two radii means the
# teeth interleave, and the mesh is then the most convincing single detail in
# the aperture - it is the one place the picture proves the parts drive
# each other rather than merely sharing a timer.
_TRAIN_R = 0.413 * _AR
_MESH = _TRAIN_R * 0.93 + EPINION_R * 1.02      # root radius meets tip radius
_TRAIN_BEARING = 300.0                          # up and to the left, clear of the balance
TRAIN = (ESCAPE[0] + _MESH * math.sin(math.radians(_TRAIN_BEARING)),
         ESCAPE[1] - _MESH * math.cos(math.radians(_TRAIN_BEARING)),
         _TRAIN_R)

# 64 teeth driving 7 leaves. The escape wheel therefore turns 9.14 times for
# every turn of the train wheel, and OpenworkedFace reads that ratio straight
# off this constant rather than being given a speed to hard-code.
TRAIN_RATIO = TRAIN_TEETH / ESCAPE_PINION_LEAVES

# The parts that are not circles - the lever, the cock, the jewel settings - are
# drawn from absolute dimensions rather than fractions, because a lever is a
# shape and not a proportion. U rescales all of them together when the aperture
# changes, so nothing gets left at its old size. It is 1.0 at the r=90 opening
# these dimensions were originally drawn against.
U = _AR / 90.0

ESCAPE_TEETH = 15

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
PALLET_HALF_SPACES = 5
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


def escape_wheel(cx, cy, R, teeth=ESCAPE_TEETH, root=0.885,
                 hub=0.17, rim_inner=0.74, crossings=4, spoke_half_deg=7.5):
    """A Swiss club-tooth escape wheel: rim disc, plus teeth, minus crossings."""
    body = disc(cx, cy, R * root)

    tooth_shapes = []
    for i in range(teeth):
        base = i * 360.0 / teeth
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


def hairspring(cx, cy, R, r0=0.17, r1=0.56, coils=6.5, steps=560):
    """
    The balance spring: a flat Archimedean spiral.

    Its absence was most of why the balance read as a gear. A balance wheel on
    its own is a ring; the spring coiled beneath it is what says oscillator, and
    it is the most recognisable object in a movement.

    Returned as an open curve to be STROKED, not as a filled ribbon. Buffering
    it into a shape doubled the point count for a part one pixel wide - 40KB of
    path data to draw a hairline.
    """
    return LineString([polar(cx, cy, (i / steps) * coils * 360.0,
                             R * (r0 + (r1 - r0) * i / steps))
                       for i in range(steps + 1)])


# ---------------------------------------------------------------- pallet fork

def pallet_fork(sx, sy, to_escape, to_balance, length=40.0, reach=None, half=None):
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
    # separates a lever from a stick.
    slot = Polygon([(L - 11, -2.0), (L + 2, -2.0), (L + 2, 2.0), (L - 11, 2.0)])

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
        "escape": escape_wheel(ex, ey, eR),
        "ecollet": collet(ex, ey, eR * 0.19),
        "balance": balance(bx, by, bR),
        "bscrews": balance_screws(bx, by, bR),
        "spring": hairspring(bx, by, bR),
        # The stones are placed off the WHEEL; the lever's arms are then sized
        # to reach them, rather than both being drawn to a remembered number.
        "fork": pallet_fork(sx, sy, heading((sx, sy), (ex, ey)),
                            heading((sx, sy), (bx, by)),
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


def chaton(cx, cy, r_jewel=3.4 * U, collar=2.6 * U):
    """A jewel setting: the steel collar. The ruby that sits in it is a
    separate part, because it is a separate material."""
    return disc(cx, cy, r_jewel + collar, 48).difference(disc(cx, cy, r_jewel, 40))


def jewels_and_screws(bx, by, ex, ey, sx, sy):
    """The jewelled bearings and the blued screws, as three sets of shapes:
    collars, rubies, screws. Positions are the pivots that actually exist -
    balance staff, escape arbor, pallet staff - plus the screws that hold the
    cock down."""
    collars, rubies = [], []
    for p, rj in (((bx, by), 3.6 * U), ((ex, ey), 2.8 * U), ((sx, sy), 2.4 * U),
                  (TRAIN[:2], 3.0 * U)):
        collars.append(chaton(p[0], p[1], rj))
        rubies.append(disc(p[0], p[1], rj, 40))

    ang = heading((bx, by), APERTURE[:2]) + 180.0
    screws = []
    for s in (-1, 1):
        n = polar(0.0, 0.0, ang + 90.0, 4.4 * U * s)
        anchor = polar(bx, by, 116.0, APERTURE[2] * 0.86)
        screws.append(disc(anchor[0] + n[0], anchor[1] + n[1], 3.0 * U, 32))

    return (unary_union(collars), unary_union(rubies), unary_union(screws))


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
    """
    holes = []

    # A jewel sink at every pivot that exists, sized to its chaton.
    for (px, py), r in ((BALANCE[:2], 7.6), (ESCAPE[:2], 6.0),
                        (STAFF, 5.2), (TRAIN[:2], 6.4)):
        holes.append(disc(px, py, r, 48))

    # The screws that hold the cock down. Their bores are countersunk, which is
    # why a screw head sits flush and not proud.
    ax, ay, ar = APERTURE
    n = polar(0.0, 0.0, 116.0 + 90.0, 1.0)
    anchor = polar(BALANCE[0], BALANCE[1], 116.0, ar * 0.86)
    for s in (-1, 1):
        holes.append(disc(anchor[0] + n[0] * 4.4 * s * 1.4,
                          anchor[1] + n[1] * 4.4 * s * 1.4, 4.2, 32))

    return unary_union(holes)


def mainplate():
    """The plate, drilled. Everything else in the aperture sits on this."""
    ax, ay, ar = APERTURE
    return disc(ax, ay, ar - 1.0, 320).difference(plate_openings())
