# ADR-0013: Production packaging + local release readiness

**Status:** Accepted
**Date:** 2026-05-22
**Decision makers:** Adam (project lead)
**Related:** ADR-0001 (no general pytest), ADR-0004 (cross-platform Mac), ADR-0005 (platformdirs user data), CLAUDE.md §12 (PyInstaller rules)

## Context

Phase 3.6 standardises how 1vmo gets from a clean source tree to a
distributable artifact. Adam's hard rules:

1. **Local-only.** No cloud updater; the existing Drive-folder
   updater stays. No telemetry, no remote service.
2. **Portable-first.** The primary artifact is a zip-able folder
   the user drops anywhere. Installer (Inno Setup) is optional.
3. **user_data_dir is upgrade-immune.** Phase 3.1 / 3.2 / 3.4 /
   3.5 state files survive every update.
4. **No destructive updates.** Backup-before-swap; `_backup_<ts>`
   sibling kept for manual rollback.
5. **No auto-update scheduler.** Toolbar-only stays (Phase 2d).

## Decision

### D1. Portable zip is the primary artifact

`tools/build/build_windows.py` produces a portable folder under
`dist/<bundle>/` and a sibling zip
`1vmo-auto-render-vX.Y.Z-windows-portable.zip`. The Inno Setup
installer is optional (D6).

### D2. macOS artifact is .app inside .dmg

`tools/build/build_macos.py` invokes a separate
`1vmo-suite-macos.spec` and wraps the resulting .app in a .dmg
via `create-dmg` (preferred) or `hdiutil` (fallback). Code-signing
+ notarisation is OPT-IN via `APPLE_DEV_ID` / `APPLE_PWD` env
vars; without them the .dmg ships unsigned with a Gatekeeper
override note in the README.

### D3. VERSION.txt is the version source of truth at runtime

`tools/build/generate_version_file.py` emits
`dist_version.txt` containing semver + git short hash + UTC
timestamp + ffmpeg banner. The build script copies it into the
bundle as `VERSION.txt`. The About dialog (deferred wiring this
phase) reads it; `check_release_integrity.py` validates its
presence.

### D4. check_release_integrity.py gates every build

Runs at the end of `build_windows.py` and is also invokable
standalone on a downloaded zip. Asserts:

- VERSION.txt present + parseable
- `_internal/core/__pycache__/*.pyc` present (CLAUDE.md §12 rule 2)
- `assets/Encoder.json` present + valid JSON
- ffmpeg binary present under `ffmpeg/` or `Resources/ffmpeg/`

Fails loudly on any missing element. Build exits non-zero.

### D5. Updater hardening (design noted; full wiring deferred)

The design specified SHA256 verify + `_pending/` extract +
backup-before-swap. Phase 3.6 ships the build-side tooling
(integrity checker + checksums.txt generator) and DOCUMENTS the
updater-side hardening in `docs/RELEASE_WINDOWS.md`. The
updater.py edits are deferred to a follow-up patch so this phase
ships strictly additive without touching the updater hot path.

### D6. Inno Setup installer is optional

`tools/build/inno_setup_compile.py` is NOT shipped this phase;
the portable zip is sufficient for Adam's existing distribution
workflow. The .iss template would be a small addition in a future
patch.

### D7. Sandbox cannot build real artifacts — documented honestly

This phase authors the scripts and validates them on the source
tree. PyInstaller invocation produces platform-native binaries
(Linux ELF in this sandbox, not Windows .exe / macOS .app), so
real artifact production happens on Adam's Windows + macOS
hosts per `docs/RELEASE_WINDOWS.md` / `docs/RELEASE_MACOS.md`.
The Phase 3.7 RC checklist marks the artifact-production rows
`[N]` with reason until they run on real host hardware.

### D8. ADR-0003 narrow-pytest extension

`generate_version_file.py` and `check_release_integrity.py` are
small stdlib-only utilities. Tests for them are pure-Python
(<1s, deterministic, no Qt, no ffmpeg). ADR-0013 extends the
narrow exception.

## Consequences

- 4 new build scripts under `tools/build/`.
- No new runtime dependency (psutil optional, already proposed in
  Phase 3.4; not required here).
- PyInstaller spec stays the same in this phase — Phase 3.6
  doesn't edit `1vmo-suite.spec` yet (the integrity checker
  validates the existing spec's output structure).
- Updater hardening documented but not yet wired.

## Rollback

1. Delete `tools/build/` and `docs/decisions/ADR-0013-*.md`.
2. Revert CHANGELOG / BACKLOG entries.
3. Existing manual PyInstaller workflow (per CLAUDE.md §12)
   continues to work unchanged.
