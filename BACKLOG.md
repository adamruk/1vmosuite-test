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

## B-014: _reload_config_settings refreshes only 2 of ~10 Settings keys

- **Status:** scheduled (deferred per v2.5.1 audit 2026-04-28; Phase 2d candidate)
- **Priority:** HIGH (functional gap surfaces if user changes GPU keys live)
- **Surfaced:** v2.5.1 PARALLEL audit on origin/main (2026-04-28)
- **Context:** auto_render.py `_reload_config_settings` (called after Settings dialog OK) only re-reads `output_collision` + `gpu_error_action`. Stale comment says "Other Settings keys (use_gpu, nvenc_quality_offset, show_ffmpeg_command, open_output_when_done) reserved for Step 4c+ when GPU pipeline lands" — but Step 4c-4d-ii has shipped (GPU pipeline wired per CHANGELOG `[442d2eb]`). The comment never caught up.
- **Implication:** User toggles `gpu_enabled` in Settings → clicks OK → Settings dialog persists to disk → `_reload_config_settings` runs but does NOT update `self.gpu_enabled` → next render uses OLD (app-startup) value. Settings change for GPU/num_threads/output_dir keys requires app restart to take effect. PORT_NOTES line 99-101 says `_reload_config_settings` should "apply output dir, GPU toggle (gated by capability), all five runtime keys" — current impl honors 2 of those.
- **Resolution:** Extend `_reload_config_settings` to mirror the 5+ GPU keys read in `__init__` (gpu_enabled, gpu_codec, gpu_preset, gpu_max_concurrent, gpu_max_quality_mode). Verify each is consumed by next render dispatch. Likely also recreate `_gpu_semaphore` if `gpu_max_concurrent` changed.
- **Trigger for pickup:** user reports GPU Settings change "not taking effect" OR Phase 2d touches Settings dialog code path.

## B-015: translate_to_nvenc codec routing contradicts ADR-0007 D4

- **Status:** scheduled (deferred per v2.5.1 audit 2026-04-28; LOW priority)
- **Priority:** LOW (niche — only affects libx265 presets when user has gpu_codec=h264_nvenc)
- **Surfaced:** v2.5.1 PARALLEL audit (2026-04-28)
- **Context:** core/preset_translator.py `translate_to_nvenc` computes `mapped = _CODEC_MAP.get(input_codec, input_codec)` (which would map libx265->hevc_nvenc per D4) but then ignores `mapped` in the `if input_codec in _CODEC_MAP:` branch and uses the `codec` kwarg instead. Comment says "respect codec arg over preset map" — intentional, but contradicts ADR-0007 D4 which states `libx265 -> hevc_nvenc`.
- **Implication:** User has libx265 preset + gpu_codec=h264_nvenc (default) → preset gets translated to h264_nvenc, NOT hevc_nvenc. Codec intent of preset overridden by user's default. Quality/compatibility consequences depending on use case.
- **Resolution:** Either (a) honor `_CODEC_MAP` per-preset mapping, OR (b) update ADR-0007 D4 commentary in a new ADR to reflect actual single-knob behavior. Document chosen direction in the implementing commit. Dead `mapped` variable in else-branch can be cleaned up regardless.
- **Trigger for pickup:** post-tag review or first user report involving libx265 preset on GPU.

## B-016: anchor #8 missing thread_bars[idx].setValue(0)

- **Status:** scheduled (deferred per v2.5.1 audit 2026-04-28; cosmetic)
- **Priority:** LOW (cosmetic flicker for ~100ms across batch boundary)
- **Surfaced:** v2.5.1 PARALLEL audit (2026-04-28)
- **Context:** anchor #8 (commit 701bf53) resets `_worker_state[idx]['percent']=0` in start_render but does NOT reset the visible QProgressBar via `self.thread_bars[idx].setValue(0)`. cancel_render does both; start_render does only the data side.
- **Implication:** Starting batch 2 in same session → labels reset to "Ready" (good) but QProgressBar visual stays at batch 1's final percent (often 100%) for ~100ms until the first new progress event. Cosmetic flicker only.
- **Resolution:** Add `self.thread_bars[idx].setValue(0)` inside the anchor #8 loop in start_render. Symmetry with cancel_render. ~1 LoC change.
- **Trigger for pickup:** Phase 2d touches the worker UI OR opportunistic during any future `start_render` edit.

## B-017: 11 Encoder.txt presets had stale Code/assets/data/ paths — RESOLVED

- **Status:** RESOLVED (closed by v2.5.1 fix-3, commit c60baf5, 2026-04-28)
- **Resolution evidence:** all 11 affected preset variants (10 Layer Overlay + 1 Line) verified rendering successfully via smoke test on 5 input videos; output filenames written; ffmpeg console clean. CHANGELOG entry under [Unreleased] ### Fixed documents BEFORE/AFTER/WHY with PATH-SEMANTICS-NOTE caveat.
- **Note for future:** moved here pre-emptively to keep B-NNN numbering monotonic. See "Resolved" section for canonical resolved-items list per BACKLOG.md resolution policy.

## B-018: Edit/Delete buttons grayed for ALL presets in fresh install (UX gap, not a bug)

- **Status:** scheduled (deferred per v2.5.1 audit 2026-04-28; UX polish)
- **Priority:** MEDIUM (user-facing confusion — looks broken)
- **Surfaced:** v2.5.1 user smoke test + PARALLEL audit (2026-04-28)
- **Context:** Per ADR-0006, built-in presets (id starts with "builtin:") are intentionally non-editable to prevent the silent-data-loss class fixed in 2c-c-4. Implementation conforms exactly to ADR-0006 spec: button-disable wired via tree_encoders.itemSelectionChanged at L553-554 + model-layer guard in edit_encoder L1838 + delete_encoder L1883 + italic visual cue at L1765-1768.
- **The bootstrap problem:** ALL 111 presets shipped in fresh install are built-in (109 from Encoder.txt + 2 hardcoded Text defaults). User-namespace empty until user explicitly clicks Add. So 100% of selections trigger the disable logic. From user POV: "Edit/Delete don't work on any preset, must be broken." From codebase POV: documented invariant working correctly.
- **Why italic isn't enough:** italic styling on column 2 only registers as "different" if there's a non-italic reference for comparison. Fresh install has zero non-italic presets. ADR-0006 acknowledged italic as "visible read-only" but didn't anticipate the bootstrap problem.
- **Tooltip lies:** Edit/Delete tooltips say "Edit the selected preset" / "Delete the selected preset" but the button is disabled — misleading.
- **No clone path:** zero matches for clone/duplicate/copy.preset/save_as/new.from in auto_render.py. User cannot start customizing without Add-from-scratch + manual re-typing of name + params + description.
- **Resolution options (ranked by UX value, all LOW risk additive — none break ADR-0006):**
  - Option 1 (~4 LoC): tooltip enrichment — append "(built-in presets are read-only)" to Edit/Delete button tooltips at L512+L521 OR install dynamic tooltip swap inside `_update_encoder_buttons_enabled`.
  - Option 2 (~30 LoC): Add "Clone" button next to Edit/Delete. When built-in selected, Clone copies preset with id="user:<slug>" and opens EncoderDialog for renaming. Solves bootstrap problem.
  - Option 3 (~5 LoC): visual cue strengthening — 🔒 prefix or gray text color in addition to italic.
  - Option 4 (~40 LoC): Combined — tooltip + Clone. Resolves both "why disabled?" (tooltip) and "what do I do instead?" (Clone) at once.
- **PARALLEL recommendation:** Option 1 first (cheap, immediately resolves "is this broken?" confusion). Option 4 is the long-term answer if user-customization is to be a first-class feature.
- **Trigger for pickup:** post-tag UX polish phase OR first explicit user request to edit a preset.

## B-019: "Completed processing N video(s)!" success-toned message fires on all-fail batch

- **Status:** scheduled (deferred per v2.5.1 audit 2026-04-28; cosmetic)
- **Priority:** LOW (misleading wording in all-fail edge case)
- **Surfaced:** v2.5.1 user smoke test (Line preset failed batch, 2026-04-28)
- **Context:** `_start_next_task` terminal cleanup branch shows "Completed processing N video(s)!" QMessageBox when called after the final task. on_render_completed shows different wording: "Successfully rendered N video(s)!". When all tasks fail, last on_render_error -> _start_next_task -> cleanup -> "Completed processing" message. User sees success-toned wording even though every progress box is red.
- **Implication:** Mild user confusion in catastrophic-failure case. Progress boxes are red but message wording sounds successful.
- **Resolution:** Either (a) detect all-fail case in cleanup branch and show error-toned wording, OR (b) reword to neutral "Batch finished — see status column for results." Option (b) is simpler and accurate in all cases.
- **Trigger for pickup:** post-tag UX polish OR opportunistic during any future _start_next_task edit.

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

## B-012: ADR-0007 D7 implementation gap (Settings checkbox doesn't bundle preset+multipass)

- **Status:** scheduled (deferred per Step 4e-fix-4 2026-04-28; addressed in post-tag review)
- **Priority:** Low
- **Surfaced:** Step 4e-fix-3 PARALLEL audit (2026-04-28)
- **Context:** ADR-0007 D7 commentary specifies "Max Quality Mode bundles preset=p7 + multipass=2 + tune=hq into one user choice." Current implementation (settings_dialog.py L260 + core/preset_translator.py L122-123) only flips multipass; does NOT change preset to p7 or add tune=hq.
- **Implication:** Toggling "Max Quality Mode" checkbox in Settings produces multipass=2 but preserves whatever preset the user selected (default p4). User-facing behavior does not match ADR-0007 D7 commentary. Empirical impact is small per fix-3 data (Max Quality Mode produced <0.05 VMAF lift even when preset=p7 was applied via the orchestrator), so the gap is more about doc/code alignment than user-visible quality.
- **Resolution:** Either (a) update implementation to bundle preset+multipass+tune per D7 commentary, or (b) update D7 commentary in a future ADR to reflect current single-knob behavior. Decision deferred to post-tag review.
- **Trigger for pickup:** v2.5-complete tag landed.

## B-013: NVENC module constants wiring gap (declared but unused inside translate_to_nvenc)

- **Status:** scheduled (deferred per Step 4e-fix-4 2026-04-28; addressed in post-tag review)
- **Priority:** Low
- **Surfaced:** Step 4e-fix-3 PARALLEL audit (2026-04-28)
- **Context:** Step 4e-fix-3 added NVENC_PRESET_DEFAULT="p7" + NVENC_MULTIPASS_DEFAULT="2" module constants to core/preset_translator.py. These constants are documentation-only - the translate_to_nvenc body still uses kwarg defaults ("p4" / hardcoded "0"-or-"2" string literals based on max_quality_mode flag). Production gpu_preset default remains "p4" via separate config path (auto_render.py L85+L369 + settings_dialog.py L45).
- **Implication:** Future readers may assume the module constants drive production behavior; they do not. Either wire them in or remove them.
- **Resolution:** Either (a) make translate_to_nvenc default kwargs read from module constants, or (b) remove the unused constants and rely on the kwarg-default mechanism alone. Decision deferred to post-tag review.
- **Trigger for pickup:** v2.5-complete tag landed.

## Resolved
- **B-017** -- 11 Encoder.txt presets with stale Code/assets/data/ paths (10 Layer Overlay + 1 Line). Rewrote to assets/data/ in Encoder.txt; regenerated Encoder.json. Smoke-tested both Line + Layer Overlay (Bottom-Left) -- both render successfully on 5 input videos. Resolved [c60baf5] 2026-04-28.

- **B-001** — ADR-0001 missing Decision makers field. Resolved [df1125a] 2026-04-27.
- **B-002** — ADR-0002 status/date mismatch. Resolved [df1125a] 2026-04-27 (canonical date: 2026-04-22).
- **B-003** — ADR-0004 missing Date + Decision makers fields. Resolved [df1125a] 2026-04-27.
- **B-005** — ruff debt in auto_render.py (E722 bare except + F841 unused current_output). BACKLOG entry stated "7 errors"; 4 were live at fix time (5 silently fixed in earlier 2c-c-* commits; 2 additional F841 unused `original_filename` errors at lines 1160 + 1219 surfaced post-audit and were also fixed as minimum-fix scope expansion to satisfy `ruff check` exit 0). Resolved [df1125a] 2026-04-27.
