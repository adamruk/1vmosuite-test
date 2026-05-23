# ADR-0012: Local-only encoder intelligence layer

**Status:** Accepted
**Date:** 2026-05-22
**Decision makers:** Adam (project lead)
**Related:** ADR-0007 (GPU pipeline), ADR-0008 (VMAF thresholds),
ADR-0009 (scoring), ADR-0010 (optimization), ADR-0011 (orchestration)

## Context

Phase 3.5 introduces an advisory layer that classifies presets,
checks them against the user's GPU capability snapshot, and
proposes ranked fallback chains when a preset wouldn't run.
Pure-Python heuristics; no ffmpeg shell-out from the analyzer/
fallback path; no automated codec switching.

## Decision

### D1. Pure-function classification + verdict

`classify_preset(preset_id, params)` scans the ffmpeg arg list for
codec sentinel tokens (`h264_nvenc`, `hevc_nvenc`, `av1_nvenc`,
`libx264`, `libx265`) and returns a `PresetClassification`.
`compatibility_check(classification, gpu_caps, gpu_enabled)`
returns a `CompatibilityVerdict` with severity `INFO / WARN /
BLOCK`.

### D2. Advisory only — no auto-switching

Every BLOCK verdict surfaces `suggested_fallback_codec`; the
user reviews the verdict in the existing Phase 3.3
RecommendationDialog and clicks Confirm before any preset change
is applied. No code path auto-mutates the user's preset
selection.

### D3. gpu_caps is read-only

The analyzer takes an arbitrary object with documented
attribute names (`h264_available`, `hevc_available`,
`av1_available`, `nvenc_session_cap`, `driver_version`,
`gpu_generation`). This decouples it from gpu_detect's exact
shape — a future Phase 3.5.x extension to gpu_detect can add
fields without breaking the analyzer.

### D4. Fallback planner ranks alternatives

`plan_fallback(failing_codec, gpu_caps, gpu_enabled,
history_codec_failures)` returns a `FallbackPlan` with ordered
`FallbackStep`s. History-aware: codecs with many recent failures
(from QueueStore + ScoreCache aggregation) get demoted or
removed from the chain.

### D5. ADR-0003 narrow-pytest extension

All Phase 3.5 tests are pure-Python over fake `gpu_caps`
objects. No real ffmpeg shell-out, no GPU probe, no Qt.
Deterministic, <1s.

### D6. Real probe-encodes deferred

The design proposed a 1-frame `ffmpeg testsrc` probe-encode per
codec to confirm runtime availability beyond the `-encoders`
text scan. This implementation does NOT run that probe at
runtime — it's a future enhancement that needs real NVIDIA
hardware in a CI environment to validate. The current analyzer
trusts the existing gpu_detect fields; a stripped or
mis-detected build can be diagnosed via the Phase 3.4
diagnostic bundle.

## Consequences

- New package `core/encoder_intel/` (4 modules, ~650 LOC).
- One new smoke test file (17 cases).
- No new runtime dependency.
- RenderWorker, ffmpeg invocation, queue / score / optimization /
  orchestration: all untouched.

## Rollback

1. Delete `core/encoder_intel/`, `tests/smoke/test_encoder_intel.py`,
   and this ADR.
2. No app-side wiring change to revert (Phase 3.5 ships the
   module without auto_render integration this pass — the
   intelligence is callable by Phase 3.3's dialogs but not
   forced into the Start path).
