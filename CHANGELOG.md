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

### Changed
- Phase 2a: shared code extracted into `core/` package across five sub-phases — `core/config.py` (2a/1), `core/file_picker.py` (2a/2), `core/widgets.py` (2a/3), `core/preset_loader.py` (2a/4), `core/ffmpeg_runner.py` (2a/5a + 5b: binary resolution + subprocess lifecycle). Pure internal refactor, no user-visible behavior change. Enables Phase 2c JSON preset migration and Phase 2d PyQt5→PySide6 migration without per-app drift. Tag `phase-2a-complete` at `3731230`. [9f5eeab] [bf6f968] [106e8b1] [a56e10c] [7b30a87] [8d26072]
- `core/preset_loader.py` gains `load_presets_json` and `save_presets_json` (Phase 2c-b); `tools/generate_encoder_json.py` switched to `save_presets_json` for single-source-of-truth serialization. Existing `load_presets()` unchanged. `auto_render.py` still uses the old path (switchover in 2c-c). [57564fe]
- `.gitignore` — originally excluded runtime config files written by apps during smoke tests; now also excludes Claude Code personal state (`.claude/settings.local.json`, `.claude/cache/`). [caf1f46] [f08b08e]
- CLAUDE.md trimmed: §7 amended for ADR-0003 exceptions, §10 and §11 replaced with docs/ROADMAP.md pointers. [Unreleased]

### Fixed
- Restored source readability after pylingual decompile: 43 control-flow reconstruction artifacts corrected across the four apps (`auto_render.py`, `cutter.py`, `merge.py`, `mixer.py`) — indentation cascades from `# irreducible cflow, using cdg fallback` blocks, broken try/except nesting, and orphaned return statements. All four apps now launch and pass end-to-end smoke tests against the reference config files. [a225831]
- `requirements.txt` — declared `Pillow>=10.0` as an explicit dependency. `merge.py` uses Pillow (function-level imports at lines 87 and 934) but it was not previously declared, meaning a fresh install strictly from `requirements.txt` would crash on image-handling code paths. Pre-existing condition from the original decompile; surfaced by repo verification on 2026-04-18.
- Top-level frames in all four apps now expand to fill the window on resize. Previously fixed-size containers left dead gutters when the window was enlarged. [5454429]
- `mixer.py` `save_config` — reconstructed scrambled dict field order from decompile artifact (fix #44, supplementing the 43 control-flow fixes above). Without this fix, mixer's saved config persisted with wrong keys matched to wrong values, corrupting preference restoration on relaunch. [3731230]

---

_Pre-2.0 history: the suite originally shipped as four separate compiled `.exe` files (Auto Render v3.5, Cutter v3.5, Merge v3.7, Mixer v3.5). Original source was not preserved; v2.0.0 is a clean-break revival reconstructed via pylingual decompile. No retroactive changelog entries are maintained for the pre-revival generation._
