"""Measures what the movement DOES to the eye, because looking at it cannot.

    python tools/motion_audit.py
    python tools/motion_audit.py --ablate      # freeze one part at a time

WHY MEASURE INSTEAD OF LOOK. Every judgement about this face so far has been
made from single frames at 1920px. It is watched animated, at about 180px
across, from across a room. Those are different artifacts, and no amount of
staring at stills bridges the gap - a still cannot show flicker, aliasing or
irregularity, which is the entire complaint. So this turns "chaotic" into three
numbers, each of which corresponds to something known about human vision:

  FLICKER. Sensitivity to a repeating luminance change peaks around 8-15 Hz.
  An escapement beats at exactly 8. A real watch gets away with it because the
  events are tiny and low contrast; a large high-contrast 8 Hz modulation is
  about the most irritating thing a display can do. Measured as the modulation
  depth of mean aperture luminance and its dominant frequency.

  UNTRACKABLE DETAIL. The eye tracks smoothly to roughly 30 deg/s of visual
  angle. Past that it cannot lock on, and SHARP detail moving faster than that
  reads as chaos while BLURRED detail at the same speed reads as smooth. This
  is the difference between fast and stressful. Measured as frame-to-frame RMS
  difference, and its variance - steady change is motion, erratic change is
  noise.

  APPARENT ROTATION. Aliasing does not merely blur a wheel, it makes it appear
  to turn the WRONG WAY, differently on different frames. The visual system
  gets contradictory motion signals and never settles. Measured by circular
  cross-correlation of the balance's angular luminance profile between frames,
  compared against the rotation it actually made.

--ablate freezes each moving part in turn and re-measures, which is how to find
out which part carries the problem instead of guessing.

The physics comes from beat_strip.read, which mirrors Services/Caliber.cs.
"""

import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import beat_strip as bs                                       # noqa: E402

ROOT = bs.ROOT
ASSETS = bs.ASSETS
OUT = os.path.join(ROOT, "captures", "beat")

# The wall shows the whole 640-unit face at about 470px. Everything below is
# measured at THAT size, because a 12px bar aliases differently from a 36px one
# and the 1920px asset is not what anybody sees.
WALL_FACE_PX = 470.0
WORK = 960                       # half the asset resolution: 4x faster, same answer
FPS = 60.0

LAYERS = ("base", "train", "escape", "fork", "spring", "balance", "cock")
MOVING = ("train", "escape", "fork", "spring", "balance")

# WHAT THE FACE ACTUALLY DOES. Every measurement below is taken against this,
# because a row measured against some other configuration is not a measurement
# of anything that ships. The balance cross-fades on its SPEED with no
# threshold at all, its smear does not turn, and the three stepping parts get a
# shutter across their jump; see OpenworkedFace.Draw.
SHIP = {"threshold": None, "spin_blur": False, "shutter": True}

# The parts that jump rather than glide, and the angular width below which their
# jump stops being resolvable as a movement of a thing. A shutter, in other
# words: on the one frame in seven and a half where the escapement fires, these
# show their smear instead of teleporting. None is a taste value - the escape
# wheel's is half its tooth spacing and the lever's is half its total travel.
STEPPED = {"escape": 6.0, "fork": 7.0, "spring": 6.0}

# Parts whose smear is HELD STILL rather than turned with them, because the
# smear is rotationally invariant and turning it would only add resampling
# noise. The balance rim is an annulus. A multi-turn spiral is very nearly the
# same: rotating r = a + b*theta by delta gives (a - b*delta) + b*theta, the
# same spiral starting a hair further in - which is also what a hairspring
# actually does. It breathes concentrically; it does not sweep.
STATIC_SMEAR = {"balance", "spring"}


def _load():
    scale = WORK / bs.FACE
    ims = {}
    for n in LAYERS:
        im = Image.open(os.path.join(ASSETS, "movement-%s.png" % n)).convert("RGBA")
        ims[n] = im.resize((WORK, WORK), Image.LANCZOS)
    for n in ("balance",) + tuple(STEPPED):
        path = os.path.join(ASSETS, "movement-%s-blur.png" % n)
        if os.path.exists(path):
            ims[n + "_blur"] = Image.open(path).convert("RGBA").resize(
                (WORK, WORK), Image.LANCZOS)
    return ims, scale


def _fade(im, k):
    r, g, b, a = im.split()
    return Image.merge("RGBA", (r, g, b, a.point(lambda v: int(v * k))))


# How far the balance travels in one 60Hz frame at its fastest. From the
# caliber rather than typed: this file had it at 4 Hz, which is the beat the
# face had before the OM10's real tooth counts put it at 3.5.
PEAK_SWEEP = bs.PEAK_DPS / FPS


def smear_of(speed, threshold):
    """
    How smeared the wheel should read.

    None is what ships and what the physics asks for: the smear is a full-turn
    rotational average, so cross-fading to it is a fade between stopped and
    spinning and the control on that is speed itself.

    A threshold is the other hypothesis - the rule the three stepping parts
    use, where a feature stops being resolvable once it sweeps more than its
    own width in a frame. On the balance that ratio is fifteen, so it clamps
    for 96% of the oscillation and the wheel appears only in a spike at each
    reversal. Kept as a row rather than deleted, because it is what the wall
    was showing when it was reported as flickering between two states.
    """
    if threshold is None:
        return speed
    return min(1.0, speed * PEAK_SWEEP / threshold)


def _spun(im, scale, name, ang):
    if not ang:
        return im
    px, py = bs.PIVOTS[name]
    return im.rotate(-ang, resample=Image.BICUBIC, center=(px * scale, py * scale))


def compose(ims, scale, beats, freeze=(), use_blur=True, threshold=None,
            spin_blur=True, shutter=True):
    """One frame of the aperture, at wall scale, as a float luminance array."""
    a = bs.read(beats)
    prev = bs.read(beats - bs.BEATS_PER_SECOND / FPS)
    out = Image.new("RGBA", (WORK, WORK), (10, 10, 13, 255))
    for n in LAYERS:
        im = ims[n]
        ang = 0.0 if n in freeze else a.get(n, 0.0)
        if ang:
            px, py = bs.PIVOTS[n]
            im = im.rotate(-ang, resample=Image.BICUBIC,
                           center=(px * scale, py * scale))

        # A shutter on the parts that jump: cross-fade to the smear by how far
        # this part actually travelled since the previous frame, and place that
        # smear at the MIDPOINT of the travel, which is what a shutter open
        # across the move would have integrated.
        if (shutter and use_blur and n in STEPPED and n not in freeze
                and (n + "_blur") in ims):
            was = prev.get(n, 0.0)
            swept = abs(ang - was)
            k = min(1.0, swept / STEPPED[n])
            if k > 0.0:
                mid = ims[n + "_blur"]
                if n not in STATIC_SMEAR:
                    mid = _spun(mid, scale, n, (ang + was) / 2.0)
                out = Image.alpha_composite(out, _fade(im, 1.0 - k))
                im = _fade(mid, k)

        if n == "balance" and use_blur:
            speed = 0.0 if "balance" in freeze else smear_of(a["speed"], threshold)
            blur = ims["balance_blur"]
            if ang and spin_blur:
                px, py = bs.PIVOTS["balance"]
                blur = blur.rotate(-ang, resample=Image.BICUBIC,
                                   center=(px * scale, py * scale))
            out = Image.alpha_composite(out, _fade(im, 1.0 - speed))
            im = _fade(blur, speed)
        out = Image.alpha_composite(out, im)

    cx, cy, r = bs.APERTURE
    m = r + 6.0
    crop = out.crop((int((cx - m) * scale), int((cy - m) * scale),
                     int((cx + m) * scale), int((cy + m) * scale)))
    wall = max(8, int(round(2 * m * WALL_FACE_PX / bs.FACE)))
    crop = crop.convert("RGB").resize((wall, wall), Image.LANCZOS)
    return np.asarray(crop, np.float64) @ np.array([0.2126, 0.7152, 0.0722])


def angular_profile(img, centre, r0, r1, bins=360):
    """Mean luminance around a ring, as a function of angle. This is the signal
    a rotating wheel modulates, and cross-correlating it between frames is what
    reveals which way the wheel APPEARS to have turned."""
    h, w = img.shape
    th = np.linspace(0, 2 * np.pi, bins, endpoint=False)
    rs = np.linspace(r0, r1, 12)
    prof = np.zeros(bins)
    for r in rs:
        xs = np.clip((centre[0] + r * np.cos(th)).astype(int), 0, w - 1)
        ys = np.clip((centre[1] + r * np.sin(th)).astype(int), 0, h - 1)
        prof += img[ys, xs]
    prof /= len(rs)
    return prof - prof.mean()


def apparent_shift(p0, p1):
    """Circular cross-correlation peak, in degrees, wrapped to +/-180."""
    c = np.fft.irfft(np.fft.rfft(p1) * np.conj(np.fft.rfft(p0)), n=len(p0))
    k = int(np.argmax(c))
    return k - 360 if k > 180 else k


def audit(ims, scale, freeze=(), use_blur=True, frames=30, threshold=None,
          spin_blur=False, shutter=True):
    step = bs.BEATS_PER_SECOND / FPS
    seq = [compose(ims, scale, 4.0 + i * step, freeze, use_blur, threshold,
                   spin_blur, shutter)
           for i in range(frames)]

    lum = np.array([f.mean() for f in seq])
    modulation = (lum.max() - lum.min()) / lum.mean()
    spec = np.abs(np.fft.rfft(lum - lum.mean()))
    freqs = np.fft.rfftfreq(frames, 1.0 / FPS)
    peak_hz = freqs[int(np.argmax(spec))] if len(spec) > 1 else 0.0

    diff = np.array([np.sqrt(((seq[i] - seq[i - 1]) ** 2).mean())
                     for i in range(1, frames)])

    # JOLT. The ratio of the worst frame to the typical one. Mean change says
    # how much is moving; this says whether it arrives as motion or as a shock.
    # An abrupt onset is the strongest involuntary attention cue vision has, so
    # a face can be almost still on average and still be exhausting if all of
    # its change lands in one frame out of eight.
    jolt = diff.max() / max(np.median(diff), 1e-9)
    peak = diff.max()

    # Apparent vs true rotation of the balance rim.
    n = seq[0].shape[0]
    ap_scale = n / (2.0 * (bs.APERTURE[2] + 6.0))
    bx, by = bs.PIVOTS["balance"]
    ax, ay, ar = bs.APERTURE
    centre = ((bx - (ax - ar - 6.0)) * ap_scale, (by - (ay - ar - 6.0)) * ap_scale)
    R = 0.600 * ar * ap_scale
    profs = [angular_profile(f, centre, 0.45 * R, 0.98 * R) for f in seq]

    agree = wrong = 0
    for i in range(1, frames):
        true = bs.read(4.0 + i * step)["balance"] - bs.read(4.0 + (i - 1) * step)["balance"]
        if abs(true) < 1e-6:
            continue
        app = apparent_shift(profs[i - 1], profs[i])
        if abs(app) < 1e-9:
            continue
        if math.copysign(1, app) == math.copysign(1, true):
            agree += 1
        else:
            wrong += 1

    return {
        "flicker_pct": 100.0 * modulation,
        "flicker_hz": peak_hz,
        "diff_mean": diff.mean(),
        "diff_cv": diff.std() / diff.mean() if diff.mean() else 0.0,
        "jolt": jolt,
        "peak": peak,
        "dir_wrong": wrong,
        "dir_total": agree + wrong,
    }


def show(label, m):
    print("%-26s flicker %4.1f%% | motion %5.2f | worst frame %5.2f (%4.1fx)"
          % (label, m["flicker_pct"], m["diff_mean"], m["peak"], m["jolt"]))


def main():
    ims, scale = _load()
    print("aperture at wall scale, 60fps sampling, two beats")
    print("lower is calmer, except that zero motion is a stopped watch\n")
    # The first row is what ships. It was labelled that while being measured
    # with the shutter off, which the face has never run without.
    show("deployed now", audit(ims, scale, **SHIP))
    show("(threshold cross-fade)", audit(ims, scale, threshold=7.0))
    show("(before the smear was pinned)",
         audit(ims, scale, threshold=7.0, spin_blur=True, shutter=False))

    if "--ablate" in sys.argv:
        print()
        for part in MOVING:
            show("frozen: %s" % part, audit(ims, scale, freeze=(part,)))
        print()
        show("only the balance moving", audit(ims, scale,
                                              freeze=tuple(p for p in MOVING if p != "balance")))
        show("everything frozen", audit(ims, scale, freeze=MOVING))


if __name__ == "__main__":
    main()
