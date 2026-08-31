"""Case, dial and applied indices - the other sixty per cent of the face.

WHY THIS EXISTS. The movement inside the aperture was rebuilt as solids and
rendered as metal, and then everything AROUND it was left as a flat PIL
gradient. That was the same mistake as before, just moved outward: the case is
the largest area of metal on the whole face and it was a grey ring with a
gradient on it, which reads as moulded plastic. The indices had a painted-on
light and dark half rather than a real facet, so they could not catch a
highlight or drop a shadow.

So the case is modelled here and rendered in the same scene, by the same lights,
at the same camera as the escapement. That last point is the one that matters:
one light direction across the whole face is what makes it look like one object
photographed once, rather than two pictures pasted together.

WHAT STAYS IN PIL. The sunburst, the minute track and the dial printing are a
TEXTURE - a soleil finish is a pattern of radial brushing, which is exactly what
a procedural image is good at and what geometry is bad at. Blender maps it onto
the dial disc and lights it. PIL draws the pattern; Blender decides how it
catches the light.

Face space throughout: 640x640, centre (320,320).
"""

import math

from shapely.geometry import Polygon
from shapely.ops import unary_union

from escapement_geometry import APERTURE, disc, polar, rounded

CENTRE = (320.0, 320.0)

CASE_R = 314.0        # outside of the bezel
BEZEL_IN = 289.0      # where the bezel stops and the dial shows
DIAL_R = 288.0        # tucks a little under the bezel, as a dial does

# Applied indices: solid metal batons sitting proud of the dial. "Applied" is
# the whole point - they are separate parts screwed or glued on, so they throw
# a shadow, and that shadow is most of what separates an applied index from a
# printed one.
INDEX_OUT = 279.0
INDEX_IN = 246.0
INDEX_HALF_W = 7.5

# A polished ring standing in the dial opening, framing the movement. Real
# openworked dials have one; without it the aperture is a hole cut in a card.
REHAUT_IN = APERTURE[2]
REHAUT_OUT = APERTURE[2] + 7.0


def baton(deg, r_in=INDEX_IN, r_out=INDEX_OUT, half_w=INDEX_HALF_W,
          offset=0.0, cx=CENTRE[0], cy=CENTRE[1]):
    """
    One index, as a rectangle lying along its own radius.

    `offset` slides it sideways off that radius, which is how the double baton
    at twelve is made: two of these, one either side.
    """
    a = math.radians(deg)
    # Unit vectors along the radius and across it.
    ux, uy = math.sin(a), -math.cos(a)
    vx, vy = uy, -ux

    def at(r, w):
        return (cx + ux * r + vx * (w + offset), cy + uy * r + vy * (w + offset))

    return Polygon([at(r_in, -half_w), at(r_out, -half_w),
                    at(r_out, half_w), at(r_in, half_w)])


def indices():
    """
    Eleven hours' worth of batons, doubled at twelve.

    Six is missing because the aperture is there. That is not a compromise - a
    dial with an opening at six omits the six, and putting one back would be the
    detail that gave the whole thing away.
    """
    out = []
    for hour in range(1, 13):
        if hour == 6:
            continue
        deg = hour * 30.0
        if hour == 12:
            # The double baton at twelve: the one asymmetry a plain baton dial
            # gets, and what makes twelve findable without a numeral.
            out.append(baton(deg, half_w=4.4, offset=-6.2))
            out.append(baton(deg, half_w=4.4, offset=6.2))
        else:
            out.append(baton(deg))
    return unary_union(out)


def bezel():
    """The case ring. A wide flat annulus, given its dome by a large chamfer at
    render time rather than by being modelled as a cone - the chamfer is a real
    45-degree facet and a facet is what catches the line of light."""
    cx, cy = CENTRE
    return disc(cx, cy, CASE_R, 512).difference(disc(cx, cy, BEZEL_IN, 512))


def dial():
    """The dial plate, with the opening at six punched clean through it. The
    movement is rendered below and shows through the hole."""
    cx, cy = CENTRE
    ax, ay, ar = APERTURE
    return disc(cx, cy, DIAL_R, 512).difference(disc(ax, ay, ar, 256))


def rehaut():
    """The polished ring standing in the opening."""
    ax, ay, ar = APERTURE
    return disc(ax, ay, REHAUT_OUT, 256).difference(disc(ax, ay, REHAUT_IN, 256))


def build():
    return {
        "bezel": bezel(),
        "dial": dial(),
        "rehaut": rehaut(),
        "indices": rounded(indices(), 1.1),
    }


# z is the underside height and thickness the depth, both in face units, and
# both stacked ABOVE the movement - the cock finishes around 37, so the dial
# starts at 44. The gap is deliberate and large: the dial's opening casts down
# into the movement well, and that shadow around the inside of the aperture is
# what gives the opening any depth at all.
#
# The chamfer column is the important one. An applied index is a baton with a
# ROOF - two flat facets meeting in a ridge down its length - and a chamfer
# wider than the baton's half-width is exactly how you get one: the two bevels
# run into each other and the flat top disappears. So the index chamfer is set
# above INDEX_HALF_W on purpose, and the bezel's is set wide enough to turn a
# flat ring into a dome.
# WHY THE CHAMFERS HERE ARE SMALL, after a pass where they were large.
#
# A bevel modifier can only make a 45-degree facet, and a 45-degree facet in a
# straight-down view reflects sideways - at the HORIZON of the environment,
# which is its darkest band. So the pass that finally got wide chamfers working
# turned every index into a black arrowhead and the bezel into a black ring.
# The chamfer was doing exactly what was asked and the ask was wrong.
#
# What a polished index actually shows is a broad near-horizontal top catching
# the sky, edged by a fine bright chamfer. Near-horizontal is the operative
# word: those surfaces reflect UPWARD, where the light is. So the tops stay flat
# and the chamfers are trimmed back to an edge treatment.
STACK = [
    ("rehaut", 41.0, 7.0, "steel", 2.0),
    ("dial", 44.0, 3.0, "dial", 0.8),
    ("bezel", 44.0, 14.0, "case", 3.4),
    ("indices", 47.0, 6.0, "index", 1.8),
]


# ----------------------------------------------------------------------- hands
#
# WHY THE HANDS ARE LIT DIFFERENTLY FROM EVERYTHING ELSE, which is the one place
# this face deliberately breaks its own rule about a single light direction.
#
# A rendered hand is baked at twelve o'clock and then TURNED by XAML. Under the
# face's key light - fixed in the upper left - the lit facet of a dauphine hand
# would turn with it, so at six o'clock the hand would appear lit from the lower
# right while every other shadow on the dial still pointed the other way. A hand
# whose shine follows it round the dial is more obviously wrong than a hand with
# no shine at all, which is why these were left as flat vectors for so long.
#
# The fix is not to bake more angles, it is to light them with something that
# does not care about angle. A source centred on the hand's own pivot axis is
# ROTATIONALLY SYMMETRIC about that axis, so rotating the hand is a symmetry of
# the lighting and a single baked image is correct at every position of the
# dial. What that gives is the bright line down the ridge, which is exactly what
# a polished dauphine hand looks like in life.
#
# So: hands are modelled here like everything else, and blender_movement.py
# swaps the lights for their pass alone.

HAND_HOUR_R = 150.0
HAND_MIN_R = 214.0
HAND_SEC_R = 232.0


def dauphine(length, half_w, shoulder, tail, cx=CENTRE[0], cy=CENTRE[1]):
    """
    A dauphine hand: a long faceted kite.

    Widest near the base and tapering in a straight line to a point, with a
    short tail past the pivot - real hands carry one to balance, and without it
    the silhouette reads as an arrow stuck on a spindle.

    The FACET is not in this outline. It comes from the chamfer at render time
    being set wider than half_w, so the two bevels meet in a ridge down the
    length and the flat top disappears. That ridge is the whole hand.
    """
    return Polygon([
        (cx, cy - length),                       # tip
        (cx - half_w, cy - shoulder),
        (cx - half_w * 0.34, cy + tail),
        (cx + half_w * 0.34, cy + tail),
        (cx + half_w, cy - shoulder),
    ])


def hand_second(cx=CENTRE[0], cy=CENTRE[1]):
    """A needle with a pierced counterweight. It carries the beat, so it is the
    hand the eye should find first - and the only one in gold."""
    w = 2.0
    needle = Polygon([(cx - w, cy - HAND_SEC_R), (cx + w, cy - HAND_SEC_R),
                      (cx + w * 1.5, cy + 40), (cx - w * 1.5, cy + 40)])
    weight = disc(cx, cy + 54, 13.0, 64).difference(disc(cx, cy + 54, 5.4, 40))
    return unary_union([needle, weight])


def cap(cx=CENTRE[0], cy=CENTRE[1]):
    """The boss over the hand pivots. Painted last of everything, because it is
    what hides three stacked arbors."""
    return disc(cx, cy, 13.0, 96)


def build_hands():
    """
    Each dauphine hand comes in TWO TIERS, not one.

    A dauphine hand is faceted, and the obvious way to model that - one slab
    with a wide chamfer - cannot work here: a bevel is always 45 degrees, and a
    45-degree facet under a straight-down camera reflects at the horizon and
    comes back black. The hands rendered as dark shards.

    So the facet is built instead as a broad base with a narrower ridge standing
    on it, each nearly flat and each with a fine chamfer. Both surfaces face
    upward, so both catch the light; the step between them draws the line down
    the length that a real dauphine hand shows. Shrinking the outline is what
    makes the ridge, and it pulls back from the tip on its own - which is right,
    because the facets on a real hand converge before the point does.
    """
    hour = dauphine(HAND_HOUR_R, 11.0, 44.0, 34.0)
    minute = dauphine(HAND_MIN_R, 9.0, 54.0, 40.0)
    return {
        "hour": hour,
        "hour_ridge": hour.buffer(-4.2, join_style=2),
        "minute": minute,
        "minute_ridge": minute.buffer(-3.4, join_style=2),
        "second": hand_second(),
        "cap": cap(),
    }


# Above the indices, which finish at 53. Each hand clears the one below it so
# they cast on each other, and the chamfer on the hour and minute hands is wider
# than their own half-width - that is what turns a flat baton into a roof.
# Thicknesses here are set by the ROOF, not by how thick a hand really is. A
# 45-degree facet drops as far as it is wide, so a chamfer of nine needs nine
# units beneath it to descend into. Seen from straight overhead none of that
# thickness is visible as thickness - it only shows as the shading of the
# facets, which is the entire object of the exercise.
HAND_STACK = [
    ("hour", 58.0, 3.4, "index", 1.1),
    ("hour_ridge", 60.8, 2.2, "index", 1.0),
    ("minute", 66.0, 3.2, "index", 1.0),
    ("minute_ridge", 68.6, 2.0, "index", 0.9),
    ("second", 74.0, 2.4, "gold", 0.9),
    ("cap", 78.0, 7.0, "index", 2.4),
]
