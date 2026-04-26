# Tests

End-to-end smoke test outputs and functional coverage logs for 1vmo Suite.

## What belongs here

Evidence of functional behavior — output from running the actual apps or scripted scenarios against them:

- Full-app smoke tests (launches, processes a reference input, produces expected output)
- Per-app e2e runs for auto_render, cutter, merge, mixer
- Regression test logs when a bug is fixed and a reproducer is captured
- Cross-platform runs once Linux/macOS support lands

## What does NOT belong here

- Performance or quality numbers — those go in `benchmarks/`.
- Unit test source code — that lives alongside the module being tested (conventional pytest layout).
- CI run artifacts not tied to a changelog entry.

A log belongs here **only if a changelog entry references it.** Otherwise it's noise.

## Naming convention

```
<test-name>-YYYYMMDD.log
<test-name>-YYYYMMDD.md
```

- Compact date (no dashes inside the date) to keep filenames shorter.
- Test name is lowercase hyphenated: app or scenario, optionally scoped.
- `.log` for raw tool output, `.md` for curated summaries with context.

Examples:
- `e2e-cutter-20260418.log`
- `smoke-all-apps-20260420.md`
- `regression-merge-audio-dropout-20260502.log`

## Content expectations

At minimum, a test log should make it possible to tell:

- What was run (commands, config file paths, input assets)
- What version / commit was under test
- Pass/fail outcome per scenario
- For failures: the actual vs. expected behavior

## Referenced from CHANGELOG.md as

`[tests/e2e-cutter-20260418.log]`

## Smoke runner convention

Smoke runners live in `tools/` and follow a consistent shape so a
reader can understand any new runner by analogy with existing ones.

Naming:
- `tools/check_*.py` — read-only validation (e.g.,
  `check_encoder_schema.py`, `check_user_data.py`,
  `check_preset_ids.py`).
- `tools/test_*.py` — round-trip + assertion (e.g.,
  `test_user_save.py`, `test_id_migration.py`,
  `test_integration_smoke.py`, `test_encoder_json_determinism.py`).

Output shape:
- First line: `=== <name> smoke (sub-phase X) ===`
- Per-test block: `[<test-name>]\n  PASS: <details>` or
  `  FAIL: <details>`.
- Last line: `=== N/M tests passed ===` then `PASS: ...` or `FAIL`.
- Exit 0 on all PASS, 1 on any FAIL.

Conventions:
- Tempdir-isolated. Smoke must NOT mutate repo state.
- Read-only on `assets/`. Use `tempfile.TemporaryDirectory()` for
  any write work.
- `PYTHONIOENCODING=utf-8` prepended at invocation when the runner
  prints non-ASCII (emoji, accented characters).
- Aggregate runner: `tools/run_all_smoke.py` runs every runner and
  exits non-zero if any fail. Manual-run only (NOT a pre-commit
  hook per ADR-0001).

When adding a new sub-phase:
- Author runner(s) in `tools/` matching the conventions above.
- Capture log to `tests/smoke-<sub-phase>-<scenario>-YYYYMMDD.log`.
- Cite the log in `CHANGELOG.md` per the project's changelog rules.
- Add the runner to the `RUNNERS` list in
  `tools/run_all_smoke.py` so future regression checks include it.
