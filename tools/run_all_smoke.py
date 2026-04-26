#!/usr/bin/env python3
"""One-command smoke runner aggregator (sub-phase 2c-c-6).

Runs every smoke script in this repo + the pytest exception in
tests/smoke/, captures each exit code, prints a summary, exits 0
only if all pass. NOT a pre-commit hook (manual convenience only).

Per ADR-0001: smoke is manual + observable; this script does NOT
enforce smoke at commit-time, just makes "run them all" one command.

Run from repo root:

  python tools/run_all_smoke.py

Exits 0 on all-PASS, 1 if any FAIL.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

RUNNERS = [
    ("schema (2c-c-1)", ["python", "tools/check_encoder_schema.py"]),
    ("user-data (2c-c-2)", ["python", "tools/check_user_data.py"]),
    ("user-save (2c-c-3)", ["python", "tools/test_user_save.py"]),
    (
        "atomic-retry (2c-c-3)",
        ["python", "-m", "pytest", "tests/smoke/test_atomic_write_retry.py", "-q"],
    ),
    ("preset-ids (2c-c-4)", ["python", "tools/check_preset_ids.py"]),
    ("id-migration (2c-c-4)", ["python", "tools/test_id_migration.py"]),
    ("integration (2c-c-6)", ["python", "tools/test_integration_smoke.py"]),
    ("determinism (2c-c-6)", ["python", "tools/test_encoder_json_determinism.py"]),
    ("hook-changelog", ["python", "tools/test_check_changelog.py"]),
]


def main() -> int:
    print("=== run_all_smoke (sub-phase 2c-c-6) ===")
    print(f"Repo root: {REPO_ROOT}")

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    active_runners = []
    for name, cmd in RUNNERS:
        if cmd[0] == "python" and len(cmd) >= 2 and cmd[1].startswith("tools/"):
            script = REPO_ROOT / cmd[1]
            if not script.exists():
                print(f"  SKIP: {name} (script not present)")
                continue
        active_runners.append((name, cmd))

    print(f"Runners to execute: {len(active_runners)}")
    print()

    results: list[tuple[str, int]] = []
    for name, cmd in active_runners:
        print(f"--- [{name}] ---")
        proc = subprocess.run(cmd, cwd=REPO_ROOT, env=env, capture_output=False)
        results.append((name, proc.returncode))
        status = "PASS" if proc.returncode == 0 else f"FAIL (exit={proc.returncode})"
        print(f"--- [{name}] {status} ---")
        print()

    print("=== AGGREGATE ===")
    for name, ec in results:
        marker = "+" if ec == 0 else "x"
        print(f"  [{marker}] {name}: exit={ec}")
    print()

    failed = [n for n, ec in results if ec != 0]
    if failed:
        print(f"FAIL: {len(failed)} of {len(results)} runners failed:")
        for n in failed:
            print(f"  - {n}")
        return 1
    print(f"PASS: all {len(results)} smoke runners green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
