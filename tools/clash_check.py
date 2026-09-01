"""Finds parts that occupy the same space, which no assembly may do.

    python tools/clash_check.py

WHY. Everything else here checks one relationship at a time - do the stones
alternate, is the train in mesh, does the fork reach the roller. This checks the
one rule that applies to every pair at once: two solids cannot be in the same
place. It is the check that would have found, without being asked, that the
pallet fork's slot had nothing to receive and that the hairspring's outer end
was pinned to thin air.

HOW IT WORKS. Each part is a footprint plus a z span, so a clash is simply an
overlap in BOTH. Plan-view overlap alone is fine and expected - a watch is a
stack, and the whole illusion of depth in a straight-down view comes from parts
lying over each other. Overlapping in z as well is the error.

Two exemptions, and they are real rather than convenient:
  * parts that TOUCH on purpose - a wheel and the pinion on its own arbor, a
    collet on the same, teeth that mesh, a stone against the tooth it locks.
  * the plate and the floor, which everything is meant to sit over.
Anything else that shares space is a part passing through another part.

Exit code is non-zero when it finds one, so this can gate a render.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import escapement_geometry as eg                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES = os.path.join(ROOT, "captures", "geom", "profiles.json")

# Ground, and the things everything is allowed to stand on.
GROUND = {"floor", "plate"}

# Pairs that are SUPPOSED to be in contact. Each is a real mechanical
# relationship, not a way of quieting the check.
ALLOWED = {
    frozenset(("escape", "epinion")),      # one arbor
    frozenset(("escape", "ecollet")),
    frozenset(("epinion", "ecollet")),
    frozenset(("train", "tpinion")),
    frozenset(("train", "tcollet")),
    frozenset(("tpinion", "tcollet")),
    frozenset(("train", "epinion")),       # the mesh itself
    frozenset(("fork", "stones")),         # stones set into the lever
    frozenset(("stones", "escape")),       # the lock
    frozenset(("balance", "bscrews")),     # screws threaded into the rim
    frozenset(("balance", "roller")),      # both on the staff
    frozenset(("roller", "impulse")),      # jewel set in the roller
    frozenset(("balance", "spring")),      # collet on the staff
    frozenset(("spring", "stud")),         # the outer end, pinned
    frozenset(("cock", "stud")),           # the stud is carried by the cock
    frozenset(("cock", "screws")),
    frozenset(("balance", "impulse")),     # pin rides on the staff assembly
}


def main():
    with open(PROFILES) as f:
        payload = json.load(f)

    parts = {}
    solids = set()
    for spec in payload["parts"]:
        z0 = spec["z"]
        parts[spec["name"]] = (z0, z0 + spec["thickness"])
        if spec.get("stl"):
            solids.add(spec["name"])

    geoms = eg.build()

    def foot(name):
        g = geoms[name]
        return g.buffer(0.6) if g.geom_type in ("LineString", "MultiLineString") else g

    # THE REAL PARTS ARE NOT CHECKED HERE, AND MUST NOT BE.
    #
    # This test is a footprint crossed with a z span, which was a fair proxy
    # while every part was a flat extrusion of that exact footprint. It is not
    # one for a real solid. A balance cock is a foot on the plate and an arm
    # RAISED over the balance: its footprint covers the balance and its z span
    # overlaps the balance, and it still does not touch it anywhere. Run this
    # against the OM10 solids and it reports a clash that is not there - and the
    # cure for a check that cries wolf is always to switch it off.
    #
    # Worse, the footprints here come from escapement_geometry's own drawings,
    # which are no longer what gets rendered. Comparing an old outline against a
    # new solid's height is not a weaker check, it is a check of nothing.
    #
    # The solids are checked properly instead, by boolean intersection volume:
    #     .venv-cad\Scripts\python.exe tools/interfere_check.py
    #
    # That is NOT run from here or from render.ps1, deliberately. It rebuilds
    # the STEP and runs a boolean intersection per pair, which costs minutes,
    # and its answer can only change when the PLACEMENT changes - not when a
    # material or a light does. So it belongs beside cad_parts.py, run when the
    # assembly moves, rather than on the front of every render where the cost
    # would be paid for nothing and would eventually get skipped.
    names = [n for n in parts
             if n in geoms and n not in GROUND and n not in solids]
    if solids:
        print("%d CAD solids checked by boolean intersection, not here: %s"
              % (len(solids), ", ".join(sorted(solids))))
    clashes = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if frozenset((a, b)) in ALLOWED:
                continue
            az, bz = parts[a], parts[b]
            overlap_z = min(az[1], bz[1]) - max(az[0], bz[0])
            if overlap_z <= 0:
                continue
            ga, gb = foot(a), foot(b)
            if not ga.intersects(gb):
                continue
            area = ga.intersection(gb).area
            if area < 0.5:
                continue
            clashes.append((area, overlap_z, a, b, az, bz))

    for area, dz, a, b, az, bz in sorted(clashes, reverse=True):
        print("CLASH  %-8s z %.1f-%.1f  vs  %-8s z %.1f-%.1f   "
              "sharing %.1f in z over %.0f sq units"
              % (a, az[0], az[1], b, bz[0], bz[1], dz, area))

    if not clashes:
        print("no clashes: every pair either misses in plan or is clear in z")
        return 0
    print("\n%d pair(s) occupying the same space." % len(clashes))
    return 1


if __name__ == "__main__":
    sys.exit(main())
