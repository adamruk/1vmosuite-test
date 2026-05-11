#!/usr/bin/env python3
"""Repository consistency validator for 1vmo Suite.

A single entry point for the manifest-style checks Adam runs by hand
during PR review. Catches:

    1. Missing required source / asset / doc files (Adam's spec).
    2. Missing required directories.
    3. PyQt5 / pyqt / .exec_() / QRegExp / qt_compat residue in *.py.
    4. Existence of qt_compat / qtpy / qt_shim files anywhere in tree.
    5. PySide6 import surface present in app entry points.

Exit codes:
    0 = clean
    1 = at least one consistency check failed
    2 = environmental error

This script is intentionally a single-purpose pre-flight gate. It is
NOT a substitute for manual functional verification (app launch + real
render) — see CLAUDE.md §2.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FILES = [
    # Apps + helpers
    "auto_render.py",
    "cutter.py",
    "merge.py",
    "mixer.py",
    "settings_dialog.py",
    "help_dialog.py",
    "updater.py",
    "bench.py",
    "gpu_detect.py",
    "requirements.txt",
    # Dot-config
    ".gitignore",
    ".pre-commit-config.yaml",
    ".markdownlint.yaml",
    ".markdownlintignore",
    ".cz.toml",
    # Root governance docs
    "README.md",
    "CLAUDE.md",
    "BACKLOG.md",
    "CHANGELOG.md",
    "FFMPEG_CPU_TO_NVENC_REFERENCE.md",
    # Core modules
    "core/__init__.py",
    "core/atomic_write.py",
    "core/config.py",
    "core/encoder_schema.py",
    "core/ffmpeg_runner.py",
    "core/file_picker.py",
    "core/naming_utils.py",
    "core/preset_loader.py",
    "core/preset_translator.py",
    "core/user_data.py",
    "core/widgets.py",
    "core/url_downloader.py",
    # Assets
    "assets/Encoder.json",
    "assets/Encoder.txt",
    "assets/Version AutoRender.json",
    # Decision records
    "docs/decisions/README.md",
    "docs/decisions/ADR-0001-phase-2-methodology-reconciliation.md",
    "docs/decisions/ADR-0002-product-trajectory.md",
    "docs/decisions/ADR-0003-narrow-pytest-exceptions.md",
    "docs/decisions/ADR-0004-cross-platform-mac-support.md",
    "docs/decisions/ADR-0005-platformdirs-user-data.md",
    "docs/decisions/ADR-0006-preset-id-schema-v2.md",
    "docs/decisions/ADR-0007-gpu-pipeline.md",
    "docs/decisions/ADR-0008-vmaf-thresholds.md",
    # Roadmap
    "docs/ROADMAP.md",
]

REQUIRED_DIRS = [
    "assets",
    "assets/data",
    "core",
    "docs",
    "docs/decisions",
    "tests",
    "tools",
    "benchmarks",
    "scripts",
]

# Source patterns that must NOT appear in *.py outside .venv/__pycache__/.git
FORBIDDEN_SOURCE_PATTERNS = [
    (r"\bfrom\s+PyQt5\b", "PyQt5 import"),
    (r"\bimport\s+PyQt5\b", "PyQt5 import"),
    (r"\bpyqtSignal\b", "PyQt5 idiom: pyqtSignal"),
    (r"\bpyqtSlot\b", "PyQt5 idiom: pyqtSlot"),
    (r"\bpyqtProperty\b", "PyQt5 idiom: pyqtProperty"),
    (r"\.exec_\(", "PyQt5 idiom: .exec_()"),
    (r"\bQRegExp\b", "PyQt5-only API: QRegExp"),
    (r"\bQStringList\b", "PyQt5-only API: QStringList"),
]

# Files that must NOT exist (compat shims)
FORBIDDEN_FILES_GLOBS = [
    "**/qt_compat*",
    "**/qtpy*",
    "**/qt_shim*",
]

# Subtrees to skip when scanning for forbidden patterns
SCAN_EXCLUDES = (".venv", "__pycache__", ".git", "build", "dist")

# Individual files that legitimately contain the forbidden tokens
# (this script's own docstring + pattern table, etc.). Skip them by
# relative path so they don't self-flag.
SCAN_EXCLUDE_FILES = {
    Path("scripts/check_repo_consistency.py"),
}


def is_excluded(path: Path) -> bool:
    if any(part in SCAN_EXCLUDES for part in path.parts):
        return True
    try:
        rel = path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return False
    return rel in SCAN_EXCLUDE_FILES


def main() -> int:
    failures: list[str] = []

    # 1. Required files
    missing_files = [rel for rel in REQUIRED_FILES if not (REPO_ROOT / rel).is_file()]
    if missing_files:
        failures.append("Missing required files:")
        for rel in missing_files:
            failures.append(f"  - {rel}")

    # 2. Required directories
    missing_dirs = [rel for rel in REQUIRED_DIRS if not (REPO_ROOT / rel).is_dir()]
    if missing_dirs:
        failures.append("Missing required directories:")
        for rel in missing_dirs:
            failures.append(f"  - {rel}/")

    # 3. Forbidden source patterns in *.py
    compiled_patterns = [
        (re.compile(p), label) for p, label in FORBIDDEN_SOURCE_PATTERNS
    ]
    forbidden_hits: list[str] = []
    for py in REPO_ROOT.rglob("*.py"):
        if is_excluded(py):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern, label in compiled_patterns:
                if pattern.search(line):
                    rel_path = py.relative_to(REPO_ROOT)
                    forbidden_hits.append(
                        f"  {rel_path}:{lineno}  ({label})  {line.strip()}"
                    )
    if forbidden_hits:
        failures.append("Forbidden source patterns:")
        failures.extend(forbidden_hits)

    # 4. Forbidden filenames (qt_compat, qtpy, qt_shim)
    shim_hits: list[str] = []
    for glob in FORBIDDEN_FILES_GLOBS:
        for path in REPO_ROOT.glob(glob):
            if is_excluded(path):
                continue
            rel_path = path.relative_to(REPO_ROOT)
            shim_hits.append(f"  - {rel_path}")
    if shim_hits:
        failures.append("Forbidden shim files exist:")
        failures.extend(shim_hits)

    # 5. PySide6 imports must be present in app entry points
    apps = ["auto_render.py", "cutter.py", "merge.py", "mixer.py"]
    pyside_missing: list[str] = []
    for app in apps:
        path = REPO_ROOT / app
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if "from PySide6" not in text and "import PySide6" not in text:
            pyside_missing.append(f"  - {app} has no PySide6 import")
    if pyside_missing:
        failures.append("Entry points missing PySide6 imports:")
        failures.extend(pyside_missing)

    if failures:
        print("FAIL: repository consistency violations:")
        for line in failures:
            print(line)
        return 1

    print(
        f"PASS: repo consistency clean. "
        f"{len(REQUIRED_FILES)} required files + {len(REQUIRED_DIRS)} "
        f"required dirs present. No PyQt5 residue. No compat shims."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
