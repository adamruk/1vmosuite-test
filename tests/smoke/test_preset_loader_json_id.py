"""Smoke test for the load_presets_json id validation hole (T4 Fix A).

`core.preset_loader.load_presets_json` constructs v2 presets with
`Preset(id=p["id"], ...)`, but its required-field check historically did
NOT include `id`. So a v2 entry missing `id` escaped the descriptive
"missing required field" ValueError and threw a bare KeyError('id')
instead. Fix A makes the required-field check schema-aware: `id` is
required for schema_version 2, but NOT for v1 (v1 entries derive their
ids). This test pins:

  - a v2 entry missing `id` raises a descriptive ValueError mentioning
    `id` (and crucially NOT a KeyError);
  - a valid v2 entry still loads with its explicit id;
  - a v1 entry without `id` still loads (id derived) — proving Fix A did
    not over-tighten the v1 path.

ADR-0003 narrow exception: pure-Python, deterministic, single-purpose.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.preset_loader import load_presets_json


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_v2_missing_id_raises_descriptive_valueerror(tmp_path):
    """A v2 entry with no `id` raises ValueError(...'id'...), never KeyError."""
    p = _write(
        tmp_path / "enc.json",
        {
            "schema_version": 2,
            "presets": [
                {
                    "group": "G",
                    "name": "N",
                    "description": "d",
                    "details": "",
                    "params": ["-x"],
                }
            ],
        },
    )
    with pytest.raises(ValueError) as exc:
        load_presets_json(p)
    assert "id" in str(exc.value)
    assert "index 0" in str(exc.value)
    # Guard the original defect: it must NOT be a bare KeyError.
    assert not isinstance(exc.value, KeyError)


def test_valid_v2_still_loads(tmp_path):
    """A well-formed v2 entry loads with its explicit id preserved."""
    p = _write(
        tmp_path / "enc.json",
        {
            "schema_version": 2,
            "presets": [
                {
                    "id": "builtin:g/n",
                    "group": "G",
                    "name": "N",
                    "description": "d",
                    "details": "",
                    "params": ["-x", "-y"],
                }
            ],
        },
    )
    presets = load_presets_json(p)
    assert len(presets) == 1
    assert presets[0].id == "builtin:g/n"
    assert presets[0].params == ("-x", "-y")


def test_v1_without_id_still_loads(tmp_path):
    """A v1 entry without `id` still loads (id derived) — Fix A is v2-only."""
    p = _write(
        tmp_path / "enc.json",
        {
            "schema_version": 1,
            "presets": [
                {
                    "group": "G",
                    "name": "N",
                    "description": "d",
                    "details": "",
                    "params": ["-x"],
                }
            ],
        },
    )
    presets = load_presets_json(p)
    assert len(presets) == 1
    # id derived from (group, name) per ADR-0006.
    assert presets[0].id == "builtin:g/n"
