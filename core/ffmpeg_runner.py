"""Shared FFmpeg subprocess utilities for 1vmo Suite apps.

Phase 5a (this commit): binary resolution, Windows hide-window helpers,
unified Popen kwargs, and ffprobe wrappers. Phase 5b (next commit) will
add run_ffmpeg() — the actual subprocess lifecycle + progress parsing.

The four apps (auto_render, cutter, merge, mixer) and bench.py + gpu_detect.py
all use the same bundled FFmpeg binary location pattern; this module
consolidates that. bench.py keeps its own Popen for v1 — only ffprobe
helpers migrate from it.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


# ========== Binary resolution ==========

def resolve_binaries(script_dir: Path) -> tuple[Path, Path]:
    """Return (ffmpeg_path, ffprobe_path) from the bundled ffmpeg/ subdirectory.

    Picks .exe suffix on Windows, no suffix elsewhere. Identical pattern to
    the literal form previously duplicated across all four apps + gpu_detect.
    """
    suffix = '.exe' if os.name == 'nt' else ''
    ffmpeg = script_dir / 'ffmpeg' / f'ffmpeg{suffix}'
    ffprobe = script_dir / 'ffmpeg' / f'ffprobe{suffix}'
    return ffmpeg, ffprobe


# ========== Windows hide-window helpers ==========

def hidden_startupinfo() -> Any:
    """Return a STARTUPINFO that hides the FFmpeg console window on Windows.

    Returns None on non-Windows platforms. Used as the startupinfo= kwarg
    to subprocess.Popen / subprocess.run.
    """
    if os.name != 'nt':
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return si


def hidden_creationflags() -> int:
    """Return CREATE_NO_WINDOW on Windows, 0 elsewhere.

    Used as the creationflags= kwarg to subprocess.Popen / subprocess.run.
    Critical for PyInstaller --noconsole builds; without it, every FFmpeg
    invocation flashes a CMD window.
    """
    if os.name != 'nt':
        return 0
    return subprocess.CREATE_NO_WINDOW


# ========== Unified Popen kwargs (Phase 5b foundation) ==========

def ffmpeg_popen_kwargs() -> dict[str, Any]:
    """Return uniform Popen kwargs for FFmpeg/ffprobe invocations.

    Includes:
    - text=True, encoding='utf-8', errors='replace': UTF-8 decode of FFmpeg
      output. Replaces Python's default cp1252 decode on Western Windows
      that crashes on non-ASCII filenames in stderr.
    - bufsize=1: line-buffered, so progress lines flush promptly.
    - stdin=PIPE: required for graceful 'q' cancellation in Phase 5b runner.
    - startupinfo + creationflags: hide console window in PyInstaller builds.

    Callers add stdout=PIPE/STDOUT/DEVNULL and stderr=PIPE/STDOUT/DEVNULL
    as needed for their use case (run_ffmpeg uses different stream wiring
    per dialect).
    """
    return {
        'text': True,
        'encoding': 'utf-8',
        'errors': 'replace',
        'bufsize': 1,
        'stdin': subprocess.PIPE,
        'startupinfo': hidden_startupinfo(),
        'creationflags': hidden_creationflags(),
    }


# ========== ffprobe helpers ==========

def probe_duration(ffprobe: Path, video: Path) -> float:
    """Return video duration in seconds via ffprobe. Returns 0.0 on probe failure.

    Uses 'show entries format=duration' for compatibility across container types.
    """
    try:
        result = subprocess.run(
            [str(ffprobe), '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(video)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            startupinfo=hidden_startupinfo(),
            creationflags=hidden_creationflags(),
            timeout=30,
        )
        return float(result.stdout.strip())
    except (subprocess.SubprocessError, ValueError, OSError):
        return 0.0


def probe_resolution(ffprobe: Path, video: Path) -> tuple[int, int]:
    """Return (width, height) via ffprobe. Returns (0, 0) on probe failure."""
    try:
        result = subprocess.run(
            [str(ffprobe), '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height',
             '-of', 'csv=s=x:p=0', str(video)],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            startupinfo=hidden_startupinfo(),
            creationflags=hidden_creationflags(),
            timeout=30,
        )
        parts = result.stdout.strip().split('x')
        return (int(parts[0]), int(parts[1]))
    except (subprocess.SubprocessError, ValueError, OSError, IndexError):
        return (0, 0)
