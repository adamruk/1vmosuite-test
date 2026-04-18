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
