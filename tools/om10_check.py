"""Checks the parts lifted out of OM10: tooth counts, and a look at each one.

    .venv-cad\\Scripts\\python.exe tools/om10_check.py

Two things have to be true before any of these are worth rendering, and neither
is visible in the extractor's own output.

FIRST, each part must be centred on the axis it turns about. Get that wrong and
a wheel wobbles by half a tooth for ever, which at 3px per face unit is a part
that will not stop shimmering and will never look like it was made. The plot
draws each part's own axis as a crosshair, so a wheel that is off-centre is
obvious rather than subtle.

SECOND, the tooth counts have to be right, because they are not decoration: the
escape wheel's count sets the beat, and the wheel-to-pinion ratio sets how fast
every other hand turns. The extractor's count ran on raw triangulation vertices,
which cluster wherever the tessellator felt like putting them and leave angular
gaps that read as gullets. This resamples the outline uniformly by walking the
mesh's boundary edges, which has no such bias.
"""

import json
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS = os.path.join(ROOT, "captures", "om10", "parts")


def outline_radius(mesh, bins=2000, samples=400000):
    """
    Max radius per angular bin, sampled uniformly over the surface.

    Sampling by AREA rather than by vertex is the whole fix: a tessellator puts
    many vertices on a tight fillet and few on a long straight, so vertex counts
    lie about where the material is. Area sampling cannot.
    """
    pts, _ = trimesh.sample.sample_surface(mesh, samples)
    r = np.hypot(pts[:, 0], pts[:, 1])
    a = (np.arctan2(pts[:, 1], pts[:, 0]) + 2 * math.pi) % (2 * math.pi)
    idx = np.minimum((a / (2 * math.pi) * bins).astype(int), bins - 1)
    prof = np.zeros(bins)
    np.maximum.at(prof, idx, r)
    ok = prof > 0
    if ok.sum() < bins * 0.9:
        prof = np.interp(np.arange(bins), np.flatnonzero(ok), prof[ok], period=bins)
    return prof


def teeth_of(prof):
    """Dominant period of the outline, with the margin it won by."""
    spec = np.abs(np.fft.rfft(prof - prof.mean()))
    lo, hi = 5, min(220, len(spec))
    band = spec[lo:hi]
    if not len(band):
        return 0, 0.0
    k = lo + int(np.argmax(band))
    mask = np.ones_like(band, dtype=bool)
    for h in range(1, 6):
        c = h * k - lo
        if 0 <= c < len(band):
            mask[max(0, c - 2):c + 3] = False
    floor = np.median(band[mask]) if mask.any() else 1.0
    return k, float(band.max() / max(floor, 1e-9))


def main():
    with open(os.path.join(PARTS, "manifest.json")) as f:
        manifest = json.load(f)

    names = list(manifest)
    cols = 6
    rows = (len(names) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2.4, rows * 2.6))
    axes = np.atleast_2d(axes)
    for ax in axes.flat:
        ax.axis("off")

    print("%-11s %8s %8s %7s %8s  %s" %
          ("part", "radius", "thick", "teeth", "margin", "source"))
    for i, name in enumerate(names):
        spec = manifest[name]
        mesh = trimesh.load(os.path.join(PARTS, spec["stl"]), process=False)
        prof = outline_radius(mesh)
        teeth, margin = teeth_of(prof)
        trust = margin > 8.0
        spec["teeth"] = teeth if trust else 0
        spec["tooth_margin"] = round(margin, 1)
        print("%-11s %8.3f %8.3f %7s %8.1f  %s" %
              (name, spec["radius"], spec["thickness"],
               teeth if trust else "-", margin, spec["source"]))

        ax = axes[i // cols][i % cols]
        ax.axis("on")
        ax.set_xticks([])
        ax.set_yticks([])
        v = mesh.vertices
        ax.plot(v[:, 0], v[:, 1], ",", color="#e8c46a", alpha=0.30, markersize=0.4)
        R = spec["radius"] * 1.12
        ax.axhline(0, color="#5ad1ff", lw=0.5, alpha=0.8)
        ax.axvline(0, color="#5ad1ff", lw=0.5, alpha=0.8)
        ax.set_xlim(-R, R)
        ax.set_ylim(-R, R)
        ax.set_aspect("equal")
        ax.set_facecolor("#14141a")
        ax.set_title("%s  r%.2f t%.2f%s" %
                     (name, spec["radius"], spec["thickness"],
                      ("  %dT" % teeth) if trust else ""),
                     fontsize=7, color="white", pad=2)
        for s in ax.spines.values():
            s.set_color("#444")

    with open(os.path.join(PARTS, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)

    path = os.path.join(ROOT, "captures", "om10", "extracted.png")
    fig.tight_layout()
    fig.savefig(path, dpi=124, facecolor="#14141a")
    print("\nwrote %s" % path)


if __name__ == "__main__":
    main()
