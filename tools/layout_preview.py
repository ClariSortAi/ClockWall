"""Draws the placed movement in the aperture, in seconds rather than minutes.

    .venv-cad\\Scripts\\python.exe tools/layout_preview.py [bearing ...]

A full render is eight minutes, which is fine for judging a material and far too
slow for judging a LAYOUT - and layout is the one thing that needs to be looked
at repeatedly, because the only way to know whether the balance cock is covering
the balance is to see it covering the balance.

So this projects the placed solids straight to their silhouettes and stacks them
in z order inside the aperture circle. It says nothing about light, shadow or
finish, and it is not meant to: it answers where things are and what hides what.

Given one or more bearings it re-places the whole movement at each and draws
them side by side. That rotation is still a similarity, so every one of these is
a mechanically correct watch - they differ only in which way it faces.
"""

import importlib.util
import json
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from matplotlib.collections import PolyCollection
from matplotlib.patches import Circle
from trimesh.path import polygons as tp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import om10_layout as L                                       # noqa: E402

PARTS = os.path.join(ROOT, "captures", "om10", "parts")
APERTURE = (320.0, 450.0, 126.0)
_MR = APERTURE[2] * 0.85
BALANCE_XY = (APERTURE[0] - 0.222 * _MR, APERTURE[1] + 0.133 * _MR)
BALANCE_R = 0.600 * _MR

# Painted back to front, with the colour each part actually renders in. The
# order is the z order, so what covers what here is what covers what there.
DRAW = [
    ("jewel", "ruby", "#8d2233", ("escape", "balance", "pallet", "fourth")),
    ("escape", "escapement", "#c8ccd2", ("escape",)),
    ("lever", "escapement", "#c8ccd2", ("pallet",)),
    ("wheel_c", "brass", "#c9a227", ("fourth",)),
    ("roller", "steel", "#b9bec6", ("balance",)),
    ("balance", "brass", "#c9a227", ("balance",)),
    ("hairspring", "blued", "#3b5da8", ("balance",)),
    ("cock", "steel", "#e7e9ee", (None,)),
]


def outline(name):
    mesh = trimesh.load(os.path.join(PARTS, "%s.stl" % name), process=False)
    return tp.projected(mesh, normal=[0, 0, 1])


def rings_of(poly):
    out = [np.array(poly.exterior.coords)]
    out += [np.array(r.coords) for r in poly.interiors]
    return out


def draw(ax, bearing, cache):
    place = L.make(BALANCE_XY, BALANCE_R, bearing)
    manifest = json.load(open(os.path.join(PARTS, "manifest.json")))

    for src, _mat, colour, arbors in DRAW:
        poly = cache.setdefault(src, outline(src))
        for arbor in arbors:
            axis = L.AXIS[arbor] if arbor else manifest[src]["axis"]
            fx, fy = place.to_face(axis[0], axis[1])
            th = math.radians(place.ROT_DEG)
            c, s = math.cos(th), math.sin(th)
            polys = []
            for ring in rings_of(poly):
                # The STL's own frame has y up; face y runs down, so flip
                # BEFORE rotating. Rotating first turns the part the wrong way,
                # which is the same trap movement.step.py's place() fell into.
                u = ring[:, 0] * place.SCALE
                v = -ring[:, 1] * place.SCALE
                polys.append(np.column_stack((fx + u * c - v * s,
                                              fy + u * s + v * c)))
            ax.add_collection(PolyCollection(
                polys, facecolors=colour, edgecolors="#00000060",
                linewidths=0.4, alpha=0.95))

    ax.add_patch(Circle(APERTURE[:2], APERTURE[2], fill=False,
                        ec="#ffffff55", lw=1.6))
    ax.set_xlim(APERTURE[0] - 140, APERTURE[0] + 140)
    ax.set_ylim(APERTURE[1] + 140, APERTURE[1] - 140)   # face y runs down
    ax.set_aspect("equal")
    ax.set_facecolor("#16161c")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("escape bearing %.1f deg" % bearing, color="white", fontsize=9)


def main():
    bearings = [float(a) for a in sys.argv[1:]] or [51.53]
    cache = {}
    cols = min(len(bearings), 4)
    rows = (len(bearings) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.6, rows * 3.8))
    axes = np.atleast_1d(axes).ravel()
    for ax in axes:
        ax.axis("off")
    for ax, b in zip(axes, bearings):
        ax.axis("on")
        draw(ax, b, cache)

    out = os.path.join(ROOT, "captures", "layout-preview.png")
    fig.tight_layout()
    fig.savefig(out, dpi=130, facecolor="#101015")
    print("wrote %s  (%d bearing%s)"
          % (out, len(bearings), "" if len(bearings) == 1 else "s"))


if __name__ == "__main__":
    main()
