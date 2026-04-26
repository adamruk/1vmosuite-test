# Changelog

All notable changes to **1vmo Suite** are documented in this file.

Format: [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

---

## Maintenance rules

These are non-negotiable. The changelog is an audit artifact, not marketing copy.

1. **Shipped version entries are IMMUTABLE.** Never edit a released version block — add a new patch/minor version instead. Retroactive edits destroy the audit trail.
2. **Measurable claims require evidence on disk.** Any entry asserting size, time, count, percentage, speed, or quality must link to a file under `benchmarks/`, `tests/`, `docs/decisions/`, or a commit hash.
3. **`[Unreleased]` holds in-progress work.** It graduates to a numbered version only when shipped. Empty subsections may be omitted entirely.
4. **Date = ship date.** Not the date work started, not the date the PR merged — the date users received it.
5. **No marketing language.** Write "Fixed race condition in session cleanup," not "improved stability." Write "hevc_nvenc encodes 3.2× faster than libx264 at VMAF 94 [bench/2026-04-18-nvenc-vmaf.md]," not "blazing-fast GPU encoding."
6. **Six-month test.** Will someone six months from now need to know this? If no, skip it.
7. **Internal refactors get consolidated entries, not per-commit bullets.** Phase-level or sub-phase-level changes (e.g., "Phase 2a: `core/` extraction") get a single `### Changed` entry citing all relevant commit hashes. One-off dev hygiene commits (`.gitignore`, CI config, test fixtures) can be single-line entries. The goal is a complete audit trail without log noise.

---

## Traceability

Every entry making a disputable claim ("faster," "fixes X," quantitative measurements) must link to at least one evidence source. Pure refactors and cosmetic changes get a bare commit hash only.

| Evidence type | Location | Reference format | When to use |
|---|---|---|---|
| Commit hash | git | `[abc1234]` (7 chars, multiple allowed: `[abc1234, def5678]`) | Every code change |
| Architecture Decision Record | `docs/decisions/` | `[ADR-0003]` | Framework migrations, encoder strategy, distribution model, API surface |
| Benchmark result | `benchmarks/` | `[bench/2026-04-18-nvenc-vmaf.md]` | Performance or quality claims |
| Test log | `tests/` | `[tests/e2e-cutter-20260418.log]` | Restored or new functional coverage |

Naming conventions:
- ADRs: `ADR-NNNN-slug.md` (4-digit zero-padded, never renumbered; superseded ADRs keep their number and add `Status: Superseded by ADR-NNNN`).
- Benchmarks: `YYYY-MM-DD-slug.md` (ISO date prefix).
- Test logs: `<test-name>-YYYYMMDD.log` or `.md` (compact date).

---

## Example entry format

This block is illustrative, not part of the project history. It shows the shape a good entry should take.

```- `.claude/settings.json` + `.claude/hooks/check-changelog.sh` - CHANGELOG-enforcement hook. Blocks `git commit` via Claude Code's PreToolUse Bash hook if `CHANGELOG.md` is not in the staged diff, unless the commit message contains `[skip changelog]` (escape hatch for pure internal refactors per amended rule 7). Deterministic enforcement of CLAUDE.md section 4. [250668b]

### Changed
- Default HEVC encoder switched from libx265 to hevc_nvenc on CUDA-capable systems — encodes 3.2× faster at matched VMAF ≥ 94 on the reference RTX 4070 preset sweep. Fallback to libx265 on CPU-only hosts unchanged. [bench/2026-04-18-nvenc-preset-vmaf-audit.md] [ADR-0001-nvenc-migration] [a1b2c3d, e4f5g6h]
```

What makes it a good entry: one concrete user-visible change, a measurable claim tied to a specific benchmark file, the architectural decision recorded separately as an ADR, and the exact commits that delivered it.

---

## [Unreleased] — v2.0.0

First release of the revived codebase. Covers the decompile-and-restore effort and Phase 1 modernization work in progress.

### Added
- GPU encoding pipeline via NVENC — **in progress, Phase 1 (detection).** Will ship with hardware capability probing, encoder auto-selection, and CPU fallback. Entry will be finalized with benchmark and ADR links before v2.0.0 is cut.
- `docs/PHASE_1_STOP_CONDITIONS.md` — lightweight Phase 1 stop-condition document (time budget, 3 hard stops, 3 soft stops) with a binding verification-and-permission protocol. Protocol prohibits automated helpers from rolling back, disabling features, or declaring phase halts autonomously — they must verify signals, produce a structured report, and wait for Adam's explicit decision before proceeding. References `FFMPEG_CPU_TO_NVENC_REFERENCE.md` §1/§6/§7.
- `bench.py` — standalone benchmark tool for measuring ffmpeg commands. Two modes: quick (wall-clock + file size, ~10s overhead) and full (adds VMAF mean and 5th-percentile, ~60s overhead). Outputs structured JSON to `bench_results/`. Used to produce the libx264 baseline measurements that drive Phase 1 NVENC migration decisions. Documentation: `benchmarks/README_BENCH_TOOL.md`.
- `benchmarks/METHODOLOGY.md` — defines how to run reproducible Phase 1 benchmarks. Encodes the cold-vs-sustained distinction (laptop NVENC throttles under load), the 20-minute warmup protocol for sustained measurements, the 3-clip diversity requirement, and standard `bench.py` invocations for CPU and GPU comparisons. Stop-condition H-3 throughput floor is defined against the sustained number, not the cold number.
- `docs/PHASE_2_ROADMAP.md` — parking-lot document recording planned modernization work for after Phase 1 ships. Captures sub-phases for shared `core/` module extraction, updater migration to GitHub Releases, Encoder.txt JSON migration, and PyQt5→PySide6 upgrade. No work begins until Phase 1 is shipped and validated.
- `tools/generate_encoder_json.py` — Phase 2c-a migration tool. Reads `assets/Encoder.txt` via `core.preset_loader` and emits `assets/Encoder.json` (schema_version=1, 111 preset entries). Deterministic output; fails loudly on any parse skip. Not yet consumed by any app (switchover in Phase 2c-c). [5fc1dc7]
- `assets/Encoder.json` — generated preset library (111 entries = 109 from `assets/Encoder.txt` + 2 Text defaults hoisted from `auto_render.py` hardcodes). Not yet consumed by any app. [5fc1dc7]
- `CLAUDE.md` at repo root — project-level non-negotiables auto-loaded by Claude Code in every session: rule precedence (§0), two-terminal workflow, self-review gate, Phase 2a summary format, ADR-0001 constraints, CHANGELOG discipline, byte-by-byte fidelity, scope discipline, deferred observation list, phase status. [f08b08e]
- `tests/fixtures/test_halfsec.mp4` — 0.5s test fixture for short-video edge case validation. [2cfbce9]
- Phase 2 governance docs: docs/ROADMAP.md (migrated from PHASE_2_ROADMAP.md via git mv), docs/PHASE_2C_PLAN.md, docs/PRESET_PHILOSOPHY.md, docs/NVENC_PARAMETER_REFERENCE.md, docs/decisions/ADR-0002-product-trajectory.md, docs/decisions/ADR-0003-narrow-pytest-exceptions.md. Observations canon migrated from CLAUDE.md §10 into docs/ROADMAP.md with letters preserved; U marked Fixed in 2c-b; new V added for RenderWorker codec-append gotcha. [Unreleased]
- ADR-0004: Cross-platform expansion — Apple Silicon Mac added to platform targets. Partially supersedes ADR-0002's Windows-only clause. Linux and Intel Mac explicitly deferred. Mac work sequenced after Phase 2 stabilization. [docs/decisions/ADR-0004-cross-platform-mac-support.md][498c0e3]
- PHASE_2_PORT_NOTES.md migrated into repo at docs/PHASE_2_PORT_NOTES.md. Spec for Phase 2.5 features port from Phase 1 (Settings dialog, naming_utils, GPU/NVENC pipeline, polish, default slots) plus 3 deferred issues (9:16 CRF High preset, Bug 9 TOCTOU race, gblur perf). [docs/PHASE_2_PORT_NOTES.md][498c0e3]
- Pre-commit toolchain installed (pre-commit, commitizen, ruff, markdownlint, custom ADR validator) [5e7e8c9]
- scripts/adr_lint.py — validates ADR header fields, status values, date consistency, filename pattern [5e7e8c9]
- .pre-commit-config.yaml, .markdownlint.yaml, .cz.toml (commitizen config; pyproject.toml decision deferred) [5e7e8c9]
- BACKLOG.md at repo root tracking deferred audit-fix items B-001 through B-009 [f2aba1a]
- `core/encoder_schema.py`: Pydantic v2 models (`EncoderPreset`, `EncoderLibrary`) for read-only validation of `assets/Encoder.json`. `extra='forbid'` on both; `schema_version` pinned to `Literal[1]`. No uniqueness validator on `(group, name)` — 13 known collisions tolerated; identity deferred to 2c-c-4. [ce51400] [v2c-c-1]
- `core.preset_loader.load_builtin_json(path)`: Pydantic-validated JSON loader returning `list[Preset]`. Coexists with hand-rolled `load_presets_json` during dark release. [ce51400] [v2c-c-1]
- `auto_render.VideoRendererTool.load_encoder_options`: `ENCODER_USE_JSON=1` env var branch reads from `assets/Encoder.json` via `load_builtin_json`. Default branch unchanged. [ce51400] [v2c-c-1]
- `tools/check_encoder_schema.py`: manual-smoke validator script. Exits 0 on PASS, non-zero on FAIL. ADR-0001-aligned (smoke-logs-only). [ce51400] [v2c-c-1]
- `requirements.txt`: `pydantic>=2.0,<3` runtime dependency added for schema validation. [ce51400] [v2c-c-1]
- `tests/smoke-2c-c-1-schema-20260426.log`: 2c-c-1 manual-smoke output capturing PASS for 111-preset validation. [ce51400] [v2c-c-1]
- `core/user_data.py`: user data directory resolver via platformdirs (default) with opt-in portable mode via `portable.txt` sentinel. Exports `resolve_user_data_dir(install_dir)`, `PortableLocationError`, `APP_NAME`, `PORTABLE_SENTINEL`. Pure resolution (no writes); callers create directories on first use in 2c-c-3. [248ac56] [v2c-c-2]
- `tools/check_user_data.py`: manual-smoke validator. Tests 4 branches (default platformdirs, portable safe, portable + protected raises, protected-dir detection). Exits 0 on PASS. ADR-0001 aligned. [248ac56] [v2c-c-2]
- `tests/smoke-2c-c-2-userdata-20260426.log`: 2c-c-2 manual-smoke output. [248ac56] [v2c-c-2]
- `docs/decisions/ADR-0005-platformdirs-user-data.md`: decision record for using platformdirs (default) + portable.txt opt-in (instead of plan's literal "./UserData/ alongside exe"). Documents VirtualStore silent-redirect bug class, os.access ACL unreliability, and cross-platform consequences for ADR-0004. [248ac56] [v2c-c-2]
- `requirements.txt`: `platformdirs>=4.0,<5` runtime dependency for cross-platform user data path resolution. [248ac56] [v2c-c-2]
- `core/atomic_write.py`: generic `save_json_atomic(path, data)` with .bak rotation + 5-retry exponential backoff (50/100/200/400/800ms) for PermissionError/OSError. Used by all user-state writers. [86edaa4] [v2c-c-3]
- `core.preset_loader.save_user_presets_json` / `load_user_presets_json`: user-preset I/O via Pydantic schema. Loader has .bak fallback + rename-to-.corrupt on double failure (never blocks startup). [86edaa4] [v2c-c-3]
- `core.user_data.resolve_or_die(install_dir, on_error)`: helper that resolves user data dir, mkdir's parents, calls on_error callback + sys.exit(1) on PortableLocationError. Callback parameter keeps core/ Qt-uncoupled. [86edaa4] [v2c-c-3]
- `core.user_data.migrate_legacy_configs(install_dir, user_data_dir)`: idempotent first-launch migration that copies install-dir config_video_*.json to user_data_dir. PRESERVES originals (per conservative-deletes principle). Returns list of copied filenames for logging. [86edaa4] [v2c-c-3]
- `tools/test_user_save.py`: manual-smoke validator for save/load round-trip + .bak rotation. Tempdir-based. ADR-0001 aligned. [86edaa4] [v2c-c-3]
- `tests/smoke/test_atomic_write_retry.py`: pytest test for retry-on-PermissionError + retry exhaustion + backoff count. ADR-0003 Exception 1 — first approved pytest exception. [86edaa4] [v2c-c-3]
- `tests/smoke-2c-c-3-usersave-20260426.log`: manual-smoke output. [86edaa4] [v2c-c-3]
- `tests/smoke-2c-c-3-retry-20260426.log`: pytest output. [86edaa4] [v2c-c-3]
- `requirements.txt`: `pytest>=8.0,<9` added per ADR-0003 ("pytest lives in requirements.txt"). [86edaa4] [v2c-c-3]
- `docs/ROADMAP.md`: Observation W added — logging.basicConfig CWD-relative video_*.log fragility in cutter/merge/mixer. Deferred per D2=b. [86edaa4] [v2c-c-3]

### Changed
- Phase 2a: shared code extracted into `core/` package across five sub-phases — `core/config.py` (2a/1), `core/file_picker.py` (2a/2), `core/widgets.py` (2a/3), `core/preset_loader.py` (2a/4), `core/ffmpeg_runner.py` (2a/5a + 5b: binary resolution + subprocess lifecycle). Pure internal refactor, no user-visible behavior change. Enables Phase 2c JSON preset migration and Phase 2d PyQt5→PySide6 migration without per-app drift. Tag `phase-2a-complete` at `3731230`. [9f5eeab] [bf6f968] [106e8b1] [a56e10c] [7b30a87] [8d26072]
- `core/preset_loader.py` gains `load_presets_json` and `save_presets_json` (Phase 2c-b); `tools/generate_encoder_json.py` switched to `save_presets_json` for single-source-of-truth serialization. Existing `load_presets()` unchanged. `auto_render.py` still uses the old path (switchover in 2c-c). [57564fe]
- `.gitignore` — originally excluded runtime config files written by apps during smoke tests; now also excludes Claude Code personal state (`.claude/settings.local.json`, `.claude/cache/`). [caf1f46] [f08b08e]
- CLAUDE.md trimmed: §7 amended for ADR-0003 exceptions, §10 and §11 replaced with docs/ROADMAP.md pointers. [Unreleased]
- ADR-0002 status header amended to note partial supersession by ADR-0004 (platform-scope clause only). Decision body unchanged for historical record. [docs/decisions/ADR-0002-product-trajectory.md][498c0e3]
- CLAUDE.md line 37 stale path fixed: docs/PHASE_2_ROADMAP.md -> docs/ROADMAP.md (post-yesterday's git mv). [CLAUDE.md][498c0e3]
- docs/ROADMAP.md Observation V status updated: "Open, scheduled Phase 2" -> "Fixed in Phase 2 (c03433a)" — closes governance loop on the Path B Observation V fix. [docs/ROADMAP.md][bf4b636]
- docs/PHASE_2C_PLAN.md governance update: removed "Observation V fix" from executive summary's "Phase 2 done = ..." formula (now shipped); added deviation note to Observation V section documenting Path B bundling as one-off, standalone-commit rule remains in force for future blockers. [docs/PHASE_2C_PLAN.md][bf4b636]
- .markdownlint.yaml MD013.line_length — was 120, now 200. Reason: 365 markdownlint violations surfaced in 2026-04-26 baseline run, most are line-length on narrative prose (CHANGELOG, ROADMAP, ADRs). 200 covers natural prose without effectively disabling the rule. [f2aba1a]
- 24 files — was carrying trailing whitespace, missing EOF newlines, and ruff-formatting drift; now normalized by pre-commit auto-fix (trailing-whitespace, end-of-file-fixer, ruff --fix, ruff-format). Files: assets/README*.md (5), assets/Version AutoRender.json, all 4 apps (auto_render.py, cutter.py, merge.py, mixer.py), bench.py, core/* (4), docs/{NVENC_PARAMETER_REFERENCE,PHASE_2C_PLAN,PRESET_PHILOSOPHY}.md, docs/decisions/{ADR-0002,ADR-0003}*.md, help_dialog.py, tools/generate_encoder_json.py, updater.py. Reason: first run of newly installed pre-commit toolchain surfaced pre-existing hygiene debt; one-shot normalization. [f2aba1a]
- `docs/PHASE_2C_PLAN.md` line ~47: filename reference. BEFORE: `assets/encoder.builtin.json`. AFTER: `assets/Encoder.json`. WHY: rename deemed unnecessary churn (single tool/loader path stays as-is); plan corrected in-commit per CLAUDE.md §6 minimum-fix. [ce51400] [v2c-c-1]
- `docs/PHASE_2C_PLAN.md` line ~54: acceptance gate. BEFORE: `tests/smoke/test_schema_validation.py passes` (pytest). AFTER: `tools/check_encoder_schema.py emits PASS to tests/smoke-2c-c-1-schema-YYYYMMDD.log` (manual-smoke). WHY: aligns with ADR-0001 (smoke-logs-only) and PHASE_2C_PLAN.md:146 ("Pydantic roundtrip — framework-covered, not added to pytest"). Resolves contradiction without amending ADR-0003 pytest-exception list. [ce51400] [v2c-c-1]
- `docs/ROADMAP.md`: 2c-c-1 entry moved from Pending blockers to Done. WHY: feature landed; tracks Phase 2 stabilization progress. [ce51400] [v2c-c-1]
- `.gitignore` line 28-29 (after `*.log`): added `!tests/smoke-*.log` negation. BEFORE: `*.log` blocked all log files including smoke logs (required `git add -f` for tests/smoke-2c-c-1-schema-20260426.log). AFTER: `!tests/smoke-*.log` exempts smoke logs from the *.log rule. WHY: removes friction across all remaining sub-phases (2c-c-3 through 2c-c-6) which each emit a smoke log. [248ac56] [v2c-c-2]
- `docs/PHASE_2C_PLAN.md` 2c-c-2 scope bullets (lines ~60-64): rewritten. BEFORE: "./UserData/ alongside exe if writable" + "Program Files install raise" + "win32 only; others raise NotImplementedError." AFTER: "platformdirs default + portable.txt opt-in" + "Windows-protected dir guard in portable mode" + "cross-platform via platformdirs." WHY: VirtualStore silent-redirect bug class (Microsoft documented behavior) makes the os.access guard unreliable. Documented in ADR-0005. [248ac56] [v2c-c-2]
- `docs/PHASE_2C_PLAN.md` 2c-c-2 acceptance criteria (lines ~67-68): rewritten. BEFORE: "tests/smoke/test_user_data_resolution.py passes" (pytest). AFTER: "tools/check_user_data.py emits PASS to tests/smoke-2c-c-2-userdata-YYYYMMDD.log" (manual-smoke). WHY: ADR-0001 (smoke-logs-only); ADR-0003's pytest exception list does not include user_data resolver. Same pattern as 2c-c-1. [248ac56] [v2c-c-2]
- `docs/PHASE_2C_PLAN.md` 2c-c-6 section (after **Tag:** line): added deviation note. BEFORE: section described adding darwin branch to user_data resolver. AFTER: note added explaining macOS path is already handled by platformdirs in 2c-c-2; 2c-c-6 reduces to verifying behavior on actual Mac hardware. WHY: platformdirs handles cross-platform paths automatically. [248ac56] [v2c-c-2]
- `docs/ROADMAP.md`: 2c-c-2 entry moved from Pending blockers to Done. WHY: feature landed; tracks Phase 2 stabilization progress. [248ac56] [v2c-c-2]
- `auto_render.py` VideoRendererTool.__init__ + load_encoder_options + save_encoder_changes. BEFORE: CONFIG_FILE was `SCRIPT_DIR / "config_video_renderer.json"` (install dir); load_encoder_options loaded only built-ins; save_encoder_changes wrote pipe-delimited text to `assets/Encoder.txt` directly with bare-except swallowing PermissionError. AFTER: CONFIG_FILE is `USER_DATA_DIR / "config_video_renderer.json"`; load_encoder_options merges user JSON via load_user_presets_json after built-in load (orthogonal to ENCODER_USE_JSON gate, per D4=a); save_encoder_changes writes ONLY user presets to `USER_PRESETS_FILE` via save_user_presets_json with specific OSError+ValueError catch + QMessageBox.warning. WHY: fix Observation O (silent PermissionError under Program Files installs) for the encoder-edit path. [86edaa4] [v2c-c-3]
- `cutter.py`, `merge.py`, `mixer.py` per-app __init__ + class-method CONFIG_FILE refs. BEFORE: CONFIG_FILE was a module-level global resolving to install-dir-relative path (`SCRIPT_DIR / "config_video_<app>.json"`); silent PermissionError under Program Files. AFTER: CONFIG_FILE is per-instance attr resolved via `resolve_or_die(SCRIPT_DIR, on_error=lambda msg: QMessageBox.critical(...))` + `migrate_legacy_configs(...)` in __init__; class-method refs all use `self.CONFIG_FILE`. WHY: fix Observation O for the 3 non-renderer apps (D5=b expansion beyond plan literal). [86edaa4] [v2c-c-3]
- `docs/PHASE_2C_PLAN.md` 2c-c-3 section. BEFORE: scope named only `save_user_presets_json` writer; acceptance referenced only test_user_save.py round-trip. AFTER: D5 expansion note added (4 config_video_*.json writes also rewired); acceptance criteria expanded to include both manual-smoke (test_user_save) and pytest (test_atomic_write_retry per ADR-0003 Exception 1) + their captured smoke logs. WHY: implementation expanded scope to fix Observation O across all 5 user-state writes; plan reconciled in-commit per 2c-c-1/2c-c-2 precedent. [86edaa4] [v2c-c-3]
- `docs/ROADMAP.md`: 2c-c-3 entry moved Pending→Done. WHY: feature landed; tracks Phase 2 stabilization progress. [86edaa4] [v2c-c-3]

### Fixed
- Observation O symptom: silent PermissionError under Program Files installs. BEFORE: all 5 user-state writes (4 config_video_*.json + EncoderDialog → assets/Encoder.txt) went to install dir; under Program Files, writes silently failed (PermissionError swallowed by bare-except in EncoderDialog; config writes succeeded into VirtualStore shadow per Windows UAC redirect). AFTER: all 5 writes routed through atomic_write.save_json_atomic + resolve_user_data_dir (platformdirs default, portable.txt opt-in); Program Files install raises PortableLocationError at startup with QMessageBox.critical. Observation O symptom resolved for the user-state-write path. WHY: bug fix — user edits no longer lost silently. [86edaa4] [v2c-c-3]
- Restored source readability after pylingual decompile: 43 control-flow reconstruction artifacts corrected across the four apps (`auto_render.py`, `cutter.py`, `merge.py`, `mixer.py`) — indentation cascades from `# irreducible cflow, using cdg fallback` blocks, broken try/except nesting, and orphaned return statements. All four apps now launch and pass end-to-end smoke tests against the reference config files. [a225831]
- `requirements.txt` — declared `Pillow>=10.0` as an explicit dependency. `merge.py` uses Pillow (function-level imports at lines 87 and 934) but it was not previously declared, meaning a fresh install strictly from `requirements.txt` would crash on image-handling code paths. Pre-existing condition from the original decompile; surfaced by repo verification on 2026-04-18.
- Top-level frames in all four apps now expand to fill the window on resize. Previously fixed-size containers left dead gutters when the window was enlarged. [5454429]
- `mixer.py` `save_config` — reconstructed scrambled dict field order from decompile artifact (fix #44, supplementing the 43 control-flow fixes above). Without this fix, mixer's saved config persisted with wrong keys matched to wrong values, corrupting preference restoration on relaunch. [3731230]
- Path B: Observation V codec-append bug fixed in auto_render.py — `_has_vcodec` helper added to RenderWorker; trailing `-c:v libx264` no longer overrides preset codecs (libx265 stays libx265). [auto_render.py][c03433a]
- Path B: `_has_acodec` helper added — trailing `-c:a aac` no longer overrides preset audio codecs (`-c:a copy` now respected). Audio half of Observation V. [auto_render.py][c03433a]
- Path B: closeEvent crash on partial-batch close — added `if worker is not None:` guard around worker iteration; pre-allocated None placeholders no longer raise AttributeError. [auto_render.py][c03433a]
- Path B: QThread.started double-spawn / RuntimeError — added `try: thread.started.disconnect() except TypeError: pass` before each of 6 quit() call sites. [auto_render.py][c03433a]
- Path B: out-of-order completion stamping wrong tree row — workers now stamp `tree_item` and `task_index` attributes in `_start_next_task`; completion/error handlers use `getattr` lookups instead of count-based row matching. [auto_render.py][c03433a]
- Path B: FFmpeg log unbounded growth — `output_text.document().setMaximumBlockCount(2000)` caps log buffer. [auto_render.py][c03433a]

---

_Pre-2.0 history: the suite originally shipped as four separate compiled `.exe` files (Auto Render v3.5, Cutter v3.5, Merge v3.7, Mixer v3.5). Original source was not preserved; v2.0.0 is a clean-break revival reconstructed via pylingual decompile. No retroactive changelog entries are maintained for the pre-revival generation._
