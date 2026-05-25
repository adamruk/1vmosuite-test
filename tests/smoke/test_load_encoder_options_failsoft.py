"""Smoke test for fail-soft JSON startup path (T4 Fix B).

`auto_render.VideoRendererTool.load_encoder_options` has an opt-in branch
(`ENCODER_USE_JSON=1`) that loads built-in presets from assets/Encoder.json
via `load_builtin_json`. Historically that call had no try/except, so a
corrupt or schema-mismatched Encoder.json crashed app startup — unlike the
default Encoder.txt path, which is fail-soft. Fix B wraps the JSON load so
a failure degrades to an empty built-in list and the app still starts.

To exercise the REAL wrapped method without constructing the QWidget (which
needs a running QApplication), these tests call the unbound method against a
lightweight fake `self` carrying only the attributes the method reads
(`SCRIPT_DIR`, `USER_PRESETS_FILE`). The else (Encoder.txt) branch is never
taken here, so `ENCODER_FILE` is unused. This is the smallest unit that runs
the actual wrapped code — no result is faked.

ADR-0003 narrow exception: pure-Python, deterministic, single-purpose.
"""

from __future__ import annotations

import os
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from auto_render import VideoRendererTool  # noqa: E402


def _fake_self(tmp_path):
    """A minimal stand-in carrying just what load_encoder_options reads."""
    assets = tmp_path / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    return types.SimpleNamespace(
        SCRIPT_DIR=tmp_path,
        ENCODER_FILE=tmp_path / "assets" / "Encoder.txt",
        # Nonexistent → load_user_presets_json returns [] (file optional).
        USER_PRESETS_FILE=tmp_path / "encoder.user.json",
    )


def test_corrupt_json_degrades_without_raising(tmp_path, monkeypatch):
    """Syntactically corrupt Encoder.json on the JSON path → [] not a crash."""
    monkeypatch.setenv("ENCODER_USE_JSON", "1")
    fake = _fake_self(tmp_path)
    (tmp_path / "assets" / "Encoder.json").write_text(
        "{ this is not valid json", encoding="utf-8"
    )
    result = VideoRendererTool.load_encoder_options(fake)
    assert isinstance(result, list)
    assert result == []  # no built-ins (corrupt), no user presets (no file)


def test_schema_mismatch_degrades_without_raising(tmp_path, monkeypatch):
    """Valid JSON but wrong schema (pydantic ValidationError) → [] not a crash."""
    monkeypatch.setenv("ENCODER_USE_JSON", "1")
    fake = _fake_self(tmp_path)
    (tmp_path / "assets" / "Encoder.json").write_text(
        '{"schema_version": 99, "presets": []}', encoding="utf-8"
    )
    result = VideoRendererTool.load_encoder_options(fake)
    assert isinstance(result, list)
    assert result == []
