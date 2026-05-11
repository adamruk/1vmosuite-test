#!/usr/bin/env python3
"""Cross-cutting integration smoke (sub-phase 2c-c-6).

Exercises the full preset pipeline post-2c-c-4:
  - load_builtin_json: read assets/Encoder.json (v2 schema with ids)
  - load_user_presets_json: round-trip a synthetic encoder.user.json
  - merged set: built-in + user
  - assert no id collisions across the merged set
  - assert id-prefix-based filtering works (built-in/user separation
    is intrinsic via prefix, not position)

Mirrors PARALLEL discovery's D1=c recommendation: smallest meaningful
cross-cut. Catches regression in the merge logic that replaced
_builtin_preset_count in 2c-c-4.

Tempdir-isolated. Read-only on assets/Encoder.json. Run from repo root:

  python tools/test_integration_smoke.py

Capture to tests/smoke-2c-c-6-regression-YYYYMMDD.log per ADR-0001.
Exits 0 on PASS.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.preset_loader import (  # noqa: E402
    Preset,
    load_builtin_json,
    load_user_presets_json,
    save_user_presets_json,
)

ENCODER_JSON = REPO_ROOT / "assets" / "Encoder.json"


# Canonical builtin preset count is 108 (= 106 from Encoder.txt + 2 hoisted
# Text defaults). See tools/generate_encoder_json.py. Was 111 before the
# B-017 + 2c-c-* preset cleanup. Historical smoke logs are immutable.
BUILTIN_PRESET_COUNT = 108


def test_builtin_loads_with_ids() -> bool:
    presets = load_builtin_json(ENCODER_JSON)
    if len(presets) != BUILTIN_PRESET_COUNT:
        print(f"  FAIL: expected {BUILTIN_PRESET_COUNT} builtin presets, got {len(presets)}")
        return False
    ids = [p.id for p in presets]
    if not all(i.startswith("builtin:") for i in ids):
        print("  FAIL: not all built-in ids start with 'builtin:'")
        return False
    if len(set(ids)) != BUILTIN_PRESET_COUNT:
        print(f"  FAIL: built-in ids not unique ({len(set(ids))}/{len(ids)})")
        return False
    print(f"  PASS: {BUILTIN_PRESET_COUNT} built-in ids loaded; all builtin: prefix; all unique")
    return True


def test_user_round_trip_then_merge() -> bool:
    with tempfile.TemporaryDirectory() as td:
        user_path = Path(td) / "encoder.user.json"
        user_presets = [
            Preset(
                id="user:integration-fresh",
                group="user",
                name="Integration Fresh",
                description="Fresh user preset for smoke",
                details="dd1",
                params=("-c:v", "libx264"),
            ),
            Preset(
                id="user:integration-shadow",
                group="user",
                name="Integration Shadow",
                description="Second user preset",
                details="dd2",
                params=("-c:v", "libx265"),
            ),
        ]
        save_user_presets_json(user_path, user_presets)
        loaded_user = load_user_presets_json(user_path)
        if loaded_user != user_presets:
            print("  FAIL: user round-trip mismatch")
            return False

        builtin = load_builtin_json(ENCODER_JSON)
        merged = list(builtin) + list(loaded_user)
        if len(merged) != BUILTIN_PRESET_COUNT + 2:
            print(f"  FAIL: merged length {len(merged)} != {BUILTIN_PRESET_COUNT}+2")
            return False

        merged_ids = [p.id for p in merged]
        if len(set(merged_ids)) != len(merged_ids):
            print("  FAIL: merged set has id collision")
            return False

        builtin_count = sum(1 for p in merged if p.id.startswith("builtin:"))
        user_count = sum(1 for p in merged if p.id.startswith("user:"))
        if builtin_count != BUILTIN_PRESET_COUNT or user_count != 2:
            print(
                f"  FAIL: id-prefix split wrong: builtin={builtin_count}, user={user_count}"
            )
            return False
        print(
            f"  PASS: merged {BUILTIN_PRESET_COUNT} builtin + 2 user; no collisions; prefix split correct"
        )
        return True


def test_user_save_filter_by_prefix() -> bool:
    """Verify that save_encoder_changes' filter (id.startswith('user:')) works."""
    with tempfile.TemporaryDirectory() as td:
        user_path = Path(td) / "encoder.user.json"
        builtin = load_builtin_json(ENCODER_JSON)
        fake_user = [
            Preset(
                id="user:filter-test",
                group="user",
                name="FilterTest",
                description="d",
                details="dd",
                params=("-c:v", "libx264"),
            ),
        ]
        merged = list(builtin) + list(fake_user)
        to_persist = [p for p in merged if p.id.startswith("user:")]
        if len(to_persist) != 1:
            print(f"  FAIL: filter kept {len(to_persist)} presets, expected 1")
            return False
        if to_persist[0].id != "user:filter-test":
            print(f"  FAIL: filter kept wrong preset: {to_persist[0].id}")
            return False
        save_user_presets_json(user_path, to_persist)
        reloaded = load_user_presets_json(user_path)
        if reloaded != to_persist:
            print("  FAIL: filter+save+reload mismatch")
            return False
        print("  PASS: id-prefix filter isolates user presets cleanly")
        return True


def main() -> int:
    print("=== Integration smoke (sub-phase 2c-c-6) ===")
    print(f"Platform: {sys.platform}")
    print(f"Encoder JSON: {ENCODER_JSON}")
    print()
    tests = [
        ("Built-in JSON loads with v2 ids", test_builtin_loads_with_ids),
        ("User round-trip + merged with built-in", test_user_round_trip_then_merge),
        ("User filter by id prefix", test_user_save_filter_by_prefix),
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
        print("PASS: integration smoke green")
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
