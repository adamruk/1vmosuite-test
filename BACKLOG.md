# Backlog

<!-- markdownlint-disable MD013 -->

Deferred audit-fix items, surfaced during the toolchain install (commits 5e7e8c9 + dc0747c) on 2026-04-26. Strategy: defer-with-tracking. This is an ongoing cross-phase tracker — Phase 2, 2.5, and 3 have shipped, and items are resolved or explicitly carried forward to a named future phase as the project advances.

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

- Items resolved: move to the "Resolved" section at bottom with commit hash and date. Routine closures collapse to one line; entries whose reasoning is the only surviving record (postmortems / won't-fix rationale) relocate in full.
- New deferrals: append here with a new B-NNN ID. B-NNN IDs are never reused or renumbered.
- Ongoing cross-phase hygiene: every B-NNN is resolved or explicitly carried forward to a named future phase. No B-NNN is silently dropped.

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

## B-031: closeEvent URL-cancel cannot be undone if user declines render-close

- **Status:** Open, Low
- **Priority:** Low (UX flaw, no data loss)
- **Surfaced:** Runtime QA Stabilization audit 2026-05-14 (QA-5)
- **Context:** `auto_render.py::closeEvent` (Phase 2d Bug 2 fix) prompts URL first, then render second. If the user confirms "Cancel URL and exit?" but then clicks No on "Render running, exit?", the URL worker is ALREADY cancelled / joined — there is no un-cancel path. User ends up with the render continuing but the URL batch lost.
- **Implication:** Worst case: user must re-issue the URL batch from scratch. Partial `.part` files from yt-dlp are still on disk so a manual resume is possible. Minor UX friction.
- **Fix sketch:** Either (a) ask the render question FIRST so a No there aborts the close before any URL cleanup happens, or (b) consolidate both into a single combined modal "URL download + render are in progress; cancel both and exit?". Option (a) is ~3 lines (reorder branches); (b) is ~10 lines plus a smoke test.
- **Trigger for pickup:** If users actually hit this in practice. Speculative until then.

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

## B-044: Bundle Deno + yt-dlp-ejs for the frozen .exe build

- **Status:** Open, deferred to the packaging phase. **Blocks the `.exe` release, NOT source-mode use** — source/dev runs resolve a system Deno via PATH (or degrade gracefully), so this is only required to make the frozen build self-contained.
- **Priority:** MEDIUM (YouTube extraction fails in the frozen `.exe` without it; no impact on source-mode runs or non-YouTube sites).
- **Surfaced:** Phase A url_downloader hardening, C4 (`_resolve_bundled_js_runtime`), merged in [124ea1d] (2026-05-24).
- **Depends on:** C4 resolver `_resolve_bundled_js_runtime` in `core/url_downloader.py` (mirrors `_resolve_bundled_ffmpeg_dir`: checks `sys._MEIPASS` then repo root for `deno(.exe)`, prepends its dir to PATH at import). The resolver is already merged; this item is the build-side work that puts a Deno binary + the EJS scripts where the resolver and yt-dlp can find them in a frozen bundle.
- **Context:** Modern yt-dlp needs a JavaScript runtime (Deno) to solve the JS "n-sig"/PO-token challenges YouTube now requires; the C4 resolver finds a bundled Deno at runtime but nothing yet bundles one for the frozen build. Without BOTH the Deno binary AND the `yt_dlp_ejs` challenge scripts present in `dist/`, YouTube downloads degrade or fail in the `.exe` even when Deno is present.
- **Checklist:**
  - Pinned Deno fetch-at-build: pull a pinned Deno 2.x — the **full `deno`**, NOT `denort`; gitignore the ~40MB+ binary; stage it the same way the bundled ffmpeg is staged.
  - `.spec`: add `deno.exe` to `binaries=` at the **same `_MEIPASS` destination as ffmpeg** so the resolver's `_MEIPASS` lookup finds it.
  - `.spec`: `collect_all('yt_dlp_ejs')` — without the EJS `.js` in `dist/`, YouTube fails in the `.exe` even with Deno present; verify the `.js` actually land in `dist/`.
  - Wire the Deno fetch to run **before** PyInstaller in the build pipeline.
  - **Verify by frozen-`.exe` YouTube extraction** — the only thing that proves the bundled `_MEIPASS` path works end-to-end (a source-mode pass does not).
- **ADR:** [ADR-0016](docs/decisions/ADR-0016-bundle-deno-js-runtime.md) records the bundle-a-JS-runtime decision (size cost, Deno pinning policy, why full `deno` over `denort`); the checklist above is that ADR's implementation checklist.
- **Trigger for pickup:** the packaging / frozen-build phase, OR a teammate reports YouTube extraction failing in the `.exe`.
- **Note — ffmpeg is the template, not new work.** ffmpeg is already bundled into the build (ADR-0013 D4 integrity check + `_resolve_bundled_ffmpeg_dir` in core/url_downloader.py). Deno bundling copies that exact pattern: same staging location, same `_MEIPASS` dest. At packaging time, ONE frozen-build verification confirms BOTH ship inside the `.exe` — a real YouTube extraction (proves Deno + yt_dlp_ejs) AND a real NVENC render (proves ffmpeg). Don't re-invent ffmpeg's bundling; mirror it.

## B-045: curl-cffi needed for TikTok impersonation in online tests

- **Status:** Open, environmental — NOT a code defect in C1–C8 or the C4 Deno work.
- **Priority:** LOW (affects only the online TikTok test legs in environments without `curl-cffi`; shipped per-URL download behavior is unaffected — a missing impersonation target surfaces as a normal failed `DownloadResult`, not a crash).
- **Surfaced:** Phase A online tests, [124ea1d] (2026-05-24).
- **Locations:**
  - `tests/smoke/test_url_downloader.py` — `test_tiktok_downloads_watermark_free`, and the TikTok leg of `test_mixed_batch_returns_correct_per_url_outcomes`.
- **Context:** Both TikTok online tests fail with yt-dlp "attempting impersonation, but no impersonate target available" — yt-dlp's TikTok extractor needs `curl-cffi` to impersonate a browser TLS fingerprint. This is an environment/dependency gap, unrelated to the C1–C8 hardening or C4 Deno bundling.
- **Resolution (pick one):**
  - Add `curl-cffi` to `requirements.txt` (provides the impersonation target the TikTok extractor wants), OR
  - Mark those two test legs as requiring impersonation deps (skip/xfail when `curl-cffi` is absent) so the suite is honest about the prerequisite.
- **Trigger for pickup:** when TikTok online coverage needs to pass in CI / a fresh env, OR alongside the next `requirements.txt` dependency review.

## B-047: pre-commit hooks not installed on this host (guards run only when invoked manually)

- **Status:** Open, backlog
- **Priority:** LOW (the guards work when run by hand; the risk is forgetting to run them)
- **Surfaced:** backlog-batch-1 MAIN session (2026-05-24)
- **Context:** `.git/hooks/` contains only the stock `*.sample` files and `pre-commit` is not on PATH, so the configured guards (markdownlint, `check-changelog`, `check_adr_references`, ruff-format) only run when invoked manually — they are NOT enforced at commit time. Additionally `markdownlint` is not installed at all on this host (no binary, no `pymarkdown` module), so the markdown lint gate could not be run during this batch; `ruff` is only reachable via `python -m ruff` (not a bare `ruff` on PATH).
- **Resolution:** run `pre-commit install` to wire the hooks into `.git/hooks/`; document the step in `setup.ps1` so a fresh clone gets them. Optionally add a markdownlint provider (npm `markdownlint-cli` or `pymarkdown`) to the dev-tooling docs so the markdown gate is actually runnable.
- **Trigger for pickup:** next toolchain/setup hygiene cycle, OR the first time a guard-violating commit slips through because the hook was not enforced.

## B-048: `show_ffmpeg_command` + `open_output_when_done` Settings have no consumer (split from B-014)

- **Status:** Open, backlog
- **Priority:** LOW–MEDIUM (two Settings toggles are inert — they persist but never change behavior)
- **Surfaced:** backlog-batch-1 MAIN session (2026-05-24), while verifying B-014
- **Context:** B-014's reload scope is closed — `_reload_config_settings` now re-reads `num_threads`, `show_ffmpeg_command`, and `open_output_when_done` on Settings OK. But a repo-wide search shows `show_ffmpeg_command` and `open_output_when_done` are only ever *written* (persisted by `settings_dialog.py`, copied into `self.config` by `_reload_config_settings`) and never *read* by the render flow. So toggling either checkbox in Settings currently does nothing: the FFmpeg command-line echo is not gated on `show_ffmpeg_command`, and the output folder is not auto-opened on completion when `open_output_when_done` is set. (`num_threads` is genuinely consumed, so it is unaffected.) Separately, the `_reload_config_settings` docstring (`auto_render.py` ~L1781) still says these three keys are "NOT rewired here", directly contradicting the closure code below it (added in baseline `f4cf89a`) — a stale docstring to correct when this is picked up.
- **Resolution:** decide per key whether the feature is wanted — either (a) implement the consumers (gate the FFmpeg-command echo on `show_ffmpeg_command`; call the existing `open_output_directory()` path on completion when `open_output_when_done` is true), or (b) remove the dead Settings checkboxes + their persistence if the features are not wanted. Either way, correct the contradictory `_reload_config_settings` docstring.
- **Trigger for pickup:** a user reports "Show FFmpeg command" / "Open output when done" doesn't do anything, OR the next Settings-dialog touch.

## B-049: `mixer.py` main-window class is named `VideoMergerTool` (copy-paste residue)

- **Status:** Open, backlog
- **Priority:** LOW (internal Python naming only; no user-facing impact)
- **Surfaced:** backlog-batch-1 MAIN session (2026-05-24), while fixing B-023
- **Context:** Same copy-paste origin as B-023 — `mixer.py` was scaffolded from `merge.py`, and the main-window class declared at `mixer.py:293` is `class VideoMergerTool(QMainWindow)` rather than a mixer-specific name. The app works (the class is internally consistent), but the `Merger` name is misleading inside the mixer module, exactly like the B-023 handler-name case. NOT fixed in B-023 (out of that commit's one-issue scope).
- **Resolution:** rename the class to a mixer-appropriate name (e.g. `VideoMixerTool`) and update its references within `mixer.py`. Confirm no other module imports the class by name. Group with any future `mixer.py`-touching commit.
- **Trigger for pickup:** opportunistic — any `mixer.py` edit in that area, OR a focused mixer cleanup pass.

## B-050: manager-review overwrites RESULTS.md instead of appending (clobbers audit history)

- **Status:** Open, backlog.
- **Priority:** MEDIUM-HIGH (silent audit-history loss on every VERIFY/gate run).
- **Surfaced:** backlog-batch-1 close-out (2026-05-24).
- **Context:** The `manager-review` skill writes RESULTS.md by truncate-and-replace. Each VERIFY run therefore wipes the prior cumulative audit log. Confirmed: the batch-1 verdict replaced 672 lines of Phase 3 + Phase A history in commit `7318ae4`; manually restored (verdict grafted on top of the full history) in commit `c156d4d`. Without a skill fix, the NEXT VERIFY run repeats the clobber.
- **Resolution (pick one):**
  - (a) Skill reads existing RESULTS.md, PREPENDS a new dated verdict block, writes back (never truncate); or
  - (b) Skill writes per-run files `RESULTS-<branch>-<YYYYMMDD>.md` and keeps RESULTS.md as an index.
  - Either way: add a guard/test that a second consecutive run does not reduce RESULTS.md line count.
- **Trigger for pickup:** before the next VERIFY/manager-review run (otherwise batch-2's gate clobbers batch-1's verdict), OR a dedicated gate-hardening pass.

## Resolved

- **B-015** — translate_to_nvenc codec routing: codified single-knob routing (user's gpu_codec wins over per-preset map) and removed the dead `mapped` variable; corrected the `_CODEC_MAP` "per ADR-0007 D4" mis-citation (D4 is the codec dropdown, not routing). Resolved [c051473], documented in [ADR-0015](docs/decisions/ADR-0015-nvenc-codec-routing.md). 2026-05-24.

- **B-017** -- 11 Encoder.txt presets with stale Code/assets/data/ paths (10 Layer Overlay + 1 Line). Rewrote to assets/data/ in Encoder.txt; regenerated Encoder.json. Smoke-tested both Line + Layer Overlay (Bottom-Left) -- both render successfully on 5 input videos. Resolved [c60baf5] 2026-04-28.

- **B-001** — ADR-0001 missing Decision makers field. Resolved [df1125a] 2026-04-27.
- **B-002** — ADR-0002 status/date mismatch. Resolved [df1125a] 2026-04-27 (canonical date: 2026-04-22).
- **B-003** — ADR-0004 missing Date + Decision makers fields. Resolved [df1125a] 2026-04-27.
- **B-005** — ruff debt in auto_render.py (E722 bare except + F841 unused current_output). BACKLOG entry stated "7 errors"; 4 were live at fix time (5 silently fixed in earlier 2c-c-* commits; 2 additional F841 unused `original_filename` errors at lines 1160 + 1219 surfaced post-audit and were also fixed as minimum-fix scope expansion to satisfy `ruff check` exit 0). Resolved [df1125a] 2026-04-27.
- **B-029** — empty_videos_hint label promised drag-drop that didn't exist; added `setAcceptDrops` + drag/drop handlers (12-extension allowlist). Resolved in Phase 2d production-hardening (Issue 4).
- **B-033** — Persistent local queue + resume-from-interrupted-render (`core/queue_models.py` + `core/queue_store.py`; 16 smoke cases). Resolved in Phase 3.1 (2026-05-22).
- **B-034** — Local originality / quality scoring system (`core/scoring/`; VMAF / SSIM / PSNR / dHash). Resolved in Phase 3.2 (2026-05-22). See [ADR-0009](docs/decisions/ADR-0009-scoring-architecture.md).
- **B-035** — Local optimization / recommendation layer (`core/optimization/`; advisory-only, Confirm-gated). Resolved in Phase 3.3 (2026-05-22). See [ADR-0010](docs/decisions/ADR-0010-render-optimization.md).
- **B-036** — Local orchestration / performance layer (`core/orchestration/`; pause/resume, retry, diagnostics). Resolved in Phase 3.4 (2026-05-22). See [ADR-0011](docs/decisions/ADR-0011-orchestration.md).
- **B-037** — Local encoder intelligence layer (`core/encoder_intel/`; pure-Python advisories). Resolved in Phase 3.5 (2026-05-22). See [ADR-0012](docs/decisions/ADR-0012-encoder-intelligence.md).
- **B-038** — Production packaging + local release readiness (build scripts + integrity checker under `tools/build/`; partial — spec/updater hardening deferred). Resolved in Phase 3.6 (2026-05-22). See [ADR-0013](docs/decisions/ADR-0013-release-packaging.md).
- **B-039** — Phase 3 closure + handoff readiness (verification-only milestone; `docs/PHASE_3_*` handoff set). Resolved in Phase 3.7 (2026-05-22). See [ADR-0014](docs/decisions/ADR-0014-phase-3-closure.md).
- **B-016** — `start_render` resets the visible per-worker QProgressBar to 0 at batch start; found already fixed by the Phase 2d Issue 7 hardening (a `thread_bars[i].setValue(0)` loop alongside the `_worker_state` reset). Confirmed already-resolved during batch-1, no new commit. 2026-05-24.
- **B-014** — `_reload_config_settings` now re-reads `num_threads` + `show_ffmpeg_command` + `open_output_when_done` on Settings OK (no app restart); found already wired in baseline [f4cf89a] (reload scope closed; `num_threads` genuinely takes effect). Batch-1 verification confirmed it; no new commit. The *consumer* gap (`show_ffmpeg_command` / `open_output_when_done` persist but nothing in the render flow reads them) + the now-contradictory docstring are split out to B-048. Resolved (reload scope) 2026-05-24.
- **B-046** — `scripts/check_adr_references.py` self-exclusion failed on Windows (`str(p)` backslash paths vs forward-slash substrings) → false exit 1; normalized via `Path.as_posix()`. Test `tests/smoke/test_check_adr_references.py`. Resolved [aedc37c] 2026-05-24.
- **B-023** — mixer slot `on_video_merge_started` renamed to `on_video_mixer_started` (def + `per_video_started.connect` site). Internal only. Resolved [fc26a70] 2026-05-24.
- **B-019** — all-fail batch no longer shows success-toned "Completed processing N video(s)!" / "Success"; terminal-cleanup branch reworded to neutral "Batch Finished" / "Batch finished — see status column for results." Resolved [c23461d] 2026-05-24.
- **B-030** — write-only `output_mapping` dead state removed (init + 2 clears + insert) and the stale `_row_ref_distorted` comment corrected; completion routes via `worker.tree_item`. No behavior change. Resolved [e7cd2b1] 2026-05-24.
- **B-018** — added an always-enabled "Clone" button so a read-only built-in preset (ADR-0006) can be copied into an editable `user:<slug>` preset; id-derivation factored into the pure `_allocate_user_preset_id` (shared by Add/Clone). Read-only tooltips (part a) had already shipped. Test `tests/smoke/test_clone_preset_id.py` + headless UI smoke; dialog rename + save MANUAL-VERIFIED. Resolved [8080631] 2026-05-24.
- **B-020** — `EncoderDialog` "Group|Name" pipe-split now strips both halves via the pure `_split_group_name` (Add/Clone helper + Edit handler), so whitespace adjacent to the pipe no longer breaks exact-match group lookups. Test `tests/smoke/test_split_group_name.py`. Resolved [cf8ef1a] 2026-05-24.

### B-032: GPU semaphore acquire is unbounded under contention + cancel

- **Status:** RESOLVED [b8f3cb1] 2026-05-24 — bounded cancellable acquire via module-level `_acquire_gpu_slot()` (tryAcquire+cancel-poll); `finally` releases only a held slot. Headless test `tests/smoke/test_gpu_semaphore_cancel.py`; live cancel-mid-NVENC is MANUAL-VERIFIED.
- **Status (original):** Open, Low
- **Priority:** Low (technical debt; bounded externally by Phase 2d Item 7 thread.wait(5000))
- **Surfaced:** Runtime QA Stabilization audit 2026-05-14 (QA-6)
- **Context:** `auto_render.py::RenderWorker.process` acquires `self.gpu_semaphore` at L359 with bare `acquire()` (no timeout). If two workers contend for a `gpu_max_concurrent=1` semaphore and the holder is hung waiting on ffmpeg, the second waiter blocks. Cancel sets `is_cancelled=True` on both workers, but the second one is inside the blocking `acquire()` call and cannot poll the cancel flag until the holder finally releases. The 5s `thread.wait(5000)` cap in `cancel_render` (Phase 2d Item 7) prevents UI-thread freeze; worst case is a brief zombie worker that exits after the holder eventually releases.
- **Implication:** UI never freezes (existing Item 7 cap). The semaphore-blocked worker can outlive its parent thread by seconds in rare contention + cancel scenarios. Not observed in practice with the default `gpu_max_concurrent=2`.
- **Fix sketch:** Replace `acquire()` with a `tryAcquire(timeout_ms)` polling loop that also checks `self.is_cancelled` between attempts. ~10 lines + a smoke test for the cancel-during-acquire path.
- **Trigger for pickup:** A user report of a stuck worker on cancel, or a deliberate teardown of low-`gpu_max_concurrent` configurations.

### B-041: "5s Cycle Zoom" preset has stray shell double-quotes that reach ffmpeg literally

- **Status:** **RESOLVED [ccd6b36]** 2026-05-24 — live RTX 4080 render verified (zoom cycles correctly: 3s normal → 1s 1.25× → 1s 1.5×, centered; audio/output valid, A/V in sync). The double-quote removal in `ea7a67d` was correct but **INCOMPLETE**: a live render on the RTX 4080 (VERIFY session) showed the preset still failed — `ffmpeg rc=-22`, `[AVFilterGraph] No option name near 'ih*1.5'`, filterchain parse error, no output. `ea7a67d` only peeled the outer shell-double-quote layer (changed the error from "No such filter" to a deeper filtergraph error); it did not make the preset renderable. The earlier "RESOLVED [ea7a67d] … Live render is MANUAL-VERIFIED" status was premature (render correctness had NOT actually been verified at that point).
  - **Root cause 1 (parse):** `zoompan=…:s='iw*1.5:ih*1.5'` — zoompan's `s=` (output size) is parsed by `av_parse_video_size` and accepts only a literal `WxH`, never `iw`/`ih` expressions; additionally the `:` inside the single-quoted value is not honored, so the option string splits on it → "No option name near 'ih*1.5'".
  - **Root cause 2 (runtime):** the `z`/`x`/`y` expressions use `mod(t,5)`, but **`t` is not a zoompan variable** — the timestamp variable in zoompan is `time`. With `t`, even after fixing `s=`, the filter fails at runtime (`Invalid argument` / "Nothing was written"). Verified by isolation: `…mod(time,5)…` renders, `…mod(t,5)…` fails.
  - **Root cause 3 (A/V desync):** `zoompan` defaults to **25 fps**, so a 30 fps source rendered at 25 fps → video 7.2 s vs copied audio 6.0 s (1.2 s desync, ~20% slow-motion). Surfaced once the preset actually rendered.
  - **Fix applied (3 edits + fps), headless render-validated:** `mod(t,5)` → `mod(time,5)` (×2 in `z`); `s='iw*1.5:ih*1.5'` → literal `s=576x1024` (matching sibling Zoom presets 1.1x/1.2x CRF); appended `:fps=30` to `zoompan` (restores 30 fps, video duration == audio duration, A/V delta 0.000s). `time` was verified on the bundled ffmpeg to drive the cycle correctly (zoom area ratios match z² within ~2%, transitions at 3s/4s; `it` lagged, `t` failed). Pre-scale `scale=iw*1.5:ih*1.5` kept (smoothness guard). `assets/Encoder.txt` L43 + regenerated `assets/Encoder.json`. Accepted trade-off: fixed 30 fps normalizes all outputs (a 60 fps source is halved; `zoompan` has no match-source-fps token).
  - **Closed:** Adam's live RTX 4080 render (2026-05-24) confirmed the zoom looks right and the output (incl. copied audio) is valid. Resolved in `ccd6b36`.
- **Priority:** MEDIUM (the preset fails to render — ffmpeg rejects the filtergraph).
- **Locations:**
  - `assets/Encoder.txt` L43 ("5s Cycle Zoom")
  - `assets/Encoder.json` (generated from Encoder.txt; the same token is embedded in its `params` list)
- **Context:** L43's command is `-vf "scale=iw*1.5:ih*1.5,zoompan=z='…':…:s='iw*1.5:ih*1.5'" -c:a copy …` — the whole `-vf` value is wrapped in shell-style **double** quotes. The app tokenizes via `code.split()` and invokes ffmpeg via `subprocess` **list** form (no shell), so the literal `"` characters are never stripped by a shell — they reach ffmpeg as part of the argv token. ffmpeg's filtergraph parser does not treat `"` as a quote char (it uses `'` and `\`), so it sees a filter named `"scale…` → "No such filter" → the preset fails. The inner single quotes (`zoompan=z='…'`) are correct ffmpeg quoting and must stay. (Broken by inspection; a live render would confirm the exact error.)
- **Why #6 does NOT fix it:** #6 is a tokenizer change. Per the #6 investigation, neither `code.split()` nor `shlex.split(posix=False)` removes these outer double-quotes; `shlex.split(posix=True)` would remove them but regresses other presets by stripping ffmpeg's own single-quotes (e.g. the `enable='lt(mod(t,10),1)*gte(t,0)'` in "Cut & Overlay 1s per 10s"). The correct fix is a **content** fix, not a tokenizer fix.
- **Resolution sketch:** In `assets/Encoder.txt` L43, drop only the outer double-quotes — `-vf "scale=…s='iw*1.5:ih*1.5'"` → `-vf scale=…s='iw*1.5:ih*1.5'` — keeping the inner zoompan single-quotes. Regenerate `assets/Encoder.json` via `tools/generate_encoder_json.py`. Verify with a live render that the filtergraph is accepted. The #6 tokenizer sweep found only L43 with this outer-double-quote pattern; re-confirm none others before/after.
- **Trigger for pickup:** a user reports "5s Cycle Zoom" fails to render, OR Adam authorizes the content fix.

### B-042: preset_loader tokenizer code.split() vs shlex (fix-pass item #6) — CLOSED (won't-fix)

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

### B-043: cycle presets (#5) "video loops, audio plays once" — CLOSED (won't-fix)

- **Status:** CLOSED — won't-fix (2026-05-24). No code change.
- **Origin:** Phase-3 fix-pass item #5 ("Cycle-loop presets: video loops 300x but audio plays once; add -stream_loop so audio matches").
- **Affected presets (investigated):** `assets/Encoder.txt` L4–L10, group "🕹️ 1vmo Ultimate" — "Cycle Ns (a-b-c) Nx Zoom" and "… Flip + Zoom" (split=300 for the 100x variants, split=18 for the 6x).
- **What they actually do (decoded):** each preset runs `[0:v]split=N`, trims N **sequential, non-overlapping windows of the SOURCE timeline** (6x example: trim 0:4, 4:7, 7:10, … 57:60 = 6×(4-3-3) = 60s), applies the zoom pattern per segment, and `concat=n=N:v=1[v]`. Audio is `-map 0:a -c:a copy` (the **full** source audio). So the presets **slice / re-zoom a ≥60s source** — they do NOT loop a short clip. Output video ≈ min(source, cycle_total); audio = full source.
- **Why the backlog premise was wrong:** "video loops 300x / audio plays once" misread the filtergraph. Nothing loops — `split → trim → concat` is a pre-calculated reassembly of source segments. The audio is already full-length (`-map 0:a`), not truncated to one cycle. The only realistic mismatch is the **opposite** (audio overruns the capped video when source > cycle_total), not audio underrun.
- **Why -stream_loop / aloop are inappropriate:** `-stream_loop` is an **input** option (must precede `-i`); a preset's code field only contributes post-`-i` params, so `-stream_loop` in a preset is a **no-op**. Placing it before `-i` (a code change) would loop **both** streams and double-loop the already-assembled video. An audio-side `aloop` would lengthen an audio track that is, if anything, already too long, and introduces audio seams. There is no clean filtergraph way to loop a short clip; the standard approach is a pre-calculated concat — which is exactly what `split=N` already encodes at authoring time.
- **Decision:** the presets work as designed for their intended ≥60s footage. Close won't-fix.
- **Future work (separate feature, NOT a preset edit):** if short-clip looping is ever wanted, it belongs in `auto_render.py` command construction — `-stream_loop <n>` before `-i` plus `-shortest` (or explicit duration math) to bound the output — as an opt-in feature with its own design, not in Encoder.txt.
- **Surfaced/closed by:** Phase-3 fix-pass #5 discovery, 2026-05-24.
