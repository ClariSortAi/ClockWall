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
# WHAT IS STILL DRAWN HERE, now that the movement itself is real.
#
# Only the things that are ours: the plate this face cuts its aperture in, the
# floor behind it so a bore reads as a bore, and the steel collars the jewels sit
# in. Every moving part - and the cock over them - is an OM10 solid placed by
# models/step/movement.step.py and arrives through captures/cad/manifest.json.
#
# The rubies used to be drawn here too. They are gone because there is now a
# real jewel, with a real olive bore, fitted at all four pivots.
STACK = [
    # A floor below the plate, so a bore reads as a bore. Drill through a plate
    # with nothing behind it and every hole renders as a black disc.
    ("floor", -5.0, 4.0, "floor"),
    ("plate", 0.0, 6.5, "plate"),

    # The steel collars the jewels are pressed into, countersunk in the plate.
    ("collars", 1.4, 5.0, "steel"),

]


CAD = os.path.join("captures", "cad", "manifest.json")


def cad_parts():
    """
    The movement, as real solids rather than outlines.

    Each entry names an STL that render_lib imports instead of extruding - the
    part already has its chamfers, its turned steps and its tooth flanks, and
    the extrude-and-bevel path would only round them off. `rings` stays empty
    on purpose: there is no 2D outline to fill, and anything put there would be
    a second, worse description of a part that is already fully described.
    """
    with open(CAD) as f:
        payload = json.load(f)
    specs = []
    for p in payload["parts"]:
        specs.append({
            "name": p["name"], "z": p["z"], "thickness": p["thickness"],
            "material": p["material"], "open": False, "rings": [],
            "stl": p["stl"], "solid": True, "arbor": p["arbor"],
            "source": p["source"], "bevel": p.get("bevel"),
        })
    return payload, specs


def main():
    parts = eg.build()

    cad, cad_specs = cad_parts()

    # The chatons, sized to the OM10's own bores against the OM10's own jewel.
    # The stone's radius is read off the placed solid rather than typed: it is
    # the same part fitted at four bearings, and what decides whether a bearing
    # gets a setting at all is how that radius compares with the hole.
    jewel = next(p for p in cad["parts"] if p["name"] == "jewel_e")
    parts["collars"] = eg.collars((jewel["bbox"][2] - jewel["bbox"][0]) / 2.0)

    # Everything is clipped to the opening. The dial covers the rest, so a part
    # that runs past the edge - the train wheel does, deliberately - simply
    # stops there, exactly as it would if you were looking through the hole.
    ax, ay, ar = eg.APERTURE
    window = eg.disc(ax, ay, ar - 1.0, 320)

    payload = {
        "face": 640,
        "aperture": list(eg.APERTURE),
        # Centres of rotation, so the render and the XAML cannot disagree about
        # where a wheel turns. These come from the CAD placement, which is the
        # same transform that positioned the solids - so a pivot and the part it
        # turns are the same point by construction, not by transcription.
        "pivots": {
            "escape": cad["pivots"]["escape"],
            "train": cad["pivots"]["fourth"],
            "balance": cad["pivots"]["balance"],
            "spring": cad["pivots"]["balance"],
            "fork": cad["pivots"]["pallet"],
        },
        "train_ratio": eg.TRAIN_RATIO,
        "escape_teeth": eg.ESCAPE_TEETH,
        "vph": eg.VPH,
        "amplitude": eg.BALANCE_AMPLITUDE,
        "scale": cad["scale"],
        "parts": list(cad_specs),
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
    solids = sum(1 for p in payload["parts"] if p.get("stl"))
    print("wrote %s (%d movement parts, %d of them real CAD solids; "
          "%d case + %d hand, %d KB)"
          % (OUT, len(payload["parts"]), solids, len(payload["case"]),
             len(payload["hands"]), os.path.getsize(OUT) // 1024))
    print("  escapement: %d-tooth escape wheel, %d-leaf pinion, %d-tooth fourth "
          "wheel, ratio %.4f"
          % (eg.ESCAPE_TEETH, eg.ESCAPE_PINION_LEAVES, eg.TRAIN_TEETH,
             eg.TRAIN_RATIO))

    # The pivots are the one thing OpenworkedFace.xaml has to copy by hand, so
    # print them in the form it wants them rather than leaving somebody to
    # transcribe a JSON file into XML attributes.
    print("  pivots for OpenworkedFace.xaml:")
    for _k, _v in payload["pivots"].items():
        print('    %-8s CenterX="%.1f" CenterY="%.1f"' % (_k, _v[0], _v[1]))


if __name__ == "__main__":
    main()
