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
- Hands on real arbors. The placement puts the OM10's centre wheel
  (`wheel_a`, 75 teeth, once an hour by the derived train) under the dial
  centre and turns the assembly 272.70 degrees so the balance sits straight
  below at 15.10mm. The hour and minute hands are on tubes at that arbor;
  the seconds hand is on an extension of the fourth wheel's arbor, 8mm out
  at seven o'clock, inside a 9.6mm aperture pulled 30% of the way from the
  balance toward it. The seconds arbor's world position is derived through
  the placement, never typed.
- A crown and stem at three on the case band, a caseback, tubes for the
  cannon pinion and hour wheel. The panel is 720 wide so the crown shows.
- `Caliber.cs`'s header names the seam where the wall clock will become an
  oscillator.

What the train analysis established, from the manifest's arbors and radii
(the original STEP is on no machine here, so this is all the evidence there
is): `wheel_c` (84) is the fourth wheel driven by `epinion`; `wheel_b` (72)
is the third, driving `pinion_b` (9); `wheel_a` (75) drives the third's
pinion at 4.68mm and is the centre wheel; `pinion_a` (25 leaves, full
height) meshes `wheel_a` at 5.50mm and its role is not known. The barrel is
not among the parts and, by the centre wheel's position, would have been
near the plate centre, 8.2mm from it.

Not done, in the order they are worth doing:

1. **The oscillator.** Replace the wall clock in `Caliber.Read` with an
   integrated balance and an event-based escapement. The contract stays.
2. **The missing parts, if the direction holds:** motion works, cannon
   pinion and hour wheel with teeth, barrel and mainspring, keyless works.
   None is visible from the front; all are needed for a thing that runs.
3. **Whether the OM10's stem slot is at three** after the placement. The
   plate's rim has a 36 degree opening at CAD azimuth 264 that may be it.
4. **The balance strobes** at speed; a sub-step additive draw gated on
   `BalanceSpeed` is the cheap fix.
5. **Depth of field, barely**; the crystal's edge refraction; the hairspring
   still turns rigidly.

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
