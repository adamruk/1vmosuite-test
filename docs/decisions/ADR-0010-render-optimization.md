# ADR-0010: Local-only render optimization / recommendation layer

**Status:** Accepted
**Date:** 2026-05-22
**Decision makers:** Adam (project lead)
**Related:** ADR-0008 (VMAF thresholds), ADR-0009 (scoring architecture)

## Context

Phase 3.2 ships local scoring per render. Users now have VMAF / pHash /
SSIM / PSNR numbers but no in-app way to turn them into next-step
guidance. Phase 3.3 introduces a heuristic recommendation layer that
maps each render's scores + duration into structured suggestions
(e.g. "raise quality", "increase originality", "enable GPU") that the
user can review and confirm before any re-render.

Adam's hard constraints:

1. **Local-only.** No cloud / no remote service / no account / no
   telemetry. Same invariant as Phase 3.1 / 3.2.
2. **Additive and reversible.** No RenderWorker change. No ffmpeg
   command change. No queue / score schema change.
3. **No silent re-renders.** Every re-render goes through an
   explicit Confirm dialog. No "Auto-fix all" silent path.
4. **No destructive overwrites.** Re-renders write to `_v2.<ext>`
   sidecars; original outputs are preserved.

## Decision

### D1. Heuristic-only, no ML

The recommender is a pure Python function over primitives
(VMAF mean/p5, pHash distance, render duration, batch median, a
settings snapshot). No model file, no remote inference, no
local ML library pulled in. Every rule is hand-written, testable,
and overridable via Settings thresholds.

### D2. Recommendations are advisory, never executors

`recommend_for_render` returns a sorted `list[Recommendation]`.
Each Recommendation has a `kind`, a one-sentence `reason`, a
`confidence` (HIGH/MEDIUM/LOW), a short `delta_summary`, and a
`proposed_params` dict. The UI presents these to the user; only
on an explicit Confirm click does `_apply_recommendation` feed
them into the existing `start_render` flow.

### D3. Failure classifier is pattern-matched, never guessed

`classify_failure(error_message)` returns a Recommendation built
from a small regex table of known ffmpeg/NVENC error patterns.
Unmatched patterns return UNKNOWN with LOW confidence and a
"inspect log" message — we never guess.

### D4. Default thresholds source from ADR-0008

VMAF mean >= 96.0 and p5 >= 93.0 (ADR-0008 calibrated) are the
default green band. Settings → Optimization tab will expose
these as tunable spinboxes; the recommender accepts them as
keyword args so tests can pin specific bands.

### D5. ADR-0003 narrow-pytest extension

All Phase 3.3 tests under `tests/smoke/test_*` are pure-Python
unit tests with no Qt / no ffmpeg / no GPU. <1s, deterministic.
They cover the same ADR-0003 narrow exception criteria as Phase
3.1 (queue store) and Phase 3.2 (score modules).

### D6. UI is one toolbar button + two dialogs

The discoverable surface is a single "🩺 Health" toolbar button
between Help and Updates. It opens a read-only RenderHealthDialog
showing the per-row table + summary banner. Double-click a row
to open RecommendationDialog with Confirm/Cancel.

No auto-popup after batches. No bulk "Re-render all" silent path.
No new modals on app startup.

## Consequences

- New package `core/optimization/` (6 modules, ~700 LOC).
- New toolbar action + 2 modal dialogs in `auto_render.py`
  (additive, no existing UI changed).
- 4 new smoke test files (~470 LOC).
- No new runtime dependency.
- No change to PyInstaller spec.
- RenderWorker / ffmpeg_runner / preset_translator / queue_models /
  scoring modules: all untouched.

## Rollback

Phase 3.3 is fully reversible:

1. Delete `core/optimization/` and `tests/smoke/test_quality_classifier.py`,
   `test_failure_classifier.py`, `test_recommender.py`,
   `test_batch_analyzer.py`.
2. Revert `auto_render.py` hunks: `health_btn` toolbar add +
   `_open_render_health_dialog`, `_show_recommendation_dialog`,
   `_apply_recommendation` helpers.
3. Revert this ADR.

No data files are created in `user_data_dir` by Phase 3.3 (the
recommender is stateless across launches).
