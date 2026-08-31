"""Dumps the 2D profiles to JSON so Blender can read them.

Blender ships its own Python and will not have shapely in it, so the boolean
work stays here and only the finished rings cross over. Face coordinates
throughout - the render camera is framed to the same 640x640 box, which is what
lets a rendered part drop into the XAML with no alignment guesswork.

    python tools/export_profiles.py
"""

import json
import os

import case_geometry as cg
import escapement_geometry as eg

OUT = "captures/geom/profiles.json"

# z is the height of a part's underside above the mainplate, thickness its
# depth. Both in face units, and BOTH MATTER MORE THAN ANY SHADER SETTING.
#
# This camera is orthographic and points straight down, so no part in the scene
# has a visible side. A flat top face under a distant lamp is one uniform tone -
# which is why three passes of shader tuning produced flat stickers. What can
# actually shade is an interior wall: the inside of a bore, the wall of a rim,
# the gap between two teeth. Those exist only because the numbers below put
# real distance between things.
#
# So the plate is thick enough for its bores to have visible walls, the jewels
# are COUNTERSUNK inside those bores rather than resting on top, and every
# pinion sits far enough under its wheel to be seen through the crossings.
#
# TWO THINGS IN MESH MUST OVERLAP IN Z. The train wheel and the escape pinion
# are drawn interleaved in plan and were at different heights, so the mesh they
# appeared to make was impossible. Their spans now cross.
STACK = [
    # A floor below the plate, so a bore reads as a bore. Drill through a plate
    # with nothing behind it and every hole renders as a black disc.
    ("floor", -5.0, 4.0, "floor"),
    ("plate", 0.0, 6.5, "plate"),

    # Jewels, sunk into the plate's bores. Their tops finish a hair below the
    # plate surface - that is what countersunk means, and it is the difference
    # between a jewelled bearing and a red sticker.
    ("collars", 1.4, 5.0, "steel"),
    ("rubies", 2.6, 3.2, "ruby"),

    # The going train. tpinion is driven from behind the plate; the train wheel
    # drives epinion, and epinion carries the escape wheel.
    ("tpinion", 6.8, 2.6, "steel"),
    ("epinion", 9.4, 2.4, "steel"),        # spans 9.4-11.8
    ("train", 9.6, 2.0, "brass"),          # spans 9.6-11.6, so they mesh
    ("tcollet", 11.6, 1.8, "steel"),
    ("escape", 12.2, 1.8, "steel"),
    ("ecollet", 14.0, 1.6, "steel"),

    ("fork", 16.0, 2.2, "steel"),
    ("stones", 16.2, 2.0, "ruby"),

    # The spring belongs UNDER the wheel. Above the arms it read as rings laid
    # on top of the balance; below, it is what you see through the crossings.
    ("spring", 17.8, 1.0, "blued"),
    ("balance", 19.8, 3.6, "brass"),
    ("bscrews", 19.5, 4.2, "steel"),

    # The cock bridges over the lot, and the gap is large on purpose: it is the
    # deepest shadow in the aperture and most of what says this is a stack of
    # parts rather than a picture of one.
    ("cock", 29.0, 6.0, "steel"),
    ("screws", 35.0, 2.2, "blued"),
]


def main():
    parts = eg.build()

    collars, rubies, screws = eg.jewels_and_screws(
        *eg.BALANCE[:2], *eg.ESCAPE[:2], *eg.STAFF)
    parts["collars"], parts["rubies"], parts["screws"] = collars, rubies, screws

    # Everything is clipped to the opening. The dial covers the rest, so a part
    # that runs past the edge - the train wheel does, deliberately - simply
    # stops there, exactly as it would if you were looking through the hole.
    ax, ay, ar = eg.APERTURE
    window = eg.disc(ax, ay, ar - 1.0, 320)

    payload = {
        "face": 640,
        "aperture": list(eg.APERTURE),
        # Centres of rotation, so the render and the XAML cannot disagree about
        # where a wheel turns. OpenworkedFace reads these back out.
        "pivots": {
            "escape": list(eg.ESCAPE[:2]),
            "train": list(eg.TRAIN[:2]),
            "balance": list(eg.BALANCE[:2]),
            "spring": list(eg.BALANCE[:2]),
            "fork": list(eg.STAFF),
        },
        "train_ratio": eg.TRAIN_RATIO,
        "parts": [],
        "case": [],
        "hands": [],
    }

    for name, z, thickness, material in STACK:
        geom = parts[name]
        common = {"name": name, "z": z, "thickness": thickness, "material": material}

        if geom.geom_type == "LineString":
            payload["parts"].append(dict(
                common, open=True,
                rings=[[list(p) for p in geom.intersection(window).simplify(0.08).coords]]))
            continue

        clipped = geom.intersection(window).simplify(eg.SIMPLIFY, preserve_topology=True)
        if clipped.is_empty:
            continue
        payload["parts"].append(dict(
            common, open=False,
            rings=[[list(p) for p in r] for r in eg.rings(clipped)]))

    # The case is NOT clipped to the aperture - it is the part of the face
    # outside it. Each case part carries its own chamfer width, because an
    # applied index needs a bevel wider than the baton is thick (that is what
    # makes the roof) while the dial plate needs almost none.
    def emit(into, source, stack):
        for name, z, thickness, material, chamfer in stack:
            geom = source[name].simplify(eg.SIMPLIFY, preserve_topology=True)
            payload[into].append({
                "name": name, "z": z, "thickness": thickness,
                "material": material, "chamfer": chamfer, "open": False,
                "rings": [[list(p) for p in r] for r in eg.rings(geom)],
            })

    emit("case", cg.build(), cg.STACK)
    emit("hands", cg.build_hands(), cg.HAND_STACK)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(payload, f)
    print("wrote %s (%d movement + %d case + %d hand parts, %d KB)"
          % (OUT, len(payload["parts"]), len(payload["case"]),
             len(payload["hands"]), os.path.getsize(OUT) // 1024))


if __name__ == "__main__":
    main()
