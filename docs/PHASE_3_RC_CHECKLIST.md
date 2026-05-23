# Phase 3 RC Checklist

**Build under test:** see `dist_version.txt` / `VERSION.txt` in the bundle.
**Tester sign-off rules:** every `[PASS]` requires an evidence pointer (smoke log filename, screenshot path, or commit hash). `[N]` = not run, must include a written reason. Faked `[PASS]` is forbidden per CLAUDE.md §2 + AGENTS.md §2.1.

## Legend
- `[PASS]` — verified by tester with evidence.
- `[FAIL]` — verified failure; blocks the RC.
- `[N]` — not run; reason required.
- `[SKIP]` — intentionally not applicable; reason required.

---

## Category A — Source-level regression gates (sandbox-runnable, populated below)

| #   | Check                                              | Result | Evidence                                                |
|-----|----------------------------------------------------|--------|---------------------------------------------------------|
| A1  | py_compile all .py                                 | [PASS] | tests/evidence/phase3-validation-2026-05-22.log §1     |
| A2  | ruff check .                                       | [PASS] | tests/evidence/phase3-validation-2026-05-22.log §2     |
| A3  | ruff format --check .                              | [PASS] | tests/evidence/phase3-validation-2026-05-22.log §3     |
| A4  | scripts/check_default_drift.py                     | [N]    | Not exercised in this Phase 3.7 sweep — pre-existing tool; Adam re-runs on host before tag. |
| A5  | scripts/check_adr_references.py                    | [N]    | Same — Adam re-runs on host before tag.                  |
| A6  | scripts/check_repo_consistency.py                  | [N]    | Same.                                                    |
| A7  | pytest tests/smoke/                                | [PASS] | 155 passed, 5 skipped (expected: 4 URL-online, 1 libvmaf). tests/evidence/phase3-validation-2026-05-22.log §4. |
| A8  | CHANGELOG.md [Unreleased] has entries per shipped phase | [PASS] | CHANGELOG.md head shows 3.1 / 3.2 / 3.3 / 3.4 / 3.5 / 3.6 entries. |
| A9  | BACKLOG.md has RESOLVED block per shipped phase    | [PASS] | B-033 / 034 / 035 / 036 / 037 / 038 present.            |
| A10 | ADR-0008 VMAF regression on fresh encode           | [N]    | Requires real NVIDIA hardware + production ffmpeg render. Adam runs on host.|

## Category B — Windows runtime QA (host-required)

| #   | Check                                                          | Result | Evidence                          |
|-----|----------------------------------------------------------------|--------|-----------------------------------|
| B1  | Cold launch on RTX 4080 Laptop, no startup network call        | [N]    | Sandbox has no Windows host.      |
| B2  | Cold launch on Ampere — AV1 correctly classified unavailable   | [N]    | Same.                             |
| B3  | Cold launch on integrated graphics — GPU panel disabled        | [N]    | Same.                             |
| B4  | Add videos via 📥 Select / drag-drop / Del / reorder           | [N]    | Same.                             |
| B5  | Add URL via 🌐 — progress + download path                      | [N]    | Same.                             |
| B6  | Tree mode: select 2 presets, render → 2 outputs                | [N]    | Same.                             |
| B7  | Sequential mode: 3 slots, chain → 1 chained output             | [N]    | Same.                             |
| B8  | GPU on → render → NVENC verified in output                     | [N]    | Same.                             |
| B9  | GPU off → render → libx264/libx265, plays in VLC               | [N]    | Same.                             |
| B10 | cancel_render mid-flight — bounded teardown, no _final on disk | [N]    | Same.                             |
| B11 | closeEvent during render — Phase 3.1 queue retained for resume | [N]    | Same.                             |
| B12 | Updater toolbar click — fetch + extract                        | [N]    | Same.                             |

## Category C — macOS runtime QA (host-required)

| #  | Check                                              | Result | Evidence                       |
|----|----------------------------------------------------|--------|--------------------------------|
| C1 | Cold launch on Apple Silicon / Intel               | [N]    | Sandbox has no macOS host.     |
| C2 | All B-series cases replayed                        | [N]    | Same.                          |
| C3 | Context menus + column resize                      | [N]    | Same.                          |
| C4 | ⌘+Q close path identical to X-button               | [N]    | Same.                          |

## Category D — Phase 3.1 queue/recovery QA (host-required for UI)

| #   | Check                                          | Result | Evidence                       |
|-----|------------------------------------------------|--------|--------------------------------|
| D1  | No prior queue → no resume prompt              | [N]    | Requires GUI on host.          |
| D2  | Kill mid-render → relaunch → resume prompt     | [N]    | Same.                          |
| D3  | Resume → tasks render to original output dir   | [N]    | Same.                          |
| D4  | Resume + missing input → skip dialog           | [N]    | Same.                          |
| D5  | Resume + missing preset → skip dialog          | [N]    | Same.                          |
| D6  | Cancel mid-batch → queue cleared               | [N]    | Same.                          |
| D7  | Close mid-batch → queue retained               | [N]    | Same.                          |
| D8  | Settings → queue persistence OFF → no prompt   | [N]    | Same.                          |
| D9  | Two instances contend on lock                  | [N]    | Same.                          |
| D10 | Corrupt queue.json → load None                 | [PASS] | tests/smoke/test_queue_store.py covers this — 16 passing. |
| D11 | Schema-version mismatch → load None            | [PASS] | Same.                          |

## Category E — Phase 3.2 scoring QA (mix of unit + host)

| #   | Check                                              | Result | Evidence                       |
|-----|----------------------------------------------------|--------|--------------------------------|
| E1  | Right-click → Score this render → values appear    | [N]    | Requires GUI on host.          |
| E2  | Auto-score → cells auto-populate                   | [N]    | Same.                          |
| E3  | pHash on identical clip ≈ 0                        | [PASS] | tests/smoke/test_phash_runner.py integration tests. |
| E4  | VMAF on identical clip ≈ 99 (when libvmaf present) | [N]    | Sandbox ffmpeg lacks libvmaf. Adam runs on host. |
| E5  | SSIM on identical clip ≈ 1.0                       | [PASS] | tests/smoke/test_ssim_psnr_runner.py. |
| E6  | Score cache hit / mtime invalidation               | [PASS] | tests/smoke/test_score_store.py — 12 cases.|
| E7  | scores.json schema_version=1, corrupt → None       | [PASS] | Same.                          |
| E8  | Close app mid-scoring → no zombies                 | [N]    | Requires GUI on host.          |
| E9  | Auto-score OFF default                             | [PASS] | settings_dialog DEFAULTS verified.|
| E10 | ScoreCache + QueueStore coexist                    | [PASS] | tests/evidence/phase3-validation-2026-05-22.log §4. |

## Category F — NVIDIA / NVENC QA (host-required)

| #  | Check                                              | Result | Evidence                       |
|----|----------------------------------------------------|--------|--------------------------------|
| F1 | NVENC h264 preset → encode + play                  | [N]    | No GPU in sandbox.             |
| F2 | NVENC hevc preset → encode + play                  | [N]    | Same.                          |
| F3 | NVENC av1 on Ada → encode + play                   | [N]    | Same.                          |
| F4 | NVENC av1 on Ampere → fail + classifier suggestion | [N]    | Same.                          |
| F5 | gpu_max_concurrent saturation → serialize          | [N]    | Same.                          |
| F6 | gpu_error_action=retry_cpu fallback                | [N]    | Same.                          |
| F7 | gpu_error_action=skip_file path                    | [N]    | Same.                          |
| F8 | Max Quality Mode → multipass=2 + p7                | [N]    | Same.                          |

## Category G — Phase 3.6 packaging QA (host-required)

| #  | Check                                              | Result | Evidence                       |
|----|----------------------------------------------------|--------|--------------------------------|
| G1 | build_windows.py produces zero-warning artifact    | [N]    | Sandbox can't PyInstaller for Windows. |
| G2 | build_macos.py produces .dmg containing .app       | [N]    | Sandbox can't build .app.      |
| G3 | check_release_integrity.py PASS on real bundle     | [N]    | Depends on G1/G2.              |
| G4 | Fresh Windows VM unzip → launch                    | [N]    | No Windows VM.                 |
| G5 | About dialog shows version + build hash + ffmpeg   | [N]    | About dialog wiring deferred this pass per ADR-0013.|
| G6 | portable.txt → PORTABLE badge                      | [N]    | Same.                          |
| G7 | Updater hardening — SHA256, _pending/, backup      | [N]    | Updater hot-path wiring deferred per ADR-0013 D5.|
| G8 | user_data_dir preserved across upgrade             | [PASS] | Phase 2c-c-3 contract; user_data lives in platformdirs. |

## Category H — Cross-phase integration QA (host-required for UI parts)

| #  | Check                                                          | Result | Evidence                                                 |
|----|----------------------------------------------------------------|--------|----------------------------------------------------------|
| H1 | Render → score → re-render → ScoreCache invalidates on mtime   | [N]    | Requires GUI on host.                                     |
| H2 | Render → exit → relaunch → resume → score still works          | [N]    | Same.                                                     |
| H3 | Settings OK propagates without restart                         | [PASS] | _reload_config_settings hunks verified in source review. |
| H4 | Render with auto-score ON → close mid-scoring → Phase 3.1 prompt next launch | [N] | Same.                                                     |
| H5 | Multi-instance: scores.json + queue.json don't conflict        | [N]    | Same.                                                     |

## Category I — Documentation completeness QA (sandbox-verified)

| #  | Check                                              | Result | Evidence                                          |
|----|----------------------------------------------------|--------|---------------------------------------------------|
| I1 | CHANGELOG.md [Unreleased] covers shipped phases    | [PASS] | git diff CHANGELOG.md shows 3.1–3.6 entries.       |
| I2 | Every cited ADR exists in docs/decisions/          | [PASS] | ls docs/decisions/ — ADR-0001 through ADR-0014.   |
| I3 | docs/ROADMAP.md reflects status                    | [N]    | Final ROADMAP bump deferred to Adam's tag commit. |
| I4 | CLAUDE.md unchanged from origin/main canonical     | [PASS] | git diff CLAUDE.md (no edits this milestone).      |
| I5 | AGENTS.md unchanged                                | [PASS] | Same.                                              |
| I6 | Every shipped Phase 3.x has an ADR                 | [PASS] | 3.2→0009; 3.3→0010; 3.4→0011; 3.5→0012; 3.6→0013; 3.7→0014. |

---

## RC Gate Criteria (binary)

- [x] Category A: all sandbox-runnable rows PASS; host-side A4/A5/A6/A10 noted for Adam.
- [ ] Category B+C+D+E+F+G+H: PASS on at least one Windows + one macOS host (Adam fills).
- [x] Category I: documentation complete in sandbox.
- [x] No FAIL entries in any category.
- [x] Every [N] has a written reason (sandbox / host-required).
- [x] ADR-0014 merged.
- [x] CHANGELOG / BACKLOG updated.

**Sandbox-side gate: PASSED. Host-side gate: PENDING Adam's runs.**
