"""Makes the smeared companion render for every part that moves too fast to see.

    python tools/smear.py

WHY SMEARS EXIST AT ALL. A display samples motion at discrete frames, and any
part that turns far enough between two of them stops being a moving object and
becomes either a strobe or a jump. Motion blur is not decoration here, it is the
standard remedy for a real artefact - the same reason a camera has a shutter
angle and the reason CG renderers simulate blur rather than just rendering
faster. Each part below gets one companion image, and the face cross-fades to it
on how far that part actually travelled since the previous frame.

WHY EACH SPAN IS WHAT IT IS. The span is never a taste value:

  balance - 180 degrees, which is the bar's exact rotational symmetry and twice
    the inertia blocks'. Smeared over exactly that, the wheel averages into a
    uniform annulus, so it becomes rotationally INVARIANT and turning it changes
    nothing at all. That is what a real balance is: a rim is a smooth ring, and
    a ring looks identical however far you rotate it. It is also why watching a
    running movement is restful, and why this one was not - measured at wall
    scale the balance had been producing 84% of every pixel that changed.

  escape and fork - one beat's travel: half a tooth-space for the wheel, bank to
    bank for the lever. These do not have the balance's problem. They have the
    opposite one: they are STILL for 94% of the beat and then jump, eight times
    a second. An abrupt onset is the strongest involuntary attention cue in
    vision - it is why a dripping tap is maddening and running water is not -
    and 8 Hz sits in the band that reads as jerky rather than as motion. A real
    escapement makes the same jump, but it makes it over seven milliseconds and
    the eye integrates it into a blur. This is that blur.

  spring - the hairspring is the only thing in the aperture moving continuously,
    and it should stay that way: continuity at ONE place is what carries the
    aliveness. It only needs enough smear to stop its coils strobing.

Outputs Assets/movement-<name>-blur.png, in the same 640-unit frame as the
source render.
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
ESCAPE_TEETH = 15
FORK_BANK = 7.0
SPRING_TRAVEL = 0.16
FPS = 60.0

BEATS_PER_SECOND = VPH / 3600.0
PEAK_BALANCE_DPS = AMPLITUDE * 2.0 * math.pi * (BEATS_PER_SECOND / 2.0)

# (part, pivot key, span in degrees). See the header for why each span is what
# it is - none of them is a dial to turn.
PARTS = [
    # 360, not the bar's 180. The roller's impulse pin is a SINGLE feature - it
    # has no rotational symmetry at all - so only a whole turn averages it into
    # a uniform ring. It earns that honestly: the pin sweeps 570 degrees every
    # beat, rather more than a full circle, so a ring is what it actually is.
    ("balance", "balance", 360.0),
    ("escape", "escape", 360.0 / (2.0 * ESCAPE_TEETH)),  # half a tooth-space
    ("fork", "fork", 2.0 * FORK_BANK),                   # bank to bank
    ("spring", "spring", PEAK_BALANCE_DPS * SPRING_TRAVEL / FPS),
]

SAMPLES = 49                           # odd, so the sharp position is included


def smear(src, centre, span, samples=SAMPLES):
    """Accumulate rotations of one render. PREMULTIPLIED, or the transparent
    surround bleeds its colour in and the part picks up a dark halo."""
    acc = np.zeros((src.size[1], src.size[0], 4), np.float64)
    for i in range(samples):
        t = (i / (samples - 1.0)) - 0.5           # -0.5 .. +0.5
        a = np.asarray(
            src.rotate(-t * span, resample=Image.BICUBIC, center=centre),
            np.float64) / 255.0
        acc[..., :3] += a[..., :3] * a[..., 3:4]
        acc[..., 3] += a[..., 3]
    acc /= samples

    alpha = acc[..., 3:4]
    rgb = np.divide(acc[..., :3], alpha, out=np.zeros_like(acc[..., :3]),
                    where=alpha > 1e-6)
    return np.clip(np.concatenate([rgb, alpha], axis=2) * 255.0, 0, 255).astype(np.uint8)


def main():
    with open(PROFILES) as f:
        pivots = json.load(f)["pivots"]

    for name, pivot_key, span in PARTS:
        path = os.path.join(ASSETS, "movement-%s.png" % name)
        src = Image.open(path).convert("RGBA")
        scale = src.size[0] / FACE
        px, py = pivots[pivot_key]
        out = smear(src, (px * scale, py * scale), span)
        dest = os.path.join(ASSETS, "movement-%s-blur.png" % name)
        Image.fromarray(out).save(dest)
        print("wrote %-34s span %6.1f deg" % (os.path.basename(dest), span))


if __name__ == "__main__":
    main()
