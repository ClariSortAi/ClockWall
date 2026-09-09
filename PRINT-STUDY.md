# Could you print it?

The direction of travel is an object that could be made. This asks the cheapest
version of that question: what does a 3D printer do to a movement 30.8 mm
across, and what is left of it by the time the machine can hold every part?

    python tools/print_scale.py
    python tools/print_scale.py --json print.json

Every thickness below is measured off the OM10's own STEP through
`om10_extract_all.load`, the same loader the exporter uses, so a part is the
same solid here as it is on the wall. 166 solids, 108 distinct parts once the
twelve identical screws fold into one row.

## The answer

A 50 µm resin printer at 3x. That is a movement 104 mm across, every part
printing whole on a 218 mm plate, with eleven parts bought or turned instead of
printed. It will turn, but it will not keep time.

Everything else is either too coarse or too small:

| Printer | Scale | Movement | Plate | |
|---|---|---|---|---|
| FDM 0.4 mm nozzle | 9x | 278 mm | 210 mm | split the mainplate in two |
| MSLA resin 50 µm | 3x | 104 mm | 218 mm | prints whole |
| DLP resin 35 µm | 2x | 70 mm | 128 mm | prints whole |
| micro-SLA 2 µm | 1x | 17 mm | 50 mm | prints whole, at full size |

The last row is a bureau service rather than a machine anyone owns, and it is
in the table because it answers the question everyone asks first. Yes, the OM10
can be printed at its own size, by somebody else, for money.

## What sets the scale

The obvious constraint is wall thickness, since the parts are foils and a
printer has a minimum wall. It is not the one that binds. The running fits bind,
by a factor of four to six.

| Printer | Walls need | Fits need |
|---|---|---|
| FDM 0.4 mm | 9x | 128x |
| MSLA 50 µm | 3x | 64x |
| DLP 35 µm | 2x | 38x |
| micro-SLA 2 µm | 1x | 6x |

The OM10's tightest running fit is a 0.0031 mm gap between a pivot and its bore,
measured at every arbor by `tools/om10_fits.py` and written up in
`docs/om10-fits.md`. Clearances scale with the part, so scaling the movement up
until its walls print drags every fit up with it. On a 50 µm machine that gap
only reaches 0.009 mm at 3x, against the 0.20 mm the machine can resolve. The
parts come off the plate looking correct and fused to their bearings.

Taken literally that kills the idea outright. 64x for resin is a movement two
metres across, and FDM asks for 128x and very nearly four.

But a clearance is a number in the model, not a consequence of the scale. Bore
the bearing holes oversize before slicing and the fits stop driving anything,
which hands the job back to the walls and their four-to-six times cheaper scale.
That is the 3x in the answer above. What it costs is a movement whose fits are
the printer's rather than the watchmaker's, which is the right trade for
something meant to be looked at and the wrong one for something meant to be
worn.

This number used to be assumed. The first version of the study put it at
0.010 mm from watchmaking practice and argued it could not be measured, since
nominal CAD draws a pivot and its jewel the same size and keeps the clearance on
the drawing. That was wrong about this file: the OM10's STEP carries its real
fits and `tools/om10_fits.py` reads them, sixteen bearings, 0.0063 to 0.0150 mm
on the diameter. The measured figure is three times tighter than the guess, so
the fits constraint is three times worse than first reported and the conclusion
is unchanged, only louder.

Measuring them also turned up an interference: the intermediate wheel's pivot is
0.0096 mm too big for its upper bearing, a leftover from the revision that
enlarged those pivots from 0.167 to 0.190. `docs/om10-fits.md` has it.

## Boring it open

The conclusion above is only worth having if somebody can act on it, so
`tools/print_bores.py` does the acting: pick a machine and a scale, and it
opens every bearing in `Assets/om10-fits.json` until the gap at that scale is
what the machine can hold, writing the result to `Assets/print-bores.json`.

    python tools/print_bores.py                     # MSLA at the study's scale
    python tools/print_bores.py --printer FDM

At 3.4x on a 50 µm machine, the model needs a 0.059 mm gap for the printed one
to come out at 0.20. That opens the escapement jewels from 0.101 to 0.211, the
train bushes from 0.301 to 0.406, and the barrel bearings from 1.401 to 1.506.
Every bore grows by about a tenth of a millimetre, and the thinnest wall left
anywhere is 0.84 mm at 3.4x against a 0.30 mm minimum, so nothing ends up
fragile.

The pivots are not touched. Opening a bore costs a bearing some wall; turning a
pivot down costs the arbor its stiffness, moves the wheel's seat and changes the
depthing. Given two ways to buy the same clearance, take the one that only moves
a hole.

The whole bore is opened rather than only its narrow band. `tools/om10_fits.py`
had to learn that these holes are parallel with an oil sink on one side, and the
same fact matters in reverse here: opening only the narrow section would leave a
step partway down the hole for the pivot to catch on. Where the sink is already
wider than the new bore, it survives as a chamfer.

The `intermediate_bearing` interference comes out in the wash. Its new bore is
calculated from the pivot rather than from its own bore, so the bush that was
never opened when the pivots were enlarged gets opened here like every other.

### Proving the cuts

Opening a 0.10 mm hole to 0.21 mm is a large relative change, and these bearings
sit inside other parts. Every opened bore is built as the tube of material it
removes and intersected against all 166 solids. All sixteen come back clean at
both scales tested: the wall holds and nothing is broken into.

Two failures showed up first and both were mine rather than the geometry's. The
test solid was a full cylinder, which contains the old hole, so the barrel
arbor's own screw registered as a part the opening ate into when the opening
never reaches it; only the annulus is new material. And the cut runs past both
faces so it leaves no skin, which meant every part merely touching a bearing's
face counted as a collision, condemning the two balance cap stones for sitting
flat against the hole jewels they close. That is what a cap stone is for.

The cuts were then checked by doing them and measuring again: bore `jewel` open
and it sections at 0.2108, which is what was asked for.

## The thinnest parts

| Part | 2V/A | bbox min | 2A/P | |
|---|---|---|---|---|
| `shock_spring_cock` | 0.028 | 0.036 | 0.131 | bought |
| `hairspring` | 0.035 | n/a | n/a | wound |
| `shock_setting_cock` | 0.061 | 0.480 | 0.050 | bought |
| `shock_jewel_dial` | 0.084 | 0.140 | 0.405 | bought |
| `escape` | 0.088 | 0.151 | 0.214 | prints |
| `shock_capstone_dial` | 0.089 | 0.221 | 0.185 | bought |
| `OM10-00234` | 0.090 | 0.170 | 0.192 | prints |
| `mainspring` | 0.098 | 1.500 | 0.107 | prints |

The first run of this let the shock springs govern every machine, which is the
right answer to the wrong question. An Incabloc-type setting is bought as an
assembly and nobody prints one at any scale. With those excluded the escape
wheel governs at 0.088 mm, so the thinnest thing you would actually print is
also the thinnest thing that matters.

Read the three columns together. `2V/A` is volume over surface area, the
hydraulic thickness: for a flat plate it returns the plate exactly, and for a
pierced toothed wheel it returns less, because teeth and spoke windows add
surface without adding volume. That bias fails safe. `bbox min` is the honest
upper bound and `2A/P` the mid-plane width, so a part whose problem is its teeth
can be told from one whose problem is that the whole part is a foil.
`shock_setting_cock` is the clearest case, 0.480 mm deep and 0.050 mm wide in
plane: a ring you could hold that you could not print.

What none of them measure is a true minimum inscribed sphere, which is the test
a slicer actually applies. `2V/A` averages over the solid, so a part that is
stout everywhere except one 0.05 mm web reads as stout. Every number here is a
floor on the problem and never a ceiling. Section a part before printing it.

## What you buy or make instead

Eleven parts, in two groups that scaling treats differently.

The first group is the wrong material at any scale. The hairspring at 0.035 mm
and the mainspring at 0.102 mm are springs: the elasticity is the part, and no
photopolymer has it. A printed spiral has no elastic limit and therefore no
rate. Both are strip steel and both are specified down to length and gauge,
though they get there differently. The hairspring is designed by
`tools/hairspring.py` for the measured balance, 127.4 mm of 0.035 x 0.16, and
the export substitutes it for the OM10's 0.020 placeholder. The mainspring is
the OM10's own, `OM10-00120`, which was taken for a barrel drum until it was
measured: 283.7 mm of 0.102 x 1.505, drawn as 11.75 coils. `tools/mainspring.py`
measures that strip rather than designing one.

The four shock settings go the same way and take their springs, capstones and
hole jewels with them: eight rows in the table, one bought assembly per pivot.
The jewels likewise, since a printed bearing is why a watch would run for weeks
rather than years.

The second group is the right material and the wrong process, and it has one
member. The balance staff is a turning job. Its pivots are the running fit, and
printed they are a rough cone in a rough hole. It is the one part where the
surface finish is the function.

## What this does not answer

Surface roughness, which for a resin print at 3x is a large fraction of a tooth
flank and is the reason the honest verdict is "it will turn" rather than "it
will run". Support removal on 166 parts. Whether a 3x escapement has the inertia
to stay in beat, which `Services/Mechanism.cs` could be asked and has not been.
Print orientation, which decides whether a 0.26 mm scaled wheel comes off flat
or bowed.

And the printer numbers themselves. They are published, conservative figures for
a well-tuned machine of each class, not measurements from any printer here.
Since the entire study is a division by them, they sit in one table at the top
of `tools/print_scale.py` rather than scattered through it. Print a test comb on
the actual machine, put its numbers in `PRINTERS`, and run it again.
