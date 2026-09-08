"""The mainspring, designed into the OM10's barrel.

    python tools/mainspring.py        # -> adds "mainspring" to Assets/mechanism.json, models/step/mainspring.step
    (tools/gltf_export.py then adds the solid to Assets/movement.glb)

WHY. The OM10 STEP has no mainspring - the disc first taken for one is the
ratchet wheel - so the mechanism's torque was a typical figure. This makes
the spring a spring: a strip whose section and length are chosen for the
barrel it has to live in, whose torque at each state of wind follows from
those, and whose reserve follows from the barrel's turns. The barrel's
cavity is measured off the OM10's own barrel solids, not assumed.

THE DESIGN, the way a barrel is sized:
  1. Measure the cavity: the inner wall radius and the height between the
     floor and the cover, and the arbor's radius.
  2. The spring fills half the annulus between arbor and wall, which is the
     classic optimum for the number of turns it gives.
  3. Choose the thickness (0.14 mm, an ordinary gauge for a barrel this
     size); the length follows from the area, the width from the cavity.
  4. Turns: the spring coiled on the arbor against coiled on the wall.
  5. Torque per turn from the strip: E w t^3 (2 pi) / (12 L), plus a
     residual of turns it keeps when 'run down' because it is hooked in
     under preload; the train's friction is the torque below which the
     escapement cannot keep the balance above the lift angle, and that is
     where the watch stops.

Everything comes out in Assets/mechanism.json; nothing is typed into C#.
"""

import json
import math
import os
import sys

import numpy as np
import trimesh
from build123d import Location, Polyline, export_step, extrude, make_face

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gltf_export as G                                       # noqa: E402

E = 200e9            # Pa, a carbon or cobalt spring steel
THICKNESS = 0.14e-3  # m
DENSITY = 7800.0
RESIDUAL_TURNS = 1.5     # hooked in under this much preload; never unwinds past it
FRICTION_FRACTION = 0.12 # of full torque: the train's own resistance, where the watch stops

BARREL_AXIS = (6.67, -3.77)   # CAD (x, z), off the catalogue
BARREL_PARTS = ("barrel", "barrel_drum", "barrel_cover", "barrel_arbor")


def mesh_of(name):
    tag = {v: k for k, v in G.NAMES.items()}[name]
    v, n, f = G.tessellate_shape(G.read_step(os.path.join(G.PARTS, tag.replace("#", "_") + ".step")), 0.01, 0.2)
    return trimesh.Trimesh(vertices=v, faces=f, process=False)


def measure_cavity():
    """Radii and height of the empty space inside the barrel, off the barrel
    solids' cross-sections. A section of the shell at a height inside the
    cavity has vertices only at the arbor bore, any hub, and the wall; the
    wall's inner radius is the smallest section radius beyond the hubs.
    Sections rather than point-in-solid tests: the ray test this used first
    flaked on the thin wall and once read it at 4.64 mm instead of 6.65."""
    shell = trimesh.util.concatenate([mesh_of(n) for n in ("barrel", "barrel_drum", "barrel_cover")])
    arbor = mesh_of("barrel_arbor")
    cx, cz = BARREL_AXIS
    walls, heights = [], []
    for y in np.linspace(-1.3, 1.2, 51):
        sec = shell.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
        if sec is None:
            continue
        r = np.hypot(*(np.array(sec.vertices)[:, [0, 2]] - np.array(BARREL_AXIS)).T)
        # Inside the cavity there is nothing between the hub radius and the wall.
        hollow = not ((r > 3.0) & (r < 5.0)).any()
        if hollow and (r > 5.0).any():
            walls.append(r[r > 5.0].min())
            heights.append(y)
    arbor_r = float(np.hypot(*(arbor.vertices[:, [0, 2]] - np.array(BARREL_AXIS)).T).max())
    return dict(inner_wall=float(np.median(walls)), arbor=arbor_r, floor=float(min(heights)), ceiling=float(max(heights)))


def design(cavity):
    R = cavity["inner_wall"] * 1e-3
    r = cavity["arbor"] * 1e-3
    height = (cavity["ceiling"] - cavity["floor"]) * 1e-3
    width = height - 0.10e-3                 # a tenth clear of floor and cover
    t = THICKNESS
    area = math.pi * (R * R - r * r) / 2     # half the annulus
    length = area / t
    # Coiled against the wall it fills from R inward to R1; on the arbor
    # from r outward to R2. Turns available is the difference.
    R1 = math.sqrt(R * R - length * t / math.pi)
    R2 = math.sqrt(r * r + length * t / math.pi)
    turns_wall = (R - R1) / t
    turns_arbor = (R2 - r) / t
    turns = turns_arbor - turns_wall
    torque_per_turn = E * width * t ** 3 * 2 * math.pi / (12 * length)
    torque_full = torque_per_turn * turns
    return dict(inner_wall=R, arbor=r, width=width, thickness=t, length=length,
                turns_total=turns, turns_residual=RESIDUAL_TURNS,
                turns_usable=turns - RESIDUAL_TURNS,
                torque_per_turn=torque_per_turn, torque_full=torque_full,
                torque_residual=torque_per_turn * RESIDUAL_TURNS,
                friction_torque=torque_full * FRICTION_FRACTION,
                coil_r_on_arbor=R2, coil_r_on_wall=R1, mass=DENSITY * width * t * length)


def build(cavity, d):
    """The strip as a solid, coiled on the arbor (full wind), in the OM10's
    frame. Hidden under the dial in the render; here so the object is whole."""
    r0 = d["arbor"] * 1e3 + 0.02
    r1 = d["coil_r_on_arbor"] * 1e3
    t = d["thickness"] * 1e3
    turns = (r1 - r0) / t
    steps = int(turns * 90)
    half = t / 2 * 0.85    # a hair under the pitch, so adjacent coils do not fuse into one solid
    outer, inner = [], []
    for k in range(steps + 1):
        th = 2 * math.pi * turns * k / steps
        rad = r0 + (r1 - r0) * k / steps
        c, s = math.cos(th), -math.sin(th)
        outer.append(((rad + half) * c, (rad + half) * s))
        inner.append(((rad - half) * c, (rad - half) * s))
    pts = outer + inner[::-1]
    strip = extrude(make_face(Polyline(*pts, pts[0])), d["width"] * 1e3)
    y0 = cavity["floor"] + 0.05
    return strip.moved(Location((BARREL_AXIS[0], y0, BARREL_AXIS[1]), (-90, 0, 0)))


def main():
    cavity = measure_cavity()
    d = design(cavity)
    strip = build(cavity, d)
    path = os.path.join(ROOT, "Assets", "mechanism.json")
    doc = json.load(open(path)) if os.path.exists(path) else {}
    doc["mainspring"] = {**{k: (float(v) if isinstance(v, (int, float)) else v) for k, v in d.items()},
                         "cavity_mm": cavity, "youngs_modulus": E, "friction_fraction": FRICTION_FRACTION,
                         "note": "Designed into the OM10's measured barrel cavity; the STEP carries no mainspring."}
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)
    export_step(strip, os.path.join(ROOT, "models", "step", "mainspring.step"))
    print("  cavity: wall r %.2f, arbor r %.2f, floor %.2f, ceiling %.2f mm" % (cavity["inner_wall"], cavity["arbor"], cavity["floor"], cavity["ceiling"]))
    print("  strip %.2f x %.2f mm, %.0f mm long; %.1f turns of which %.1f usable; %.2f N mm full, %.2f residual, friction %.2f"
          % (d["thickness"] * 1e3, d["width"] * 1e3, d["length"] * 1e3, d["turns_total"], d["turns_usable"],
             d["torque_full"] * 1e3, d["torque_residual"] * 1e3, d["friction_torque"] * 1e3))
    print("  reserve at 6.69 h per barrel turn: %.1f h" % (d["turns_usable"] * 107 / 16))
    print("  wrote mainspring into Assets/mechanism.json and models/step/mainspring.step (volume %.2f mm3)" % strip.volume)


if __name__ == "__main__":
    main()
