"""The sheet the face is judged from: our watch at wall scale, beside real ones.

    python tools/wall_sheet.py                       # capture the app, then build
    python tools/wall_sheet.py captures/app-mech.png  # use a capture you have
    python tools/wall_sheet.py --refs 08,10,04

WHY A SHEET AND NOT A SCREENSHOT. Every judgement about this face so far has
been made from a crop at render resolution, and every one of them has been
wrong in the same direction: things that read beautifully at 1920px across
disappear or turn to mush at the 640 the wall actually gives them, and a
choice that looks bold in a crop looks like a smudge from the sofa. The
aperture is a fifth of the dial. Nobody stands with their nose against it.

So the sheet shows the same face three times - at the wall's own pixel scale,
at half of it, and at a quarter - because those are roughly what the face looks
like from in front of the panel, from across the room, and from the doorway. A
detail that survives all three is a detail worth rendering. One that only reads
at 100% is costing render time to be invisible.

AND BESIDE REAL WATCHES, at the same size, because "does this look like a
photograph of a watch" is not a question anybody can answer against a blank
background. captures/refs/ has front-on open-heart and skeleton dials collected
for exactly this comparison; see its NOTES.md for what each one shows. The
reference is scaled to the same box, so the comparison is like for like.

Writes captures/wall/wall-sheet.png, and the capture it used beside it.
"""

import datetime as dt
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import motion_check as mc                                     # noqa: E402

ROOT = mc.ROOT
OUT = os.path.join(ROOT, "captures", "wall")
REFS = os.path.join(ROOT, "captures", "refs")

# The wall's own scale. The design canvas gives the face 640 pixels on the
# 1080x1920 panel, so 640 is 100% however small the window was on the machine
# that took the capture - the capture gets rescaled to it rather than the
# other way about, or a sheet built on a laptop would be judging a different
# picture from a sheet built on the wall.
WALL_PX = 640

STEPS = ((1.0, "100%  the wall, from in front of it"),
         (0.5, "50%  across the room"),
         (0.25, "25%  from the doorway"))

# Front-on, dial-side, open-heart or skeleton. The caseback shots in refs/ are
# deliberately not here: this face looks at the front of a watch, which is the
# question that folder settled (see HANDOVER-REALISM.md).
DEFAULT_REFS = ("08", "10", "04")

MARGIN = 28
GAP = 20


def _font(size):
    for name in ("segoeui.ttf", "arial.ttf"):
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def capture():
    """One screenshot of the running app, into captures/wall/."""
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "capture.png")
    proc = subprocess.run([mc.EXE, "--screenshot", path],
                          capture_output=True, text=True, timeout=90)
    if proc.returncode != 0:
        raise SystemExit("ClockWall exited %d: %s" % (proc.returncode, proc.stderr.strip()))
    return path


def face_of(path):
    """The watch, cut out of a full-wall capture and put back at wall scale."""
    lum = mc._load(path)
    ox, oy, scale, zncc = mc.locate_face(lum)
    size = int(round(mc.FACE * scale))
    with Image.open(path) as im:
        crop = im.convert("RGB").crop((int(round(ox)), int(round(oy)),
                                       int(round(ox)) + size, int(round(oy)) + size))
    return crop.resize((WALL_PX, WALL_PX), Image.LANCZOS), zncc


def _fit(path, box):
    """A reference photo, cropped square about its centre and fitted to box."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        side = min(im.size)
        left = (im.width - side) // 2
        top = (im.height - side) // 2
        return im.crop((left, top, left + side, top + side)).resize((box, box), Image.LANCZOS)


def refs(wanted):
    out = []
    for name in sorted(os.listdir(REFS)):
        if name.endswith(".md"):
            continue
        if name.split("-")[0] in wanted:
            out.append((name, os.path.join(REFS, name)))
    return out


def sheet(face, ref_paths, source, zncc):
    title = _font(22)
    label = _font(16)
    small = _font(13)

    left_width = WALL_PX
    right_width = len(ref_paths) * (WALL_PX + GAP)
    width = MARGIN * 2 + left_width + GAP + right_width
    height = MARGIN * 3 + 40 + WALL_PX + int(WALL_PX * 0.5) + 60

    im = Image.new("RGB", (width, height), (18, 18, 20))
    draw = ImageDraw.Draw(im)

    draw.text((MARGIN, MARGIN - 6),
              "ClockWall, at wall scale, beside the real thing   -   %s"
              % dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
              font=title, fill=(235, 235, 235))
    draw.text((MARGIN, MARGIN + 22),
              "from %s (face matched %.2f). Nothing here is a crop at render "
              "resolution: this is the size the wall gives it."
              % (os.path.relpath(source, ROOT), zncc),
              font=small, fill=(150, 150, 155))

    top = MARGIN + 52
    # The three scales, down the left: full size first, then the smaller two
    # side by side underneath it, each on the ground the wall would give it.
    draw.rectangle([MARGIN, top, MARGIN + WALL_PX, top + WALL_PX], fill=(0, 0, 0))
    im.paste(face, (MARGIN, top))
    draw.text((MARGIN, top + WALL_PX + 6), STEPS[0][1], font=label, fill=(210, 210, 215))

    y = top + WALL_PX + 30
    x = MARGIN
    for factor, caption in STEPS[1:]:
        side = int(WALL_PX * factor)
        im.paste(face.resize((side, side), Image.LANCZOS), (x, y))
        draw.text((x, y + side + 6), caption, font=label, fill=(210, 210, 215))
        x += side + GAP * 2

    x = MARGIN + left_width + GAP
    for name, path in ref_paths:
        im.paste(_fit(path, WALL_PX), (x, top))
        draw.text((x, top + WALL_PX + 6), name, font=label, fill=(210, 210, 215))
        # And the same photo at the two smaller scales, so the comparison is
        # made at each distance rather than only at the flattering one.
        yy, xx = top + WALL_PX + 30, x
        for factor, _ in STEPS[1:]:
            side = int(WALL_PX * factor)
            im.paste(_fit(path, side), (xx, yy))
            xx += side + GAP * 2
        x += WALL_PX + GAP

    return im


def main():
    args = sys.argv[1:]
    wanted = set(DEFAULT_REFS)
    if "--refs" in args:
        wanted = set(args[args.index("--refs") + 1].split(","))
        args = args[:args.index("--refs")] + args[args.index("--refs") + 2:]

    source = args[0] if args else capture()
    os.makedirs(OUT, exist_ok=True)

    face, zncc = face_of(source)
    ref_paths = refs(wanted)
    if not ref_paths:
        raise SystemExit("No reference photos matched %s in captures/refs" % sorted(wanted))

    out = os.path.join(OUT, "wall-sheet.png")
    sheet(face, ref_paths, source, zncc).save(out)
    print("%s\n  from %s\n  against %s"
          % (os.path.relpath(out, ROOT), os.path.relpath(source, ROOT),
             ", ".join(n for n, _ in ref_paths)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
