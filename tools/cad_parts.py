"""Writes the placed movement out for the renderer.

    .venv-cad\\Scripts\\python.exe tools/cad_parts.py

The assembly itself is models/step/movement.step.py - real OM10 solids carried
into the face by one similarity transform. This is the bridge from that to the
render: one STL per part, already in face coordinates with its z set, plus a
manifest saying what each part is made of, which arbor it turns about, and where
that arbor is.

WHY THE STL IS WRITTEN HERE AND NOT BY scripts/export. The renderer needs the
parts SEPARATELY - each rotating group is its own image, because XAML turns
images - and a single exported assembly is one mesh. Splitting it afterwards
would mean matching solids back to names by size, which is exactly the guessing
this whole rewrite exists to stop doing.

The pivots are the other output and they matter as much. OpenworkedFace.xaml
turns each layer about a centre, and that centre has to be the axis the solid
was placed on. Emitting both from the same placement is what makes it impossible
for them to disagree - previously the XAML held a hand-copied transcript of a
JSON file, and re-copying it was a step somebody had to remember.
"""

import importlib.util
import json
import math
import os
import sys

import numpy as np
import trimesh
from build123d import export_stl
from shapely.geometry import Polygon
from trimesh.path import polygons as tp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(ROOT, "models", "step", "movement.step.py")
OUT = os.path.join(ROOT, "captures", "cad")
OM10 = os.path.join(ROOT, "captures", "om10", "parts")

# How finely the solids are tessellated for the render. At 3 px per face unit a
# 0.05 unit deviation is a sixth of a pixel, which is under what the camera can
# resolve - and the angular tolerance is what actually decides whether a turned
# rim looks turned, because it sets how many facets go round a circle.
TOLERANCE = 0.05
ANGULAR_TOLERANCE = 0.12


def load_entry(path):
    """A `.step.py` cannot be imported by name; load it by path."""
    spec = importlib.util.spec_from_file_location("movement_step", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Parts whose tooth count is load-bearing, and what it must be. These set the
# beat and every rotation rate downstream, so a wrong one is not a cosmetic
# error - it is a watch that runs at the wrong speed.
#
# THIS GUARD EXISTS BECAUSE THE HAZARD IS AN ORDERING, WHICH IS INVISIBLE.
# om10_extract.py writes provisional tooth counts from raw triangulation
# vertices and gets them wrong; om10_check.py recounts properly and overwrites
# them. Re-running the extractor therefore silently puts the bad numbers back,
# and the first symptom was a train ratio of 84/0. Nothing about the STL export
# looked wrong, because nothing about it was.
EXPECTED_TEETH = {"escape": 20, "epinion": 8, "wheel_c": 84}


def check_teeth(manifest):
    """Refuse to export against tooth counts that have been clobbered."""
    wrong = {k: manifest[k]["teeth"] for k, want in EXPECTED_TEETH.items()
             if manifest[k]["teeth"] != want}
    if wrong:
        raise SystemExit(
            "tooth counts are wrong: %s (expected %s).\n"
            "This is almost always om10_extract.py having been re-run after "
            "om10_check.py - the extractor's counts are provisional and it "
            "overwrites the good ones. Run:\n"
            "    .venv-cad\\Scripts\\python.exe tools/om10_check.py"
            % (wrong, {k: EXPECTED_TEETH[k] for k in wrong}))


# How far a pivot may sit from the bore drilled for it, in face units, before
# the mainplate is not the plate this movement runs in. The four bores come out
# within a tenth of a unit, which is the same coincidence-that-is-not-a-
# coincidence as the cock's jewel landing on the balance arbor: the plate and
# the parts were placed by the SAME similarity, so a real bore has to arrive
# under a real pivot or something upstream is wrong.
BORE_TOLERANCE = 1.0

# The plan rings are simplified to this, in face units. Three asset pixels per
# unit, so a fifth of a unit is well under a pixel and the JSON stays small
# enough that export_profiles reads it without noticing.
RING_SIMPLIFY = 0.20


def mainplate_drilling(place, axis):
    """
    The real mainplate's plan - its outline and every hole - in face units.

    WHY THIS IS EMITTED HERE. The plate is drawn by escapement_geometry, which
    runs under the SYSTEM interpreter because render.ps1 needs it to; the
    drilling can only be read off the OM10 solid, which needs trimesh, which
    lives in .venv-cad. So the drilling crosses the same way the parts do: this
    file measures it once and writes it into the manifest, and the drawing side
    reads face coordinates and never learns what a STEP is.

    WHY THE PLAN AND NOT THE SOLID. The camera is orthographic and points
    straight down, so what a plate contributes to the picture is its top face,
    its bores and the walls of those bores. The OM10's own plate is 2.5 mm -
    29.5 face units - against the 6.5 this face uses, for the same reason the
    jewels cannot inherit their depth: the stack here is compressed. Extruding
    the real plan to the face's own thickness keeps every millimetre of the
    real drilling and drops the one dimension that cannot come across.

    NOTE the plate covers 88% of the aperture and no more: it is a 366-unit
    disc whose centre sits 92 units from a 252-unit opening, so the opening
    reaches 218 units from the plate's centre against a 183-unit radius. What
    is shown through the window is a REGION of the real plate, and the far
    upper-left crescent of the opening is the only part of it that is still
    ours. Nothing is drilled there, because the real plate does not reach.
    """
    mesh = trimesh.load(os.path.join(OM10, "mainplate.stl"), process=False)
    plan = tp.projected(mesh, normal=[0, 0, 1])

    # The extractor centred this solid on its own bounding-box centre, and
    # recorded that point as its `axis`. Carry THAT into the face, or the whole
    # plate lands a couple of units out and every bore misses its pivot.
    fx, fy = place.to_face(axis[0], axis[1])
    # The STL's own frame has y up and the face's runs down, so flip BEFORE
    # rotating - rotating first turns the plate the other way, which is the
    # trap movement.step.py's place() records in its own comment.
    th = math.radians(place.ROT_DEG)
    cos_t, sin_t = math.cos(th), math.sin(th)

    def to_face(ring):
        pts = np.asarray(ring.coords)
        u = pts[:, 0] * place.SCALE
        v = -pts[:, 1] * place.SCALE
        return Polygon(np.column_stack((fx + u * cos_t - v * sin_t,
                                        fy + u * sin_t + v * cos_t)))

    outline = to_face(plan.exterior).simplify(RING_SIMPLIFY)
    holes = [to_face(r).simplify(RING_SIMPLIFY) for r in plan.interiors]

    # The bore under each pivot, so the plate can size a chaton to it and
    # placement_invariants can assert it is there at all.
    bores = {}
    for arbor in ("balance", "pallet", "escape", "fourth"):
        px, py = place.axis_face(arbor)
        near = min(holes, key=lambda h, p=(px, py):
                   math.hypot(h.centroid.x - p[0], h.centroid.y - p[1]))
        d = math.hypot(near.centroid.x - px, near.centroid.y - py)
        if d > BORE_TOLERANCE:
            raise SystemExit(
                "No bore in the OM10 mainplate under the %s pivot: nearest "
                "hole is %.2f face units away, limit %.1f. The plate and the "
                "parts are placed by the same transform, so this means the "
                "transform changed under one of them." % (arbor, d, BORE_TOLERANCE))
        bores[arbor] = [near.centroid.x, near.centroid.y,
                        math.sqrt(near.area / math.pi), d]

    return {
        "source": "OM10-00214",
        "outline": [[round(x, 2), round(y, 2)] for x, y in outline.exterior.coords],
        "holes": [[[round(x, 2), round(y, 2)] for x, y in h.exterior.coords]
                  for h in holes],
        "bores": bores,
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    gen = load_entry(GENERATOR)
    assembly = gen.gen_step()
    manifest = gen._manifest()
    check_teeth(manifest)
    place = gen.PLACE

    parts = []
    for (name, src, arbor, material, _at, _tz), child in zip(gen.STACK, assembly.children):
        path = os.path.join(OUT, "%s.stl" % name)
        export_stl(child, path, tolerance=TOLERANCE,
                   angular_tolerance=ANGULAR_TOLERANCE)
        box = child.bounding_box()
        parts.append({
            "name": name,
            "material": material,
            "arbor": arbor,
            "stl": path.replace("\\", "/"),
            # Face coordinates, y down - the frame profiles.json speaks.
            "z": box.min.Z,
            "thickness": box.max.Z - box.min.Z,
            "bbox": [box.min.X, -box.max.Y, box.max.X, -box.min.Y],
            "source": manifest[src]["source"],
            "teeth": manifest[src]["teeth"],
            # Face units, and only the parts this project builds itself carry
            # one. A solid lifted out of the OM10 already HAS its chamfers cut
            # into the B-rep, and render_lib is explicit that bevelling those
            # again would round off the very edges that were the reason to use
            # real CAD. A prism we extruded ourselves has no chamfer at all
            # until something puts one on, and the reference photos make that
            # edge the brightest thing on the part.
            "bevel": manifest[src].get("bevel_units"),
            "kb": os.path.getsize(path) // 1024,
        })
        print("  %-9s %-11s z %5.1f..%5.1f  %4d KB  <- OM10 %s"
              % (name, material, box.min.Z, box.max.Z,
                 parts[-1]["kb"], manifest[src]["source"]), flush=True)

    plate = mainplate_drilling(place, manifest["mainplate"]["axis"])
    print("\nmainplate %s: %d holes, a bore under every pivot"
          % (plate["source"], len(plate["holes"])))
    for arbor, (bx, by, br, d) in plate["bores"].items():
        print("  %-8s bore at (%6.1f,%6.1f) r %5.2f  %.2f units off the pivot"
              % (arbor, bx, by, br, d))

    payload = {
        "scale": place.SCALE,
        "rotation": place.ROT_DEG,
        "mainplate": plate,
        "pivots": {k: list(place.axis_face(k))
                   for k in ("balance", "pallet", "escape", "fourth")},
        "teeth": {
            "escape": manifest["escape"]["teeth"],
            "escape_pinion": manifest["epinion"]["teeth"],
            "fourth": manifest["wheel_c"]["teeth"],
        },
        "parts": parts,
    }
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(payload, f, indent=1)

    print("\nscale %.3f face units/mm, rotation %.2f deg" % (place.SCALE, place.ROT_DEG))
    print("teeth: escape %d, escape pinion %d, fourth wheel %d  (ratio %.4f)"
          % (payload["teeth"]["escape"], payload["teeth"]["escape_pinion"],
             payload["teeth"]["fourth"],
             payload["teeth"]["fourth"] / payload["teeth"]["escape_pinion"]))
    print("pivots, for OpenworkedFace.xaml:")
    for k, v in payload["pivots"].items():
        print('    %-8s CenterX="%.1f" CenterY="%.1f"' % (k, v[0], v[1]))
    print("\nwrote %s" % os.path.join(OUT, "manifest.json"))


if __name__ == "__main__":
    main()
