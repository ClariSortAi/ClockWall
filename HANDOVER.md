# Handover: the mechanical watch face

Written 2026-09-01 for whoever picks this up next. The session that produced it
ended so that Claude Code would reload `.mcp.json` and get the Blender MCP tools.

## Why the session ended

`.mcp.json` registers a Blender MCP server (`uvx blender-mcp`). It was added
mid-session, and Claude Code only reads that file at startup. Everything else
described here works without it, because `tools/blender_rpc.py` speaks to the
same socket the MCP server uses.

## Start here

Nothing is half-finished. The tree is clean, every check passes, and the app is
deployed and running. Two processes were left up and will not survive a reboot:

    # Blender, with the MCP addon enabled and port 9876 open
    & "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe" --python tools\blender_live.py

    # the wall clock itself
    .\deploy.ps1

Confirm the socket is answering before relying on it:

    python tools/blender_rpc.py "import bpy; print(bpy.app.version_string)"

## The task in progress

The current job is geometry realism, and the approach changed near the end of
the session. Read that as the main thread.

Every part of the movement is a 2D outline from `escapement_geometry.py`,
extruded to a constant thickness and given one blanket bevel in Blender. That is
correct for the parts that really are stamped sheet, meaning the escape wheel
and the pallet lever. It is wrong for the parts that are turned on a lathe. A
balance wheel's rim is taller than its arm and chamfered on all four edges,
its hub stands proud of both, and its timing screws thread radially into the rim
rather than sitting on top of it. That is four heights and four chamfers in one
component. An extruded outline can express one of each.

Under a straight-down orthographic camera those chamfers are most of what there
is to see, because they are the only surfaces angled toward a light.

So the turned parts move to CadQuery, which is OpenCASCADE driven from Python.
`tools/cad_parts.py` does the balance wheel this way already, as a proof that
the whole path works: revolve a cross-section, chamfer named edges, export STL,
import into Blender. Run it with the CAD virtualenv, not the system Python:

    .\.venv-cad\Scripts\python.exe tools\cad_parts.py

### What is left to convert

- Jewels: olive-drilled bore (a revolved curve, not a cylinder) set in chatons.
- Screws: domed heads with real slots. Currently flat discs.
- Pinion leaves: rounded tips instead of a flat extruded profile.
- The cock: a stepped boss over the balance staff, and polished anglage along
  its curved edge rather than a uniform bevel.
- Countersunk jewel settings in the mainplate.

The escape wheel and lever stay as 2D profiles, but their chamfers should move
from the blanket Blender modifier to real edge selections.

### The wiring that does not exist yet

`render_lib.build_part()` extrudes a part's 2D rings. It needs a branch that
imports an STL when a part has one. Until that exists, `cad_parts.py` output is
only reachable through `blender_rpc.py`, not through the shipping render.

## Running the pipeline

One command regenerates every asset:

    .\tools\render.ps1

It takes a lock, refuses to start if another render holds it, gates on
`clash_check.py`, and fails if any rendered asset ends up older than the
profiles it came from. Use it. Do not run the steps by hand.

That guard exists because it was needed. Two renders were once started close
together, both wrote `Assets\`, they interleaved, and what landed on disk was
half of one render and half of another. Nothing errored. The motion audit then
measured a scene that had never existed, and the result was committed.

## The tools, and what each is for

`clash_check.py` tests every pair of parts for overlap in plan and in z at the
same time. Plan overlap alone is fine and expected, since a watch is a stack.
Overlapping in z as well means one part passes through another. It exits
non-zero, so `render.ps1` gates on it.

`motion_audit.py` renders the aperture at wall scale, samples it at 60fps, and
reduces the motion to numbers: luminance modulation, mean frame-to-frame change,
and the worst single frame. `--ablate` freezes one part at a time, which is how
to find which part is responsible instead of guessing. This tool is the reason
several things got fixed, and it disproved at least one confident theory.

`beat_strip.py` draws stills of the escapement across a beat, with `--zoom` for
the escape wheel and `--sub` for inside the seven millisecond transit that no
real frame ever lands on. It deliberately draws the stepping parts sharp,
because the question it answers is whether a pallet stone meets a tooth.
`motion_audit.py` is the one that models what actually ships.

`smear.py` builds the motion-blur companion for each fast part. Every span is
derived, not chosen. Read its header before changing one.

`blender_rpc.py` executes Python inside the live Blender and returns whatever it
printed. Use it to look at a part from an angle. Straight-down orthographic
hides exactly the errors that matter in a turned part: the first tilted look at
the CAD balance showed its timing screws cutting scalloped notches through the
rim, which had been invisible from above.

## Where the numbers stand

Measured by `motion_audit.py` at wall scale, aperture only:

| stage | motion | worst frame |
|---|---|---|
| start of session | 10.08 | |
| balance smear fixed | 3.57 | 11.27 |
| escapement contrast and shutter | 2.28 | 7.30 |
| margin, roller, clean re-render | 2.05 | 6.86 |

Flicker is 0.4 percent. Lower is calmer, except that zero motion is a stopped
watch.

## Traps

The app you launch is not the app you built. It runs from
`%LOCALAPPDATA%\Programs\ClockWall`, and `dotnet build` does not update it. Run
`deploy.ps1`.

Never `dotnet publish` self-contained. Smart App Control blocks the unsigned
runtime it bundles.

The rotation pivots in `Controls/OpenworkedFace.xaml` are a hand-copied
transcript of `captures/geom/profiles.json`. Move a part in the geometry and
they must be re-copied, or every wheel turns about a point it no longer sits on
and the face still looks plausible. `export_profiles.py` prints them in the form
XAML wants.

`Assets/dial-texture.png` is an input, not an output. `dial_render.py` draws it
and Blender maps it onto the dial, so it is legitimately older than the profiles.

CadQuery segfaults on interpreter teardown on this machine. The work completes
first, so scripts end with `sys.stdout.flush()` then `os._exit(0)`. Without the
flush you get an exit code of zero and no output at all.

`uvx blender-mcp install-addon` crashes printing a Unicode arrow to a cp1252
console. Set `PYTHONIOENCODING=utf-8` first.

Which face the wall shows is stored in
`%LOCALAPPDATA%\ClockWall\clock-mode.txt`. The value for this one is
`mechanical`. Screenshots pick up whatever is saved there, so a screenshot
showing the digital face usually means somebody pressed C.

## The blender-skills package

`skills-lock.json` records 16 skills from `kevinbadi/blender-skills`, installed
under `.agents/skills/`. None of them runs against this pipeline: every one is a
Node client that drives a live Blender GUI over a socket, and they assume
Blender 5.x with MCP. They are worth reading anyway. Their default studio HDRI
is `studio_small_09`, which is the one already vendored in `tools/hdri/`, and
`polyhaven-material-swap` encodes a loop this project still lacks, which is
rendering several variants in one Blender session and tiling them for
comparison. At the moment a single material question costs a full eight minute
render.

## Session history

Twelve commits, `5324d79` through `caf8e36`. The ones worth reading before
touching the escapement:

- `cb19e6e` fixed five faults that made the escapement mechanically impossible,
  including a fork whose slot had no impulse pin to receive, arbors that were 22
  degrees off the line of centres, and a hairspring anchored to nothing.
- `0ed6e9c` found that the balance was producing 84 percent of all frame-to-frame
  change in the aperture, and cut it to nothing.
- `caf8e36` re-rendered the assets after the overlapping-render corruption and
  corrected the numbers that had been reported from it.
