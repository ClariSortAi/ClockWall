"""The mainspring: the OM10's own, measured, and the torque its strip gives.

    python tools/mainspring.py        # -> adds "mainspring" to Assets/mechanism.json

WHY. OM10-00120 is the mainspring. The catalogue had it as "barrel_drum" and
a note here said the STEP carried no spring at all; the drum is 00121, and
00120 is the 0.10 mm strip wound eleven and three-quarter turns inside it.
For a while a designed strip was added on top, and the assembly check found
the two in the same space - which is how the STEP's own spring was noticed.
So the spring is now the one that is there, and the mechanism's torque is
measured off it: thickness, height and length from the solid, in the cavity
the barrel's own solids enclose. Nothing here is chosen but the alloy's
modulus, the hooked-in residual, and the train's friction fraction; each is
named where it is set.

HOW. Exact point-in-solid tests (BRepClass3d_SolidClassifier) on the
B-rep solids, because a 0.1 mm strip is thinner than a mesh's error: a ray
test on the tessellation flaked and read the wall at 4.64 mm, and section
polygons would not build from three overlapping shells.
  - Four rays out from the barrel's axis at mid-height cross the strip
    once per coil: the crossings' width is the thickness, their count the
    turns, the first and last their radii. The strip's height is the
    spring's extent along the axis at one coil.
  - The cavity: the top of the drum's floor, the underside of the cover,
    the drum's inner wall, the arbor's hub, each found on a ray.
  - The length of an Archimedean spiral of n turns from r_in to r_out is
    n pi (r_in + r_out).

THE TORQUE, the way a barrel is figured:
  - per turn, E w t^3 (2 pi) / (12 L);
  - turns available: the strip coiled on the arbor against coiled on the
    wall, each from the area the strip occupies, minus the residual it keeps
    when 'run down' because it is hooked in under preload;
  - the train's friction is the torque below which the escapement cannot
    keep the balance above the lift angle, and that is where the watch stops.

Everything comes out in Assets/mechanism.json; nothing is typed into C#.
"""

import json
import math
import os
import sys

import numpy as np
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_IN, TopAbs_ON

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gltf_export as G                                       # noqa: E402

E = 200e9                # Pa, a carbon or cobalt spring steel: the alloy is not in the STEP
DENSITY = 7800.0
RESIDUAL_TURNS = 1.5     # hooked in under this much preload; never unwinds past it
FRICTION_FRACTION = 0.12 # of full torque: the train's own resistance, where the watch stops

BARREL_AXIS = (6.67, -3.77)   # CAD (x, z), off the catalogue
PARTS = ("mainspring", "barrel", "barrel_cover", "barrel_arbor")
STEP_R = 0.002                # mm, the scan pitch along a ray: a fiftieth of the strip


def classifiers():
    inv = {v: k for k, v in G.NAMES.items()}
    out = {}
    for n in PARTS:
        shape = G.read_step(os.path.join(G.PARTS, inv[n].replace("#", "_") + ".step"))
        out[n] = BRepClass3d_SolidClassifier(shape)
    return out


def inside(c, x, y, z):
    c.Perform(gp_Pnt(x, y, z), 1e-7)
    return c.State() in (TopAbs_IN, TopAbs_ON)


def measure():
    """The cavity and the strip, mm, off the barrel's four solids."""
    cls = classifiers()
    cx, cz = BARREL_AXIS
    spring, drum, cover, arbor = (cls[n] for n in PARTS)

    def at(c, r, y, ang=0.0):
        a = math.radians(ang)
        return inside(c, cx + r * math.cos(a), y, cz + r * math.sin(a))

    # The strip, on four rays at mid-height.
    counts, thick, r_in, r_out = [], [], [], []
    for ang in (0, 90, 180, 270):
        runs, on, start = [], False, 0.0
        for r in np.arange(0.8, 7.0, STEP_R):
            s = at(spring, r, 0.0, ang)
            if s and not on:
                on, start = True, r
            elif on and not s:
                on = False
                runs.append((start, r - STEP_R))
        counts.append(len(runs))
        thick += [b - a for a, b in runs]
        r_in.append(runs[0][0])
        r_out.append(runs[-1][1])
    turns = float(np.mean(counts))
    thickness = float(np.median(thick))
    # Height: the spring's extent along the axis at one coil's middle.
    r_coil = next(r for r in np.arange(2.5, 3.5, STEP_R) if at(spring, r, 0.0))
    ys = [y for y in np.arange(-1.6, 1.6, 0.005) if at(spring, r_coil, y)]
    height = float(max(ys) - min(ys) + 0.005)

    # The cavity: on a ray at r 4, the drum's floor from below and the
    # cover from above; at mid-height, the drum's wall outward and the
    # arbor's hub inward.
    floor = max(y for y in np.arange(-2.0, 0.0, 0.005) if at(drum, 4.0, y)) + 0.005
    ceiling = min(y for y in np.arange(0.0, 2.0, 0.005) if at(cover, 4.0, y))
    wall = next(r for r in np.arange(5.5, 7.5, STEP_R) if at(drum, r, 0.0))
    hub = max(r for r in np.arange(0.5, 2.5, STEP_R) if at(arbor, r, 0.0))
    return dict(cavity=dict(inner_wall=float(wall), arbor=float(hub), floor=float(floor), ceiling=float(ceiling)),
                strip=dict(thickness=thickness, height=height, turns_as_drawn=turns,
                           r_in=float(np.mean(r_in)), r_out=float(np.mean(r_out)),
                           length=float(math.pi * turns * (np.mean(r_in) + np.mean(r_out)))))


def design(m):
    """The torque curve the measured strip gives in the measured cavity, SI."""
    R = m["cavity"]["inner_wall"] * 1e-3
    r = m["cavity"]["arbor"] * 1e-3
    t = m["strip"]["thickness"] * 1e-3
    width = m["strip"]["height"] * 1e-3
    length = m["strip"]["length"] * 1e-3
    # Coiled against the wall it fills from R inward to R1; on the arbor
    # from r outward to R2. Turns available is the difference.
    R1 = math.sqrt(R * R - length * t / math.pi)
    R2 = math.sqrt(r * r + length * t / math.pi)
    turns = (R2 - r) / t - (R - R1) / t
    torque_per_turn = E * width * t ** 3 * 2 * math.pi / (12 * length)
    torque_full = torque_per_turn * turns
    return dict(inner_wall=R, arbor=r, width=width, thickness=t, length=length,
                turns_total=turns, turns_residual=RESIDUAL_TURNS,
                turns_usable=turns - RESIDUAL_TURNS,
                torque_per_turn=torque_per_turn, torque_full=torque_full,
                torque_residual=torque_per_turn * RESIDUAL_TURNS,
                friction_torque=torque_full * FRICTION_FRACTION,
                coil_r_on_arbor=R2, coil_r_on_wall=R1, mass=DENSITY * width * t * length)


def main():
    m = measure()
    d = design(m)
    path = os.path.join(ROOT, "Assets", "mechanism.json")
    doc = json.load(open(path)) if os.path.exists(path) else {}
    doc["mainspring"] = {**{k: float(v) for k, v in d.items()},
                         "cavity_mm": m["cavity"], "strip_mm": m["strip"],
                         "youngs_modulus": E, "friction_fraction": FRICTION_FRACTION,
                         "note": "OM10-00120, measured; the torque is that strip's in that cavity."}
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)
    c, s = m["cavity"], m["strip"]
    print("  cavity: wall r %.3f, arbor r %.3f, floor %.2f, ceiling %.2f mm" % (c["inner_wall"], c["arbor"], c["floor"], c["ceiling"]))
    print("  strip as drawn: %.3f thick, %.2f high, %.2f coils from r %.2f to %.2f, %.0f mm long"
          % (s["thickness"], s["height"], s["turns_as_drawn"], s["r_in"], s["r_out"], s["length"]))
    print("  %.1f turns of which %.1f usable; %.2f N mm full, %.2f residual, friction %.2f"
          % (d["turns_total"], d["turns_usable"], d["torque_full"] * 1e3, d["torque_residual"] * 1e3, d["friction_torque"] * 1e3))
    print("  reserve at 6.69 h per barrel turn: %.1f h" % (d["turns_usable"] * 107 / 16))
    print("  wrote mainspring into Assets/mechanism.json")


if __name__ == "__main__":
    main()
