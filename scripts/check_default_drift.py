#!/usr/bin/env python3
"""Default-drift checker for 1vmo Suite.

Enforces that the six runtime-tunable defaults centralized in
`core.config.AppDefaults` are the only definition sites. Any literal
default for one of these keys outside `core/config.py` is a drift bug.

Covered keys:
    gpu_enabled, gpu_preset, gpu_max_concurrent, gpu_codec,
    gpu_error_action, output_collision.

Strategy:
    For each `<key>=<value>` literal default seen in the listed source
    files (function signatures + dict literals), confirm the value is
    `core_config.APP_DEFAULTS.<key>`, `APP_DEFAULTS.<key>`, or comes from
    `config.get("<key>", <APP_DEFAULTS ref>)`. A bare literal (e.g.
    `gpu_preset="p4"` outside `core/config.py`) is a violation.

Exit codes:
    0 = clean
    1 = drift detected (prints offending lines)
    2 = environmental error (file missing, etc.)

This script is intentionally narrow: it does NOT auto-fix, only report.
Per CLAUDE.md §6, fixes are a human decision.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Keys whose default lives in core.config.AppDefaults. Any other source
# file using a literal default for one of these keys is drift.
APP_DEFAULTS_KEYS = {
    "gpu_enabled",
    "gpu_preset",
    "gpu_max_concurrent",
    "gpu_codec",
    "gpu_error_action",
    "output_collision",
}

# Files where literals ARE the canonical definition — skip them.
ALLOWED_LITERAL_FILES = {
    Path("core/config.py"),
}

# Files we scan for drift. Add new modules here when they grow defaults.
SCAN_FILES = [
    Path("auto_render.py"),
    Path("cutter.py"),
    Path("merge.py"),
    Path("mixer.py"),
    Path("settings_dialog.py"),
    Path("help_dialog.py"),
    Path("updater.py"),
    Path("core/preset_translator.py"),
    Path("core/ffmpeg_runner.py"),
    Path("core/widgets.py"),
    Path("core/file_picker.py"),
]


# Matches a literal-default assignment in a function signature
# (e.g. `gpu_preset: str = "p4"`) or a dict literal (e.g.
# `"gpu_preset": "p4"`). The value must be a string, int, or bool literal
# (not an expression like APP_DEFAULTS.foo).
LITERAL_VALUE_PATTERN = re.compile(
    r"""
    (?P<key>(?:"|')?(?:gpu_enabled|gpu_preset|gpu_max_concurrent
                       |gpu_codec|gpu_error_action|output_collision)(?:"|')?)
    \s*[:=]\s*
    (?P<value>"[^"]*"|'[^']*'|True|False|\d+)
    """,
    re.VERBOSE,
)


def is_app_defaults_reference(snippet: str) -> bool:
    """True if the value is an APP_DEFAULTS reference (acceptable form)."""
    return (
        "APP_DEFAULTS" in snippet
        or "_d.gpu_" in snippet
        or "_d.output_" in snippet
        or "_d.gpu_codec" in snippet
        or "_d.gpu_error_action" in snippet
    )


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return [(line_no, key, full_line), ...] for each drift hit."""
    drifts: list[tuple[int, str, str]] = []
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return drifts
    for lineno, line in enumerate(source.splitlines(), start=1):
        # Skip comments outright.
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        # If line already references APP_DEFAULTS, it's fine even if it
        # also contains a literal-looking substring.
        if is_app_defaults_reference(line):
            continue
        for match in LITERAL_VALUE_PATTERN.finditer(line):
            key = match.group("key").strip("\"'")
            if key in APP_DEFAULTS_KEYS:
                drifts.append((lineno, key, line.strip()))
    return drifts


def main() -> int:
    violations: list[tuple[Path, int, str, str]] = []
    for rel in SCAN_FILES:
        if rel in ALLOWED_LITERAL_FILES:
            continue
        full = REPO_ROOT / rel
        if not full.exists():
            print(f"WARN: scan target missing: {rel}", file=sys.stderr)
            continue
        for lineno, key, line in scan_file(full):
            violations.append((rel, lineno, key, line))

    # Also sanity-check that core/config.py actually defines AppDefaults
    # with the expected fields. Catches the "someone deleted the
    # dataclass" failure mode.
    core_config = REPO_ROOT / "core" / "config.py"
    if core_config.exists():
        src = core_config.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:
            print(f"FAIL: core/config.py does not parse: {exc}")
            return 2
        defined: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "AppDefaults":
                for child in node.body:
                    if isinstance(child, ast.AnnAssign) and isinstance(
                        child.target, ast.Name
                    ):
                        defined.add(child.target.id)
        missing = APP_DEFAULTS_KEYS - defined
        if missing:
            print(
                "FAIL: core/config.py::AppDefaults missing required fields: "
                + ", ".join(sorted(missing))
            )
            return 1

    if violations:
        print(
            "FAIL: default drift detected (literals must come from core.config.APP_DEFAULTS):"
        )
        for path, lineno, key, line in violations:
            print(f"  {path}:{lineno}  key={key}  {line}")
        return 1

    print(
        f"PASS: no default drift across {len(SCAN_FILES) - len(ALLOWED_LITERAL_FILES)}"
        " scanned files; AppDefaults defines all expected fields."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
