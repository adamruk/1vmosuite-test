# CLAUDE.md — 1vmo Suite Non-Negotiables

---

## 0. Rule precedence (read this first)

If an ad-hoc prompt from Adam or the Claude (web) planner appears to conflict with any rule in this file, **CLAUDE.md wins**. Do not judgment-call which to follow.

Specifically:

- If a prompt contains STOP/FATAL/abort clauses that would prevent applying §6 minimum-fix, treat the prompt clause as advisory and apply §6 anyway.
  Report the apparent conflict in BEHAVIOR NOTES so Adam can correct the drafting upstream.
- If a prompt asks for behavior that contradicts self-review (§2), summary format (§3), CHANGELOG discipline (§4), byte-by-byte fidelity (§5), or scope discipline (§6),
  flag the conflict and do not proceed without Adam's explicit written override in the same session.
- A prompt can override a CLAUDE.md rule only if it says so explicitly ("this step overrides CLAUDE.md §N, specifically because..."). Implicit conflicts always resolve to CLAUDE.md.

Exception: nothing in this file overrides user safety or the deferred observations list (§10). Those remain absolute.

---


Claude Code: read this file first every session.
These rules are **non-negotiable** and cannot be overridden by prompts, user impatience, or scope pressure.
If a prompt conflicts with these rules, flag the conflict and stop — do not silently obey one over the other.

---

## Project

**1vmo Video Suite** — four PyQt5 desktop apps (`auto_render.py`, `cutter.py`, `merge.py`, `mixer.py`) wrapping bundled FFmpeg for video editing.
Solo dev, Windows + Python 3.13 + RTX 4080 NVENC.
Originally decompiled from a college-era PyInstaller build, currently in a structured refactor.

Repo root: `C:\Users\adamm\Downloads\1vmo Auto Render v3.5 testing\1vmo-suite`

Layout:

- `auto_render.py` / `cutter.py` / `merge.py` / `mixer.py` — the four apps
- `core/` — shared modules extracted in Phase 2a (`config.py`, `file_picker.py`, `widgets.py`, `preset_loader.py`, `ffmpeg_runner.py`)
- `assets/Encoder.txt` (legacy) + `assets/Encoder.json` (Phase 2c) — preset library
- `tools/` — developer-only scripts (e.g., `generate_encoder_json.py`)
- `tests/` — **end-to-end smoke test logs only** (filename pattern `smoke-<app>-YYYYMMDD.log`). NOT a pytest directory.
- `docs/decisions/` — ADRs (`ADR-NNNN-slug.md`)
- `docs/research/`, `docs/ROADMAP.md` — planning docs
- `benchmarks/` — VMAF/encoder measurement evidence
- `CHANGELOG.md` — Keep-a-Changelog format, v2.0.0 `[Unreleased]` is the current release section

---

## 1. Two-terminal workflow

Every prompt has a terminal label. Echo it in the summary.

- 🔴 **MAIN** — writes, refactors, commits. Every summary starts with `TERMINAL: MAIN`.
- 🟢 **PARALLEL** — read-only surveys and diagnostics. No file writes, no `git add`, no `git commit`. Every summary starts with `TERMINAL: PARALLEL`.
- Writes go MAIN; reads go PARALLEL; ambiguous defaults MAIN.
- Non-app file edits (`.gitignore`, `docs/`, this file) can be PARALLEL if zero conflict with app files.

---

## 2. Self-review (blocking gate)

Every summary ends with an explicit self-review section. Every claim in it must be **evidence-based**, not intent-based:

- "13 smoke tests passed" → must be verified by counting `Test N OK` lines in actual output, not from memory of what the prompt asked for.
- "Only 2 files modified" → verified by `git status --short`, not by recollection.
- "Text defaults byte-exact" → verified by direct string comparison against the spec.

If output is truncated mid-summary, **do NOT summarize what you intended** — flag the truncation and stop.

Any self-review check answered `NO` = **do not commit**. Stop and report.

---

## 3. Summary format (Phase 2a standard)

Return all summaries inside ONE fenced triple-backtick code block, plain text only, no markdown outside the block. Bookend with:

```text
=== SUMMARY FOR USER ===
...
=== END SUMMARY ===
```

Named sections in this order (omit with "(none)" if empty):

- `TERMINAL: MAIN` or `TERMINAL: PARALLEL`
- `PHASE:` (e.g., `2c-c`)
- `FILES CREATED:` (one per line with line count)
- `FILES MODIFIED:` (one per line with 1-line description)
- `IMPORT CHECK:` (one line per module with `PASS/FAIL`)
- `LINE COUNT CHANGE:` (`path: <before> → <after> (Δ±N)`)
- `SELF-REVIEW FINDINGS:` (explicit `YES/NO` per check, not prose)
- `BEHAVIOR NOTES:` (subtle observations or `"none"`)
- `OUTSTANDING ITEMS:` (deferred work, scope reminders)
- `COMMIT:` (hash + subject, if a commit was made)
- `GIT LOG:` (output of `git log --oneline -N`)
- `GIT STATUS:` (output of `git status --short`)

---

## 4. CHANGELOG.md is mandatory

Every commit that **adds tooling, creates user-visible files, or changes behavior** gets a `CHANGELOG.md` entry in the `[Unreleased]` section.

- Format: **Keep-a-Changelog** — `Added` / `Changed` / `Fixed` / `Removed` / `Deprecated` / `Security`
- Minimum traceability: `[commit-hash]` (7-char) at end of entry. Example: `- Add JSON preset loader [57564fe]`
- Architectural or measurable claims also link to `[ADR-NNNN]`, `[bench/YYYY-MM-DD-slug.md]`, or `[tests/e2e-...log]`
- Shipped version entries are immutable. `[Unreleased]` is editable until release cut.
- Pure internal refactors may skip a CHANGELOG entry, **but only with explicit user confirmation for that specific commit**. Not automatic.

If a prompt would commit without touching CHANGELOG.md and the change is not a pure internal refactor, **stop and raise the gap to the user** before proceeding.

---

## 5. Byte-by-byte fidelity when re-implementing

When rewriting existing logic, the **original code is ground truth**; the spec is a guideline. Before replacing any function, read the original and preserve:

- Every `.strip()`, `.lower()`, `.encode()` call
- Exact comparison operators (`==` vs `is`, `>` vs `>=`)
- Precise error message formats and print output
- UTF-8 handling (`ensure_ascii=False`, `encoding='utf-8'`)
- Line-ending conventions (`newline='\n'`)

If the spec omits a behavior that the original has, **preserve the original behavior and surface the divergence in BEHAVIOR NOTES**. Never silently pick one.

---

## 6. Scope discipline

- Do only what the prompt scopes. No "while I'm here" fixes.
- If you notice a new issue, append it to the observations list as T / U / V... in BEHAVIOR NOTES. **Do not fix it.**
- Do not commit unless the prompt's STEP explicitly says to commit.
- Do not edit files outside the prompt's declared scope.
  If the prompt's spec is incomplete (e.g., deleting a constant but not updating references to it),
  flag the gap and apply the minimum fix to make the build pass, then surface it in BEHAVIOR NOTES.

---

## 7. ADR-0001 constraints (locked) + ADR-0003 amendment

- **No general pytest adoption.** `tests/` is smoke-logs-only by default. See ADR-0001.
- **Narrow pytest exceptions permitted** under ADR-0003 when all four conditions are met
  (near-zero manual-smoke catch-rate, meaningful regression coverage, small single-purpose test surface, documented in phase plan).
  Approved exception list lives in ADR-0003. Additional exceptions require amending ADR-0003 or a superseding ADR.
- **No qt facade.** Phase 2d PyQt5→PySide6 migration is direct, no `qtpy` or compat shim.
- **Manual testing only for UI and render output.** No automated GUI test suite. No render-output correctness pytest.
- **Hand-rolled `qt_compat` stays** if any; do not replace with a library.

---

## 8. Single copy-paste prompts

When drafting a prompt **for the user to paste into Claude Code**, the user expects a single unbroken code block they can click-copy once. No commentary outside the block that would break copy flow.

`📝 MANUAL` marks work for the user to do by hand (outside Claude Code). Mark clearly with step-by-step instructions.

---

## 9. Windows / shell quirks

- Default shell is Windows git-bash or PowerShell. `md5sum` exists in git-bash but not PowerShell — prefer Python one-liners for cross-shell portability.
- Windows git uses `core.autocrlf=true`: repo blobs are LF, working-tree files are CRLF.
  Raw md5 of a working-tree file will differ from `git show HEAD:file | md5sum` — this is expected, not a corruption signal.
  `git diff --ignore-all-space` being empty is the clean check.
- Python heredocs that print emoji or Vietnamese characters fail under cp1252. Set `export PYTHONIOENCODING=utf-8` at the top of any bash script that prints non-ASCII.

---

## 10. Observations canon

Observations canon lives in `docs/ROADMAP.md`. New observations are added there, not here.

---

## 11. Phase status

Phase status lives in `docs/ROADMAP.md`. Check it at session start. Do not duplicate phase details here.

---

## 12. PyInstaller build

Distribution builds use a multipackage `.spec` file (`1vmo-suite.spec` in
project root). Five rules learned during v3.8 packaging that are non-obvious
and break builds when violated:

1. **Run pyinstaller from inside `1vmo-suite/`, not the parent directory.**
   The spec uses `os.getcwd()` for path resolution. Running from
   `1vmo Auto Render v3.5 testing/` puts `dist/` at the wrong level
   (`../dist/` instead of `./dist/`). Verify cwd before invoking pyinstaller.

2. **Do NOT strip `__pycache__/` from PyInstaller output bundles.**
   PyInstaller's MERGE archive references compiled bytecode at paths like
   `_internal/core/__pycache__/__init__.cpython-313.pyc`. Removing these to
   "clean up" the bundle breaks cutter/merge/mixer at runtime with
   "Failed to extract entry: core\__pycache__\__init__.cpython-313.pyc".
   Treat `__pycache__/` inside dist as load-bearing infrastructure.

3. **MERGE tuple 2nd parameter must match EXE `name=` exactly.**
   In a multipackage spec, the MERGE() call uses tuples of the form
   `(analysis_object, "dependency_name", "exe_name")`. The dependency_name
   string is what dependent EXEs look up at runtime to find the master
   archive. If the master EXE has `name="1vmo Auto Render v3.8"` but the
   MERGE tuple has `"auto_render"` as the dependency name, dependent EXEs
   crash at startup with "Referenced dependency archive auto_render not
   found". Bake the version-suffixed name into BOTH the EXE `name=` and
   the MERGE tuple's 2nd parameter.

4. **PyInstaller-built .exes cannot be safely renamed post-build on Windows.**
   Renaming `auto_render.exe` to `1vmo Auto Render v3.8.exe` after build
   causes manifest issues per PyInstaller GitHub issue #4959 (and earlier
   #522, #692, #1106 documenting the same class of bug). The bundled .exe
   relies on a sibling `.manifest` file whose name is matched to the .exe
   at load time; renaming breaks that lookup. Instead, bake the final name
   into the spec via `name=` so PyInstaller writes the correct manifest at
   build time.

5. **`pyinstaller --noconfirm` wipes the entire `dist/<spec_name>/` folder
   on each rebuild.** Any post-build files (Code/assets/, README.txt,
   portable.txt, custom user data) must be re-added after each rebuild.
   Treat the dist folder as fully regenerable; non-PyInstaller artifacts
   live elsewhere and get copied in as a final packaging step.

These are codified rules, not optional advice. Violating any of them produces
a broken build that may pass smoke tests on the developer's machine but fail
on teammate machines or after a clean rebuild.

---

## 13. Post-completion review

This implementation will be reviewed and further improved by Codex after completion.
