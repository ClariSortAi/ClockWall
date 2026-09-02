"""What the wall does BETWEEN two frames, measured on the real composited app.

    python tools/motion_check.py                      # 16 frames, 500ms apart
    python tools/motion_check.py --frames 24 --interval 250
    python tools/motion_check.py --rescore            # re-read captures/motion

Exits non-zero when the mainplate inside the aperture changes between frames,
which is the failing state the current build is in and the number a fix has to
move. It is NOT wired into render.ps1: it needs a BUILT app, and Assets/ only
reaches bin/ at build time, so it belongs after the build rather than after the
render.

WHY A SECOND INSTRUMENT. tools/placement_invariants.py --assets reads the PNGs
and says which layers carry shading that will swing when the app turns them.
This one runs the app and watches it swing. They answer different questions and
the second cannot be inferred from the first: the assets are composited,
cross-faded, scaled to whatever the wall is showing and covered by three hands,
and it is that composite the user is complaining about.

WHAT IT MEASURES, AND WHY THAT IS THE RIGHT THING. Change inside a wheel's own
rim is the wheel: teeth turning, which is the entire point of the aperture.
Change OUTSIDE every part, on the mainplate, is not. Nothing is there to move.
The plate is a static layer, painted once, and if the pixels over it are
different from one frame to the next then something that belongs to the world
is riding on a sprite that turns. That is the defect, stated as a measurement
that does not need to know the escapement's phase, the frame rate, or which
way anything is going:

    the mainplate inside the aperture must not change.

Reported per wheel by attributing each plate pixel to the nearest moving
arbor, so a fix can be seen landing on the part it was aimed at, and against a
noise floor taken from the dial - a region that is genuinely static, so
whatever it reads is what this pipeline's arithmetic costs.

HOW THE FRAMES ARE TAKEN. `ClockWall.exe --screenshot-seq N MS` (see
MainWindow.xaml.cs) - one launch, one settled window, N captures a known
interval apart, each stamped with the instant it was taken. Relaunching
`--screenshot` in a loop cannot do this job: four seconds of process start per
frame is several whole turns of the escape wheel, so consecutive frames land at
unrelated phases and nothing can be differenced.

THE SECONDS HAND IS THE ONE REAL CONTAMINANT. It sweeps through the aperture
for about seven seconds a minute, and it is the brightest moving thing on the
dial, so a pair of frames it crosses would otherwise swamp every number here.
All three hands are masked out by their own sprites, rotated to where the frame
timestamp says they were, and a pair with too much of the plate masked is
dropped rather than scored - a dropped pair is honest, a contaminated one is
not.

WRITES, all under captures/motion/:
    frame-000.png ...   the frames themselves, so a score can be re-derived
    frames.json         when each was taken, and where the face was found
    change-map.png      where the change is. This is the picture to look at.
    scores.json         this run
    scores-baseline.json  the FIRST run's, never overwritten, so a fix has a
                          before to be measured against
"""

import datetime as dt
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import placement_invariants as pi                             # noqa: E402

ROOT = pi.ROOT
ASSETS = pi.ASSETS
OUT = os.path.join(ROOT, "captures", "motion")
EXE = os.path.join(ROOT, "bin", "Release", "net10.0-windows10.0.19041.0",
                   "win-x64", "ClockWall.exe")

FACE = pi.FACE

# The window is sized to 1080x1920 physical pixels and then shrunk uniformly to
# fit the monitor, with a Viewbox scaling the design canvas by the same factor
# (MainWindow.SizeClientToDesign). So a capture's WIDTH is the whole scale
# story, and the face's 640 design units land at width/1080 pixels each. On the
# wall panel itself that factor is 1; on a laptop it is whatever fits.
DESIGN_WIDTH = 1080.0

# How much of the face the case template has to explain before this is believed
# to be the mechanical face at all. The panel cycles three faces on the C key
# and remembers the choice, so "the wall is showing the analogue face" is a
# thing that happens, and measuring an empty dial for motion would otherwise
# report a beautiful zero.
MATCH_MIN = 0.5

# Grown by this much, in face units, before a part's own disc is cut out of the
# plate. It covers the anti-aliased edge and the sub-pixel wander of a rotating
# sprite's boundary, neither of which is the shadow this is looking for.
PART_MARGIN = 2.0

# The dial ring the noise floor is read from: far enough out to clear the
# aperture, far enough in to clear the applied indices and the bezel. Nothing
# on the wall moves here except the hands, and those are masked.
NOISE_RING = (200.0, 300.0)

# A pair with more than this much of the plate under a hand tells you about the
# hand and not about the movement.
MAX_MASKED = 0.30

# How much change the mainplate is allowed, as a mean absolute difference in
# 0-255 luminance levels per pixel per frame pair. The plate is a static layer:
# with the shading where it belongs this is the compositor's rounding, which
# measures around a tenth of a level. One whole level is ten times that and
# still far below anything a person can see - and the current build reads
# three to five.
PLATE_LIMIT = 1.0

# Which parts occupy the aperture, and the radius each one reaches, in face
# units. Read off the sprites rather than typed: a part's reach is the furthest
# its own solid pixels get from the pivot the XAML turns it about, so this
# tracks the geometry instead of remembering it.
APERTURE_MOVERS = ("movement-balance.png", "movement-escape.png",
                   "movement-train.png", "movement-fork.png",
                   "movement-spring.png")

# The hands, which are masked rather than measured, and how much of each one to
# mask. The rule is not about how bright a hand is, it is about how fast:
#
#   The seconds hand moves several degrees between frames, so EVERYTHING it
#   carries has to go, its own faint cast shadow included - a 0.1-alpha shadow
#   sweeping across the plate is exactly the kind of change this instrument is
#   looking for, and it would be scored against the movement.
#
#   The hour and minute hands move a fraction of a degree across a whole
#   capture. A static shadow contributes no change at all, so masking their
#   shadows would only throw away plate for nothing. Their solid silhouettes
#   are enough.
#
# The difference is a fifth of the plate: masking every hand's full alpha
# covers 35% of it and leaves too little to measure.
HANDS = {"hand-second.png": 0.02, "hand-minute.png": 0.5, "hand-hour.png": 0.5}


# ---------------------------------------------------------------- the capture

def capture(frames, interval_ms):
    """Run the app once and bring back N stamped frames."""
    if not os.path.exists(EXE):
        raise SystemExit("No build at %s - run dotnet build first." % EXE)

    os.makedirs(OUT, exist_ok=True)
    for old in os.listdir(OUT):
        if old.startswith("frame-") and old.endswith(".png"):
            os.remove(os.path.join(OUT, old))

    base = os.path.join(OUT, "frame.png")
    proc = subprocess.run(
        [EXE, "--screenshot", base, "--screenshot-seq", str(frames), str(interval_ms)],
        capture_output=True, text=True,
        timeout=60 + frames * interval_ms / 1000.0)
    if proc.returncode != 0:
        raise SystemExit("ClockWall exited %d: %s" % (proc.returncode, proc.stderr.strip()))

    taken = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        taken.append({"index": int(parts[0]),
                      "taken": parts[1],
                      "path": parts[3]})
    if len(taken) < 2:
        raise SystemExit("Expected frames on stdout, got:\n%s" % proc.stdout)
    return taken


def _load(path):
    with Image.open(path) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.float32)
    # Rec. 601 luma. The question here is "did this pixel change", which is a
    # question about light, and a straight channel mean answers it worse.
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def locate_face(frame):
    """
    Where the 640-unit face sits in a capture, and how sure we are it is there.

    The scale is arithmetic, not a search - see DESIGN_WIDTH. Only the vertical
    offset is unknown, because the face is one item in a StackPanel whose other
    items resize with the roster. So this correlates the case's own render
    against the frame and takes the peak, then checks the horizontal answer
    against the one arithmetic already knew. If those two disagree, the thing
    being measured is not the face.
    """
    height, width = frame.shape
    scale = width / DESIGN_WIDTH
    size = int(round(FACE * scale))

    with Image.open(os.path.join(ASSETS, "case.png")) as im:
        case = np.asarray(im.convert("RGBA").resize((size, size), Image.LANCZOS),
                          dtype=np.float32)
    template = ((case[..., 0] * 0.299 + case[..., 1] * 0.587 + case[..., 2] * 0.114)
                * (case[..., 3] / 255.0))

    from scipy import signal
    t = template - template.mean()
    corr = signal.fftconvolve(frame - frame.mean(), t[::-1, ::-1], mode="valid")
    oy, ox = np.unravel_index(int(np.argmax(corr)), corr.shape)

    window = frame[oy:oy + size, ox:ox + size]
    a = window - window.mean()
    zncc = float((a * t).sum() / math.sqrt((a * a).sum() * (t * t).sum()))

    drift = abs((ox + size / 2.0) - width / 2.0)
    if zncc < MATCH_MIN or drift > 3.0:
        raise SystemExit(
            "That capture does not look like the mechanical face (match %.2f, "
            "centre %.1fpx off). ClockPanel cycles three faces on the C key and "
            "remembers the choice in %%LOCALAPPDATA%%\\ClockWall\\clock-mode.txt; "
            "it has to say 'mechanical'." % (zncc, drift))
    return float(ox), float(oy), scale, zncc


# ---------------------------------------------------------------- the regions

class Frame:
    """One capture, with the face located and the geometry in pixels."""

    def __init__(self, path, taken, ox, oy, scale):
        self.path = path
        self.taken = taken
        self.lum = _load(path)
        self.ox, self.oy, self.scale = ox, oy, scale

    def to_px(self, x, y):
        return self.ox + x * self.scale, self.oy + y * self.scale


def _disc(shape, cx, cy, r):
    ys, xs = np.ogrid[0:shape[0], 0:shape[1]]
    return (xs - cx) ** 2 + (ys - cy) ** 2 <= r * r


def _ring(shape, cx, cy, r0, r1):
    ys, xs = np.ogrid[0:shape[0], 0:shape[1]]
    d2 = (xs - cx) ** 2 + (ys - cy) ** 2
    return (d2 > r0 * r0) & (d2 <= r1 * r1)


def _reach(name, pivot):
    """How far a part's own solid pixels get from its pivot, in face units."""
    a, unit = pi._alpha(name)
    ys, xs = np.nonzero(a >= pi.SOLID_ALPHA)
    return float(np.hypot((xs + 0.5) * unit - pivot[0],
                          (ys + 0.5) * unit - pivot[1]).max())


def geometry(shape, ox, oy, scale):
    """
    Every region the scoring needs, in capture pixels.

    Returns the aperture, one disc per moving part, the plate (the aperture
    with every part cut out of it), a nearest-arbor cell per part so plate
    change can be attributed without any pixel being counted twice, and the
    dial ring the noise floor comes from.
    """
    with open(os.path.join(ROOT, "captures", "geom", "profiles.json")) as f:
        profile = json.load(f)
    ax, ay, ar = profile["aperture"]

    pivots = {name: pivot for name, pivot, _ in pi._layers() if pivot is not None}

    def px(x, y):
        return ox + x * scale, oy + y * scale

    aperture = _disc(shape, *px(ax, ay), ar * scale)

    parts, discs = {}, {}
    for name in APERTURE_MOVERS:
        pivot = pivots[name]
        reach = _reach(name, pivot)
        parts[name] = {"pivot": pivot, "reach": reach}
        discs[name] = _disc(shape, *px(*pivot), (reach + PART_MARGIN) * scale)

    plate = aperture.copy()
    for mask in discs.values():
        plate &= ~mask

    # Nearest arbor, over the plate only. The hairspring shares the balance's
    # pivot, so it is not a cell of its own - it would be the same cell.
    cells, names = {}, [n for n in APERTURE_MOVERS if n != "movement-spring.png"]
    ys, xs = np.indices(shape)
    d = np.stack([(xs - px(*parts[n]["pivot"])[0]) ** 2
                  + (ys - px(*parts[n]["pivot"])[1]) ** 2 for n in names])
    nearest = np.argmin(d, axis=0)
    for i, name in enumerate(names):
        cells[name] = plate & (nearest == i)

    noise = _ring(shape, *px(FACE / 2, FACE / 2),
                  NOISE_RING[0] * scale, NOISE_RING[1] * scale)

    return {"aperture": aperture, "parts": parts, "discs": discs,
            "plate": plate, "cells": cells, "noise": noise}


def hand_mask(shape, ox, oy, scale, when):
    """
    Where the hands are in this frame, from the clock and their own sprites.

    Rotating the actual PNG is worth the cost over a wedge of the right angle:
    it covers the counterweight, the tail past the centre and the hand's own
    cast shadow, which is displaced sideways and which a wedge misses. Angles
    come from the timestamp rather than from the pixels, so this cannot mask
    the thing it is meant to leave alone.
    """
    seconds = when.second + when.microsecond / 1e6
    minutes = when.minute + seconds / 60.0
    angles = {"hand-second.png": seconds * 6.0,
              "hand-minute.png": minutes * 6.0,
              "hand-hour.png": (when.hour % 12 + minutes / 60.0) * 30.0}
    assert set(angles) == set(HANDS)

    size = int(round(FACE * scale))
    out = np.zeros(shape, bool)
    for name, angle in angles.items():
        with Image.open(os.path.join(ASSETS, name)) as im:
            alpha = im.convert("RGBA").split()[-1].resize((size, size), Image.LANCZOS)
        # PIL turns anticlockwise, the face turns clockwise.
        turned = np.asarray(alpha.rotate(-angle, resample=Image.BILINEAR,
                                         center=(FACE / 2 * scale, FACE / 2 * scale)))
        patch = turned >= HANDS[name] * 255.0
        y0, x0 = int(round(oy)), int(round(ox))
        y1, x1 = min(y0 + size, shape[0]), min(x0 + size, shape[1])
        out[y0:y1, x0:x1] |= patch[:y1 - y0, :x1 - x0]

    from scipy import ndimage
    return ndimage.binary_dilation(out, iterations=max(1, int(round(2.0 * scale))))


# ---------------------------------------------------------------- the scoring

def score(frames, geom):
    """One row per consecutive pair, plus the medians that are the answer."""
    rows = []
    changes = []
    hands = np.zeros(frames[0].lum.shape, bool)
    for a, b in zip(frames, frames[1:]):
        d = np.abs(b.lum - a.lum)
        changes.append(d)
        masked = hand_mask(d.shape, a.ox, a.oy, a.scale, a.taken) | \
            hand_mask(d.shape, b.ox, b.oy, b.scale, b.taken)
        hands |= masked

        plate = geom["plate"] & ~masked
        covered = 1.0 - plate.sum() / max(geom["plate"].sum(), 1)
        row = {"from": a.taken.isoformat(timespec="milliseconds"),
               "dt_ms": (b.taken - a.taken).total_seconds() * 1000.0,
               "masked": float(covered),
               "dropped": bool(covered > MAX_MASKED)}
        if not row["dropped"]:
            row["plate"] = float(d[plate].mean())
            row["noise"] = float(np.median(d[geom["noise"] & ~masked]))
            row["cells"] = {}
            row["cores"] = {}
            for name in geom["cells"]:
                cell = geom["cells"][name] & ~masked
                core = geom["discs"][name] & ~masked
                row["cells"][name] = float(d[cell].mean()) if cell.any() else float("nan")
                row["cores"][name] = float(d[core].mean()) if core.any() else float("nan")
        rows.append(row)

    kept = [r for r in rows if not r["dropped"]]
    if not kept:
        raise SystemExit("Every pair was under a hand. Capture more frames.")

    def med(key, name=None):
        vals = [r[key] if name is None else r[key][name] for r in kept]
        return float(np.nanmedian(vals))

    summary = {"pairs": len(rows), "scored": len(kept),
               "plate": med("plate"), "noise": med("noise"),
               "wheels": {n: {"halo": med("cells", n), "core": med("cores", n)}
                          for n in geom["cells"]}}
    return rows, summary, changes, hands


# ---------------------------------------------------------------- the picture

def change_map(frames, changes, hands, geom, summary, path):
    """
    The artifact to actually look at: every frame's change, at once, over the
    face it happened on. Red is change. The plate glowing red IS the defect -
    nothing on the plate moves, so any red outside the drawn part circles is
    shading that is riding on a sprite the app turns.
    """
    # Everything the hands touched anywhere in the capture is dimmed rather
    # than removed: a sweeping seconds hand is by far the largest change in the
    # frame and would otherwise be the only thing anybody sees here, but
    # deleting it would hide what was excluded from the numbers.
    peak = np.max(changes, axis=0) * np.where(hands, 0.12, 1.0)
    f = frames[0]
    size = int(round(FACE * f.scale))
    y0, x0 = int(round(f.oy)), int(round(f.ox))

    base = f.lum[y0:y0 + size, x0:x0 + size]
    heat = np.clip(peak[y0:y0 + size, x0:x0 + size] * 5.0, 0, 255)
    rgb = np.stack([np.clip(base * 0.45 + heat, 0, 255),
                    base * 0.45, base * 0.45], axis=-1).astype(np.uint8)

    scale_up = 2
    im = Image.fromarray(rgb).resize((size * scale_up, size * scale_up), Image.LANCZOS)
    draw = ImageDraw.Draw(im)

    def circle(cx, cy, r, colour):
        x = (cx * f.scale) * scale_up
        y = (cy * f.scale) * scale_up
        rr = r * f.scale * scale_up
        draw.ellipse([x - rr, y - rr, x + rr, y + rr], outline=colour, width=2)

    with open(os.path.join(ROOT, "captures", "geom", "profiles.json")) as fh:
        ax, ay, ar = json.load(fh)["aperture"]
    circle(ax, ay, ar, (120, 200, 255))
    for name, part in geom["parts"].items():
        circle(part["pivot"][0], part["pivot"][1], part["reach"] + PART_MARGIN,
               (255, 235, 120))

    lines = ["mainplate change %.2f levels a frame pair (limit %.2f, "
             "dial noise floor %.2f)" % (summary["plate"], PLATE_LIMIT, summary["noise"]),
             "blue = the aperture, yellow = how far each part reaches.",
             "Red inside a yellow circle is the part moving, which is the point.",
             "Red outside them is shading moving over a plate that does not.",
             "Faded red is where a hand passed, and is masked out of every number.",
             ""]
    for name, v in sorted(summary["wheels"].items()):
        lines.append("  %-9s off-part %5.2f    within its own reach %5.2f"
                     % (name.replace("movement-", "").replace(".png", ""),
                        v["halo"], v["core"]))
    text = "\n".join(lines)
    box = draw.multiline_textbbox((14, 12), text, spacing=4)
    draw.rectangle([box[0] - 8, box[1] - 6, box[2] + 8, box[3] + 6], fill=(0, 0, 0))
    draw.multiline_text((14, 12), text, fill=(255, 255, 255), spacing=4)

    im.save(path)


# ---------------------------------------------------------------- entry point

def _parse(args, flag, default):
    return int(args[args.index(flag) + 1]) if flag in args else default


def main():
    args = sys.argv[1:]
    frames_wanted = _parse(args, "--frames", 16)
    interval = _parse(args, "--interval", 500)
    os.makedirs(OUT, exist_ok=True)

    index_path = os.path.join(OUT, "frames.json")
    if "--rescore" in args:
        with open(index_path) as f:
            taken = json.load(f)["frames"]
        print("re-scoring %d frames already in captures/motion" % len(taken))
    else:
        print("capturing %d frames %dms apart from the running app..."
              % (frames_wanted, interval))
        taken = capture(frames_wanted, interval)

    first = _load(taken[0]["path"])
    ox, oy, scale, zncc = locate_face(first)
    print("face found at (%.0f, %.0f), %.4f px per face unit, match %.2f\n"
          % (ox, oy, scale, zncc))

    frames = [Frame(t["path"], dt.datetime.fromisoformat(t["taken"]), ox, oy, scale)
              for t in taken]
    geom = geometry(first.shape, ox, oy, scale)
    rows, summary, changes, hands = score(frames, geom)

    with open(index_path, "w") as f:
        json.dump({"frames": taken,
                   "face": {"x": ox, "y": oy, "scale": scale, "match": zncc}}, f, indent=2)

    print("%d pairs, %d scored (%d dropped as too far under a hand)"
          % (summary["pairs"], summary["scored"], summary["pairs"] - summary["scored"]))
    print("\n%-12s %10s %10s %8s" % ("", "off-part", "inside rim", "ratio"))
    for name, v in sorted(summary["wheels"].items()):
        short = name.replace("movement-", "").replace(".png", "")
        ratio = v["halo"] / v["core"] if v["core"] else float("nan")
        print("%-12s %10.2f %10.2f %8.2f" % (short, v["halo"], v["core"], ratio))

    print("\nmainplate inside the aperture   %.2f levels per pair" % summary["plate"])
    print("dial, which nothing moves on     %.2f levels per pair (the noise floor)"
          % summary["noise"])

    change_map(frames, changes, hands, geom, summary,
               os.path.join(OUT, "change-map.png"))

    result = {"when": dt.datetime.now().isoformat(timespec="seconds"),
              "interval_ms": interval,
              "limit": PLATE_LIMIT,
              "summary": summary,
              "pairs": rows}
    with open(os.path.join(OUT, "scores.json"), "w") as f:
        json.dump(result, f, indent=2)

    baseline_path = os.path.join(OUT, "scores-baseline.json")
    if not os.path.exists(baseline_path):
        with open(baseline_path, "w") as f:
            json.dump(result, f, indent=2)
        print("\nbaseline written to captures/motion/scores-baseline.json "
              "(this file is never overwritten - it is the before)")
    else:
        with open(baseline_path) as f:
            base = json.load(f)
        print("\nagainst the baseline taken %s: mainplate %.2f -> %.2f"
              % (base.get("when", "on the first run"),
                 base["summary"]["plate"], summary["plate"]))
        for name, v in sorted(summary["wheels"].items()):
            print("    %-9s off-part %5.2f -> %5.2f"
                  % (name.replace("movement-", "").replace(".png", ""),
                     base["summary"]["wheels"][name]["halo"], v["halo"]))

    print("captures/motion/change-map.png is the picture")

    failed = summary["plate"] > PLATE_LIMIT
    print("\n[%s] the mainplate inside the aperture changes by %.2f levels a "
          "frame pair; nothing on it moves, so the limit is %.2f"
          % ("FAIL" if failed else "ok  ", summary["plate"], PLATE_LIMIT))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
