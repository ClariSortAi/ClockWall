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

No test suite. Verify a change by building and taking a screenshot. `captures/` is
gitignored for exactly that.

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

## Layout

- `MainWindow.xaml[.cs]` — window shell only: size, presenter, keyboard, drag, CLI /
  screenshot entry, roster budget. No visual content.
- `Controls/` — `ClockPanel`, `SystemMeters`, `ActivityTicker`, `AgentListPanel`.
- `Services/` — `SessionWatcher` (finds sessions + subagents), `AgentSession` (model),
  `TranscriptTokens` (tail-follows transcripts by byte offset).
- `Themes/Theme.xaml` — the entire design system.

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
