"""Smoke tests for `core.scoring.phash_runner` (Phase 3.2 dHash).

We exercise the pure-Python pieces (dHash, Hamming distance) without
requiring ffmpeg. The end-to-end frame-extract path is exercised in
the optional integration test below, which is skipped if ffmpeg is
unavailable.

ADR-0003 narrow exception per ADR-0009.
"""

from __future__ import annotations

import io
import shutil
import subprocess
from pathlib import Path

import pytest

from core.scoring.phash_runner import (
    _dhash_64,
    _hamming64,
    _probe_duration_seconds,
    score_phash,
)
from core.scoring.score_models import ScoreAxisStatus

# ----------------------------------------------------------------------
# Pure-Python: dHash + Hamming
# ----------------------------------------------------------------------


def _make_solid_jpeg(color: int) -> bytes:
    """Make a 144x128 solid-grey JPEG. Uses Pillow."""
    from PIL import Image

    img = Image.new("L", (144, 128), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_dhash_same_color_yields_zero_distance():
    a = _make_solid_jpeg(128)
    b = _make_solid_jpeg(128)
    ha = _dhash_64(a)
    hb = _dhash_64(b)
    assert ha is not None and hb is not None
    assert _hamming64(ha, hb) == 0


def test_dhash_different_color_still_zero_for_solid():
    # Two solid-grey but different brightness images both produce
    # all-zero dHash (no per-row gradient). This is a known dHash
    # property; verifying it pins the expectation.
    a = _make_solid_jpeg(50)
    b = _make_solid_jpeg(200)
    ha = _dhash_64(a)
    hb = _dhash_64(b)
    assert ha is not None and hb is not None
    assert _hamming64(ha, hb) == 0


def test_dhash_vertical_stripes_vs_solid_nonzero():
    """Vertical stripes (8 alternating black/white bands) produce a
    non-zero hash because adjacent dHash cells straddle the band
    boundaries. Solid grey produces all-zero. Hamming distance must
    be > 0 — verifies dHash sensitivity to spatial structure.
    """
    from PIL import Image

    stripes = Image.new("L", (144, 128))
    px = stripes.load()
    band_w = 144 // 8
    for y in range(stripes.height):
        for x in range(stripes.width):
            band = (x // band_w) % 2
            px[x, y] = 255 if band == 0 else 0
    buf = io.BytesIO()
    stripes.save(buf, format="JPEG", quality=90)
    a_bytes = buf.getvalue()
    b_bytes = _make_solid_jpeg(128)
    ha = _dhash_64(a_bytes)
    hb = _dhash_64(b_bytes)
    assert ha is not None and hb is not None
    # Stripes produce a strong alternating pattern; expect at least
    # 4 bits of difference vs solid (which is all-zero).
    assert _hamming64(ha, hb) >= 4


def test_dhash_corrupt_bytes_returns_none():
    assert _dhash_64(b"not a jpeg") is None


def test_hamming_basics():
    assert _hamming64(0, 0) == 0
    assert _hamming64(0xFFFF_FFFF_FFFF_FFFF, 0) == 64
    assert _hamming64(0b101, 0b010) == 3


# ----------------------------------------------------------------------
# Integration with ffmpeg — skipped if unavailable.
# ----------------------------------------------------------------------


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _make_testsrc_video(out_path: Path, duration: float = 2.0) -> bool:
    """Build a tiny test video using ffmpeg's testsrc filter. Returns True on success."""
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


def test_phash_identical_clips_distance_zero(tmp_path: Path):
    if not _has_ffmpeg():
        pytest.skip("ffmpeg not on PATH")
    ref = tmp_path / "ref.mp4"
    if not _make_testsrc_video(ref):
        pytest.skip("could not synthesize test clip via ffmpeg testsrc")
    dist = tmp_path / "dist.mp4"
    # Copy the file byte-for-byte → distance must be 0 for every frame.
    dist.write_bytes(ref.read_bytes())
    ff_path = Path(shutil.which("ffmpeg"))
    result = score_phash(ff_path, ref, dist, n_frames=5)
    assert result.phash_status is ScoreAxisStatus.OK
    assert result.phash_avg_distance == pytest.approx(0.0, abs=1.0)


def test_phash_missing_file_returns_error(tmp_path: Path):
    ff_path = Path(shutil.which("ffmpeg") or "/nonexistent")
    result = score_phash(
        ff_path, tmp_path / "missing_a.mp4", tmp_path / "missing_b.mp4"
    )
    assert result.phash_status is ScoreAxisStatus.ERROR
    assert result.phash_error is not None


def test_probe_duration_nonexistent_returns_none(tmp_path: Path):
    ff = shutil.which("ffmpeg")
    if ff is None:
        pytest.skip("ffmpeg not on PATH")
    assert _probe_duration_seconds(Path(ff), tmp_path / "missing.mp4") is None
