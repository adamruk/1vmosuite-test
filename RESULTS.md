# Manager Review — backlog-batch-1

- **Branch:** `backlog-batch-1`
- **Base:** `phase3-adam-v39-merge` (`b8331e6`)
- **Audited HEAD:** `8e8852f`
- **Phase key:** none matched — **durable rules only**
- **Reviewed:** 2026-05-24 (VERIFY session, read-only)

## Phase / scope note

`.agent-status/main.json` is **stale**: it still describes the prior
`phase-a-url-dl-hardening` session (`last_sha 9a2263a`, scope
`core/url_downloader.py`), none of which is on this branch. The actual
work under review is `backlog-batch-1` (7 commits, 8 files). The only
`phase_rules` key is `url-dl-hardening`, which is **not** a substring of
this branch and whose target (`core/url_downloader.py`) is absent from the
diff — so the URLDL-* phase rules are inapplicable and were not applied.
Durable rules were evaluated against the batch-1 task definition.

## Commits

| sha | subject |
|---|---|
| aedc37c | fix(scripts): B-046 check_adr_references self-exclusion fails on Windows backslash paths |
| fc26a70 | refactor(mixer): B-023 rename on_video_merge_started to on_video_mixer_started |
| c23461d | fix(ui): B-019 neutral batch-finished message instead of success-toned on all-fail |
| e7cd2b1 | refactor(auto-render): B-030 remove write-only output_mapping dead state |
| 8080631 | feat(ui): B-018 add Clone for built-in presets (Option 4, part b) |
| cf8ef1a | fix(encoder-dialog): B-020 strip whitespace around Group\|Name pipe-split |
| 8e8852f | docs(backlog): file B-047/B-048/B-049; move batch-1 closures to Resolved |

Files: BACKLOG.md, CHANGELOG.md, auto_render.py, mixer.py,
scripts/check_adr_references.py, tests/smoke/test_check_adr_references.py,
tests/smoke/test_clone_preset_id.py, tests/smoke/test_split_group_name.py
(+354 / −146).

## Rule results

| rule id | name | severity | result | evidence |
|---|---|---|---|---|
| DURABLE-CONTRACT | Per-item failures never raise | critical | PASS | B-019 changes only the message string in the `_start_next_task` terminal-cleanup branch (auto_render.py:2810-2820); no per-item exception path altered, `RenderWorker.process` untouched. |
| DURABLE-NO-SILENT-CATCH | No silent error swallowing | warning | PASS | No `except` block appears in any changed line (new code: `_split_group_name`, `_allocate_user_preset_id`, `clone_encoder`, `_create_user_preset_from_result`, the as_posix line). |
| DURABLE-SCOPE | Diff stays within phase scope | critical | PASS | All 8 paths map to declared batch-1 items (auto_render.py→B-018/019/020/030; mixer.py→B-023; scripts/check_adr_references.py→B-046; 3 smoke tests→repro tests; BACKLOG.md+CHANGELOG.md→docs/changelog discipline). No "while I'm here" edit. (main.json scope is stale; judged vs the batch-1 task.) |
| DURABLE-COMMITS | One issue per commit | warning | PASS | 7 commits, each names its B-NNN and a single concern; verified B-018 commit `8080631` does NOT contain `_split_group_name` (that lands in B-020 `cf8ef1a`) — clean separation. |
| DURABLE-DOCS | Docs/ADR move with behavior | warning | PASS | New methods/helpers all carry docstrings; B-018 cites ADR-0006 (exists); Clone follows the existing user-namespace model, no new ADR required. ADR-reference checker exits 0. |
| DURABLE-HOOK-CONV | Hook scripts follow convention | critical | SKIP | No Claude Code hook script in the diff. |
| QT-THREADSAFE | No UI access from worker threads | critical | PASS | `clone_encoder`/`_create_user_preset_from_result` are GUI-thread button slots; `_split_group_name`/`_allocate_user_preset_id` are pure module functions. No worker-thread widget access added. |
| NO-BLOCK-EVENTLOOP | No blocking calls on GUI thread | warning | PASS | Clone reuses the pre-existing `save_encoder_changes` (small atomic JSON write + modal) already used by Add; no new long-running/blocking GUI-thread call. |
| SUBPROCESS-SAFE | External-process handling safe | critical | SKIP | No subprocess/FFmpeg/ffprobe/yt-dlp/deno invocation changed. |
| FROZEN-BUILD | Frozen-build path correctness | critical | SKIP | No bundled-binary/resource resolution changed. `scripts/check_adr_references.py` is a dev-only tool (not shipped in the frozen build); its `as_posix()` change is path-string matching, not resource resolution. |
| RESOURCE-CLEANUP | Resources released on all paths | warning | PASS | Changed code allocates no unmanaged resources; `Path.read_text` (check_adr) is self-closing; no temp file/dir, process handle, or thread pool added. |
| NO-SECRETS-PATHS | No hardcoded secrets/machine paths | critical | PASS | grep_diff of added lines: only matches are the prose word "token" ("ADR token") and a synthetic test fixture `PureWindowsPath(r"C:\repo\scripts\...")`. No credential or `C:\Users\<name>` machine path. |
| TESTS-PRESENT | Behavior changes ship with tests | warning | PASS | New pure logic each has a dedicated deterministic test: B-046→test_check_adr_references.py, B-018 id-mint→test_clone_preset_id.py, B-020 split→test_split_group_name.py (12 tests, all pass independently). B-019 (string reword), B-030 (dead-code removal), B-023 (internal rename) are no-behavior-change / UI-string, verified by py_compile + import + static check per the manual-UI policy (ADR-0001/0003). See Observations for the residual Clone-flow gap. |
| DETERMINISTIC-TESTS | Tests are deterministic | warning | PASS | All 3 new test files run offscreen, offline, no `sleep`-as-sync, no order dependence; `test_check_adr_references` scans the real tree deterministically. |

## Independent verification (re-run by VERIFY, not trusted from summary)

- `python -m py_compile auto_render.py mixer.py scripts/check_adr_references.py` → OK
- `python -m ruff check` (changed code + 3 new tests) → All checks passed
- `pytest tests/smoke/` → **203 passed, 6 skipped**
- 3 batch-1 test files in isolation → **12 passed**
- `python scripts/check_adr_references.py` → exit 0 (was exit 1 before B-046)
- Correctness probe: Clone of a **built-in** copies params — confirmed `load_encoders_to_tree` stores `" ".join(encoder.params)` in `Qt.UserRole` for every row (auto_render.py:3528), which `clone_encoder` reads (auto_render.py:3626).

## Observations (informational — not rule failures)

1. **Clone drops `details`.** `_create_user_preset_from_result` uses
   `result.get("details", "")` and `EncoderDialog` has no details field, so
   a cloned preset loses the source's `details` text. This matches existing
   Add behavior and the known EncoderDialog limitation (edit_encoder works
   around it for the in-place case); acceptable for a NEW preset the user is
   about to customize. Worth a one-line backlog note if details-preservation
   on clone is desired.
2. **Clone UI flow is only helper-tested.** `clone_encoder` →
   `EncoderDialog` → `save_encoder_changes` is covered at the pure-helper
   level (`_allocate_user_preset_id`) + a headless button-wiring smoke;
   the dialog/save round-trip is MANUAL-VERIFIED, consistent with the
   no-automated-GUI-test policy (ADR-0001 §7).
3. **MAIN correctly STOPPED on B-014 and B-016** (found already fixed
   in-tree) rather than inventing fixes, and split the discovered gaps into
   B-048 (inert show_ffmpeg_command/open_output_when_done settings + stale
   `_reload_config_settings` docstring) and B-049 (mixer class still named
   `VideoMergerTool`). Good scope discipline.
4. **Stale `.agent-status/main.json`** should be refreshed to the
   `backlog-batch-1` branch/phase so future reviews key off the right scope.

## Score

- passed = 11, failed = 0, warned = 0, skipped = 3
- score_pct = 11 / (11 + 0 + 0×0.5) × 100 = **100%**
- **Grade: A**
- **Status: PASSED**
