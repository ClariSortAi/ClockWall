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

EVERY ROTATING PART CARRIES ITS OWN SHADOW. An earlier version baked the moving
parts' shadows into the static plate, which meant the balance's shadow stayed
put while the balance spun. Each rotating group is now rendered over an
invisible shadow catcher, so its shadow lands in its OWN image and turns with
it, and the plate pass casts nothing from anything that moves.

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

# Rotating groups, in the order XAML must paint them - which is z order, since a
# painter's algorithm is all a stack of Images can express. Parts inside a group
# share one pivot and therefore one transform. The last value is the height the
# group's shadow lands at.
#
# The cock is a group even though it does not turn: it sits ABOVE the balance,
# and baking it into the base plate meant the balance was drawn over its own
# bridge. It has to be a layer on top, and its shadow falls on the balance
# rather than on the plate twenty units further down. It carries the upper
# balance jewel with it - the ruby is set IN the bridge, so it belongs in the
# bridge's image and not twenty units down in the plate's.
#
# The last value says to light the group on its OWN AXIS instead of by the
# face's key. Only the balance asks for it, and it is the same exception the
# hands get, for a stronger reason. A baked render carries its highlight in the
# image, so rotating the image drags that highlight around with it - and the
# balance turns through 570 degrees eight times a second. A specular band
# sweeping round a rim is not what a turned wheel does; the rim is
# rotationally symmetric and its highlight STAYS WHERE THE LIGHT IS.
#
# It is also most of why the movement reads as chaotic. Measured at wall scale,
# the balance was producing 84% of all frame-to-frame change in the aperture,
# and a real balance produces almost none - its rim is a smooth annulus, so
# turning it changes nothing you can see. Lighting it axially makes rotation a
# symmetry of the lighting again, and leaves only the bar and the timing screws
# actually moving, which is what a real one shows.
# The names are the OM10's parts now, so the groups are the real sub-assemblies
# that share an arbor: a wheel with the pinion it is riveted to, the lever with
# both its stones and its guard dart, the balance with its staff and roller.
# Grouping by arbor is not a rendering convenience - it is what "turns together"
# means in the movement, and profiles.json carries each part's arbor so a part
# added later cannot end up in the wrong group by accident.
GROUPS = [
    ("train", ("tpinion", "train"), PLATE_TOP, None),
    ("escape", ("epinion", "escape"), PLATE_TOP, None),
    ("fork", ("lever", "stone_a", "stone_b", "guard"), PLATE_TOP, None),
    ("spring", ("spring",), PLATE_TOP, None),
    ("balance", ("balance", "roller", "staff", "collet"), PLATE_TOP, "balance"),
    ("cock", ("cock", "jewel_c", "screw_1"), BALANCE_TOP, None),
]
MOVING = {n for _, names, _, _ in GROUPS for n in names}

# Each hand is two tiers - a base and a raised ridge - which must render into
# ONE image, because XAML turns one image per hand.
HAND_GROUPS = [
    ("hour", ("hour", "hour_ridge")),
    ("minute", ("minute", "minute_ridge")),
    ("second", ("second",)),
    ("cap", ("cap",)),
]


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

    def show(names, catching, z=PLATE_TOP, radius=1.0):
        for name, obj in objects.items():
            obj.visible_camera = name in names
            obj.visible_shadow = name in names
        catcher.is_shadow_catcher = catching
        catcher.hide_render = not catching
        catcher.location.z = z
        catcher.scale = (radius, radius, 1.0)

    # ---- the movement, seen through the opening --------------------------
    static = [n for n in objects
              if n not in MOVING and n not in case_names and n not in hand_names]
    show(static, catching=False)
    rl.render_to(os.path.join(rl.ASSETS, "movement-base.png"))

    for group, names, catch_z, axial in GROUPS:
        show(names, catching=True, z=catch_z)
        if axial:
            # Blender's y runs the other way from face space.
            px, py = payload["pivots"][axial]
            rl.clear_lights()
            rl.lights_axial((px, -py))
        rl.render_to(os.path.join(rl.ASSETS, "movement-%s.png" % group))
        if axial:
            rl.clear_lights()
            rl.lights()

    # ---- the case ---------------------------------------------------------
    # The catcher stays at plate height so the dial's opening casts DOWN into
    # the movement well. That crescent of shadow inside the aperture is most of
    # what stops the opening reading as a hole cut in card.
    show(case_names, catching=True, z=PLATE_TOP)
    rl.render_to(os.path.join(rl.ASSETS, "case.png"))

    # ---- the hands --------------------------------------------------------
    # Lights swapped for a source on the pivot axis, so a single baked image is
    # correct at every hour. See the note in case_geometry.py.
    rl.clear_lights()
    rl.lights_axial()
    for hand, names in HAND_GROUPS:
        # Each hand's shadow lands on the dial, and must turn with it.
        show(names, catching=True, z=DIAL_TOP + 3.5, radius=rl.DIAL_R / ap_r)
        rl.render_to(os.path.join(rl.ASSETS, "hand-%s.png" % hand))


if __name__ == "__main__":
    main()
