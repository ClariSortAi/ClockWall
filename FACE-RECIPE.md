# The face recipe

How to take a reference design - a photograph, a brand's product shot, a
sketch with a palette - and put it on the wall as a live, lit, moving watch.
This is the process the blue soleil face was built by, written down so the
next face costs a day and not a fortnight.

## Where this is going, read first

This watch is meant to become an object that works: **every part a
watertight solid that could be made, and the time driven by the mechanism
rather than the system clock.** That is the direction of travel and it
shapes every step below:

- Shapes live in CAD (`tools/case_solids.py`, build123d), exported to a GLB
  for the renderer and a STEP for anything that measures, checks or prints.
  The renderer builds no geometry. A shape that is wrong is fixed in CAD.
- Hands sit on arbors that exist. The hour and minute hands are on the centre
  wheel, which the placement puts under the dial centre; the seconds hand is
  on the fourth wheel's arbor, wherever the placement puts it. Nothing turns
  about a point with no axle under it.
- Motion comes from `Services/Caliber.cs`, whose beat count is the seam: today
  it is the wall clock, tomorrow an integrated oscillator. Its header says so.
  The renderer consumes a `Reading` and does not care which.

Appearance work - the rest of this file - is one lane of that road. It is
not the whole road, and a decision that makes the face prettier by making
it less of a mechanism is the wrong decision.

## The one rule

**Look, do not reason.** Every expensive mistake on this project was an
argument that should have been a render: the environment aimed by
arithmetic (wrong twice), the hands read as swapped from a small strip (they
were not), the plaid on the dial attributed to shadow acne (it was the
softbox's grid), a black panel attributed to timing (a culled full-screen
triangle). The loop is build, deploy, screenshot, look at the full 1080x1920
frame, and only then change a number.

## 0. Inputs

Gather before touching code. Missing any of these is where the time goes.

- **Reference photographs.** At least two: one of the whole watch at a
  normal viewing angle, one macro of the detail that matters (the dial
  finish, the aperture, the hands). Keep them in `captures/reference/`
  (gitignored) and look at them beside every screenshot.
- **The palette, as numbers.** Linear RGB for each metal and the dial's body
  tone, and sRGB for any printing. Write them into `Material` statics or the
  design before rendering anything. Do not tune colours against a render.
- **Proportions in millimetres.** Case, bezel, dial, index and hand
  dimensions. The blue soleil carries case_geometry.py's "face units" (640
  across the panel) through `WatchDesign.FaceUnit`; a new face should just
  use millimetres in `case_solids.py`.
- **The movement.** If it is the OM10, `Assets/movement.glb` (all 166
  solids, `tools/gltf_export.py` from `tools/om10_extract_all.py`), the
  rotation map in `WatchScene.Rotations` and the open-heart cut are done,
  and the layout is the OM10's own: hands at its plate centre, small seconds
  at nine, crown at three, balance under eleven. A different movement needs
  its own extraction, naming and rotation map, and that is a project. Get
  its STEP and its parts list first; every role inferred from geometry on
  this project was wrong.
- **The light.** `tools/hdri/*.hdr`. Measure a new panorama before using it:
  what LOOKS bright in a tone-mapped preview is often radiance 1; the
  sources that make polished metal read as metal are the ones in the tens.
  `captures/hdri-preview.png` came from twenty lines of numpy.

## 1. Stand the panel up (done once, never again)

`Controls/MovementView` and `Rendering/WatchRenderer` are face-independent:
the swap chain, DPI, resize, device-lost, the fault log, the backdrop
composite. Do not touch them for a new face. If the panel is empty, read
`%LOCALAPPDATA%\ClockWall\render-log.txt` before anything else.

## 2. Solids, flat-shaded

Build the case set in `tools/case_solids.py`: case, caseback, crystal, dial
with its holes, rehaut, indices, the three hands with their tubes and arbor,
the cap, the crown. Every part must pass `is_valid` and have a volume; the
script refuses otherwise. Run it; it writes `Assets/case.glb` and
`models/step/case.step`. Build, deploy to the dev slot, screenshot. Judge only
silhouette and proportion against the reference - nothing about light yet:

1. The case fills the panel with the margin the reference has, and the crown
   is not clipped (the panel is wider than it is tall for that reason).
2. The aperture is where the placement puts it and the movement is right way
   up inside it. (Y-up glTF: if it lies on its side, a consumer is
   double-converting; the exporter is right.)
3. Hands at a known time. Pin them - hour 0, minute 90, second 180 - for one
   build if there is any doubt; the pinned frame is unambiguous where a live
   one at 2:43 is not. Check the seconds hand sits on the fourth wheel.
4. Indices: count them, and check the twelve marker is the odd one out.

The placement itself (`PlacedArborCad`, `PlacedArborWorldXZ`,
`MovementRotationDeg`, and the aperture that follows from it) is derived
from the manifest's arbors, not chosen by eye. The derivation for the blue
soleil is a dozen lines of Python in the session notes; repeat it for a
different composition rather than nudging numbers.

## 3. Palette and finish, still

Fill `WatchDesign.Case` and `WatchDesign.Movement`. Every surface is a
`Material`: base colour, metalness, roughness along the grain, roughness
across it, and a `Finish` that says which way the grain runs:

| Finish | Grain | Used for |
|---|---|---|
| `Isotropic` | none | polished steel, screws, pinions |
| `Dial` | radial from the dial centre | the soleil; also prints the track and lettering |
| `Radial` | radial from `FinishCentre` | a sunburst on anything else |
| `Circular` | around `FinishCentre` | wheels, the bezel, the rehaut, the crown |
| `Straight` | along `FinishDir`, scalloped | cotes de Geneve on bridges |
| `Perlage` | around hex-grid spots | the mainplate |
| `BlackPolish` | none, mirror | the lever |

A new finish is a new tangent rule in `GrainDirection()` in `watch.hlsl` and
a new enum value in both `Materials.cs` and the shader header. The number is
the contract.

On brushed metal, the opposite of intuition: the bright lobes of a sunburst
run ALONG the grain, and their angular width is set by the **along-grain**
roughness. Small gives sabre-thin streaks; 0.3 gives the wide wedge the
reference photographs show. The across-grain roughness sets how dark the
flanks go.

Check: a still beside the reference, differences named out loud. Fix the
palette numbers, not the light, if a colour is wrong.

## 4. Aim the studio

`EnvPitchDeg`, `EnvYaw`, `EnvYawSwing`. Flat polished metal facing the viewer
reflects world +Y; where +Y lands in the panorama decides whether the hands
and indices read as silver or as gunmetal. Aim it at the one source that is
both bright and broad.

**Do not compute this. Run with `CLOCKWALL_DEBUG_VIEW=1`.** Every surface
renders as a mirror of the studio by its normal. Adjust, rebuild, look again.

Then the fill. `ibl.hlsl`'s `PsEquirect` scales the panorama, knees its
peaks, lifts its floor and adds a diffuser over the main box. Those numbers
are the studio's exposure and are shared by every face; if a new face
changes them, re-check the old one.

## 5. The key light and the rig

`KeyBearingDeg` / `KeyElevationDeg` and their swings; `CameraTiltDeg` and
its swing. The key throws the shadows and the crisp lobes; its wander is
what makes the sunburst sweep. Lower elevation means longer hand shadows.

Check with a sequence, not a still: `--screenshot-seq 4 9000` and lay the
frames side by side. The lobes must move between frames.

## 6. The aperture and the depth cues

In order of how much each buys, from `ART-DIRECTION.md`:

1. the sunburst sweeps (step 5)
2. the crystal: a faint sheet that moves independently (`crystal.hlsl`; keep it subtle)
3. the bezel has a wall and casts a shadow (the case profile, and the shadow map)
4. indices are faceted geometry (chamfered prisms in the CAD)
5. the hands cast shadows that sweep (hand heights in the CAD - higher hands throw longer shadows)
6. the aperture is a recess (the rehaut's well in the CAD, and the occlusion term in `watch.hlsl`)
7. depth of field, barely (not implemented)

## 7. The wall

Only now judge it as a whole: the full screenshot at real size, from across
the room, and then the app running, not a still. Then the two numbers that
say it can run for days, measured on the deployed build with `nvidia-smi`
and the process CPU over a minute.

## The checklist

- [ ] references in `captures/reference/`, looked at
- [ ] palette written as numbers before the first render
- [ ] solids in `case_solids.py`; all valid; STEP written
- [ ] placement derived from the manifest, hands on arbors that exist
- [ ] geometry judged flat against the reference; hands pinned once
- [ ] materials and finishes; still beside reference, differences named
- [ ] studio aimed with `CLOCKWALL_DEBUG_VIEW=1`, not by arithmetic
- [ ] key and rig; four-frame sequence shows the lobes moving
- [ ] hand shadows visible at wall distance
- [ ] aperture darker than the dial, falling off at its rim
- [ ] full-frame screenshot judged from across the room
- [ ] `nvidia-smi` and process CPU measured on the deployed build
- [ ] committed in small steps with messages that say why

## Traps, all of them measured

- **The face you launch is not the face you built.** `deploy.ps1`; use
  `-Dest` for a dev slot so the wall keeps running.
- **The face choice persists by name** in `clock-mode.txt`; a stale value
  looks exactly like a build that did nothing.
- **Smart App Control blocks a fresh DLL, intermittently.** The event log
  says `0x800711C7`. Run it again; it is not your code.
- **The compositor ignores the swap chain's alpha.** The face paints the wall
  colour itself. Do not spend an afternoon on premultiplied alpha.
- **Release strips `Debug.WriteLine`.** The fault log is the only voice the
  renderer has on the wall; it also records each scene build and its time.
- **A gridded softbox reflects as a grid.** Anything smooth and broad - the
  crystal, a lacquer, a flat mirror - samples the environment blurred on
  purpose. The plaid it makes otherwise looks like a shader bug and is not.
- **A dauphine facet steeper than about ten degrees reflects outside the
  softbox** and the hand goes dark at half the hours.
- **Rasterizer state leaks between passes.** The crystal's back-culling
  state culled the post pass's clockwise full-screen triangle and the panel
  showed a never-painted black. Set every state you depend on, every pass.
- **The XAML `ThemeResource` on a `SwapChainPanel` crashed the app at load.**
  Read theme brushes from `Application.Current.Resources` in code instead.
