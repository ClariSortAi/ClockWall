"""What the wall does BETWEEN two frames, measured on the real composited app.

    python tools/motion_check.py                      # 16 frames, 500ms apart
    python tools/motion_check.py --frames 24 --interval 250
    python tools/motion_check.py --rescore            # re-read captures/motion
    python tools/motion_check.py --balance            # the balance's waveform

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

--balance IS A DIFFERENT QUESTION ON THE SAME FRAMES. The plate score above
asks whether anything moves that should not. That one asks whether the balance
moves the way it should: it is the only part in the aperture that swings rather
than steps, and a swing is the one thing a screen grab cannot watch directly at
286 ms an oscillation. It does not try to. Every frame carries the instant it
was taken and the movement is a pure function of the wall clock, so folding the
stamps into beat phase reconstructs one oscillation out of frames taken at any
rate at all. See the section at the bottom of this file.

WRITES, all under captures/motion/:
    frame-000.png ...   the frames themselves, so a score can be re-derived
    frames.json         when each was taken, and where the face was found
    change-map.png      where the change is. This is the picture to look at.
    scores.json         this run
    scores-baseline.json  the FIRST run's, never overwritten, so a fix has a
                          before to be measured against

and from --balance, which keeps its own frames so the two never tread on each
other's baselines:
    balance/            its frames and their stamps
    balance-waveform.png  both waveforms against one folded oscillation
    balance-frames.png  the angle estimator checked against the pixels by eye
    balance.json, balance-baseline.json   same bargain as the pair above
"""

import datetime as dt
import json
import math
import os
import re
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

def capture(frames, interval_ms, out=None):
    """Run the app once and bring back N stamped frames."""
    if not os.path.exists(EXE):
        raise SystemExit("No build at %s - run dotnet build first." % EXE)

    out = out or OUT
    os.makedirs(out, exist_ok=True)
    for old in os.listdir(out):
        if old.startswith("frame-") and old.endswith(".png"):
            os.remove(os.path.join(out, old))

    base = os.path.join(out, "frame.png")
    # The interval is a floor, not a promise: each frame is a screen grab plus
    # a PNG encode, and at a short interval that encode is the whole cost. The
    # timestamps are what the analysis folds on, so a slow frame is honest
    # rather than fatal - but the timeout has to allow for it or a fast run
    # gets killed for succeeding slowly.
    proc = subprocess.run(
        [EXE, "--screenshot", base, "--screenshot-seq", str(frames), str(interval_ms)],
        capture_output=True, text=True,
        timeout=60 + frames * (interval_ms / 1000.0 + 0.25))
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


# ----------------------------------------------------- the balance waveform

# WHY THIS MODE EXISTS, AND WHY IT IS NOT DEFEATED BY THE CAPTURE RATE.
#
# The balance is the one part in the aperture that is supposed to move
# CONTINUOUSLY: a swing, not a step. Reported from the wall as "it flickers
# across two apparent states". A screen grab costs tens of milliseconds and the
# balance oscillates every 286, so nothing here can watch it at 60 Hz - and it
# does not have to. Every frame is stamped with the instant it was taken and
# the movement is a pure function of the wall clock, so folding each stamp into
# beat phase turns N frames taken at any rate at all into N samples of ONE
# oscillation. Sampling rate stops mattering; only the total number of frames
# does. That is the whole trick, and it is why the interval below is set for
# throughput rather than for any relation to the beat.
#
# Two things are read off each frame:
#
#   WHERE the wheel is. Cross-correlate the balance's own render, rotated,
#   against what the annulus in the capture actually shows. A continuous swing
#   traces a sinusoid against folded phase. Snapping between two poses traces
#   two dots.
#
#   HOW MUCH of the sharp wheel is on screen at all, which is the other half of
#   what a viewer calls flicker. The face cross-fades the sharp render against
#   a rotationally invariant smear, so if that cross-fade is a square wave the
#   wheel strobes in and out of existence at beat rate whatever its angle is
#   doing. This falls out of the same correlation for free: the regression
#   coefficient IS the sharp layer's opacity.

# Where the balance's structure is, as radii in face units from its pivot.
# Inside 14 is the roller and the staff, near enough solid and carrying almost
# no angular signal; outside 66 is off the wheel entirely. Measured off
# Assets/movement-balance.png rather than chosen.
BALANCE_BAND = (14.0, 66.0)
BALANCE_BINS = 360                     # one angular sample per degree
BALANCE_RINGS = 26

# Polar cells under the balance cock's arm. It is painted OVER the wheel and
# never moves, so whatever it covers is not evidence about the wheel.
ARM_ALPHA = 0.35

# A frame with more of the annulus than this under a hand is dropped rather
# than scored, on the same principle as the plate score above.
BALANCE_MAX_MASKED = 0.30

# How much of the sharp layer has to be on screen before its angle counts as
# an OBSERVATION rather than as a fit to noise. The units are layer opacity,
# recovered by least squares, and the run prints the noise floor beside it so
# this can be checked rather than trusted.
SHARP_VISIBLE = 0.10


def caliber_spec():
    """
    The movement's numbers, read out of Services/Caliber.cs.

    Not typed here. A second copy of the beat rate is a copy free to drift, and
    this instrument folds every measurement onto that one number - so a stale
    period would not produce a wrong answer, it would produce a smeared one
    that looks like the defect being measured.
    """
    path = os.path.join(ROOT, "Services", "Caliber.cs")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"Swiss4Hz\s*=\s*new\(\s*\"[^\"]*\"\s*,\s*([\d_]+)\s*,\s*(\d+)"
                  r"\s*,\s*([\d.]+)", src, re.S)
    if not m:
        raise SystemExit("Could not read Caliber.Swiss4Hz out of %s" % path)
    vph = int(m.group(1).replace("_", ""))
    beats = vph / 3600.0
    hertz = beats / 2.0
    return {"vph": vph, "escape_teeth": int(m.group(2)),
            "amplitude": float(m.group(3)),
            "beats_per_second": beats, "hertz": hertz, "period_s": 1.0 / hertz}


def _polar(lum, cx, cy, scale):
    """The annulus around a pivot, unrolled: (rings, bins) of luminance."""
    from scipy.ndimage import map_coordinates
    th = np.arange(BALANCE_BINS) * 2.0 * np.pi / BALANCE_BINS
    rs = np.linspace(BALANCE_BAND[0], BALANCE_BAND[1], BALANCE_RINGS)
    # theta measured with y DOWNWARDS, so increasing theta runs clockwise on
    # screen - the same direction a positive RotateTransform turns a sprite.
    # That is what makes an estimated shift directly comparable to the angle
    # the XAML was written with, sign and all.
    x = cx + np.outer(rs, np.cos(th)) * scale
    y = cy + np.outer(rs, np.sin(th)) * scale
    return map_coordinates(lum, [y, x], order=1, mode="nearest")


def _asset_polar(name, scale, channel="luma"):
    """One asset, resized to capture scale and unrolled about the balance."""
    size = int(round(FACE * scale))
    with Image.open(os.path.join(ASSETS, name)) as im:
        a = np.asarray(im.convert("RGBA").resize((size, size), Image.LANCZOS),
                       dtype=np.float32)
    alpha = a[..., 3] / 255.0
    # Premultiplied: what the layer CONTRIBUTES to the composite at opacity 1,
    # which is the quantity the regression below is trying to find a fraction
    # of. Straight luma would weight the transparent gaps as if they were metal.
    lum = alpha if channel == "alpha" else \
        (a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114) * alpha
    pivot = _balance_pivot()
    return _polar(lum, pivot[0] * scale, pivot[1] * scale, scale)


def _balance_pivot():
    with open(os.path.join(ROOT, "captures", "geom", "profiles.json")) as f:
        return json.load(f)["pivots"]["balance"]


def _symmetry_order(template):
    """
    How many times the wheel repeats in one turn, measured off its own render.

    This is not a detail. A three-armed balance is the same picture at 0 and at
    120 degrees, so 120 is the largest angle any instrument - or any eye - can
    tell apart, and an estimate has to be reported modulo it or it is reporting
    a precision it does not have.
    """
    p = template.mean(axis=0)
    p = p - p.mean()
    ac = np.fft.irfft(np.abs(np.fft.rfft(p)) ** 2, n=BALANCE_BINS)
    ac /= max(ac[0], 1e-9)
    best = 1
    for order in range(2, 13):
        if BALANCE_BINS % order:
            continue
        if ac[BALANCE_BINS // order] > 0.90:
            best = order
    return best


def _fold(when, hertz, lag_s=0.0):
    """A timestamp as a fraction of one oscillation.

    Caliber.Read takes beats from midnight, so balance = A sin(2 pi f t) with t
    the time of day. Folding is that identity and nothing else.
    """
    t = when.hour * 3600 + when.minute * 60 + when.second + when.microsecond / 1e6
    return ((t - lag_s) * hertz) % 1.0


def balance_waveform(frames, spec):
    """
    Angle and sharp-layer opacity for every frame, by rotating the balance's
    own render against the annulus in the capture.

    The composite in the annulus is a static part (plate seen through the
    openwork, the cock's arm, its shadow), plus the smear, which is a full-turn
    rotational average and therefore FLAT in theta, plus the sharp wheel at
    some opacity and some angle. Averaging over the run kills the first;
    subtracting each frame's own angular mean kills the second; whatever is
    left is the wheel, and a circular cross-correlation says where it is and
    how much of it there is.

    The average is refined once against the fit, because a wheel that dwells at
    two poses leaves those two poses in its own average and would otherwise
    subtract away part of the signal it is there to expose.
    """
    scale = frames[0].scale
    pivot = _balance_pivot()

    template = _asset_polar("movement-balance.png", scale)
    arm = _asset_polar("movement-cock.png", scale, channel="alpha") > ARM_ALPHA
    # Measured on the WHOLE render. Symmetry is a property of the wheel, and
    # the arm is a thing standing in front of it - zeroing those cells first
    # reports a three-armed balance as having no symmetry at all.
    order = _symmetry_order(template)
    period = 360.0 / order

    stack, masked, keep = [], [], []
    for f in frames:
        hands = hand_mask(f.lum.shape, f.ox, f.oy, f.scale, f.taken)
        cx, cy = f.to_px(*pivot)
        hidden = arm | (_polar(hands.astype(np.float32), cx, cy, f.scale) > 0.5)
        stack.append(_polar(f.lum, cx, cy, f.scale))
        masked.append(hidden)
        keep.append(hidden.mean() <= BALANCE_MAX_MASKED)

    p = np.stack(stack)
    hide = np.stack(masked)
    keep = np.array(keep)
    if keep.sum() < 8:
        raise SystemExit("Almost every frame was under a hand. Capture more.")

    # Masked cells take no part in anything - not in the average, not in the
    # correlation. That is the same as saying they carry no evidence either
    # way, which is exactly true of a cell that is under a hand.
    live = np.where(hide, 0.0, 1.0) * keep[:, None, None]
    # The template stays WHOLE. Masked cells are zeroed on the capture side
    # only, which already excludes them from every product in the correlation -
    # punching the same holes in the template as well would instead reward the
    # shifts that happen to line one hole up with another.
    w = template - template.mean(axis=1, keepdims=True)
    w_energy = float((w * w).sum())
    wf = np.conj(np.fft.rfft(w, axis=1))
    seen_fraction = np.clip(1.0 - hide.mean(axis=(1, 2)), 1e-3, 1.0)

    angles = np.zeros(len(frames))
    opacity = np.zeros(len(frames))
    noise = np.zeros(len(frames))
    model = np.zeros_like(p)

    for _ in range(2):
        back = ((p - model) * live).sum(axis=0) / np.maximum(live.sum(axis=0), 1.0)
        d = np.where(hide, 0.0, p - back)
        # The smear is a full-turn rotational average, so it is FLAT in theta:
        # subtracting each frame's own angular mean removes it along with any
        # overall brightness the aperture applies, and leaves only what has an
        # angle. Taken over the cells that survived, not over the zeros.
        seen = np.where(hide, 0.0, 1.0)
        mean = (d.sum(axis=2, keepdims=True)
                / np.maximum(seen.sum(axis=2, keepdims=True), 1.0))
        d = np.where(hide, 0.0, d - mean)

        # c[f, a] = sum over the annulus of d[f, theta] * w[theta - a], so the
        # peak sits at the angle the sprite has been turned to.
        c = np.fft.irfft(np.fft.rfft(d, axis=2) * wf[None], n=BALANCE_BINS,
                         axis=2).sum(axis=1)
        c /= max(w_energy, 1e-9) * seen_fraction[:, None]

        # Only one period of it is distinguishable; folding first is what makes
        # the argmax mean something rather than picking between identical peaks.
        folded = c[:, :int(round(period))]
        for k in range(1, order):
            folded = folded + c[:, k * int(round(period)):(k + 1) * int(round(period))]
        folded /= order

        best = np.argmax(folded, axis=1)
        angles = best.astype(float)
        opacity = folded[np.arange(len(frames)), best]
        # The floor this sits on: how big a coefficient the same correlation
        # returns at the angles it did NOT pick. Printed, so SHARP_VISIBLE can
        # be checked against it instead of believed.
        noise = np.median(np.abs(folded), axis=1)

        model = np.zeros_like(p)
        for i in range(len(frames)):
            if keep[i] and opacity[i] > 0:
                model[i] = opacity[i] * np.roll(w, int(best[i]), axis=1)

    return {"angle": angles, "opacity": opacity, "noise": noise,
            "keep": keep, "order": order, "period": period,
            "masked": hide.mean(axis=(1, 2))}


def _fit_gain(phase, opacity, weights=None):
    """
    The gain the face is applying to |cos| before it clamps, recovered from the
    picture on the wall.

    The cross-fade the physics asks for is opacity = 1 - |cos|: all of the
    sharp wheel at the reversals, none of it at full speed, and a smooth ride
    between. Any implementation that multiplies |cos| by g before clamping
    gives 1 - min(1, g|cos|), which for g = 1 is that curve and for large g is
    a square wave. So ONE fitted number separates the two hypotheses, and it is
    an absolute number rather than a self-normalised one, which is what lets a
    before and an after be compared at all.
    """
    c = np.abs(np.cos(2.0 * np.pi * phase))
    w = np.ones_like(opacity) if weights is None else weights
    best = (None, -np.inf)
    for g in np.exp(np.linspace(np.log(0.2), np.log(60.0), 400)):
        m = 1.0 - np.clip(g * c, 0.0, 1.0)
        # Scale and offset are free: the recovered opacity carries whatever the
        # aperture does to a layer's luminance on its way to the screen.
        a = np.vstack([m, np.ones_like(m)]).T
        sol, *_ = np.linalg.lstsq(a * w[:, None], opacity * w, rcond=None)
        resid = opacity - a @ sol
        ss = 1.0 - (w * resid ** 2).sum() / max((w * (opacity - np.average(
            opacity, weights=w)) ** 2).sum(), 1e-12)
        if ss > best[1]:
            best = ((float(g), sol), ss)
    (g, sol), r2 = best
    return {"gain": g, "scale": float(sol[0]), "offset": float(sol[1]),
            "r2": float(r2)}


def _fit_lag(frames, wave, spec):
    """
    The capture's own lag, in seconds, fitted rather than assumed.

    The stamp is read after the compositor presented a frame that was drawn
    from a slightly earlier instant, and the screen grab happens after that
    again. It is a few milliseconds, which is a few per cent of a beat, and
    leaving it out would rotate every waveform below by that much and blame the
    face for it.
    """
    keep = wave["keep"]
    best = (0.0, -np.inf)
    for lag in np.linspace(-0.030, 0.030, 121):
        phase = np.array([_fold(f.taken, spec["hertz"], lag) for f in frames])
        fit = _fit_gain(phase[keep], wave["opacity"][keep])
        if fit["r2"] > best[1]:
            best = (float(lag), fit["r2"])
    return best[0]


def balance_verdict(frames, wave, spec, lag):
    """Every number the mode exists to print, in one dict."""
    keep = wave["keep"]
    phase = np.array([_fold(f.taken, spec["hertz"], lag) for f in frames])
    fit = _fit_gain(phase[keep], wave["opacity"][keep])

    # ...and the same data scored against the curve the physics asks for, so
    # the fitted gain has something to be read against rather than standing on
    # its own. Two R-squareds, one hypothesis each.
    unit_r2 = float(_score_at(phase[keep], wave["opacity"][keep], 1.0))

    seen = keep & (wave["opacity"] > SHARP_VISIBLE)
    bins = int(round(wave["period"] / 5.0))
    occupied = np.zeros(bins, bool)
    if seen.any():
        idx = (wave["angle"][seen] / wave["period"] * bins).astype(int) % bins
        occupied[idx] = True

    # Runs of occupied bins around the circle, and how wide a run is. The count
    # alone does not separate the hypotheses and it took a measurement to find
    # that out: both builds show TWO runs, because the sharp layer is brightest
    # around the two reversals either way. What separates them is whether a run
    # is a point or an arc - 5 degrees of dwell against 40 degrees of swing.
    poses = 0
    if occupied.any():
        rolled = np.roll(occupied, -int(np.argmin(occupied)))
        poses = int(np.sum(rolled[1:] & ~rolled[:-1]) + (1 if rolled[0] else 0))

    # How far the angle estimates sit from where Caliber says the wheel was.
    amp = spec["amplitude"]
    want = (amp * np.sin(2.0 * np.pi * phase)) % wave["period"]
    err = (wave["angle"] - want + wave["period"] / 2.0) % wave["period"] \
        - wave["period"] / 2.0
    rms = float(np.sqrt((err[seen] ** 2).mean())) if seen.any() else float("nan")

    return {
        "frames": int(len(frames)), "scored": int(keep.sum()),
        "period_s": spec["period_s"], "lag_ms": lag * 1000.0,
        "symmetry_deg": wave["period"],
        "noise_floor": float(np.median(wave["noise"][keep])),
        "visible_frames": int(seen.sum()),
        "visible_fraction": float(seen.sum() / max(keep.sum(), 1)),
        # What one whole unit of layer opacity is worth in the recovered
        # coefficient. It is well under 1 because the smear is composited OVER
        # the sharp render and the aperture is darker than the render, and it
        # is reported rather than divided out: a self-normalised waveform would
        # have looked exactly the same before and after.
        "opacity_scale": fit["scale"],
        "crossfade_gain": fit["gain"],
        "crossfade_r2": fit["r2"],
        "r2_at_unit_gain": unit_r2,
        "swing_coverage": float(occupied.mean()),
        "poses": poses,
        "pose_span_deg": float(occupied.mean() * wave["period"] / max(poses, 1)),
        "angle_rms_deg": rms,
        # Two numbers, one per hypothesis, and both have to hold. The gain says
        # the cross-fade is a fade rather than a switch; the span says the
        # wheel is seen through an arc of its swing rather than parked at the
        # ends of it. Either on its own can be argued with.
        "verdict": "continuous swing"
                   if fit["gain"] < 2.0
                   and occupied.mean() * wave["period"] / max(poses, 1) > 20.0
                   else "two-state",
    }


def _score_at(phase, opacity, gain):
    """R^2 of the recovered opacity against ONE hypothesis' curve."""
    m = 1.0 - np.clip(gain * np.abs(np.cos(2.0 * np.pi * phase)), 0.0, 1.0)
    a = np.vstack([m, np.ones_like(m)]).T
    sol, *_ = np.linalg.lstsq(a, opacity, rcond=None)
    resid = opacity - a @ sol
    return 1.0 - (resid ** 2).sum() / max(((opacity - opacity.mean()) ** 2).sum(), 1e-12)


def balance_plot(frames, wave, spec, lag, verdict, path):
    """The artifact: both waveforms against one folded oscillation."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    keep = wave["keep"]
    phase = np.array([_fold(f.taken, spec["hertz"], lag) for f in frames])
    seen = keep & (wave["opacity"] > SHARP_VISIBLE)
    u = np.linspace(0, 1, 721)
    amp = spec["amplitude"]
    per = wave["period"]

    fig, ax = plt.subplots(3, 1, figsize=(9.5, 11.0), sharex=True)
    fig.suptitle("balance waveform, %d frames folded on one %.1f ms oscillation\n"
                 "cross-fade gain %.2f (1.00 = opacity tracks speed; large = a "
                 "square wave), verdict: %s"
                 % (verdict["scored"], spec["period_s"] * 1000.0,
                    verdict["crossfade_gain"], verdict["verdict"]), fontsize=11)

    # Both curves carry the fitted scale, so they are drawn in the units the
    # measurement is actually in. A full-opacity sharp layer recovers well
    # under 1 here - the smear is composited over it and the aperture is
    # darker than the render - and normalising that away would have made the
    # failing build and the fixed one plot identically.
    k = verdict["opacity_scale"]
    ax[0].plot(u, k * (1.0 - np.clip(verdict["crossfade_gain"]
                                     * np.abs(np.cos(2 * np.pi * u)), 0, 1)),
               color="crimson", lw=1.2, label="best fit, gain %.2f"
               % verdict["crossfade_gain"])
    ax[0].plot(u, k * (1.0 - np.abs(np.cos(2 * np.pi * u))), color="seagreen",
               lw=1.2, ls="--", label="what the physics asks for (gain 1)")
    ax[0].scatter(phase[keep], wave["opacity"][keep], s=12, color="black",
                  alpha=0.65, label="measured")
    ax[0].axhline(verdict["noise_floor"], color="grey", lw=0.8, ls=":",
                  label="noise floor %.3f" % verdict["noise_floor"])
    ax[0].set_ylabel("sharp balance layer, recovered coefficient")
    ax[0].legend(fontsize=8, loc="upper center")

    ax[1].plot(u, (amp * np.sin(2 * np.pi * u)) % per, ",", color="seagreen",
               ms=1, label="Caliber's angle, mod %.0f deg" % per)
    ax[1].scatter(phase[seen], wave["angle"][seen], s=16, color="black",
                  label="measured, where the sharp layer is visible")
    ax[1].scatter(phase[keep & ~seen], wave["angle"][keep & ~seen], s=8,
                  color="lightgrey", label="below the visibility floor - no angle")
    ax[1].set_ylabel("balance angle, degrees mod %.0f" % per)
    ax[1].legend(fontsize=8, loc="upper center")

    lum = np.array([float(np.nanmean(_polar(f.lum, *f.to_px(*_balance_pivot()),
                                            f.scale))) for f in frames])
    ax[2].scatter(phase[keep], lum[keep], s=12, color="black")
    ax[2].set_ylabel("mean luminance of the annulus")
    ax[2].set_xlabel("phase of one oscillation (0 = balance crossing centre)")

    for a in ax:
        a.grid(alpha=0.25)
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    fig.savefig(path, dpi=110)
    plt.close(fig)


def balance_validation(frames, wave, path):
    """
    The estimator checked by eye, which is the step nothing else can replace.

    Six of the frames the fit was most confident about, each beside the balance
    render turned to the angle the fit claims. If those two do not line up the
    numbers above are decoration.
    """
    keep = wave["keep"]
    rank = np.argsort(np.where(keep, wave["opacity"], -np.inf))[::-1][:6]
    scale = frames[0].scale
    pivot = _balance_pivot()
    reach = int(round((BALANCE_BAND[1] + 4) * scale))
    size = int(round(FACE * scale))
    with Image.open(os.path.join(ASSETS, "movement-balance.png")) as im:
        sprite = im.convert("RGBA").resize((size, size), Image.LANCZOS)

    tiles = []
    for i in rank:
        f = frames[i]
        cx, cy = f.to_px(*pivot)
        with Image.open(f.path) as im:
            shot = im.convert("RGB").crop((int(cx - reach), int(cy - reach),
                                           int(cx + reach), int(cy + reach)))
        turned = sprite.rotate(-float(wave["angle"][i]), resample=Image.BICUBIC,
                               center=(pivot[0] * scale, pivot[1] * scale))
        ref = Image.new("RGB", turned.size, (0, 0, 0))
        ref.paste(turned, (0, 0), turned)
        ref = ref.crop((int(pivot[0] * scale - reach), int(pivot[1] * scale - reach),
                        int(pivot[0] * scale + reach), int(pivot[1] * scale + reach)))
        tiles.append((shot, ref, float(wave["angle"][i])))

    w = reach * 4 + 12
    out = Image.new("RGB", (w, (reach * 2 + 26) * len(tiles)), (18, 18, 22))
    draw = ImageDraw.Draw(out)
    for row, (shot, ref, ang) in enumerate(tiles):
        y = row * (reach * 2 + 26)
        out.paste(shot, (0, y))
        out.paste(ref, (reach * 2 + 12, y))
        draw.text((6, y + reach * 2 + 6),
                  "capture  |  the render turned to %.0f deg" % ang,
                  fill=(230, 230, 235))
    out = out.resize((w * 2, out.size[1] * 2), Image.LANCZOS)
    out.save(path)


def balance_main(args):
    spec = caliber_spec()
    out = os.path.join(OUT, "balance")
    os.makedirs(out, exist_ok=True)
    index_path = os.path.join(out, "frames.json")

    # Short and many, on purpose. Phase coverage comes from the number of
    # frames and the fact that the capture rate has no relation to the beat -
    # not from sampling fast enough to follow it, which is impossible here.
    frames_wanted = _parse(args, "--frames", 240)
    interval = _parse(args, "--interval", 20)

    if "--rescore" in args:
        with open(index_path) as f:
            taken = json.load(f)["frames"]
        print("re-scoring %d frames already in captures/motion/balance" % len(taken))
    else:
        print("capturing %d frames from the running app (~%ds, foreground)..."
              % (frames_wanted, int(frames_wanted * 0.09)))
        taken = capture(frames_wanted, interval, out=out)

    first = _load(taken[0]["path"])
    ox, oy, scale, zncc = locate_face(first)
    frames = [Frame(t["path"], dt.datetime.fromisoformat(t["taken"]), ox, oy, scale)
              for t in taken]
    span = (frames[-1].taken - frames[0].taken).total_seconds()
    print("face found at (%.0f, %.0f), %.4f px per face unit, match %.2f" %
          (ox, oy, scale, zncc))
    print("%d frames over %.1fs, %.1f ms apart on average, against a %.1f ms "
          "oscillation (%.1f Hz, %d vph, %.0f deg amplitude - read from "
          "Services/Caliber.cs)\n"
          % (len(frames), span, span / max(len(frames) - 1, 1) * 1000.0,
             spec["period_s"] * 1000.0, spec["hertz"], spec["vph"],
             spec["amplitude"]))

    with open(index_path, "w") as f:
        json.dump({"frames": taken,
                   "face": {"x": ox, "y": oy, "scale": scale, "match": zncc}},
                  f, indent=2)

    wave = balance_waveform(frames, spec)
    lag = _fit_lag(frames, wave, spec)
    verdict = balance_verdict(frames, wave, spec, lag)

    print("the balance repeats every %.0f degrees (measured off its own render, "
          "so that is all any estimate can resolve)" % verdict["symmetry_deg"])
    print("capture lag fitted at %.1f ms\n" % verdict["lag_ms"])
    print("%-42s %s" % ("frames scored", "%d of %d" % (verdict["scored"],
                                                       verdict["frames"])))
    print("%-42s %d  (%.0f%% of the oscillation)"
          % ("frames showing the sharp balance at all", verdict["visible_frames"],
             100.0 * verdict["visible_fraction"]))
    print("%-42s %.3f" % ("correlation noise floor", verdict["noise_floor"]))
    print("%-42s %.2f" % ("...one unit of layer opacity is worth",
                          verdict["opacity_scale"]))
    print("%-42s %.2f   (R2 %.2f)" % ("cross-fade gain on |cos|",
                                      verdict["crossfade_gain"],
                                      verdict["crossfade_r2"]))
    print("%-42s %.2f" % ("...the same data against gain 1.00",
                          verdict["r2_at_unit_gain"]))
    print("%-42s %d, %.0f deg wide each"
          % ("arcs of the swing the wheel is seen in", verdict["poses"],
             verdict["pose_span_deg"]))
    print("%-42s %.0f%%" % ("of the swing ever seen sharp",
                            100.0 * verdict["swing_coverage"]))
    print("%-42s %.1f deg" % ("angle error against Caliber",
                              verdict["angle_rms_deg"]))

    plot = os.path.join(OUT, "balance-waveform.png")
    balance_plot(frames, wave, spec, lag, verdict, plot)
    balance_validation(frames, wave, os.path.join(OUT, "balance-frames.png"))
    print("\ncaptures/motion/balance-waveform.png is the picture")
    print("captures/motion/balance-frames.png checks the estimator by eye")

    record = {"when": dt.datetime.now().isoformat(timespec="seconds"),
              "caliber": spec, "verdict": verdict,
              "phase": [_fold(f.taken, spec["hertz"], lag) for f in frames],
              "angle": wave["angle"].tolist(),
              "opacity": wave["opacity"].tolist(),
              "scored": wave["keep"].tolist()}
    with open(os.path.join(OUT, "balance.json"), "w") as f:
        json.dump(record, f, indent=2)

    baseline = os.path.join(OUT, "balance-baseline.json")
    if not os.path.exists(baseline):
        with open(baseline, "w") as f:
            json.dump(record, f, indent=2)
        print("\nbaseline written to captures/motion/balance-baseline.json "
              "(never overwritten - it is the before)")
    else:
        with open(baseline) as f:
            base = json.load(f)
        was = dict(base["verdict"], when=base.get("when", "the first run"))
        # The baseline predates pose_span_deg, so derive it rather than lose
        # the before. It is only ever coverage spread over the runs it fell in.
        span = was.get("pose_span_deg", was["swing_coverage"]
                       * was["symmetry_deg"] / max(was["poses"], 1))
        print("\nagainst the baseline taken %s:\n"
              "    cross-fade gain      %6.2f -> %6.2f   (1.00 is speed itself)\n"
              "    swing seen sharp     %5.0f%%  -> %5.0f%%\n"
              "    each arc seen        %5.0f   -> %5.0f    degrees wide\n"
              "    verdict              %s -> %s"
              % (was["when"], was["crossfade_gain"], verdict["crossfade_gain"],
                 100.0 * was["swing_coverage"], 100.0 * verdict["swing_coverage"],
                 span, verdict["pose_span_deg"],
                 was.get("verdict", "?"), verdict["verdict"]))

    failed = verdict["verdict"] != "continuous swing"
    print("\n[%s] the balance reads as %s"
          % ("FAIL" if failed else "ok  ", verdict["verdict"]))
    return 1 if failed else 0


# ---------------------------------------------------------------- entry point

def _parse(args, flag, default):
    return int(args[args.index(flag) + 1]) if flag in args else default


def main():
    args = sys.argv[1:]
    if "--balance" in args:
        return balance_main(args)

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
