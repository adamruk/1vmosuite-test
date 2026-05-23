# Phase 3 Rollback Runbook

Three independent rollback paths. All are non-destructive.

## R1 — Updater-side rollback (per-machine, user-facing)

Use when a user's installation behaves badly after an update and you want to revert to the prior version.

Pre-Phase-3.6 hardening (still the case today):
1. Close the app.
2. Open the install folder (the one containing `1vmo Auto Render vX.Y.Z.exe`).
3. Rename the current folder aside (e.g., `1vmo-broken`).
4. Locate the prior version's zip you downloaded before the update — extract it.
5. Relaunch.

Phase 3.6 designed (NOT YET WIRED into `updater.py` — see ADR-0013 D5):
- Backup-before-swap: every successful update will leave a `_backup_<ts>/` sibling next to the new install. Rollback = rename `_backup_<ts>` over the new install. The 7-day retention prompt protects against premature deletion.

**user_data_dir is upgrade-immune.** Phase 2c-c-3 (CHANGELOG anchor `[5fc1dc7]`) moved every Phase 3.x state file (queue.json / scores.json / queue_state.json / encoder.user.json / etc.) into platformdirs. A rollback never corrupts those files; the older code's `load()` either reads them cleanly (same schema_version) or rejects with a logged warning (different version) and starts clean.

## R2 — Per-phase repo-side rollback (developer-facing)

Each Phase 3.x sub-phase is additive and reversible:

### Phase 3.1 rollback
Delete `core/queue_models.py`, `core/queue_store.py`, `tests/smoke/test_queue_store.py`. Revert auto_render.py hunks (queue init in `__init__`, lifecycle wiring in `start_render` / `_start_next_task` / `on_render_completed` / `on_render_error` / `cancel_render` / `closeEvent`, 8 helper methods). Revert settings_dialog.py queue-persistence checkbox. Orphan `queue.json` on disk is inert under the rolled-back build.

### Phase 3.2 rollback
Delete `core/scoring/*` (7 files), `tests/smoke/test_score_*.py`, `tests/smoke/test_capabilities.py`, `tests/smoke/test_phash_runner.py`. Revert auto_render.py scoring helpers + ScoreWorker class + 3 tree_output columns + right-click menu. Revert settings_dialog.py Scoring tab. Orphan `scores.json` is inert.

### Phase 3.3 rollback
Delete `core/optimization/*` (6 files), `tests/smoke/test_quality_classifier.py`, `tests/smoke/test_failure_classifier.py`, `tests/smoke/test_recommender.py`, `tests/smoke/test_batch_analyzer.py`. Revert auto_render.py hunks (`health_btn`, `_open_render_health_dialog`, `_show_recommendation_dialog`, `_apply_recommendation`). No user_data_dir state to clean.

### Phase 3.4 rollback
Delete `core/orchestration/*` (8 files), `tests/smoke/test_scheduler.py`, `tests/smoke/test_retry_policy.py`, `tests/smoke/test_queue_state.py`, `tests/smoke/test_task_logger.py`, `tests/smoke/test_diagnostic_bundle.py`. Revert auto_render.py hunks (Pause/Diagnostics buttons + helpers + `is_paused` init + dispatcher pause guard). Orphan `queue_state.json` and `logs/` directory are inert.

### Phase 3.5 rollback
Delete `core/encoder_intel/*` (4 files), `tests/smoke/test_encoder_intel.py`. No auto_render.py wiring to revert (module-only ship).

### Phase 3.6 rollback
Delete `tools/build/*` (4 scripts). No runtime app behavior change — Phase 3.6 ships only dev tooling.

In every case: revert the corresponding CHANGELOG.md / BACKLOG.md / docs/decisions/ADR-XXXX-*.md.

## R3 — Schema rollback (data-side)

Phase 3 files on disk that survive a downgrade:
- queue.json (Phase 3.1) — `schema_version=1`
- scores.json (Phase 3.2) — `schema_version=1`
- queue_state.json (Phase 3.4) — `schema_version=1`
- logs/index.json (Phase 3.4) — `schema_version=1`

Every loader follows the same contract: file missing → None; JSON corrupt → None + log warning; schema_version mismatch → None + log warning. The next launch in the rolled-back build starts clean. No file is ever transformed in place; we never migrate a v1 file into a hypothetical v2 layout. The schema-version-reject path is the rollback path.

## What is NOT a rollback path

- **Deleting `USER_DATA_DIR` entirely.** Users would lose their custom presets (`encoder.user.json`), their Settings, and their render history. Use R1 instead.
- **Editing schema_version by hand.** Don't. The reject path is correct behavior; a hand-edited file will fail validation and confuse the next attempt.
- **Renaming the install dir while the app is running.** Always close the app first.

## Verification after rollback

1. Launch the rolled-back build. Confirm window appears, no crash.
2. Render a 1-task batch. Confirm output file is correct.
3. Open Settings. Confirm values match expectations.
4. Optional: `python3 tools/build/check_release_integrity.py <bundle>` against the rolled-back artifact.
5. If R1 used: confirm `_backup_<ts>/` (when present) was properly preserved.
