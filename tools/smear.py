"""Makes the smeared companion to the balance render.

    python tools/balance_blur.py

WHY A BLURRED COPY EXISTS AT ALL. The balance is the largest wheel in the
aperture and the fastest thing in the watch: 285 degrees either side of centre,
four times a second. At 60fps that is up to 119 degrees BETWEEN CONSECUTIVE
FRAMES, and the wheel has two arms and a ring of timing screws - so 119 degrees
is indistinguishable from 61 the other way, the apparent direction reverses at
random, and a correctly running balance reads as a wheel spinning at some
enormous and varying speed. It is the wagon-wheel effect, and no amount of
correcting the physics touches it, because the physics is not what is wrong.
The display cannot sample it. Nothing at 4 Hz can be sampled at 60.

WHAT A REAL ONE LOOKS LIKE, WHICH IS THE ANSWER. A balance photographed or
watched does not resolve into arms. It smears into a translucent disc through
the middle of its swing and comes back into focus at the two turning points,
where it is momentarily stationary - that flutter is the whole visual signature
of a running watch. So the face cross-fades between this smear and the sharp
render by the balance's own angular speed, and the aliasing has nothing left to
bite on: at the speeds that alias there is no longer any detail to alias.

The smear spans one FRAME of travel at peak speed, because that is the exposure
being imitated. Accumulating the real asset rather than blurring it in a paint
program keeps the screws, the shadow and the rim highlight all smearing the way
they actually would.

Output: Assets/movement-balance-blur.png, same 640-unit frame as its source.
"""

import json
import math
import os

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "Assets")
PROFILES = os.path.join(ROOT, "captures", "geom", "profiles.json")

FACE = 640.0
VPH = 28_800
AMPLITUDE = 285.0
FPS = 60.0

# Peak angular speed of simple harmonic motion is amplitude * omega, and the
# balance completes one oscillation every two beats. 119 degrees per frame at
# 4 Hz on a 60Hz panel - which is the LOWER bound on how far it smears, since
# the eye integrates over more like two or three frames, not one.
BEATS_PER_SECOND = VPH / 3600.0
PEAK_DEG_PER_SEC = AMPLITUDE * 2.0 * math.pi * (BEATS_PER_SECOND / 2.0)
FRAME_SWEEP = PEAK_DEG_PER_SEC / FPS

# ...but the span is taken from the wheel's SYMMETRY instead, and that choice is
# the difference between a smear that helps and one that only half helps.
#
# This balance is one bar through the centre - 180 degree symmetry - and four
# inertia blocks at 90. Smeared over exactly 180 degrees both features average
# into a perfectly uniform annulus, so the blurred wheel becomes rotationally
# INVARIANT and turning it changes nothing at all. That is not a trick; it is
# what a real smeared balance is. A rim is a smooth ring, and a ring does not
# look different when you rotate it - which is why a running balance is calm to
# watch and why measuring one frame against the next found this face's balance
# producing 84% of all the change in the aperture.
#
# 119 degrees left the bar smeared but still lumpy, so rotating the smear went
# on churning pixels for no visible motion. 180 is both wider than the frame
# sweep (so, honest) and the exact point where the churn goes to zero.
SPAN = 180.0

SAMPLES = 49                           # odd, so the sharp position is included


def main():
    with open(PROFILES) as f:
        pivot = json.load(f)["pivots"]["balance"]

    src = Image.open(os.path.join(ASSETS, "movement-balance.png")).convert("RGBA")
    scale = src.size[0] / FACE
    centre = (pivot[0] * scale, pivot[1] * scale)

    # Accumulate PREMULTIPLIED, or the transparent surround bleeds its colour
    # into the smear and the wheel picks up a dark halo.
    acc = np.zeros((src.size[1], src.size[0], 4), np.float64)
    for i in range(SAMPLES):
        t = (i / (SAMPLES - 1.0)) - 0.5           # -0.5 .. +0.5
        a = np.asarray(
            src.rotate(-t * SPAN, resample=Image.BICUBIC, center=centre),
            np.float64) / 255.0
        acc[..., :3] += a[..., :3] * a[..., 3:4]
        acc[..., 3] += a[..., 3]
    acc /= SAMPLES

    alpha = acc[..., 3:4]
    rgb = np.divide(acc[..., :3], alpha, out=np.zeros_like(acc[..., :3]),
                    where=alpha > 1e-6)
    out = np.concatenate([rgb, alpha], axis=2)

    path = os.path.join(ASSETS, "movement-balance-blur.png")
    Image.fromarray(np.clip(out * 255.0, 0, 255).astype(np.uint8)).save(path)
    print("wrote %s  span %.0f deg over %d samples" % (path, SPAN, SAMPLES))


if __name__ == "__main__":
    main()
