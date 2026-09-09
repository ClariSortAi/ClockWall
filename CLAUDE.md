# ClockWall

WinUI 3 (Windows App SDK) on .NET 10, unpackaged, C# + XAML. A 1080x1920 portrait wall
display showing a clock, machine meters, and the Claude Code sessions running on this
machine. README.md explains how the data is sourced and why; this file is the
operational layer.

## Commands

    dotnet build ClockWall.csproj -c Release -r win-x64
    .\bin\Release\net10.0-windows10.0.19041.0\win-x64\ClockWall.exe

    .\deploy.ps1              # build + install to %LOCALAPPDATA%\Programs\ClockWall + relaunch
    .\deploy.ps1 -NoRestart

    ClockWall.exe --screenshot out.png   # renders a 1080x1920 PNG and exits
    ClockWall.exe --fullscreen           # Esc exits, F11 toggles

    python tools/om10_extract_all.py     # once: all 166 OM10 solids -> captures/om10/all (needs the STEP, see below)
    python tools/gltf_export.py          # regenerates Assets/movement.glb + movement-parts.json (OCP + build123d)
    python tools/case_solids.py          # regenerates Assets/case.glb + models/step/case.step (build123d)
    python tools/hairspring.py           # designs the hairspring -> Assets/mechanism.json (run before gltf_export)
    python tools/mainspring.py           # measures the OM10's mainspring and barrel -> Assets/mechanism.json
    python tools/assembly_check.py --quick   # exact interference check, our solids against the OM10's (~15 min)
    python tools/print_export.py         # the print set: one STL per part at print scale, bores opened -> captures/print/
    python tools/dial_print.py           # regenerates Assets/dial-print.png
    python tools/crystal_wear.py         # regenerates Assets/crystal-wear.png (the scratch and the dust)

    .\deploy.ps1 -NoRestart -Dest "$env:LOCALAPPDATA\Programs\ClockWall-dev"   # a dev install that leaves the wall's copy running

No test suite. Verify a change by building and taking a screenshot. `captures/` is
gitignored for exactly that. For the live face, judge the full 1080x1920 screenshot
at wall distance, not a crop: `ART-DIRECTION.md` is the brief and the wall is the
acceptance test.

## Traps

- **The app you launch is not the app you built.** It runs from
  `%LOCALAPPDATA%\Programs\ClockWall`; `dotnet build` does not update it. If a change
  seems to have no effect, you are looking at the old binary — run `deploy.ps1`.
- **Never `dotnet publish` self-contained.** Smart App Control is enforced here and
  blocks the unsigned runtime a self-contained publish bundles (`FileLoadException`
  0x800711C7, CodeIntegrity event 3077). `deploy.ps1` copies the framework-dependent
  *build* output for that reason. A freshly built `ClockWall.dll` can be blocked too,
  intermittently — that is SAC being reputation-based, not a build error.
- `dotnet` may not be on PATH in a plain PowerShell session; `deploy.ps1` prepends
  `C:\Program Files\dotnet`.
- **The live face shows an empty square and nothing else.** Release strips
  `Debug.WriteLine`. Read `%LOCALAPPDATA%\ClockWall\render-log.txt` — the renderer
  writes every scene-build fault there with a stack. A shader that fails to compile
  or a missing asset lands there, not on screen.
- **The XAML compositor ignores the swap chain's alpha** (measured: a strip forced to
  alpha 0 stayed black). The live face composites itself over the wall colour it reads
  from `WallBackgroundBrush`; do not spend time on premultiplied alpha.
- **The OM10 STEP is the source of truth and it exists.** It is at
  `captures/om10/om10-00001_20220701_va_01_3.stp` (gitignored; the owner's copy is in
  OneDrive `3dstuff`, with `OM10_Release_notes.pdf`, which names the parts in
  French). Before inferring any part's role from radii and distances, open the file.
  The hands' arbor, the stem direction and the seconds wheel were all inferred once
  and all three inferences were wrong.
- **Do not reason about the environment's orientation; look.** Run with
  `CLOCKWALL_DEBUG_VIEW=1` and every surface renders as a mirror of the studio by its
  normal. The dial then shows what world +Y is aimed at. Two sessions of arithmetic
  were wrong before this existed.

## Layout

- `MainWindow.xaml[.cs]` — window shell only: size, presenter, keyboard, drag, CLI /
  screenshot entry, roster budget. No visual content.
- `Controls/` — `ClockPanel`, `SystemMeters`, `ActivityTicker`, `AgentListPanel`,
  `OpenworkedFace` (the sprite face), `MovementView` (the live face's panel).
- `Services/` — `SessionWatcher` (finds sessions + subagents), `AgentSession` (model),
  `TranscriptTokens` (tail-follows transcripts by byte offset), `Caliber` (the
  movement's specification and its kinematic form: every angle from one beat count
  read off the wall clock), `Mechanism` (the running watch: an integrated balance,
  an event-based escapement, a mainspring; the beat count is its own, the wall
  clock only sets it. The live face uses this; the sprite face still uses Caliber).
- `Rendering/` — the live face. `WatchDesign` is the FACE (palette, materials,
  movement placement, light rig); `WatchScene` is the ENGINE (passes, arbors,
  transforms) and builds no geometry; `WatchRenderer` the device and swap chain;
  `Environment` the HDRI bake; `Shaders/*.hlsl` embedded and compiled at start-up.
  Shapes come from two GLBs: `Assets/movement.glb` (the OM10, `tools/gltf_export.py`)
  and `Assets/case.glb` (everything else as watertight solids, `tools/case_solids.py`,
  which also writes `models/step/case.step`). `FACE-RECIPE.md` is the repeatable
  process for producing a new face.
- **Direction of travel.** This is meant to become an object that could be made and
  whose time comes from its own mechanism, not the system clock. Every part is a
  solid; the hands sit on the OM10's own arbors; the live face's time comes from
  `Services/Mechanism.cs`, which keeps its own rate (measured at start-up and written
  to the fault log, with hourly drift). Do not add geometry that is not a solid, or
  motion that could not come from the train, or a number the solids could have given.
- `Themes/Theme.xaml` — the entire design system.
- `tools/` — the Python pipeline: CAD extraction, the glTF exporter, the dial print
  mask, and the retired Blender sprite renders.

## Conventions

- **One SessionWatcher.** `AgentListPanel` constructs and owns it; anything else needing
  the roster reads `AgentList.Sessions`. A second watcher means duplicate
  FileSystemWatchers and timers over the same directory.
- **No colours, fonts or sizes outside `Themes/Theme.xaml`.** Resources are named by
  purpose, never by hue. Brushes via `{ThemeResource}`, metrics via `{StaticResource}`.
  Light / Dark / HighContrast are each defined explicitly — never "Default".
- **Comments say why, and are expected to be dense.** A `// ponytail:` comment marks a
  deliberately minimal choice, its cost, and its upgrade path. Keep the marker if you
  revisit one.
- It runs unattended for days: a missing, locked or mid-write file must self-heal via the
  periodic poll rather than throw.
- Numeric readouts pad with figure spaces (U+2007) plus tabular figures so values keep a
  constant rendered width as they change.
