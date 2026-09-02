<#
    Regenerates every rendered asset, once, in the right order.

        .\tools\render.ps1
        .\tools\render.ps1 -SkipAudit

    WHY THIS EXISTS. The pipeline is a sequence of steps that all write to
    Assets\, in an order that matters. Running them by hand worked until two
    renders were started close together: both wrote the same files, they
    interleaved, and what landed on disk was half of one render and half of
    another. Nothing errored. The assets looked fine, the audit measured a
    scene that had never existed, and it all got committed.

    So this takes a lock, refuses to start if another render holds it, and runs
    the steps in order. It also GATES twice - on clash_check before the render,
    because there is no point spending eight minutes on an assembly whose parts
    pass through each other, and on placement_invariants --assets after it,
    because a render that bakes a cast shadow into a wheel the app spins is a
    render nobody can see is wrong. A failing check stops the pipeline rather
    than annotating it.
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

    Write-Host "`n[1/6] profiles" -ForegroundColor Cyan
    python tools/export_profiles.py

    # The gate. Two solids in the same place is not something to render around.
    Write-Host "`n[2/6] clash check" -ForegroundColor Cyan
    python tools/clash_check.py
    if ($LASTEXITCODE -ne 0) { throw "Parts are interpenetrating - fix the geometry before rendering." }

    Write-Host "`n[3/6] blender" -ForegroundColor Cyan
    & $blender.FullName --background --python tools/blender_face.py 2>&1 |
        Select-String -Pattern "audit|Error|Traceback|SceneError" | ForEach-Object { $_.Line }
    if ($LASTEXITCODE -ne 0) { throw "Blender exited $LASTEXITCODE" }

    Write-Host "`n[4/6] smears" -ForegroundColor Cyan
    python tools/smear.py

    # Every RENDERED asset must be newer than the profiles that produced it.
    # This is what actually catches a half-finished or interleaved render, as
    # opposed to trusting that the steps above ran to completion.
    #
    # dial-texture.png is excluded because it is an INPUT, not an output: PIL
    # draws the soleil albedo and Blender maps it onto the dial. Requiring it to
    # be newer than the profiles failed a render that was in fact perfectly
    # consistent, which is the classic way a good check gets switched off.
    $inputs = @("dial-texture.png")
    $stamp = (Get-Item "captures\geom\profiles.json").LastWriteTime
    $stale = Get-ChildItem "Assets\*.png" |
        Where-Object { $inputs -notcontains $_.Name -and $_.LastWriteTime -lt $stamp }
    if ($stale) {
        throw "Stale assets, so this render is not self-consistent: $($stale.Name -join ', ')"
    }
    Write-Host "  all $((Get-ChildItem 'Assets\*.png' | Where-Object { $inputs -notcontains $_.Name }).Count) rendered assets are newer than the profiles they came from"

    # The second gate, and unlike clash_check it runs AFTER the render because
    # it reads what the render produced. It asks whether the layers the app
    # ROTATES can survive being rotated - a cast shadow baked into a wheel's
    # own sprite orbits that wheel on the wall and is invisible in every still
    # frame, which is how it survived three sessions of looking at screenshots.
    # It is a few seconds of PNG arithmetic with no CAD imports, so it can
    # afford to run every time, which interfere_check cannot.
    Write-Host "`n[5/6] baked directionality" -ForegroundColor Cyan
    python tools/placement_invariants.py --assets
    if ($LASTEXITCODE -ne 0) { throw "Shading is baked into layers the app moves - see the failures above." }

    if (-not $SkipAudit) {
        Write-Host "`n[6/6] motion audit" -ForegroundColor Cyan
        python tools/motion_audit.py
    }
    Write-Host "`nrender complete" -ForegroundColor Green
}
finally {
    Remove-Item $lock -Force -ErrorAction SilentlyContinue
}
