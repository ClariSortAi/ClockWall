"""Fast EEVEE preview of the watch face, for shading questions the full
Cycles render is far too slow to answer.

    "C:\\Program Files\\Blender Foundation\\Blender 4.5\\blender.exe" ^
        --background --python tools/shade_preview.py -- [--full] [--out NAME]
                                                          [--samples N] [--res N]

Blender must run this, the same way it runs tools/blender_face.py - it needs
bpy. The `--` before the flags is Blender's own convention: everything after
it is left alone for the script's argv instead of being parsed by Blender.

    tools\\render.ps1 already knows where blender.exe is; the two lines below
    are the whole invocation, copied out so this can be run on its own:

        $blender = Get-ChildItem "C:\\Program Files\\Blender Foundation" `
            -Recurse -Filter blender.exe | Select-Object -First 1
        & $blender.FullName --background --python tools/shade_preview.py -- --full

FLAGS
    --full        Render the whole 640x640 face - movement, case, hands -
                  uncropped. Default is a crop of just the movement aperture,
                  which is what most shading questions are actually about
                  ("is the cock still a white slab") and is most of why this
                  is fast: a border render only costs what is inside it.
    --out NAME    Output file base name. Writes captures/preview/NAME.png.
                  Defaults to "full" or "aperture" depending on the mode above.
    --samples N   EEVEE render samples. Default 24: enough to read shape,
                  material and light direction, nowhere near enough to be
                  noise-free - that trade is the entire point of this tool.
    --res N       Full-canvas resolution before any cropping. Default 900 for
                  the aperture crop, 640 for --full.

WHY THIS EXISTS. render.ps1 -> blender_face.py -> render_lib is Cycles at 256
samples, eleven passes, 1920px - about eight minutes end to end - and every
visual question during the OM10 rewrite cost the whole eight minutes, because
there was no cheaper way to ask Blender what a material looked like.
HANDOVER-REALISM.md names this the single biggest missing capability of the
session that wrote it: "Whoever picks this up should build it before touching
a material."

WHY IT IS SAFE TO TRUST. This does not draw its own scene - a preview of
different materials or different geometry would answer nothing. It calls the
exact same render_lib.world() / lights() / camera() / build_part() the full
render calls, against the exact same captures/geom/profiles.json. The only
things that change are the engine, the sample count, the resolution and the
render border, all of which are switches render_lib.reset() and Blender's own
render settings already provide - nothing about the full render's default
path (CYCLES, 256 samples) moved to make this possible.

WHAT IT DELIBERATELY SKIPS. blender_face.py's one-image-per-rotating-group
choreography and shadow-catcher swapping exist so XAML can spin each group
independently at runtime. A still preview has no runtime to serve: every part
from the chosen scope is built and left visible at once, and Blender's own
depth buffer composites them - which is a MORE faithful picture of "how the
assembled watch looks" than any single one of the real render's layers would
be alone.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import render_lib as rl                                       # noqa: E402

OUT_DIR = os.path.join(rl.ROOT, "captures", "preview")


def _args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []

    full = "--full" in argv
    samples, res, name = 24, None, None
    for i, a in enumerate(argv):
        if a == "--samples" and i + 1 < len(argv):
            samples = int(argv[i + 1])
        elif a == "--res" and i + 1 < len(argv):
            res = int(argv[i + 1])
        elif a == "--out" and i + 1 < len(argv):
            name = argv[i + 1]

    if res is None:
        res = 640 if full else 900
    if name is None:
        name = "full" if full else "aperture"
    return full, samples, res, name


def main():
    full, samples, res, name = _args()

    with open(rl.PROFILES) as f:
        payload = json.load(f)

    os.makedirs(OUT_DIR, exist_ok=True)
    scene = rl.reset(samples=samples, res=res, engine="BLENDER_EEVEE_NEXT")
    # THE ENVIRONMENT IS THE MATERIAL (render_lib's own words). Every part
    # here is metallic and metal has no diffuse component - it can only show
    # what it reflects. EEVEE Next's screen-space defaults leave a mirror
    # showing nothing behind the camera, which renders every part flat black
    # regardless of how good the material is, so real ray-traced reflection
    # of the HDRI has to be turned on explicitly.
    scene.eevee.use_raytracing = True

    rl.world()
    rl.lights()
    rl.camera()

    specs = list(payload["parts"])
    if full:
        specs += payload["case"] + payload["hands"]
    for spec in specs:
        rl.build_part(spec)

    if not full:
        # Blender's render border is normalised 0..1 over the FULL canvas,
        # origin bottom-left - so x tracks face x directly, and y is flipped
        # because face y runs down. A 15% pad keeps the plate's own edge in
        # frame around the aperture instead of cutting exactly to it.
        ax, ay, ar = payload["aperture"]
        pad = 1.15
        scene.render.use_border = True
        scene.render.use_crop_to_border = True
        scene.render.border_min_x = (ax - ar * pad) / rl.FACE
        scene.render.border_max_x = (ax + ar * pad) / rl.FACE
        scene.render.border_min_y = 1.0 - (ay + ar * pad) / rl.FACE
        scene.render.border_max_y = 1.0 - (ay - ar * pad) / rl.FACE

    out = os.path.join(OUT_DIR, "%s.png" % name)
    rl.render_to(out, check=True)
    print("[preview] engine=%s samples=%d res=%d%s -> %s"
          % (scene.render.engine, samples, res,
             "" if full else " (bordered)", out))


if __name__ == "__main__":
    main()
