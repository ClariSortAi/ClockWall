# The OM10's running fits, measured

    python tools/om10_fits.py

`tools/print_scale.py` needed one number it could not get off the file: the gap
between a pivot and its bearing. It assumed 0.010 mm from watchmaking practice
and said so in its own comments, on the reasoning that nominal CAD draws a pivot
and its jewel to the same size and keeps the clearance on the drawing.

The reasoning was sound and it was wrong about this file. The OM10's STEP
carries its real fits, they are different at every arbor, and they can be read
straight out of it.

## What was measured

For each of the sixteen bearings, the part turning in it is the one on the same
arbor whose height range contains the bearing. Both get sectioned with a
horizontal plane and measured radially from the arbor: the bearing's section is
an annulus, so its smallest radius is the bore, and the pivot's section is a
disc, so its largest radius is the pivot.

Sections come from `BRepAlgoAPI_Section` against the exact surfaces, sampled
through `BRepAdaptor_Curve` on the exact curves. A mesh would not do. A pivot is
0.1 mm across, and tessellating one at any deflection you would render at moves
its radius by more than the clearance being measured.

| Bearing | Runs | Bore | Pivot | Clearance |
|---|---|---|---|---|
| `intermediate_bearing` | `intermediate` | 0.1812 | 0.1908 | **-0.0096** |
| `shock_jewel_dial` | `staff` | 0.0891 | 0.0829 | 0.0063 |
| `jewel_3` | `epinion` | 0.1012 | 0.0929 | 0.0083 |
| `jewel` | `epinion` | 0.1012 | 0.0929 | 0.0083 |
| `jewel_2` | `impulse_pin` | 0.1012 | 0.0929 | 0.0083 |
| `shock_jewel_cock` | `staff` | 0.0912 | 0.0829 | 0.0083 |
| `jewel_4` | `impulse_pin` | 0.1017 | 0.0929 | 0.0088 |
| `train_bearing_back` | `intermediate` | 0.2012 | 0.1908 | 0.0104 |
| `barrel_bearing_2` | `barrel_arbor` | 1.4008 | 1.3882 | 0.0127 |
| `barrel_bearing` | `barrel_arbor` | 1.4008 | 1.3882 | 0.0127 |
| `centre_bearing_2` | `pinion_centre` | 0.5509 | 0.5381 | 0.0129 |
| `centre_bearing` | `pinion_centre` | 0.5509 | 0.5381 | 0.0129 |
| `train_bearing_3` | `pinion_third` | 0.3012 | 0.2878 | 0.0134 |
| `train_bearing` | `pinion_third` | 0.3012 | 0.2878 | 0.0134 |
| `train_bearing_back_2` | `pinion_seconds` | 0.2020 | 0.1870 | 0.0150 |
| `train_bearing_2` | `pinion_seconds` | 0.3020 | 0.2870 | 0.0150 |

All diameters, in mm. The tightest running fit in the watch is 0.0063 mm on the
diameter, at the balance's dial-side shock jewel, which is where you would
expect it: the balance turns more than everything else combined.

## Not the middle of the hole

The first version measured at each bearing's mid-height, reasoning that a jewel
hole is olive-shaped and narrowest in the middle. Scan the escapement jewel down
its height and the bore reads 0.101, 0.109, 0.196, 0.311, 0.387, 0.445. It is a
parallel hole with an oil sink opening out of one side, and its middle is
already inside the sink. Measuring there reported the escape pinion at 0.218 mm
of clearance, twenty times its real figure.

So the bore is scanned over the bearing's whole height and the narrowest section
wins, with the pivot measured at that same height. Everything above it is the
oil reservoir.

## An interference, and where it came from

`intermediate` is 0.0096 mm too big for `intermediate_bearing`. That is not a
tight fit, it is metal through metal, and the release notes say why.

`OM10_Release_notes.pdf`, in the 2021/02/01 entry:

> OM10-00152 et OM10-00164 Modification diamètre pivot roue seconde et roue
> intermédiaire 0.167+-0.003 augmente à 0.190+-0.003.

The intermediate wheel's and seconds wheel's pivots were enlarged from 0.167 to
0.190. Measured off the geometry, `intermediate` is 0.1908 and `pinion_seconds`
is 0.1870, both inside the new tolerance, which is an independent check that the
sectioning is reading the right thing.

The intermediate wheel's lower bearing was opened to match: `train_bearing_back`
is 0.2012, a 0.0104 fit on the new pivot. Its upper bearing was not.
`intermediate_bearing` is still 0.1812, which is 0.0142 on the *old* 0.167
pivot, a textbook fit for the part as it was before the change.

One bush was missed when the pivots were enlarged. The number is small enough to
have survived every check that did not section the hole.

## What this changed downstream

`tools/print_scale.py` now reads `Assets/om10-fits.json` and uses the tightest
measured gap instead of the assumption. Two corrections came with it.

The first is a factor of two. A printer's quoted clearance is the gap between
two surfaces, so the watch number to compare it against is the radial gap, half
the diametral clearance. The tightest fit is therefore a 0.0031 mm gap, not
0.0063.

The second is the conclusion. At 0.010 mm the fits already governed the print
scale ahead of the walls, by four to six times. At the measured 0.0031 they
govern by thirteen to twenty: FDM needs 128x rather than 9x, and a 3.9 metre
movement. The finding survives, and the case for boring the fits open in the
model rather than paying for them in scale is now overwhelming, because there is
no scale that pays for them.
