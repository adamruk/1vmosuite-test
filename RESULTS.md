# RESULTS.md — VERIFY session (read-only auditor)

Phase 3 closeout, independent verification. This session writes ONLY this file
and `.agent-status/verify.json`. No source edits.

---

## BASELINE — phase3-fixes committed tree

- **Recorded:** 2026-05-24
- **Branch:** `phase3-fixes`
- **HEAD at baseline:** `c051473` (`fix(nvenc): B-015 codify single-knob codec routing, remove dead mapped var`)
- **Working tree:** clean (no uncommitted changes — `git status --short` empty)

> ⚠️ **Discrepancy vs prompt:** the prompt pinned the baseline at `phase3-fixes @ d438fb0` (A4).
> The branch HEAD has since advanced to `c051473` (B-015), one commit beyond `d438fb0`.
> I baselined the **current committed tree (`c051473`)**, which already contains both A4 (`d438fb0`)
> and B-015 (`c051473`). Both target commits the prompt asked me to confirm — `d438fb0` (A4) and
> `a877ada` (hook fix) — are present in the log (see check 4). This baseline is therefore A4+B-015
> inclusive, not A4-only. Flagging so the A4/B-015 reviews account for it.

### 1. `ruff check .`
- **Result: PASS** — `All checks passed!` (exit 0). 0 errors, 0 warnings.

### 2. `pytest tests/smoke -q`
- **Result: PASS** — **173 passed, 4 skipped** (exit 0). 0 failed.
- (Whole-repo `pytest` at session start, on `phase3-adam-v39-merge`, was 184 passed / 4 skipped /
  17 PytestReturnNotNoneWarning — those warnings live in `tools/test_*.py`, outside `tests/smoke`,
  and are pre-existing return-not-None style warnings, not failures.)

### 3. ffmpeg bundled-build capability — `./ffmpeg/ffmpeg.exe`
- **libvmaf filter: PRESENT** — `libvmaf  VV->V  Calculate the VMAF between two video streams.`
  - `-version` configuration string contains `--enable-libvmaf`. **VMAF axis is viable.**
- **NVENC encoders: 3 PRESENT** —
  - `h264_nvenc` (NVIDIA NVENC H.264 encoder)
  - `hevc_nvenc` (NVIDIA NVENC hevc encoder)
  - `av1_nvenc` (NVIDIA NVENC av1 encoder)

### 4. `git log --oneline -5`
```
c051473 fix(nvenc): B-015 codify single-knob codec routing, remove dead mapped var
d438fb0 fix(gpu): A4 decouple H.264 NVENC availability from HEVC hardware signal
a877ada fix(governance): hook command must be script path, not bash.exe prefix (Git-Bash double-invocation)
2ca34fd chore(ffmpeg): ignore shared-build DLLs (ffmpeg/*.dll)
1a89578 chore(governance): add Claude Code settings, hooks, verifier agent + section 13 fix-pass rules
```
- ✅ `d438fb0` (A4) present.
- ✅ `a877ada` (hook fix) present.

### Baseline verdict
**GREEN.** Lint clean, smoke suite green, libvmaf + 3 NVENC encoders available. Ready to verify fixes.
A4 review NOT yet performed (per prompt instruction to stop after baseline).

---

## FIX-PASS REVIEW — A4 (`d438fb0`) + B-015 (`c051473`), reviewed as a pair

Reviewed 2026-05-24 using the verifier procedure (`.claude/agents/verifier.md`),
independently re-running repros against committed code (and against PRE-FIX code in
throwaway temp dirs — repo source untouched).

### A4 — `d438fb0` `fix(gpu): decouple H.264 NVENC from HEVC hardware signal`

**Claim:** `gpu_detect.detect()` gated H.264 on the HEVC signal
(`h264_available = hw_supports_hevc and codecs.h264`), hiding H.264 NVENC (and the
whole NVENC path) on pre-Turing cards. Fix: `caps.h264_available = codecs.h264`.

- **Decouple correct? YES.** [gpu_detect.py:270](gpu_detect.py#L270) now sets
  `h264_available = codecs.h264` (own ffmpeg probe). HEVC ([:271](gpu_detect.py#L271))
  and AV1 ([:272](gpu_detect.py#L272)) still gen-gate via `hw_supports_hevc` /
  `gen.supports_av1`. `nvenc_available` ([:273](gpu_detect.py#L273)) is the OR of the
  three. Minimal, targeted, semantically right.
- **Repro genuinely fails pre-fix? YES — empirically proven, not a tautology.** Ran the
  committed test against `d438fb0^:gpu_detect.py` in a temp dir:
  `test_h264_decoupled_from_hevc_on_pre_turing` **FAILS** pre-fix
  (`AssertionError: assert False is True` on `h264_available`; the captured caps show
  `h264_available=False, nvenc_available=False` — exactly the A4 bug). Passes post-fix.
  Logic check confirms it: `GPUGeneration.PRE_TURING.supports_hevc` is `False`
  ([gpu_detect.py:51-58](gpu_detect.py#L51-L58)), so pre-fix `hw_supports_hevc and
  codecs.h264` = `False`, collapsing the whole NVENC path.
- **Ada/4080 path unchanged? YES.** `test_ada_full_codec_matrix_unchanged` passes pre
  AND post. For ADA, `supports_hevc`/`supports_av1` are both `True`, so pre-fix
  `h264_available` was already `True and True` → identical to post-fix `codecs.h264`.
  Byte-identical on the 4080 path.
- **B-NNN mismatch? NONE (expected).** Subject/CHANGELOG explicitly state "No B-NNN: A4
  is an audit-issue id (see `f4cf89a` baseline)". Correct — A4 is an audit id, not a
  backlog item.
- **Scope:** 3 files (gpu_detect.py +1 line/+4 comment, new test, CHANGELOG). No drive-by.
- **Tests now:** `tests/smoke/test_gpu_detect.py` → **2 passed** on current tree.

**A4 VERDICT: READY-TO-MERGE**
(Minor/nit: CHANGELOG A4 entry has no own `[d438fb0]` 7-char hash per CLAUDE.md §4 — the
self-reference chicken-and-egg; repo precedent `1be6adb` backfills these. Not a blocker.)

### B-015 — `c051473` `fix(nvenc): codify single-knob codec routing`

**Claim:** `translate_to_nvenc` computed an unused per-preset `mapped` value; remove it,
behavior byte-identical, codify single-knob routing in new ADR-0015.

- **Behavior-PRESERVING? YES — empirically proven.** The diff's only logic change is in
  the `else` (unrecognized-codec) branch: `out.extend([p, mapped])` →
  `out.extend([p, input_codec])`. In that branch `input_codec ∉ _CODEC_MAP`, so
  `mapped = _CODEC_MAP.get(input_codec, input_codec)` **equals** `input_codec` — identical
  output. In the `if` branch `mapped` was already unused (output = `codec`). Ran the 4
  characterization tests against `c051473^:core/preset_translator.py` (pre-fix) **and**
  current: **4 passed both ways**. Confirmed no behavior change.
- **Decision = keep-single-knob, NOT honor `_CODEC_MAP`? YES.** Recognized CPU codec
  (libx264/libx265) emits the `codec` kwarg = user's `gpu_codec`
  ([core/preset_translator.py:98-101](core/preset_translator.py#L98)), never
  `_CODEC_MAP[input_codec]`. ADR-0015 §Decision pt.1 and §Alternatives explicitly REJECT
  honoring `_CODEC_MAP`. Matches BACKLOG B-015 resolution option (b).
- **Characterization tests pin current behavior? YES.** The meaningful guard
  (`test_unrecognized_codec_passes_through_unchanged`) pins the exact branch that changed;
  `test_libx265_..._not_hevc` pins the single-knob invariant (libx265 + h264_nvenc →
  h264_nvenc). All pass pre+post, which is the point of a characterization test.
- **ADR-0015 exists? YES** —
  [docs/decisions/ADR-0015-nvenc-codec-routing.md](docs/decisions/ADR-0015-nvenc-codec-routing.md)
  (Accepted, 2026-05-24). Documents single-knob, states it "Amends: none (clarifies the
  scope of ADR-0007 D4; does not change any ADR-0007 decision)."
- **ADR-0007 NOT edited? CONFIRMED.** `c051473` changed-file list is exactly:
  CHANGELOG.md, core/preset_translator.py, ADR-0015, test. `ADR-0007-gpu-pipeline.md` is
  NOT in it. (An earlier grep falsely matched "ADR-0007" inside the commit *message*; the
  authoritative `--name-only` list clears it.) The mis-citation is corrected by the
  in-code comment + ADR-0015, leaving ADR-0007 itself untouched — correct per the
  no-silent-ADR-edit rule.
- **Scope:** 4 files, all on-issue. No drive-by.
- **Tests now:** `tests/smoke/test_preset_translator_routing.py` → **4 passed**.

**B-015 VERDICT: READY-TO-MERGE**
(Minor/nit: CHANGELOG B-015 entry links ADR-0015 but carries no own `[c051473]` hash —
same §4 self-reference nit as A4. Not a blocker.)

### Pair-level note
Both commits are independently correct and in-scope; the A4+B-015-inclusive baseline
(GREEN) holds. No interaction between them.

---

## SIDE-ISSUE — MAIN's flag: `supports_hevc` vs ADR-0007 D5 L149

**Question:** Does `gpu_detect.GPUGeneration.supports_hevc` only return `True` for Turing+,
while ADR-0007 D5 L149 claims HEVC is universal from Maxwell forward?

**CONFIRMED — the discrepancy is REAL.**

- **Code:** [gpu_detect.py:51-58](gpu_detect.py#L51-L58) — `supports_hevc` returns `True`
  only for `TURING, AMPERE, ADA, BLACKWELL`. `PRE_TURING` (the bucket that encompasses
  Maxwell 2014 + Pascal) returns **`False`**. So the code gates HEVC NVENC at **Turing+**.
- **ADR-0007 D5, L149** ([docs/decisions/ADR-0007-gpu-pipeline.md:149](docs/decisions/ADR-0007-gpu-pipeline.md#L149)):
  "NVENC works on any NVIDIA GPU from **Maxwell (2014) forward**; **h264_nvenc and
  hevc_nvenc are universal across that range.**" i.e. ADR-0007 says Maxwell/Pascal DO
  support HEVC NVENC. (L238 repeats "NVENC support extends back to Maxwell-generation.")
- **Conflict:** code (Turing+) ≠ ADR-0007 (Maxwell+). On a Pascal/Maxwell card, current code
  reports `hevc_available=False` even when the hardware + `hevc_nvenc` ffmpeg encoder are
  present. Hardware reality sides with ADR-0007 (2nd-gen Maxwell GM206 and all Pascal ship
  HEVC NVENC), so the **code's `supports_hevc` floor is too high** — a latent under-report
  of HEVC on pre-Turing cards, analogous to the A4 H.264 bug but NOT fixed by A4 (A4 left
  `hevc_available = hw_supports_hevc and codecs.hevc` unchanged).
- **Note:** the A4 CHANGELOG entry itself describes "Pascal/Maxwell — H.264-capable, no
  HEVC", embedding the same wrong assumption. So the inconsistency lives in code AND the new
  changelog narrative, opposite ADR-0007.

**Severity / scope:** This is a PRE-EXISTING latent issue, NOT introduced by A4 or B-015, and
NOT a blocker for either merge (both are correct within their declared scope). It is a
candidate new backlog/observation item (HEVC NVENC under-reported on Maxwell/Pascal). **Not
fixing — reporting only**, per instruction. Proposed direction for MAIN to consider later:
either lower the `supports_hevc` floor to include Maxwell/Pascal (matching ADR-0007 D5) the
same way A4 decoupled H.264, OR correct ADR-0007 D5 L149 if the Turing+ floor is intentional —
the two sources must be reconciled in one direction.

---

## FIX-PASS REVIEW — B-032 (`b8f3cb1`) `fix(render): cancellable GPU semaphore acquire under contention`

Reviewed 2026-05-24, verifier procedure + independent pre-fix repro.

**Claim:** `RenderWorker.process()` used a bare blocking `QSemaphore.acquire()`, so a queued
render under full-slot contention couldn't be cancelled. Fix adds module-level
`_acquire_gpu_slot()` (bounded `tryAcquire`+cancel-poll loop); `finally` releases only a held
slot; cancelled-while-waiting routes to the existing cancel handler.

### 1. Repro genuinely fails pre-fix? YES — PROVEN (not just green now)
Ran the committed test against `b8f3cb1^:auto_render.py` in a temp dir (repo source
untouched; `core`/siblings resolved from repo via PYTHONPATH). Pre-fix `auto_render.py`
contains **0** occurrences of `_acquire_gpu_slot` → **all 3 tests FAIL**:
`AttributeError: module 'auto_render' has no attribute '_acquire_gpu_slot'` (helper absent;
the contention test's daemon-thread call also raises it, so cancel is not honored). Post-fix:
**3 passed** on current tree. The helper is the load-bearing change and the tests genuinely
depend on it.

### 2. Semaphore balance — no over-acquire / over-release? CONFIRMED
- `_gpu_slot_held` inits `False` ([auto_render.py:431](auto_render.py#L431)); set `True` only
  when `_acquire_gpu_slot` returns `True`, which happens **only** on a successful
  `tryAcquire(1, poll_ms)` ([auto_render.py:225-229](auto_render.py#L225)). At most one permit
  taken (returns immediately on success) — **no over-acquire**.
- `finally` releases **only** `if _gpu_slot_held:` ([auto_render.py:465-467](auto_render.py#L466)):
  - **CPU path** (`_gpu_path_taken` False or `gpu_semaphore is None`): `_acquire_gpu_slot`
    never called → `_gpu_slot_held` stays False → **no release**. ✓
  - **Cancelled-during-acquire**: helper returns False → `_gpu_slot_held` False → **no
    release** (nothing was acquired). ✓ No over-release.
  - **Acquired then run/raise**: `_gpu_slot_held` True → released exactly once in `finally`,
    even on exception. ✓ 1 acquire ↔ 1 release.
- Pre-fix released unconditionally (`if _gpu_path_taken and gpu_semaphore is not None`); the
  new gate is equivalent on every path that actually acquired, and correctly skips release on
  the new no-acquire cancel path. **No balance regression.** (Also: GPU slot is released in
  `finally` *before* the L495 CPU-retry runs, so CPU retry never holds an NVENC slot — correct,
  unchanged.)

### 3. Cancel routing — read from control flow, not assumed? CONFIRMED CORRECT
Cancelled-while-waiting sets `rc = 0` ([auto_render.py:442-452](auto_render.py#L442)). Tracing
the current code:
- [auto_render.py:470](auto_render.py#L470) `if rc != 0 and _gpu_path_taken:` → `rc==0` makes
  this **False** → the entire GPU-fail branch (skip_file at :471 **and** CPU-retry at :495-522)
  is **skipped**. ✓ Does NOT trip the CPU-retry branch.
- [auto_render.py:523](auto_render.py#L523) `if self.is_cancelled:` → True on cancel (that's
  why the helper returned False) → emits "Cancelled", progress→0, cleans up placeholder/`.partial`,
  and **`return`** at [:544](auto_render.py#L544). ✓ Routes to the existing is_cancelled handler.
- [auto_render.py:545](auto_render.py#L545) `if rc == 0:` success branch → **never reached**
  (the `return` at :544 exits first). ✓ Does NOT hit the success/promote branch.

### 4. Footprint? CONFIRMED clean
`git show --name-only b8f3cb1` = exactly **CHANGELOG.md, auto_render.py,
tests/smoke/test_gpu_semaphore_cancel.py**. No baseline file, no `ffmpeg/*.dll`, no drive-by.

**B-032 VERDICT: READY-TO-MERGE**

Notes (non-blocking):
- **Coverage caveat (Minor):** the headless test exercises `_acquire_gpu_slot` in isolation;
  the rc=0 routing through `RenderWorker.process()` (steps 2-3 above) is verified here by
  code reading, and the commit explicitly labels live cancel-mid-NVENC on the 4080 as
  MANUAL-VERIFIED. Acceptable given no real NVENC in a headless suite, but the integration
  path itself has no automated coverage — flagging, not blocking.
- **Minor/nit:** CHANGELOG B-032 entry carries no own `[b8f3cb1]` 7-char hash per CLAUDE.md §4
  — same self-reference nit as A4/B-015 (repo backfill precedent `1be6adb`).

---

## DOCS AUDIT — CHANGELOG.md + BACKLOG.md accuracy

Audited 2026-05-24. **HEAD advanced during this run:** prompt pinned `53337b4`, actual HEAD is
**`ea7a67d`** (`fix(presets): B-041 drop stray double-quotes in 5s Cycle Zoom`, added by MAIN
mid-audit). `ea7a67d` is visible in my log → reconcilable, not "unverifiable." It touched
`CHANGELOG.md`, `assets/Encoder.json`, `assets/Encoder.txt` — **not** `BACKLOG.md` — which is
itself the source of finding **B3** below. All named fix-pass hashes (d438fb0, c051473,
b8f3cb1, 53bf0a2, a898c36, db2fb34, f308f4c, 53337b4) confirmed present; referenced hashes
`f4cf89a` and `c60baf5` also confirmed present (no broken/nonexistent hash refs).

### Findings table

| ITEM | FILE | ISSUE | SEV | SUGGESTED FIX |
|---|---|---|---|---|
| **C1** | CHANGELOG.md L71 | #4 entry's NOTE says `Encoder.json` "still carries the same `[v]` token and should be regenerated… if/when that path is promoted." **Now false** — `a898c36` regenerated it (verified on disk: **0** `[v]scale=720x1280`, **1** `[0:v]scale=720x1280`). Misleading: implies the json still has the bug. | **HIGH** | Rewrite the NOTE: `assets/Encoder.json` was regenerated in `a898c36` (deterministic regen; diff = the single `[v]`→`[0:v]` token). Drop the "should be regenerated if/when promoted" clause. |
| **C2** | CHANGELOG.md L65,67,99,103,268,425 | `[Unreleased]` block (L59→552, the only version block) has **3× `### Fixed`** (L67, L99, L425), **2× `### Changed`** (L63, L268), interleaved as Changed/Fixed/Fixed/Added/Changed/Fixed — violates Keep-a-Changelog one-subsection-per-category + canonical order (Added→Changed→Fixed). | LOW | Consolidate into a single `### Added`, single `### Changed`, single `### Fixed` in canonical order. Pre-existing fragmentation from merged work streams; fix-pass entries already co-located in the first `### Fixed`. |
| **C3** | CHANGELOG.md L65,69,71,73,75 | Fix-pass entries (B-015, B-041, #4, B-032, A4) carry **no own 7-char commit hash**, which CLAUDE.md §4 + the file's own Traceability table ("Commit hash … Every code change") mandate. (A4 cites `f4cf89a` baseline, not its own `d438fb0`.) | MED | Append: B-015 `[c051473]`, B-041 `[ea7a67d]`, #4 `[53bf0a2, a898c36]`, B-032 `[b8f3cb1]`, A4 `[d438fb0]`. Self-reference backfill, per repo precedent `1be6adb`. |
| **B1** | BACKLOG.md L43 | **B-015 status WRONG**: "scheduled (deferred per v2.5.1 audit…; LOW)". Actually **FIXED** by `c051473` + ADR-0015 (VERIFY: READY-TO-MERGE). | **HIGH** | Mark **RESOLVED** (`c051473`, [ADR-0015]); move to Resolved section. Resolution path taken = option (b) from its own entry (new ADR documents single-knob). |
| **B2** | BACKLOG.md L318 | **B-032 status WRONG**: "Open, Low". Actually **FIXED** by `b8f3cb1` (VERIFY: READY-TO-MERGE). | **HIGH** | Mark **RESOLVED** (`b8f3cb1`); the entry's own "Fix sketch" (tryAcquire+cancel poll loop + smoke test) matches what shipped. Move to Resolved. |
| **B3** | BACKLOG.md L431 | **B-041 status STALE**: "Open, backlog. Adam to decide whether to fix this session." Actually **FIXED** by `ea7a67d` (post-pin; CHANGELOG L69 already records it, but `ea7a67d` did not update BACKLOG). | **HIGH** *(recheck)* | Mark **RESOLVED** (`ea7a67d`). **Recheck caveat:** depends on `ea7a67d`, which landed during this audit; re-confirm it is final before closing. |
| **B4** | BACKLOG.md | **Size = 56,143 chars** (was ~48.3k; > 40k Claude Code perf warning). | LOW | Archive RESOLVED/CLOSED to `BACKLOG_ARCHIVE.md`. Candidates + measured sizes below. |

### Statuses that are CORRECT (no change needed)
- **B-040** (L415) "Open, backlog — do NOT fix in current GPU pass" ✓ accurate (it's my HEVC
  gen-gate side-issue, deliberately deferred; `db2fb34` filed it).
- **B-042** (L443) "CLOSED — won't-fix (2026-05-24)" ✓ accurate (#6 tokenizer won't-fix).

### Cross-references (check 6) — INTACT
- **B-042 → B-041:** L451 authoring guideline "do NOT wrap a whole value in shell-style
  double-quotes (see B-041)"; B-041 L437 also back-refs #6. ✓
- **B-040 → A4 wording:** L423-425 explicitly names the A4 CHANGELOG entry ("Pascal/Maxwell —
  H.264-capable, no HEVC") AND the A4 test docstrings as wording to correct when B-040 is
  fixed. ✓ No broken/missing cross-refs found.

### Duplicates (check 7) — NONE
No duplicate B-NNN IDs; no two entries describing the same issue. (B-013 "NVENC constants
declared but unused" is thematically adjacent to B-015's dead-`mapped`-var but is a distinct
issue — not a duplicate.)

### Archival candidates (check 9) — measured, NOT moved
BACKLOG total **56,143 chars**. Archive to `BACKLOG_ARCHIVE.md`:

| Candidate | Lines | Chars |
|---|---|---|
| B-033–B-039 (Phase 3.1–3.7 milestones, all RESOLVED) | 326–412 | 9,630 |
| B-042 (CLOSED won't-fix) | 441–453 | 2,585 |
| Resolved-section list | 454–end | 997 |
| B-017 (RESOLVED) | 61–66 | 636 |
| B-029 (RESOLVED) | 291–295 | 572 |
| **Subtotal** | | **14,420 → leaves 41,723** |

41.7k is still marginally over 40k. Also archiving **B-015 + B-032 + B-041 once marked
RESOLVED** (B1/B2/B3, ≈4k combined) brings BACKLOG to **≈37.7k** — comfortably under the 40k
warning. Biggest single win is the B-033–B-039 Phase-3 milestone block (9.6k).

### Prioritized fix-list for MAIN (HIGH → LOW)
1. **B1 (HIGH)** — BACKLOG B-015 status → RESOLVED (`c051473`, ADR-0015).
2. **B2 (HIGH)** — BACKLOG B-032 status → RESOLVED (`b8f3cb1`).
3. **B3 (HIGH, recheck)** — BACKLOG B-041 status → RESOLVED (`ea7a67d`); confirm `ea7a67d` final.
4. **C1 (HIGH)** — CHANGELOG #4 NOTE: state Encoder.json regenerated in `a898c36`; drop stale "should be regenerated" clause.
5. **C3 (MED)** — CHANGELOG: append own commit hashes to A4/B-015/B-032/#4/B-041 entries.
6. **C2 (LOW)** — CHANGELOG: consolidate the 3×Fixed / 2×Changed into one each, canonical order.
7. **B4 (LOW)** — Archive resolved entries (table above) to get BACKLOG < 40k.

### Per-file verdicts
- **CHANGELOG.md: NEEDS-FIXES** (1 HIGH stale-fact, 1 MED traceability, 1 LOW structure).
- **BACKLOG.md: NEEDS-FIXES** (3 HIGH stale statuses, 1 LOW size). Cross-refs + dup-check clean.

---

## FIX-PASS REVIEW — preset/docs commits (53bf0a2, a898c36, ea7a67d, 82ff187)

Reviewed 2026-05-24. HEAD has since advanced to `ffaa4ce` (closes #5 won't-fix — out of this
review's scope, noted only). All four target commits confirmed present; footprints verified
via `--name-only`.

### 53bf0a2 — #4 Encoder.txt L76 `[v]`→`[0:v]`
- **Footprint:** `CHANGELOG.md` + `assets/Encoder.txt` only.
- **Only L76 changed?** YES — `git show --stat` = 1 insertion / 1 deletion; the single diff
  hunk is the "9:16 Bitrate" preset, `-filter_complex [v]scale=720x1280` → `[0:v]scale=720x1280`.
- **`[v1]`..`[v26]` split labels untouched?** YES — a 1-line diff cannot touch them; surrounding
  preset rows in the hunk context are byte-identical.
- **Preset still parses?** YES — `core.preset_loader.load_presets(Path('assets/Encoder.txt'))`
  returns **106 presets**; "9:16 Bitrate" resolves to
  `('-filter_complex', '[0:v]scale=720x1280,setdar=9/16', '-vcodec', 'libx264', …)`. Clean.
- **VERDICT: READY-TO-MERGE**

### a898c36 — #4 Encoder.json regen
- **Footprint:** `assets/Encoder.json` only.
- **Clean one-token regen, no reformat/reorder?** YES — `--numstat` = **1 / 1**; the only changed
  line is the params entry `"[v]scale=720x1280,setdar=9/16"` → `"[0:v]scale=720x1280,setdar=9/16"`.
- **Generated from fixed Encoder.txt, NOT hand-edited?** YES — **proven deterministically.**
  Re-ran `tools/generate_encoder_json.py` against the current (fixed) `Encoder.txt`; the freshly
  generated `assets/Encoder.json` is **byte-identical to the committed file** (`git status` shows
  it unmodified after regen). A hand-edited or reordered file would have diverged. The committed
  artifact is exactly what the generator emits.
  *(Note: invoking the generator inadvertently rewrote `assets/Encoder.json` in the working tree,
  but since output is identical there is NO net tree change — read-only posture intact.)*
- **VERDICT: READY-TO-MERGE**

### ea7a67d — B-041 "5s Cycle Zoom" stray outer double-quotes
- **Footprint:** `CHANGELOG.md` + `assets/Encoder.json` + `assets/Encoder.txt`.
- **Only the stray OUTER double-quotes removed?** YES — Encoder.txt L43: 1 ins / 1 del. Before:
  `-vf "scale=…zoompan=z='…':…:s='iw*1.5:ih*1.5'"`. After: the wrapping `"…"` is gone.
- **Inner zoompan single-quotes preserved?** YES — `z='if(between(mod(t,5),0,3),1,…)'`,
  `x='iw/2-(iw/zoom/2)'`, `y='ih/2-(ih/zoom/2)'`, `s='iw*1.5:ih*1.5'` all intact (those are
  ffmpeg's own quoting). Parsed result confirms it:
  `('-vf', "scale=iw*1.5:ih*1.5,zoompan=z='…':…:s='iw*1.5:ih*1.5'", '-c:a', 'copy', …)` — no
  leading/trailing `"`.
- **Encoder.json regen matches?** YES — `--numstat` = 1 / 1; the params `-vf` value loses exactly
  the escaped outer `\"…\"`, inner single-quotes kept. Consistent with the Encoder.txt edit.
- **VERDICT: READY-TO-MERGE**
  (Non-blocking: live "5s Cycle Zoom" render is MANUAL-VERIFIED per the entry; no automated
  render check — same accepted caveat as the other preset fixes.)

### 82ff187 — docs reconciliation (BACKLOG + CHANGELOG)
- **Footprint:** `BACKLOG.md` + `CHANGELOG.md` only — **docs-only; no code/behavior change.** CONFIRMED.
- **B-015/032/041 statuses now correct?** YES —
  - B-015: active entry removed, moved to **Resolved** with `[c051473]` + ADR-0015 link (addresses my B1).
  - B-032: status → **`RESOLVED [b8f3cb1] 2026-05-24`** (keeps "Status (original): Open, Low" for history; addresses B2).
  - B-041: status → **`RESOLVED [ea7a67d] 2026-05-24`** (addresses B3).
- **#4 stale "should be regenerated" clause gone?** YES — the L71 clause is replaced by "The
  generated `assets/Encoder.json` … was regenerated with the same fix `[a898c36]`. `[53bf0a2]`."
  (addresses my C1 — the misleading claim is gone).
- **Hashes present?** YES — own commit hashes appended to all five fix entries: B-015 `[c051473]`,
  B-041 `[ea7a67d]`, #4 `[53bf0a2, a898c36]`, B-032 `[b8f3cb1]`, A4 `[d438fb0]` (addresses my C3).
- **No code snuck in?** CONFIRMED — only the two doc files touched; no source/asset change.
- **VERDICT: READY-TO-MERGE**

### Carry-over (still open after 82ff187 — explicitly deferred in its commit msg)
- **C2 (LOW)** — CHANGELOG still has 3× `### Fixed` / 2× `### Changed` fragmentation (not reordered).
- **B4 (LOW)** — BACKLOG archive not yet done (still > 40k).
Both are LOW and acknowledged by MAIN as deferred — not a merge blocker for these commits.

### Working-tree observation (not a commit finding)
`setup.ps1` shows **uncommitted (` M `)** in the shared working tree — a 49+/9− WIP edit adding a
**capability-qualified ffmpeg selector** (libvmaf = HARD requirement, NVENC = SOFT, deterministic
alphabetical tiebreak). This is MAIN's in-progress work (the "setup.ps1 libvmaf selector" item),
not part of any reviewed commit and not caused by VERIFY. Left untouched. Flagging for awareness;
it should be reviewed once MAIN commits it.

---

## 4080 MANUAL-VERIFY QUEUE (merge gate) — VERIFY session run, 2026-05-24

Environment confirmed: **on the Legion RTX 4080** (`nvidia-smi`: NVIDIA GeForce RTX 4080 Laptop
GPU, driver 591.44, 12 GB). Branch `phase3-fixes`, HEAD `bbf21b1`, tree clean (RESULTS.md
untracked). `bbf21b1` (#7 setup.ps1) is committed. No `main.json` (MAIN not signaling a GPU render).

**Role boundary (important):** I am the READ-ONLY VERIFY session, not a human operator. Items that
require interactive GUI clicks, subjective visual judgment, a venv-recreating `setup.ps1` run in
this shared tree, or live NVENC encodes (governance-blocked from bash) cannot be honestly executed
by this session. Per CLAUDE.md §2 I do not fabricate a PASS for anything I did not observe. Below,
each item is marked with what I actually verified vs. what must stay with a human on the 4080.

### MERGE-GATE VERDICT: ❌ DO NOT MERGE
**Item 3 (B-041) FAILED.** Per the queue's own rule ("IF ANY ITEM FAILS: do NOT merge"), the gate
is closed. I did not perform the merge (also outside my read-only lane). Items 1 (full run) and 4
remain unverified and need a human on the 4080.

### Item 1 — #7 setup.ps1 capability selector (bbf21b1): ⚠ PARTIAL (logic verified; full run deferred)
- **Selector logic (read bbf21b1 `setup.ps1` L114-172): SOUND.** Capability-based, not name/mtime:
  enumerates sibling `../*/ffmpeg/` with both exes, excludes own dir, `Sort-Object` only as a
  *deterministic tiebreak*. HARD-rejects builds lacking the libvmaf filter (regex
  `^\s*\S+\s+libvmaf\b` — matches the filter line, not an incidental substring); NVENC is a SOFT
  preference (`_nvenc` encoder → take immediately); libvmaf-only build kept as fallback with a
  warning; clear warn + no silent bad pick if nothing qualifies.
- **Probe replicated (non-destructive):** all four candidate builds
  (`1vmo-suite`, `…-handoff-4b68846`, `…-phase2d-e315e3c`, bundled `./ffmpeg`) pass the libvmaf
  HARD gate (1 libvmaf filter line each). Bundled build also has 3 NVENC encoders (baseline) →
  full-capability qualifying.
- **NOT executed:** a true end-to-end run (the selector only fires when `ffmpeg/` is EMPTY; here it
  is populated, so a plain `setup.ps1` run hits "ffmpeg already present" and skips the selector).
  Forcing it would mean emptying `ffmpeg/` and recreating the venv in a tree shared with MAIN —
  out of read-only scope. **Defer the fresh-checkout run to a human / disposable checkout.** The
  "picks libvmaf+nvenc, NOT alphabetically-first-regardless" assertion is supported by the logic
  + probe, but not yet observed end-to-end.

### Item 2 — A4 gpu_detect sanity (d438fb0): ✅ PASS
`gpu_detect.detect(Path('ffmpeg/ffmpeg.exe'))` on the 4080 returns:
`has_nvidia=True, nvenc_available=True, h264_available=True, hevc_available=True,
av1_available=True, error=None`, primary = RTX 4080 Laptop (Ada Lovelace, CC 8.9). No exception.
H.264 available, HEVC available, NVENC detected → regression sanity PASS. (As the prompt notes, the
original A4 bug can't repro on Ada; this only confirms no regression.)

### Item 3 — B-041 "5s Cycle Zoom" renders (ea7a67d): ❌ FAIL  ← BLOCKS MERGE
**The preset does NOT render after the B-041 fix.** Verified headless via the app's exact
invocation path (preset_loader params → `subprocess` list form, CPU libx264 — faithful to
RenderWorker; no NVENC involved).

- **Exact command built (the `-vf` value is ONE argv token; outer `"` already removed by B-041):**
  ```
  ffmpeg -i <input> -vf scale=iw*1.5:ih*1.5,zoompan=z='if(between(mod(t,5),0,3),1,if(between(mod(t,5),3,4),1.25,1.5))':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s='iw*1.5:ih*1.5' -c:a copy -vcodec libx264 -crf 18 -preset superfast -y <out>
  ```
- **ffmpeg result:** `rc=4294967274` (int32 wrap of `-22`/EINVAL). stderr:
  `[AVFilterGraph] No option name near 'ih*1.5'` → `Error parsing filterchain …` →
  `Error opening output files: Invalid argument`. **No output produced.** This is a *parse* error —
  input-independent, the render never starts.
- **Isolation (all CPU, on synthetic testsrc2 input):**
  | variant | result |
  |---|---|
  | `scale=iw*1.5:ih*1.5` alone | PASS |
  | `zoompan=z=1.5:d=1` (minimal) | PASS |
  | `zoompan=z='1':d=1:s=640x360` (quoted expr + literal x-size) | PASS |
  | `zoompan=z='1':d=1:s='640:360'` (colon inside single-quoted `s=`) | **FAIL — "No option name"** |
  | full preset string | **FAIL — "No option name near 'ih*1.5'"** |
  | zoompan z/x/y expressions with `s=` removed | **FAIL — runtime "Invalid argument / Nothing was written / Conversion failed"** |
- **Two distinct defects (B-041 fixed neither — it only removed the outer shell double-quotes):**
  1. **Parse:** `s='iw*1.5:ih*1.5'` — the `:` inside the single-quoted `s=` value is not honored as
     a literal by ffmpeg's filter-option parser here; it splits on the colon → "No option name".
     (Separately, zoompan's `s` size option does not accept `iw`/`ih` expressions at all — it needs
     a literal `WxH`.)
  2. **Runtime:** even with `s=` removed, the zoompan `z`/`x`/`y` expression chain fails at runtime
     (EINVAL, zero packets written). The zoompan design itself needs rework.
- **Why this matters:** B-041's double-quote removal is a *correct prerequisite* (it changed the
  error from "No such filter" to a deeper parse error), but it is **incomplete** — the preset is
  still unrenderable. The CHANGELOG/BACKLOG hedge ("render correctness pending MANUAL-VERIFIED") is
  now resolved to **FAIL**.
- **Proposed direction for MAIN (describe, do not fix — read-only):** reopen B-041. Give `zoompan`
  a literal output size (a fixed `WxH`, or drop `s=` and append a separate `scale` to 1.5×), and
  validate the `z`/`x`/`y` expressions actually emit frames — then re-verify with a real render.
  **B-041 BACKLOG status `RESOLVED [ea7a67d]` is premature → should revert to Open** with these
  findings; the CHANGELOG #4/B-041 area stays under "Fixed" only for the double-quote removal, not
  for render correctness.

### Item 4 — B-032 cancel mid-NVENC under contention (b8f3cb1): ⏭ NOT EXECUTED (needs human on 4080)
This is the interactive integration path: it requires the GUI app running multiple concurrent
renders to create genuine semaphore contention, then **timing-sensitive manual cancels** of a
waiting render and an actively-encoding render, plus visual confirmation of prompt-stop, no
deadlock, a fresh render re-acquiring the slot, and no orphaned partials. An automated read-only
session cannot drive the PySide6 GUI or time the cancels; additionally, **ad-hoc NVENC ffmpeg from
bash is governance-blocked** (the `block-dangerous.sh` hook rejected even a `_nvenc` substring this
session — confirming the guard works), so a scripted live-NVENC harness is intentionally off-limits
here. The headless review already established the `_acquire_gpu_slot` logic + rc=0 cancel routing
are sound (see B-032 review above); only the **live integration** remains, and it must be done by a
human on the 4080 following the queue's Item-4 checklist. **Status: unverified.**

### Coordination / hygiene
- GPU: no NVENC render performed by VERIFY (Item 2 = detection only; Item 3 = CPU libx264).
  `verify.json` stayed non-RENDERING; no collision risk with MAIN.
- All test artifacts were written to `%TEMP%` (outside the repo). The repo working tree is
  unchanged by this verification (only RESULTS.md / gitignored verify.json written).

---

## FINAL RECONCILIATION (post-merge, HEAD 684523d) — supersedes mid-pass verdicts above

Recorded 2026-05-24 on branch `phase3-adam-v39-merge` @ `684523d`. The sections above are a
**mid-pass snapshot** (taken at HEAD `bbf21b1`, before the B-041 follow-up fix and the merge)
and are left intact as the honest record of what I saw at the time. Three verdicts in them are
now superseded by work that landed afterward. Each item below was **re-confirmed against the
current tree** (git log / file contents / a CPU-only headless render); hardware-only PASSes are
attributed to the human operator (CLAUDE.md §2 — I do not fabricate a hardware PASS).

Log hashes re-confirmed present on this branch: `ccd6b36`, `7f01263`, `fcd424b`, `d32f3c1`,
`684523d` (all resolve via `git log -1`).

### 1. B-041 "5s Cycle Zoom" — was ❌ FAIL (@ ea7a67d) → now ✅ PASS (@ ccd6b36)
- **Re-confirmed by me (current tree):**
  - `ccd6b36` (`fix(presets): B-041 zoompan literal size + time var + fps`) is in the log.
  - `assets/Encoder.txt` L43 now has **`s=576x1024`** (literal — old `s='iw*1.5:ih*1.5'` absent),
    **`mod(time,5)`** (×2 — `mod(t,5)` absent), and **`:fps=30`**.
  - **CPU-only headless render of the committed preset: `rc=0`, no error signatures**; output
    video 576x1024 @ 30/1 fps, duration 6.000s; audio duration 6.000s → **A/V aligned, delta
    0.000s**. (No GPU touched — libx264 CPU path.)
- **Operator-verified on hardware (per Adam):** live RTX 4080 render confirmed PASS — zoom cycles
  correctly, A/V aligned (6.000s == 6.000s), renders after app Refresh. I did not run the GUI/live
  path; this PASS is attributed to the operator.
- **Why the earlier FAIL was correct:** my snapshot tested `ea7a67d`, which had only removed the
  outer double-quotes and still hit the `s='iw*1.5:ih*1.5'` parse error + the `mod(t,5)` runtime
  failure. `ccd6b36` fixed both (literal size + `time` var) plus the zoompan-default-25fps A/V
  desync (`:fps=30`). The FAIL drove the fix — gate working as intended.
- **Verdict now: READY-TO-MERGE / RESOLVED [ccd6b36]** (BACKLOG B-041 = RESOLVED, confirmed).

### 2. #7 setup.ps1 capability selector — was ⚠ PARTIAL → now ✅ PASS (happy path)
- **Operator-verified on hardware (per Adam):** ran end-to-end on a disposable checkout with an
  empty `ffmpeg/`; output showed **"Selected ffmpeg by capability"** + **"all 7 app modules import
  cleanly"**. The selects-a-libvmaf-build happy path is now observed end-to-end (my snapshot had
  only logic-read + non-destructive probe). Attributed to the operator.
- **Limit still standing:** the **reject-bad-build path** (a sibling that lacks libvmaf →
  warn-and-skip / fall back) remains **code-read only** — not exercised end-to-end with a
  deliberately-stripped ffmpeg. Low risk (logic is a straightforward filter), but stated as a gap.
- **Verdict now: PASS (happy path verified; reject path code-read only).**

### 3. B-032 cancel-under-contention — was ⏭ NOT EXECUTED → now ✅ PASS
- **Operator-verified on hardware (per Adam):** ran the cancel-under-contention test on the 4080
  GUI — cancel stops promptly **and** a fresh render re-acquires the GPU afterward (no semaphore
  leak, no deadlock). This is the interactive/live-NVENC path I could not drive (and ad-hoc NVENC
  from bash is governance-blocked). Attributed to the operator. My earlier headless review had
  already confirmed the `_acquire_gpu_slot` logic + rc=0 cancel routing are sound; the live
  integration is now also confirmed.
- **Verdict now: PASS.**

### 4. MERGE-GATE — was ❌ DO NOT MERGE → now ✅ GATE GREEN — MERGED
- All four gate items now pass: **A4 ✅** (re-confirmed by me on the 4080: detect() reports
  h264/hevc/av1/nvenc all available), **#7 ✅** (operator), **B-041 ✅** (me headless + operator
  hardware), **B-032 ✅** (operator).
- **Merge performed:** `7f01263` (`merge: phase 3 fix-pass (A4/B-015/B-032/#4/B-041/#7 + #5,#6
  won't-fix)`) — confirmed in log.
- **Post-merge docs cleanup committed:** `fcd424b` (mark B-041 resolved), `d32f3c1` (backfill
  fix-pass hashes), `684523d` (consolidate [Unreleased] sections) — all three confirmed in log.
- **Verdict now: ✅ GATE GREEN — MERGED.**

### 5. Still open (carry forward — NOT merge blockers)
- **B-040** (HEVC gen-gate under-reports HEVC NVENC on Maxwell/Pascal, A4-class) — re-confirmed
  **still Open** in BACKLOG ("Open, backlog. Do NOT fix in the current GPU fix-pass"). Filed for a
  later dedicated NVENC-gate pass. (This is the side-issue I flagged earlier.)
- **BACKLOG < 40k archive** (B4) — deferred; BACKLOG still over the perf-warning threshold.
- **#7 reject-bad-build path** — code-read only (see item 2 above).

### Reconciliation self-review
- B-041 fix tokens re-confirmed from `assets/Encoder.txt` L43, not assumed?    YES
- B-041 now renders rc=0 + A/V aligned, re-run CPU-only by me?                 YES (576x1024/30fps, 6.000s==6.000s)
- Hardware PASSes attributed to the operator, not claimed as mine?            YES (#7, B-032, B-041 live)
- All 5 superseding/merge hashes confirmed in the log?                        YES (ccd6b36, 7f01263, fcd424b, d32f3c1, 684523d)
- B-040 re-confirmed still Open?                                              YES
- Earlier snapshot sections left intact (append-only)?                        YES
- No GPU/NVENC run by VERIFY in this reconciliation (CPU libx264 only)?       YES

---
---

# MANAGER REVIEW — phase-a-url-dl-hardening  (phase: url-dl-hardening)

- **Recorded:** 2026-05-24
- **Auditor:** VERIFY session via `/manager-review` (read-only)
- **Base:** `phase3-adam-v39-merge` (`7484196`) → **HEAD** `9a2263a` (14 commits)
- **Scope diff:** `core/url_downloader.py`, `requirements.txt`, `tests/smoke/test_url_downloader.py` (matches main.json `scope_files` exactly)
- **Rules applied:** 14 durable + 10 `phase_rules["url-dl-hardening"]`
- **Suite re-run by me:** `pytest tests/smoke/test_url_downloader.py` → **28 passed, 6 skipped** (6 online deselected); `py_compile` OK. ruff not installed in this venv (MAIN's "ruff: All checks passed" not independently re-confirmed).

## Verdict: **PASSED_WITH_WARNINGS** · Grade **A** (95%)

`score_pct = 20 / (20 + 0 + 2*0.5) * 100 = 95.2`. 20 PASS, 0 FAIL, 2 WARN, 2 SKIP. No critical FAIL ⇒ not blocked.

| rule id | name | severity | result | evidence |
|---------|------|----------|--------|----------|
| URLDL-C1-FORMAT | Quality-maximal mkv intermediate | critical | ✓ PASS | `QUALITY_FORMATS` L117-124 has no `[ext=...]` pins, height caps retained (`bv*[height<=1080]+ba/b...`); `merge_output_format":"mkv"` L338; glob fallback `glob.escape(filename.stem)` L523, no `.mp4` preference (`candidates[0]` L525). |
| URLDL-C2-HOOK | Progress hook trivial (#5957) | critical | ✓ PASS | `_hook` L437-459 hot path = 3 `d.get` reads + one division (L450-452) + callback; `logger.exception` is in the cold except (caller-callback failure only) L458-459. `subtitle_langs` threaded: `download_videos` L572 → `_download_one` L406 → `_build_ydl_opts` L320 → `list(subtitle_langs)` L379. Online subs+progress test L412-435 asserts video+`.srt`+`max(seen)>=100`. |
| URLDL-C3-CLEANUP | Partial-file cleanup after with-block | critical | ✓ PASS | `paths={"home":work_dir,"temp":temp_dir}` L333; `temp_dir=work_dir/".ytdl_tmp_{idx}"` L461; `shutil.rmtree(temp_dir, ignore_errors=True)` in `finally` L558-561, AFTER the `with YoutubeDL` (L482) closes — not in the hook. Online cancel test L440-464 asserts `cancelled` + zero `.part`/`.ytdl` + temp dir gone + pool drained. |
| URLDL-C4-DENO | Bundled Deno / JS runtime | critical | ✓ PASS | `_resolve_bundled_js_runtime` L75-95 mirrors ffmpeg resolver (`_MEIPASS`→repo root, `deno(.exe)`); PATH prepend at import L98-105; `no_warnings` absent, `"logger": logger` L356; `js_runtime_missing` branch L232-233. Deno binary + .spec = noted integration task, not failed (per rule note). |
| URLDL-C5-COOKIES | cookies_file replaces cookies_browser | critical | ✓ PASS | `grep cookies_browser\|VALID_BROWSERS` = **0**. `cookies_file:Optional[Path]` L575, validated `is_file`→FileNotFoundError / `R_OK`→PermissionError L623-628, `opts["cookiefile"]` L390; `cookies_invalid` branch L234-242; caller-owns-consent docstring L586-591. |
| URLDL-C6A-LIMITS | Timeouts, concurrency cap, live guard | warning | ✓ PASS | `socket_timeout:30` L343; `max_concurrent>16` rejected L614-622 (bool + `>=1` kept); `is_live` guard after `extract_info(download=False)` probe L488-494. |
| URLDL-C6B-CONTRACT | One result per URL guaranteed | critical | ✓ PASS | None-fill loop L694-704 synthesises a failed result for any `None` slot, preserves order — not a bare filter. Test L280-293 monkeypatches `as_completed`→empty, asserts `len(out)==len(urls)` + order. |
| URLDL-C6C-ERRORCATS | Error categorization gaps closed | warning | ✓ PASS | `ImportError→dependency_missing` L213-214 + L431-435; members-only→`auth_required` L251-254; `"blocked"+"country"`→`region_locked` L262-263. Tests L189-216. |
| URLDL-C7-PIN | yt-dlp[default] pin bumped | critical | ✓ PASS | `requirements.txt:25` `yt-dlp[default]>=2026.03.17` — regex `yt-dlp\[default\]>=2026\.03\.17` matched. |
| URLDL-C8-PROXY | Optional proxy support | warning | ✓ PASS | `proxy:Optional[str]`→`opts["proxy"]` L395-396; scheme regex `^(https?\|socks5h?\|socks4)://` raises ValueError L633-637; `""`=direct L632-633; `geo_bypass` only in a comment (NOT set) L393; `proxy_error` branch L277-291; module reads no env/config. Tests L230-255. |
| DURABLE-CONTRACT | Per-item failures never raise | critical | ✓ PASS | `_download_one` always returns a Result (every path caught); `download_videos` raises only on arg/precondition validation (L601-646); worker exceptions caught + categorised L681-688; None-fill guarantees a Result. |
| DURABLE-NO-SILENT-CATCH | No silent error swallowing | warning | ✓ PASS | Every `except` in the diff logs or returns a categorised result (L423-427, L431-435, L456-459, L497-513, L681-688). `rmtree(ignore_errors=True)` L561 = deliberate best-effort cleanup (rule's allowed exception). |
| DURABLE-SCOPE | Diff stays within phase scope | critical | ✓ PASS | `git diff --name-only` = the 3 declared files only; governance files (quality-rules.json/.claude) git-ignored locally + excluded by rule. |
| DURABLE-COMMITS | One issue per commit | warning | ✓ PASS | 14 commits, each names one C-item; `53682f1` is an honest single-purpose fixup (restore shutil import). No bundling. |
| DURABLE-DOCS | Docs / ADR move with behavior | warning | ⚠ WARN | Stale comment `core/url_downloader.py:39` still says `merge_output_format=mp4`, but C1 changed it to `mkv` (L338) — doc drift where behavior changed. Also new `subtitle_langs` param is undocumented in the `download_videos` docstring (L579-600 covers cookies_file/proxy only). Fix: update the L39 comment to `mkv` and add a `subtitle_langs` line to the docstring. |
| DURABLE-HOOK-CONV | Hook scripts follow 1vmo convention | critical | ⊘ SKIP | No Claude Code hook script in the diff. |
| QT-THREADSAFE | No UI access from worker threads | critical | ⚠ WARN | Core satisfied: the module touches zero Qt widgets. But `progress_callback` is invoked from worker threads (`_hook` fires on the download thread, L438) and the public `download_videos` docstring never states this — a future caller could wire a direct widget update into it and crash under a batch. The internal `_hook` comment documents the thread context; the caller-facing contract does not. Fix: add a docstring line — "progress_callback fires on worker threads; marshal any Qt UI update via a signal/queued connection." |
| NO-BLOCK-EVENTLOOP | No blocking calls on the GUI thread | warning | ⊘ SKIP | No GUI-thread code in the diff; the module is worker-side by design (the QThread caller `URLDownloadWorker` is out of scope, verified-not-modified per main.json). |
| SUBPROCESS-SAFE | FFmpeg / external process handling is safe | critical | ✓ PASS | No raw `subprocess`/`shell=True` in the diff; ffmpeg/deno are driven by yt-dlp in library mode (bundled binaries via `ffmpeg_location` L366 + PATH for Deno); `socket_timeout` bounds I/O; cancel via `_CancelledMarker` from the hook. |
| FROZEN-BUILD | Frozen-build path correctness | critical | ✓ PASS | New Deno dependency resolved via `_MEIPASS`→repo root (L86-94) + PATH injection — mirrors the ffmpeg pattern; no bare-PATH/abs-dev-path assumption. The PyInstaller `.spec` entry + shipping the `deno` binary are the noted separate integration task (not a module FAIL, per C4). |
| RESOURCE-CLEANUP | Resources released on all paths | warning | ✓ PASS | temp dir `rmtree` in `finally` (success/error/cancel) L558-561; `ThreadPoolExecutor` (L660) and `YoutubeDL` (L482) both context-managed. |
| NO-SECRETS-PATHS | No hardcoded secrets or machine paths | critical | ✓ PASS | Added-line scan found only test fixtures (`1.2.3.4:8080`, `127.0.0.1:9050`); no `C:\Users\...`, API keys, or credentials. |
| TESTS-PRESENT | Behavior changes ship with tests | warning | ✓ PASS | Each C-item maps to a test: C1 L264, C2 L412, C3 L440, C4 L336/L343, C5 L165/L174/L218, C6a L116/L125/L296, C6b L280, C6c L189/L201/L211, C8 L230-255. |
| DETERMINISTIC-TESTS | Tests are deterministic | warning | ✓ PASS | Offline tests hit no network; the 6 network tests are `@pytest.mark.online` + `@_skip_online`; is_live / lost-future use `monkeypatch` (deterministic). |

### Warnings to acknowledge (non-blocking)
1. **DURABLE-DOCS** — `core/url_downloader.py:39` stale `merge_output_format=mp4` comment (now `mkv`); `subtitle_langs` undocumented in the docstring.
2. **QT-THREADSAFE** — `download_videos` docstring doesn't warn that `progress_callback` runs on a worker thread (scale-risk for a future caller; the lone current caller marshals correctly).

### Observations (info — not scored)
- C2 subs+progress (L412) and C3 no-orphan (L440) guards are **online-only**, so the offline CI does not exercise the subtitle/cleanup assertions — run `RUN_ONLINE_TESTS=1` periodically to keep them honest.
- C6c adds a metadata-only `extract_info(download=False)` probe before each download (one extra round-trip/URL) — acceptable, already noted by MAIN.

### Manager-review self-review
- Read the actual post-fix code in full, not the commit messages?            YES (709-line module + 481-line test read end-to-end)
- Every PASS/FAIL/WARN cited to a real file:line, re-verified this session?    YES
- Offline suite re-run by me and counted from real output (28 passed)?         YES
- C7 pin confirmed by regex match, C5 removal by grep=0, C8 geo_bypass absent?  YES
- No critical FAIL ⇒ correctly NOT blocked; no BLOCKERS.json / CLAUDE.md edit?  YES
- No source/test/config edited by VERIFY (governance outputs only)?            YES

---
---

# MANAGER REVIEW — phase-a-url-dl-hardening (RE-GRADE after C3 fix)

- **Recorded:** 2026-05-24
- **Phase key:** `url-dl-hardening` (branch substring; main.json.phase absent)
- **Base:** `phase3-adam-v39-merge` (7484196)
- **Audited HEAD:** `ca8d34f` (main.json.last_sha 9a2263a is stale; branch advanced by the doc + C3-fix commits — audited current HEAD)
- **Changed files (scope):** `core/url_downloader.py`, `requirements.txt`, `tests/smoke/test_url_downloader.py`, `CHANGELOG.md` (+550 / −77)

> This re-grade SUPERSEDES the prior A/95% PASSED_WITH_WARNINGS section above. The prior
> URLDL-C3-CLEANUP "pass" was static-only and hollow (an online cancel test then proved temp
> isolation was a no-op: absolute `outtmpl` made yt-dlp ignore `paths`). C3 was fixed in
> `8a5fef6`; this pass re-verifies it with FIRST-HAND RUNTIME evidence, not structure alone.

## Verdict table

| rule id | name | severity | result | evidence |
|---|---|---|---|---|
| DURABLE-CONTRACT | Per-item failures never raise | critical | PASS | `_download_one` returns a DownloadResult on every error path (L420/431/439/498/504/517/537); aggregation loop catches `fut.result()` and records a result (url_downloader.py:690-699); only arg-validation raises (L612-657) |
| DURABLE-NO-SILENT-CATCH | No silent swallowing | warning | PASS | every except logs/re-raises/records: L429,437,503,507,692; hook's `except Exception` logs `logger.exception` and re-raises `_CancelledMarker` first (L462-465) — matches the callback-guard exception clause |
| DURABLE-SCOPE | Diff within scope | critical | PASS | 4 changed files all on-phase (module + pin + tests + CHANGELOG); no out-of-scope path |
| DURABLE-COMMITS | One issue per commit | warning | PASS | 18 commits, each single-concern + descriptive (C1..C8, C3 fix 8a5fef6, doc/changelog split) |
| DURABLE-DOCS | Docs move with behavior | warning | PASS | **prior warning CLEARED**: L39 comment now `merge_output_format=mkv`; `subtitle_langs` documented (L592); cookies_file consent (L597-602); proxy (L604-610) [cb8fe69] |
| DURABLE-HOOK-CONV | Hook script convention | critical | SKIP | no Claude Code hook script in the diff |
| QT-THREADSAFE | No UI access from workers | critical | PASS | **prior warning CLEARED**: module touches no Qt; docstring L593-595 states `progress_callback` fires on WORKER threads and callers must marshal via signal/queued connection [cb8fe69] |
| NO-BLOCK-EVENTLOOP | No blocking on GUI thread | warning | SKIP | no GUI-thread code in diff; module is worker-side by design |
| SUBPROCESS-SAFE | External-process handling safe | critical | PASS | no `shell=True` / no direct subprocess in module; yt-dlp (library) runs ffmpeg/deno — cancellable via `_CancelledMarker` in hook (L450), `socket_timeout=30` (L349), children reaped when `with yt_dlp.YoutubeDL` closes (L488) |
| FROZEN-BUILD | Frozen-build path correctness | critical | PASS | new deno dep resolved by `_resolve_bundled_js_runtime` (L75-95) mirroring ffmpeg resolver (sys._MEIPASS→repo root), PATH-prepend at import (L98-105). deno binary + .spec entry are integration tasks per rule note — not a FAIL |
| RESOURCE-CLEANUP | Resources released all paths | warning | PASS | temp dir rmtree in `finally` (L564-567); `with` on YoutubeDL (L488) and ThreadPoolExecutor (L671) |
| NO-SECRETS-PATHS | No secrets / machine paths | critical | PASS | grep_diff: no credential literals, no `C:\Users\...`; proxy doc text is generic |
| TESTS-PRESENT | Behavior ships with tests | warning | PASS | each Cx mapped to a test (34 test fns); C3→test_cancel_mid_download_leaves_no_orphans, C6d→test_lost_future_filled_so_len_matches_urls, etc. |
| DETERMINISTIC-TESTS | Tests deterministic | warning | PASS | offline 28 pass with no network; online gated by `@pytest.mark.online`+`RUN_ONLINE_TESTS`; is_live/lost_future tests use monkeypatch/sys.modules injection |
| URLDL-C1-FORMAT | Quality-maximal mkv | critical | PASS | QUALITY_FORMATS L117-124 (no `[ext=]`, height caps kept e.g. `bv*[height<=1080]`); `merge_output_format:"mkv"` L344; readback trusts prepare_filename + `glob.escape(filename.stem)` fallback L529, no `.mp4` hardcode. **Re-checked after C3 fix:** prepare_filename still returns the full abs path under work_dir (probed) — youtube_short + subtitles_and_progress online tests PASSED, file located post-download |
| URLDL-C2-HOOK | Progress hook trivial (#5957) | critical | PASS | hook L443-465 = dict reads + one division (L458); logger only in the callback-failure branch (not hot path, documented L447); `subtitle_langs` threaded L578→L412→L320; test_subtitles_and_progress_reach_completion asserts video+.srt+pct 100 (L412) |
| URLDL-C3-CLEANUP | Partial-file cleanup | critical | **PASS (runtime-verified)** | (1) outtmpl RELATIVE `"%(title).100B-%(id)s.%(ext)s"` L334, NOT `str(work_dir/...)`; `paths={"home":work_dir,"temp":temp_dir}` L339. (2) rmtree in `finally` L564-567 AFTER the `with` (opens L488), not in hook. (3) **RUNTIME:** VERIFY re-ran `RUN_ONLINE_TESTS=1 ...test_cancel_mid_download_leaves_no_orphans` → **1 passed (3.09s)**; asserts error_type=='cancelled', `rglob` over work_dir = 0 `.part`/`.ytdl` (covers temp dir), `.ytdl_tmp_0` removed, pool drained. Fixed in 8a5fef6 |
| URLDL-C4-DENO | Bundled Deno / JS runtime | critical | PASS | `_resolve_bundled_js_runtime` L75-95 mirrors ffmpeg resolver; PATH-prepend at import L98-105; `logger` routing L362 (no `no_warnings`); `js_runtime_missing` branch L232-233. deno binary/.spec absent = integration task per rule |
| URLDL-C5-COOKIES | cookies_file replaces browser | critical | PASS | grep `cookies_browser`/`VALID_BROWSERS` = 0; `cookies_file:Optional[Path]` L581 validated exists+readable raises (L634-639); `opts["cookiefile"]` L396; `cookies_invalid` branch L234-242; consent docstring L597-602 |
| URLDL-C6A-LIMITS | Timeouts / cap / live guard | warning | PASS | `socket_timeout:30` L349; `max_concurrent>16` rejected L629 (keeps `>=1`+bool L626-628); `is_live` guard after extract_info L494-500 |
| URLDL-C6B-CONTRACT | One result per URL | critical | PASS | None-fill loop L705-715 (not a bare filter), returns `out`; test_lost_future_filled_so_len_matches_urls L280 |
| URLDL-C6C-ERRORCATS | Error categorization gaps | warning | PASS | ImportError→`dependency_missing` L213-214 + L440; members-only→auth_required L251-254; country-block→region_locked L262-263 |
| URLDL-C7-PIN | yt-dlp[default] pin | critical | PASS | requirements.txt:25 `yt-dlp[default]>=2026.03.17` (regex match) |
| URLDL-C8-PROXY | Optional proxy | warning | PASS | `proxy`→`opts["proxy"]` L401-402; scheme regex `^(https?\|socks5h?\|socks4)://` raises L644; `""`=direct; geo_bypass only in a comment (L399, deliberately NOT set); `proxy_error` branch L277-291; offline tests test_proxy_bad_scheme_raises L230 + test_categorize_socks_refused_is_proxy_error L250 |

## Score / grade / status
- **PASS 22, FAIL 0, WARN 0, SKIP 2.**
- `score_pct = 22 / (22 + 0 + 0*0.5) * 100 = 100%` → **Grade A**.
- No critical FAIL, no warning → **PASSED**. Not blocked; no BLOCKERS.json written; CLAUDE.md has no Agent Warnings line for this branch (nothing to clear).

## Environmental note (not counted)
- `test_tiktok_downloads_watermark_free` + the TikTok leg of `test_mixed_batch_returns_correct_per_url_outcomes` fail in this env — yt-dlp TikTok extractor "attempting impersonation, but no impersonate target available" (curl-cffi missing). Environmental, unrelated to C1–C8.

### Re-grade self-review
- C3 outtmpl confirmed RELATIVE + paths set, cited to real lines (334/339)?      YES
- C3 cancel test re-run BY ME this session with runtime evidence (not static)?    YES (1 passed, 3.09s)
- C1 output readback re-checked post-fix (prepare_filename + glob fallback)?       YES (probe + 2 online success tests)
- Both prior warnings (DURABLE-DOCS, QT-THREADSAFE) confirmed cleared at file:line? YES
- TikTok failures excluded as environmental, not charged to the branch?           YES
- No source/test/config edited by VERIFY (only RESULTS.md + verify.json)?          YES
