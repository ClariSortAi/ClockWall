"""The dial's printing, as a mask for the real-time face.

    python tools/dial_print.py        # -> Assets/dial-print.png

The live renderer draws the sunburst, the minute track and everything else in
the shader, because those are light and light has to move. Lettering is not
light: it is a pad print, matte ink sitting on the lacquer, and its shape is
the one thing on the dial that IS a picture. So it is rendered here once, as a
single-channel coverage mask in face units, and the dial shader lays ink down
wherever the mask is set. Same font, same lines, same sizes and same positions
as dial_render.py gives the sprite face, so the two faces say the same thing.

THE BEAT IS READ, NOT TYPED - the same rule dial_render follows. The signature
line comes from escapement_geometry.VPH, so a dial that disagrees with its own
movement cannot be produced by this file.
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

SIZE = 1024                 # pixels across the 640-unit face
SCALE = SIZE / 640.0
CX = SIZE / 2.0


def line(mask, s, y_units, size_pt, tracking, strength):
    try:
        font = ImageFont.truetype("segoeui.ttf", int(size_pt * SCALE))
    except OSError:
        font = ImageFont.load_default()
    d = ImageDraw.Draw(mask)
    widths = [d.textlength(ch, font=font) for ch in s]
    total = sum(widths) + tracking * SCALE * (len(s) - 1)
    x = CX - total / 2
    for ch, w in zip(s, widths):
        d.text((x, y_units * SCALE), ch, font=font, fill=strength)
        x += w + tracking * SCALE


def main():
    sys.path.insert(0, HERE)
    import escapement_geometry as eg
    signature = "%.3g Hz  ·  %s vph" % (eg.VPH / 7200.0, format(eg.VPH, ","))

    mask = Image.new("L", (SIZE, SIZE), 0)
    # Two strengths: the name at full ink, the signature a little lighter,
    # which is how dial_render.py tones them (232,238,250 against 198,210,230).
    line(mask, "CW  ·  OPENWORKED", 176, 25, 2.2, 255)
    line(mask, signature, 214, 17, 1.6, 200)
    mask = mask.filter(ImageFilter.GaussianBlur(0.35 * SCALE))

    out = os.path.join(ROOT, "Assets", "dial-print.png")
    mask.save(out)
    print("wrote", out, mask.size)


if __name__ == "__main__":
    main()
