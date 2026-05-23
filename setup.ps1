<#
.SYNOPSIS
    One-shot environment bootstrap for the 1vmo Suite.

.DESCRIPTION
    Creates the .venv virtual environment, installs everything in
    requirements.txt, and makes sure the bundled ffmpeg/ffprobe binaries are
    present. Idempotent: safe to run repeatedly. Replaces the manual
    "create venv -> activate -> pip install -> copy ffmpeg" steps.

    Both .venv/ and ffmpeg/*.exe are gitignored, so a fresh clone has neither.
    This script provisions both.

.PARAMETER Recreate
    Delete the existing .venv and build it from scratch.

.PARAMETER SkipFfmpeg
    Do not touch ffmpeg/ (use when you manage ffmpeg yourself).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>
[CmdletBinding()]
param(
    [switch]$Recreate,
    [switch]$SkipFfmpeg
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    OK  $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    !!  $msg" -ForegroundColor Yellow }

# ---------------------------------------------------------------------------
# 1. Locate a Python interpreter (3.11+ required, 3.13 is the tested target)
# ---------------------------------------------------------------------------
Write-Step "Locating Python interpreter"
$pythonCmd = $null
foreach ($candidate in @(
        @{ exe = 'py';      args = @('-3') },
        @{ exe = 'python';  args = @() },
        @{ exe = 'python3'; args = @() })) {
    $cmd = Get-Command $candidate.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        try {
            $ver = & $candidate.exe @($candidate.args + '--version') 2>&1
            if ($ver -match 'Python 3\.(\d+)') {
                if ([int]$Matches[1] -ge 11) {
                    $pythonCmd = $candidate
                    Write-Ok "$ver  ($($cmd.Source))"
                    break
                } else {
                    Write-Warn "$ver is too old (need 3.11+), skipping"
                }
            }
        } catch { }
    }
}
if (-not $pythonCmd) {
    throw "No suitable Python found (need 3.11+). Install Python 3.13 from python.org and re-run."
}

# ---------------------------------------------------------------------------
# 2. Create / recreate the virtual environment
# ---------------------------------------------------------------------------
$venv = Join-Path $root '.venv'
$venvPy = Join-Path $venv 'Scripts\python.exe'

if ($Recreate -and (Test-Path $venv)) {
    Write-Step "Removing existing .venv (-Recreate)"
    Remove-Item $venv -Recurse -Force
}

if (Test-Path $venvPy) {
    Write-Step "Reusing existing .venv"
    Write-Ok (& $venvPy --version 2>&1)
} else {
    Write-Step "Creating .venv"
    & $pythonCmd.exe @($pythonCmd.args + @('-m','venv', $venv))
    if (-not (Test-Path $venvPy)) { throw "venv creation failed: $venvPy not found." }
    Write-Ok (& $venvPy --version 2>&1)
}

# ---------------------------------------------------------------------------
# 3. Install dependencies from requirements.txt
# ---------------------------------------------------------------------------
Write-Step "Upgrading pip"
& $venvPy -m pip install --upgrade pip --quiet
Write-Ok "pip ready"

Write-Step "Installing requirements.txt"
& $venvPy -m pip install -r (Join-Path $root 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)." }
& $venvPy -m pip check
Write-Ok "dependencies installed"

# ---------------------------------------------------------------------------
# 4. Provision bundled ffmpeg / ffprobe
# ---------------------------------------------------------------------------
if ($SkipFfmpeg) {
    Write-Step "Skipping ffmpeg provisioning (-SkipFfmpeg)"
} else {
    Write-Step "Checking ffmpeg/"
    $ffDir   = Join-Path $root 'ffmpeg'
    $ffExe   = Join-Path $ffDir 'ffmpeg.exe'
    $ffProbe = Join-Path $ffDir 'ffprobe.exe'

    if ((Test-Path $ffExe) -and (Test-Path $ffProbe)) {
        Write-Ok "ffmpeg.exe and ffprobe.exe already present"
    } else {
        # Search sibling folders (../*/ffmpeg/ffmpeg.exe) for a usable bundle.
        $parent = Split-Path -Parent $root
        $source = Get-ChildItem -Path $parent -Directory -ErrorAction SilentlyContinue |
            ForEach-Object { Join-Path $_.FullName 'ffmpeg' } |
            Where-Object { (Test-Path (Join-Path $_ 'ffmpeg.exe')) -and (Test-Path (Join-Path $_ 'ffprobe.exe')) } |
            Where-Object { $_ -ne $ffDir } |
            Select-Object -First 1

        if ($source) {
            Write-Ok "Found ffmpeg bundle: $source"
            if (-not (Test-Path $ffDir)) { New-Item -ItemType Directory -Path $ffDir | Out-Null }
            # Copy exes plus any shared-build DLLs (shared ffmpeg builds need them).
            Copy-Item (Join-Path $source '*') -Destination $ffDir -Force
            Write-Ok "Copied ffmpeg binaries into ffmpeg/"
        } else {
            Write-Warn "No ffmpeg bundle found in sibling folders."
            Write-Warn "Place ffmpeg.exe + ffprobe.exe (and any DLLs) into: $ffDir"
        }
    }
}

# ---------------------------------------------------------------------------
# 5. Verify the environment can actually load the apps
# ---------------------------------------------------------------------------
Write-Step "Verifying app imports"
$env:QT_QPA_PLATFORM = 'offscreen'
# Write the check to a temp file: passing multi-line Python with quotes to a
# native exe via -c gets mangled by PowerShell argument quoting.
$checkPy = Join-Path $env:TEMP "_1vmo_setup_check.py"
@'
import importlib, sys
mods = ['auto_render','cutter','merge','mixer','updater','settings_dialog','gpu_detect']
bad = []
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:
        bad.append('{0}: {1}'.format(m, e))
if bad:
    print('IMPORT FAILURES:')
    print(chr(10).join(bad))
    sys.exit(1)
print('all {0} app modules import cleanly'.format(len(mods)))
'@ | Set-Content -Path $checkPy -Encoding utf8
try {
    # PYTHONPATH = repo root so the apps import even though the check script
    # lives in TEMP (Python puts the script's own dir on sys.path, not cwd).
    $env:PYTHONPATH = $root
    & $venvPy $checkPy
    $checkExit = $LASTEXITCODE
} finally {
    Remove-Item $checkPy -ErrorAction SilentlyContinue
    $env:PYTHONPATH = $null
}
if ($checkExit -ne 0) { throw "App import verification failed." }
Write-Ok "apps import cleanly"

# ffmpeg sanity (non-fatal)
$ffExe = Join-Path $root 'ffmpeg\ffmpeg.exe'
if (Test-Path $ffExe) {
    $ffver = (& $ffExe -version 2>&1 | Select-Object -First 1)
    Write-Ok "ffmpeg: $ffver"
}

Write-Host "`n==> Setup complete. Run an app with:" -ForegroundColor Cyan
Write-Host "    .\.venv\Scripts\python.exe auto_render.py" -ForegroundColor White
