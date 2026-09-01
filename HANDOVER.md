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
   `models/step/movement.step.py`, which is the actual assembly.

4. `python tools/export_profiles.py`, then Blender, then `tools/smear.py`.
   Unchanged in shape. `export_profiles` now takes the movement from the CAD
   manifest and only draws the plate, the floor and the jewel collars itself.

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

Both pallet stones reach inside the escape wheel's tooth-tip circle by 0.160 mm
and 0.158 mm. Equal lock on entry and exit is what a correctly set escapement
has, and two thousandths of a millimetre apart is not something a drawing gets
by accident.

The stones bear 202.0 and 264.1 degrees from the escape arbor, 62.08 degrees
apart. On a 20-tooth wheel that is 6.90 half tooth-spaces, so 7. The reasoning
already in `escapement_geometry.py` says the count has to be odd or the wheel
arrives with a tooth pointing at the gap between the stones and cannot
alternate. It is odd. Our own figure had been 5.

`scripts/inspect validate` reports ok with zero failures.
`tools/interfere_check.py` reports 7 contacts, all of them press fits and
bearings that are declared with their reason, and no part passing through
another. `tools/placement_invariants.py` passes 7 of 7.

`tools/beat_strip.py` is now stale and was not updated. It draws from
`escapement_geometry`'s own outlines, which are no longer what gets rendered for
any moving part. The question it existed to answer, whether a pallet stone meets
a tooth, is answered above by measurement instead.

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

The plate is the headline item left. It is still ours: a 6.5-unit disc with
bores, plain against the real parts sitting on it. The OM10 mainplate is in
`captures/om10/parts/mainplate.step` if anyone wants to try it, though at this
scale it is 363 face units across against a 252-unit aperture, so bringing it
in is a framing decision and not a drop-in. `HANDOVER-REALISM.md`'s closing
section has the rest of what is still open: viewing-distance legibility through
the dial's crystal, and a bridge-foot screw that sits close to the plate's rim
at the plate's current size.
