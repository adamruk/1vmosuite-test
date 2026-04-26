#!/usr/bin/env python3
"""Manual-smoke validator for user-preset save/load round-trip (sub-phase 2c-c-3).

Aligned with ADR-0001 (smoke-logs-only). Run from repo root:
  python tools/test_user_save.py
Capture output to tests/smoke-2c-c-3-usersave-YYYYMMDD.log.
Exits 0 on PASS, non-zero on FAIL with reason.

Uses tempdir for isolation (D8=b decision); never pollutes real user_data_dir.
"""

from __future__ import annotations

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


def test_missing_file_returns_empty() -> bool:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "encoder.user.json"
        result = load_user_presets_json(path)
        if result != []:
            print(f"  FAIL: missing file should return []; got {result}")
            return False
        print("  PASS: missing file returns []")
        return True


def test_round_trip() -> bool:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "encoder.user.json"
        original = [
            Preset(
                group="user",
                name="Test1",
                description="d1",
                details="dd1",
                params=("-c:v", "libx264", "-crf", "20"),
            ),
            Preset(
                group="user",
                name="Vietnamese",
                description="Tiếng Việt",
                details="Chi tiết",
                params=("-c:a", "copy"),
            ),
        ]
        save_user_presets_json(path, original)
        loaded = load_user_presets_json(path)
        if loaded != original:
            print("  FAIL: round-trip mismatch")
            print(f"    expected: {original}")
            print(f"    got:      {loaded}")
            return False
        print(
            f"  PASS: round-trip preserved {len(original)} presets (incl. Vietnamese)"
        )
        return True


def test_bak_rotation() -> bool:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "encoder.user.json"
        gen1 = [Preset(group="user", name="V1", description="", details="", params=())]
        gen2 = [Preset(group="user", name="V2", description="", details="", params=())]

        save_user_presets_json(path, gen1)
        save_user_presets_json(path, gen2)

        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            print("  FAIL: .bak should exist after second save")
            return False

        bak_contents = load_user_presets_json(bak)
        if bak_contents != gen1:
            print(f"  FAIL: .bak should hold first generation; got {bak_contents}")
            return False
        print("  PASS: .bak rotation preserves first generation")
        return True


def main() -> int:
    print("=== User-preset save/load smoke (sub-phase 2c-c-3) ===")
    print(f"Platform: {sys.platform}")
    print()

    tests = [
        ("Missing file returns []", test_missing_file_returns_empty),
        ("Round-trip with Vietnamese chars", test_round_trip),
        (".bak rotation preserves first generation", test_bak_rotation),
    ]

    results = []
    for name, fn in tests:
        print(f"[{name}]")
        ok = fn()
        results.append(ok)
        print()

    passed = sum(results)
    total = len(results)
    print(f"=== {passed}/{total} tests passed ===")
    if passed == total:
        print("PASS: user-preset save/load round-trip works")
        return 0
    print("FAIL: one or more branches failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
