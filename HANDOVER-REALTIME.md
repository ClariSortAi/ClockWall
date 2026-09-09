# Handover: the real-time renderer

The decision is taken. The watch gets a **real 3D renderer on a
`SwapChainPanel`**, native D3D, not pre-rendered sprite sequences and not a
browser. `PIPELINE.md` argued the case for sequences and lost on the merits;
read it for the analysis of *why the old pipeline caps out*, and ignore its
recommendation.

This file is what the next agent needs and nothing else.

## What is already true

**The asset pipeline works end to end and is committed.**

    python tools/gltf_export.py            # -> captures/gltf/movement.glb

23 named OM10 parts, 339,266 triangles at 4 um deflection, one 11 MB GLB, twelve
seconds. Real extent 30.78 x 5.24 x 30.46 mm - the actual movement, with its
real Z stack. Normals are the analytic CAD surface normals evaluated at each
vertex's UV, never averaged from triangles, which is the difference between a
smooth chamfer and the black slivers on the current bezel.

It emits **Y-up**, because glTF says Y-up. This was got wrong once and the
failure was silent: the movement imported lying on its side and an orbit camera
just looks like it framed the shot badly. If something loads sideways, suspect a
consumer that is double-converting, not this exporter.

**The animation driver already exists and is renderer-agnostic.**
`Services/Caliber.cs` returns

    Reading(Hour, Minute, Second, Escape, Train, Advanced, Balance,
            BalanceSpeed, Fork, Beat)

Every angle is a function of one fractional beat count. No horology needs
writing. Bind these to transforms and the movement runs.

**Cycles on OptiX renders this in 9 seconds** at 1100px / 192 samples on the
2070, which is the offline reference to check the real-time renderer against.
`captures/gltf/preview-34.png` is that reference.

## The rotation map

Derived from `captures/om10/parts/manifest.json`, not guessed: 23 parts on 17
distinct arbors, in millimetres from the movement centre.

| Drive | Arbor (mm) | Parts |
|---|---|---|
| `Reading.Balance` | (-8.06, 3.51) | `staff`, `roller`, `balance`, `collet`, `hairspring` |
| `Reading.Escape` | (-3.68, 7.90) | `escape`, `epinion` |
| `Reading.Fork` | (-5.87, 5.71) | `lever`, and carried by it: `stone_a`, `stone_b`, `guard` |
| `Reading.Train` | (0.00, 8.00) | `wheel_c`, `pinion_b` - this is the seconds wheel |
| derived ratios | various | `wheel_a`, `wheel_b`, `pinion_a` |
| static | - | `mainplate`, `bridge`, `cock`, `screw_a/b/c`, `jewel` |

## Next steps, in order

**1. Stand up the panel with nothing in it.** A `SwapChainPanel` in a new
`Controls/MovementView.xaml`, a D3D11 device, a swap chain sized to the panel,
clearing to a colour, presenting on the existing frame timer. Done when the
panel changes colour on a timer inside the running app. Do this before touching
geometry - if DPI, resize or device-lost handling are wrong, they are much
easier to find against a flat clear than against a watch.

**2. Load the GLB and draw it flat-shaded.** `SharpGLTF.Core` 1.0.6 reads it;
`Vortice.Direct3D11` 3.8.3 is the thinner of the two binding options and
`Silk.NET.Direct3D11` 2.23.0 the other. Both are pure interop over the system
`d3d11.dll` and ship **no native binaries of their own**, which matters here -
see the Smart App Control note in `CLAUDE.md`. Done when the movement appears,
right way up, at the right scale.

**3. Light it.** IBL from `tools/hdri/studio_small_09_2k.hdr` - the same
environment the offline render uses, and `tools/hdri/SOURCE.txt` explains why a
measured studio *is* the material for an all-metal watch. Prefilter it to a
cubemap once at load. Add one directional key with a shadow map. Done when a
still from the panel is recognisably the same object as `preview-34.png`.

**4. Bind `Reading` to the transforms** using the table above. Done when the
escapement runs and the seconds wheel keeps time with the seconds hand.

**5. Add it as a fourth face.** `ClockPanel` cycles faces on C and persists the
choice **by name** in `%LOCALAPPDATA%\ClockWall\clock-mode.txt`. Add the name,
do not renumber - the existing comment explains that a face inserted in the
middle must not reinterpret somebody's saved choice.

**6. Then materials.** Anisotropy is the whole point and is why this pipeline
was chosen: circular graining, straight-grained steel and a polished bevel *are*
anisotropic highlights, and none of them can exist in the current face. glTF
core cannot express anisotropy at all, so `tools/gltf_export.py` does not write
it - the shader supplies it, keyed on part name.

## Traps

**Same arbor does not mean same motion.** `jewel` sits on the escape arbor at
(-3.68, 7.90) and is a fixed jewel. It must not turn with the escape wheel.

**The lever's passengers have misleading axes.** `stone_a`, `stone_b` and
`guard` each carry their own `axis` in the manifest, and it is their own centre,
not their pivot. They are mounted on the lever and must rotate about the
**lever's** arbor. Using their manifest axis spins each in place, which is
wrong in a way that looks like a physics bug rather than a data-reading bug.

**`Reading` has four movement angles and there are more than four moving
parts.** `wheel_a`, `wheel_b` and `pinion_a` have no angle of their own. Either
extend `Caliber` or derive them from the tooth counts, and derive them - the
counts are in `ATTRIBUTION.md` and `escapement_geometry.py`, and inventing
ratios is the specific mistake that section of ATTRIBUTION exists to record.

**Metal viewed straight down goes black.** A metal shows only what it reflects,
so a flat plate under a camera pointing at it reflects whatever is above the
camera, which is nothing. `captures/gltf/preview-lit.png` is that failure and
`preview-34.png` is the same asset at three-quarters. Either the environment
gets something overhead or the face commits to a tilted view. This is a design
decision, not a bug, and it is the same failure `render_lib`'s SOURCE.txt
already records from the other direction.

**`captures/` is gitignored, so none of the input is in the repo.** The 23 OM10
parts came off JTRMain at `192.168.40.47` (the `id_ed25519_msi` key opens it)
from `C:\Dev\ClockWall\captures\om10\parts`, 26 MB. The original 18.8 MB
openmovement STEP is no longer on that machine. A fresh clone can build the app
but **cannot regenerate the GLB**.

**Build framework-dependent, always.** `deploy.ps1`, never `dotnet publish`
self-contained. The reason is in `CLAUDE.md` and it is Smart App Control, not
preference.

## Status, 2026-09-08: built

All six steps are done and on the wall as the fourth face, `live`. What
exists, where, and what the next session should know:

- `Rendering/WatchDesign.cs` is the face as data; `Rendering/WatchScene.cs`
  is the engine. `FACE-RECIPE.md` is the process for the next design, with
  every trap this one hit.
- The materials are anisotropic GGX with a tangent field per finish
  (`watch.hlsl`), and the studio is sampled along the lobe with seven taps.
  The sunburst sweeps; a four-frame sequence shows it.
- The studio is `studio_small_09` aimed at its one big softbox, with a
  synthetic diffuser and fill added in `ibl.hlsl`. Everything about that
  was found with `CLOCKWALL_DEBUG_VIEW=1`, not derived.
- The compositor ignores the swap chain's alpha; the post pass composites
  over the wall colour. Faults go to `%LOCALAPPDATA%\ClockWall\render-log.txt`.
- Measured on the deployed build: about 35% GPU at idle clocks and 33 W;
  about 12% of one CPU core above the digital face; working set flat.

## Status, later the same day: solids and real arbors (branch `mechanism`)

The direction changed: this is to become an object that could be made,
whose time comes from its own mechanism. `main` still runs the face above;
`mechanism` has:

- Every non-movement part as a watertight solid in `tools/case_solids.py`
  (build123d), exported to `Assets/case.glb` and `models/step/case.step`.
  The renderer builds no geometry; `MeshBuilder` is gone.
- Hands on the OM10's own arbors - after a wrong turn. The first attempt
  moved the movement so its centre wheel sat under the dial centre. Then
  the original STEP turned up (owner's OneDrive, now also at
  `captures/om10/om10-00001_20220701_va_01_3.stp`, gitignored) with the
  release notes, which name the parts, and they showed the OM10 already
  carries its hands at its plate centre: cannon pinion `00127`, hour wheel
  `00206`, cannon wheel `00128`, driven indirectly from the off-centre
  centre wheel through the intermediate `00152` (the old `pinion_a`). The
  seconds wheel `00164`/`00165` turns once a minute 8mm out, and the stem
  `00225` fixes three o'clock. With the crown at the wearer's right the
  balance is under eleven and the small seconds at nine. That is the
  layout now. `tools/gltf_export.py` exports all 166 solids into the
  renderer's frame with the plate centre at the dial centre; the design
  says only how deep the movement sits.
- **The open-heart cut.** The OM10 is not an open-heart movement; from the
  dial side its balance is under the plate, the date plate and the dial
  rest. The exporter cuts a window through those three over the balance,
  keeping a bar along the line of centres to carry the three dial-side
  jewel seats. It is the operation a maker performs on a stock movement,
  done to our exported copies; the OM10 files are untouched.
- A crown at three on the OM10's own stem, a stem hole in the band, a
  caseback, hand collars on the OM10's cannon pinion and hour wheel. The
  panel is 720 wide so the crown shows.
- `Caliber.cs`'s header names the seam where the wall clock will become an
  oscillator.

The train, now from the parts themselves: barrel `00121` at 8.0mm from the
centre wheel `00150` (75 teeth, once an hour); centre wheel to the third's
pinion `00161` at 4.68mm; third `00162` (72) to the seconds pinion `00164`
(9); seconds wheel `00165` (84) to the escape pinion (8). The intermediate
`00152` (25) takes the centre wheel to three turns an hour and the cannon
wheel at the plate centre back to one. The minute wheel `00159` and the
barrel's tooth count are not counted yet, so both are drawn static.

## Status, evening: the mechanism keeps its own time

`Services/Mechanism.cs`. A balance with the inertia integrated off the OM10
solids (1.864e-9 kg m^2), a hairspring stiffness, viscous damping, an
escapement that unlocks when the pin enters the fork slot, takes an
unlocking loss, delivers the impulse from a quarter of the half-lift before
centre to the slot's far edge, and locks on drop; a mainspring whose torque
falls linearly over six barrel turns. The beat count is the count of unlock
events; the hands show the set time plus beats over the beat rate. The wall
clock sets it at start-up and again after a five-second stall.

Measured by running it (`Mechanism.Measure`, logged at every launch):
**3.4999 Hz at 285.1 degrees, losing 2.9 s/day** against the caliber's
3.5 Hz. The rate is not typed anywhere; it is the free period pulled slow
by an impulse after centre, which is the escapement error a real lever
shows. It will change as the amplitude falls with the spring. The fault log
gets a line an hour with drift, amplitude and reserve.

What is measured off the solids: the inertia, every tooth and leaf count
(barrel 107, centre pinion 16, third pinion 10, seconds pinion 9,
intermediate 25 with a 20-leaf pinion into the 60-tooth cannon wheel, minute
wheel 48 with 12 into the 54-tooth hour wheel; the cannon pinion is 18 by
the 12:1 the motion works require), the lift angle. What is not: the
hairspring's stiffness - the STEP's strip is a 0.020 mm placeholder that
would beat at 1.5 Hz, so the stiffness is the train's 3.5 Hz against the
measured inertia; the damping, set to give 285 degrees at full wind; the
escapement's efficiency and unlocking loss, ordinary Swiss-lever figures.
Every one of those is named in the class header with its source.

Everything under the dial now turns too: barrel group at 16/107 of the
centre wheel, minute wheel at 18/48 against the cannon pinion.

Not done, in the order they are worth doing:

Winding is wired: past the sixth barrel turn the impulse is zero, the
balance dies down on its damping, and once its swing is inside the lift
angle the pin cannot reach the fork - no unlocks, no beats, the hands
stand. `W` winds the spring and, if the watch had stopped, shakes the
balance to 60% amplitude to start it. Both the stop and each wind go to
the fault log with the drift at that moment. A wall that nobody winds will
show a stopped watch after forty hours, which is the honest behaviour and
the reason the sprite face is still there under C.

Not done, in the order they are worth doing:

1. **Setting.** The five-second stall rule re-sets from the wall clock.
   That is the owner setting it; it is not recorded anywhere but the log.
2. **Name the last 16 of the 166 - done.** 166 of 166 are named in
   `gltf_export.NAMES`, the last sixteen with their confidence in the
   comments and the evidence in `docs/om10-unnamed.md`. Corrections along
   the way: `00197` is the ratchet wheel, not the mainspring; `00120`,
   catalogued as the drum, is the mainspring itself; `00107` is the
   lever's staff and `00111` the impulse pin; `00102` is the dial-side
   pallet bridge.
3. **Depth of field, barely - done** (item 7 below); the crystal's edge
   refraction was computed at 0.27 px at the rim and left undrawn
   (`crystal.hlsl` has the arithmetic); the hairspring breathes (item 3).

Checked and closed: **the balance strobing.** When the balance has swept
more than six degrees since the last colour frame it is drawn as a fan of
copies across that sweep - one per five degrees, up to twenty-four - each
a fraction opaque, deferred to after every opaque part so nothing lands on
top of them. The rim, which maps onto itself, comes out solid; the spokes
come out as the translucent sweep a real balance shows; near the reversals
it is drawn once and sharp, which is the only moment an eye gets one in
focus. The first attempt drew the copies in place and the plate under the
balance, drawn later with depth, wiped them to a ghost. Measured, fixed.

Checked and closed: **mesh phase.** Every wheel-to-pinion drive ratio in
`WatchScene.Rotations` equals its tooth ratio with the opposite sign, so
the STEP's assembled mesh is preserved at every angle by construction. The
escapement, which is not a ratio, was measured: in the STEP the fork slot
sits on the line of centres to 0.06 degrees and the impulse pin on it to
0.16, so the STEP's pose is the mid-transit pose the drive already treats
as zero, and the escape wheel clears both stones (0.03 mm off the entry
stone at rest, no vertex of either inside the other) through the first
three half-teeth at either bank.

## The road to real, in progress

**1. A hairspring that is a spring - done.** `tools/hairspring.py` designs
the strip from the measured inertia and the train's rate the way a spring
maker does: alloy 200 GPa, width 0.16 mm (the OM10's layer), thickness
0.035 mm (a made gauge), so the active length is 127.4 mm, wound as an
Archimedean spiral of 11.5 coils from 0.65 to 2.75 mm with a terminal curve
out to the OM10's stud at 3.10 mm, turning the way the OM10's does. It
writes `Assets/mechanism.json` (inertia, stiffness, every strip number) and
`models/step/hairspring.step`; the exporter puts the solid into the
movement in place of the OM10's placeholder. `Mechanism` reads the JSON
and types nothing. Regulated by the pins' angle for the escapement's
measured error: the watch keeps 3.5000 Hz, +0.0 s/day.

**2. A mainspring that is a spring - done, twice.** The first pass designed
a strip into the barrel's measured cavity (0.14 gauge, half the annulus,
13.6 N mm) and added it to the export as a part of its own. Then the
assembly check (item 5) found that strip inside another solid: `00120`,
catalogued as the barrel drum, is the OM10's own mainspring - a 0.102 by
1.50 mm strip drawn as an 11.75-coil Archimedean spiral from r 1.48 to
6.21, 284 mm long. So `tools/mainspring.py` now measures rather than
designs: the strip's thickness, height and length off its solid by exact
point-in-solid tests, and the cavity (wall 6.626, arbor 1.354, floor -0.85,
ceiling 0.75) off the drum, cover and arbor. That strip in that cavity gives
12.1 turns of which 10.6 are usable above a 1.5-turn hooked-in residual,
7.13 N mm at full wind, a 71 h reserve at the barrel's 6.69 h a turn, and
the train's friction (12% of full) as the torque below which the watch
stops. The mechanism's torque curve is that strip's; the "typical 6 N mm"
was gone before and stays gone. The escapement error moved with the torque
each time and the regulator index was moved to match, which is what a
timing machine is for.

**3. The breathing hairspring - done.** `Finish.Hairspring` in
`watch.hlsl`: the vertex shader turns each point of the strip about the
staff by the balance's angle times one minus the point's fraction along
the strip, which on an Archimedean spiral is read off its radius (the
design's inner and outer radii come from `mechanism.json`). Inner end with
the collet, outer end pinned at the stud, the turn shared out between: the
coils open on one half of the swing and close on the other. The strip's
normals turn with it. It is no longer in the rotation map.

**4. Setting through the crown - done.** The silent re-set from the wall
clock after a stall is gone. A watch keeps running while nobody looks at
it, so on waking the mechanism catches up the real time that passed, ten
minutes of beats per frame, and if the spring ran out while it slept it
stopped then. `S` pulls the crown (it rides out 0.6mm on the stem) and
pushes it in; out, the arrows turn it, a minute a press and an hour with
Shift, moving the cannon pinion on its arbor - the hands and nothing
else, the balance swinging on, as the OM10 has no hacking lever. The
system clock is now read exactly once, at launch: the owner setting the
watch from a reference. Every pull, push and wind goes to the log.

**5. Assembly check - done.** `tools/assembly_check.py` intersects our
solids with the OM10's as B-reps (`BRepAlgoAPI_Common`, exact, no meshes)
through their working ranges: each hand round the dial, the balance through
its 285 degrees either way, the lever bank to bank, the escape wheel over a
tooth, the intermediate in its two bearings, and the fixed parts against
everything they could touch. Any common volume over a speck (1e-4 mm3) is
a clash. The first run found sixteen; the fixes were the kind a number
cannot show on the wall: the hands' collars were solid rods with the
pinion inside them (now tubes, minute inside hour, bored to the pipes they
press on); the dial sat 0.35 mm into the case's flange (the flange is at
the dial's underside now); the rehaut's well wall ran through the dial and
the plate (dial hole and plate window opened to clear it, the plate's
retained bar stopped short of it); the stem hole began at the band and
missed the flange it crosses first; the cap reached down through both
collars. The second run's biggest clash, 10 mm3 of designed mainspring
inside "barrel_drum", was the STEP telling us that `00120` IS the
mainspring (item 2, above). The one overlap left is the OM10's own: the
spring's inner end hooked into the arbor's hub, 0.037 mm3, a joint, and
the check reports it as one. The peer session's fits study
(`docs/om10-fits.md`) found the file's one interference, the intermediate's
upper bearing left at the old pivot size; `gltf_export.BORED` opens it and
the check turns the intermediate in it. Output is
`captures/assembly-check-*.txt`; a clean run is `0 clashes`, exit 0.

**6. Print it - done, with the peer session.** `PRINT-STUDY.md`
settles the scale (3.4x on a 50 um MSLA machine, three prints of about
104 mm) and finds that the running fits, not the walls, govern: the
tightest is 0.0063 mm on the diameter, and no scale a printer can hold
pays for that. So the bearings are bored open in the model instead:
`tools/print_bores.py` (branch `fits-study`) opens every bearing in
`Assets/om10-fits.json` until the gap at the chosen scale is what the
machine holds, pivots untouched, and proves each opening breaks into
nothing. `tools/print_export.py` writes the set: every part, ours and
the OM10's, prepared as the wall export prepares them and with the bore
table applied when `Assets/print-bores.json` exists, one binary STL each
in one frame at one scale into `captures/print/<scale>x/` with a
manifest that marks the springs and the jewels as not for printing. Run
with the table: 177 STLs at 3.392x, every one watertight, and the bored
bearings measure in the STL what the table says (intermediate_bearing
1.044 mm against 1.047 asked, the difference the tessellation's chord).
`assembly_check.py --print` runs the same check on the bored set: 0
clashes, on both machines, and the intermediate clears both its bearings.
Done.

**The studio, in physical units (2026-09-08).** `Rendering/Lighting.cs`:
seven numbers - key bearing, elevation, lux, kelvin, angular size; ambient
lux; EV100 - on keys through the same chain as the crown, with a four-second
readout on the panel and a one-line file for persistence, and as sliders
across the top of the wall (`Controls/StudioStrip`, behind a STUDIO toggle,
L) on scales `LightRig.Scale` decides - stops for amounts of light; the
strip's bounds are cut out of the window's drag region as a passthrough
(`InputNonClientPointerSource`) so it takes the pointer. Poking the running
build from a script needs physical pixels: the DWM extended frame bounds and
a DPI-aware thread, or every click lands 40 px off. Colour from
Planck's law; the HDRI calibrated off its own irradiance read back after
the bake; the softbox's size in the penumbra (PCSS) and in the highlight
width (Karis); exposure the Filament way. Defaults reproduce the designed
face: 700 lux key, 1000 lux ambient, EV 8.2. Not done: the panorama's own
softbox and the key are two copies of one light (the key dominates it
five to one); a rectangular area light (linearly transformed cosines,
anisotropic) would replace both with one.

**The small seconds, and the bearings the heart had bared (2026-09-09).**
The OM10's fourth wheel pinion comes up at nine, 1.9 mm under the dial,
inside the open heart, where the seconds hand was a bare needle among the
wheels. Sizing a sub-dial for it exposed a flaw the interference check
never asked about: the window as first cut had removed the plate from
round the dial-side bushes of the seconds pinion (`train_bearing_2`, cad
(0, 8)) and the third pinion (`train_bearing`, cad (4.45, 8.12)). Nothing
clashed, because the bushes are their own solids and stayed put in the
file; in a made watch the train would have fallen over. The plate now
keeps a boss round each on a second bar, from the third's boss through
the seconds' to the window's wall - the bridge an openworked plate has
(`gltf_export.open_heart`). The lesson for the checker: "held" is a
different question from "clear", and it is not yet asked automatically.

On that bar stands the fixture (`tools/case_solids.py`): the opening is
now a keyhole, the heart bulged out 4.6 mm round the seconds arbor, and in
the bulge a chapter ring 8.5 mm across floats over the movement on two
posts screwed to the bar, its sixty-groove track engraved and ink-filled
(the ink its own solid, white where the ring is black), and a polished
steel hand with a counterweight on the pinion's extended pivot. The
shader's recess term takes the keyhole as two circles (`Aperture2`). The
heart was not made smaller, on the owner's instruction; it got bigger.

**The centre-seconds conversion (2026-09-09).** The owner wanted a sweep
hand. The OM10 has nothing at its centre turning once a minute and a solid
centre post, so this is a conversion, done the way they have been done for
a century: an indirect centre seconds on the back (`tools/sweep_seconds.py`,
`models/step/sweep-seconds.step`). Where it could go was measured off the
solids first: the dial side is crowded to the middle by the motion works
and the cannon pinion's pipe is blind; the back, below the barrel bridge
and the train bridge, is free to the caseback. So: a transfer wheel on the
fourth pinion's lengthened back pivot, an idler on a stud, a centre wheel
on a dia 0.30 arbor, all 40 teeth at the train's module 0.11 (involute,
20 degrees, generated), under a Y-shaped cock with two jewels screwed to
the two bridges, with a friction spring on the centre wheel's hub. The
arbor runs up through the barrel bridge, the centre post (a 0.17 mm tube
now, as centre tubes are) and the cannon pinion, drilled through, to a
polished hand with a counterweight above the minute hand. The hands came
down (hour 0.75, minute 1.15) so the sweep hand clears the crystal by 0.3;
the cap is a ring; the case is 1.8 deeper and the caseback further back,
which also fixed a caseback that had sat 0.1 mm INTO the bridges' backs
unchecked. The small-seconds fixture and its keyhole are retired (the bar
and its bosses stay: the bearings still need holding). The assembly check
turns the meshing pairs together through a tooth pitch, and the arbor
through its four bores. Every changed OM10 solid is listed in
`ATTRIBUTION.md`. What is NOT modelled: the module's extra friction on the
train (the mechanism's friction fraction is unchanged), and the fourth
wheel's endshake with the longer pivot.

**Gold, by its constants (2026-09-09).** The centre seconds hand is gold:
not a colour but Johnson & Christy's n and k at three wavelengths, with the
exact conductor Fresnel evaluated in `watch.hlsl` (`F_Conductor`; the
split-sum's F0 A + B is replaced by the exact reflectance at the view
angle for such metals), so the reflectance at normal incidence and the
climb to white at grazing both fall out of the physics. Two things
learned: a flat polished hand under a softbox is all highlight and reads
white whatever its metal, so the hand's needle is half-round in section
and shows a bright line along its crown with the gold either side; and
iron's constants, tried for the case, made polished steel cream (iron's
F0 is warm), so the case keeps the palette's cool tone until constants
for a chromium-rich stainless surface are to hand. `Material.Conductor`
is the way to give any part its constants.

**7. Cosmetic - done; the crystal since redone as glass.** The crystal is
now a box sapphire with a bevel standing proud of the bezel, and its shader
a light path: a four-layer anti-reflective stack by the transfer-matrix
method, refraction through the sapphire to what is behind, the underside as
a second mirror, the key's glint on both surfaces, and the wear. See
`FACE-RECIPE.md` 6b. The refraction that was declined below was declined
for the OLD low dome; the bevel is where it earns its place. Depth of field: a
second target carries view distance out of the watch pass and the post
pass gathers a small disc weighted by each tap's own circle of confusion;
focus a millimetre behind the dial, a pixel of blur per four millimetres,
capped at a pixel and a half, so the bezel's rim goes a hair soft and the
balance stays readable (twice that turned the open heart to mush). The
last sixteen names, above. The crystal's edge refraction: the dome is a
375 mm sphere, its rim tilts 3.75 degrees, sapphire bends the ray 1.6
degrees for 0.8 mm, 0.023 mm of shift, 0.27 px at this rig's 11.8 px/mm.
Not drawn; the arithmetic is in `crystal.hlsl` so nobody re-derives it.

## The licence question, asked and answered

**Settled 2026-09-08: not a concern.** This is a wall clock in somebody's
house, not a product, and it is not being distributed. The owner was asked and
said so. Do not re-raise it; the rest of this section is kept only so that
whoever forks this knows what changed and why the old note existed.

**The licence position changes the moment this ships.**

`ATTRIBUTION.md` says, in terms: *"This project uses the geometry to render a
decorative wall clock and redistributes no OM10 source file, only rendered
images of the parts. If you fork this and mean to redistribute anything derived
from the STEP itself, check the current terms with openmovement first."*

The current face is safe because it ships **pictures**. A real-time renderer
ships the **geometry** - `movement.glb` is a derived work of the OM10 STEP,
distributed inside the application. That defence does not survive the change.

That would matter for anything distributed, and it would want checking before
the renderer was built rather than after, since it could constrain what the GLB
may contain. It does not matter here. Note also that
`models/step/movement.step` was already committed and is already derived from
the STEP, so nothing about the real-time work is a new step in that direction.

openmovement is open-source and the download sits behind a free registration
rather than a licence fee. Anyone forking this to redistribute should check the
current terms; anyone building a clock for their own wall should not.
