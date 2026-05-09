# ADR-0005: User Data Storage via platformdirs (with opt-in portable mode)

**Status:** Accepted

**Date:** 2026-04-26

**Decision makers:** Adam (project lead)

## Status

Accepted (2026-04-26).

## Context

Sub-phase 2c-c-2 (PHASE_2C_PLAN.md) originally specified a Windows-only
resolver returning `./UserData/` alongside the exe, raising
`PortableLocationError` on Program Files installs, and raising
`NotImplementedError` on non-win32 platforms.

Three concerns surfaced during implementation:

1. **Windows VirtualStore silent redirect.** When an app installed under
   `C:\Program Files\` writes to its own install directory, Windows
   redirects the write to `%LOCALAPPDATA%\VirtualStore\Program Files\<app>\`
   without raising any error. `os.access(install_dir, os.W_OK)` returns
   True for Program Files paths. The plan's Program Files guard would
   therefore be unreliable: users would see writes succeed (to a hidden
   shadow location) when the guard is bypassed by the os.access soft-check.

2. **Cross-platform requirement (ADR-0004).** Adding macOS support in a
   future sub-phase (2c-c-6) would mean writing platform-branching code
   for path resolution. Each new platform increases surface area.

3. **`os.access` unreliability on Windows.** Documented since Python
   bpo-2528 (2008): `os.access` does not properly account for ACLs,
   VirtualStore redirects, or token elevation state.

The `platformdirs` package (56M+ downloads as of April 2026; used by
pip, scipy, black, virtualenv, tox) provides cross-platform user data
directory resolution honoring OS conventions:
  - Windows: `%LOCALAPPDATA%\1vmo-suite`
  - macOS:   `~/Library/Application Support/1vmo-suite`
  - Linux:   `~/.local/share/1vmo-suite`

Microsoft's own guidance for app config storage names `ApplicationData`
/ `CommonApplicationData` as the correct location, not Program Files.
Notepad++, Anki, OBS Studio, and VS Code all default to AppData with
portable mode as an explicit opt-in via a sentinel file.

## Decision

Use `platformdirs` as the default user data directory source. Support
opt-in portable mode via a `portable.txt` sentinel file alongside the
install directory. In portable mode, raise `PortableLocationError` if
the install is under a Windows-protected location (Program Files,
Windows, ProgramData) where writes would silently redirect via
VirtualStore.

Add `platformdirs>=4.0,<5` as a runtime dependency.

Concrete deviations from the original plan text:
  - Default user data location is platformdirs, not `./UserData/`.
  - Cross-platform out of the box; no `NotImplementedError` for
    non-win32 platforms.
  - 2c-c-6 (macOS support) reduces in scope to verification rather
    than implementation of a new code path.

## Consequences

Positive:
  - Eliminates VirtualStore silent-redirect bug class entirely.
  - Eliminates `os.access` unreliability concern (no writability check
    in the default path).
  - Aligns with Microsoft's official guidance for app config storage.
  - Aligns with peer-app convention (AppData default, portable opt-in).
  - Cross-platform support for ADR-0004 satisfied without new code.
  - `core/user_data.py` is shorter and simpler than a manual
    Program-Files-detection + os.access fallback would have been.
  - Lazy migration (per ADR-0002) is on the modern path: future
    consolidation toward platform conventions is incremental rather
    than disruptive.

Negative:
  - One additional runtime dependency (after pydantic). 6 total runtime
    deps now.
  - "Portable alongside exe" is no longer the default; users who want
    that behavior must place a `portable.txt` sentinel. Documented in
    user-facing docs when those land.
  - Plan text required substantive amendment rather than just
    filename/test-gate corrections.

Migration:
  - Sub-phase 2c-c-3 will need to migrate any existing
    `config_video_*.json` files from the install directory (legacy
    location) to the resolved user data dir. Migration logic deferred
    to 2c-c-3 per "no writes yet" gate in 2c-c-2.

## References

- PHASE_2C_PLAN.md sub-phases 2c-c-2 and 2c-c-6 (amended in this commit).
- ADR-0002 (UserData location is a versioned decision; lazy-migrable).
- ADR-0004 (cross-platform support: macOS added).
- https://platformdirs.readthedocs.io/
- Python bpo-2528 / GH-46780 (os.access ACL unreliability).
- Microsoft guidance: SpecialFolder.ApplicationData for app config.
