"""Composites the rendered assets into one face, at a chosen time.

    python tools/face_sheet.py [HH:MM:SS]

The layers and their paint order are the same ones OpenworkedFace.xaml uses, so
this is a faithful preview of what the control will show - without a build, a
deploy and a screenshot for every look.
"""
import sys
from PIL import Image

LAYERS = ["movement-base", "movement-train", "movement-escape", "movement-fork",
          "movement-spring", "movement-balance", "movement-cock", "case"]
RES = 1920
C = RES // 2


def compose(h, m, s):
    out = Image.new("RGBA", (RES, RES), (14, 14, 18, 255))
    for n in LAYERS:
        out = Image.alpha_composite(out, Image.open("Assets/%s.png" % n).convert("RGBA"))
    for n, ang in (("hour", (h % 12 + m / 60.0) * 30.0),
                   ("minute", m * 6.0 + s * 0.1),
                   ("second", s * 6.0),
                   ("cap", 0.0)):
        im = Image.open("Assets/hand-%s.png" % n).convert("RGBA")
        if ang:
            im = im.rotate(-ang, resample=Image.BICUBIC, center=(C, C))
        out = Image.alpha_composite(out, im)
    return out


if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else "10:09:33"
    h, m, s = (int(v) for v in t.split(":"))
    img = compose(h, m, s)
    img.save("captures/face-full.png")
    img.resize((820, 820), Image.LANCZOS).save("captures/face-small.png")
    print("wrote captures/face-full.png and face-small.png at", t)
