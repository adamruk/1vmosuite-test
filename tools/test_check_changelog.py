#!/usr/bin/env python3
"""Manual smoke validator for scripts/check_changelog.py.

Tempdir-based — creates throwaway git repos and exercises the hook
against each scenario. Run from repo root:

  python tools/test_check_changelog.py

Capture output to tests/smoke-hook-changelog-YYYYMMDD.log per ADR-0001.
Tempdir isolation per D8 spirit (no real-repo pollution).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_changelog.py"


def setup_repo(tmpdir: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmpdir, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmpdir,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmpdir,
        check=True,
    )
    (tmpdir / "README.md").write_text("init\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmpdir, check=True)
    subprocess.run(
        ["git", "commit", "-q", "--no-verify", "-m", "init"],
        cwd=tmpdir,
        check=True,
    )


def stage(tmpdir: Path, path: str, content: str = "x\n") -> None:
    full = tmpdir / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", path], cwd=tmpdir, check=True)


def run_hook(tmpdir: Path, message: str) -> tuple[int, str, str]:
    msg_file = tmpdir / "COMMIT_MSG"
    msg_file.write_text(message, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(msg_file)],
        cwd=tmpdir,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def test_source_without_changelog_blocks() -> bool:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        setup_repo(td)
        stage(td, "core/foo.py")
        rc, out, err = run_hook(td, "feat: add foo\n")
        combined = out + err
        if rc != 1:
            print(f"  FAIL: expected exit 1, got {rc}")
            print(f"  output: {combined[:300]}")
            return False
        if "BLOCKED" not in combined:
            print(f"  FAIL: expected BLOCKED in output; got {combined[:200]}")
            return False
        print("  PASS: source-without-changelog correctly blocked")
        return True


def test_source_with_changelog_passes() -> bool:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        setup_repo(td)
        stage(td, "core/foo.py")
        stage(td, "CHANGELOG.md", "## [Unreleased]\n- entry\n")
        rc, _, err = run_hook(td, "feat: add foo\n")
        if rc != 0:
            print(f"  FAIL: expected exit 0, got {rc}; stderr={err[:200]}")
            return False
        print("  PASS: source+CHANGELOG passes")
        return True


def test_skip_marker_passes() -> bool:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        setup_repo(td)
        stage(td, "core/foo.py")
        rc, _, err = run_hook(td, "refactor: minor [skip changelog]\n")
        if rc != 0:
            print(f"  FAIL: expected exit 0, got {rc}; stderr={err[:200]}")
            return False
        print("  PASS: [skip changelog] bypass works")
        return True


def test_pure_docs_passes() -> bool:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        setup_repo(td)
        stage(td, "docs/some_note.md", "note\n")
        stage(td, "BACKLOG.md", "B-001\n")
        rc, _, err = run_hook(td, "docs: add note\n")
        if rc != 0:
            print(f"  FAIL: expected exit 0, got {rc}; stderr={err[:200]}")
            return False
        print("  PASS: pure-docs commit passes")
        return True


def test_merge_commit_passes() -> bool:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        setup_repo(td)
        stage(td, "core/foo.py")
        rc, _, err = run_hook(td, "Merge branch 'feature/x'\n")
        if rc != 0:
            print(f"  FAIL: expected exit 0, got {rc}; stderr={err[:200]}")
            return False
        print("  PASS: merge commit bypassed")
        return True


def test_requirements_txt_triggers() -> bool:
    """D2 verification: requirements.txt is SOURCE."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        setup_repo(td)
        stage(td, "requirements.txt", "pytest\n")
        rc, out, err = run_hook(td, "build: add pytest\n")
        combined = out + err
        if rc != 1 or "requirements.txt" not in combined:
            print(f"  FAIL: requirements.txt should trigger; rc={rc}")
            print(f"  output: {combined[:300]}")
            return False
        print("  PASS: requirements.txt classified as SOURCE")
        return True


def main() -> int:
    print("=== check_changelog.py smoke (sub-phase: hook-changelog) ===")
    print(f"Platform: {sys.platform}")
    print()
    tests = [
        ("Source w/o CHANGELOG blocks", test_source_without_changelog_blocks),
        ("Source w/ CHANGELOG passes", test_source_with_changelog_passes),
        ("[skip changelog] marker passes", test_skip_marker_passes),
        ("Pure docs passes", test_pure_docs_passes),
        ("Merge commit passes", test_merge_commit_passes),
        ("requirements.txt triggers (D2 verify)", test_requirements_txt_triggers),
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
        print("PASS: check_changelog hook works end-to-end")
        return 0
    print("FAIL: one or more scenarios failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
