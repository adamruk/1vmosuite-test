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

import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Literal, Optional


# ========== Binary resolution ==========


def resolve_binaries(script_dir: Path) -> tuple[Path, Path]:
    """Return (ffmpeg_path, ffprobe_path) from the bundled ffmpeg/ subdirectory.

    Picks .exe suffix on Windows, no suffix elsewhere. Identical pattern to
    the literal form previously duplicated across all four apps + gpu_detect.
    """
    suffix = ".exe" if os.name == "nt" else ""
    ffmpeg = script_dir / "ffmpeg" / f"ffmpeg{suffix}"
    ffprobe = script_dir / "ffmpeg" / f"ffprobe{suffix}"
    return ffmpeg, ffprobe

    # ========== Windows hide-window helpers ==========


def hidden_startupinfo() -> Any:
    """Return a STARTUPINFO that hides the FFmpeg console window on Windows.

    Returns None on non-Windows platforms. Used as the startupinfo= kwarg
    to subprocess.Popen / subprocess.run.
    """
    if os.name != "nt":
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
    if os.name != "nt":
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
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
        "stdin": subprocess.PIPE,
        "startupinfo": hidden_startupinfo(),
        "creationflags": hidden_creationflags(),
    }

    # ========== ffprobe helpers ==========


def probe_duration(ffprobe: Path, video: Path) -> float:
    """Return video duration in seconds via ffprobe. Returns 0.0 on probe failure.

    Uses 'show entries format=duration' for compatibility across container types.
    """
    try:
        result = subprocess.run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
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
            [
                str(ffprobe),
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=s=x:p=0",
                str(video),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            startupinfo=hidden_startupinfo(),
            creationflags=hidden_creationflags(),
            timeout=30,
        )
        parts = result.stdout.strip().split("x")
        return (int(parts[0]), int(parts[1]))
    except (subprocess.SubprocessError, ValueError, OSError, IndexError):
        return (0, 0)

        # ========== Progress parsers (pure functions — easy to unit test) ==========


_LEGACY_DURATION_RE = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2})")
_LEGACY_TIME_RE = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})")
_PROGRESS_PIPE_TIME_RE = re.compile(r"out_time_ms=(\d+)")


class _DurationTracker:
    """Holds the discovered duration for the legacy_stderr dialect.

    FFmpeg emits a 'Duration:' line once near the start, then 'time=' lines
    throughout. We discover duration mid-stream, then compute percent.
    """

    def __init__(self, precomputed: Optional[float] = None) -> None:
        self.duration = precomputed or 0.0

    def feed_duration_line(self, line: str) -> None:
        if self.duration > 0:
            return  # already found
        m = _LEGACY_DURATION_RE.search(line)
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            self.duration = h * 3600 + mi * 60 + s


def _parse_legacy_line(line: str, tracker: _DurationTracker) -> Optional[int]:
    """Parse one line of legacy stderr output, return percent (0-100) or None."""
    tracker.feed_duration_line(line)
    if tracker.duration <= 0:
        return None
    m = _LEGACY_TIME_RE.search(line)
    if not m:
        return None
    h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
    elapsed = h * 3600 + mi * 60 + s
    pct = int(elapsed / tracker.duration * 100)
    return max(0, min(100, pct))


def _parse_progress_pipe_line(line: str, duration_seconds: float) -> Optional[int]:
    """Parse one line of -progress pipe:1 output, return percent (0-100) or None."""
    if duration_seconds <= 0:
        return None
    m = _PROGRESS_PIPE_TIME_RE.search(line)
    if not m:
        return None
        # Note: ffmpeg key is named out_time_ms but value is microseconds (ffmpeg misnomer)
    elapsed = int(m.group(1)) / 1_000_000
    pct = int(elapsed / duration_seconds * 100)
    return max(0, min(100, pct))

    # ========== Cancel ladder (Windows-correct graceful stop) ==========


def _cancel_ffmpeg(
    proc: subprocess.Popen,
    graceful_timeout: float = 8.0,
    terminate_timeout: float = 2.0,
) -> None:
    """Cancel a running FFmpeg process with proper graceful → kill escalation.

    Critical: on Windows, Popen.terminate() is equivalent to kill() (TerminateProcess).
    It does NOT flush the MP4 moov atom. To get a playable partial output, we must
    first ask FFmpeg to stop gracefully by writing 'q\\n' to stdin.

    Ladder:
    1. Write 'q\\n' to stdin (graceful — FFmpeg writes trailer). Wait up to 8s.
    2. If still alive: proc.terminate() (forceful — no cleanup). Wait up to 2s.
    3. If still alive: proc.kill() (last resort).
    """
    if proc.poll() is not None:
        return
        # Step 1: graceful 'q'
    try:
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.write("q\n")
            proc.stdin.flush()
            proc.stdin.close()
    except (OSError, BrokenPipeError, ValueError):
        pass
    try:
        proc.wait(timeout=graceful_timeout)
        return
    except subprocess.TimeoutExpired:
        pass
        # Step 2: terminate
    try:
        proc.terminate()
    except (OSError, ProcessLookupError):
        return
    try:
        proc.wait(timeout=terminate_timeout)
        return
    except subprocess.TimeoutExpired:
        pass
        # Step 3: kill
    try:
        proc.kill()
        proc.wait(timeout=terminate_timeout)
    except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
        pass

        # ========== Stderr drain (prevents pipe deadlock in progress_pipe mode) ==========


def _drain_stream(
    stream,
    on_line: Optional[Callable[[str], None]],
) -> None:
    """Drain a stream line-by-line, optionally calling on_line per line.

    Intended to run in a daemon thread so the pipe buffer never fills
    (which would deadlock ffmpeg). If on_line is None, lines are read
    and discarded.
    """
    try:
        for line in stream:
            if on_line is not None:
                try:
                    on_line(line.rstrip("\r\n"))
                except Exception:
                    pass  # caller's callback errors must not kill the drain
    except (OSError, ValueError):
        pass

        # ========== The runner ==========


Dialect = Literal["legacy_stderr", "progress_pipe"]


def run_ffmpeg(
    command: list[str],
    *,
    dialect: Dialect,
    duration_seconds: Optional[float] = None,
    on_progress: Optional[Callable[[int], None]] = None,
    on_output_line: Optional[Callable[[str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> int:
    """Run ffmpeg, stream progress, and handle cancellation cleanly.

    Args:
        command: Full ffmpeg command as list[str]. Callers are responsible
            for constructing the command including any dialect-specific
            flags (e.g., '-progress pipe:1' for progress_pipe dialect).
        dialect: 'legacy_stderr' parses 'Duration:' and 'time=' from stderr.
            'progress_pipe' parses 'out_time_ms=' from stdout — REQUIRES
            duration_seconds to be precomputed and passed in.
        duration_seconds: Precomputed video duration for percent calc.
            Required for progress_pipe dialect; optional for legacy_stderr
            (discovered from stream if not supplied).
        on_progress: Called with integer percent 0-100 ONLY when the percent
            increases by 1 or more (debounced to prevent UI thrash).
            Callback may emit Qt signals — Qt handles cross-thread queue.
        on_output_line: Called with every raw stream line (no trailing
            newline). Used for appending to an output console/text widget.
            Callback may emit Qt signals for cross-thread UI updates.
        should_cancel: Called frequently (between lines). If it returns
            True, the runner invokes the graceful cancel ladder. Typical:
            `lambda: self.is_cancelled` or `cancel_event.is_set`.

    Returns:
        Process exit code. 0 = success. Non-zero = ffmpeg's reported exit
        (callers classify whether it's a real failure vs. graceful cancel).
        A graceful 'q' cancel typically returns 255.

    Callback thread safety:
        All callbacks are invoked from the thread that called run_ffmpeg.
        That thread is almost certainly a worker thread (QThread or
        QRunnable.run()). When callbacks emit Qt signals, the default
        queued-connection semantics deliver them to the main thread safely.
        Do NOT directly touch Qt widgets from inside callbacks — emit
        signals instead.
    """
    # Build Popen kwargs from Phase 5a helper + dialect-specific stream wiring
    kwargs = ffmpeg_popen_kwargs()
    if dialect == "progress_pipe":
        # Progress blocks on stdout; stderr must be drained concurrently to
        # avoid pipe-buffer deadlock when ffmpeg writes warnings/errors.
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    else:  # legacy_stderr
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.PIPE

    proc = subprocess.Popen(command, **kwargs)
    drain_thread: Optional[threading.Thread] = None

    try:
        # If progress_pipe, drain stderr in background
        if dialect == "progress_pipe" and proc.stderr is not None:
            drain_thread = threading.Thread(
                target=_drain_stream,
                args=(proc.stderr, on_output_line),
                daemon=True,
            )
            drain_thread.start()

            # Choose primary stream and parser
        if dialect == "progress_pipe":
            primary_stream = proc.stdout
        else:
            primary_stream = proc.stderr

        tracker = (
            _DurationTracker(duration_seconds) if dialect == "legacy_stderr" else None
        )
        last_pct = -1

        if primary_stream is None:
            proc.wait()
            return proc.returncode

        for line in primary_stream:
            # Cancellation check (polled per line — cheap, fast)
            if should_cancel is not None and should_cancel():
                _cancel_ffmpeg(proc)
                break

            clean_line = line.rstrip("\r\n")

            # Emit raw line if requested (for console/log display).
            # In progress_pipe mode, stderr lines go via the drain thread;
            # here we emit primary-stream (stdout) lines.
            if on_output_line is not None:
                try:
                    on_output_line(clean_line)
                except Exception:
                    pass

                    # Parse progress
            if dialect == "legacy_stderr":
                pct = _parse_legacy_line(line, tracker)
            else:
                pct = _parse_progress_pipe_line(line, duration_seconds or 0.0)

                # Emit only on monotonic increase (prevents UI jitter)
            if pct is not None and pct > last_pct:
                last_pct = pct
                if on_progress is not None:
                    try:
                        on_progress(pct)
                    except Exception:
                        pass

                        # Wait for exit code
        rc = proc.wait()
        if drain_thread is not None:
            drain_thread.join(timeout=2.0)
        return rc

    finally:
        # Safety net: if we exit by exception or early return, ensure
        # no zombie process lingers.
        if proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=2.0)
            except (OSError, subprocess.TimeoutExpired):
                pass
