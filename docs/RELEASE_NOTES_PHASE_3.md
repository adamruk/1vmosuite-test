# 1vmo Auto Render — Release Notes (Phase 3)

**Date:** 2026-05-22

Phase 3 is a major closure milestone. Six sub-phases of work shipped a stack of features that make long-form video rendering safer, more measurable, and easier to recover from. All of it runs on your own computer — no cloud, no login, no remote analysis, no telemetry.

## Headline features

### Crash-safe queue + resume
If a render batch is interrupted — crash, hard quit, power loss, or you intentionally closed the app mid-batch — the next launch offers to pick up where you left off. The original output files are preserved; only the unfinished tasks re-run. You can disable the feature in Settings → Advanced if you prefer the old behaviour.

### Local scoring per render
Right-click any finished row in the output tree and choose **Score this render**. You'll see:
- **VMAF** — how visually close the render is to the source (needs libvmaf-enabled ffmpeg).
- **pHash** — how visually *different* the render is from the source.
- **SSIM** — structural similarity, fast and always available.

You can also turn on **Settings → Scoring → "Score every render automatically"** (default OFF) if you want scores for every batch without the right-click.

### Render Health + suggestions
Click the new 🩺 **Health** toolbar button to see a per-row health summary with one-sentence suggestions for any render that fell outside your quality / originality thresholds. Each suggestion has a Confirm/Cancel dialog before any re-render — nothing happens silently. Re-renders use a `_v2` suffix; your originals are never overwritten.

### Pause / Resume + Diagnostics
- ⏸️ **Pause** halts new task dispatch after the current one finishes. The running ffmpeg is never interrupted (use Cancel for that). Pause survives an app restart.
- 🧰 **Diagnostics** exports a local zip with your logs + queue + scores + a sanitized copy of your config. The zip never leaves your computer; share it manually if you need support.

### Per-task ffmpeg logs
Every render's ffmpeg output is saved to `USER_DATA_DIR/logs/<batch>/<task>.log`. The last 5 batches are kept by default; older ones are pruned automatically. Useful when something goes wrong and you want to inspect what ffmpeg said.

### Production packaging
A new set of build scripts (`tools/build/`) produces reproducible Windows portable zips and macOS .app/.dmg artifacts with consistent VERSION.txt + SHA256 checksums. The local Drive-folder updater is unchanged — no auto-update on schedule.

## What didn't change

- The render command, the encoder pipeline, your existing presets, the GPU semaphore, your output file naming — all unchanged.
- Cutter / Merge / Mixer apps — unchanged this milestone.
- Your existing Settings — every new toggle defaults to a safe value (auto-scoring OFF, queue persistence ON, auto-retry OFF, sleep prevention OFF).

## Upgrade safety

Your `USER_DATA_DIR` (config + queue + scores + custom presets) lives in platformdirs, not in the install folder. Any update — including a rollback to a prior version — preserves it. Phase 3.6's build pipeline backs up the prior install folder as `_backup_<timestamp>/` before applying an update; you can roll back manually by renaming directories.

## For developers + power users

- Every Phase 3 sub-phase has an ADR under `docs/decisions/` (ADR-0009 through ADR-0014).
- Every state file on disk is schema-versioned with a never-raises load contract.
- Every new feature is additive and reversible — see `docs/PHASE_3_ROLLBACK.md`.

Bug reports + feedback: as before, through Adam's existing channel.
