"""Smoke tests for `core.config.load` .bak read-back on corruption (T1).

Mirrors the proven .bak fallback in
core.preset_loader.load_user_presets_json: when the main config file is
corrupt but save_json_atomic already left a last-good `<path>.bak`, the
loader recovers the GOOD data instead of silently returning the default.

ADR-0003 narrow-pytest exception: pure-Python disk-IO unit, no Qt / no
ffmpeg / no GPU, deterministic, sub-second.
"""

from __future__ import annotations

from pathlib import Path

from core import config

GOOD = {"gpu_enabled": True, "gpu_preset": "p7", "num_threads": 4}
DEFAULT = {"gpu_enabled": False}


def _config_path(tmp_path: Path) -> Path:
    return tmp_path / "config_video_renderer.json"


def test_corrupt_main_recovers_from_bak(tmp_path: Path) -> None:
    """save() writes the file; a second save() rotates the first to .bak.
    Corrupting the main file then must recover the GOOD data from .bak."""
    path = _config_path(tmp_path)
    # First save creates the file; second save rotates it to .bak.
    config.save(path, GOOD)
    config.save(path, GOOD)
    bak = path.with_suffix(path.suffix + ".bak")
    assert bak.exists()
    # Corrupt the main file in place.
    path.write_text("{ this is not json", encoding="utf-8")

    loaded = config.load(path, default=DEFAULT)
    assert loaded == GOOD
    assert loaded != DEFAULT


def test_both_corrupt_returns_default(tmp_path: Path) -> None:
    path = _config_path(tmp_path)
    config.save(path, GOOD)
    config.save(path, GOOD)
    bak = path.with_suffix(path.suffix + ".bak")
    assert bak.exists()
    path.write_text("{ broken", encoding="utf-8")
    bak.write_text("also broken {", encoding="utf-8")

    loaded = config.load(path, default=DEFAULT)
    assert loaded == DEFAULT


def test_corrupt_main_no_bak_returns_default(tmp_path: Path) -> None:
    path = _config_path(tmp_path)
    path.write_text("{ broken", encoding="utf-8")
    # No .bak was ever written.
    assert not path.with_suffix(path.suffix + ".bak").exists()

    loaded = config.load(path, default=DEFAULT)
    assert loaded == DEFAULT


def test_bak_holding_non_dict_falls_back_to_default(tmp_path: Path) -> None:
    """A .bak that parses but is not a dict must not be returned —
    config.load contract is dict-only."""
    path = _config_path(tmp_path)
    bak = path.with_suffix(path.suffix + ".bak")
    path.write_text("{ broken", encoding="utf-8")
    bak.write_text("[1, 2, 3]", encoding="utf-8")

    loaded = config.load(path, default=DEFAULT)
    assert loaded == DEFAULT


def test_missing_file_returns_default_without_touching_bak(tmp_path: Path) -> None:
    """Missing main file is the first-launch case; a stale .bak must NOT
    be loaded (preserves the existing missing-file early-return)."""
    path = _config_path(tmp_path)
    bak = path.with_suffix(path.suffix + ".bak")
    bak.write_text('{"gpu_enabled": true}', encoding="utf-8")
    assert not path.exists()

    loaded = config.load(path, default=DEFAULT)
    assert loaded == DEFAULT


def test_good_main_unaffected(tmp_path: Path) -> None:
    """Happy path is unchanged: a valid main file is returned verbatim."""
    path = _config_path(tmp_path)
    config.save(path, GOOD)
    loaded = config.load(path, default=DEFAULT)
    assert loaded == GOOD
