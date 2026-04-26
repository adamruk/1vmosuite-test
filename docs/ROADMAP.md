# 1vmo Suite — Roadmap

Source of truth for phase status, observations canon, and strategic context. CLAUDE.md §7 and §11 point here.

---

## Team and context

- **Team:** 5 distributed contributors — 3 × Windows (Python 3.13, NVENC-capable GPUs), 2 × macOS. **Development is solo for Phase 2.** Future collaboration decided case-by-case.
- **Product trajectory:** team-internal tool. Commercial release not currently planned. Recorded in `docs/decisions/ADR-0002-product-trajectory.md`.
- **Platform strategy:** Windows-first. Mac-compat ships as a dedicated sub-phase after each major Windows milestone.
- **Preset sharing:** via git (`encoder.user.json` committed to repo, pulled to sync).

---

## Phase status

### Done

- **Phase 1** — 43 decompile fixes (`a225831`).
- **Phase 2a** — `core/` extraction (`3731230`, tag `phase-2a-complete`).
- **Phase 2c-a** — Encoder.json generation (`5fc1dc7`).
- **Phase 2c-b** — preset_loader JSON I/O (`57564fe`).
- **Phase 2c-c-1** — Pydantic schema + JSON dark release behind `ENCODER_USE_JSON` (`[ce51400]`, tag `v2c-c-1`).
- **Phase 2c-c-2** — platformdirs-based UserData resolver + portable.txt opt-in (`[248ac56]`, tag `v2c-c-2`).
- **Phase 2c-c-3** — atomic_write + user preset writer + caller rewire + migration. Fixes Observation O across all 5 user-state writes (`[86edaa4]`, tag `v2c-c-3`).
- **Phase 2c-c-4** — Prefix-namespaced preset IDs + schema v2 + EncoderDialog UI-Min. Fixes silent-data-loss bug from 2c-c-3 D3=a. See ADR-0006 (`[23c64bf]`, tag `v2c-c-4`).
- **Phase 2c-c-6** — Windows-only smoke regression suite (integration + determinism + aggregator + tests/README convention) (`[hash-pending]`, tag `v2c-c-6`).
- **Phase 2c done** — all 5 sub-phases shipped + post-2c-c-4 regression green; Mac smoke deferred to post-Phase-2 with Junaid (`[hash-pending]`, tag `v2c-c-complete`).
- **Governance backfill** — CLAUDE.md + CHANGELOG backfill (`f08b08e`), self-referential hash-fill (`fa0763b`), CHANGELOG hook installation (`250668b`), hook hash-fill (`9537660`).

### Pending — blocking Phase 2 done

| Phase | Scope summary | Est | Detail |
|---|---|---|---|
| **2d** | PyQt5 → PySide6 migration. Mac-quality-forced for current team. PySide6 6.9.1 target (not 6.9.2). 30-line `core/_qt.py` scaffold, libcst rewriter, Nuitka packaging. | 3-4 weeks | Playbook TBD |

**Phase 2 done = all rows above shipped.** Estimate: ~100-155 hours solo. At 6 hrs/day × 5 days = 3-5 calendar weeks. At 4 hrs/day × 5 days = 5-8 weeks.

### Backlog — not blocking Phase 2 done

Deferred items. Tracked here so they're not lost; picked up later if and when they become worth the time.

| Item | Trigger for pickup |
|---|---|
| **2c-c-5** — `extends:` schema field | Audit reveals deep preset redundancy that factors cleanly, or inheritance UI becomes needed |
| **2c-d** — Zoom-cycle generator | Zoom-cycle preset maintenance becomes tedious, or a new cycle family needs to be added |
| **2c-e Part B** — Inheritance UI + preset audit | 2c-c-5 picked up, or preset quality becomes a team complaint |
| **Phase 2e** — Parameter validation layer | User-authored preset corruption becomes a recurring issue, or commercial trajectory activates |
| **Phase 2f** — Vietnamese → English translation | Commercial trajectory activates (Observation T) |

**Phase 3** (commercial release prep) is a future decision, not currently planned. Future ADR would capture the decision to activate it.

---

## Observations canon

Items surfaced during scoped work but NOT fixed in scope (per CLAUDE.md §6). Status: Open / Triaged / Fixed in Phase X (sha) / Won't fix.

**Migrated 2026-04-21** from CLAUDE.md §10 (which becomes a one-line pointer here). Letters are permanent — once assigned, never reused.

| ID | Summary | Surfaced | Status |
|----|---------|----------|--------|
| A | Widget resize polish — ~90 `setFixed*` calls need review for display scaling | 2026-04 | Open, backlog |
| C | `merge.py` type-coercion crash in `load_last_paths` | 2026-04 | Open, backlog |
| D | Duplicate config files across apps | 2026-04 | Open, backlog (partially addressed by Phase 2c JSON migration) |
| F | `merge.py` doesn't use NVENC | 2026-04 | Open, backlog |
| H | Config key inconsistency across apps (`output_dir` vs `last_output_dir` etc.) | 2026-04 | Open, backlog |
| I | `mixer.py` Stop button is non-functional (`cancel_event` set but never read) | 2026-04 | Open, backlog |
| J | `cutter.py` Stop only kills queued jobs, not in-flight | 2026-04 | Open, backlog |
| K | Cancel caller-side cleanup incomplete (runner-side fixed, callers remain) | 2026-04 | Open, backlog |
| L | `EncoderDialog` returns `dict`, not `Preset` | 2026-04 | Open, backlog |
| M | Progress dialect harmonization (`legacy_stderr` vs `progress_pipe`) across apps | 2026-04 | Open, backlog |
| N | Python 3.13 + PyQt5 time bomb | 2026-04 | Open, scheduled Phase 2d |
| O | Frozen `.exe` behavior unvalidated | 2026-04 | **Fixed in 2c-c-3** (`86edaa4`) — all 5 user-state writes routed through `core/atomic_write.py` + `core/user_data.py` (platformdirs default, portable.txt opt-in); silent PermissionError under Program Files installs no longer possible |
| P | `merge.py` `_RunnerHandle` sentinel cleanup (compatibility shim added during Phase 2a) | 2026-04 | Open, backlog |
| Q | `auto_render.py` cancel unvalidated | 2026-04 | Open, backlog |
| S | `EncoderDialog` loses `details` field on edit | 2026-04 | Open, backlog |
| T | Vietnamese text throughout UI, docs, and preset metadata. Translation needed before any commercial release. No impact on team-internal use. | 2026-04-20 | Open, backlog (Phase 2f trigger = commercial activation) |
| U | `tools/generate_encoder_json.py` save path inconsistency | 2026-04 | **Fixed in Phase 2c-b** (`57564fe`) — tool now uses `save_presets_json` |
| V | `RenderWorker.process()` appends `-c:v libx264 -c:a aac` after preset params. FFmpeg last-wins silently overrides `-vcodec libx265` → H.264 and `-c:a copy` → AAC re-encode. Image encoders (presets with `-f` or `image2`) are the only exception. Reproduce: `grep -E "libx265\|hevc_nvenc\|-c:a copy" assets/Encoder.txt`. Blocks HEVC and NVENC presets from working as authored. | 2026-04-21 | **Fixed in Phase 2 (`c03433a`)** — `_has_vcodec`/`_has_acodec` helpers gate codec-append in Path B |
| W | `logging.basicConfig(filename="video_*.log", ...)` in cutter.py / merge.py / mixer.py uses bare filenames that resolve against CWD. Under shortcut/Program-Files launches the log lands in an unpredictable directory. Out of 2c-c-3 scope per plan ("user preset writer" focus). Fix is to move to `user_data_dir / "logs/"` in a follow-up cleanup commit. | 2026-04-26 | Open, deferred from 2c-c-3 (D2=b) |

**Letter convention.** B, E, G, R were skipped during original surfacing and remain reserved — do not reuse. Observation IDs are permanent; fixed observations keep their letter with updated status.

**Adding an observation:** append with next letter (W next). Never add to CLAUDE.md. If reproducible, save to `tests/repro/observation-<letter>-<slug>.py` per peer rule 1.

---

## Peer rules (adopted 2026-04-21 from NVD playbook)

1. **Reproduction-file rule.** Observations with reproducible behavior ship a minimal script at `tests/repro/observation-<letter>-<slug>.py`. Not required for doc drift or architectural-only observations.

2. **Two-sources rule.** Strategic claims in ROADMAP, PHASE_2C_PLAN, PRESET_PHILOSOPHY cite at least two independent sources where possible. Single-source claims flagged *(single source)*.

3. **Late-work cutoff rule.** If a session is past planned end-time and a decision would foreclose future flexibility, defer rather than force. 80% of planned scope on time beats 100% at 2am with 20% rework.

---

## Strategic context — document map

- `docs/PHASE_2C_PLAN.md` — Phase 2 blockers and backlog items, acceptance criteria, pytest exceptions, rollback anchors.
- `docs/PRESET_PHILOSOPHY.md` — preset design principles, taxonomy, kitchen-sink criteria.
- `docs/NVENC_PARAMETER_REFERENCE.md` — Windows-only NVENC reference.
- `docs/decisions/ADR-0001-phase-2-methodology-reconciliation.md` — Phase 2 methodology (manual-smoke-only foundation).
- `docs/decisions/ADR-0002-product-trajectory.md` — team-internal tool, commercial not currently planned.
- `docs/decisions/ADR-0003-narrow-pytest-exceptions.md` — narrow pytest exceptions permitted within ADR-0001.
- `docs/SESSION_LOG.md` — historical decision traces.
- `docs/RESEARCH_SUMMARY.md` — distilled prior-research rationale.
- `docs/CORRECTIONS.md` — research-verification audit log (17 numbered corrections).
- `docs/PHASE_1_STOP_CONDITIONS.md` — Phase 1 kill criteria (completed, historical).

---

## Maintenance

Authoritative for phase status and observations canon. Update on phase completion, new observations, peer-rule changes, and when backlog items move to blocker status (or vice versa). Audit trail: `git log docs/ROADMAP.md`.
