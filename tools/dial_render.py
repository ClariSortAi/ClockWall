"""Generates the dial's albedo texture for Blender.

    python tools/dial_render.py

WHAT THIS USED TO DO, AND WHY IT STOPPED. This file used to draw the entire
face: case, dial, applied indices, hands, and a painted-on highlight for each of
them. That was the same mistake the escapement had already been rescued from,
just moved outward - a case rendered as a grey ring with a gradient reads as
moulded plastic, and an index with a light half and a dark half cannot catch a
highlight or drop a shadow, because it is a drawing of an index rather than a
solid.

The case, the bezel and the indices are now modelled in case_geometry.py and
rendered in the same Blender scene, by the same lights, as the movement. One
light direction across the whole face is what makes it look like one object
photographed once instead of two pictures pasted together.

WHAT IS LEFT HERE IS THE ONE THING GEOMETRY IS BAD AT. A soleil dial is not a
shape, it is a FINISH: metal brushed radially, so fine that the pattern is a
texture and never a model. PIL is exactly the right tool for that and Blender is
exactly the wrong one. So this writes a flat colour image and Blender maps it
onto the dial disc and decides how it catches the light.

Output: Assets/dial-texture.png, 1280x1280, covering the 640x640 face box.
"""

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SS = 2                     # supersample: face px -> image px
W = 640 * SS
CX = CY = 320.0 * SS

# Light comes from the upper left and never moves. THIS NUMBER IS SHARED WITH
# THE RENDER - blender_movement.py puts its key at a bearing that matches, and
# if the two ever disagree the dial's own flare will point one way while every
# cast shadow points the other, which is the sort of wrongness people see
# without being able to name.
LIGHT_DEG = 315.0

CHAPTER_R = 268.0 * SS     # the printed track sits just inside the indices

# How dark the dial is allowed to get across the brushing. Zero gives the black
# cross; one gives a flat disc with no sunburst at all.
LOBE_FLOOR = 0.42


def polar(cx, cy, deg, r):
    a = math.radians(deg)
    return (cx + r * math.sin(a), cy - r * math.cos(a))


def mask(size, draw_fn, blur=0.6):
    m = Image.new("L", size, 0)
    draw_fn(ImageDraw.Draw(m))
    return m.filter(ImageFilter.GaussianBlur(blur * SS)) if blur else m


def paste(base, colour_layer, m):
    base.paste(colour_layer, (0, 0), m)


def flat(size, rgb):
    return Image.new("RGB", size, tuple(rgb))


def sunburst(size, r_out, shadow, mid, hot, streak=0.030, lobe_power=1.05, seed=7):
    """
    A soleil (sunburst) dial.

    Two things make it, and both are physical. The metal is brushed RADIALLY, so
    every scratch runs from the centre outward - which means the noise has to be
    a function of angle alone and constant along the radius. And because those
    scratches all lie the same way, the dial has two bright lobes opposite each
    other and two dark ones at ninety degrees, sweeping as you tilt it. That
    swing from near-white to near-black across one disc is the whole effect, and
    it is why a sunburst dial looks alive and a flat one looks like paint.

    The lobes are baked in here rather than left to Blender because they are an
    ANISOTROPIC reflection - the dial is bright along the brushing and dark
    across it - and a flat albedo cannot tell a renderer that. Baking is honest
    for a part that never moves, and the bearing matches the key light, so the
    real specular Blender adds on top lands on the same side.
    """
    h, w = size[1], size[0]
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = x - CX, y - CY
    r = np.hypot(dx, dy)
    th = np.arctan2(dy, dx)

    # The brush: fine angular noise, identical at every radius. One line, and it
    # is the difference between brushed metal and a gradient.
    n = 32768
    rng = np.random.default_rng(seed)
    grain = rng.normal(0.0, 1.0, n)
    k = np.ones(3, np.float32) / 3.0
    grain = np.convolve(np.r_[grain[-2:], grain, grain[:2]], k, "same")[2:-2]
    brush = grain[((th + np.pi) / (2 * np.pi) * n).astype(np.int32) % n]
    # Every scratch converges on the centre, so without this the middle is a
    # spike of noise rather than metal.
    brush = brush * np.clip(r / (0.22 * r_out), 0.0, 1.0)

    # A FLOOR UNDER THE LOBES, which matters more than it looks. Taken raw,
    # |cos| reaches exactly zero twice, so the two dark axes crossed the dial as
    # hard black bands and met at the centre in an X that read as a printing
    # fault rather than as a finish. A real soleil dial darkens across the
    # brushing; it does not go out. The floor keeps the whole sweep and drops
    # the crossing.
    flare = np.abs(np.cos(th - math.radians(LIGHT_DEG - 90.0))) ** lobe_power
    lobe = LOBE_FLOOR + (1.0 - LOBE_FLOOR) * flare

    # Slight darkening toward the rim: a dial is very slightly domed, and the
    # falloff is most of what stops it reading as a flat sticker.
    vign = np.clip(1.0 - 0.14 * (r / r_out) ** 2.2, 0.0, 1.0)

    t = np.clip(lobe * vign + brush * streak, 0.0, 1.0)

    shadow, mid, hot = (np.array(c, np.float32) for c in (shadow, mid, hot))
    lo = shadow + (mid - shadow) * np.clip(t / 0.55, 0, 1)[..., None]
    hi = mid + (hot - mid) * np.clip((t - 0.55) / 0.45, 0, 1)[..., None]
    rgb = np.where(t[..., None] < 0.55, lo, hi)
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))


def draw_track(img, ink):
    """The printed minute track: sixty marks, heavier on the hours."""
    size = img.size
    for i in range(60):
        major = i % 5 == 0
        w, ln = (3.0 if major else 1.5) * SS, (17.0 if major else 10.0) * SS
        a = i * 6.0
        p0 = polar(CX, CY, a, CHAPTER_R)
        p1 = polar(CX, CY, a, CHAPTER_R + ln)
        paste(img, flat(size, ink), mask(
            size,
            lambda d, p0=p0, p1=p1, w=w: d.line([p0, p1], fill=255, width=int(round(w))),
            0.5))


def text(img, s, y, size_pt, rgb, tracking=0.0):
    """
    Dial printing, letter-spaced by hand.

    Sized considerably larger than it was. Dial text on a real watch is tiny
    because you hold the watch at arm's length; this one hangs on a wall, and at
    that distance the old line read as a smudge rather than as words.
    """
    from PIL import ImageFont
    try:
        font = ImageFont.truetype("segoeui.ttf", int(size_pt * SS))
    except OSError:
        font = ImageFont.load_default()

    layer = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(layer)
    widths = [d.textlength(ch, font=font) for ch in s]
    total = sum(widths) + tracking * SS * (len(s) - 1)
    x = CX - total / 2
    for ch, w in zip(s, widths):
        d.text((x, y * SS), ch, font=font, fill=255)
        x += w + tracking * SS
    paste(img, flat(img.size, rgb), layer.filter(ImageFilter.GaussianBlur(0.35 * SS)))


def render():
    size = (W, W)
    img = sunburst(size, 300.0 * SS,
                   shadow=(9, 17, 42), mid=(28, 56, 118), hot=(112, 160, 226))

    ink = (232, 238, 250)
    draw_track(img, ink)

    # Both lines sit in the upper half, clear of the opening at six.
    text(img, "CW  ·  OPENWORKED", 176, 25, ink, tracking=2.2)
    text(img, "4 Hz  ·  28,800 vph", 214, 17, (198, 210, 230), tracking=1.6)
    return img


if __name__ == "__main__":
    os.makedirs("Assets", exist_ok=True)
    out = render()
    out.save("Assets/dial-texture.png")
    print("wrote Assets/dial-texture.png", out.size)
