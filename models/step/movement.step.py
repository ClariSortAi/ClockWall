"""The watch movement seen through the aperture, as a placed CAD assembly.

    python .claude/skills/cad/scripts/gen models/step/movement.step.py --write

WHAT THIS IS. The parts are openmovement.org's OM10 - a real, open-source Swiss
movement - lifted out of its STEP export by tools/om10_extract.py and placed into
the ClockWall face by one similarity transform. Modelling them is what the
previous version did, and the result was a balance wheel that was a hoop with a
bar across it, a hairspring that was concentric circles, and pinions that were
literally overlapping discs.

ONE PART IS OURS, AND ONLY ONE: the slim balance bridge, `_balance_bridge()`
below. It is here because the OM10 has no part that could do its job. See the
long note above that function - the short version is that this face looks at the
FRONT of the watch, the front of a watch has a thin arm over the balance rather
than a decorated cock, and the OM10's inventory was searched for one before a
line of it was written.

WHY ONE TRANSFORM. A similarity - uniform scale, rotation, translation -
preserves every length ratio and every angle in the cluster. So the escapement
that arrives in the face is the escapement that left the OM10: the line of
centres is still straight, the pallet stones still straddle the escape wheel at
the span that lets it alternate, the roller jewel still reaches the fork slot,
and no two solids can have been pushed into one another. The correctness is
inherited rather than re-established, which is the entire reason for reusing a
real movement instead of drawing one.

UNITS ARE FACE UNITS, NOT MILLIMETRES, and that is deliberate. The render, the
profiles and the XAML all speak the 640-unit face frame; a CAD artifact that
spoke millimetres instead would be one conversion away from drift at every step.
The scale is uniform, so measurements and interference volumes are still exactly
as meaningful - they are simply reported in the frame everything else uses.
One face unit is 1/11.78 mm of real watch.

Z is height above the mainplate, +Z toward the camera, matching the render.
"""

import json
import math
import os
import sys

from build123d import (Circle, Compound, Location, Polygon, Rotation, extrude,
                       import_step)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "tools"))
import om10_layout as L                                       # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PARTS = os.path.join(ROOT, "captures", "om10", "parts")

# ------------------------------------------------------------------- framing
#
# The two numbers that are ours. Everything else is measured off the OM10 and
# lives in om10_layout.
APERTURE = (320.0, 450.0, 126.0)
MOVEMENT_FILL = 0.85
_MR = APERTURE[2] * MOVEMENT_FILL

BALANCE_XY = (APERTURE[0] - 0.222 * _MR, APERTURE[1] + 0.133 * _MR)
BALANCE_R = 0.600 * _MR
ESCAPE_BEARING = 51.53          # degrees clockwise from twelve, as before

PLACE = L.make(BALANCE_XY, BALANCE_R, ESCAPE_BEARING)

# What goes in the window, and what each part is made of. The materials are not
# decoration: brass wheels against steel escapement parts and a blued screw is
# the only colour a movement has, and getting it wrong throws that away.
#
# `arbor` is the axis the part turns about, and is what the render rotates it
# around. None means it does not turn.
#
# The fifth column is a placement override: put this solid on a DIFFERENT arbor
# than the one it came off. Only the jewels use it, and they use it because a
# watch has the same jewel at every pivot - one part, fitted four times. Copying
# the real one to the other three bearings is more honest than drawing a red
# disc there, which is what those bearings had before.
#
# The sixth is where a part's TOP face should land, overriding its real height,
# and only the jewels need it. Their real depth is measured against the OM10's
# own mainplate, which is 9.42 mm thick - 111 face units at this scale, against
# the 6.5-unit plate this face uses. Carried across literally the jewels bury
# themselves several plate-thicknesses down and render as nothing at all. Sunk
# just under the plate surface instead, which is what countersunk looks like
# from above, and is the one place the real movement's z cannot be inherited
# because the part it is measured against is not the part we are rendering.
JEWEL_TOP = 5.8

# The slim balance bridge's top face, in face units. It is the height the OM10
# cock's top face used to sit at, and it is not a free choice: the cock screw's
# HEAD begins at 39.81 (its shank is 0.40 mm to local z 1.60, then it steps out
# to 0.794), so a bridge whose top went any higher would have the screw head
# buried in it instead of clamping it down.
BRIDGE_TOP = 39.6

# The bridge, in the OM10's own millimetres, about the balance arbor.
#
# Every number is set against something measured rather than chosen by eye:
#   - the ARM runs at the one cock screw, so the foot lands on a hole the plate
#     already has drilled and the blued screw that was already there still
#     clamps something.
#   - the BORE is wider than the balance staff is anywhere along the height the
#     bridge occupies (the staff is 0.227 mm at its widest there, measured off
#     staff.stl), so the arm cannot foul the thing it is carrying.
#   - the BOSS and the arm's waist are set from the reference photographs in
#     captures/refs: the arm covers about a tenth of the balance disc, against
#     the 40-50% the OM10 cock covered, which is what "largely unobstructed
#     under a thin arm" measures out to.
BRIDGE_T = 0.70                     # mm thick
BRIDGE_BOSS_R = 1.30                # the round pad over the jewel
BRIDGE_BORE_R = 0.62                # clears the staff, and seats the jewel
BRIDGE_FOOT_R = 1.15                # the pad the screw clamps
BRIDGE_FOOT_HOLE_R = 0.55           # the OM10 cock's own screw clearance
# Half-width of the arm at fractions of the way from boss to foot. The waist is
# what makes it read as an arm rather than a slab.
BRIDGE_WAIST = [(0.15, 0.88), (0.42, 0.52), (0.72, 0.56), (1.00, 0.68)]

# The chamfer, in FACE units, and it is applied in Blender rather than here.
# See render_lib.build_part: OCCT refuses to chamfer this outline at any width
# (the arm meets the boss and the foot at near-tangent vertices, which is
# exactly the case its chamfer algorithm gives up on), and Blender's bevel
# modifier does it on the welded mesh without complaint. The reference photos
# make this edge the single most important surface on the part - a continuous
# mirror line round the whole contour - so it is not optional.
BRIDGE_BEVEL_UNITS = 2.4

# The one cock screw. There were two; the other one landed at face (259.9,
# 570.4), which is 134.6 units from the aperture centre and therefore behind the
# dial, so it was never visible and a second foot only widened the arm. Real
# balance cocks are made both ways and every front-on reference photo shows one
# arm. escapement_geometry.COCK_SCREWS carries the same coordinate for the
# plate's hole, and placement_invariants checks the two still agree.
COCK_SCREW = (-13.67, -0.98)

STACK = [
    # name        source part   arbor       material      placed at   top z
    ("escape",    "escape",     "escape",   "escapement", None,       None),
    ("epinion",   "epinion",    "escape",   "steel",      None,       None),
    ("lever",     "lever",      "pallet",   "escapement", None,       None),
    ("stone_a",   "stone_a",    "pallet",   "ruby",       None,       None),
    ("stone_b",   "stone_b",    "pallet",   "ruby",       None,       None),
    ("guard",     "guard",      "pallet",   "steel",      None,       None),
    ("train",     "wheel_c",    "fourth",   "brass",      None,       None),
    ("tpinion",   "pinion_b",   "fourth",   "steel",      None,       None),
    ("roller",    "roller",     "balance",  "steel",      None,       None),
    ("staff",     "staff",      "balance",  "steel",      None,       None),
    ("balance",   "balance",    "balance",  "brass",      None,       None),
    ("collet",    "collet",     "balance",  "steel",      None,       None),
    ("spring",    "hairspring", "balance",  "blued",      None,       None),

    # The arm over the balance, and the ruby its upper pivot runs in. Still
    # called "cock" because that is the layer OpenworkedFace.xaml paints and
    # the invariant that checks a jewel bore lands on the balance arbor; what
    # changed is the SOLID, not the job it does.
    ("cock",      "arm",        None,       "bridge",     "balance",  BRIDGE_TOP),
    ("jewel_c",   "jewel",      "balance",  "ruby",       "balance",  BRIDGE_TOP),

    ("jewel_e",   "jewel",      "escape",   "ruby",       "escape",   JEWEL_TOP),
    ("jewel_b",   "jewel",      "balance",  "ruby",       "balance",  JEWEL_TOP),
    ("jewel_p",   "jewel",      "pallet",   "ruby",       "pallet",   JEWEL_TOP),
    ("jewel_t",   "jewel",      "fourth",   "brass",      "fourth",   JEWEL_TOP),

    # The screw that holds the bridge down, at one of the OM10 cock's OWN screw
    # holes. Not a formula: the holes were read out of the cock's projected
    # outline, and they land on OM00-00106 #8 and #9 in the assembly to two
    # decimals. The earlier pair were drawn from a bearing-and-radius rule that
    # had nothing to do with where the bridge actually is, and once the bridge
    # moved they were left standing in open plate.
    ("screw_1",   "screw_a",    None,       "blued",   COCK_SCREW,       None),
]


def _balance_bridge():
    """
    The one part in this face that is ours, and why.

    WHAT THE PHOTOGRAPHS SAY. captures/refs holds thirteen reference images and
    five of them are open-heart or skeleton dials shot straight on: an Orient
    Bambino, a Tissot Gentleman, a Frederique Constant Heart Beat, a JLC
    Squelette and a full skeleton dress watch. Every one shows the balance
    almost entirely open under a NARROW ARM that ends in a polished boss at the
    jewel. The heavy, shaped, decorated balance COCK appears only in the two
    photographs taken through a display caseback.

    That is not a styling preference, it is which side of the watch you are on.
    A balance has a pivot at each end and a bearing over each pivot. The
    caseback pivot gets the cock, because that is the side a watchmaker
    decorates and a customer looks at through the back. The dial pivot is
    normally buried under the dial, so its bearing is small and plain. An
    open-heart aperture is a hole cut in the DIAL, so it looks at the small
    plain one - and this face is a working clock, so it is the front the viewer
    sees. The render had the caseback's cock sitting in the dial's window.

    WHY THIS IS MODELLED AND NOT LIFTED. The OM10 was searched first, part by
    part, before any of this was written - all 166 solids, sorted by distance
    from the balance arbor and by how little of their own bounding circle they
    fill. What sits over the balance on the dial side is OM10-00102, and it is
    not an arm: it is a 7.6 mm plate section carrying both the balance and the
    pallet bores, which would cover the middle of the balance rather than reach
    across it. The regulator parts (OM00-00125/126/129) are arcs that live ON
    the cock and reach nothing. The movement simply has no thin dial-side
    balance arm to borrow, because in the real OM10 that bearing is a hole in
    the mainplate.

    So this is a prism, one sketch, no invented mechanism: a boss over the
    jewel, a waisted arm, a foot at the screw that was already there. Its
    chamfer is put on in Blender - see BRIDGE_BEVEL_UNITS.

    Comes back in millimetres, about the balance arbor, underside on z = 0 -
    which is exactly the convention om10_extract.py writes its parts in, so
    place() cannot tell the difference and does not have to.
    """
    bx, bz = L.AXIS["balance"]
    dx, dz = COCK_SCREW[0] - bx, COCK_SCREW[1] - bz
    span = math.hypot(dx, dz)
    ux, uz = dx / span, dz / span
    px, pz = -uz, ux                      # unit normal to the arm's axis

    def at(t, half):
        return (ux * span * t + px * half, uz * span * t + pz * half)

    pts = ([at(t, w) for t, w in BRIDGE_WAIST]
           + [at(t, -w) for t, w in reversed(BRIDGE_WAIST)])
    # Polygon builds a face from the winding it is given, and a clockwise one
    # comes out with its normal pointing at -Z - which then extrudes DOWNWARD
    # while the circles beside it extrude up, and the union is a shape with the
    # right volume in the wrong place. Shoelace, then reverse if negative.
    area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1]
               - pts[(i + 1) % len(pts)][0] * pts[i][1]
               for i in range(len(pts))) / 2.0
    if area < 0:
        pts = pts[::-1]

    foot = Location((ux * span, uz * span))
    outline = (Circle(BRIDGE_BOSS_R)
               + foot * Circle(BRIDGE_FOOT_R)
               + Polygon(*pts, align=None)
               - Circle(BRIDGE_BORE_R)
               - foot * Circle(BRIDGE_FOOT_HOLE_R))
    return extrude(outline, amount=BRIDGE_T)


# Parts this file builds rather than lifts out of the OM10, with the same
# manifest shape the extractor writes so place() and cad_parts.py need to know
# nothing about the difference. Kept HERE rather than added to
# captures/om10/parts/manifest.json on purpose: that file is rewritten wholesale
# every time om10_extract.py runs, and an entry hand-added to it would vanish
# silently on the next extraction.
LOCAL = {
    "arm": {
        "source": "ClockWall slim balance bridge",
        "builder": _balance_bridge,
        "thickness": BRIDGE_T,
        "z_lo": 0.0,                      # placed by top_z, so this is unused
        "axis": list(L.AXIS["balance"]),
        "teeth": 0,
        "bevel_units": BRIDGE_BEVEL_UNITS,
    },
}


def _manifest():
    with open(os.path.join(PARTS, "manifest.json")) as f:
        return dict(json.load(f), **LOCAL)


# The datum the whole stack hangs from: the escape wheel's underside sits here,
# just clear of the mainplate's top face at 6.5.
#
# It has to be a WHEEL, and picking the lowest point of any part instead is a
# mistake worth recording. The arbors and the jewels are legitimately BELOW the
# wheels - a pinion runs down through the plate into its bore, a jewel is
# countersunk into it - so taking the floor from the lowest solid lifted the
# entire movement 23 units into the air, hovering over a plate it is supposed to
# be sitting on. Nothing about that is visible in a still: everything moves
# together, so the assembly stays self-consistent and simply floats.
ESCAPE_UNDERSIDE = 8.0


def _floor_mm(manifest):
    """The OM10 height that maps onto ESCAPE_UNDERSIDE - the lowest wheel."""
    return manifest["escape"]["z_lo"]


def place(shape, src, manifest, floor_mm, at=None, top_z=None):
    """
    Carry one OM10 solid into the face.

    Scale, then rotate about Z, then translate - in that order, because the
    extractor already put the part on its own axis at the origin. The axis
    lands where om10_layout says, so the render's rotation centre and this
    solid's centre are the same point by construction rather than by agreement.
    """
    spec = manifest[src]
    # `at` is either a named arbor or an explicit point in the OM10's plane.
    if at is None:
        axis = spec["axis"]
    elif isinstance(at, str):
        axis = L.AXIS[at]
    else:
        axis = at

    scaled = shape.scale(PLACE.SCALE)
    # NEGATED, and the sign is not a detail. om10_layout.to_face rotates POINTS
    # in face coordinates, where y runs down; this rotates SOLIDS in Blender's
    # frame, where y runs up. The same angle in the two frames turns opposite
    # ways, so using it unnegated spun every solid 2 x ROT_DEG away from the
    # layout that positioned it.
    #
    # It is close to invisible, which is why it survived a first check. Every
    # wheel is rotationally symmetric, so spinning one 13 degrees changes
    # nothing you can see, and every part still landed at the right CENTRE
    # because centres come from to_face. Only the long parts show it: the cock's
    # balance jewel hole ended up 14 units off the balance staff, and its screws
    # were driven into solid metal 12 units from their holes.
    turned = Rotation(0, 0, -PLACE.ROT_DEG) * scaled

    fx, fy = PLACE.to_face(axis[0], axis[1])
    if top_z is None:
        z = PLACE.to_z(spec["z_lo"], floor_mm=floor_mm, plate_top=ESCAPE_UNDERSIDE)
    else:
        z = top_z - spec["thickness"] * PLACE.SCALE
    # Face y runs down; the CAD and the render both work in Blender's y-up.
    return Location((fx, -fy, z)) * turned


def gen_step():
    manifest = _manifest()
    floor = _floor_mm(manifest)

    children = []
    for name, src, arbor, material, at, top_z in STACK:
        builder = manifest[src].get("builder")
        if builder is None:
            solid = import_step(os.path.join(PARTS, "%s.step" % src))
        else:
            solid = builder()
        placed = place(solid, src, manifest, floor, at=at, top_z=top_z)
        # Verbose native labels, so inspect/snapshot/viewer name real parts
        # rather than "Solid 7". The material rides along in the label because
        # STEP has nowhere better to put it that survives every reader.
        placed.label = "%s [%s] <- OM10 %s" % (name, material, manifest[src]["source"])
        children.append(placed)

    asm = Compound(children=children)
    asm.label = "ClockWall movement (OM10, scaled %.3f face units/mm)" % PLACE.SCALE
    return asm


if __name__ == "__main__":
    shape = gen_step()
    print("assembly: %d children" % len(shape.children))
    for c in shape.children:
        b = c.bounding_box()
        print("  %-46s x[%7.1f %7.1f] y[%7.1f %7.1f] z[%6.1f %6.1f]"
              % (c.label, b.min.X, b.max.X, b.min.Y, b.max.Y, b.min.Z, b.max.Z))
