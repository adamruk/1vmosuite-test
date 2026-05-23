# ADR-0014: Phase 3 closure — verification-only mandate

**Status:** Accepted
**Date:** 2026-05-22
**Decision makers:** Adam (project lead)
**Related:** all prior Phase 3 ADRs (0008–0013); cites without revising.

## Context

Phase 3.1 (queue persistence) and Phase 3.2 (local scoring) shipped
working code. Phase 3.3 (optimization), Phase 3.4 (orchestration),
Phase 3.5 (encoder intelligence), and Phase 3.6 (packaging
infrastructure) shipped their core modules + tests in a single
Phase-3 close-out implementation pass. Phase 3.7 closes the
milestone: no new features, no architecture changes, no
RenderWorker edits — only verification and handoff.

## Decision

### D1. Verification-only mandate

Phase 3.7 does NOT touch runtime Python modules (auto_render,
core/*, cutter / merge / mixer, ffmpeg_runner, preset_translator,
queue_models, queue_store, scoring modules, optimization modules,
orchestration modules, encoder_intel modules). It produces docs
+ smoke logs + the handoff bundle. Any defect surfaced during
QA gets fixed in its own patch / phase, not in 3.7.

### D2. Conditional handling for unshipped designs

Where a Phase 3.3 / 3.4 / 3.5 / 3.6 design row reached production
code by RC time, the matrix in `docs/PHASE_3_RC_CHECKLIST.md`
runs it. Where it didn't, the row is marked `[N]` with a written
reason. Faked `[PASS]` is forbidden per CLAUDE.md §2 + AGENTS.md
§2.1.

### D3. Sandbox limitations recorded honestly

The implementation pass ran in a Linux sandbox without
Windows / macOS / NVIDIA hardware. The Phase 3.7 RC checklist
columns for "Real Windows .exe build", "Real macOS .app/.dmg
build", "NVENC end-to-end render", "Driver-floor warning", and
"Updater backup-before-swap" are pre-marked `[N]` until Adam
runs them on his host machines. The deliverable explicitly
flags these as host-side QA, not omitted-for-time.

### D4. ADR-0014 supersedes nothing

It cites ADR-0001 (narrow pytest), ADR-0003 (narrow extension),
ADR-0008 (VMAF thresholds), ADR-0009 (scoring), ADR-0010
(optimization), ADR-0011 (orchestration), ADR-0012 (encoder
intelligence), ADR-0013 (packaging) without revising any.

### D5. Handoff bundle is the canonical artifact

`1vmo-phase3-handoff-vX.Y.Z-<date>.zip` contains: BUILD/ (real
artifacts when produced on host), DOCS/ (handoff README +
checklist + rollback runbook + release notes + readiness notes +
all ADRs), EVIDENCE/ (smoke logs + ruff/pytest output + ADR-0008
VMAF JSON when available), SOURCE/ (git commit hash + git
archive snapshot), and PHASE_4_READINESS_NOTES.md (observations,
no design).

### D6. Phase 4 stays parked

Phase 4's encoder plugin architecture is out of scope. The
readiness notes capture friction observed during Phase 3
without making any Phase 4 decisions.

## Consequences

- 6 new docs under `docs/` (handoff, RC checklist, rollback,
  release notes, Phase 4 readiness, this ADR).
- 0 Python files modified.
- CHANGELOG / BACKLOG / ROADMAP entries closing the milestone.

## Rollback

Phase 3.7 is documentation-only; rollback = delete the new
docs/ files and revert the closing CHANGELOG/BACKLOG/ROADMAP
hunks. The handoff zip is external to the repo; it can be
re-cut at any time from the same source.
