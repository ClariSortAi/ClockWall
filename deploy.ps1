# Build ClockWall and install it to where it actually runs from.
#
# Why this exists: the app you launch lives in %LOCALAPPDATA%\Programs\ClockWall, NOT in
# bin\. Editing the source and rebuilding does NOT update it, so a change can look like it
# "didn't work" when really you are still running the old binary. This script closes that gap.
#
# Why it copies the BUILD output and not `dotnet publish` output: Smart App Control is
# enforced on this machine (HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy\
# VerifiedAndReputablePolicyState = 1). A self-contained publish carries its own unsigned
# copy of the .NET / Windows App SDK runtime, and SAC blocks loading those, so the published
# app dies with FileLoadException (CodeIntegrity event 3077). The framework-dependent build
# output loads the runtime from Program Files, where it is Microsoft-signed, so it runs.
# See README "Deploying to a wall machine" before changing this.

param([switch]$NoRestart)

$ErrorActionPreference = "Stop"
$env:PATH = "C:\Program Files\dotnet;" + $env:PATH

$root = $PSScriptRoot
$src  = Join-Path $root "bin\Release\net10.0-windows10.0.19041.0\win-x64"
$dest = Join-Path $env:LOCALAPPDATA "Programs\ClockWall"

dotnet build (Join-Path $root "ClockWall.csproj") -c Release -r win-x64
if ($LASTEXITCODE -ne 0) { throw "Build failed" }

$running = @(Get-Process ClockWall -ErrorAction SilentlyContinue)
if ($running) {
    # Close politely so the window position is saved, then make sure it is gone.
    $running | ForEach-Object { $_.CloseMainWindow() | Out-Null }
    Start-Sleep -Seconds 2
    Get-Process ClockWall -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 1
}

New-Item -ItemType Directory -Force $dest | Out-Null
Get-ChildItem $src -File | Copy-Item -Destination $dest -Force
if (Test-Path (Join-Path $src "Assets")) {
    Copy-Item (Join-Path $src "Assets") $dest -Recurse -Force
}

Write-Host "Installed -> $dest\ClockWall.exe"

if (-not $NoRestart) {
    Start-Process (Join-Path $dest "ClockWall.exe") | Out-Null
    Write-Host "Relaunched (restores its saved window position)."
}
