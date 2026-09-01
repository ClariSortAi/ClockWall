"""Does any part of the movement occupy the same space as another one.

    .venv-cad\\Scripts\\python.exe tools/interfere_check.py

This replaces what clash_check.py used to do for the moving parts, and it
replaces it because the old test could no longer be right. That one crossed a
2D footprint with a z span, which is a fair proxy for flat extrusions and a bad
one for real solids: a balance cock is a foot on the plate and an arm RAISED
over the balance, so its footprint covers the balance and its z span overlaps
the balance, and it still touches nothing. A check that reports that as a clash
gets switched off, and then it is not a check.

So this asks the only question that actually has an answer - what is the volume
of the boolean intersection - using the CAD skill's `inspect interfere`.

WHAT COUNTS AS A CLASH. Not "any contact". A watch is full of parts that share
space on purpose: a pallet stone is cemented into a slot cut for it, a collet is
driven onto a staff, an arbor turns inside a jewel it passes through. Those are
press fits and bearings, they are listed below with the reason, and finding them
is the check working. Anything NOT on that list is a part passing through
another part.

Volumes are reported in real cubic millimetres. The assembly is built in face
units, where one millimetre of watch is 11.78 units, so a raw face-unit volume
is 1634x too large and reads as alarming when it is nothing.

WHEN TO RUN IT. After anything that moves a part: a new entry in the generator's
STACK, a changed bearing, a new datum. Not on every render. It rebuilds the STEP
and runs a boolean per pair, which costs minutes, and its answer cannot change
when only a material or a light does.
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, "models", "step", "movement.step.py")
INSPECT = os.path.join(ROOT, ".claude", "skills", "cad", "scripts", "inspect")
MANIFEST = os.path.join(ROOT, "captures", "cad", "manifest.json")

# Pairs that are SUPPOSED to be in contact, each with the mechanical reason.
# Copied in spirit from clash_check's own list, which got this idea right.
EXPECTED = {
    frozenset(("lever", "stone_a")):   "pallet stone cemented into its slot",
    frozenset(("lever", "stone_b")):   "pallet stone cemented into its slot",
    frozenset(("staff", "collet")):    "hairspring collet driven onto the staff",
    frozenset(("staff", "roller")):    "roller table driven onto the staff",
    frozenset(("staff", "balance")):   "balance riveted to its staff",
    frozenset(("staff", "cock")):      "the staff's upper pivot runs in the cock",
    frozenset(("staff", "jewel_b")):   "pivot turning inside its jewel",
    frozenset(("staff", "jewel_c")):   "the upper pivot, in the bridge's jewel",
    frozenset(("epinion", "jewel_e")): "pivot turning inside its jewel",
    frozenset(("tpinion", "jewel_t")): "pivot turning inside its jewel",
    frozenset(("lever", "jewel_p")):   "pivot turning inside its jewel",
    frozenset(("escape", "epinion")):  "escape wheel riveted to its pinion",
    frozenset(("train", "tpinion")):   "fourth wheel riveted to its pinion",
    frozenset(("epinion", "train")):   "the mesh itself - teeth between leaves",
    frozenset(("balance", "cock")):    "the bridge arches over the balance",
    frozenset(("cock", "jewel_c")):    "the jewel, seated in the bridge's bore",
    frozenset(("cock", "screw_1")):    "the screw head clamping the bridge foot",
    frozenset(("spring", "collet")):   "the hairspring's inner end, pinned",
    frozenset(("guard", "lever")):     "the guard dart, set in the lever",
}

# Above this, in real cubic millimetres, an EXPECTED contact stops being a fit
# and starts being a mistake. A watch press fit is an interference of a few
# microns over a small area; a hundredth of a cubic millimetre is already
# generous. This is what stops the list above from becoming a blanket amnesty.
CONTACT_LIMIT_MM3 = 0.10


def part_of(label):
    """`escape [escapement] <- OM10 OM00-00101` -> `escape`."""
    return label.split(" ", 1)[0]


def main():
    with open(MANIFEST) as f:
        scale = json.load(f)["scale"]
    per_mm3 = scale ** 3

    proc = subprocess.run(
        [sys.executable, INSPECT, "interfere", ENTRY,
         "--tolerance", "0.5", "--format", "json"],
        capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0 and not proc.stdout.strip():
        print(proc.stderr[-2000:], file=sys.stderr)
        raise SystemExit("inspect interfere failed to run")

    report = json.loads(proc.stdout)
    pairs = report.get("clashes", [])

    unexpected, contacts = [], []
    for c in pairs:
        a = part_of(c["a"]["name"])
        b = part_of(c["b"]["name"])
        vol = c["volume"] / per_mm3
        key = frozenset((a, b))
        if key in EXPECTED and vol <= CONTACT_LIMIT_MM3:
            contacts.append((vol, a, b, EXPECTED[key]))
        else:
            unexpected.append((vol, a, b, EXPECTED.get(key)))

    for vol, a, b, why in sorted(contacts, reverse=True):
        print("  contact  %-8s x %-8s %8.4f mm3   %s" % (a, b, vol, why))

    if not unexpected:
        print("\n%d expected contacts, no part passes through another."
              % len(contacts))
        return 0

    print()
    for vol, a, b, why in sorted(unexpected, reverse=True):
        note = ("EXCEEDS the %.2f mm3 contact limit - %s" % (CONTACT_LIMIT_MM3, why)
                if why else "not a fit anyone declared")
        print("CLASH    %-8s x %-8s %8.4f mm3   %s" % (a, b, vol, note))
    print("\n%d pair(s) share space they should not." % len(unexpected))
    return 1


if __name__ == "__main__":
    sys.exit(main())
