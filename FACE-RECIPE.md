# The face recipe

How to take a reference design - a photograph, a brand's product shot, a
sketch with a palette - and put it on the wall as a live, lit, moving watch.
This is the process the blue soleil face was built by, written down so the
next face costs a day and not a fortnight.

The engine does not change between faces. `Rendering/WatchScene.cs` draws
whatever `Rendering/WatchDesign.cs` describes; a new face is a new
`WatchDesign` instance and, at most, one new finish in the shader. Everything
below is about filling that record in the right order and checking each
step on the wall before taking the next.

## The one rule

**Look, do not reason.** Every expensive mistake on this project was an
argument that should have been a render: the environment aimed by
arithmetic (wrong twice), the hands read as swapped from a small strip (they
were not), the plaid on the dial attributed to shadow acne (it was the
softbox's grid). The loop is build, deploy, screenshot, look at the full
1080x1920 frame, and only then change a number. `HANDOVER-REALISM.md` and
`ART-DIRECTION.md` both say it; this file exists because it kept having to be
relearned.

## 0. Inputs

Gather before touching code. Missing any of these is where the time goes.

- **Reference photographs.** At least two: one of the whole watch at a
  normal viewing angle, one macro of the detail that matters (the dial
  finish, the aperture, the hands). Keep them in `captures/reference/`
  (gitignored) and look at them beside every screenshot. The brief calls
  working without a reference "the central handicap of an entire session".
  It was.
- **The palette, as numbers.** Linear RGB for each metal and the dial's body
  tone, and sRGB for any printing. Write them into `Material` statics or the
  design before rendering anything. Do not tune colours against a render;
  the render is what the palette produces under the light.
- **Proportions in one unit.** Case, bezel, dial, index and hand dimensions.
  The existing face uses "face units", 640 across the panel, from
  `tools/case_geometry.py`, converted through `WatchDesign.FaceUnit`. A new
  face can use millimetres directly. Mixing the two is the classic error.
- **The movement.** If it is the OM10, `Assets/movement.glb` and the rotation
  map in `WatchScene.Rotations` are done. A different movement needs
  `tools/gltf_export.py` run against its parts and a new rotation map, and
  that is a project, not a step.
- **The light.** `tools/hdri/*.hdr`. Measure a new panorama before using it:
  `captures/hdri-preview.png` and the block-radiance listing in the session
  notes came from a twenty-line numpy script. What LOOKS bright in a
  tone-mapped preview is often radiance 1; the sources that make polished
  metal read as metal are the ones in the tens.

## 1. Stand the panel up (done once, never again)

`Controls/MovementView` and `Rendering/WatchRenderer` are face-independent:
the swap chain, DPI, resize, device-lost, the fault log, the backdrop
composite. Do not touch them for a new face. If the panel is empty, read
`%LOCALAPPDATA%\ClockWall\render-log.txt` before anything else.

## 2. Geometry, flat-shaded

Fill the dimension half of `WatchDesign`. Build, deploy, screenshot. Judge
only silhouette and proportion against the reference - nothing about light
yet. The checks, in order:

1. The case fills the panel with the margin the reference has.
2. The aperture is where the reference puts it and the movement is right way
   up inside it. (Y-up glTF: if it lies on its side, a consumer is
   double-converting; the exporter is right.)
3. Hands at a known time. Pin them - hour 0, minute 90, second 180 - for one
   build if there is any doubt; the pinned frame is unambiguous where a live
   one at 2:43 is not.
4. Indices: count them, and check the twelve marker is the odd one out.

## 3. Palette and finish, still

Fill the material half. Every surface is a `Material`: base colour, metalness,
roughness along the grain, roughness across it, and a `Finish` that says which
way the grain runs. The finishes that exist:

| Finish | Grain | Used for |
|---|---|---|
| `Isotropic` | none | polished steel, screws, pinions |
| `Dial` | radial from the dial centre | the soleil; also cuts the aperture and prints the track and lettering |
| `Radial` | radial from `FinishCentre` | a sunburst on anything else |
| `Circular` | around `FinishCentre` | wheels, the bezel, the rehaut |
| `Straight` | along `FinishDir`, scalloped | cotes de Geneve on bridges |
| `Perlage` | around hex-grid spots | the mainplate |
| `BlackPolish` | none, mirror | the lever |

A new finish is a new tangent rule in `GrainDirection()` in `watch.hlsl` and
a new enum value in both `Materials.cs` and the shader header. The number is
the contract.

What to know about roughness on brushed metal, because it is the opposite
of intuition: the bright lobes of a sunburst run ALONG the grain, and their
angular width is set by the **along-grain** roughness. Small along-grain
roughness gives sabre-thin streaks; 0.3 gives the wide wedge the reference
photographs show. The across-grain roughness sets how dark the flanks go.

Check: put a still beside the reference and name the differences out loud.
The dial's body tone, the metal's whiteness, the warmth of the brass. Fix
the palette numbers, not the light, if a colour is wrong.

## 4. Aim the studio

The studio panorama is turned by `EnvPitchDeg`, `EnvYaw` and `EnvYawSwing`.
Flat polished metal facing the viewer reflects world +Y; where +Y lands in
the panorama decides whether the hands and indices read as silver or as
gunmetal. Aim it at the one source that is both bright and broad.

**Do not compute this. Run with `CLOCKWALL_DEBUG_VIEW=1`.** Every surface
renders as a mirror of the studio by its normal: the dial shows exactly what
+Y is aimed at, the bezel's dome shows the neighbourhood. Adjust, rebuild,
look again. Two sessions of correct-looking arithmetic put +Y in the wrong
place before this view existed.

Then the fill. `ibl.hlsl`'s `PsEquirect` scales the panorama, knees its
peaks, lifts its floor and adds a soft diffuser over the main box. Those
four numbers are the studio's exposure and they are shared by every face.
If a new face needs them changed, change them and re-check the old one.

## 5. The key light and the rig

`KeyBearingDeg` / `KeyElevationDeg` and their swings; `CameraTiltDeg` and
its swing. The key throws the shadows and the crisp lobes; its wander is
what makes the sunburst sweep. Lower elevation means longer hand shadows.

Check with a sequence, not a still: `--screenshot-seq 4 9000` and lay the
frames side by side. The lobes must move between frames. If they do not,
the anisotropy is not working, whatever a single still looks like.

## 6. The aperture and the depth cues

In order of how much each buys, from `ART-DIRECTION.md`:

1. the sunburst sweeps (step 5)
2. the crystal: a faint sheet that moves independently (`crystal.hlsl`; keep it subtle)
3. the bezel has a wall and casts a shadow (the lathe profile in `BuildCase`, and the shadow map)
4. indices are faceted geometry (`ChamferedPrism`)
5. the hands cast shadows that sweep (`HourBase` etc. - higher hands throw longer shadows)
6. the aperture is a recess (`WellDepth`, and the occlusion term in `watch.hlsl`)
7. depth of field, barely (not implemented; the first thing to add if the face still reads as a picture)

## 7. The wall

Only now judge it as a whole: the full screenshot at real size, from across
the room, and then the app running, not a still. Then the two numbers that
say it can run for days, measured on the deployed build:

- GPU load and power with `nvidia-smi` while the face runs (blue soleil:
  about 35% at idle clocks, 33 W).
- Process CPU and working set over a minute (blue soleil: about 12% of one
  core above the digital face, working set flat).

## The checklist, as a list

- [ ] references in `captures/reference/`, looked at
- [ ] palette written as numbers before the first render
- [ ] `WatchDesign` dimensions; geometry judged flat against the reference
- [ ] hands pinned once and verified
- [ ] materials and finishes; still beside reference, differences named
- [ ] studio aimed with `CLOCKWALL_DEBUG_VIEW=1`, not by arithmetic
- [ ] key and rig; four-frame sequence shows the lobes moving
- [ ] hand shadows visible at wall distance
- [ ] aperture darker than the dial, falling off at its rim
- [ ] full-frame screenshot judged from across the room
- [ ] `nvidia-smi` and process CPU measured on the deployed build
- [ ] committed in small steps with messages that say why

## Traps, all of them measured

- **The face you launch is not the face you built.** `deploy.ps1`.
- **The face choice persists by name** in `clock-mode.txt`; a stale value
  looks exactly like a build that did nothing.
- **The compositor ignores the swap chain's alpha.** The face paints the wall
  colour itself. Do not spend an afternoon on premultiplied alpha.
- **Release strips `Debug.WriteLine`.** The fault log is the only voice the
  renderer has on the wall.
- **A gridded softbox reflects as a grid.** Anything smooth and broad - the
  crystal, a lacquer, a flat mirror - samples the environment blurred on
  purpose. The plaid it makes otherwise looks like a shader bug and is not.
- **A dauphine facet steeper than about ten degrees reflects outside the
  softbox** and the hand goes dark at half the hours.
- **A polygon wound the wrong way faces down.** `ChamferedPrism` checks its
  winding now; anything new that fans a polygon should too.
- **The XAML `ThemeResource` on a `SwapChainPanel` crashed the app at load.**
  Read theme brushes from `Application.Current.Resources` in code instead.
