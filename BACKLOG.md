# Backlog

Deferred audit-fix items, surfaced during the toolchain install (commits 5e7e8c9 + dc0747c) on 2026-04-26. Strategy: defer-with-tracking. End-of-Phase-2 cleanup phase resolves all items below before Phase 2 ships.

Each item has a stable ID (B-NNN) referenceable in commit messages and CHANGELOG entries.

---

## Governance / ADR

**B-004** — Audit findings M1-M16 from 2026-04-26 audit (see chat record). Includes deviation note errors in `bf4b636`, missing Observation V git tag, ADR-0004 format inconsistency, Path B bundling rollback impact, and other governance items.

## Documentation hygiene

**B-006** — Markdownlint violations repo-wide (365 total before MD013 bump to 200; expected reduction of approximately 200-300 with bump). Spans CHANGELOG.md, ROADMAP.md, PHASE_2C_PLAN.md, PHASE_2_PORT_NOTES.md, NVENC_PARAMETER_REFERENCE.md, PRESET_PHILOSOPHY.md, all 4 ADRs, all 5 README*.md, tests/README.md, scripts/. Auto-fixable rules remaining: MD022 (blanks around headings), MD031 (blanks around fences), MD032 (blanks around lists). Manual rule: MD040 (fenced code language tags).

**B-007** — Memory rule #13 cleanup: timeline / hours / fatigue language across multiple governance docs (ROADMAP.md lines 11/37 + table, PHASE_2C_PLAN.md lines 11/15/31/43/58/72/87/103/120/128/156/164/166/168, ADR-0002 lines 62/64/85, ADR-0003 lines 85/96). User finds this language patronizing; rule was added after these docs were written.

## Toolchain follow-ups

**B-008** — `pyproject.toml` decision deferred. Commitizen config currently in `.cz.toml`. If the project later needs `pyproject.toml` (packaging, ruff config, etc.), migrate `.cz.toml` content to `[tool.commitizen]` section.

**B-009** — Strict-mode commitizen-branch hook deferred. Currently `.pre-commit-config.yaml` uses lenient enforcement (commit-msg only, no commitizen-branch on pre-push). Flip to strict by adding commitizen-branch hook with `stages: [pre-push]` once team is comfortable with Conventional Commits.

---

## Resolution policy

- Items resolved: move to a "Resolved" section at bottom with commit hash and date.
- New deferrals during Phase 2 work: append here with new B-NNN ID.
- End-of-Phase-2 cleanup phase: every B-NNN must be resolved or explicitly downgraded to a future phase before Phase 2 ships.

---

## B-010: Per-task + batch ETA in auto_render.py

- **Status:** scheduled
- **Pickup:** post-v2.5-complete tag, pre-Phase-2d migration start (Step 5.5 in docs/ROADMAP.md)
- **Scope:** ~80-120 LoC; QLabel display in auto_render.py + new core/eta_estimator.py helper; EMA smoothing window 5-10 progress updates; per-task ETA + batch ETA math
- **Source:** ffmpeg progress parser already extracts out_time_us in core/ffmpeg_runner.py (Phase 2a/5b)
- **Dependencies (all land in Phase 2.5):**
  - F3 GPU pipeline (Step 4) — single ETA implementation covers CPU + NVENC paths, no rewrite later
  - Settings dialog (Step 4) — ETA on/off + smoothing window as settings options
  - Slot defaults (Step 4) — multi-task batch context for batch-ETA math
  - F4 onboarding tooltip infrastructure (Step 3) — for "±30% in first quarter, calibrating..." hover-help
- **Why pre-Phase-2d:** ~+1% to the 8,612 LoC migration sweep (cheap); avoids writing PySide6 from scratch without templates
- **Trigger for pickup:** v2.5-complete tag landed
- **Surfaced by:** Adam, planning chat 2026-04-27 (during Phase 2.5 step 1.5 verification)

## B-011: core/config.py atomic-write migration

- **Status:** scheduled (deferred per Step 4d-i 2026-04-28)
- **Priority:** Medium
- **Discovered:** Step 4b PARALLEL discovery (G3 finding); confirmed Step 4d-i
- **Context:** ADR-0007 D8 (Accepted 2026-04-27) asserts that core/config.py already handles atomic write. Discovery during Step 4b revealed this is incorrect: core/config.py uses direct `open(path, "w") + json.dump(...)` overwrite pattern (no `os.replace`, no tempfile-and-rename). The atomic-write primitive exists separately at core/atomic_write.py (used only for user-preset writes per Phase 2c-c-3).
- **Implication:** All Settings keys persisted via core/config.save() (Phase 2.5b: output_collision, gpu_error_action, sequential_slots, plus the 6 new GPU keys from Step 4d-i) inherit a non-atomic-write risk. If the user crashes mid-save (power loss, OS panic, app crash), config_video_renderer.json can corrupt — losing ALL user settings.
- **Why deferred:**
  1. Migration touches core/config.save() which is shared by all 4 apps (auto_render, cutter, merge, mixer) — broader blast radius than Phase 2.5's GPU-only scope.
  2. Step 4d-i + 4d-ii's GPU keys inherit the same risk that's already shipped for output_collision (Step 4b) — no NEW exposure introduced; the existing risk is carried forward.
  3. Per web research consensus (Microsoft Azure / AWS / Fowler / Cognitect), Accepted ADRs are immutable. ADR-0007 D8's atomic-write assertion is recognized here as a drafting error, not edited in place. If migration becomes architectural priority, write ADR-0008 to supersede the relevant subclaim.
- **Fix sketch:** Migrate core/config.save(path, data) to delegate to core/atomic_write.save_json_atomic(path, data). Verify behavior preserved: same return type, same exception class, same encoding, same indent. Test in all 4 apps that use core/config.
- **Trigger for pickup:** v2.5-complete tag landed. Re-evaluate priority based on (a) whether any user reports config corruption in the wild, (b) whether Phase 2d PySide6 migration touches core/config (good time to fold in), (c) whether atomic-write parity becomes a project-wide hygiene goal.
- **Surfaced by:** Step 4d-i 2026-04-28 (post-Phase-1-discovery confirmation of Step 4b PARALLEL G3 finding).

## Resolved

- **B-001** — ADR-0001 missing Decision makers field. Resolved [df1125a] 2026-04-27.
- **B-002** — ADR-0002 status/date mismatch. Resolved [df1125a] 2026-04-27 (canonical date: 2026-04-22).
- **B-003** — ADR-0004 missing Date + Decision makers fields. Resolved [df1125a] 2026-04-27.
- **B-005** — ruff debt in auto_render.py (E722 bare except + F841 unused current_output). BACKLOG entry stated "7 errors"; 4 were live at fix time (5 silently fixed in earlier 2c-c-* commits; 2 additional F841 unused `original_filename` errors at lines 1160 + 1219 surfaced post-audit and were also fixed as minimum-fix scope expansion to satisfy `ruff check` exit 0). Resolved [df1125a] 2026-04-27.
