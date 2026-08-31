"""Postage-stamp crops of the real face, for iterating on materials in seconds.

    blender --background --python tools/blender_swatch.py

WHY THIS EXISTS. Every material question so far - is the bezel too dark, did the
chamfer form, is the seconds hand actually gold - was answered by re-rendering
all twelve full-size passes and looking at the result, which is minutes per
question. Nearly all of them are visible in a strip sixty units wide.

IT IS THE SAME SCENE, NOT A MOCK-UP. Cycles' border render evaluates only the
requested rectangle, so these are genuine crops of the actual assembly with the
actual lights and the actual materials - there is no separate test rig to drift
out of step with what ships. Everything lives in render_lib, which both this and
blender_face.py import.

Writes captures/swatch/*.png; view them tiled with tools/swatch_sheet.py.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy                                                    # noqa: E402
import render_lib as rl                                       # noqa: E402

OUT = os.path.join(rl.ROOT, "captures", "swatch")
RES = 2560          # 4 px per face unit inside a crop
SAMPLES = 96        # a crop this small converges fast; this is for looking, not shipping

# (name, x0, y0, x1, y1) in face coordinates, plus which parts to show. None
# means "everything that is not a hand"; a tuple isolates one part, which the
# hands need because all three are modelled pointing at twelve and would
# otherwise pile up on top of each other in the crop.
REGIONS = [
    ("index", 548, 296, 620, 348, None),
    ("bezel", 276, 2, 364, 86, None),
    ("escapement", 336, 350, 436, 450, None),
    ("balance", 232, 402, 332, 502, None),
    ("hour", 292, 236, 352, 330, ("hour", "hour_ridge")),
    ("second", 296, 330, 346, 400, ("second",)),
]


def region(x0, y0, x1, y1):
    """Border render, in face coordinates. Blender's border is normalised and
    y-up; face space is y-down, so the two y bounds swap."""
    r = bpy.context.scene.render
    r.use_border = True
    r.use_crop_to_border = True
    r.border_min_x = x0 / rl.FACE
    r.border_max_x = x1 / rl.FACE
    r.border_min_y = 1.0 - y1 / rl.FACE
    r.border_max_y = 1.0 - y0 / rl.FACE


def main():
    with open(rl.PROFILES) as f:
        payload = json.load(f)

    os.makedirs(OUT, exist_ok=True)
    rl.reset(samples=SAMPLES, res=RES)
    rl.world()
    rl.lights()
    rl.camera()

    specs = payload["parts"] + payload["case"] + payload["hands"]
    objects = {s["name"]: rl.build_part(s) for s in specs}
    hand_names = {s["name"] for s in payload["hands"]}

    # The audit is the point of the exercise as much as the pictures are: it
    # catches an unwelded mesh or an unbevelled part before a single sample is
    # traced, and it costs nothing.
    rl.audit(objects, specs)

    def show(names):
        for name, obj in objects.items():
            obj.visible_camera = name in names
            obj.visible_shadow = name in names

    face = [n for n in objects if n not in hand_names]
    show(face)
    for name, x0, y0, x1, y1, only in REGIONS:
        if only is not None:
            continue
        region(x0, y0, x1, y1)
        rl.render_to(os.path.join(OUT, "%s.png" % name))

    rl.clear_lights()
    rl.lights_axial()
    for name, x0, y0, x1, y1, only in REGIONS:
        if only is None:
            continue
        show(only)
        region(x0, y0, x1, y1)
        rl.render_to(os.path.join(OUT, "%s.png" % name))


if __name__ == "__main__":
    main()
