# Phase 2 — Modernization Roadmap

## Status

**Not started.** This document records planned scope. Phase 2 begins only after Phase 1 (NVENC GPU encoding feature) is shipped and validated. Do not start any Phase 2 work while Phase 1 is in progress — concurrent feature + modernization work makes failure causes ambiguous.

## Scope

Phase 2 is pure modernization of the existing codebase. No new user-facing features. The goal is reducing technical debt and improving maintainability so future feature work (Phase 3+) is faster and safer.

Each sub-phase below is independently shippable. They can be done in any order, but the suggested order minimizes risk.

## Sub-phase 2a — Extract shared `core/` module

**Problem:** auto_render.py (~1150 lines), cutter.py (~921 lines), merge.py (~1366 lines), and mixer.py (~770 lines) duplicate significant infrastructure: file picker dialogs, FFmpeg subprocess workers, progress bar widgets, config save/load, output directory pickers. Roughly estimated 40–60% code overlap. Bug fixes need to be applied four times. Behavior drifts between apps.

**Goal:** extract shared infrastructure into a `core/` package imported by all four apps. No user-visible behavior change.

**Deliverable:**
- `core/ffmpeg_runner.py` — subprocess wrapper, progress parsing (using `-progress pipe:1` from Phase 1), cancellation
- `core/file_picker.py` — input/output dialog widgets
- `core/config.py` — JSON config load/save with schema validation
- `core/widgets.py` — shared progress bar, status label, output tree
- `core/preset_loader.py` — preset library reader (will read both legacy 5-column Encoder.txt and Phase 1's 6-column dual CPU/GPU format)
- All four apps refactored to use `core/`. Line counts should drop ~30% per app.

**Risk:** medium. Touches every app. Needs end-to-end smoke tests for all four apps before and after.

**Estimated effort:** 3–5 working days.

**Pre-work:** ensure all four apps have working e2e smoke tests committed to `tests/` first. Without baseline tests, regressions during refactor are invisible.

## Sub-phase 2b — Updater: Google Sheets/Dropbox → GitHub Releases

**Problem:** `updater.py` polls a public Google Sheet for version info and pulls binaries from Dropbox. Both are fragile (sheet can be edited, Dropbox links can rotate, no signing, no versioned history). Standard practice for desktop app updates is GitHub Releases or similar.

**Goal:** migrate update mechanism to GitHub Releases API.

**Deliverable:**
- `updater.py` rewritten to query GitHub Releases API for latest release tag
- Release artifacts hosted on GitHub Releases (free, versioned, optionally signed)
- Migration path for existing users: old updater can do one final update that points to the new mechanism, then disables itself
- Documentation: how to cut a new release, what files to attach, version tagging convention

**Risk:** low if existing users can be migrated cleanly; medium if not.

**Estimated effort:** 1–2 working days for the code, plus ongoing release-process documentation.

**Pre-work:** ADR documenting the migration decision and the rollback plan if GitHub Releases proves unsuitable.

## Sub-phase 2c — Encoder.txt: pipe-delimited → JSON

**Problem:** the pipe-delimited format is already strained. Phase 1 adds a sixth column (GPU command). The 300-way zoom presets have multi-thousand-character filter_complex strings on a single line with embedded special characters. JSON is the proven format (HandBrake uses it for its preset library) and handles edge cases cleanly.

**Goal:** migrate `Encoder.txt` to a JSON format. Each preset becomes a structured object with named fields.

**Deliverable:**
- New format spec documented in `docs/PRESET_FORMAT.md`
- Migration script `tools/migrate_presets.py` that converts the existing 6-column pipe format to JSON, validates the result, and writes `assets/Encoder.json`
- Parser in `core/preset_loader.py` updated to read JSON
- Legacy `Encoder.txt` kept as backup for one release cycle, then removed in a subsequent version
- Validation tooling: schema check on load, surfaced as warnings if a preset is malformed

**Risk:** low. Pure data migration with a deterministic script. Original format kept until JSON is proven.

**Estimated effort:** 1–2 working days.

**Pre-work:** must come AFTER 2a (depends on `core/preset_loader.py` existing).

## Sub-phase 2d — PyQt5 → PySide6

**Problem:** PyQt5 still works but is on a slow maintenance track. PySide6 is the official Qt-for-Python binding from the Qt Company, has LGPL licensing (more permissive than PyQt5's GPL), and matches the modern Qt6 API. Most Python desktop apps have migrated.

**Goal:** migrate the suite from PyQt5 to PySide6.

**Deliverable:**
- All `from PyQt5...` imports changed to `from PySide6...` (API is ~98% compatible)
- Signal/slot decorators updated where syntax differs (PyQt5's `pyqtSignal` becomes PySide6's `Signal`)
- Test that all four apps launch and process a reference video on PySide6
- requirements.txt updated; PyQt5 removed
- One ADR documenting the migration and any compatibility issues encountered

**Risk:** low to medium. APIs are compatible enough that automated migration tools (e.g., `qt5-to-6`) handle ~90%. The remaining 10% is edge cases like deprecated widgets or signal binding patterns.

**Estimated effort:** 1–3 working days.

**Pre-work:** must come AFTER 2a and 2c so the modernized core is what gets migrated, not the duplicated pre-2a code.

## Sub-phase 2e (deferred — Phase 3 candidate) — Cross-platform support

**Why deferred:** Adam's primary platform is Windows. Linux/macOS support is nice-to-have, not required. Most of the cross-platform work happens naturally during 2a (using `pathlib` instead of os-specific paths, etc.). Final cross-platform polish can wait until there's demand.

## Sub-phase 2f (deferred — Phase 3 candidate) — Slim FFmpeg bundle

**Why deferred:** the bundled FFmpeg is 243 MB. Distribution would be lighter if we used `imageio-ffmpeg` (lazy-downloaded smaller binary) or system PATH detection. But this only matters if Adam is distributing the suite to others as a download. Until distribution scale matters, the bundled-binary approach is simpler.

## Sub-phase ordering — recommended sequence

1. **2a (core/ extraction)** first. Everything else depends on it.
2. **2b (updater)** can ship in parallel with 2a if there's appetite.
3. **2c (JSON presets)** after 2a.
4. **2d (PySide6)** after 2a and 2c.

Total Phase 2 estimated effort: 6–12 working days, spread over whatever calendar time Adam wants.

## Out of scope for Phase 2

The following are explicitly NOT Phase 2 work, and live in their own future phases:

- New features (those go to Phase 3+)
- Test framework adoption (pytest, etc.) — currently `tests/` holds smoke logs only; switching to a real test framework is its own decision
- Continuous integration setup
- Code signing for Windows distribution
- Installer (currently distributed as raw Python project)

## When Phase 2 begins

Phase 2 begins when ALL of the following are true:

1. Phase 1 has shipped a tagged release (e.g., v2.1.0)
2. Phase 1 NVENC code has been used in real workload for at least one week without regression reports
3. Adam has explicitly decided to start Phase 2 (this is a deliberate choice, not automatic)

Until then, this document is a parking lot, not an action plan.
