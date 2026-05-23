# Backlog

<!-- markdownlint-disable MD013 -->

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

- **Status:** Open — partial fix landed in commit `ffcf529` (Phase 1; the 5 GPU Pipeline keys are now rewired). The remaining ~3 keys (`num_threads`, `show_ffmpeg_command`, `open_output_when_done`) are still not re-read by `_reload_config_settings`.
- **Priority:** HIGH (functional gap surfaces if user changes GPU keys live)
- **Surfaced:** v2.5.1 PARALLEL audit on origin/main (2026-04-28)
- **Context:** auto_render.py `_reload_config_settings` (called after Settings dialog OK) historically only re-read `output_collision` + `gpu_error_action`. Stale comment said "Other Settings keys (use_gpu, nvenc_quality_offset, show_ffmpeg_command, open_output_when_done) reserved for Step 4c+ when GPU pipeline lands" — but Step 4c-4d-ii had shipped (GPU pipeline wired per CHANGELOG `[442d2eb]`). The comment never caught up.
- **Implication (original):** User toggles `gpu_enabled` in Settings → clicks OK → Settings dialog persists to disk → `_reload_config_settings` runs but does NOT update `self.gpu_enabled` → next render uses OLD (app-startup) value. Settings change for GPU/num_threads/output_dir keys requires app restart to take effect. PORT_NOTES line 99-101 says `_reload_config_settings` should "apply output dir, GPU toggle (gated by capability), all five runtime keys" — current impl honors 2 of those.
- **Resolution (post-partial-fix):** The 5 GPU Pipeline keys (`gpu_enabled`, `gpu_codec`, `gpu_preset`, `gpu_max_quality_mode`, `gpu_max_concurrent`) are now wired through `core.config.APP_DEFAULTS` and re-applied on Settings OK; `_gpu_semaphore` is rebuilt when `gpu_max_concurrent` changes. The remaining functional gap covers `num_threads` + `show_ffmpeg_command` + `open_output_when_done` — still requires an app restart to take effect. Extend `_reload_config_settings` for these three keys to fully close B-014.
- **Trigger for pickup:** user reports any of the remaining 3 keys "not taking effect" without an app restart, OR Phase 2.5 touches Settings dialog code path again.
- **Partial cleanup (2026-04-29, v2.5.3):** The stale `nvenc_quality_offset` reference in the `_reload_config_settings` comment block (`auto_render.py` L885) was removed.
- **Partial fix (2026-05-11, Phase 1 / `ffcf529`):** The 5 GPU Pipeline keys (`gpu_enabled`, `gpu_codec`, `gpu_preset`, `gpu_max_quality_mode`, `gpu_max_concurrent`) are now refreshed on Settings dialog OK without an app restart, sourced from `core.config.APP_DEFAULTS` for default values. `QSemaphore` is rebuilt only when `gpu_max_concurrent` actually changes; in-flight workers retain their existing semaphore reference. Pre-existing wiring for `output_collision` / `gpu_error_action` preserved. B-014 stays Open for the remaining 3 keys above.

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

## B-020: EncoderDialog "Group|Name" pipe-split doesn't .strip() halves [N51]

- **Status:** Open, backlog
- **Priority:** LOW (silent — affects only users who type whitespace adjacent to the pipe character)
- **Surfaced:** v2.5.3 audit (2026-04-30)
- **Locations:**
  - `auto_render.py:1841` (Add encoder handler)
  - `auto_render.py:1898` (Edit encoder handler)
- **Context:** Both Add and Edit handlers extract group and name from the EncoderDialog's name field via:

  ```python
  name_parts = dialog.result["name"].split("|", 1)
  group = name_parts[0] if len(name_parts) > 1 else ""
  name  = name_parts[1] if len(name_parts) > 1 else dialog.result["name"]
  ```

  Neither `name_parts[0]` nor `name_parts[1]` is `.strip()`ed. User input `"Test | My Preset"` yields `group="Test "` (trailing space) and `name=" My Preset"` (leading space). Group lookups elsewhere use exact string match and silently miss.

  `EncoderDialog.accept` (`auto_render.py:~2093`) already strips the OUTER whitespace of the full name field via `self.name_edit.text().strip()`, so this bug only affects whitespace immediately adjacent to the `|` character.

  Explicitly NOT affected: `core/preset_loader.py` L138/L144 Encoder.txt file-format parser — different semantics.
- **Resolution:** Apply `.strip()` to both halves of `name_parts` at both L1841 and L1898. Two-line fix per site.
- **Trigger for pickup:** Phase 2d UX phase, OR a user reports "my preset doesn't show under the right group", OR EncoderDialog gets touched for any other reason.

## B-021: Logging-to-UserData feature for all 4 apps

- **Status:** Open, scheduled (post-v3.8; v2.5.4 candidate)
- **Priority:** MEDIUM (logs currently scattered; portability gap; Junaid will likely touch this during Mac migration)
- **Surfaced:** v3.8 PyInstaller distribution build (2026-04-30)
- **Locations:**
  - `cutter.py:57` (`logging.basicConfig(filename="video_cutter.log", ...)`)
  - `merge.py:54` (`logging.basicConfig(filename="video_merge.log", ...)`)
  - `mixer.py:54` (`logging.basicConfig(filename="video_mixer.log", ...)`)
  - `auto_render.py` (no log file at all — see B-024)
- **Context:** Three of the four apps call `logging.basicConfig` at module-import time with a bare filename, which writes the log to the process CWD (typically the install dir next to the .exes). Users requested logs in `UserData/` for portability and to keep the install dir clean. The architectural challenge: `logging.basicConfig` runs at module import, BEFORE the per-instance `USER_DATA_DIR` is resolved via `resolve_or_die()` inside `__init__` (cutter.py L405, merge.py L716, mixer.py L296). This is an import-time-vs-init-time ordering problem. Three resolution options were considered during v3.8 planning: (a) Move `resolve_or_die()` to module level alongside `SCRIPT_DIR` so `USER_DATA_DIR` is available when `basicConfig` runs (caveat: error handler needs to work pre-QApplication); (b) Defer `basicConfig` until inside `__init__` after USER_DATA_DIR is known (caveat: any logging during module import goes to stdout/default); (c) Keep top-level `basicConfig` with a fallback location, then reconfigure root logger's FileHandler to point at `UserData/` after init (most robust but most complex). Verified during v3.8 smoke test: `video_mixer.log` (1 KB), `video_cutter.log` (0 KB), `video_merge.log` (0 KB) all appeared at install-dir top level alongside the .exes.
- **Resolution:** Pick one of options (a)/(b)/(c) above and apply consistently to cutter.py + merge.py + mixer.py. Combine with B-024 to add logging to auto_render.py at the same time. Test on clean machine that logs end up in `<install>/UserData/` when portable mode is active and in AppData when not.
- **Trigger for pickup:** v2.5.4 hygiene cycle, or natural moment when Junaid touches `core/user_data.py` for Mac platform branches (Phase 2.6 Mac migration).

## B-022: portable.txt detection not engaging in PyInstaller frozen builds

- **Status:** Open, scheduled (post-v3.8; v2.5.4 candidate)
- **Priority:** MEDIUM (portable mode shipped but is a no-op in frozen builds; teammate state lives in AppData by default which is unexpected given the ADR-0005 design)
- **Surfaced:** v3.8 PyInstaller distribution smoke test (2026-04-30)
- **Locations:**
  - `core/user_data.py` (`resolve_or_die`, `resolve_user_data_dir`)
  - Affected at runtime in all 4 apps that call `resolve_or_die(SCRIPT_DIR, ...)` from `__init__`
- **Context:** ADR-0005 specifies platformdirs default with `portable.txt` sentinel opt-in for portable mode. The sentinel mechanism works correctly in script (non-frozen) execution. In v3.8's PyInstaller frozen build (onedir mode), `portable.txt` was placed at the install dir top level (next to the .exes) as a true 0-byte file, but apps still wrote configs to `%LOCALAPPDATA%/1vmo-suite/` instead of `<install>/UserData/`. Verified by smoke test: `config_video_mixer.json` written to AppData (May 4 12:17), no `UserData/` folder created in install dir. Root cause: per PyInstaller runtime documentation, in a frozen onedir bundle the `__file__` attribute on imported modules resolves to the bundle's `_internal/` folder (not the install dir where the .exe lives). `SCRIPT_DIR` is computed via `Path(os.path.dirname(os.path.abspath(__file__)))`, so `SCRIPT_DIR/portable.txt` evaluates to a path inside `_internal/`, where the sentinel file does not exist. The actual .exe (and the co-located `portable.txt`) are at `Path(sys.executable).parent` in frozen mode.
- **Resolution:** In `core/user_data.py`, detect frozen state via `getattr(sys, 'frozen', False)`. When frozen, derive the install dir from `Path(sys.executable).parent` instead of trusting the caller's `SCRIPT_DIR`, and check `portable.txt` there. Either update `resolve_or_die`/`resolve_user_data_dir` to perform this detection internally (preferred — keeps callers ignorant of frozen-vs-script), or add a `_get_install_dir()` helper that callers use to compute the path passed in. Verify behavior in both script and frozen runs.
- **Trigger for pickup:** v2.5.4 hygiene cycle. Mac migration will also need similar `sys.frozen` handling in path resolution, so this is a natural pre-requisite.

## B-023: Mixer event handler `on_video_merge_started` naming inconsistency

- **Status:** Open, backlog
- **Priority:** LOW (internal Python naming only; no user-facing impact)
- **Surfaced:** v3.8 PyInstaller distribution audit (2026-04-30)
- **Locations:**
  - `mixer.py:971` (handler definition `def on_video_merge_started(...)`)
  - `mixer.py:1094` (signal connection `self._merge_coordinator.video_started.connect(self.on_video_merge_started)`)
- **Context:** Same copy-paste origin as the v3.8-fixed log/config filename typos (mixer.py was scaffolded from merge.py in early development; the `merge_` prefix was missed in three rename passes — log filename, config filename, and this handler name). The handler functions correctly because the signal-to-slot connection still resolves; the name is just misleading inside mixer's own module. Internal-only — no UI string, no external API consumer, no log output user-facing impact.
- **Resolution:** Rename `on_video_merge_started` to `on_video_mixer_started` at both sites (definition + signal connection). Two-line change. Group with any future mixer.py-touching commit for cleanup.
- **Trigger for pickup:** Opportunistic — any mixer.py edit that already touches that area, OR a focused `mixer.py` cleanup pass.

## B-024: auto_render.py has no log file (consistency gap)

- **Status:** Open, scheduled (combine with B-021 logging-to-UserData feature)
- **Priority:** LOW (informational gap; no functional break)
- **Surfaced:** v3.8 PyInstaller distribution audit (2026-04-30)
- **Locations:**
  - `auto_render.py` — no `logging.basicConfig` call anywhere in the module
- **Context:** cutter.py, merge.py, and mixer.py all call `logging.basicConfig(filename="video_<app>.log", ...)` at module level (around line 54-58). auto_render.py has no equivalent — it relies entirely on the in-UI FFmpeg output panel for runtime feedback and writes nothing to disk for log-style debugging. This is an inconsistency rather than a bug: when teammates report issues, they can attach video_cutter.log / video_merge.log / video_mixer.log but cannot attach a renderer-side log because none exists. Working around this requires asking teammates to copy/paste from the in-UI panel.
- **Resolution:** Add `logging.basicConfig(filename="video_renderer.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")` to auto_render.py at a parallel location (around line 54-58). The filename `video_renderer.log` matches the existing config filename convention (`config_video_renderer.json`). Combine with B-021 so all 4 apps gain UserData/-based logging in one cycle.
- **Trigger for pickup:** v2.5.4 hygiene cycle alongside B-021.

## B-025: Vietnamese docstrings in auto_render.py

- **Status:** Open, backlog
- **Priority:** LOW (docstrings only — not user-visible UI text)
- **Surfaced:** v3.8 PyInstaller distribution audit (2026-04-30); scope corrected during Codex post-completion review (2026-05-11) — the original entry undercounted.
- **Locations (full enumeration; line numbers reflect the current `phase2d-pyside6-migration` working tree):**
  - `auto_render.py:58`   `"""Lấy đường dẫn tuyệt đối cho tài nguyên, hoạt động cả khi chạy từ source và từ file exe"""`
  - `auto_render.py:806`  `"""Căn chỉnh kích thước các cột khi cửa sổ thay đổi kích thước"""`
  - `auto_render.py:835`  `"""Kiểm tra sự tồn tại của FFmpeg và FFprobe"""`
  - `auto_render.py:881`  `"""Tải cấu hình từ config_video_renderer.json nếu tồn tại."""`
  - `auto_render.py:1010` `"""Lưu cấu hình vào config_video_renderer.json."""`
  - `auto_render.py:1034` `"""Đọc các tùy chọn render từ file Encoder.txt và bỏ qua các dòng lỗi."""`
  - The `auto_render.py:831` QSS block also contains two inline Vietnamese stylesheet comments (`/* Thêm viền xanh */`, `/* Thêm padding */`) — stylesheet comments rather than docstrings, but readable as non-English if the goal is full English-ification.
  - The earlier "L857 / L954" pair was a partial snapshot from older line numbering and missed four other docstrings. Treat the list above as canonical.
- **Context:** Leftover from the original Vietnamese-language developer who authored the pre-v2 source. The 43 control-flow reconstruction artifacts from the pylingual decompile (commit a225831) addressed Python correctness; non-English docstrings survived because they were syntactically valid. cutter/merge/mixer were grep'd at audit time and appear English-only.
- **Resolution:** Translate the 6 docstrings above (and optionally the 2 QSS comments) to English. NOT a two-line change as originally described. Verify no other Vietnamese strings exist via a Unicode-range grep over the Vietnamese-extended-Latin block.
- **Trigger for pickup:** Opportunistic, OR before sharing the codebase with non-Vietnamese-reading contributors (which is now imminent with Junaid handoff).

## B-028: 4 onboarding/handoff .md files at repo root — Adam decision pending

- **Status:** Open, Adam decision pending. **Do NOT delete without Adam's explicit instruction.**
- **Priority:** LOW (docs only)
- **Surfaced:** Codex post-completion review (2026-05-11). 4 root-level Markdown files were added during Junaid's onboarding handoff but are NOT in the original Adam-spec 45-file manifest. They shipped in the `phase2d-pyside6-migration` branch's first commit and remain on main as of `58dec26`.
- **Files in scope (preserved as-is for now):**
  - `ONBOARDING.md`           — Junaid's onboarding orientation
  - `URL_DOWNLOADER_SPEC.md`  — spec doc paired with `core/url_downloader.py`
  - `WORKING_AGREEMENT.md`    — Junaid <-> Adam working agreement
  - `IDEAS_BACKLOG.md`        — open-form ideas list (mostly empty template)
- **Decision needed:**
  - (a) Keep all 4 on main (current state).
  - (b) Move all 4 to `docs/onboarding/` so they don't clutter the root.
  - (c) Move some, keep others. URL_DOWNLOADER_SPEC.md in particular makes a credible case to stay near root as the active spec until the feature lands in the UI.
  - (d) Delete some/all if Adam has alternative copies elsewhere and doesn't want them in the repo.
- **Resolution policy:** This is governance, not bug. No code or runtime impact. Picking (a) is currently in effect by default. Awaiting Adam's call.
- **Trigger for pickup:** Adam's review of the Phase 2d PR.

## B-027: `THAY_THẾ_NỘI_DUNG` literal placeholder in 2 built-in drawtext presets

- **Status:** Open, backlog
- **Priority:** LOW–MEDIUM (user-visible: the literal string renders into the output video if the user runs the preset as-is without editing the param)
- **Surfaced:** Codex post-completion review (2026-05-11) — searched `assets/Encoder.json` for non-ASCII content during the Vietnamese-strings sweep.
- **Locations:**
  - `assets/Encoder.json:1933` — drawtext filter param: `drawtext=fontfile=Arial:text='THAY_THẾ_NỘI_DUNG':x=(w-text_w)/2:y=(h-text_h)/1.05:fontsize=35:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=10`
  - `assets/Encoder.json:1944` — same shape, second placement (top vs bottom positioning).
- **Context:** `THAY_THẾ_NỘI_DUNG` translates roughly to "REPLACE_CONTENT" in Vietnamese. It is a literal placeholder baked into 2 built-in presets that draw a text overlay on the video. If a user picks one of these presets without manually editing the `text=...` argument first, the rendered video will literally show the Vietnamese phrase `THAY_THẾ_NỘI_DUNG` on screen — which is almost certainly never the intent.
- **Resolution options (no preset semantics change required):**
  - (a) Replace the placeholder with an English-language placeholder (e.g. `text='YOUR_TEXT_HERE'`) so the failure mode is at least readable.
  - (b) Add a UI hint / pre-flight check that warns when a selected preset still contains a known placeholder token (`THAY_THẾ_NỘI_DUNG`, `YOUR_TEXT_HERE`, etc.) and prompts the user to edit before render.
  - (c) Move the text content out of the preset and require the user to enter it explicitly per render.
- **Trigger for pickup:** When a user reports a rendered video containing the placeholder string, OR alongside B-025 Vietnamese cleanup, OR before Junaid's URL_DOWNLOADER feature lands its UI (since touching preset metadata is a related surface).

## B-026: PyInstaller spec files untracked in git

- **Status:** Open, backlog
- **Priority:** LOW (governance: undecided commit-vs-gitignore policy)
- **Surfaced:** v3.8 PyInstaller distribution build (2026-04-30)
- **Locations:**
  - `1vmo-suite.spec` (multipackage spec used for v3.8)
  - `auto_render.spec`, `cutter.spec`, `merge.spec`, `mixer.spec` (per-app specs, possibly stale)
- **Context:** Five `.spec` files exist in the project root but are not tracked in git (`git status` shows them as untracked). The `1vmo-suite.spec` is the canonical multipackage spec used to build v3.8 (encodes EXE names with version numbers, MERGE archive tuples, hidden-imports list, ffmpeg binary inclusion). Without it in git, future contributors cannot reproduce the build. Per-app .spec files appear to be older single-app variants from earlier experiments. Two valid policies exist: (a) commit `1vmo-suite.spec` as canonical build artifact, gitignore the per-app variants; (b) gitignore all `.spec` files and document the build via a script (`tools/build_dist.py` or similar) that generates the spec on demand.
- **Resolution:** Decide between (a) and (b). Option (a) is lower-effort and preserves the v3.8-tested spec verbatim. Option (b) is more flexible if build configurations diverge per platform (likely needed for Mac migration anyway). Update `.gitignore` accordingly and either commit `1vmo-suite.spec` or create the generator script.
- **Trigger for pickup:** Before Junaid attempts a from-scratch build, OR before Mac migration (Phase 2.6) where build configurations may diverge.

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

## B-029: empty_videos_hint label promises drag-drop that doesn't exist — RESOLVED

- **Status:** Resolved in Phase 2d production-hardening batch (Issue 4).
- **Resolution:** Implemented option (b) — `VideoRendererTool` now sets `setAcceptDrops(True)` and overrides `dragEnterEvent` / `dragMoveEvent` / `dropEvent` to accept local video file URLs (12-extension allowlist). Dropped paths flow through the same `self.videos` mutation as `select_videos`. Placeholder text also updated. Multi-file, unicode, spaces, and Windows backslash paths handled by `QUrl.toLocalFile`.

## B-030: self.output_mapping dict is dead state (write-only, never read)

- **Status:** Open, Low
- **Priority:** Low (technical debt)
- **Surfaced:** Runtime QA Stabilization audit 2026-05-14 (QA-4)
- **Context:** `auto_render.py` initialises `self.output_mapping = {}` (L725), clears it on every render start (L1957), and inserts `output_mapping[f"Processing - {basename}"] = item` at L2072. Nothing in the file ever reads back from this dict — `on_render_completed` and `on_render_error` route via `worker.tree_item` directly. The whole construct is dead state from an earlier design iteration.
- **Implication:** Harmless memory waste + reader confusion. Removable without behavior change.
- **Fix sketch:** Delete L725, L1957 `output_mapping.clear()`, L2072-2074 insertion. Verify py_compile + ruff + smoke. ~5 lines removed.
- **Trigger for pickup:** Next polish PR touching `start_render` / `_start_next_task`.

## B-031: closeEvent URL-cancel cannot be undone if user declines render-close

- **Status:** Open, Low
- **Priority:** Low (UX flaw, no data loss)
- **Surfaced:** Runtime QA Stabilization audit 2026-05-14 (QA-5)
- **Context:** `auto_render.py::closeEvent` (Phase 2d Bug 2 fix) prompts URL first, then render second. If the user confirms "Cancel URL and exit?" but then clicks No on "Render running, exit?", the URL worker is ALREADY cancelled / joined — there is no un-cancel path. User ends up with the render continuing but the URL batch lost.
- **Implication:** Worst case: user must re-issue the URL batch from scratch. Partial `.part` files from yt-dlp are still on disk so a manual resume is possible. Minor UX friction.
- **Fix sketch:** Either (a) ask the render question FIRST so a No there aborts the close before any URL cleanup happens, or (b) consolidate both into a single combined modal "URL download + render are in progress; cancel both and exit?". Option (a) is ~3 lines (reorder branches); (b) is ~10 lines plus a smoke test.
- **Trigger for pickup:** If users actually hit this in practice. Speculative until then.

## B-032: GPU semaphore acquire is unbounded under contention + cancel

- **Status:** Open, Low
- **Priority:** Low (technical debt; bounded externally by Phase 2d Item 7 thread.wait(5000))
- **Surfaced:** Runtime QA Stabilization audit 2026-05-14 (QA-6)
- **Context:** `auto_render.py::RenderWorker.process` acquires `self.gpu_semaphore` at L359 with bare `acquire()` (no timeout). If two workers contend for a `gpu_max_concurrent=1` semaphore and the holder is hung waiting on ffmpeg, the second waiter blocks. Cancel sets `is_cancelled=True` on both workers, but the second one is inside the blocking `acquire()` call and cannot poll the cancel flag until the holder finally releases. The 5s `thread.wait(5000)` cap in `cancel_render` (Phase 2d Item 7) prevents UI-thread freeze; worst case is a brief zombie worker that exits after the holder eventually releases.
- **Implication:** UI never freezes (existing Item 7 cap). The semaphore-blocked worker can outlive its parent thread by seconds in rare contention + cancel scenarios. Not observed in practice with the default `gpu_max_concurrent=2`.
- **Fix sketch:** Replace `acquire()` with a `tryAcquire(timeout_ms)` polling loop that also checks `self.is_cancelled` between attempts. ~10 lines + a smoke test for the cancel-during-acquire path.
- **Trigger for pickup:** A user report of a stuck worker on cancel, or a deliberate teardown of low-`gpu_max_concurrent` configurations.

## B-039: Phase 3 closure + handoff readiness — RESOLVED (Phase 3.7)

- **Status:** RESOLVED in Phase 3.7 (2026-05-22).
- **Resolution:** Verification-only milestone documented in [ADR-0014](docs/decisions/ADR-0014-phase-3-closure.md). Handoff doc set published under `docs/PHASE_3_*.md` + RELEASE_NOTES_PHASE_3.md + PHASE_4_READINESS_NOTES.md. Source gates captured in `tests/evidence/phase3-validation-2026-05-22.log`. Hardware-dependent QA rows honestly marked `[N]` in the RC checklist for Adam's host runs.

## B-038: Production packaging + local release readiness — RESOLVED (Phase 3.6)

- **Status:** RESOLVED in Phase 3.6 (2026-05-22) — partial. Build scripts + integrity checker shipped; PyInstaller spec edits + updater hardening deferred to follow-up patches.
- **Resolution (Phase 3.6):**
  - 4 new scripts under `tools/build/` (~700 LOC total): `generate_version_file.py`, `check_release_integrity.py`, `build_windows.py`, `build_macos.py`.
  - VERSION.txt flow: generator → `dist_version.txt` → build script copies → bundle's `VERSION.txt` → integrity check + future About dialog.
  - SHA256 checksums.txt: build_windows.py appends one line per artifact; teammate verification via `python3 tools/build/check_release_integrity.py <bundle>`.
  - Portable-first: zip is the primary artifact (CLAUDE.md §12 rule 5 honoured — extras re-copied after PyInstaller wipe).
  - macOS .app+.dmg authored with optional code-signing branch.
  - Documented in [ADR-0013](docs/decisions/ADR-0013-release-packaging.md).
- **Deferred items (Phase 3.6.x or Phase 4):**
  - `1vmo-suite.spec` edits for VERSION.txt embed + assets/* datas (currently the build script copies VERSION.txt post-build; in-spec datas is a future cleanup).
  - `1vmo-suite-macos.spec` sibling spec authoring (build_macos.py expects it; documented in RELEASE_MACOS.md when promoted).
  - `updater.py` hardening: SHA256 verify, `_pending/` extract, backup-before-swap, queue-running guard. Designed in ADR-0013 D5; wiring deferred.
  - `inno_setup_compile.py` for optional Windows installer.

## B-037: Local encoder intelligence layer — RESOLVED (Phase 3.5)

- **Status:** RESOLVED in Phase 3.5 (2026-05-22).
- **Priority:** MEDIUM (product feature; users had no in-app advisory for codec compatibility / NVENC session limits / fallback chains).
- **Resolution (Phase 3.5):**
  - New `core/encoder_intel/` package (4 modules, ~650 LOC). Pure-Python heuristics; no ML; no remote model.
  - Advisory-only — every codec switch goes through Phase 3.3's RecommendationDialog Confirm click. No forced switching.
  - 17 new smoke tests under `tests/smoke/test_encoder_intel.py`. ADR-0003 narrow exception extended per [ADR-0012](docs/decisions/ADR-0012-encoder-intelligence.md).
  - RenderWorker, ffmpeg invocation, gpu_detect (extended via duck-typed attribute access; not modified), preset_translator: all unchanged.
  - Deferred: runtime 1-frame probe-encode (needs real NVIDIA hardware in CI to validate) and Start-time pre-flight gate (kept additive this pass).

## B-036: Local orchestration / performance layer — RESOLVED (Phase 3.4)

- **Status:** RESOLVED in Phase 3.4 (2026-05-22).
- **Priority:** MEDIUM (product feature; users had no pause control, no per-task log persistence, no support-bundle export).
- **Resolution (Phase 3.4):**
  - New `core/orchestration/` package (8 modules, ~1100 LOC). Side-state file `queue_state.json` with its own `schema_version=1`; Phase 3.1 queue schema FROZEN.
  - Pause/Resume toolbar button. Current task never interrupted; only next-dispatch waits. Persisted across crashes.
  - Strict-opt-in retry policy (default OFF). Allow-list of retry-eligible Kinds is small; per-batch ceiling caps loops.
  - Per-task ffmpeg log persistence with 8 MB cap + last-N-batch rotation.
  - Cross-platform sleep inhibitor (Windows / macOS / Linux), degrades silently on missing-tool platforms.
  - psutil-optional system monitor sampler.
  - Diagnostic bundle exporter with config sanitization (strips `output_dir`, basenames-only `input_files`).
  - 33 new smoke tests. ADR-0003 narrow exception extended per [ADR-0011](docs/decisions/ADR-0011-orchestration.md).
  - RenderWorker, ffmpeg command construction, Phase 3.1 queue schema, scoring (Phase 3.2), optimization (Phase 3.3) all unchanged.

## B-035: Local optimization / recommendation layer — RESOLVED (Phase 3.3)

- **Status:** RESOLVED in Phase 3.3 (2026-05-22).
- **Priority:** MEDIUM (product feature; users had scores from Phase 3.2 but no in-app way to convert them into next-step guidance).
- **Surfaced:** Phase 3.3 design doc + Adam's no-destructive-automation rule (2026-05-22).
- **Resolution (Phase 3.3):**
  - New `core/optimization/` package (6 modules, ~700 LOC). Heuristic-only, no ML.
  - Recommendations are advisory; the user clicks Confirm in `_show_recommendation_dialog` before any re-render fires.
  - Re-renders go through the EXISTING `start_render` path; output filenames use the existing `naming_utils._v2` rotation so originals are preserved.
  - 39 smoke tests under `tests/smoke/test_quality_classifier.py`, `test_failure_classifier.py`, `test_recommender.py`, `test_batch_analyzer.py`. ADR-0003 narrow-pytest exception extended per [ADR-0010](docs/decisions/ADR-0010-render-optimization.md).
  - Single new toolbar button (🩺 Health) between Help and Updates. No auto-popups.

## B-034: Local originality / quality scoring system — RESOLVED (Phase 3.2)

- **Status:** RESOLVED in Phase 3.2 (2026-05-22).
- **Priority:** MEDIUM (product feature; previously the user had no in-app way to measure how close a render was to its source or how visually different it was for derivative-content use).
- **Surfaced:** Phase 3.2 design doc + Adam's local-only clarification (2026-05-22).
- **Context (pre-Phase-3.2):** Quality / originality measurement existed only in `bench.py` (a standalone CLI tool used by the team for VMAF validation rounds). End users had no way to score their own renders from inside the app. The product domain — making derivative video content that needs to be "different enough" while still acceptable quality — has no in-app diagnostic for either axis.
- **Resolution (Phase 3.2):**
  - New `core/scoring/` package — capability probe, four scoring axes (VMAF / SSIM / PSNR / dHash), pydantic v2 on-disk schema, and a local-only persistent cache (`scores.json` next to Phase 3.1's `queue.json` in `user_data_dir`).
  - Additive UI: three appended columns on `tree_output` (VMAF / pHash / SSIM), right-click context menu ("Score this render" / "Score selected" / "Score all rendered rows"), and a new "Scoring" tab in Settings with auto-score (default OFF), axis selection, max-parallel spinbox, and pHash-frames spinbox.
  - Local-only by construction: no network code in any scoring module, no remote upload, no remote model download, no account, no login. Mirrors Phase 3.1's local-first invariant verbatim.
  - RenderWorker, ffmpeg command generation, the Phase 3.1 queue store, the GPU semaphore, and `output_collision` semantics are all unchanged. Scoring lives on its own QThread pool and never contends with render threads.
  - 6 new smoke tests under `tests/smoke/` (34 cases) — ADR-0003 narrow-pytest exception extended per ADR-0009.
  - Documented in [ADR-0009](docs/decisions/ADR-0009-scoring-architecture.md).

## B-033: Persistent local queue + resume-from-interrupted-render — RESOLVED (Phase 3.1)

- **Status:** RESOLVED in Phase 3.1 (2026-05-22).
- **Priority:** MEDIUM (functional gap — prior to Phase 3.1 an unclean shutdown lost the entire in-progress batch with no recovery path).
- **Surfaced:** Phase 3.1 design doc + Adam's local-first clarification (2026-05-19).
- **Context (pre-Phase-3.1):** `auto_render.py` held batch state entirely in process memory (`self.all_tasks`, `self.completed_tasks`, `self.videos`, `self.selected_encoders`). Any of {app crash, OS panic, power loss, user-confirmed exit mid-render} discarded the entire batch with no path to resume the unrendered tasks. Users had to re-pick videos + presets + output dir + re-click Start.
- **Resolution (Phase 3.1):**
  - New `core/queue_models.py` (~95 LOC) — pydantic v2 schema for the on-disk batch, with `QUEUE_SCHEMA_VERSION = 1`, a 7-state `TaskStatus` enum, and `UNFINISHED_STATUSES` for the resume-decision predicate.
  - New `core/queue_store.py` (~260 LOC) — local-only JSON store with O_CREAT|O_EXCL file lock + 60s stale-lock reclaim + atomic write (reuses `core.atomic_write.save_json_atomic`) + schema-version rejection. `load()` never raises.
  - `auto_render.py` wiring is additive: a snapshot is persisted at `start_render`, transitions are recorded at `_start_next_task` (DISPATCHED), `on_render_completed` (COMPLETED + clear at batch terminal), `on_render_error` (FAILED), and `cancel_render` (CANCELLED + clear). `closeEvent` render-Yes branch keeps the file intact and demotes in-flight tasks to PENDING so the resume prompt at next launch sees them as outstanding work. RenderWorker contract / ffmpeg pipeline / GPU semaphore / output_collision semantics are unchanged.
  - Settings dialog: new Advanced-tab checkbox "Save queue for resume on next launch" persists `queue_persistence_enabled` (default True). Disabling it is reversible — all wiring is no-op when the flag is False.
  - Local-only by construction: queue file lives in the user's local `user_data_dir`, no network code, no auth, no remote endpoint.
  - Test coverage: `tests/smoke/test_queue_store.py` (16 cases) covers all 11 scenarios from the design doc §6.1 — ADR-0003 narrow-pytest exception (pure-IO unit, no Qt/ffmpeg/GPU, <2s, deterministic).

## B-040: gpu_detect HEVC gen-gate under-reports HEVC NVENC on Maxwell/Pascal (A4-class)

- **Status:** Open, backlog. **Do NOT fix in the current GPU fix-pass** — filed for a later, dedicated NVENC-gate pass.
- **Priority:** LOW–MEDIUM (HEVC GPU path silently hidden on Maxwell/Pascal cards that actually support it; same bug class as A4, one codec over).
- **Surfaced:** B-015 VERIFY review (2026-05-24), while confirming the A4 fix (`d438fb0`).
- **Locations:**
  - `gpu_detect.py` — `GPUGeneration.supports_hevc` (returns True only for Turing/Ampere/Ada/Blackwell, i.e. CC 7.5+)
  - `gpu_detect.py::detect()` — `caps.hevc_available = hw_supports_hevc and codecs.hevc`
- **Context:** `supports_hevc` gates HEVC to Turing-and-newer. But ADR-0007 D5 (line 149) states "NVENC works on any NVIDIA GPU from Maxwell (2014) forward; h264_nvenc and hevc_nvenc are universal across that range." NVIDIA hardware sides with the ADR: 2nd-gen Maxwell (GM206, GTX 950/960) and all Pascal (GTX 10xx) ship HEVC NVENC encoders. So a Maxwell/Pascal card with `hevc_nvenc` present in ffmpeg is wrongly reported `hevc_available=False`, hiding the HEVC GPU path. This is the exact A4 bug class (hardware gate too strict relative to the real ffmpeg-probe signal), shifted from H.264 to HEVC.
- **Nuance (why this is not a trivial one-liner):** the floor is not simply "all PRE_TURING". 1st-gen Maxwell (GM107) and Kepler lack HEVC NVENC, so blindly enabling HEVC for the whole `PRE_TURING` bucket would over-report. The robust fix likely mirrors A4 by leaning on the ffmpeg `codecs.hevc` probe as the real capability signal (the probe already reflects what THIS build/GPU exposes), rather than widening the hardware-generation gate alone. NVENC is high-risk per CLAUDE.md §13 — needs a repro test and care.
- **Wrong assumption to correct WHEN B-040 is fixed:** the A4 fix embedded the inaccurate premise that Maxwell/Pascal have "no HEVC". When fixing B-040, correct that wording in two places so the repo stops shipping the wrong premise:
  - the A4 CHANGELOG entry under `[Unreleased]` ### Fixed ("Pascal/Maxwell — H.264-capable, no HEVC"),
  - the A4 test docstrings/comments in `tests/smoke/test_gpu_detect.py` (`test_h264_decoupled_from_hevc_on_pre_turing` says "no HEVC hardware support" / "Pascal genuinely lacks HEVC NVENC"). The A4 *test assertions* stay valid (the PRE_TURING fixture uses CC 6.1 with `hevc=False` in the mocked ffmpeg probe, so `hevc_available=False` is correct for that fixture); only the prose rationale is wrong.
- **Resolution sketch:** rework the HEVC gate to honor the ffmpeg `codecs.hevc` probe for the HEVC-capable pre-Turing range (mirroring A4's H.264 decoupling), add a repro test (Maxwell/Pascal-class fixture + `hevc=True` → `hevc_available=True`), and correct the two A4 wording sites above in the same commit.
- **Trigger for pickup:** a user on a Maxwell/Pascal card reports HEVC GPU encoding unavailable, OR a focused `gpu_detect` generation-gate pass.

## B-041: "5s Cycle Zoom" preset has stray shell double-quotes that reach ffmpeg literally

- **Status:** Open, backlog. Surfaced during the #6 tokenizer investigation (2026-05-24). Adam to decide whether to fix this session. **Not fixed by #6** (tokenizer scope; see below).
- **Priority:** MEDIUM (the preset fails to render — ffmpeg rejects the filtergraph).
- **Locations:**
  - `assets/Encoder.txt` L43 ("5s Cycle Zoom")
  - `assets/Encoder.json` (generated from Encoder.txt; the same token is embedded in its `params` list)
- **Context:** L43's command is `-vf "scale=iw*1.5:ih*1.5,zoompan=z='…':…:s='iw*1.5:ih*1.5'" -c:a copy …` — the whole `-vf` value is wrapped in shell-style **double** quotes. The app tokenizes via `code.split()` and invokes ffmpeg via `subprocess` **list** form (no shell), so the literal `"` characters are never stripped by a shell — they reach ffmpeg as part of the argv token. ffmpeg's filtergraph parser does not treat `"` as a quote char (it uses `'` and `\`), so it sees a filter named `"scale…` → "No such filter" → the preset fails. The inner single quotes (`zoompan=z='…'`) are correct ffmpeg quoting and must stay. (Broken by inspection; a live render would confirm the exact error.)
- **Why #6 does NOT fix it:** #6 is a tokenizer change. Per the #6 investigation, neither `code.split()` nor `shlex.split(posix=False)` removes these outer double-quotes; `shlex.split(posix=True)` would remove them but regresses other presets by stripping ffmpeg's own single-quotes (e.g. the `enable='lt(mod(t,10),1)*gte(t,0)'` in "Cut & Overlay 1s per 10s"). The correct fix is a **content** fix, not a tokenizer fix.
- **Resolution sketch:** In `assets/Encoder.txt` L43, drop only the outer double-quotes — `-vf "scale=…s='iw*1.5:ih*1.5'"` → `-vf scale=…s='iw*1.5:ih*1.5'` — keeping the inner zoompan single-quotes. Regenerate `assets/Encoder.json` via `tools/generate_encoder_json.py`. Verify with a live render that the filtergraph is accepted. The #6 tokenizer sweep found only L43 with this outer-double-quote pattern; re-confirm none others before/after.
- **Trigger for pickup:** a user reports "5s Cycle Zoom" fails to render, OR Adam authorizes the content fix.

## B-042: preset_loader tokenizer code.split() vs shlex (fix-pass item #6) — CLOSED (won't-fix)

- **Status:** CLOSED — won't-fix (2026-05-24). No code change to `core/preset_loader.py`.
- **Origin:** Phase-3 fix-pass item #6 ("preset_loader.py:161 uses `tuple(code.split())`, which breaks presets with quoted args; switch to `shlex.split`").
- **Investigation (all 106 Encoder.txt presets tokenized both ways):**
  - `code.split()` mis-splits a preset ONLY when a quoted value contains a literal space (e.g. `text='hello world'`). NO shipping preset has that, so `split()` mis-tokenizes nothing today — the bug is **latent**, not active.
  - `shlex.split(code)` (posix=True) **strips** quote characters. ffmpeg filtergraph quoting (`enable='lt(mod(t,10),1)*gte(t,0)'`, `zoompan=z='…'`, drawtext `text='…'`) is parsed BY ffmpeg, so those quotes must remain in the argv token (the app invokes ffmpeg via `subprocess` list form — no shell strips them). posix=True would therefore **regress** such presets (e.g. "Cut & Overlay 1s per 10s": the commas in the `enable` expression get exposed → filtergraph breaks).
  - `shlex.split(code, posix=False)` keeps quotes but only groups across spaces for token-**boundary** quotes (`'a b'`). ffmpeg presets use **embedded** quotes (`key='a b'`), for which posix=False tokenizes IDENTICALLY to `split()` — verified equal on all 106 presets and on the embedded-quote latent case. So posix=False is a **no-op**.
- **Decision (rationale):** `code.split()` is the correct model for ffmpeg's quoting — the quote characters belong IN the argv token and ffmpeg parses them itself. `shlex` models SHELL quoting, the wrong layer: it either strips the quotes ffmpeg needs (posix=True regression) or does nothing useful (posix=False no-op). Switching is inappropriate. The latent "space inside a quoted value" risk is real but theoretical (no preset triggers it).
- **Future work (out of scope):** if first-class arbitrary-quoted-arg support is ever needed, write an ffmpeg-**aware** tokenizer that splits on whitespace while respecting `'…'` and `\` escaping AND retains the quote characters. That is a new component with its own design + tests, not a one-line `code.split()` swap.
- **Preset-authoring guideline (interim mitigation):** when authoring Encoder.txt preset commands, do NOT place a literal space inside a quoted ffmpeg value, and do NOT wrap a whole value in shell-style double-quotes (see B-041). Keep ffmpeg's own `'…'` quoting for expressions containing `:` or `,`.
- **Surfaced/closed by:** Phase-3 fix-pass #6 investigation, 2026-05-24.

## Resolved

- **B-017** -- 11 Encoder.txt presets with stale Code/assets/data/ paths (10 Layer Overlay + 1 Line). Rewrote to assets/data/ in Encoder.txt; regenerated Encoder.json. Smoke-tested both Line + Layer Overlay (Bottom-Left) -- both render successfully on 5 input videos. Resolved [c60baf5] 2026-04-28.

- **B-001** — ADR-0001 missing Decision makers field. Resolved [df1125a] 2026-04-27.
- **B-002** — ADR-0002 status/date mismatch. Resolved [df1125a] 2026-04-27 (canonical date: 2026-04-22).
- **B-003** — ADR-0004 missing Date + Decision makers fields. Resolved [df1125a] 2026-04-27.
- **B-005** — ruff debt in auto_render.py (E722 bare except + F841 unused current_output). BACKLOG entry stated "7 errors"; 4 were live at fix time (5 silently fixed in earlier 2c-c-* commits; 2 additional F841 unused `original_filename` errors at lines 1160 + 1219 surfaced post-audit and were also fixed as minimum-fix scope expansion to satisfy `ruff check` exit 0). Resolved [df1125a] 2026-04-27.
