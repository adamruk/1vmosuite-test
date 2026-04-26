#!/usr/bin/env python3
"""CHANGELOG enforcement: block commits that change source files without
a corresponding CHANGELOG.md edit.

Pre-commit framework variant of .claude/hooks/check-changelog.sh
(defense-in-depth — D1=a). Fires on every git commit, regardless of
whether Claude Code or a direct terminal initiates it.

Stage: commit-msg.
Bypass: [skip changelog] anywhere in commit message body.
Always-passes: if CHANGELOG.md is in the staged diff, OR if the
               commit is a merge commit, OR if no source files are
               staged at all.

Source-file classification (D2): see SOURCE_PATTERNS below.

Error model (D4): fail-open on environmental confusion (git missing,
merge commit, message file missing). Fail-closed on actual rule
violations.

Per CLAUDE.md §4 — every commit that adds tooling, creates user-visible
files, or changes behavior must include a CHANGELOG.md entry.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# D2 SOURCE patterns — match a staged path = trigger the rule.
SOURCE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^auto_render\.py$"),
    re.compile(r"^cutter\.py$"),
    re.compile(r"^merge\.py$"),
    re.compile(r"^mixer\.py$"),
    re.compile(r"^bench\.py$"),
    re.compile(r"^updater\.py$"),
    re.compile(r"^help_dialog\.py$"),
    re.compile(r"^gpu_detect\.py$"),
    re.compile(r"^core/.*\.py$"),
    re.compile(r"^tools/.*\.py$"),
    re.compile(r"^scripts/.*\.py$"),
    re.compile(r"^\.claude/hooks/.*\.sh$"),
    re.compile(r"^requirements\.txt$"),
    re.compile(r"^assets/Encoder\.(txt|json)$"),
    re.compile(r"^tests/smoke/test_.*\.py$"),
    re.compile(r"^tests/repro/.*\.py$"),
]

CHANGELOG_PATH = "CHANGELOG.md"
BYPASS_MARKER = "[skip changelog]"


def is_source(path: str) -> bool:
    return any(p.match(path) for p in SOURCE_PATTERNS)


def get_staged_paths() -> list[str] | None:
    """Return list of staged paths via git diff --cached --name-only.

    Returns None on git invocation failure (D4: fail-open on env confusion).
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main(argv: list[str]) -> int:
    # D4: fail-open if commit-msg file path is missing
    if len(argv) < 2:
        print(
            "check_changelog: no commit-msg file path passed; passing.",
            file=sys.stderr,
        )
        return 0

    msg_file = Path(argv[1])
    try:
        msg = msg_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        print(
            f"check_changelog: cannot read {msg_file}; passing.",
            file=sys.stderr,
        )
        return 0

    # D4: bypass marker (anywhere in message)
    if BYPASS_MARKER in msg:
        return 0

    # D4: merge commit (env confusion-class fail-open)
    if msg.lstrip().startswith("Merge "):
        return 0

    # Get staged files (D4: fail-open on git failure)
    staged = get_staged_paths()
    if staged is None:
        print(
            "check_changelog: git diff --cached failed; passing.",
            file=sys.stderr,
        )
        return 0

    # CHANGELOG.md staged → pass
    if CHANGELOG_PATH in staged:
        return 0

    # Find source files in staged set
    source_hits = [p for p in staged if is_source(p)]
    if not source_hits:
        return 0

    # Block (D4: fail-closed on actual rule violations)
    print("=" * 70, file=sys.stderr)
    print("CHANGELOG enforcement: commit BLOCKED.", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "Source file(s) changed but CHANGELOG.md is not in the staged diff:",
        file=sys.stderr,
    )
    for p in source_hits:
        print(f"  - {p}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "Per CLAUDE.md §4: every commit that adds tooling, creates",
        file=sys.stderr,
    )
    print(
        "user-visible files, or changes behavior must include a",
        file=sys.stderr,
    )
    print("CHANGELOG.md entry.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Resolve by:", file=sys.stderr)
    print("  (a) Stage a CHANGELOG.md edit:", file=sys.stderr)
    print("      git add CHANGELOG.md", file=sys.stderr)
    print("      (then retry the commit)", file=sys.stderr)
    print(
        "  (b) Bypass for pure internal refactor / non-behavior change:",
        file=sys.stderr,
    )
    print(
        "      add the literal string [skip changelog] to the commit",
        file=sys.stderr,
    )
    print(
        "      message body, then amend / retry the commit.",
        file=sys.stderr,
    )
    print("=" * 70, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
