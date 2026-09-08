# The right pipeline

A design, not a change. Nothing in this file has been built. The numbers come
from `Services/Caliber.cs` and `tools/escapement_geometry.py` and are arithmetic
on constants already in the repo, but no frame of it has been rendered, so treat
the counts as sizing rather than as measurement.

## The constraint chain

Everything wrong with how this face looks comes from one chain, and each link is
individually correct:

    the app rotates one sprite per part
      -> that sprite must look right at every angle
        -> its lighting must be a symmetry of rotation
          -> axial ring light, no shadow catcher
            -> no directional highlight, no contact shadow
              -> no form

`HANDOVER.md` states the law at the fourth link and enforces it with
`placement_invariants.py`. The law is right. The chain is what is wrong, and it
starts at the first link, not the fourth. **The pipeline pre-renders parts and
animates them by rotation, when it should pre-render states and animate them by
selection.**

Rotating a sprite is the only reason the lighting has to be formless. Remove
that one decision and every downstream constraint dissolves at once: the key
light comes back, shadow catchers come back, parts shadow each other again, and
anisotropic highlights - which are the entire visual content of brushed and
circular-grained metal - become expressible.

## The principle

**Decompose by rate, not by part.** The current face is ten layers because ten
things move independently. They do not. The movement has one degree of freedom -
`Caliber` already says so, in terms: *"ONE CLOCK, AND IT IS THE BALANCE.
Everything below is a function of a single fractional beat count."* If every
moving part's position is a function of one number, then the whole assembly has
one state per value of that number, and a state can be rendered as a single
correctly-lit image.

Per-part layering exists only to serve per-part rotation. Drop the rotation and
the layering goes with it, and inter-part shadows - a wheel darkening the plate
under it, the lever's shadow falling across the escape wheel - stop being
forbidden and start being free.

**Symmetry is the budget.** A part with k-fold rotational symmetry is pixel-wise
identical at angle t and t + 360/k, so a sequence only has to cover 360/k. This
is what makes the approach affordable rather than absurd, and it is worth
computing before anything else.

## The design

Four layers, split by how fast they change rather than by what they are.

**Static.** Mainplate, bridge, jewels, dial, bezel, case. One image. Full
directional key, full shadow catcher, every shadow that static geometry casts on
static geometry. This is the layer the seam and the bezel shards live on, so
those get fixed here regardless of anything else.

**Fast group** - escape wheel, pallet lever, balance, and the shadows all three
cast down onto the plate. One sequence, looping.

**Slow group** - the going-train wheel and its shadow. Its own sequence, because
its period is long and mixing it into the fast loop multiplies the two.

**Hands.** Left as they are for now, which is honest rather than ideal: they are
already rendered with no shadow by an explicit decision, so keeping them costs
nothing new and changes nothing that the wall complained about. Sequencing them
is the natural next step and is sized below.

## The frame math

From `Caliber.Swiss4Hz`, whose real values are `(25_200 vph, 20 teeth, 285 deg
amplitude)` with an 84-tooth train wheel on an 8-leaf pinion:

- 25,200 vph is **7 beats per second**, so a full balance oscillation is 2/7 s.
- `EscapeStepDegrees` is 360/(2*20) = **9 degrees per beat**, 18 per oscillation.
- The escape wheel has 20 teeth and 4 crossings. Teeth repeat every 18 degrees,
  crossings every 90, and 90 contains exactly five tooth pitches - so the wheel
  is **identical every 90 degrees**.
- 90/18 = **5 oscillations**, and the balance and lever are both whole-period at
  5. So the fast group's loop is 5 oscillations = 10 beats = **1.4286 seconds**.

That is the whole fast group in about **48 frames at 33.6 fps**, or 64 at 44.8.
Pick the frame count first and derive the rate from it, so the loop closes
exactly rather than drifting.

The going-train wheel is the awkward one, and the reason is worth stating
because it is a lever the next session can pull. It has **84 teeth and 5
crossings**. Teeth repeat every 4.286 degrees and crossings every 72, and 72 is
not a whole number of tooth pitches - `gcd(84, 5) = 1` - so the wheel is only
identical after a **full 360 degrees**, which at one revolution per minute is a
60-second sequence.

**Give it 6 crossings instead of 5 and the period collapses to 60 degrees**,
because 84/6 = 14 is whole. That is a ten-second loop instead of sixty, for a
change that is invisible at this size and no less authentic - real going-train
wheels are crossed four, five or six ways, and `escapement_geometry.py` calls
five "shaped crossings" as a drawing choice, not a measurement off the OM10.
Four crossings also divides (84/4 = 21) and gives 90 degrees, or fifteen
seconds.

So the design principle, stated once: **choose crossing counts that divide the
tooth count.** Symmetry is bought at zero visual cost and paid back in frames.

Sizing, at 6 crossings and 0.5-degree steps: fast group about 48-64 frames, slow
group 120. Call it **under 200 frames** for the entire movement, against 17 MB of
assets today. Hands, if sequenced later, are the expensive part - they have no
symmetry at all, so each needs its full 360 degrees - and the cheap way in is to
sequence only the *shadow*, which is a soft grey alpha shape that compresses to
almost nothing, and leave the hand bodies as they are.

## What this deletes

`world_axial` and `lights_axial` stop being needed. `placement_invariants.py`
stops being needed in its current form, because it exists to prove that nothing
directional was baked into a mover, and after this change baking directional
light into a mover is the entire point.

The gate that replaces it is stronger and much simpler: **frame count times
angular step must equal the symmetry period.** If it does, the loop closes; if it
does not, the wheel visibly jumps once per loop. That is one assertion per
sequence, and it is checkable without rendering anything.

The parts of the pipeline that are good survive untouched: the CAD extraction
from the real OM10 STEP, `clash_check`, `interfere_check`, the render lock in
`render.ps1`, the vendored HDRI and the argument in its SOURCE.txt for why a
measured studio environment *is* the material for an all-metal watch.

## A correction that belongs here

`HANDOVER.md` argues the balance's aliasing is tolerable on the grounds that
*"the wheel has three arms, so it repeats every 120 degrees, and past 60 degrees
in a frame the spokes appear to run backwards."*

The balance does not have three arms. `escapement_geometry.balance()` builds
**one bar straight through the centre, so two arms**, plus **four inertia blocks**
in the rim, and `balance_screws` sets **eight** timing screws around it. Two arms
give 180 degrees, four blocks give 90, eight screws give 45. The repeat is 90
degrees at best and 45 if the screws resolve - never 120.

The aliasing threshold is therefore **45 or 22.5 degrees per frame, not 60**. The
error is in the unsafe direction: aliasing starts sooner than the document
argues, over more of the swing. This is the one open question `HANDOVER.md`
flagged as "an argument rather than a measurement", the wall has now reported
motion that "looks really weird", and the argument turns out to rest on a wrong
number. It should be re-derived before anyone tunes the smear again.

This is also an argument for the design above, not just a bug in the old one:
pre-rendered states do not alias, because nothing is being rotated between
frames - each frame is the assembly as it actually stood.

## The alternative, and when it is right

The other coherent answer is to stop pre-rendering and light the watch live:
export the assembly to GLB, bake Cycles-quality surface detail into normal,
roughness and AO maps, and render in real time with image-based lighting from
the same HDRI. The app already ships WebView2, so a Three.js path exists without
adding a renderer to the build.

It is better on three axes - continuous rather than quantised motion, no asset
budget at all, and genuine parallax, which is the thing that actually reads as
"a 3D artifact" rather than a picture of one. It is worse on two that matter
here: real-time image-based lighting does not match a path tracer on metal,
which is nearly every surface in this watch, and it puts a GPU renderer inside
an app whose stated job is to run unattended for days.

**Recommendation: build the sequence pipeline.** It is an incremental change to
something that already works, it keeps path-traced quality, its cost is
computable in advance - and it is the one of the two that can be abandoned
cheaply if it disappoints, because the CAD, the gates and the render script all
survive either way. Revisit live rendering if the frame budget turns out worse
than the arithmetic above suggests, or once "looks real" is solved and "feels
three-dimensional" becomes the goal.

## What to validate first, in order

1. **Render one fast-group loop and step through it.** 48 frames, full
   directional light, shadow catcher on the plate. This answers whether the
   flatness really was the lighting, and it answers it in one render rather than
   after a rewrite. If the aperture does not visibly improve, the diagnosis in
   `HANDOVER-WALL-READ.md` is wrong and nothing further should be built on it.

2. **Check the loop closes.** Frame 48 against frame 0. They must be identical.

3. **Re-derive the balance symmetry** from the geometry rather than from
   `HANDOVER.md`, and recompute the aliasing threshold against it.

4. **Change the train wheel to 6 crossings** and confirm the 60-degree period,
   before rendering 360 frames of anything.

5. **Only then** touch materials. The finishing work - anglage, perlage, cotes
   de Geneve - is worth nothing until there is a light that can show it, and
   worth a great deal immediately afterwards.
