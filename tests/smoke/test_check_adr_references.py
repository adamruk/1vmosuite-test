"""Smoke test for the ADR-reference checker's self-exclusion (B-046).

B-046: `scripts/check_adr_references.py` excluded itself (and the
`docs/decisions/ADR-*` tree, which may cite future ADRs) via substring
matching against `str(p)`. On Windows a resolved `Path` stringifies with
backslash separators, so the forward-slash `EXCLUDE_PATH_SUBSTRINGS`
never matched — the script scanned itself, found the fabricated
four-digit ADR token in its own regex range comment, and exited 1 on
every clean Windows run.

The fix normalizes the path to forward slashes via `Path.as_posix()`
before the substring test, making exclusion separator-agnostic. These
tests exercise that on the real repo tree (so they pass on the CI/dev
OS regardless of separator) plus a synthetic Windows path to prove the
normalization itself.

ADR-0003 narrow exception: pure-Python, deterministic, single-purpose.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path, PureWindowsPath

_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent
    / "scripts"
    / "check_adr_references.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("check_adr_references", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_script_excludes_itself():
    """collect_scan_paths must not include the checker script itself."""
    mod = _load_module()
    scanned = {p.name for p in mod.collect_scan_paths()}
    assert "check_adr_references.py" not in scanned


def test_script_excludes_adr_decision_files():
    """ADR files (which may cite future ADRs) are not scanned."""
    mod = _load_module()
    for p in mod.collect_scan_paths():
        assert "/docs/decisions/ADR-" not in p.as_posix()


def test_main_exits_zero_on_clean_tree():
    """The real defect: on a clean tree the checker must exit 0, not 1."""
    mod = _load_module()
    assert mod.main() == 0


def test_exclusion_is_separator_agnostic():
    """The fix's core: a Windows-style path must still match the
    forward-slash exclusion substrings via as_posix()."""
    win_path = PureWindowsPath(r"C:\repo\scripts\check_adr_references.py")
    # Pre-fix behavior used str(p) (backslashes) — would NOT match.
    assert "/scripts/check_adr_references.py" not in str(win_path)
    # Post-fix behavior uses as_posix() — DOES match.
    assert "/scripts/check_adr_references.py" in win_path.as_posix()
