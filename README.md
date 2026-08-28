# ClockWall

An always-on wall/kiosk dashboard for a 1080x1920 portrait display: a very large digital
clock, the date under it, and a live list of the Claude Code agent sessions currently
running on the machine.

![ClockWall on a 1080x1920 portrait panel](docs/preview.png)

The screenshot above is produced by the app itself (`--screenshot`, see below), so it is a
real 1:1 capture of the composed window rather than a mockup.

## Stack

| | |
|---|---|
| UI | WinUI 3 (Windows App SDK 1.x), XAML |
| Runtime | .NET 10 (`net10.0-windows10.0.19041.0`), x64 |
| Packaging | **Unpackaged** (`WindowsPackageType=None`) - a plain `.exe`, no MSIX, no store identity |
| Tooling | `dotnet` CLI only; no Visual Studio required |

WinUI 3 was chosen because the design system this project follows
(see Credits) targets WinUI 3 directly: the type ramp, the theme dictionaries
(Light / Dark / HighContrast) and the surface brushes in `Themes/Theme.xaml` are all
expressed as real XAML resources, and the layout is real XAML - not a hand-built visual
tree. Unpackaged keeps deployment to "copy a folder and run it", which is what a wall
machine wants.

`app.manifest` declares per-monitor-v2 DPI awareness. Every number in the design system is
in **physical pixels**: the window's *client* area is sized to exactly 1080x1920 physical
pixels, and a `Viewbox` maps the fixed 1080x1920 design canvas onto it (at 125% scaling
that client area is only 864x1536 DIPs, so the canvas is scaled by 96/dpi). Text stays
crisp because that is a coordinate transform, not a bitmap stretch.

## Build and run

```powershell
# dotnet 10 SDK; if it is not on PATH:
$env:PATH = "C:\Program Files\dotnet;" + $env:PATH

dotnet build ClockWall.csproj -c Release -r win-x64
.\bin\Release\net10.0-windows10.0.19041.0\win-x64\ClockWall.exe
```

The window is chrome-less (no border, no title bar, no caption buttons) and holds a
display request (`ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED`) for as long as the process
lives, so the panel never sleeps or blanks.

### CLI flags

| Flag | Effect |
|---|---|
| `--fullscreen` | Start in the full-screen presenter. The design canvas is 9:16, so it fills a 1440x2560 or 1350x2400 portrait panel edge to edge. |
| `--screenshot PATH` | Move the window to 0,0, let the clock tick and the first session scan land, capture the 1080x1920 client region, write it as a PNG to `PATH`, and exit. A watchdog guarantees the process terminates. |

Unrecognised arguments are ignored so a stray flag can never stop the wall from starting.

### Keyboard

| Key | Effect |
|---|---|
| `Esc` | Quit |
| `F11` | Toggle full screen |

## Agent discovery and liveness

`Services/SessionWatcher.cs` watches `%USERPROFILE%\.claude\sessions\` - resolved at
runtime from the user profile, never hardcoded. Each running Claude Code session writes one
`<pid>.json` there; the directory also contains `*.key` files, which are ignored.

Fields read: `pid`, `sessionId`, `cwd`, `startedAt`, `version`, `kind`, `entrypoint`,
`name`, `status`, `updatedAt`, `statusUpdatedAt`. Parsing is `System.Text.Json`.

**A session file is not proof of a running session.** A `.json` can outlive the process
that wrote it, and pids get reused. A session is shown only if:

1. `Process.GetProcessById(pid)` succeeds and the process has not exited, **and**
2. the process's real start time is within **2 minutes** of the file's `startedAt`.

Any exception from either step is treated as "not running". If `startedAt` is absent or
zero, that is treated as *no timestamp* (not as 1970) and step 2 is skipped - liveness of
the pid alone decides - so a session whose file has not yet written that field is still
shown rather than silently dropped.

Update cadence:

* a `FileSystemWatcher` on the directory, debounced 300 ms;
* a 5 s poll as a safety net (self-heals a dropped watcher, a deleted directory, or a file
  caught mid-write);
* a 1 s UI-only tick that re-raises `PropertyChanged` for the uptime counters - no disk and
  no process-table access.

A missing directory, a locked or half-written file, or a watcher failure is tolerated: the
panel keeps running and picks the data up on the next cycle. The roster is sorted
busy-first, then most-recently-active. At most five cards are shown; any remainder is
announced honestly in the footer ("2 MORE AGENTS") rather than being clipped.

## Deploying to a wall machine

### Publish

```powershell
dotnet publish ClockWall.csproj -c Release -r win-x64 `
  --self-contained true `
  -p:PublishSingleFile=true `
  -p:WindowsAppSDKSelfContained=true `
  -p:EnableMsixTooling=true
```

Produces a single `bin\Release\net10.0-windows10.0.19041.0\win-x64\publish\ClockWall.exe`
(~218 MB - it carries the .NET runtime *and* the Windows App SDK runtime inside it). Copy
that one file to the wall machine. `EnableMsixTooling=true` is required by the Windows App
SDK's own single-file target (it generates the embedded `resources.pri`), not because
anything is packaged as MSIX - the app stays unpackaged.

If you prefer a folder to a self-extracting exe (faster cold start, no per-launch
extraction into `%TEMP%\.net`), drop `-p:PublishSingleFile=true`. That yields a ~215 MB
directory that is copied whole and is otherwise equivalent.

### What the target machine needs

* Windows 10 1809 (17763) or later, x64.
* **Nothing else.** With `--self-contained true -p:WindowsAppSDKSelfContained=true` both
  the .NET 10 runtime and the Windows App Runtime travel with the app; no runtime installer
  is needed.
* **Code signing, if the machine enforces application control.** The publish output is
  unsigned. This development machine has Smart App Control enabled
  (`HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy\VerifiedAndReputablePolicyState = 1`),
  which blocks the loading of *any* copied unsigned managed assembly - the published build
  fails there with `FileLoadException ... An Application Control policy has blocked this
  file. (0x800711C7)` and CodeIntegrity event 3077, single-file and folder alike. The
  in-place development build (`bin\Release\...\ClockWall.exe`) is unaffected and is what
  renders `docs/preview.png`. Sign the output, or run the wall machine without Smart App
  Control, before relying on the published artifact. Because of that policy, the published
  artifact could not be launch-verified on this machine.

### Autostart

Per-user, no admin rights, survives sign-in:

```powershell
$exe = "C:\ClockWall\ClockWall.exe"          # wherever you copied it
$startup = [Environment]::GetFolderPath('Startup')
$s = (New-Object -ComObject WScript.Shell).CreateShortcut("$startup\ClockWall.lnk")
$s.TargetPath = $exe
$s.Arguments  = "--fullscreen"
$s.Save()
```

For a true kiosk, also: set the panel as the primary display in portrait orientation, and
set Power & battery -> Screen and sleep -> "Never" for both screen and sleep (the app's
display request covers the screen, but a machine-level sleep policy still wins).

To run it without a signed-in interactive session, use Task Scheduler with trigger
"At log on", action `ClockWall.exe --fullscreen`, and "Run only when user is logged on".

## Layout notes

The vertical composition is deliberate and worth knowing before editing `MainWindow.xaml`:

* The **hero row is the elastic one** (`Height="*"`, `VerticalAlignment="Center"`). The
  roster is content-sized and bounded at five cards, so it can never fill a reserved
  remainder at a realistic agent count - giving it the slack just parks a third of the
  panel of dead background under the last card. The hero takes the slack instead and the
  list sits on the bottom inset at any agent count.
* **No system backdrop.** Mica/Acrylic only paint their material while the window is
  active; the moment it loses focus - a kiosk's permanent state - the controller falls back
  to a solid `#202020`, which is *lighter* than the `#1B1B22` agent cards and inverts the
  card elevation the dark palette is built on. `WallRoot` keeps the opaque, activation-
  independent `WallBackgroundBrush` (`#0E0E12`), which is also what lets the HighContrast
  theme dictionary reach the window.
* Seconds and the AM/PM designator live in **one** `TextBlock` as two `Run`s, so they share
  a line box and therefore a baseline. Side-by-side `TextBlock`s of different sizes are
  top-aligned, which makes the smaller meridiem read as a superscript.
* The clock is jitter-free by construction: fixed character counts (zero-padded hours) plus
  `Typography.NumeralAlignment="Tabular"`, so the centred line's measured width never
  changes from tick to tick.

## Credits

Design system and WinUI 3 layout guidance from the Windows dev skills at
<https://github.com/microsoft/win-dev-skills> (see `docs/design-reference/`).
