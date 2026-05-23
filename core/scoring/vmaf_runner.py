"""Phase 3.2 — VMAF runner using the bundled local ffmpeg + libvmaf.

The filter expression and JSON parsing are lifted from `bench.py`
_run_vmaf (the proven primitive). Two changes versus bench.py:

  1. subprocess.Popen with a polling loop instead of subprocess.run
     so a long VMAF pass can be cancelled mid-flight by the
     ScoreWorker.
  2. Returns a ScoreResult (with vmaf_* fields populated) instead of
     a raw dict; the rest of ScoreResult stays PENDING so the caller
     can chain additional axis runners against the same row.

NEVER touches the render pipeline. NEVER mutates any user file. The
only filesystem write is a private tempdir holding libvmaf's JSON log
(cleaned up on context exit).

All paths stay local.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

from core import ffmpeg_runner as core_ffmpeg_runner
from core.scoring.score_models import ScoreAxisStatus, ScoreResult

logger = logging.getLogger("core.scoring.vmaf_runner")


def _escape_filter_path(p: Path) -> str:
    """Escape a path for use inside an ffmpeg filtergraph log_path=.

    Lifted verbatim from bench.py — Windows drive-letter colons
    collide with libvmaf's filter-option ':' separator, so we both
    forward-slash the separators AND backslash-escape colons. Caller
    wraps the result in single quotes inside the filter string.
    """
    return str(p).replace("\\", "/").replace(":", "\\:")


def _stat_or_zero(p: Path) -> float:
    """Return mtime or 0 if unreadable — keeps ScoreResult.populate sane."""
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def score_vmaf(
    ffmpeg_path: Path,
    reference: Path,
    distorted: Path,
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
    progress_cb: Optional[Callable[[int], None]] = None,
    timeout_seconds: float = 1800.0,
) -> ScoreResult:
    """Compute VMAF mean / p5 / min / max for (reference, distorted).

    Args:
        ffmpeg_path: bundled local ffmpeg (must have libvmaf).
        reference: path to the original source file.
        distorted: path to the rendered output file.
        should_cancel: callable returning True when the caller wants
            the in-flight VMAF pass to terminate. Polled at ~250 ms.
        progress_cb: optional int callback (0..100); libvmaf does not
            stream per-frame progress cleanly, so we just emit 50 at
            start and 100 at finish — placeholder for future
            -progress pipe integration.
        timeout_seconds: hard cap on the whole pass. Default 30 min;
            libvmaf is single-threaded and slow on long clips.

    Returns:
        ScoreResult with vmaf_* fields populated (status OK / ERROR /
        CANCELLED). Other axis fields remain PENDING.

    Never raises. All errors are surfaced via vmaf_status=ERROR +
    vmaf_error="...". A missing libvmaf is the caller's responsibility
    to detect via ScoringCapabilities; this runner will still run and
    just return ERROR with the ffmpeg stderr tail.
    """
    result = ScoreResult(
        reference_path=str(reference),
        reference_mtime=_stat_or_zero(reference),
        distorted_path=str(distorted),
        distorted_mtime=_stat_or_zero(distorted),
        computed_at=time.time(),
    )

    if not ffmpeg_path.is_file():
        result.vmaf_status = ScoreAxisStatus.ERROR
        result.vmaf_error = f"ffmpeg not found at {ffmpeg_path}"
        return result
    if not reference.is_file():
        result.vmaf_status = ScoreAxisStatus.ERROR
        result.vmaf_error = f"reference missing: {reference}"
        return result
    if not distorted.is_file():
        result.vmaf_status = ScoreAxisStatus.ERROR
        result.vmaf_error = f"distorted missing: {distorted}"
        return result

    result.vmaf_status = ScoreAxisStatus.RUNNING
    if progress_cb is not None:
        try:
            progress_cb(0)
        except Exception:
            pass

    with tempfile.TemporaryDirectory(prefix="vmaf_") as tmpdir:
        log_path = Path(tmpdir) / "vmaf.json"
        filter_str = (
            "[0:v]setpts=PTS-STARTPTS[distorted];"
            "[1:v]setpts=PTS-STARTPTS[reference];"
            f"[distorted][reference]libvmaf=log_path='{_escape_filter_path(log_path)}'"
            ":log_fmt=json"
        )
        cmd = [
            str(ffmpeg_path),
            "-hide_banner",
            "-nostdin",
            "-i",
            str(distorted),
            "-i",
            str(reference),
            "-lavfi",
            filter_str,
            "-f",
            "null",
            "-",
        ]
        logger.debug("vmaf_runner: launching ffmpeg %r", cmd)
        # ffmpeg_popen_kwargs() already sets stdin=PIPE for graceful
        # cancel; we add stdout/stderr=PIPE for output capture.
        kwargs = core_ffmpeg_runner.ffmpeg_popen_kwargs()
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
        try:
            proc = subprocess.Popen(cmd, **kwargs)
        except OSError as exc:
            result.vmaf_status = ScoreAxisStatus.ERROR
            result.vmaf_error = f"ffmpeg launch failed: {exc}"
            return result

        # Poll for completion + cancel + timeout. We deliberately do
        # NOT call proc.communicate() in a single shot — we want
        # responsiveness for cancel.
        start = time.time()
        cancelled = False
        while True:
            rc = proc.poll()
            if rc is not None:
                break
            elapsed = time.time() - start
            if elapsed > timeout_seconds:
                logger.warning(
                    "vmaf_runner: timeout after %.0fs — killing ffmpeg",
                    elapsed,
                )
                _terminate(proc)
                result.vmaf_status = ScoreAxisStatus.ERROR
                result.vmaf_error = f"VMAF timed out after {int(timeout_seconds)}s"
                return result
            if should_cancel is not None:
                try:
                    if should_cancel():
                        cancelled = True
                        _terminate(proc)
                        break
                except Exception:
                    pass
            time.sleep(0.25)

        # Drain remaining stdout/stderr so the pipes close cleanly.
        # ffmpeg_popen_kwargs() sets text=True so stdout/stderr are
        # already str, not bytes.
        try:
            _stdout, stderr_b = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            _terminate(proc)
            _stdout, stderr_b = "", ""
        stderr_text = stderr_b or ""

        if cancelled:
            result.vmaf_status = ScoreAxisStatus.CANCELLED
            return result

        if proc.returncode != 0:
            tail = (
                stderr_text.strip().splitlines()[-1]
                if stderr_text.strip()
                else f"libvmaf exited {proc.returncode}"
            )
            result.vmaf_status = ScoreAxisStatus.ERROR
            result.vmaf_error = tail
            return result

        if not log_path.is_file():
            result.vmaf_status = ScoreAxisStatus.ERROR
            result.vmaf_error = "libvmaf produced no log file"
            return result

        try:
            with open(log_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            result.vmaf_status = ScoreAxisStatus.ERROR
            result.vmaf_error = f"failed to read libvmaf log: {exc}"
            return result

    pooled = data.get("pooled_metrics", {}).get("vmaf", {})
    frames = data.get("frames", [])
    per_frame = [
        f.get("metrics", {}).get("vmaf")
        for f in frames
        if f.get("metrics", {}).get("vmaf") is not None
    ]
    if not per_frame:
        result.vmaf_status = ScoreAxisStatus.ERROR
        result.vmaf_error = "libvmaf log had no per-frame vmaf metrics"
        return result

    per_frame_sorted = sorted(per_frame)
    p5_idx = int(0.05 * len(per_frame_sorted))
    result.vmaf_mean = pooled.get("mean")
    result.vmaf_p5 = per_frame_sorted[p5_idx]
    result.vmaf_min = pooled.get("min")
    result.vmaf_max = pooled.get("max")
    result.vmaf_status = ScoreAxisStatus.OK
    if progress_cb is not None:
        try:
            progress_cb(100)
        except Exception:
            pass
    return result


def _terminate(proc: subprocess.Popen) -> None:
    """Polite terminate -> kill ladder; tolerates already-dead child."""
    try:
        proc.terminate()
    except (OSError, ProcessLookupError):
        return
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except (OSError, ProcessLookupError):
            pass


# `os` import kept implicit by callers; ensure module compiles standalone.
_ = os  # noqa: F841 — referenced indirectly via Path operations


__all__ = ["score_vmaf"]
