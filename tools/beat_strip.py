"""Frames of the movement across one beat, so the MOTION can be looked at.

    python tools/beat_strip.py               # 60fps sampling, two beats
    python tools/beat_strip.py --sub         # inside the transit, 40x slower
    python tools/beat_strip.py --fork-sign -1

WHY THIS EXISTS. Everything else in tools/ answers questions about how the
movement LOOKS at one instant, and blender_swatch.py made that loop eight
seconds long. There was no equivalent for how it MOVES, so every question about
the motion cost a build, a deploy, a screenshot that shows a single frame, and
then guessing. Two things went unnoticed for exactly that reason:

  * the balance is the largest wheel in the aperture and sweeps 570 degrees at
    4 Hz, which at 60fps is up to 119 degrees BETWEEN FRAMES - so a wheel with
    two arms and a ring of timing screws aliases into nonsense. It is not
    turning too fast; it is being sampled far too slowly, and that is a
    property of the display, not of the caliber.
  * the pallet fork and the escape wheel have a phase RELATIONSHIP that the
    drawing has to agree with. Both are periodic in two beats, so getting it
    backwards does not look broken in a still - it looks broken in motion, and
    only in motion.

--sub samples inside the seven milliseconds the lever is actually crossing,
which no real frame ever lands on. That is the ground truth to check the
engagement against, not something to make the app do.

THE ANGLES HERE MIRROR Services/Caliber.cs and the tooth counts come from
escapement_geometry, which is also where the drawing gets them. Kept in step by
_check() below rather than by hope.

Writes captures/beat/strip.png.
"""

import math
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import escapement_geometry as eg                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "Assets")
OUT = os.path.join(ROOT, "captures", "beat")

RES = 1920                      # the assets' native size
FACE = 640.0
SCALE = RES / FACE

VPH = 28_800
ESCAPE_TEETH = 15
AMPLITUDE = 285.0
LIFT = 52.0
FORK_BANK = 7.0                 # the face's exaggeration, from OpenworkedFace

BEATS_PER_SECOND = VPH / 3600.0
ESCAPE_STEP = 360.0 / (2.0 * ESCAPE_TEETH)
TRAIN_STEP = -ESCAPE_STEP * eg.ESCAPE_PINION_LEAVES / eg.TRAIN_TEETH
SPRING_TRAVEL = 0.16
BALANCE_BAR_DEG = 7.0           # see OpenworkedFace.BalanceBarDegrees
PEAK_DPS = AMPLITUDE * 2.0 * math.pi * (BEATS_PER_SECOND / 2.0)

PIVOTS = {
    "escape": (387.158, 391.158),
    "train": (333.849, 360.380),
    "balance": (292.028, 466.758),
    "spring": (292.028, 466.758),
    "fork": (356.414, 430.344),
}

APERTURE = (320.0, 450.0, 126.0)


def read(beats, fork_sign=1.0):
    """Caliber.Read, in Python. See the module docstring on why this is a copy
    rather than an import: the shipping version is C# inside a WinUI app."""
    balance = AMPLITUDE * math.sin(math.pi * (beats % 2.0))
    fork = max(-1.0, min(1.0, balance / (LIFT / 2.0)))
    n = math.floor(beats + 0.5)
    heading = 1.0 if n % 2 == 0 else -1.0
    advanced = n - 1.0 + (fork * heading + 1.0) / 2.0
    return {
        "balance": balance,
        "speed": min(1.0, abs(math.cos(math.pi * (beats % 2.0)))
                     * PEAK_DPS / 60.0 / BALANCE_BAR_DEG),
        "spring": balance * SPRING_TRAVEL,
        "fork": fork * FORK_BANK * fork_sign,
        "escape": advanced * ESCAPE_STEP,
        "train": advanced * TRAIN_STEP,
    }


def _check():
    """The invariants Caliber.SelfCheck asserts, restated here so this tool
    cannot quietly disagree with the movement it claims to be previewing."""
    assert abs(read(4.0)["balance"]) < 1e-9, "balance is at centre on the beat"
    assert abs(abs(read(4.5)["balance"]) - AMPLITUDE) < 1e-6, "and at the top mid-beat"
    assert abs(abs(read(4.5)["fork"]) - FORK_BANK) < 1e-9, "lever banked mid-beat"
    transit = 2.0 * math.asin(LIFT / 2.0 / AMPLITUDE) / math.pi
    assert transit < 0.12, "lever still for most of the beat"
    # A whole beat of escape wheel is half a tooth: two beats per tooth.
    assert abs(2.0 * ESCAPE_TEETH * ESCAPE_STEP - 360.0) < 1e-9
    return transit


def fade(im, k):
    """Scale an RGBA layer's alpha, the way XAML Opacity does."""
    r, g, b, al = im.split()
    return Image.merge("RGBA", (r, g, b, al.point(lambda v: int(v * k))))


def frame(beats, fork_sign=1.0, zoom=False):
    """One composited frame of the movement, cropped to the aperture."""
    a = read(beats, fork_sign)
    out = Image.new("RGBA", (RES, RES), (10, 10, 13, 255))
    for name in ("base", "train", "escape", "fork", "spring", "balance", "cock"):
        im = Image.open(os.path.join(ASSETS, "movement-%s.png" % name)).convert("RGBA")
        if name in a and a[name]:
            px, py = PIVOTS[name]
            im = im.rotate(-a[name], resample=Image.BICUBIC,
                           center=(px * SCALE, py * SCALE))
        if name == "balance":
            # The same cross-fade the face does, or this previews something the
            # app does not show - which is the one thing a preview must not do.
            im = fade(im, 1.0 - a["speed"])
            # The smear is NOT rotated - it is rotationally invariant, so
            # turning it would only add resampling noise. See the .xaml.
            blur = Image.open(os.path.join(ASSETS, "movement-balance-blur.png")).convert("RGBA")
            out = Image.alpha_composite(out, im)
            im = fade(blur, a["speed"])
        out = Image.alpha_composite(out, im)

    if zoom:
        # Tight on the escape wheel and the lever pivoting below it - the only
        # place the fork's phase is actually legible.
        cx, cy, m = 378.0, 400.0, 58.0
    else:
        cx, cy, r = APERTURE
        m = r + 6.0
    box = (int((cx - m) * SCALE), int((cy - m) * SCALE),
           int((cx + m) * SCALE), int((cy + m) * SCALE))
    return out.crop(box).convert("RGB"), a


def strip(samples, fork_sign, tile=300, zoom=False):
    cells = []
    for beats in samples:
        im, a = frame(beats, fork_sign, zoom)
        im = im.resize((tile, tile), Image.LANCZOS)
        d = ImageDraw.Draw(im)
        d.text((6, 4), "b%+.4f" % (beats - round(beats)), fill=(255, 240, 160))
        d.text((6, 18), "bal %+7.1f" % a["balance"], fill=(200, 220, 255))
        d.text((6, 32), "fork %+5.2f" % a["fork"], fill=(255, 180, 180))
        d.text((6, 46), "esc %+8.2f" % (a["escape"] % 360.0), fill=(180, 255, 200))
        cells.append(im)

    sheet = Image.new("RGB", (tile * len(cells), tile), (0, 0, 0))
    for i, c in enumerate(cells):
        sheet.paste(c, (i * tile, 0))
    return sheet


def main():
    transit = _check()
    os.makedirs(OUT, exist_ok=True)

    sign = 1.0
    if "--fork-sign" in sys.argv:
        sign = float(sys.argv[sys.argv.index("--fork-sign") + 1])

    if "--sub" in sys.argv:
        # Inside the transit. Nothing on a 60Hz display ever sees this; it is
        # here to check that the stones actually engage the teeth.
        half = transit / 2.0
        samples = [4.0 + t * half for t in (-1.6, -1.0, -0.5, 0.0, 0.5, 1.0, 1.6)]
        name = "transit"
    else:
        # What a 60Hz display actually samples: 7.5 frames to the beat.
        step = BEATS_PER_SECOND / 60.0
        samples = [4.0 + i * step for i in range(8)]
        name = "sixty"

    out = os.path.join(OUT, "%s%s%s.png" % (name, "-zoom" if "--zoom" in sys.argv else "", "" if sign > 0 else "-flipped"))
    strip(samples, sign, zoom="--zoom" in sys.argv).save(out)
    print("wrote", out)
    print("transit = %.4f beat = %.2f ms" % (transit, transit * 1000.0 / BEATS_PER_SECOND))
    print("balance sweeps up to %.0f deg between frames at 60fps"
          % (AMPLITUDE * 2 * math.pi * BEATS_PER_SECOND / 2.0 / 60.0))


if __name__ == "__main__":
    main()
