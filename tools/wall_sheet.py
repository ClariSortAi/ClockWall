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

AND WITH ONE NUMBER ATTACHED TO IT, because "the aperture pulls the eye" is
the kind of statement three people will read three ways. The aperture/dial
luminance ratio below turns it into arithmetic: if the opening is brighter
than the dial around it, no amount of finish inside the opening will stop it
being the first thing anybody sees from the doorway. Exits non-zero when it
is, so this file is a gate and not only a picture.

Writes captures/wall/wall-sheet.png, the capture it used, and
captures/wall/ratio-regions.png showing exactly which pixels the ratio was
taken over.
"""

import datetime as dt
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import case_geometry as cg                                    # noqa: E402
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

# ------------------------------------------------------- the aperture's weight
#
# WHAT IS MEASURED. Mean Rec. 601 luma over the aperture disc, divided by the
# same over a band of dial immediately outside it. Both taken from the
# COMPOSITED capture rather than from Assets/, because what decides where the
# eye lands is the finished picture: the plate seen through the dial's opening,
# under the rehaut's shadow, with the hands over it.
#
# WHY A BAND AND NOT THE WHOLE DIAL. The eye reads contrast locally. An
# aperture is loud or quiet against the dial TOUCHING it, not against the
# average of a face whose far side it is nowhere near - and the far side of
# this dial carries the sunburst's own bright quadrant, which would drag the
# denominator around for reasons that have nothing to do with the opening.
#
# WHY A MEAN AND NOT SOMETHING ROBUST. The hands cross both regions and they
# are bright, so a mean is contaminated. It is contaminated in BOTH terms and
# the ratio divides most of it out: on the capture this was written against,
# mean and median disagreed by 1.2 per cent (1.175 against 1.189). The mean is
# the number the acceptance is stated in and the median is printed beside it,
# so a run where the two part company is visible rather than silent.
RATIO_MAX = 1.0

# The band, as radii about the aperture centre in face units. Inside edge is
# clear of the rehaut (which finishes at REHAUT_OUT) so the polished ring's own
# highlight lands in neither region; outside edge is clipped to the dial, which
# is what stops it running off the bottom of the face and onto the bezel.
DIAL_BAND = (cg.REHAUT_OUT + 12.0, cg.REHAUT_OUT + 72.0)

# The same measurement on the reference photographs, which is what says whether
# RATIO_MAX is a real target or a number somebody liked. Each entry is
# (aperture cx, cy, r; dial band r0, r1) in that photo's own pixels, read off
# the image by hand once - the openings are not concentric with their dials and
# the Tissot's is not even a circle, so there is nothing to derive them from.
# captures/wall/ratio-regions.png draws every one of them over its photo, which
# is how a reader checks these numbers land where they claim to.
REF_REGIONS = {
    "08": (661, 481, 75, 95, 150),      # Orient Bambino, round opening at 9
    "10": (815, 730, 100, 190, 250),    # Tissot Gentleman, heart at 10-11
}


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


def _luma(im):
    a = np.asarray(im.convert("RGB"), dtype=np.float32)
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def _masks(shape, cx, cy, r, r0, r1):
    ys, xs = np.ogrid[0:shape[0], 0:shape[1]]
    d2 = (xs - cx) ** 2 + (ys - cy) ** 2
    return d2 <= r * r, (d2 > r0 * r0) & (d2 <= r1 * r1)


def measure(im, region, clip=None):
    """Aperture mean over dial mean, on one image, over one pair of regions."""
    lum = _luma(im)
    ap, band = _masks(lum.shape, *region)
    if clip is not None:
        band = band & clip
    a, d = lum[ap], lum[band]
    return {"aperture": float(a.mean()), "dial": float(d.mean()),
            "ratio": float(a.mean() / d.mean()),
            "median_ratio": float(np.median(a) / np.median(d)),
            "px": (int(ap.sum()), int(band.sum()))}


def face_region():
    """
    Where the opening and its band of dial are, in the 640px face crop.

    The aperture comes out of profiles.json rather than being typed here: it is
    what the render actually cut the hole at, and it has moved once already.
    """
    with open(os.path.join(ROOT, "captures", "geom", "profiles.json")) as f:
        ax, ay, ar = json.load(f)["aperture"]
    u = WALL_PX / mc.FACE                       # face units to crop pixels
    return (ax * u, ay * u, ar * u, DIAL_BAND[0] * u, DIAL_BAND[1] * u)


def _dial_clip(shape):
    """The printed dial, which is what keeps the band off the bezel and the
    black outside the case as the band runs past the bottom of the face."""
    u = WALL_PX / mc.FACE
    ys, xs = np.ogrid[0:shape[0], 0:shape[1]]
    return ((xs - cg.CENTRE[0] * u) ** 2 + (ys - cg.CENTRE[1] * u) ** 2
            <= (cg.DIAL_R * u) ** 2)


def face_ratio(face):
    region = face_region()
    return measure(face, region, clip=_dial_clip((WALL_PX, WALL_PX))), region


def ref_ratios():
    out = {}
    for name, path in refs(set(REF_REGIONS)):
        key = name.split("-")[0]
        with Image.open(path) as im:
            out[key] = (path, measure(im.convert("RGB"), REF_REGIONS[key]))
    return out


def regions_image(face, region, ref_measured, box=380):
    """
    The masks, drawn over what they were measured on.

    A ratio nobody can check is a ratio nobody should believe, and these
    circles are hand-placed on the photographs. This is the picture that says
    they sit where the text claims.
    """
    panels = [("ours", face, region)]
    for key in sorted(ref_measured):
        path, _ = ref_measured[key]
        with Image.open(path) as im:
            panels.append((key, im.convert("RGB"), REF_REGIONS[key]))

    label = _font(16)
    sheet = Image.new("RGB", (len(panels) * (box + GAP) + GAP, box + GAP + 26),
                      (18, 18, 20))
    draw = ImageDraw.Draw(sheet)
    for i, (tag, im, region) in enumerate(panels):
        cx, cy, r, r0, r1 = region
        # The PIXELS, tinted, rather than circles drawn over them. Our own band
        # is clipped to the dial and so is a crescent, not the ring an outline
        # would promise - and a picture that promises the wrong region is worse
        # than no picture.
        ap, band = _masks((im.height, im.width), *region)
        if tag == "ours":
            band = band & _dial_clip((im.height, im.width))
        a = np.asarray(im, dtype=np.float32)
        for mask, tint in ((ap, (255, 60, 60)), (band, (0, 190, 255))):
            a[mask] = a[mask] * 0.68 + np.array(tint, dtype=np.float32) * 0.32
        im = Image.fromarray(a.clip(0, 255).astype(np.uint8))
        half = r1 * 1.12
        crop = im.crop((int(cx - half), int(cy - half),
                        int(cx + half), int(cy + half))).resize((box, box),
                                                                Image.LANCZOS)
        x = GAP + i * (box + GAP)
        sheet.paste(crop, (x, GAP))
        draw.text((x, GAP + box + 4), tag, font=label, fill=(210, 210, 215))
    return sheet


def refs(wanted):
    out = []
    for name in sorted(os.listdir(REFS)):
        if name.endswith(".md"):
            continue
        if name.split("-")[0] in wanted:
            out.append((name, os.path.join(REFS, name)))
    return out


def sheet(face, ref_paths, source, zncc, ours, ref_measured):
    title = _font(22)
    label = _font(16)
    small = _font(13)

    left_width = WALL_PX
    right_width = len(ref_paths) * (WALL_PX + GAP)
    width = MARGIN * 2 + left_width + GAP + right_width
    height = MARGIN * 3 + 60 + WALL_PX + int(WALL_PX * 0.5) + 60

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

    passed = ours["ratio"] < RATIO_MAX
    draw.text((MARGIN, MARGIN + 38),
              "aperture / dial luminance  %.3f  (%s < %.2f)   %s"
              % (ours["ratio"], "pass" if passed else "FAIL", RATIO_MAX,
                 "   ".join("ref %s %.3f" % (k, v["ratio"])
                           for k, (_p, v) in sorted(ref_measured.items()))),
              font=small, fill=(120, 220, 130) if passed else (240, 120, 110))

    top = MARGIN + 72
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

    ours, region = face_ratio(face)
    ref_measured = ref_ratios()

    out = os.path.join(OUT, "wall-sheet.png")
    sheet(face, ref_paths, source, zncc, ours, ref_measured).save(out)
    regions = os.path.join(OUT, "ratio-regions.png")
    regions_image(face, region, ref_measured).save(regions)

    print("%s\n  from %s\n  against %s"
          % (os.path.relpath(out, ROOT), os.path.relpath(source, ROOT),
             ", ".join(n for n, _ in ref_paths)))
    print("\naperture / dial luminance, from the composited capture")
    print("  ours      aperture %6.1f   dial %6.1f   ratio %.3f  "
          "(median %.3f, %d / %d px)"
          % (ours["aperture"], ours["dial"], ours["ratio"],
             ours["median_ratio"], ours["px"][0], ours["px"][1]))
    for key, (_path, m) in sorted(ref_measured.items()):
        print("  ref %-5s aperture %6.1f   dial %6.1f   ratio %.3f  (median %.3f)"
              % (key, m["aperture"], m["dial"], m["ratio"], m["median_ratio"]))
    print("  regions drawn at %s" % os.path.relpath(regions, ROOT))

    if ours["ratio"] >= RATIO_MAX:
        print("\nFAIL  the opening is brighter than the dial around it "
              "(%.3f, wanted < %.2f). Every reference dial in captures/refs has "
              "its aperture DARKER than its dial - it is a recess, not a lamp."
              % (ours["ratio"], RATIO_MAX))
        return 1
    print("\nok  %.3f < %.2f, against %s in the references"
          % (ours["ratio"], RATIO_MAX,
             " and ".join("%.3f" % m["ratio"] for _k, (_p, m)
                          in sorted(ref_measured.items()))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
