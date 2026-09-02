# Handover: the mechanical watch face

Written 2026-09-01 for whoever picks this up next.

This file is the pipeline and the traps. **`HANDOVER-REALISM.md` is the one to
read first**: it says what state the work was left in, what has actually been
verified, what went wrong on the way, and what to do next to finish the job.

## What changed, in one line

The movement in the aperture used to be drawn. It is now openmovement.org's
OM10, a real open-source Swiss movement, scaled and placed into the face.
ATTRIBUTION.md says where it came from and what the licence allows.

## Why that mattered

Every part was a flat outline pushed to a constant thickness and given one
blanket bevel. The balance was a hoop with a bar across it. The hairspring was a
set of concentric circles. The pinions were, in the source's own words,
overlapping discs, on the argument that a pinion looks like a flower at this
size. Under a straight-down orthographic camera the only things that can shade
are interior walls and chamfers, and all of ours were invented.

The tooth counts were invented too, and those are not cosmetic. A 15-tooth
escape wheel driving a 7-leaf pinion off a 64-tooth wheel sets the beat and every
rotation rate downstream from it. The real counts are 20, 8 and 84.

## The pipeline

Run in this order. `tools/render.ps1` does everything from step 3 on.

1. `.venv-cad\Scripts\python.exe tools/om10_extract.py`
   Reads the OM10 STEP from `C:\Users\jason\Downloads\`, pulls out the two dozen
   parts the face uses, and writes each as STL plus STEP into
   `captures/om10/parts/`, centred on its own axis of rotation.

2. `.venv-cad\Scripts\python.exe tools/om10_check.py`
   Recounts the teeth properly and rewrites the manifest. **This must run after
   the extractor, every time.** See the traps.

3. `.venv-cad\Scripts\python.exe tools/cad_parts.py`
   Places every part into the face and writes `captures/cad/*.stl` plus a
   manifest carrying the pivots, materials and tooth counts. It loads
   `models/step/movement.step.py`, which is the actual assembly. It also
   projects the OM10 mainplate and writes its drilling into the same manifest
   in face coordinates, because `escapement_geometry` draws the plate and runs
   under the system interpreter, where trimesh does not exist.

4. `python tools/export_profiles.py`, then Blender, then `tools/smear.py`.
   Unchanged in shape. `export_profiles` now takes the movement from the CAD
   manifest and only draws the plate, the floor and the jewel collars itself.

## Two laws, and the instruments that hold them

### Nothing directional may be baked into a layer that moves

A cast shadow belongs to the surface it lands on and a raking highlight belongs
to the lamp that threw it. Bake either into a sprite the app rotates and it
orbits the arbor once a turn: the geometry is right, the light is right, and
what the wall shows is a gear wobbling. No single frame shows it, which is why
it survived every screenshot anybody took of this face.

The render now splits on one question, and `Controls/OpenworkedFace.xaml`
answers it: does the app turn this layer?

A layer that turns gets no shadow catcher at all, an environment collapsed onto
its own axis (`render_lib.world_axial`, the studio HDRI rebuilt as a ring
light), lamps on the same axis (`lights_axial`), and nothing else visible to
its reflected rays. Rotating it is then a symmetry of everything lighting it.
That covers the five movement groups, their smear twins and the three hands.

A layer that holds still keeps the directional key and its catcher: the
mainplate base, the cock, the case, the cap over the hand pivots. Every cast
shadow in the face now lives on one of those four.

The grounding moved with the shadows. Movers cast into the base pass while
staying invisible to the camera, so each wheel's contact pool sits on the plate
under the wheel and stays there while the wheel turns. The hands were given no
shadow rather than an argument about which shadows are axial enough; the cap is
what says they stand off the dial.

`python tools/placement_invariants.py --assets` is the gate, and
`tools/render.ps1` throws at step 5 until it passes. It reads the
RotateTransforms out of the XAML, so a layer that gains one gains a gate on the
same edit. Of a symmetric mover it asks whether the alpha centroid sits on the
pivot; of any mover, how much alpha lies outside the part's own silhouette.
Before the relight, ten layers failed fourteen checks, with 46 to 50 per cent
of each wheel's alpha off the part and nearly all of it bearing about 235
degrees, which is the key light's direction rather than any wheel's. After it,
the worst layer reads 1.1 per cent and no centroid is further than 0.05 units
from its pivot.

Do not soften `SOLID_ALPHA`, `PART_MARGIN`, `STRAY_FRACTION_MAX` or
`CENTROID_MAX`. Each was set against these layers and the file says how. The
gate is deliberately blind in one place, a shadow lying along a hand's own
axis, because an axial source really does cast one that way. It is written down
as evidence for whoever reads a failure, not as a hole to drive a shadow
through.

### The wall is the acceptance test

Nothing here is settled from a crop at render resolution. Render, build,
deploy, screenshot the deployed app, then look at the sheet:

    .\tools\render.ps1                                    # ~8 min, one Blender ever
    dotnet build ClockWall.csproj -c Release -r win-x64
    python tools/motion_check.py                          # ~20 s, takes the foreground
    python tools/motion_check.py --balance                # ~20 s, same
    .\deploy.ps1
    ClockWall.exe --screenshot captures\wall\deployed.png
    python tools/wall_sheet.py captures\wall\deployed.png

The order matters. `Assets/` reaches `bin/` only at build time and
`%LOCALAPPDATA%` only at deploy time, so a screenshot taken before either one
shows the previous render. `motion_check.py` runs the built app and watches it
move, which is the question `placement_invariants.py` cannot ask: what the user
complains about is a composite that has been cross-faded, scaled to the panel
and covered by three hands. Its baseline lives in
`captures/motion/scores-baseline.json` and is never overwritten, so every run
prints a before and an after.

`--balance` is the same capture put to a different question, and it is the one
the balance needs. The plate score asks whether anything moves that should not.
This asks whether the one part that swings rather than steps is swinging. It
cannot watch a 286 ms oscillation at the eight frames a second a screen grab
manages, and it does not try: every frame carries the instant it was taken and
the movement is a function of the wall clock alone, so folding 240 stamps into
beat phase rebuilds one oscillation out of frames taken at any rate at all. The
capture rate stops mattering; only the count does. Then it rotates the balance's
own render against the annulus in each frame, which gives the angle and, as the
regression coefficient, how much of the sharp layer was on screen.
`captures/motion/balance-waveform.png` plots both against one folded
oscillation and `balance-frames.png` puts six captures beside the render turned
to the angle claimed for them, because an angle estimator nobody has checked
against pixels is an angle estimator nobody should believe.

`captures/wall/wall-sheet.png` is the only artifact appearance may be judged
from. It shows the face at full size, half and a quarter beside real open-heart
dials, because every judgement made at render resolution has been wrong the
same way: it read beautifully at 1920 and turned to mush at the 640 the wall
actually gives it.

The sheet also prints one number and exits non-zero on it, because "the
aperture pulls the eye" is not a sentence two people read the same way. It is
the mean luminance of the opening over the mean luminance of the band of dial
immediately outside it, taken from the composited capture rather than from
`Assets/`, and it has to come out under 1.0: the opening has to be darker than
the dial around it. Every reference in `captures/refs` is, and by more than
this face is - the Orient measures 0.588 and the Tissot 0.689, both of them
against silver dials rather than a dark blue one. This face read 1.177 before
the plate work and 0.836 after. In absolute terms its opening is now darker
than either photograph's; what differs is the dial they are measured against.

The band is local on purpose. Contrast is read against what a thing touches,
and the far side of this dial carries the sunburst's own bright quadrant, which
would swing the denominator for reasons that have nothing to do with the
opening. `captures/wall/ratio-regions.png` draws every region over the image it
was taken from, because the two reference circles are placed by hand and a
ratio nobody can check is a ratio nobody should believe.

## The one idea worth keeping

Every part of the escapement is placed by a **single similarity transform**:
one scale, one rotation, one translation, applied to the whole cluster. A
similarity preserves every distance ratio and every angle, so the escapement
that arrives in the face is the one that left the OM10. The line of centres is
still straight. The stones still straddle the escape wheel at a span that lets
it alternate. Nothing can pass through anything, because nothing moved relative
to anything else.

That is why the old machinery for getting these right one at a time is gone: the
pallet-phase solver, the derived mesh distance, the hand-fitted 0.591 pallet
fraction. The correctness is inherited rather than re-established.

Two numbers are still ours, and both are framing rather than mechanism: where
the balance sits in the window, and `ESCAPE_BEARING`, which is the direction the
rest of the movement runs from it. `tools/layout_preview.py` draws the layout at
any set of bearings in about ten seconds, which is the tool to use before
spending eight minutes on a render. It confirmed 51.53 degrees is the right one:
the others throw the fourth wheel outside the aperture.

The same trade applies to shading. `tools/shade_preview.py` runs a fast EEVEE
pass over the same scene `render_lib` builds for the full Cycles render, cropped
to the aperture and done in seconds rather than minutes. Use it for a material
or lighting question; save the full render for the question layout_preview and
shade_preview cannot answer, which is what the assembled scene looks like once
it is actually lit and denoised.

## What was checked, and what it said

None of this is "it looks right". Each is a number with an answer.

The cock's balance jewel hole, read out of the cock's own projected outline,
lands at (-8.06, 3.51) in the movement's plane. That is the balance arbor read
independently off the assembly. Two decimals, so the arbor, the extraction
centring and the placement transform all agree.

Both pallet stones reach inside the escape wheel's tooth-tip circle, by 0.1612
mm and 0.1803 mm. Equal lock on entry and exit is what a correctly set
escapement has, and nineteen thousandths of a millimetre apart, against a
tolerance of fifty, is not something a drawing gets by accident. (An earlier
version of this file quoted 0.160 and 0.158. Those numbers do not come out of
the code as it stands, and re-running the placement with the plate work stashed
gives the pair above, so they are a stale transcription rather than a change
anything made.)

The stones bear 202.0 and 264.1 degrees from the escape arbor, 62.08 degrees
apart. On a 20-tooth wheel that is 6.90 half tooth-spaces, so 7. The reasoning
already in `escapement_geometry.py` says the count has to be odd or the wheel
arrives with a tooth pointing at the gap between the stones and cannot
alternate. It is odd. Our own figure had been 5.

`scripts/inspect validate` reports ok with zero failures.
`tools/interfere_check.py` reports 6 contacts, all of them press fits and
bearings that are declared with their reason, and no part passing through
another. `tools/placement_invariants.py` passes 9 of 9.

The four pivot bores are the newest of those nine and the cheapest to explain.
Every pivot has to run in a hole the OM10 actually drilled, and the hole has to
be able to take the stone. Both halves hold: the worst bore sits 0.053 face
units from its pivot, which is four microns of watch, and the tightest measures
5.77 units against a 5.91-unit jewel, which is the interference a jewel is
pressed in with. A plate scaled or turned even slightly wrong breaks one of the
two.

`tools/beat_strip.py`'s strip drawing is still stale. It draws from
`escapement_geometry`'s own outlines, which are no longer what gets rendered for
any moving part. The question it existed to answer, whether a pallet stone meets
a tooth, is answered above by measurement instead. Its copy of the physics is
not stale any more, because `motion_audit` imports it and was giving wrong
answers on the strength of it; see the balance entry under Still open.

## Traps

**Re-running the extractor silently breaks the tooth counts.**
`om10_extract.py` writes provisional counts taken from raw triangulation
vertices, which cluster where the tessellator chose and leave angular gaps that
read as gullets. It scores the escape wheel as having no teeth at all.
`om10_check.py` recounts by sampling the surface uniformly by area and
overwrites them. Run the extractor afterwards and the bad numbers come back. The
first symptom was a train ratio of 84 divided by zero. `cad_parts.py` now
refuses to run against wrong counts and says how to fix it.

**Do not take the stack datum from the lowest point of any part.** Pinion arbors
hang below the wheels on purpose and jewels are countersunk below that, so the
lowest solid is not the floor. Taking it as the floor lifted the whole movement
23 units into the air over a plate it should be sitting on, and nothing looked
wrong because everything floated together. The datum is the escape wheel's
underside, in `movement.step.py`.

**The jewels are the one place the OM10's own z cannot be used.** Their real
depth is measured against a mainplate 9.42 mm thick, which is 111 face units
here, against the 6.5-unit plate this face uses. Carried across literally they
bury themselves several plate-thicknesses down and render as nothing. They are
placed by an explicit top-face height instead.

**The OM10 manifest's mainplate thickness is not the mainplate's.** The
manifest records the plate as 9.42 mm between z -4.41 and 5.01. The STEP and
the STL the extractor actually wrote span 2.21 to 4.71, so 2.5 mm, and their
volumes agree with each other to three decimals. What the manifest quotes is
`BRepBndLib`'s box, taken before the solid is triangulated, and on a plate full
of cylindrical bores that box is loose in exactly the axis that comes from the
OM10's own y. Nothing in the render depends on it, because the drilling is a
plan projection and the plate is extruded to the face's own 6.5 units. It
matters only if somebody quotes 9.42 as a real plate thickness, which this file
did until now.

**`build123d` is patched in `.venv-cad`.** One malformed file in the Windows
font folder, `C:\Windows\Fonts\mstmc.ttf`, raises "bad sfntVersion" during the
library's font scan and aborts `import build123d` outright. `register_folder` in
`build123d/text.py` now skips unreadable fonts and reports them on stderr.
Reinstalling build123d loses the patch, and the symptom is that every CAD script
stops working at once.

**clash_check no longer checks the moving parts, deliberately.** It crosses a 2D
footprint with a z span, which was fair while every part was an extrusion of
that exact footprint and is wrong for a real solid: a balance cock is a foot on
the plate and an arm raised over the balance, so its footprint covers the
balance and its z span overlaps the balance, and it touches nothing. Run
`tools/placement_invariants.py` first: it checks the geometry that actually
implies a correct placement (the cock jewel on the balance arbor, the fork
pointing at the balance, screws in their holes, pallet stones locking evenly)
in about a second. Then run `tools/interfere_check.py`, which asks for the
boolean intersection volume and knows which pairs are supposed to be in
contact. Neither is wired into `render.ps1`: interfere_check costs minutes and
neither answer changes when only a material or a light does, so run both after
moving a part, not before every render.

**A render is not in the binary until you rebuild.** `Assets/` is copied into
`bin/` at build time, so a screenshot taken from `bin/` after a render still
shows the previous assets. This bit once already and it was invisible: the dial
kept reading 28,800 vph after the movement had been rebeaten to 25,200, because
`bin/Assets/case.png` was twelve minutes older than the one just rendered. It is
the same trap as the deployed copy, one layer in. Render, then build, then
screenshot.

The older traps all still apply. The app runs from
`%LOCALAPPDATA%\Programs\ClockWall`, so run `deploy.ps1` or you are looking at
the old binary. Never `dotnet publish` self-contained, because Smart App Control
blocks the unsigned runtime it bundles. `Assets/dial-texture.png` is an input,
not an output. CadQuery segfaults on interpreter teardown, so scripts end with a
flush and `os._exit(0)`.

## Where the pivots live now

`OpenworkedFace.xaml` still holds the rotation centres as literal attributes, and
they still have to match the placement. They are printed by both `cad_parts.py`
and `export_profiles.py` in the form the XML wants. Current values:

    balance / spring  296.2, 464.2
    fork              324.8, 441.5
    escape            353.4, 418.8
    train             396.6, 422.6

## Still open

The balance cock question is resolved: this dial looks at the front of the
watch, not the back, so the OM10's own decorated cock does not belong in the
aperture at all. It has been replaced with a thin front-view arm,
`_balance_bridge()` in `models/step/movement.step.py`, sized against reference
photographs of open-heart and skeleton dials rather than against the OM10 cock
it stands in for. See that function's docstring for the full reasoning.

The plate is no longer ours. Every hole in it comes out of
`captures/om10/parts/mainplate.step`: `cad_parts.py` projects the real solid,
carries the plan into face coordinates through the same similarity the parts go
through, and writes it into the manifest, where
`escapement_geometry.plate_openings()` reads it. Forty holes, twenty of them
inside the opening, and the four that matter land on the four pivots to within
0.05 face units. Nothing aimed them there. They arrive under the pivots because
the plate and the parts came out of the same movement and went through the same
transform.

What is still ours is the disc under the drilling, and that is the framing
decision this always was. The real plate is 366 face units across with its
centre 92 units from a 252-unit opening, so it reaches 88 per cent of the way
across the window and stops. The far upper-left crescent is plate we drew,
coplanar with the real one and in the same material, so the join has no edge to
find. Covering the whole opening with the real outline instead would mean
shrinking the movement, which is a rescale, which is pivot coordinates in the
XAML and somebody's decision rather than a render setting.

Two things followed from having real bores. The chatons are now the gap between
each hole and the stone that goes in it, which leaves exactly one: the balance's
hole is 11.06 units against a 5.91-unit jewel, while the escape and pallet bores
are 5.77 and take the stone directly. And the jewels came down. `JEWEL_TOP` was
5.8, which is where a stone looks right and where every arbor is at its widest;
at 3.5 each one sits around the turned-down pivot instead, still wholly inside a
plate that runs 0 to 6.5. `interfere_check.py` went from seven contacts to six:
the balance staff stopped touching its jewel at all, and the fourth wheel's
halved from 0.0396 to 0.0200 mm3.

The bridge foot's screw still sits 112 units out on a plate of 126, and it is
now defensible rather than tolerated. The OM10 drilled a hole there, it is one
of the forty, and the screw goes into it. It is near the rim because the
aperture is cut where it is, not because there is anything wrong with the screw.

The balance swings again. It was reported from the wall as flickering between
two apparent states, and it was. `Draw` faded the sharp wheel into its smear on
the rule the three stepping parts use, which asks whether a part has moved
further in one frame than the smallest feature on it. For the balance that
ratio is fifteen, so the clamp sat at full smear for 96 per cent of every
oscillation and the sharp wheel existed only in a six-millisecond spike at each
reversal. Measured on the deployed app it was on screen in four frames out of
240, at the same two angles both times. Those two angles are the two states.

It now fades on speed itself, which is `reading.BalanceSpeed`, which is |cos|:
thickest smear through centre, the wheel in focus at the two turning points
where a real balance is momentarily stopped. Fitting a gain on |cos| back out
of the pixels gives 15.43 before and 1.05 after, against 1.00 for a fade that
tracks speed exactly. The wheel is seen sharp through 62 per cent of its swing
instead of 8, in two arcs 38 degrees wide instead of two five-degree dwells,
and where it is caught it sits 2.8 degrees from where `Caliber` says it is.
`captures/motion/balance-baseline.json` holds the failing run.

What is not settled is the aliasing that threshold was over-defending against.
The wheel has three arms, so it repeats every 120 degrees, and past 60 degrees
in a frame the spokes appear to run backwards. That covers most of the swing.
The sharp layer is under 43 per cent opacity everywhere it happens and reaches
zero at the worst of it, over a smear with no angular structure to run
backwards at all, so the argument is that nothing coherent is left to see. That
is an argument rather than a measurement. If the wall shows a counter-rotating
ghost, the knob is a gain on `BalanceSpeed` in `Draw`, fading out where the
aliasing starts instead of fifteen times before it, and `--balance` will read
whatever is set there. Do not put the old clamp back without measuring it.

The cross-fade does modulate the light in the annulus, because a wheel in focus
and a wheel smeared into a ring do not carry the same amount of it. Over the
whole aperture that comes to 0.7 per cent, against 0.6 before, which is what
the third panel of the waveform plot is for.

`tools/motion_audit.py` had been auditing a face nobody shipped, and its
numbers should be read knowing what was wrong with them. Its physics comes from
`beat_strip.py`, which still had 28,800 vph and a 15-tooth escape wheel, and
`beat_strip.read` was returning the balance's speed with the face's smear
threshold already multiplied into it, so `motion_audit` applied that threshold a
second time. Its first row, labelled "deployed now", was also drawn with the
shutter off, which the face has never run without. Rate and tooth count now come
from `profiles.json`, `read` returns the speed `Caliber` means by that name, and
the three rows are what ships, the threshold cross-fade that was just removed,
and the build before the smear was pinned. On those rows the jolt, which is the
worst frame's change over the typical frame's, was 44.5x with the threshold and
is 2.0x now. That is the same defect counted a second way. `beat_strip`'s own
strip drawing is still stale for the reasons already given above.

`HANDOVER-REALISM.md`'s closing section has the one left: legibility at the
wall's real viewing distance, through the dial's crystal haze. The wall sheet
answers the scale half of that and nothing has been tried on the haze.
