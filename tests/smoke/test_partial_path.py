"""Smoke tests for `naming_utils.partial_path` (v3.9 F-001 ship-blocker fix).

ADR-0003 narrow exception — pure-Python, <1s, deterministic. Pins
the contract that on-disk `.partial` files preserve the original
extension so ffmpeg's muxer inference works on Windows.
"""

from __future__ import annotations

from core.naming_utils import partial_path


def test_mp4_keeps_extension():
    assert partial_path("/out/clip.mp4") == "/out/clip.partial.mp4"


def test_mkv_keeps_extension():
    assert partial_path("/out/clip.mkv") == "/out/clip.partial.mkv"


def test_mov_keeps_extension():
    assert partial_path("/out/clip.mov") == "/out/clip.partial.mov"


def test_no_extension_falls_back_to_literal_suffix():
    assert partial_path("/out/clip") == "/out/clip.partial"


def test_does_not_produce_dot_partial_extension():
    """The whole point of v3.9 F-001: NEVER produce `<name>.<ext>.partial`."""
    for src in ("a.mp4", "b.mkv", "c.mov", "d.webm"):
        out = partial_path(src)
        assert not out.endswith(".partial"), f"{src} -> {out}"


def test_preserves_directory():
    p = partial_path("/some/long/path/clip01_h264.mp4")
    assert p.startswith("/some/long/path/")


def test_preserves_dot_in_basename():
    # File names with dots in the stem keep them; only the LAST
    # extension is the muxer-relevant one.
    assert partial_path("/out/clip.v2.mp4") == "/out/clip.v2.partial.mp4"
