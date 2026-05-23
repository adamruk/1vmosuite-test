# ADR-0011: Local-only render orchestration / performance layer

**Status:** Accepted
**Date:** 2026-05-22
**Decision makers:** Adam (project lead)
**Related:** Phase 3.1 (queue persistence), ADR-0009 (scoring), ADR-0010 (optimization)

## Context

Phase 3.4 adds pause/resume, retry policy, scheduler policies,
per-task ffmpeg logging, diagnostic bundle export, and a
cross-platform sleep inhibitor. All additions are dispatcher-side
or side-state files — RenderWorker, ffmpeg invocation, and the
Phase 3.1 queue schema stay frozen.

## Decision

### D1. Side-state file, not a queue schema bump

Pause flag, scheduler policy, per-task priorities, and retry
counters all live in `USER_DATA_DIR/queue_state.json` — a new
side file with its own schema_version=1. Phase 3.1's queue.json
schema is FROZEN at v1; a Phase-3.4-unaware build sees the queue
file unchanged.

### D2. Pause means "no new dispatch", never "interrupt"

The pause flag is consulted by `_start_next_task` at entry. Any
task already running on a worker keeps going. Cancel still works
as before for hard interruption.

### D3. Retry is strict-opt-in

`RetryPolicyConfig` defaults to `enabled=False` and
`max_retries_per_task=0`. `decide_retry` returns NONE unless the
user has explicitly opted in. Even then, the allow-list of
retry-eligible RecommendationKinds is small (RETRY_AS_IS,
USE_CPU) and a hard per-batch ceiling caps runaway loops.

### D4. Sleep inhibitor degrades silently

Per-platform implementation (Windows SetThreadExecutionState,
macOS caffeinate, Linux systemd-inhibit). Missing platform tools
return False from `acquire()` with a log warning; the render
keeps running, just without sleep prevention. Default OFF.

### D5. psutil is optional

The system monitor imports psutil lazily; if absent, every probe
returns None. pynvml (already a Phase 2d dep) is used for GPU
temperature, also wrapped in try/except. Phase 3.4 does not
introduce psutil as a hard dependency in this implementation
pass — the system-monitor surface degrades gracefully.

### D6. Per-task log retention via manifest

`logs/index.json` (its own schema_version=1) tracks the last N
batch directories. Each task log is bounded at 8 MB. Rotation
happens at `end_batch()`. Older batches are removed via
`shutil.rmtree` after the manifest is updated.

### D7. Diagnostic bundle sanitizes config

`export_diagnostic_zip` strips the user's `output_dir` to
`<redacted>` and reduces `input_files` to basenames before
inclusion. The bundle is meant for sharing; leaking absolute
paths is avoided.

### D8. ADR-0003 narrow-pytest extension

Phase 3.4 smoke tests for scheduler / retry policy / queue state /
task logger / diagnostic bundle are pure-Python (no Qt, no
ffmpeg). Deterministic, <2s. ADR-0011 extends the narrow exception.

## Consequences

- New package `core/orchestration/` (8 modules).
- 5 new smoke tests (33 cases).
- New side file `queue_state.json` in `user_data_dir`.
- New `logs/` directory in `user_data_dir`.
- Two new toolbar actions (Pause/Resume, Diagnostics).
- No new mandatory dependency; psutil optional, pynvml already present.
- RenderWorker, ffmpeg invocation, queue_models, scoring modules: untouched.

## Rollback

1. Delete `core/orchestration/`, the 5 new smoke test files, and
   ADR-0011.
2. Revert auto_render.py hunks: Pause/Diagnostics buttons,
   `_toggle_pause`, `_open_diagnostics_export`, `is_paused`
   init, dispatcher pause guard.
3. Optionally clear `queue_state.json` and `logs/` from
   user_data_dir (the next launch ignores them anyway).
