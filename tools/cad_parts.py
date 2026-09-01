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
import os
import sys

from build123d import export_stl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATOR = os.path.join(ROOT, "models", "step", "movement.step.py")
OUT = os.path.join(ROOT, "captures", "cad")

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

    payload = {
        "scale": place.SCALE,
        "rotation": place.ROT_DEG,
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
