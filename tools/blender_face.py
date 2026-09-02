"""Renders every asset Controls/OpenworkedFace.xaml loads.

    blender --background --python tools/blender_face.py

The scene - world, lights, materials, solids and the checks on all of them -
lives in render_lib, which tools/blender_swatch.py imports too. That sharing is
the point: the swatch renders postage-stamp crops of THIS scene in eight
seconds, so materials get settled there and only the settled result is rendered
at full size. Nothing about the two can drift apart, because neither owns any of
the setup.

ONE SCENE, MANY PASSES. The whole watch - movement, case and hands - is built
once and each pass only changes who the camera can see. That is what keeps every
layer in register: there is one set of coordinates, one camera, and (for
everything but the hands) one light.

NOTHING DIRECTIONAL MAY BE BAKED INTO A LAYER THAT MOVES. This is the law the
whole file is now arranged around, and it was learned twice in opposite
directions.

The version before this one gave every rotating group its own shadow catcher,
so each sprite carried the shadow it cast. That is correct for a photograph and
wrong for a sprite: XAML turns the image, so the shadow orbits the arbor once a
turn. tools/placement_invariants.py --assets measured it at 46-50% of each
wheel's alpha, lying 18 to 63 units off the pivot at a bearing of about 235
degrees on every one of them - the same bearing, because it is the key light's,
not the wheel's. No still frame shows it. It is the only thing the wall shows.

So each moving group is now rendered with:

  * NO SHADOW CATCHER. A cast shadow belongs to the surface it lands on. That
    surface is the mainplate, and the mainplate is a static layer, so the
    movers cast into the BASE pass instead - visible to shadow rays, invisible
    to the camera. The pools under the wheels stay where the wheels are while
    the wheels turn, which is what a real movement does.

  * AN AXIALLY SYMMETRIC RIG, centred on the group's own arbor: rl.world_axial
    (the measured studio averaged over azimuth, so it is a ring light) plus
    rl.lights_axial on the pivot. Rotation is then a symmetry of everything
    lighting the part, and one baked image is right at every angle.

The static layers - base, cock, case, hand cap - keep the directional key and
their catchers. That is where the drama is allowed to live, and it is what
makes the face read as one object photographed once.

THE HANDS HAVE NO CAST SHADOW AT ALL. Their lobes measured 28 to 121 degrees off
their own axis, which is a sideways shadow from a raking light rather than
anything the axial rig implies. Rather than argue about which shadows are
axial enough, they get none, and the grounding moves to the pivot cap - a
static layer, so its shadow is free to be a real one.

Outputs to Assets/: movement-base.png, one image per rotating group, case.png,
and one per hand - all RGBA in the same 640-unit face frame.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import render_lib as rl                                       # noqa: E402

RES = 1920          # 3 px per face unit: a chamfer must land on more than one

PLATE_TOP = 6.6
# The balance's top face, which is where the cock's shadow lands. Taken from the
# CAD placement rather than remembered: the balance now sits at 19.0-24.6, and a
# shadow catcher left at the old 23.4 would float the cock's shadow inside the
# wheel it is supposed to fall on.
BALANCE_TOP = 24.6
DIAL_TOP = 47.0

# Groups, in the order XAML must paint them - which is z order, since a
# painter's algorithm is all a stack of Images can express. Parts inside a group
# share one pivot and therefore one transform.
#
# The last value is the ARBOR THE GROUP TURNS ABOUT, as a key into
# profiles.json's pivots, and None means the group does not turn. It decides
# everything: a turning group is lit axially about that arbor and catches no
# shadow, a still one gets the face's directional key and its own catcher. The
# XAML is the authority on which is which - tools/placement_invariants.py reads
# the RotateTransforms straight out of it - so a group that gains a transform
# there has to gain a pivot key here on the same edit.
#
# The cock is a group even though it does not turn: it sits ABOVE the balance,
# and baking it into the base plate meant the balance was drawn over its own
# bridge. It has to be a layer on top, and its shadow falls on the balance
# rather than on the plate twenty units further down. It carries the upper
# balance jewel with it - the ruby is set IN the bridge, so it belongs in the
# bridge's image and not twenty units down in the plate's. Being still, it is
# also the one group in this list still allowed a catcher.
#
# The names are the OM10's parts now, so the groups are the real sub-assemblies
# that share an arbor: a wheel with the pinion it is riveted to, the lever with
# both its stones and its guard dart, the balance with its staff and roller.
# Grouping by arbor is not a rendering convenience - it is what "turns together"
# means in the movement, and profiles.json carries each part's arbor so a part
# added later cannot end up in the wrong group by accident.
GROUPS = [
    ("train", ("tpinion", "train"), PLATE_TOP, "train"),
    ("escape", ("epinion", "escape"), PLATE_TOP, "escape"),
    ("fork", ("lever", "stone_a", "stone_b", "guard"), PLATE_TOP, "fork"),
    ("spring", ("spring",), PLATE_TOP, "spring"),
    ("balance", ("balance", "roller", "staff", "collet"), PLATE_TOP, "balance"),
    ("cock", ("cock", "jewel_c", "screw_1"), BALANCE_TOP, None),
]
MOVING = {n for _, names, _, _ in GROUPS for n in names}

# Each hand is two tiers - a base and a raised ridge - which must render into
# ONE image, because XAML turns one image per hand.
#
# The cap is not a hand. XAML paints it last and never turns it, so it is a
# static layer, and it is the one thing on the dial still allowed to drop a
# shadow: with the three hands' own shadows gone it is what says the hands
# stand off the dial rather than being printed on it.
HAND_GROUPS = [
    ("hour", ("hour", "hour_ridge")),
    ("minute", ("minute", "minute_ridge")),
    ("second", ("second",)),
]
CAP_GROUP = ("cap", ("cap",))


def main():
    with open(rl.PROFILES) as f:
        payload = json.load(f)

    os.makedirs(rl.ASSETS, exist_ok=True)
    rl.reset(samples=256, res=RES)
    rl.world()
    rl.lights()
    rl.camera()

    specs = payload["parts"] + payload["case"] + payload["hands"]
    objects = {s["name"]: rl.build_part(s) for s in specs}
    rl.audit(objects, specs)

    case_names = [s["name"] for s in payload["case"]]
    hand_names = [s["name"] for s in payload["hands"]]
    aperture = payload["aperture"]
    catcher = rl.shadow_catcher(aperture, PLATE_TOP)
    ap_r = aperture[2] - 1.0

    def show(names, catching, z=PLATE_TOP, radius=1.0, casters=None,
             isolate=False):
        """Who the camera sees, who casts, and where a shadow may be caught.

        `casters` splits the two halves of visibility apart, and that split is
        the whole fix: the base pass sees only the static parts but is CAST ON
        by every part in the movement, so the contact pools under the wheels
        land on the plate they belong to instead of on the wheels' own sprites.

        `isolate` closes the last door a bearing can get in through. An object
        the camera cannot see is still there for a reflected ray, so a wheel's
        polished chamfer was mirroring the perlaged plate and the two wheels
        beside it - all of them at fixed bearings, all of them baked into a
        sprite that turns. On a moving group the only thing left to reflect is
        the ring world, which has no bearings in it.
        """
        shadowed = names if casters is None else casters
        for name, obj in objects.items():
            seen = name in names
            obj.visible_camera = seen
            obj.visible_shadow = name in shadowed
            for channel in ("visible_diffuse", "visible_glossy",
                            "visible_transmission"):
                setattr(obj, channel, seen if isolate else True)
        catcher.is_shadow_catcher = catching
        catcher.hide_render = not catching
        catcher.location.z = z
        catcher.scale = (radius, radius, 1.0)

    def static_rig():
        """The face's own light: directional, dramatic, and only ever baked
        into something that holds still."""
        rl.clear_lights()
        rl.world()
        rl.lights()

    def axial_rig(pivot_key):
        """Everything that lights this group, centred on the arbor it turns
        about - the ring-light environment as well as the lamps, because the
        environment is what a metal part actually shows."""
        px, py = payload["pivots"][pivot_key]
        rl.clear_lights()
        rl.world_axial()
        rl.lights_axial((px, -py))          # Blender's y runs the other way

    # ---- the movement, seen through the opening --------------------------
    # THE GROUNDING LIVES HERE. Every part of the movement casts into this
    # pass, movers included, while only the still ones are visible to the
    # camera - so each wheel's contact pool is baked onto the plate at the
    # position that wheel occupies, and stays there while the wheel turns. It
    # is the same light and the same shadow as before; what changed is which
    # image it lands in.
    movement_names = [n for n in objects
                      if n not in case_names and n not in hand_names]
    static = [n for n in movement_names if n not in MOVING]
    show(static, catching=False, casters=movement_names)
    rl.render_to(os.path.join(rl.ASSETS, "movement-base.png"))

    for group, names, catch_z, pivot_key in GROUPS:
        moves = pivot_key is not None
        show(names, catching=not moves, z=catch_z, isolate=moves)
        if moves:
            axial_rig(pivot_key)
        rl.render_to(os.path.join(rl.ASSETS, "movement-%s.png" % group))
        if moves:
            static_rig()

    # ---- the case ---------------------------------------------------------
    # The dial's opening casts DOWN into the movement well, and that crescent
    # inside the aperture is most of what stops the opening reading as a hole
    # cut in card. WHERE IT LANDS decides how much of the aperture it covers,
    # and the plate was the wrong answer: the plate is 37 units below the dial
    # but the movement standing on it is not - the balance tops out at 24.6 and
    # the cock at 37 - so projecting onto the plate threw the crescent about
    # twice as far in as anything could actually receive it. It covered the
    # whole opening at a mean alpha of 0.28, which is a 28% black veil over
    # every part the aperture exists to show. Catching it at the height of the
    # movement's own top surfaces halves its reach and keeps the depth cue.
    show(case_names, catching=True, z=BALANCE_TOP)
    rl.render_to(os.path.join(rl.ASSETS, "case.png"))

    # ---- the hands --------------------------------------------------------
    # A source on the pivot axis, so a single baked image is correct at every
    # hour - and no catcher, so nothing is baked into a hand but the hand. See
    # this file's header for why the shadows went rather than being argued
    # about, and case_geometry.py for the lighting.
    rl.clear_lights()
    rl.world_axial()
    rl.lights_axial()
    for hand, names in HAND_GROUPS:
        show(names, catching=False, isolate=True)
        rl.render_to(os.path.join(rl.ASSETS, "hand-%s.png" % hand))

    # ---- the cap, which is a static layer and drops the one real shadow ----
    hand, names = CAP_GROUP
    static_rig()
    show(names, catching=True, z=DIAL_TOP + 3.5, radius=rl.DIAL_R / ap_r)
    rl.render_to(os.path.join(rl.ASSETS, "hand-%s.png" % hand))


if __name__ == "__main__":
    main()
