"""The crystal's wear: one hairline scratch and a little dust, as a mask.

    python tools/crystal_wear.py        # -> Assets/crystal-wear.png

WHY. A spotless crystal is the thing that reads as rendered. A watch that
has been worn has, at the least, one fine arc scratched into the sapphire
where a cuff or a door frame caught it, and a few motes of dust that the
last wipe missed. ART-DIRECTION.md asks for the crystal to be subtle; the
defect is ever so slight, but it is there, and it catches the key light
when the rig drifts past it, which is exactly what a scratch does.

The mask is in face units like the dial print (1024 px over the 640-unit
face, the same faceUv the dial shader uses), so the crystal shader finds
it by the world position under the dome:
  R  the scratch: coverage, a Gaussian across a stroke a few hundredths
     of a millimetre wide
  G  dust: specks, one to two pixels, a few of them
  B  the scratch's direction along the stroke, angle / pi, so the shader
     can light it as a groove (bright where the half-vector is across it)
The scratch's place and shape are chosen here once and are part of the
face's design; a random scratch would move every time this ran.
"""

import math
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "Assets", "crystal-wear.png")

SIZE = 1024
SCALE = SIZE / 640.0          # px per face unit
U_MM = 0.08488                # mm per face unit (case_solids.U)
PX_MM = SCALE / U_MM          # px per mm, about 18.8

# The scratch: an arc down the lower right of the crystal, over the
# sunburst and clear of the open heart - the first one crossed the heart
# and read as a stray hand among the wheels. Centre and radius in mm from
# the dial centre, x right, y up; start and end angles in degrees.
SCRATCH = dict(centre=(34.0, -14.0), radius=26.0, a0=160.0, a1=195.0, width_mm=0.045, depth=0.75)
# A second, shorter one crossing it: the way scratches come in pairs off
# one edge, and a lone perfect arc looks placed.
SCRATCH2 = dict(centre=(-6.0, 22.5), radius=8.0, a0=190.0, a1=228.0, width_mm=0.03, depth=0.45)

DUST = [  # (x mm, y mm, radius px, brightness)
    (6.2, 9.8, 1.0, 0.7), (-11.4, -3.1, 1.3, 0.8), (14.9, -12.6, 0.9, 0.6), (-2.3, -16.8, 1.1, 0.75),
    (18.5, 6.4, 0.8, 0.55), (-17.9, 7.2, 1.4, 0.85), (3.6, -7.9, 0.7, 0.5), (-8.8, 18.6, 1.0, 0.65),
    (10.7, 16.1, 0.8, 0.6), (-15.2, -13.4, 1.2, 0.7),
]


def to_px(x_mm, y_mm):
    return SIZE / 2 + x_mm * PX_MM, SIZE / 2 - y_mm * PX_MM


def stroke(cov, ang, s):
    cx, cy = s["centre"]
    sigma = s["width_mm"] * PX_MM / 2.0
    n = int(abs(s["a1"] - s["a0"]) * s["radius"] * PX_MM / 20.0) + 50
    ys, xs = np.mgrid[0:SIZE, 0:SIZE]
    for k in range(n + 1):
        t = k / n
        a = math.radians(s["a0"] + (s["a1"] - s["a0"]) * t)
        x = cx + s["radius"] * math.cos(a)
        y = cy + s["radius"] * math.sin(a)
        px, py = to_px(x, y)
        if not (0 <= px < SIZE and 0 <= py < SIZE):
            continue
        # A scratch is deepest in its middle and fades at both ends.
        fade = math.sin(math.pi * t) ** 0.5
        # Depth wanders a little along the stroke, as a real one does.
        wander = 0.75 + 0.25 * math.sin(t * 37.0) * math.sin(t * 11.0)
        x0, x1 = int(px) - 4, int(px) + 5
        y0, y1 = int(py) - 4, int(py) + 5
        d2 = (xs[y0:y1, x0:x1] - px) ** 2 + (ys[y0:y1, x0:x1] - py) ** 2
        g = np.exp(-d2 / (2 * sigma * sigma)) * s["depth"] * fade * wander
        cov[y0:y1, x0:x1] = np.maximum(cov[y0:y1, x0:x1], g)
        # Direction along the stroke, in the face's x-right, y-up frame.
        tangent = math.atan2(math.cos(a), -math.sin(a)) % math.pi
        mask = g > 0.02
        ang[y0:y1, x0:x1][mask] = tangent / math.pi


def main():
    cov = np.zeros((SIZE, SIZE), np.float32)
    ang = np.zeros((SIZE, SIZE), np.float32)
    dust = np.zeros((SIZE, SIZE), np.float32)
    stroke(cov, ang, SCRATCH)
    stroke(cov, ang, SCRATCH2)
    ys, xs = np.mgrid[0:SIZE, 0:SIZE]
    for x_mm, y_mm, r, b in DUST:
        px, py = to_px(x_mm, y_mm)
        d2 = (xs - px) ** 2 + (ys - py) ** 2
        dust = np.maximum(dust, np.exp(-d2 / (2 * r * r)) * b)
    rgb = np.stack([cov, dust, ang], axis=-1)
    Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8), "RGB").save(OUT)
    print("  scratch %.0f px long, %.3f mm wide; %d motes; wrote %s" % (
        math.radians(abs(SCRATCH["a1"] - SCRATCH["a0"])) * SCRATCH["radius"] * PX_MM, SCRATCH["width_mm"], len(DUST), OUT))


if __name__ == "__main__":
    main()
