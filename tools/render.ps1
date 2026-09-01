<#
    Regenerates every rendered asset, once, in the right order.

        .\tools\render.ps1
        .\tools\render.ps1 -SkipAudit

    WHY THIS EXISTS. The pipeline is five steps that must run in sequence and
    all write to Assets\. Running them by hand worked until two renders were
    started close together: both wrote the same files, they interleaved, and
    what landed on disk was half of one render and half of another. Nothing
    errored. The assets looked fine, the audit measured a scene that had never
    existed, and it all got committed.

    So this takes a lock, refuses to start if another render holds it, and runs
    the steps in order. It also GATES on clash_check - there is no point
    spending eight minutes rendering an assembly whose parts pass through each
    other, and a failing check should stop the pipeline rather than annotate it.
#>

param([switch]$SkipAudit)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$lock = Join-Path $root "captures\.render.lock"
New-Item -ItemType Directory -Force -Path (Split-Path $lock) | Out-Null

if (Test-Path $lock) {
    $held = Get-Content $lock -Raw
    if (Get-Process -Id ([int]($held -split '\s+')[0]) -ErrorAction SilentlyContinue) {
        throw "A render is already running (pid $held). Wait for it, or stop it first."
    }
    Write-Host "Clearing a stale lock from pid $held"
    Remove-Item $lock -Force
}
"$PID $(Get-Date -Format o)" | Set-Content $lock

try {
    $blender = Get-ChildItem "C:\Program Files\Blender Foundation" -Recurse -Filter blender.exe `
        -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $blender) { throw "Blender not found under C:\Program Files\Blender Foundation" }

    $env:PYTHONPATH = "tools"

    Write-Host "`n[1/5] profiles" -ForegroundColor Cyan
    python tools/export_profiles.py

    # The gate. Two solids in the same place is not something to render around.
    Write-Host "`n[2/5] clash check" -ForegroundColor Cyan
    python tools/clash_check.py
    if ($LASTEXITCODE -ne 0) { throw "Parts are interpenetrating - fix the geometry before rendering." }

    Write-Host "`n[3/5] blender" -ForegroundColor Cyan
    & $blender.FullName --background --python tools/blender_face.py 2>&1 |
        Select-String -Pattern "audit|Error|Traceback|SceneError" | ForEach-Object { $_.Line }
    if ($LASTEXITCODE -ne 0) { throw "Blender exited $LASTEXITCODE" }

    Write-Host "`n[4/5] smears" -ForegroundColor Cyan
    python tools/smear.py

    # Everything must be newer than the profiles that produced it. This is what
    # actually catches a half-finished or interleaved render, as opposed to
    # trusting that the steps above ran to completion.
    $stamp = (Get-Item "captures\geom\profiles.json").LastWriteTime
    $stale = Get-ChildItem "Assets\*.png" | Where-Object { $_.LastWriteTime -lt $stamp }
    if ($stale) {
        throw "Stale assets, so this render is not self-consistent: $($stale.Name -join ', ')"
    }
    Write-Host "  all $((Get-ChildItem 'Assets\*.png').Count) assets newer than the profiles they came from"

    if (-not $SkipAudit) {
        Write-Host "`n[5/5] motion audit" -ForegroundColor Cyan
        python tools/motion_audit.py
    }
    Write-Host "`nrender complete" -ForegroundColor Green
}
finally {
    Remove-Item $lock -Force -ErrorAction SilentlyContinue
}
