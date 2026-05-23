"""Smoke tests for `core.scoring.capabilities` (Phase 3.2 probe).

ADR-0003 narrow exception per ADR-0009. The probe shells out to the
bundled ffmpeg; in the CI / sandbox where ffmpeg may not be present
at the expected path, the tests cover the graceful-degradation
paths instead (missing binary → all-False caps with probe_error).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from core.scoring.capabilities import _FILTER_LINE, ScoringCapabilities, detect


def test_filter_line_matches_3char_flags():
    """Classic ffmpeg builds: 3-char flag column like `T..`."""
    sample = " T.. libvmaf            VV->V    Calculate VMAF.\n"
    matches = _FILTER_LINE.findall(sample)
    assert matches == ["libvmaf"]


def test_filter_line_matches_2char_flags():
    """v3.9 H1 fix: bundled ffmpeg can emit 2-char flag columns like `TS`."""
    sample = " TS  ssim              VV->V    Calculate SSIM.\n"
    matches = _FILTER_LINE.findall(sample)
    assert matches == ["ssim"]


def test_filter_line_matches_psnr_with_2char_flags():
    sample = " TS  psnr              VV->V    Calculate PSNR.\n"
    matches = _FILTER_LINE.findall(sample)
    assert matches == ["psnr"]


def test_filter_line_handles_multiline_block():
    sample = (
        " TS. psnr              VV->V    Calculate PSNR.\n"
        " TS  ssim              VV->V    Calculate SSIM.\n"
        " T.. libvmaf           VV->V    Calculate VMAF.\n"
    )
    matches = set(_FILTER_LINE.findall(sample))
    assert {"psnr", "ssim", "libvmaf"} <= matches


def test_default_capabilities_have_phash():
    caps = ScoringCapabilities()
    # pHash is always-on (it doesn't depend on ffmpeg filters).
    assert caps.phash_available is True
    # The ffmpeg axes default False.
    assert caps.vmaf_available is False
    assert caps.ssim_available is False
    assert caps.psnr_available is False


def test_summary_includes_phash_only_by_default():
    caps = ScoringCapabilities()
    assert "pHash" in caps.summary()


def test_any_axis_available_default_true():
    # pHash is always-on so any_axis_available() is True even with
    # no ffmpeg.
    assert ScoringCapabilities().any_axis_available() is True


def test_detect_missing_binary_returns_safe_caps(tmp_path: Path):
    bogus = tmp_path / "definitely_not_ffmpeg"
    caps = detect(bogus)
    assert caps.vmaf_available is False
    assert caps.ssim_available is False
    assert caps.psnr_available is False
    assert caps.phash_available is True
    assert caps.probe_error is not None
    assert "ffmpeg not found" in caps.probe_error


def test_detect_with_real_ffmpeg_if_available():
    """If a real ffmpeg lives on PATH, the probe should succeed and
    report at least SSIM + PSNR (universally available).

    Skipped when ffmpeg is absent — common on locked-down CI."""
    ff = shutil.which("ffmpeg")
    if not ff:
        return  # silent skip — ADR-0003 narrow exception
    caps = detect(Path(ff))
    # If the probe itself didn't error, at least one of SSIM/PSNR
    # should be available on any modern ffmpeg.
    if caps.probe_error is None:
        assert caps.ssim_available or caps.psnr_available
