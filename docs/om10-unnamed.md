# The sixteen parts still going by their OM number

`tools/gltf_export.py` names 150 of the OM10's 166 solids. These are the rest,
with a proposed name and the evidence for it. Nothing here has been applied:
`NAMES` is untouched, and the two entries worth acting on first are the two that
are corrections rather than additions.

Evidence is position (arbor, height, distance to named neighbours), the section
at mid-height about the part's own axis, and the OM number's family. Confidence
is stated because it varies a lot, and four of these are guesses wearing a
plausible name.

## Two corrections, high confidence

**`OM10-00111` is the impulse pin, and `OM10-00107` is not.**

`00107` currently carries the name `impulse_pin`. It cannot be one. The impulse
pin stands on the roller and turns about the balance; `00107` sits on the pallet
fork's own arbor at (-5.87, 5.71), and `tools/om10_fits.py` measures it running
in `jewel_2` and `jewel_4`, the fork's upper and lower jewels, with 0.0083 and
0.0088 mm of clearance. A part running in the fork's two jewels is the fork's
staff.

`00111` is what the impulse pin looks like: 0.32 mm across, 0.50 mm tall, 0.026
mm³, standing at (-7.58, 4.00), half a millimetre off the balance axis, at
y 0.220 to 0.720. The roller runs y 0.220 to 0.970. It starts at the roller's
own bottom face, on the roller, offset from the centre.

Proposed: `00111` becomes `impulse_pin`, `00107` becomes `lever_staff`. The
rotation map should be checked after, since anything keyed to `impulse_pin`
today is being driven by the fork's arbor rather than by the roller.

**`OM00-00138` is the centre post.**

A 0.698 mm cylinder, 2.50 mm long, dead on the plate centre, running y 0.050 to
2.550. The cannon pinion's bore measures 0.709 at that height, so the pinion
turns on it with 0.011 mm of clearance. That is the post the motion works run
on. Proposed: `centre_post`. The `OM00` prefix agrees, since that family is the
standard hardware shared across calibres.

## Plausible, medium confidence

**`OM10-00241`, both instances: `washer_d`.** A 1.35 mm ring, 0.20 thick, bore
1.01. Both sit at distance 0.00 from a `screw_d` and its `insert_d`. A washer
under a screw is the only thing that shape is.

**`OM00-00130`: `pin_long`.** A plain 0.56 mm cylinder, 1.51 long, on the back
beside `insert_b_2`. The catalogue already has `pin` for `OM00-00100`, which is
0.60 by 0.70. Same family, different length, so the name should say which.

**`OM10-00234`: a spring in the keyless works.** 0.17 mm thick, 3.4 by 5.0, an
arc, 0.44 mm from `setting_lever_spring`. At that thickness in that group it is
sprung steel doing sprung steel's job. Proposed `yoke_spring_2`, held loosely:
the thickness and the neighbour are solid evidence, the exact role is not.

**`OM10-00237`: also a spring.** 0.20 thick, 2.3 by 5.5, near `winding_pinion`.
Same reasoning and the same caveat.

**`OM10-00304`: `keyless_plate`.** 9.7 by 4.8 by 1.15, on the back, 21.2 mm³.
The `003xx` family is the keyless rework the release notes introduce in the
2021/09/19 entry: `00306` couvre méca, `00307` pont de méca, `00308` vis de
tirette. `00304` belongs with them.

**`OM10-00211`: `date_jumper_spring`.** 0.20 mm thick and 7.5 by 13.2 across, so
a long thin arc, on the back, 1.98 from `date_jumper`. Thin, long, arced and next
to a jumper reads as the spring that loads it.

## Guesses, low confidence, listed so nobody has to measure them twice

**`OM10-00102`.** The largest puzzle. 13.4 mm³, 6.1 by 7.6, only 0.60 thick,
sitting y 0.069 to 0.671 with a 1.58 mm central hole, centred 0.30 mm off the
balance axis. Between the balance below it and the roller above it. The `001xx`
family is the escapement. It is either the balance wheel proper, which would
mean `00113` is something else, or a plate carried on the balance staff. It
wants a look rather than a name.

**`OM10-00136`.** 2.4 by 3.4 by 0.95, on the back, 0.99 from the cock. The
release notes tie `00181` and `00196` to the raquetterie, so something in that
area is the regulator's, and this is in that area. `index_arm` is the guess.

**`OM10-00200`.** 0.40 mm plate, 3.7 by 4.9, on the back out at r 13.0, near the
plate rim. The `002xx` family is keyless and date. A thin plate at the rim on the
back is most likely a retaining spring or a clamp.

**`OM10-00231`.** An arc from r 2.43 to 3.06, 0.50 thick, dial side, in among
the setting wheels.

**`OM10-00233`.** 3.3 across, 0.70 thick, 0.25 from `setting_wheel_2` and just
above it. Probably a wheel in the date drive.

**`OM10-00240`.** On the stem line at (0.00, -11.63), 2.22 long, about 2.9
across, between `winding_pinion` and `sliding_pinion`. Something on the stem
between the two; naming it properly means looking at how it engages.

**`OM10-00245`.** The biggest unnamed part at 67.1 mm³, 14.0 by 7.8 by 2.25,
spanning the plate's thickness at the keyless works, 0.13 from `keyless_bridge`.
Big enough to be structural. The OM10 ships in VA and VB variants and this may
belong to only one of them.
