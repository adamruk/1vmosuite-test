#!/usr/bin/env python3
"""ADR reference checker for 1vmo Suite.

Every `ADR-NNNN` reference in source, docs, CHANGELOG, or BACKLOG must
correspond to an actual file in `docs/decisions/`. Catches the
"cited a fabricated ADR" failure mode (e.g. Phase A's spurious
ADR-0008 fix-2 / p5 citation).

Scans:
    *.py        — comments and docstrings
    *.md        — docs/decisions/, root governance files, CHANGELOG/BACKLOG

Exit codes:
    0 = clean
    1 = at least one orphan ADR reference
    2 = environmental error

Distinct from `scripts/adr_lint.py`, which validates the format of
ADR files themselves (Status, Date, filename pattern).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = REPO_ROOT / "docs" / "decisions"

# Matches "ADR-0001" through "ADR-9999" with word boundaries.
ADR_REF_PATTERN = re.compile(r"\bADR-(\d{4})\b")

# Files we scan. Source = *.py everywhere except .venv/build/dist/docs/external.
# Docs = governance markdown files.
SOURCE_GLOBS = [
    "*.py",
    "core/*.py",
    "tools/*.py",
    "scripts/*.py",
    "tests/**/*.py",
]
DOC_FILES = [
    "CHANGELOG.md",
    "BACKLOG.md",
    "README.md",
    "CLAUDE.md",
    "AGENTS.md",
    "docs/ROADMAP.md",
    "FFMPEG_CPU_TO_NVENC_REFERENCE.md",
    "ONBOARDING.md",
    "URL_DOWNLOADER_SPEC.md",
    "IDEAS_BACKLOG.md",
]
DOC_GLOBS = [
    "docs/*.md",
    "docs/decisions/*.md",
    "benchmarks/*.md",
]

EXCLUDE_PATH_SUBSTRINGS = (
    "/.venv/",
    "/.git/",
    "/__pycache__/",
    "/build/",
    "/dist/",
    "/docs/external/",
    # ADR files may legitimately reference future ADRs in supersession
    # / amendment plans (e.g. ADR-0008 referencing a hypothetical
    # ADR-0009 supersession). Don't scan ADR contents.
    "/docs/decisions/ADR-",
    # This script itself contains the literal "ADR-9999" in a regex
    # comment as a range example; don't self-flag.
    "/scripts/check_adr_references.py",
)


def collect_existing_adrs() -> set[str]:
    """Return the set of ADR numbers (e.g. {'0001', '0002', ...}) that
    have files in docs/decisions/."""
    out: set[str] = set()
    if not ADR_DIR.is_dir():
        return out
    pattern = re.compile(r"^ADR-(\d{4})-")
    for f in ADR_DIR.iterdir():
        if f.is_file() and f.suffix == ".md":
            m = pattern.match(f.name)
            if m:
                out.add(m.group(1))
    return out


def collect_scan_paths() -> list[Path]:
    paths: list[Path] = []
    for glob in SOURCE_GLOBS:
        paths.extend(REPO_ROOT.glob(glob))
    for glob in DOC_GLOBS:
        paths.extend(REPO_ROOT.glob(glob))
    for rel in DOC_FILES:
        p = REPO_ROOT / rel
        if p.is_file():
            paths.append(p)
    # Filter out excluded subtrees + duplicates
    seen: set[Path] = set()
    out: list[Path] = []
    for p in paths:
        p = p.resolve()
        if p in seen:
            continue
        # EXCLUDE_PATH_SUBSTRINGS use forward slashes; on Windows a
        # resolved Path stringifies with "\\", so str(p) substring
        # matching silently fails (B-046) and the script scans — and
        # falsely flags — itself + docs/decisions/ADR-*. Normalize to
        # "/" via as_posix() so the match is path-separator-agnostic.
        if any(sub in p.as_posix() for sub in EXCLUDE_PATH_SUBSTRINGS):
            continue
        seen.add(p)
        out.append(p)
    return out


def main() -> int:
    existing = collect_existing_adrs()
    if not existing:
        print(
            "WARN: docs/decisions/ contains no ADR-NNNN-*.md files. "
            "Skipping reference check.",
            file=sys.stderr,
        )
        return 0

    orphans: list[tuple[Path, int, str, str]] = []  # (path, lineno, ref, line)
    for path in collect_scan_paths():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in ADR_REF_PATTERN.finditer(line):
                num = match.group(1)
                if num not in existing:
                    rel = path.relative_to(REPO_ROOT)
                    orphans.append((rel, lineno, match.group(0), line.strip()))

    if orphans:
        print(
            "FAIL: orphan ADR references (cited but no matching file in docs/decisions/):"
        )
        for path, lineno, ref, line in orphans:
            print(f"  {path}:{lineno}  {ref}  | {line}")
        return 1

    print(
        f"PASS: every ADR reference matches an existing file. "
        f"({len(existing)} ADRs defined: "
        f"{', '.join('ADR-' + n for n in sorted(existing))})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
