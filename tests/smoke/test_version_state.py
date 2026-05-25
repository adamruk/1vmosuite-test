"""Smoke test: version-state relocation + update-channel removal (ADR-0017 / B-051).

Two concerns, both deterministic and offline (ADR-0003 narrow exception — no
GPU, no ffmpeg, no network, no Qt event loop):

1. **Every app still imports** after `updater.py` was deleted and the version
   helpers moved to ``core/version_state.py`` — a dangling `from updater import
   DriveUpdater` in any of the four apps would fail collection here.
2. **The relocated helper works**: ``load_current_version`` reads
   ``assets/Version AutoRender.json`` and returns the stored version string, the
   save→load round-trip persists, and unknown apps / a missing file yield
   ``None`` (the semantics each app relies on for its title-label default).

Also guards that the in-app update channel is gone: ``import updater`` must fail
and no app module exposes a ``DriveUpdater`` attribute.
"""

from __future__ import annotations

import importlib
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from core import version_state  # noqa: E402

APP_MODULES = ["auto_render", "cutter", "merge", "mixer"]


@pytest.mark.parametrize("module_name", APP_MODULES)
def test_every_app_still_imports(module_name):
    """Each app imports cleanly (no dangling updater import)."""
    mod = importlib.import_module(module_name)
    assert mod is not None
    # The update channel is gone — no app should expose DriveUpdater.
    assert not hasattr(mod, "DriveUpdater")


def test_update_channel_module_removed():
    """`updater.py` was deleted — importing it must fail."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("updater")


def test_load_returns_stored_version_from_real_file():
    """The real assets/Version AutoRender.json loads a version string."""
    assert os.path.exists(version_state.VERSION_FILE)
    version = version_state.load_current_version("1vmo Auto Render")
    assert isinstance(version, str) and version


def test_load_unknown_app_returns_none():
    assert version_state.load_current_version("no such app") is None


def test_save_then_load_round_trip(tmp_path, monkeypatch):
    """save_current_version persists; load reads it back. Uses a temp file so
    the real version file is never mutated."""
    temp_file = tmp_path / "Version AutoRender.json"
    monkeypatch.setattr(version_state, "VERSION_FILE", str(temp_file))

    # Missing file → None.
    assert version_state.load_current_version("1vmo Cutter") is None

    version_state.save_current_version("9.9", "1vmo Cutter")
    assert version_state.load_current_version("1vmo Cutter") == "9.9"

    # A second app key coexists; the JSON shape matches the original schema.
    version_state.save_current_version("1.2", "1vmo Mixer")
    assert version_state.load_current_version("1vmo Cutter") == "9.9"
    assert version_state.load_current_version("1vmo Mixer") == "1.2"

    data = json.loads(temp_file.read_text())
    assert data["software"]["1vmo Cutter"]["version"] == "9.9"
    assert data["software"]["1vmo Mixer"]["version"] == "1.2"
