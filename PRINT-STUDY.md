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
| FDM 0.4 mm | 9x | 40x |
| MSLA 50 µm | 3x | 20x |
| DLP 35 µm | 2x | 12x |
| micro-SLA 2 µm | 1x | 2x |

A watch's running clearance, a pivot in its hole, is about a hundredth of a
millimetre. Clearances scale with the part, so scaling the movement up until its
walls print drags every fit up with it. On a 50 µm machine a 0.010 mm fit only
reaches 0.030 mm at 3x, well under the 0.20 mm gap that machine can resolve. The
parts come off the plate looking correct and fused to their bearings.

Taken literally that kills the idea. 20x for resin is a 616 mm movement, and
nothing that size goes on a plate.

But a clearance is a number in the model, not a consequence of the scale. Bore
the bearing holes oversize before slicing and the fits stop driving anything,
which hands the job back to the walls and their four-to-six times cheaper scale.
That is the 3x in the answer above. What it costs is a movement whose fits are
the printer's rather than the watchmaker's, which is the right trade for
something meant to be looked at and the wrong one for something meant to be
worn.

This is the one number in the study that does not come off the STEP. It cannot:
that file is nominal CAD, where a pivot and its jewel are drawn the same size
and the clearance lives on the drawing. 0.010 mm is watchmaking practice, and
`RUNNING_FIT_MM` is where to change it.

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
| `barrel_drum` | 0.098 | 1.500 | 0.107 | prints |

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
and the mainspring at 0.14 mm are springs: the elasticity is the part, and no
photopolymer has it. A printed spiral has no elastic limit and therefore no
rate. Both are strip steel, and `tools/hairspring.py` and `tools/mainspring.py`
already specify them down to length and gauge, 127.4 mm of 0.035 x 0.16 and 446
mm of 0.14 x 1.95. The four shock settings go the same way and take their
springs, capstones and hole jewels with them: eight rows in the table, one
bought assembly per pivot. The jewels likewise, since a printed bearing is why a
watch would run for weeks rather than years.

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
