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
        # Search sibling folders (../*/ffmpeg/) for a CAPABILITY-qualified bundle.
        # Selection is by capability, never by name/mtime: a build must expose
        # libvmaf (HARD - the VMAF scoring axis needs it) and preferably an NVENC
        # encoder (SOFT - GPU renders fall back to CPU per ADR-0007 D5 if absent).
        $parent = Split-Path -Parent $root

        # Candidate sibling ffmpeg dirs that physically have both exes, sorted
        # alphabetically by path so the tiebreak among equally-qualified builds
        # is deterministic and stable (NOT dependent on filesystem enumeration
        # order). The first qualifying build in this order wins.
        $candidates = @(
            Get-ChildItem -Path $parent -Directory -ErrorAction SilentlyContinue |
                ForEach-Object { Join-Path $_.FullName 'ffmpeg' } |
                Where-Object { (Test-Path (Join-Path $_ 'ffmpeg.exe')) -and (Test-Path (Join-Path $_ 'ffprobe.exe')) } |
                Where-Object { $_ -ne $ffDir } |
                Sort-Object
        )

        $source   = $null   # first build with libvmaf + nvenc (full capability)
        $fallback = $null   # first build with libvmaf but no nvenc
        foreach ($cand in $candidates) {
            $candExe = Join-Path $cand 'ffmpeg.exe'
            try {
                $filters  = & $candExe -hide_banner -filters  2>$null | Out-String
                $encoders = & $candExe -hide_banner -encoders 2>$null | Out-String
            } catch {
                Write-Warn "Candidate ffmpeg failed to run (missing DLLs?), skipping: $cand"
                continue
            }
            # Match the libvmaf FILTER line specifically (flags column + name
            # column), not an incidental substring in another filter's text.
            if ($filters -notmatch '(?m)^\s*\S+\s+libvmaf\b') {
                Write-Warn "Rejecting $cand : missing libvmaf (required for VMAF scoring)"
                continue
            }
            # NVENC is preferred but soft: match an encoder whose name column ends
            # in _nvenc (h264_nvenc / hevc_nvenc / av1_nvenc).
            if ($encoders -match '(?m)^\s*\S+\s+\w+_nvenc\b') {
                $source = $cand   # full capability - take it, stop searching
                break
            }
            if (-not $fallback) { $fallback = $cand }   # remember first libvmaf-only
        }
        if (-not $source -and $fallback) {
            $source = $fallback
            Write-Warn "Using libvmaf-only ffmpeg (no NVENC): $source - GPU renders fall back to CPU (ADR-0007 D5)"
        }

        if ($source) {
            Write-Ok "Selected ffmpeg by capability: $source"
            if (-not (Test-Path $ffDir)) { New-Item -ItemType Directory -Path $ffDir | Out-Null }
            # Copy exes plus any shared-build DLLs (shared ffmpeg builds need them).
            Copy-Item (Join-Path $source '*') -Destination $ffDir -Force
            Write-Ok "Copied ffmpeg binaries into ffmpeg/"
        } else {
            Write-Warn "No ffmpeg bundle with libvmaf found in sibling folders."
            Write-Warn "Place a libvmaf-capable ffmpeg.exe + ffprobe.exe (and any DLLs) into: $ffDir"
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
