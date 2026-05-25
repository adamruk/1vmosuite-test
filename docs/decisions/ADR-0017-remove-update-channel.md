# ADR-0017: Remove the in-app update channel; relocate version-state to core/ (B-051)

**Status:** Accepted

**Date:** 2026-05-24

**Decision makers:** Adam (project lead)

**Supersedes:** none

**Amends:** ADR-0013 D5 (the updater-hardening contract — the updater it hardened is removed; the SHA / Authenticode follow-up tracked there as B-051 is closed by removal rather than by hardening).

## Context

All four apps (`auto_render.py`, `cutter.py`, `merge.py`, `mixer.py`) imported
`DriveUpdater` from `updater.py` and exposed a "🔄 Updates" toolbar button that
ran an in-app update channel: read a public Google Sheet (anonymous `gviz` CSV
endpoint) for a published version + Dropbox `download_link`, download the
`.exe`, and swap-and-relaunch it.

This channel is inherited decompiled code. It is the subject of **B-051**: its
only authenticity gate is best-effort (an optional sibling `.sha256` that is
*tolerated* when absent, plus the C2 HTTPS + PE-header sanity checks). The hash
is fetched from the same Sheet/Dropbox-controlled channel as the binary, so a
single compromised channel can serve both a malicious `.exe` and a matching
hash. Downloading and executing a remote binary whose source of truth is an
editable Google Sheet is a large attack surface.

Crucially, **there are no `.exe`-only users.** The audience is source-based
developers who update with `git pull`. For that audience the entire
download-and-run-remote path is pure attack surface with no benefit — the app
never needs to fetch and execute a binary it could instead get from source
control.

The channel also carried the only on-disk **version-state** helpers
(`_load_current_version` / `_save_current_version` on `DriveUpdater`, reading
`assets/Version AutoRender.json`). Each app uses these purely for its window
**title version label** (e.g. `1vmo Auto Render v3.1 (Assets v1.0)`). That
display must keep working after the channel is gone.

## Decision

1. **Remove the in-app update channel entirely.** Delete `updater.py`
   (`DriveUpdater` + `UpdaterDialog` + the Sheet/Dropbox download/relaunch).
   Remove the `from updater import DriveUpdater` import, the `self.updater`
   construction, the "🔄 Updates" button (and its toolbar add), and the
   `check_for_updates` method from all four apps.

2. **Relocate version-state to `core/version_state.py`.** A small, network-free
   module with `load_current_version(app_name) -> str | None` and
   `save_current_version(version, app_name) -> None`, preserving the original
   read/write semantics over `assets/Version AutoRender.json` byte-for-byte
   (same JSON shape `data["software"][app_name]["version"]`, same `indent=4`,
   same broad-except-and-print error handling). Apps import these for the title
   label. `core/` (not `core/user_data.py`) because the version file is a
   **repo/install asset** under `assets/`, not per-user state under
   platformdirs — folding it into `user_data.py` would conflate two different
   storage locations.

3. **Hard rule:** after this change, no code path fetches a manifest or
   downloads/executes a remote file. Enforced by an empty-result grep for
   `gviz|spreadsheet|dropbox|download_link|browser_download|check_and_update`
   across `*.py`.

4. `scripts/check_repo_consistency.py` drops `updater.py` from REQUIRED_FILES
   and gains `core/version_state.py`.

## Consequences

**Positive:**

- The arbitrary-remote-`.exe` attack surface is gone; B-051 is resolved by
  removal (no fail-open hash, no Sheet-controlled binary source).
- Version display is unchanged — the title label still reads the same JSON.
- The app launches with no network dependency anywhere in the path.

**Negative / trade-off:**

- No in-app "check for updates" affordance. For the current source-based
  audience this is a non-issue: updates come from `git pull`.

**Neutral / reversible:**

- This is **reversible and not scorched earth.** If a real distribution
  audience (`.exe`-only users) appears later, a *new* update channel can be
  added — preferably a signed **GitHub Releases** channel (verify an
  Authenticode signature / a release-asset checksum from a channel independent
  of the binary host), recorded in a future ADR. The `assets/Version
  AutoRender.json` file and `core/version_state.py` remain, so a future channel
  has its version-state primitives ready.

## Alternatives considered

- **Harden the existing channel (B-051 options 1/2: mandatory fail-closed SHA
  from a trusted channel, and/or Authenticode verification).** Rejected for the
  current audience: it invests in securing a feature no source-based dev needs,
  and still trusts an editable Google Sheet as the manifest. Removal is simpler
  and eliminates the surface outright.
- **Keep the channel, disable the button.** Rejected — dead-but-present
  download/exec code is still attack surface and still must be maintained.

## References

- `core/version_state.py` — relocated version-state helpers
- `tests/smoke/test_version_state.py` — version-load + all-apps-import coverage
- `assets/Version AutoRender.json` — the version file (unchanged)
- BACKLOG.md — B-051 (resolved by this ADR)
- ADR-0013 D5 — the updater-hardening contract this amends

## Related

- ADR-0013 (release packaging)
