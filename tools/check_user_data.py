#!/usr/bin/env python3
"""Manual-smoke validator for core.user_data.resolve_user_data_dir.

Aligned with ADR-0001 (smoke-logs-only convention; no pytest).
Run from repo root: python tools/check_user_data.py
Capture output to tests/smoke-2c-c-2-userdata-YYYYMMDD.log.
Exits 0 on PASS, non-zero on FAIL with reason.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.user_data import (  # noqa: E402
    PortableLocationError,
    _is_protected_dir,
    resolve_user_data_dir,
)
from platformdirs import user_data_path  # noqa: E402


def test_default_returns_platformdirs() -> bool:
    with tempfile.TemporaryDirectory() as td:
        install_dir = Path(td)
        result = resolve_user_data_dir(install_dir)
        expected = Path(user_data_path("1vmo-suite", appauthor=False))
        if result != expected:
            print(f"  FAIL: expected {expected}, got {result}")
            return False
        print(f"  PASS: default -> {result}")
        return True


def test_portable_safe_returns_userdata() -> bool:
    with tempfile.TemporaryDirectory() as td:
        install_dir = Path(td)
        (install_dir / "portable.txt").write_text("test\n", encoding="utf-8")
        result = resolve_user_data_dir(install_dir)
        expected = install_dir / "UserData"
        if result != expected:
            print(f"  FAIL: expected {expected}, got {result}")
            return False
        print(f"  PASS: portable safe -> {result}")
        return True


def test_portable_protected_raises() -> bool:
    with tempfile.TemporaryDirectory() as td:
        install_dir = Path(td)
        (install_dir / "portable.txt").write_text("test\n", encoding="utf-8")
        with patch("core.user_data._is_protected_dir", return_value=True):
            try:
                resolve_user_data_dir(install_dir)
                print("  FAIL: expected PortableLocationError, none raised")
                return False
            except PortableLocationError:
                print("  PASS: portable + protected -> raised PortableLocationError")
                return True


def test_protected_dir_detection() -> bool:
    if sys.platform != "win32":
        print("  SKIP: non-win32 platform")
        return True
    pf = os.environ.get("ProgramFiles")
    if not pf:
        print("  SKIP: no %ProgramFiles% env var")
        return True
    fake_install = Path(pf) / "1vmo-test"
    if not _is_protected_dir(fake_install):
        print(f"  FAIL: '{fake_install}' not detected as protected")
        return False
    print(f"  PASS: '{fake_install}' detected as protected")
    return True


def main() -> int:
    print("=== core.user_data smoke validation (sub-phase 2c-c-2) ===")
    print(f"Platform: {sys.platform}")
    print()

    tests = [
        (
            "Default (no sentinel) returns platformdirs path",
            test_default_returns_platformdirs,
        ),
        (
            "Portable mode + safe install dir returns UserData",
            test_portable_safe_returns_userdata,
        ),
        ("Portable mode + protected dir raises", test_portable_protected_raises),
        ("Protected-dir detection (Program Files)", test_protected_dir_detection),
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
        print("PASS: core.user_data resolves correctly across all branches")
        return 0
    print("FAIL: one or more branches failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
