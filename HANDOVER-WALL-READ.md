# Handover: the honest read from the wall, 2026-09-08

Written on the machine that had never seen this face. It pulled the 25 commits,
built them, put them on the 1080x1920 wall and looked. Nothing here was fixed.
This is a reading and a decision, and the decision is not mine to take.

## First, a trap that cost ten minutes

The face did not appear. The build was clean, the assets were there, and the
wall showed the flat digital clock from August.

`%LOCALAPPDATA%\ClockWall\clock-mode.txt` held `digital`, written by a session
on this machine on 08-29 and outliving every build since. `ClockPanel`'s
constructor restores it by name, which is the right design and is why the stale
value survived three faces being added. A machine that has run an older
ClockWall will not show the new face until that file is changed or C is pressed
twice. It is not a build failure and it looks exactly like one.

## What the wall showed

Verbatim, because the phrasing is the evidence:

- "It looks like it's moving really weird."
- "The little gears inside of the little window don't look realistic."
- "There's also a random shadow at the twelve o'clock position."
- "Vertical black lines at the very top of the outside silver bezel that look
  completely unnatural."
- "Whatever mechanism is here to create the view of depth between the bezel and
  the watch face isn't quite realistic."

Note what is not in that list. Nothing about proportion, layout, tooth count,
pivot placement or the escapement's geometry - the things the last three
sessions spent themselves on. The geometry work landed. What is left is light.

## What the pixels say

Measured off `captures/mechanical-face.png`, the 1080x1920 screenshot this
build renders with `--screenshot`. Numbers, not impressions.

**The twelve o'clock shadow is a seam, and it is on the centreline.** In the
dial band above the printing (y 300-380, chosen because the `CW - OPENWORKED`
line and the hour hand both contaminate anything lower) there is a dark column
6 pixels wide at its half-depth, 11.6 per cent below the surrounding dial. Its
minimum sits at x=540. The case spans x=226 to x=852, so the dial's centre is
x=539.0. The column is on the dial's exact vertical centreline, to within a
pixel. A shadow cast by something would not land there and would not be
straight; a radial texture whose two ends do not meet would land exactly there.
Read it as a wrap seam in the sunburst, not as a shadow.

I could not test whether it repeats at six o'clock. The aperture occupies the
lower dial and there is no clean dial left to measure. Someone should confirm
the seam is single before assuming which radius it is on.

**The bezel shards are real and they are near-black.** Constrained to inside
the case outline, so background cannot be mistaken for bezel: at y=248 a
30-pixel run below luminance 40 inside a bezel whose lit pixels average 191. At
y=256, three separate runs of 10, 5 and 6 pixels. They thin out by y=288. They
sit on the inner flank of the bezel roughly between half past ten and half past
one. Against a surface averaging L=191 these read as holes, which is what makes
them look unnatural rather than merely dark - there is no penumbra, they go
straight to black over one or two pixels.

**The aperture is flat, and flat in a specific way.** Nothing casts a shadow on
anything. The wheels, the lever, the balance and the plate all sit at one
apparent depth. The bores read as painted black ellipses because no countersink
catches light. The plate's graining reads as a repeating checker rather than
perlage. The lever and pallet region is a dark cluster that does not resolve
into a component. The one part that reads is the fourth wheel, and it reads
because it has spokes and a jewel to catch an edge on.

**There is no wall between the dial and the bezel.** No rehaut, and no shadow
thrown by the bezel's overhang onto the dial edge. The transition is a hard
bright-to-dark stroke. That is what "the mechanism to create depth isn't quite
realistic" is pointing at: the depth cue is a line, and a line is what you draw
when you are not lighting a surface.

**The motion complaint is not measured.** A screenshot cannot show it and I did
not instrument it. `HANDOVER.md` already predicts a specific way this can look
wrong - the balance's three arms alias past 60 degrees per frame and can appear
to run backwards - and says in terms that the defence against it is "an
argument rather than a measurement". Treat "it's moving really weird" as the
first outside report against that open question, not as a new one.

## The finding that matters

The flatness is not an oversight. It is the price of a law this repo already
wrote down, and the law is correct.

`HANDOVER.md`: **nothing directional may be baked into a layer that moves.**
Bake a cast shadow or a raking highlight into a sprite the app rotates and it
orbits the arbor once per turn. So every layer the XAML turns - the five
movement groups, their smear twins, and the three hands - is rendered with
`world_axial`, `lights_axial` and no shadow catcher. Rotating it is then a
symmetry of everything lighting it.

Rotationally symmetric lighting is, by construction, the lighting that produces
no form. There is no direction for a highlight to come from. That is the whole
mechanism behind "the little gears don't look realistic": the parts the eye
goes to are precisely the parts that architecturally cannot have a directional
highlight or a contact shadow. `placement_invariants.py` is not a bug catcher
here, it is the enforcer of that constraint, and it passes cleanly on this
machine - all invariants hold, worst stray alpha 1.1 per cent.

So the ceiling is structural. Pre-render a sprite per part and rotate it in
XAML, and the movers must stay flat. The three sessions of geometry work were
not wasted, but no amount of further geometry, material or finish work on a
rotating layer will move this, because the light is the thing that is missing
and the light is what the architecture forbids.

The fork, stated so the next session starts from it rather than rediscovering
it:

1. **Keep the architecture and stop spending on movers.** Put the remaining
   effort into the four static layers, which keep their directional key and
   catcher: the case, the base plate, the cock and the hand cap. The gears stay
   flat. This is cheap and it has a known ceiling.

2. **Pre-render each mover as a sequence rather than a sprite.** N angles per
   part, each lit correctly and directionally, and the app plays a frame
   instead of rotating one image. Directional light becomes legal on movers and
   the flatness goes away. Costs N times the assets and memory, and it changes
   what `placement_invariants` means - the centroid check exists precisely
   because there is one image per part.

3. **Light it live.** Real-time 3D in the app rather than pre-rendered layers.
   Removes the constraint at the root and is the largest change by a wide
   margin.

This is a product decision about how much the wall is worth, not a rendering
question, which is why it is written here and not taken.

## Two defects that are not about any of that

The seam and the bezel shards are both on `case.png`, which the XAML holds
still. Static layers keep their directional key and their shadow catcher, so
neither defect is constrained by the law above. They are ordinary render bugs
on a layer that is allowed to be lit properly, and they are the cheapest real
improvement available. They are also, notably, two of the five things the wall
actually complained about.

## The tooling, and what it does and does not solve

This machine had none of it. It now has what the other machine had, and the
research behind that list is worth recording because the obvious answer is
partly wrong.

The obvious answer is [blender-mcp](https://github.com/ahujasid/blender-mcp),
which is what most public writing on "Claude plus Blender" means. It is already
in this repo - `.mcp.json` declares it and `tools/blender_live.py` starts a live
Blender for it. But `blender_live.py`'s own docstring is careful about why: the
headless render is what ships and should stay that way, and the live session is
for *looking* at a part from an angle before committing eight minutes to a
render. That division is right and should be kept. A socket-driven GUI Blender
is not going to author the material node graphs `render_lib` already has.

`HANDOVER-REALISM.md` reached the same verdict about `blender-toolkit` and said
so: its material vocabulary is create/set-colour/set-metallic, which cannot
express these node graphs, and our render is headless. It is installed for
parity with the other machine, not because it fits.

**The twenty skills are for a different genre of work, and it is worth being
blunt about it.** They assume the product-visualisation reel: import a mesh, put
it on a pedestal, light it from an HDRI, orbit a camera, export a video. This
project is close to the opposite shape - a fixed top-down render of a
CAD-accurate assembly, cut into per-part sprite layers, composited and animated
by a XAML app that never moves a camera at all.

Concretely, of the twenty: six are camera animation (`turntable`, `crane-shot`,
`dolly-rotate`, `slow-zoom`, `perfect-loop`, `dynamic-full-loop`) and all six
drive `render.anim` over a frame range, which this pipeline never does. Two are
Meshy photogrammetry (`image-to-3d`, `multi-image-to-3d`), which would replace a
real Swiss movement's STEP geometry with a guessed mesh and destroy the
provenance `ATTRIBUTION.md` exists to state. Six more - the five PolyHaven
skills and `product-polish` - are Node scripts that drive a *live GUI* Blender
over MCP port 9876, so none of them can run in the headless pipeline;
`product-polish` additionally clears the scene and switches to EEVEE, which
would demolish anything `render_lib` had built.

The PolyHaven ones in particular have nothing left to give this repo, and the
reason is a small compliment to the last session: `render_lib.HDRI` is already
`studio_small_09_2k.hdr`, which is the exact default `polyhaven-studio-setup`
would download. It is vendored under `tools/hdri/` with a SOURCE.txt explaining
why a measured studio environment is not lighting but *is* the material for an
all-metal watch, and the exposure is derived from the HDRI rather than tuned
against it. The one thing worth keeping from that group is an idea rather than
a script - `polyhaven-hdri-showcase`'s notion of rendering one subject under
several environments and comparing - which is a legitimate technique for the
bezel and dial work, and which `render_lib.world()` already takes a path
argument for.

The one skill from that set that genuinely fits is `cad`, because it is
build123d, which is the kernel `models/step/movement.step.py` and
`case_geometry.py` already use. Its `cadgen` runtime is not installed and is not
needed; the value is in `references/build123d-modeling.md`, `positioning.md` and
`step-generation.md`. `dxf` is the same kernel aimed at 2D and is marginal.
`threejs-export` is irrelevant unless option 3 above is taken, in which case it
stops being irrelevant, since the app already ships WebView2. `openscad` is a
different kernel entirely and `mechanical-engineer` is a prose description of
the profession.

**Nineteen of the twenty were removed and four better ones installed.** The
replacements come from [ra100/blender-claude-plugin](https://github.com/ra100/blender-claude-plugin)
(MIT), which is reference documentation rather than scripts that drive a GUI -
SKILL.md plus a node catalogue and a Python API reference per domain. Its
MCP-first preamble degrades correctly: with no MCP server connected it emits bpy
Python, which is exactly what `render_lib` is.

- `blender-shader-nodes` (792 lines) is the important one, and the reason is
  specific. `render_lib` builds every material from about twenty nodes, and the
  graining is `ShaderNodeTexWave` driven through `Mapping` and `TexCoord`. There
  is no `ShaderNodeTangent` anywhere in it, and Tangent is the node that emits a
  **radial** tangent - which is what circular graining and a sunburst dial are.
  A linear wave forced into a radial layout by mapping is exactly the kind of
  construction that produces one discontinuity on one radius, which is what the
  twelve o'clock seam measures like. The same reference also carries
  `ShaderNodeBsdfMetallic` (complex IOR, anisotropy, tangent - new in 5.0, and a
  better fit than Principled for a watch where SOURCE.txt already argues the
  environment *is* the material) and `ShaderNodeTexGabor` (directional
  anisotropic noise, which is what cotes de Geneve is). None of the three is in
  use today.
- `blender-modeling-modifiers` (992 lines), because `render_lib` cuts its
  chamfers with a BEVEL modifier and the bezel shards look like a bevel or
  normals artifact. Twenty-one references to bevel and forty to normals.
- `blender-scene-rendering` (1752 lines) for Cycles, sampling, denoising and
  clamping.
- `blender-python-scripting` (1445 lines) for the bpy data model, since
  `render_lib` is a thousand lines of it.

Four of the eight in that plugin were skipped after checking this pipeline
against them: geometry nodes, compositing, animation/rigging and physics. The
pipeline uses no compositor - `use_nodes` appears twice in `render_lib`, once
for the world and once for a material - no geometry nodes, no keyframes and no
simulation.

Worth knowing for later: that plugin targets the **official** Blender MCP server
(Blender Lab), whose tools include `search_api_docs` and `get_python_api_docs`.
`.mcp.json` here points at `ahujasid/blender-mcp`, which is a different server.
Neither is required for the reference material to be useful, but they are not
the same thing and the names collide.

Neither the new skills nor the old ones cover the two gaps: nothing addresses
shadow catchers or light linking, which is what option 2 of the fork would need,
and nothing provides a reference-image workflow.

**The two gaps `HANDOVER-REALISM.md` named are still gaps.** Nothing in the
twenty skills covers watch finishing - anglage, perlage, cotes de Geneve - and
nothing provides a reference-image workflow for putting a photograph next to a
render. For a brief whose success criterion is "looks real", the second one is
the more expensive absence, and it is the same handicap the last session
recorded. Installing more Blender skills will not close it.

## What this machine now has

Verified, not assumed. Each line was run.

| Thing | Version | How it was checked |
|---|---|---|
| Blender | 5.2.1 LTS (2026-08-25) | `--version` |
| Cycles on GPU | OptiX, RTX 2070 | 160px/32-sample render in 4.6s |
| `render_lib` under 5.2 | imports | `world_axial` / `lights_axial` both present |
| blender-mcp addon | installed, enables | `bpy.ops.blendermcp.start_server` and `blendermcp_port` both exist |
| uv / uvx | 0.12.10 | on the persistent user PATH |
| build123d / OCP | 0.11.1 / 7.9.3.1 | import |
| trimesh, shapely, scipy, matplotlib, numpy, pillow | current | import |
| skills | 5 installed | `cad` plus four from `ra100/blender-claude-plugin`; the other 19 were removed |
| the repo's own gate | passes | `placement_invariants.py --assets` - all invariants hold |

Blender 5.2 is a version ahead of what these tools were written against.
`render_lib` imports and Cycles renders, which is real evidence but not proof:
a full pipeline render has not been run on this machine, because running it
rewrites `Assets/` and this session was not to change anything.

The addon directory did not exist until it was created -
`%APPDATA%\Blender Foundation\Blender\5.2\scripts\addons`. `uvx blender-mcp
install-addon` fails with "could not find a Blender user addons directory"
until Blender has been run once or the directory is made by hand.

## What is not done

**`skills-lock.json` no longer describes this machine and was deliberately left
alone.** It lists twenty skills; nineteen have been removed here and four
others added. All twenty were installed first and verified against it, which is
how the four upstream drifts below were found, so the check was worth doing even
though the result was thrown away. Sixteen of the twenty hash-matched exactly,
confirming the lockfile is honest and the hash is a plain sha256 of `SKILL.md`.
`cad`, `dxf`, `openscad` and `mechanical-engineer` had drifted upstream. Whoever
next touches the lock should decide whether it describes the other machine or
this one; it cannot describe both.

**The project MCP server is declared but was never connected in this session.**
`.mcp.json` names `uvx blender-mcp`, and `uvx blender-mcp --help` and
`addon-paths` both answer correctly, so the launch path works. But a
project-scoped MCP server needs approval, and this session started before any of
it existed. Expect the next session to be prompted for it.

**No render has been run end to end**, for the reason above.

**The motion complaint has not been instrumented.** `tools/motion_audit.py`
exists and was re-baselined last session; nobody has pointed it at the thing the
wall is complaining about.
