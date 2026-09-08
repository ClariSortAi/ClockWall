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
measured inertia; the mainspring's torque - the STEP's spring is a ring -
so 6 N mm, typical; the damping, set to give 285 degrees at full wind; the
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
2. **Name the last 16 of the 166.** `Assets/movement-parts.json` carries
   every part's position; 150 are named from the release notes and the
   geometry (the shock settings both sides, the raquetterie, the bearings,
   the keyless works, the date works, the fixings). The 16 still by id are
   small keyless and cock-side pieces whose role the geometry alone does
   not settle. One correction on the way: `00197`, first taken for the
   mainspring, is the ratchet wheel; the STEP has no mainspring.
3. **Depth of field, barely**; the crystal's edge refraction; the hairspring
   still turns rigidly.

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

**2. A mainspring that is a spring - done.** `tools/mainspring.py` measures
the OM10's barrel cavity off its own solids by cross-section (wall 6.45 mm,
arbor 1.36, 2.05 high - the first ray-based measurement flaked and read
4.64; sections are repeatable) and sizes the strip into it the way a barrel
is sized: half the annulus, 0.14 mm gauge, so 1.95 wide and 446 mm long,
10.8 turns of which 9.3 are usable above a 1.5-turn hooked-in residual;
13.6 N mm at full wind, a 62 h reserve at the barrel's 6.69 h a turn, and
the train's friction (12% of full) as the torque below which the watch
stops. The solid, coiled on the arbor, joins the movement export as a part
of its own. The mechanism's torque curve is that strip's; the typical
"6 N mm" is gone. The escapement error grew with the torque (-2.9 to -7.2
s/day) and the regulator index was moved to match, which is what a
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
