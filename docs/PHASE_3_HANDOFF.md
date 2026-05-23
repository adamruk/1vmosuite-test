# Phase 3 Handoff

**Milestone:** Phase 3 (queue, scoring, optimization, orchestration, encoder intelligence, packaging) closed.
**Date:** 2026-05-22
**Built from:** see `SOURCE/git-commit-hash.txt` in the handoff zip.

## What shipped in Phase 3

| Sub-phase | Status                | Surface                                                                                          |
|-----------|------------------------|--------------------------------------------------------------------------------------------------|
| 3.1       | SHIPPED (code + tests) | Persistent local queue with crash recovery + resume prompt + Settings toggle.                    |
| 3.2       | SHIPPED (code + tests) | Local VMAF / SSIM / PSNR / pHash scoring; auto-score default OFF.                                |
| 3.3       | SHIPPED (code + tests) | Optimization / recommendation engine + 🩺 Health dialog + Confirm-only re-render.                |
| 3.4       | SHIPPED (code + tests) | Pause/Resume, scheduler policies, retry policy, per-task log + rotation, diagnostic bundle export, sleep inhibitor, system monitor. |
| 3.5       | SHIPPED (code + tests) | Encoder intelligence (preset classifier, compatibility checker, fallback planner). Module-only this pass; UI wiring deferred. |
| 3.6       | SHIPPED (scripts + ADR)| Build scripts + integrity checker + VERSION.txt flow + ADR-0013. Real artifact production happens on Adam's host (sandbox limitation). |
| 3.7       | THIS DOCUMENT          | Closure + handoff.                                                                               |

## Where state lives

All user data is local. Nothing is sent anywhere:

- `USER_DATA_DIR/config_video_renderer.json`  — Settings.
- `USER_DATA_DIR/queue.json`                 — Phase 3.1 batch persistence.
- `USER_DATA_DIR/queue.json.bak`             — single-generation atomic-write rotation.
- `USER_DATA_DIR/scores.json`                — Phase 3.2 score cache.
- `USER_DATA_DIR/queue_state.json`           — Phase 3.4 pause/resume + scheduler policy + per-task priorities + retry counters.
- `USER_DATA_DIR/logs/<batch>/<task>.log`    — Phase 3.4 per-task ffmpeg logs.
- `USER_DATA_DIR/logs/index.json`            — Phase 3.4 rotation manifest.
- `USER_DATA_DIR/encoder.user.json`          — user-authored presets.

`USER_DATA_DIR` resolves via `core/user_data.resolve_or_die` to:
- Windows: `%LOCALAPPDATA%\1vmo-suite`
- macOS:   `~/Library/Application Support/1vmo-suite`
- Linux:   platformdirs default
- Portable mode: sibling of the .exe when `portable.txt` is present.

## Upgrade-immune contract

Every Phase 3.x file is schema-versioned with a never-raises load. A downgrade to a pre-Phase-3 build leaves these files inert on disk; the next launch ignores them. A schema bump in a future version makes the old code's `load()` return None — the user starts clean, no corruption.

## How to roll back

See `PHASE_3_ROLLBACK.md` for the three paths (updater-side, per-phase repo-side, schema-side).

## How to build the release artifacts

See `RELEASE_WINDOWS.md` (manual recipe — CLAUDE.md §12 rules) and `RELEASE_MACOS.md`. Phase 3.6's `tools/build/build_windows.py` + `tools/build/build_macos.py` automate the steps; sandbox could not produce real artifacts and they are deferred to Adam's host machines.

## How to verify the handoff

1. Extract the zip.
2. Open `DOCS/PHASE_3_RC_CHECKLIST.md` — every category-A source-gate row should be `[PASS]`. Hardware-dependent rows are `[N]` with reason — Adam fills these in on his host.
3. Open `EVIDENCE/phase3-validation-2026-05-22.log` — confirms the source gates passed in the sandbox.
4. SHA256 the BUILD artifacts against `BUILD/checksums.txt`.
5. Optional: `python3 tools/build/check_release_integrity.py <bundle>` for any artifact in BUILD/.

## Open known issues

| ID    | Severity | Description                                                                                       |
|-------|----------|---------------------------------------------------------------------------------------------------|
| B-014 | HIGH     | `_reload_config_settings` refreshes only some keys; remaining `num_threads / show_ffmpeg_command / open_output_when_done` still need an app restart. (Open since v2.5.1.) |
| B-018 | MEDIUM   | Edit/Delete buttons grayed for ALL presets in a fresh install (ADR-0006 bootstrap problem). Tooltip enrichment is the lowest-risk fix. |
| 3.5-UI | LOW    | Phase 3.5 encoder intelligence module exists; the Start-time pre-flight compatibility gate (UI flow B in the design doc) is not yet wired. |
| 3.6-spec | LOW  | `1vmo-suite.spec` not edited to embed VERSION.txt via `datas=`. Currently the build script copies VERSION.txt post-build. Cleaner: in-spec datas. |
| 3.6-updater | MEDIUM | `updater.py` SHA256-verify + `_pending/` extract + backup-before-swap is documented in ADR-0013 D5 but not yet wired in the updater hot path. |

None of these block shipping the Phase 3 milestone. They are tracked in `BACKLOG.md` and follow-up patches.

## Phase 4 readiness

See `PHASE_4_READINESS_NOTES.md` — observations only. No Phase 4 design.
