"""Smoke tests for `core.scoring.vmaf_runner` (Phase 3.2 VMAF).

The bulk of these tests gracefully skip when libvmaf is unavailable
in the bundled ffmpeg — that is itself the documented fallback path
(per ADR-0009). Two tests still run unconditionally:

  * test_missing_binary_returns_error
  * test_missing_input_files_return_error

both verifying that the runner never raises and always returns a
ScoreResult with vmaf_status set.

ADR-0003 narrow exception per ADR-0009.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from core.scoring.capabilities import detect
from core.scoring.score_models import ScoreAxisStatus
from core.scoring.vmaf_runner import score_vmaf


def _libvmaf_available() -> bool:
    ff = shutil.which("ffmpeg")
    if ff is None:
        return False
    caps = detect(Path(ff))
    return caps.vmaf_available


def _make_testsrc_video(out_path: Path, duration: float = 1.0) -> bool:
    ff = shutil.which("ffmpeg")
    if ff is None:
        return False
    cmd = [
        ff,
        "-hide_banner",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={duration}:size=320x240:rate=15",
        "-pix_fmt",
        "yuv420p",
        str(out_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=30)
        return proc.returncode == 0 and out_path.is_file()
    except subprocess.TimeoutExpired:
        return False


def test_missing_binary_returns_error(tmp_path: Path):
    """Runner must NEVER raise — it must return ScoreResult.vmaf_status=ERROR."""
    bogus_ffmpeg = tmp_path / "not_ffmpeg"
    result = score_vmaf(bogus_ffmpeg, tmp_path / "ref.mp4", tmp_path / "dist.mp4")
    assert result.vmaf_status is ScoreAxisStatus.ERROR
    assert result.vmaf_error is not None
    assert "ffmpeg" in result.vmaf_error.lower()


def test_missing_input_files_return_error(tmp_path: Path):
    ff = shutil.which("ffmpeg")
    if ff is None:
        pytest.skip("ffmpeg not on PATH")
    result = score_vmaf(Path(ff), tmp_path / "no_ref.mp4", tmp_path / "no_dist.mp4")
    assert result.vmaf_status is ScoreAxisStatus.ERROR


def test_identical_clip_yields_high_vmaf(tmp_path: Path):
    """When libvmaf is available, VMAF of a clip against itself ≈ 100."""
    if not _libvmaf_available():
        pytest.skip("libvmaf not available in bundled ffmpeg")
    ref = tmp_path / "ref.mp4"
    if not _make_testsrc_video(ref):
        pytest.skip("could not synthesize testsrc clip")
    dist = tmp_path / "dist.mp4"
    dist.write_bytes(ref.read_bytes())
    ff_path = Path(shutil.which("ffmpeg"))
    result = score_vmaf(ff_path, ref, dist, timeout_seconds=120.0)
    assert result.vmaf_status is ScoreAxisStatus.OK
    assert result.vmaf_mean is not None
    # An identical-clip VMAF can come out at exactly 100 or just under;
    # require >=95 as a generous floor that still flags a broken filter.
    assert result.vmaf_mean >= 95.0
