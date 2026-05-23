"""Phase 3.2 — SSIM + PSNR runner using ffmpeg-native filters.

Why bundled together: SSIM and PSNR can be computed in a single
ffmpeg pass via `-lavfi ssim;psnr`, so one ffmpeg invocation gives
both metrics. Cheaper than two separate passes (~5-10 s on a 60 s
1080p clip on a modern CPU).

No libvmaf dependency. Every reasonable ffmpeg build supports these
filters; the capability probe is still there as a defensive guard.

Output parsing:
    The `ssim` filter prints lines to stats_file in the form:
        n:1 Y:0.987 U:0.992 V:0.991 All:0.989 (19.49)
    The `psnr` filter prints:
        n:1 mse_avg:0.49 mse_y:0.56 ... psnr_avg:51.20 psnr_y:50.65 ...
    We don't ask for stats_file — we let the filter print its summary
    to ffmpeg's stderr in the form `SSIM Y:... All:0.989 (xx.xx dB)`
    and `PSNR y:50.65 u:54.12 v:54.18 average:51.20 min:40.00 max:73.99`
    and grep that line. Avoids writing extra temp files.

Local-only. No network. No external API.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

from core import ffmpeg_runner as core_ffmpeg_runner
from core.scoring.score_models import ScoreAxisStatus, ScoreResult

logger = logging.getLogger("core.scoring.ssim_psnr_runner")

# `[Parsed_ssim_0 @ 0x...] SSIM Y:0.987 U:0.992 V:0.991 All:0.989 (19.49)`
_SSIM_ALL_RE = re.compile(r"SSIM\s.*?All:([0-9.]+)", re.IGNORECASE)

# `[Parsed_psnr_1 @ 0x...] PSNR y:50.65 u:54.12 v:54.18 average:51.20 min:... max:...`
_PSNR_AVG_RE = re.compile(r"PSNR\s.*?average:([0-9.]+)", re.IGNORECASE)


def _stat_or_zero(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def score_ssim_psnr(
    ffmpeg_path: Path,
    reference: Path,
    distorted: Path,
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
    timeout_seconds: float = 900.0,
    base_result: Optional[ScoreResult] = None,
) -> ScoreResult:
    """Compute SSIM (All) + PSNR (average) for (reference, distorted).

    Args:
        ffmpeg_path: bundled local ffmpeg.
        reference: source file.
        distorted: rendered output.
        should_cancel: optional cancel poll.
        timeout_seconds: hard cap (15 min default — SSIM/PSNR are
            much faster than VMAF so the budget is tighter).
        base_result: optionally a ScoreResult to mutate in place
            (e.g. one already populated by score_vmaf). If None,
            a fresh ScoreResult is created with all other axes
            left PENDING.

    Returns the same ScoreResult with ssim_* and psnr_* fields
    updated. Never raises.
    """
    if base_result is None:
        result = ScoreResult(
            reference_path=str(reference),
            reference_mtime=_stat_or_zero(reference),
            distorted_path=str(distorted),
            distorted_mtime=_stat_or_zero(distorted),
            computed_at=time.time(),
        )
    else:
        result = base_result

    if not ffmpeg_path.is_file():
        msg = f"ffmpeg not found at {ffmpeg_path}"
        result.ssim_status = ScoreAxisStatus.ERROR
        result.ssim_error = msg
        result.psnr_status = ScoreAxisStatus.ERROR
        result.psnr_error = msg
        return result
    if not reference.is_file():
        msg = f"reference missing: {reference}"
        result.ssim_status = ScoreAxisStatus.ERROR
        result.ssim_error = msg
        result.psnr_status = ScoreAxisStatus.ERROR
        result.psnr_error = msg
        return result
    if not distorted.is_file():
        msg = f"distorted missing: {distorted}"
        result.ssim_status = ScoreAxisStatus.ERROR
        result.ssim_error = msg
        result.psnr_status = ScoreAxisStatus.ERROR
        result.psnr_error = msg
        return result

    result.ssim_status = ScoreAxisStatus.RUNNING
    result.psnr_status = ScoreAxisStatus.RUNNING

    # Run both filters in a single ffmpeg pass. The split is used
    # to fork the reference + distorted streams into both filters.
    filter_str = (
        "[0:v]setpts=PTS-STARTPTS,split=2[d1][d2];"
        "[1:v]setpts=PTS-STARTPTS,split=2[r1][r2];"
        "[d1][r1]ssim;"
        "[d2][r2]psnr"
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
    logger.debug("ssim_psnr_runner: launching ffmpeg %r", cmd)
    # ffmpeg_popen_kwargs() already sets stdin=PIPE; we add
    # stdout/stderr=PIPE for output capture.
    kwargs = core_ffmpeg_runner.ffmpeg_popen_kwargs()
    kwargs["stdout"] = subprocess.PIPE
    kwargs["stderr"] = subprocess.PIPE
    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except OSError as exc:
        msg = f"ffmpeg launch failed: {exc}"
        result.ssim_status = ScoreAxisStatus.ERROR
        result.ssim_error = msg
        result.psnr_status = ScoreAxisStatus.ERROR
        result.psnr_error = msg
        return result

    start = time.time()
    cancelled = False
    while True:
        rc = proc.poll()
        if rc is not None:
            break
        if time.time() - start > timeout_seconds:
            _terminate(proc)
            msg = f"SSIM/PSNR timed out after {int(timeout_seconds)}s"
            result.ssim_status = ScoreAxisStatus.ERROR
            result.ssim_error = msg
            result.psnr_status = ScoreAxisStatus.ERROR
            result.psnr_error = msg
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

    # ffmpeg_popen_kwargs() sets text=True so stdout/stderr come back
    # as str already — no .decode() needed.
    try:
        _stdout, stderr_b = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        _terminate(proc)
        _stdout, stderr_b = "", ""
    stderr_text = stderr_b or ""

    if cancelled:
        result.ssim_status = ScoreAxisStatus.CANCELLED
        result.psnr_status = ScoreAxisStatus.CANCELLED
        return result

    if proc.returncode != 0:
        tail = (
            stderr_text.strip().splitlines()[-1]
            if stderr_text.strip()
            else f"ffmpeg exited {proc.returncode}"
        )
        result.ssim_status = ScoreAxisStatus.ERROR
        result.ssim_error = tail
        result.psnr_status = ScoreAxisStatus.ERROR
        result.psnr_error = tail
        return result

    # Parse the SSIM/PSNR summary lines from stderr.
    ssim_match = _SSIM_ALL_RE.search(stderr_text)
    psnr_match = _PSNR_AVG_RE.search(stderr_text)
    if ssim_match is not None:
        try:
            result.ssim_mean = float(ssim_match.group(1))
            result.ssim_status = ScoreAxisStatus.OK
        except ValueError:
            result.ssim_status = ScoreAxisStatus.ERROR
            result.ssim_error = "could not parse SSIM value"
    else:
        result.ssim_status = ScoreAxisStatus.ERROR
        result.ssim_error = "no SSIM summary line in ffmpeg output"
    if psnr_match is not None:
        try:
            result.psnr_mean = float(psnr_match.group(1))
            result.psnr_status = ScoreAxisStatus.OK
        except ValueError:
            result.psnr_status = ScoreAxisStatus.ERROR
            result.psnr_error = "could not parse PSNR value"
    else:
        result.psnr_status = ScoreAxisStatus.ERROR
        result.psnr_error = "no PSNR summary line in ffmpeg output"
    return result


def _terminate(proc: subprocess.Popen) -> None:
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


__all__ = ["score_ssim_psnr"]
