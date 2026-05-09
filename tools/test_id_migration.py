#!/usr/bin/env python3
"""Round-trip a v1 user JSON file through the lazy migration (sub-phase 2c-c-4).

Per ADR-0006: load_user_presets_json supports v1 (no id, derive at
load) and v2 (read as-is). On first save after a v1 load, file is
rewritten as v2. This script exercises that path with a tempdir.
Run from repo root:

  python tools/test_id_migration.py

Capture to tests/smoke-2c-c-4-migration-YYYYMMDD.log per ADR-0001.
Exits 0 on PASS.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.preset_loader import (  # noqa: E402
    Preset,
    load_user_presets_json,
    save_user_presets_json,
)


def test_v1_loads_with_derived_ids() -> bool:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "encoder.user.json"
        v1_payload = {
            "schema_version": 1,
            "presets": [
                {
                    "group": "user",
                    "name": "First Entry",
                    "description": "d1",
                    "details": "dd1",
                    "params": ["-c:v", "libx264"],
                },
                {
                    "group": "user",
                    "name": "Second Entry",
                    "description": "d2",
                    "details": "dd2",
                    "params": ["-c:v", "libx265"],
                },
            ],
        }
        path.write_text(json.dumps(v1_payload), encoding="utf-8")
        loaded = load_user_presets_json(path)
        if len(loaded) != 2:
            print(f"  FAIL: expected 2 presets, got {len(loaded)}")
            return False
        if loaded[0].id != "user:first-entry" or loaded[1].id != "user:second-entry":
            print(f"  FAIL: derived ids wrong; got {[p.id for p in loaded]}")
            return False
        print(f"  PASS: v1 file loaded with derived ids: {[p.id for p in loaded]}")
        return True


def test_v1_to_v2_persisted_on_save() -> bool:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "encoder.user.json"
        v1_payload = {
            "schema_version": 1,
            "presets": [
                {
                    "group": "user",
                    "name": "Test",
                    "description": "d",
                    "details": "dd",
                    "params": ["-c:v", "libx264"],
                },
            ],
        }
        path.write_text(json.dumps(v1_payload), encoding="utf-8")
        loaded = load_user_presets_json(path)
        save_user_presets_json(path, loaded)
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("schema_version") != 2:
            print(f"  FAIL: expected v2 after save, got {raw.get('schema_version')}")
            return False
        if not raw["presets"][0].get("id", "").startswith("user:"):
            print("  FAIL: id field missing or wrong format after save")
            return False
        print(
            f"  PASS: v1 -> v2 persisted on save; first id={raw['presets'][0]['id']!r}"
        )
        return True


def test_v2_loads_as_is() -> bool:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "encoder.user.json"
        original = [
            Preset(
                id="user:custom-one",
                group="user",
                name="Custom One",
                description="d1",
                details="dd1",
                params=("-c:v", "libx264"),
            ),
        ]
        save_user_presets_json(path, original)
        loaded = load_user_presets_json(path)
        if loaded != original:
            print("  FAIL: v2 round-trip mismatch")
            return False
        print("  PASS: v2 round-trip preserved")
        return True


def main() -> int:
    print("=== ID migration smoke (sub-phase 2c-c-4) ===")
    print(f"Platform: {sys.platform}")
    print()
    tests = [
        ("v1 file loads with derived ids", test_v1_loads_with_derived_ids),
        ("v1 -> v2 persisted on save", test_v1_to_v2_persisted_on_save),
        ("v2 file round-trips as-is", test_v2_loads_as_is),
    ]
    results = []
    for name, fn in tests:
        print(f"[{name}]")
        results.append(fn())
        print()
    passed = sum(results)
    total = len(results)
    print(f"=== {passed}/{total} tests passed ===")
    if passed == total:
        print("PASS: ID migration round-trip works")
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
