# Phase 2c Execution Plan

Detailed execution plan for Phase 2 blockers and backlog. Phase status and team context: `docs/ROADMAP.md`.

---

## Executive summary

**Phase 2 done = 4 blocker sub-phases + PySide6 migration.**

Total: ~100-155 hours solo. At 6 hrs/day × 5 days: **3-5 calendar weeks.** At 4 hrs/day × 5 days: **5-8 weeks.**

Backlog items (2c-c-4, 2c-c-5, 2c-d, 2c-e Part B, Phase 2e, Phase 2f) are scoped here for pickup later. They don't ship as part of Phase 2.

Pre-requisite for 2c-c-1: a **small audit** of Observation-U-affected presets (~2-3 hrs, not the full preset audit).

---

## Pre-2c-c-1: small audit

**Why small, not full.** Full 111-preset audit was scoped for the broader Phase 2c-e Part B work (backlog). For Phase 2 done, we only need to know which presets Observation V affects so the 2c-c schema and Observation V fix are both well-scoped.

**Scope.** Spreadsheet at `docs/planning/observation-u-blast-radius.md`:
- `id` — current preset identifier
- `group` — current group
- `codec` — video codec from params (libx265, h264_nvenc, hevc_nvenc, or none)
- `audio_mode` — copy / re-encode / strip
- `observation_u_affected` — Y/N
- `notes`

**Target.** All 111 entries, but only the codec/audio columns need careful attention. Fast pass. 2-3 hours.

**Pass criterion.** Spreadsheet complete. Blast radius enumerated (count of affected presets + which groups). Ships as own commit before 2c-c-1.

**Deferred to backlog.** Factoring-pattern analysis, kitchen-sink flagging, zoom-cycle pattern categorization — all part of the larger 2c-e Part B audit when picked up.

---

## Phase 2 blockers — detailed plans

Each sub-phase ends with green smoke test on main, CHANGELOG entry, and commit. Trunk-based. Rollback = `git revert` of the sub-phase commit.

### 2c-c-1 — Pydantic schema + builtin.json, dark-released (6-8 hrs, Windows)

**Scope.**
- `core/encoder_schema.py`: `EncoderPreset`, `EncoderLibrary` (`schema_version: int = 1`, `presets: list[EncoderPreset]`).
- Regenerate `assets/Encoder.json` via existing `tools/generate_encoder_json.py`.
- Add `load_builtin_json()` to `core/preset_loader.py`.
- Gate behind `ENCODER_USE_JSON=1` env var. Legacy `Encoder.txt` loader remains default. No UI or write changes.

**Acceptance.**
- `ENCODER_USE_JSON=1` launches with 111 presets from JSON; unset launches from `Encoder.txt`.
- Load time within 100ms of legacy.
- `tools/check_encoder_schema.py` emits PASS to `tests/smoke-2c-c-1-schema-YYYYMMDD.log` (manual-smoke per ADR-0001).

**Tag:** `v2c-c-1`.

### 2c-c-2 — Portable UserData + writable-install-dir guard (3-4 hrs, Windows)

**Scope.**
- `core/user_data.py` with `resolve_user_data_dir()`. Returns `./UserData/` alongside exe if writable.
- On Program Files install, raise `PortableLocationError` with clear user-facing message.
- `sys.platform == 'win32'` only; others raise `NotImplementedError` (2c-c-6 handles).
- No writes yet — pure resolution.

**Acceptance.**
- Writable directory returns `./UserData/`; Program Files path raises with clear message.
- `tests/smoke/test_user_data_resolution.py` passes.

**Tag:** `v2c-c-2`.

### 2c-c-3 — User preset writer: atomic write + .bak + retry (5-7 hrs, Windows)

**Scope.**
- `core/atomic_write.py` with `save_json_atomic(path, data)`: serialize-to-bytes first (catch errors pre-disk), write `path.tmp` in same directory, `f.flush() + os.fsync()`, rotate `path` → `path.bak` (single generation), `os.replace(path.tmp, path)` wrapped in **5-retry exponential backoff** (50/100/200/400/800ms) for `PermissionError`/`OSError`.
- `save_user_presets_json(presets)` in preset_loader using this primitive.
- Writes only triggered by new `tools/test_user_save.py` smoke script.

**Acceptance.**
- `tools/test_user_save.py` round-trip works.
- Corrupted main file auto-falls-back to `.bak` on load with visible warning log.
- `tests/smoke/test_atomic_write_retry.py` passes — **ADR-0001 pytest exception** (see Testing section below).
- Manual smoke: open file in Notepad during save; retry resolves within 1.6s.

**Tag:** `v2c-c-3`.

### Observation V fix — standalone commit (3-5 hrs)

**Not a sub-phase, a standalone commit.** Fits between 2c-c-3 and 2c-c-6 in the timeline but independent.

**Scope.**
- `RenderWorker.process()` skips `-c:v libx264 -c:a aac` append when preset already specifies a video or audio codec (scan for `-vcodec`, `-c:v`, `-codec:v`, `-acodec`, `-c:a`, `-codec:a`).
- Image-encoder exception (`-f image2`) unchanged.
- Reproduction script at `tests/repro/observation-v-codec-append.py` (peer rule 1).
- Mark Observation V as **Fixed in Phase 2 (<sha>)** in ROADMAP.md.

**Acceptance.**
- Reproduction script shows pre-fix silent override and post-fix correct behavior.
- Manual smoke: HEVC preset, `-c:a copy` preset, NVENC preset all render to preset intent (not silently overridden).

**Commit message format:** *"Fix Observation V: RenderWorker codec-append gotcha."*

**Status update (2026-04-23):** Fix shipped in commit `c03433a` as part of Path B, bundled with 5 other isolated bug fixes ported from Phase 1 (Bugs 1, 3, 5, 6, 7 + new `_has_acodec` helper). This deviates from the "standalone commit" rule above. The deviation is acknowledged as a one-off justified by tight relatedness (all 6 fixes from the same Phase 1 source folder, all touching the same `RenderWorker` class). The standalone-commit rule remains in force for future scheduled blocker fixes (2c-c-1, 2c-c-2, 2c-c-3, 2c-c-6, 2d). Acceptance items 1 (reproduction script) and 2 (status amendments) status: (1) skipped — fix already shipped, manual smoke testing covers regression risk; (2) addressed by this commit.

### 2c-c-6 — Mac-compat pass (5-8 hrs, Mac)

**Scope.**
- `core/user_data.py`: `sys.platform == 'darwin'` branch resolves to either bundled-app-relative `./UserData/` (if writable) or `~/Library/Application Support/1vmo/UserData/` fallback. Linux raises `NotImplementedError`.
- Bundled macOS ffmpeg binary (or PATH-resolved — decide with Mac teammates during sub-phase).
- Retry loop in `atomic_write.py` unchanged — Spotlight indexing occasionally causes transient `EBUSY`; existing backoff handles it.
- NVENC-requiring presets show non-blocking info message on Mac ("this preset uses NVENC, unavailable on this platform").

**Acceptance.**
- auto_render launches on Mac with 111 presets loaded.
- User preset round-trip works on Mac.
- Bundled ffmpeg renders a libx264 preset successfully.
- NVENC preset selection shows info message.
- Both Mac teammates confirm launch + basic render.

**Tag:** `v2c-c-complete`.

### Phase 2d — PyQt5 → PySide6 migration (3-4 weeks, ~80-120 hrs)

Separate playbook (TBD when Phase 2d begins). High-level scope:

- **Motivation.** Mac-quality-forced for current team. Licensing headroom preserved for any future commercial decision.
- **Approach.** 30-line deletable `core/_qt.py` scaffold; libcst mechanical rewriter (`migrate_qt.py`); per-app migration.
- **Target.** PySide6 6.9.1 on QtWidgets. Pin explicitly NOT 6.9.2 due to QTBUG-140144 and Anki community reports of 6.9.2 blank-main-window issues.
- **Packaging.** Nuitka standalone.
- **Fallback.** $670 Riverbank commercial PyQt5 license pre-approved if migration exceeds 60 hours.

**Cross-thread slot handling:** `@Slot` + explicit `Qt.ConnectionType.QueuedConnection` on every cross-thread `connect()`. If wrong-thread execution persists (PySide 6.8.x-6.9.x worker-object pattern caveat per Qt engineer guidance), fall back to QThread-subclass pattern.

**Detailed playbook drafted when Phase 2d begins.** Not in scope for today's commit.

---

## Testing: the one ADR-0001 exception kept for Phase 2

ADR-0001 locks manual-smoke-only. One narrow pytest exception in 2c-c-3.

The second exception (extends: cycle detection) was planned for 2c-c-5 — that sub-phase is now backlog. Exception deferred with it.

| Exception | File | Why pytest not manual | Size |
|---|---|---|---|
| Atomic-write retry | `tests/smoke/test_atomic_write_retry.py` | OneDrive sync and AV file-locks aren't reliably reproducible on demand. Manual smoke has ~0 catch-rate for retry-loop regressions. Mock `os.replace` to raise `PermissionError` N times; assert retry count, backoff timing, error propagation. | ~30 min, ~15 lines |

**Not added to pytest:** Pydantic roundtrip (framework-covered), copy-on-write identity (backlog, not in Phase 2 scope), UI behavior (Phase 2d concern), render-output correctness (manual smoke sufficient).

---

## Rollback strategy

| Scenario | Action |
|---|---|
| Single sub-phase regression | `git revert <sha>` of offending sub-phase. Prior sub-phases remain shipped. Update ROADMAP. |
| Schema design flaw found post-ship | Don't revert. Ship schema_version=2 later with lazy migration on load. Reference: Azure Cosmos DB, Zed settings. |
| Observation V fix regression | Isolated commit — revert independently. |
| Mac-compat breaks Windows (unlikely — 2c-c-6 is additive) | Revert 2c-c-6. Windows returns to 2c-c-3 + Observation V fix; Mac returns to pre-2c-c. |
| Phase 2d migration bug shipped | Per-app revert possible (4 separate migration commits). Shim pattern preserves ability to run mixed PyQt5/PySide6 during rollback window. |

---

## Work rhythm

Target: **6 hrs/day × 5 days/week** for sustainable solo pace. Evidence: Cal Newport's 3-4 hour ceiling for deep work + 2 hours of lower-intensity coordination work. Accept 3-5 calendar weeks for Phase 2 blockers.

**Do not.** Attempt 10-12 hrs/day sustained for Phase 2. The 80-120 hour PySide6 migration (2d) is where hour-10-of-day-12 mistakes compound. A migration bug shipped because you were tired at 11pm on day 14 costs a week of debugging later.

**Do.** Accept the 3-5 week timeline. Allow natural sprints (8-10 hrs) when a sub-phase has momentum. Hard-cap 2d days at 6 hrs.

---

## Completion criteria

All of:
1. Tags exist: `v2c-c-1`, `v2c-c-2`, `v2c-c-3`, Observation V fix commit, `v2c-c-complete`, `v2d-complete`.
2. All 111 presets load, validate, render correctly on Windows + Mac.
3. All 4 apps run on PySide6 with no PyQt5 imports remaining.
4. Observation V marked Fixed in ROADMAP.md with sha.

**At that point: Phase 2 done.** Backlog items revisited case-by-case as they become worth the time.

---

## Backlog — scoped for pickup later

Items deferred from Phase 2 scope. Captured here so they're not lost when they become worth picking up.

### 2c-c-4 — Prefix-namespaced IDs + copy-on-write for built-ins (5-7 hrs)

Preset `id` field required, namespaced: `builtin:<group>/<slug>` or `user:<slug>`. Copy-on-write on built-in mutation. Load-time validation rejects malformed or misprefixed IDs.

**Trigger for pickup.** Preset ID collision issues in team use, or commercial distribution becomes planned.

### 2c-c-5 — extends: schema field (6-9 hrs)

Experimental `extends: str | None` field. Resolver with single-parent chain, max depth 8, cycle detection. Second ADR-0001 pytest exception (`test_extends_cycle_detection.py`) activates with this sub-phase.

**Trigger for pickup.** Audit reveals deep preset redundancy that factors cleanly, or inheritance UI becomes needed.

### 2c-d — Zoom-cycle generator (6-8 hrs + 1-2 hr Mac smoke)

Parametric generator for `Cycle 10s 4-3-3` family. Produces Windows NVENC + cross-platform libx264 variants.

**Trigger for pickup.** Zoom-cycle preset maintenance becomes tedious, or a new cycle family needs to be added.

### 2c-e Part B — Inheritance UI + preset audit (8-10 hrs + 1-2 hr Mac smoke)

Full audit of Ultimate group + kitchen-sink criteria application + read-only inheritance UI in EncoderDialog.

**Trigger for pickup.** 2c-c-5 picked up (inheritance UI needs extends: field present), or preset quality becomes a team complaint.

### Phase 2e — Parameter validation layer (20-30 hrs)

Pydantic schema + known-bad-combination guards + pixel-format assertions. Tiered validation. Hand-curated encoder capability catalog.

**Trigger for pickup.** User-authored preset corruption becomes a recurring issue, or commercial trajectory activates.

### Phase 2f — Vietnamese → English translation

Per Observation T. Required only if commercial trajectory activates.

**Trigger for pickup.** Commercial trajectory ADR written, or team convenience becomes compelling (2 non-Vietnamese team members).

---

## Maintenance

- Each sub-phase has fixed scope. Expand only via explicit CLAUDE.md §0 override in a prompt.
- If estimate exceeded by >50%, pause and re-scope.
- Commit message format: *"Per docs/PHASE_2C_PLAN.md sub-phase 2c-c-N, [action]."*
- CHANGELOG entry per sub-phase is mandatory (hook-enforced).
- When a backlog item's trigger fires, move it from Backlog section to Phase 2-style detailed plan. Document the pickup decision in a new commit.

---

## Evidence references

Strategic claims draw from research in session transcripts 2026-04-19 through 2026-04-21. Key multi-source patterns:

- Schema versioning (lazy migration, integer versions): Azure Cosmos DB, Zed editor, SQLite `user_version`.
- Atomic write + retry: Python bug 46003, VTK CMake `cmSystemTools::RenameFile`.
- Sub-phasing benefits (trend direction, not specific percentages): GitClear 12,638-PR study, Graphite 50-line analysis.
- Work rhythm: Cal Newport, Anders Ericsson.

Two-sources rule (ROADMAP peer rule 2) met for operative claims.
