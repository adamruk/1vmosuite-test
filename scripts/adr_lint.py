#!/usr/bin/env python3
"""Custom ADR linter for 1vmo-suite governance docs.

Checks:
  1. Required header fields present (Status, Date, Decision makers).
  2. Status value is in allowed set (Proposed, Accepted, Deprecated, Superseded).
  3. First inline date in Status section matches Date field exactly.
  4. Filename matches ADR-NNNN-kebab-title.md pattern.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ALLOWED_STATUS = {"Proposed", "Accepted", "Deprecated", "Superseded"}
FILENAME_PATTERN = re.compile(r"^ADR-\d{4}-[a-z0-9-]+\.md$")
STATUS_PATTERN = re.compile(
    r"^\*?\*?Status:\*?\*?\s*(.+?)$", re.MULTILINE | re.IGNORECASE
)
DATE_PATTERN = re.compile(
    r"^\*?\*?Date:\*?\*?\s*(\d{4}-\d{2}-\d{2})", re.MULTILINE | re.IGNORECASE
)
DECISION_MAKERS_PATTERN = re.compile(
    r"^\*?\*?Decision makers:\*?\*?\s*(.+?)$", re.MULTILINE | re.IGNORECASE
)
INLINE_DATE_PATTERN = re.compile(r"\((\d{4}-\d{2}-\d{2})\)")


def lint_adr(path: Path) -> list[str]:
    violations: list[str] = []

    if not FILENAME_PATTERN.match(path.name):
        violations.append("Filename does not match ADR-NNNN-kebab-title.md pattern")

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        violations.append(f"Cannot read file: {exc}")
        return violations

    status_match = STATUS_PATTERN.search(content)
    date_match = DATE_PATTERN.search(content)
    decision_makers_match = DECISION_MAKERS_PATTERN.search(content)

    if not status_match:
        violations.append("Missing required field: Status")
    if not date_match:
        violations.append("Missing required field: Date")
    if not decision_makers_match:
        violations.append("Missing required field: Decision makers")

    if status_match:
        status_value = status_match.group(1).strip()
        first_word_match = re.match(r"([A-Za-z]+)", status_value)
        first_word = first_word_match.group(1) if first_word_match else ""
        if first_word not in ALLOWED_STATUS:
            violations.append(
                f"Status value '{first_word}' not in allowed set: "
                f"{sorted(ALLOWED_STATUS)}"
            )

    if status_match and date_match:
        status_value = status_match.group(1)
        date_value = date_match.group(1)
        inline_dates = INLINE_DATE_PATTERN.findall(status_value)
        if inline_dates and inline_dates[0] != date_value:
            violations.append(
                f"Inline status date {inline_dates[0]} does not match "
                f"Date field {date_value}"
            )

    return violations


def main(argv: list[str]) -> int:
    if not argv:
        return 0
    exit_code = 0
    for arg in argv:
        path = Path(arg)
        violations = lint_adr(path)
        if violations:
            exit_code = 1
            print(f"{path}:")
            for v in violations:
                print(f"  - {v}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
