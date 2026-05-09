# CORRECTIONS.md — Cumulative Research Audit Findings

**Scope:** all factual claims made in Phase 2 research artifacts (Phase 2a shared-core plan, Phase 2d PyQt5→PySide6 migration plan, Phase 2c JSON preset migration plan) that were caught and corrected across six verification passes between 15–19 April 2026.

**Purpose:** single source of truth for what was wrong, what's now right, and what the correction traced back to. Lives in the repo as institutional memory — when anyone (future-you, a collaborator, an auditor) reads the research docs and wonders whether a claim was verified, this file answers.

**Methodology:** the original research was produced in a single pass, then audited four times for Phase 2a/2d and twice for Phase 2c. Each audit pass fetched primary sources directly (PyPI, GitHub, RFCs, official docs, IEEE papers) and compared the cited facts against what the sources actually said. Corrections below are each tied to the source that disproved the original claim.

**Total corrections across all passes:** 15 substantive + 2 version-drift updates.

---

## Corrections from Phase 2a/2d research (audit rounds 1–4, 15–17 April 2026)

### 1. PyQt5 5.15.11 release date

- **Original claim:** PyQt5 5.15.11 released July 2024
- **Correct fact:** PyQt5 5.15.11 released **14 October 2023**
- **Source:** PyPI https://pypi.org/project/PyQt5/ release history
- **Why it mattered:** version-cadence argument in the 2d migration plan cited this to argue PyQt5 was still receiving updates. The actual date is ~9 months earlier, which weakens (but does not eliminate) the cadence argument.

### 2. PySide6 current version

- **Original claim:** PySide6 6.10.x is current
- **Correct fact:** PySide6 **6.11.0** released **23 March 2026** is current as of this writing
- **Source:** PyPI https://pypi.org/project/PySide6/
- **Why it mattered:** 2d migration plan's pin recommendation needed the current version number.

### 3. Copilot-migration paper statistics

- **Original claim:** Copilot-assisted migration paper reported ~74% test pass rate on SQLAlchemy
- **Correct fact:** Paper reports **100% migration coverage median**, **39.75% test-pass rate on SQLAlchemy** (not 74%)
- **Source:** Almeida, Xavier, Valente — arXiv:2510.26699 "GitHub Copilot for Software Library Migrations"
- **Why it mattered:** 74% would have been a reason to consider automating the PyQt5→PySide6 migration. 39.75% is much weaker and supports the manual-migration conclusion the plan ended up with.

### 4. qutebrowser issue classification

- **Original claim:** qutebrowser PRs #5395, #7202, #7628 document PyQt5→PySide6 migration learnings
- **Correct fact:** #5395 and #7202 are **issues**, not PRs. #7628 is a **discussion**, not a PR.
- **Source:** GitHub github.com/qutebrowser/qutebrowser/{issues,discussions}
- **Why it mattered:** calling them "PRs" implied code-change evidence; they're actually "community reports and design threads." Same substantive content, different evidence weight.

### 5. Parallel Change attribution

- **Original claim:** Parallel Change pattern is Kent Beck's
- **Correct fact:** Parallel Change was **first documented by Joshua Kerievsky in 2006** at the Lean Software and Systems Conference in his "Limited Red Society" talk. **Danilo Sato wrote the canonical bliki article on 13 May 2014** at martinfowler.com/bliki/ParallelChange.html that codified the name.
- **Source:** https://martinfowler.com/bliki/ParallelChange.html (Sato article with Kerievsky acknowledgment)
- **Why it mattered:** Kent Beck is widely cited for XP refactoring patterns, but this one isn't his. Attribution matters for the shared-core extraction plan's citation integrity.

### 6. Branch by Abstraction attribution

- **Original claim:** Martin Fowler originated Branch by Abstraction
- **Correct fact:** **Stacy Curl coined the term**. **Paul Hammant first documented it** in April 2007 at paulhammant.com/blog/branch_by_abstraction.html. Fowler and Jez Humble later popularized it through the Continuous Delivery book.
- **Source:** Hammant's 2007 blog post; Fowler bliki entry at martinfowler.com/bliki/BranchByAbstraction.html credits Curl
- **Why it mattered:** same integrity issue as #5. The plan's citation section needed the right person credited.

### 7. QFontMetrics.width status

- **Original claim:** QFontMetrics.width was **removed** in Qt 6
- **Correct fact:** QFontMetrics.width is **deprecated**, not removed. Still callable, emits deprecation warning.
- **Source:** Qt 6 documentation https://doc.qt.io/qt-6/qfontmetrics.html
- **Why it mattered:** "removed" would require code changes in 2d; "deprecated" means existing code works but should be migrated to horizontalAdvance() at convenience. Different urgency.

### 8. GitHub Actions free-tier minutes

- **Original claim:** GitHub Actions free tier is 2000 minutes/month
- **Correct fact:** 2000 minutes/month is the **Linux runner allowance**. Windows runners count **2× against that quota**, so effective Windows-minutes is ~1000/month. macOS runners count 10×.
- **Source:** https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions
- **Why it mattered:** 1vmo Suite is Windows-only. A CI plan that assumed 2000 Windows-minutes would hit the cap roughly twice as fast as expected.

### 9. Nathaniel McCarthy "10:1 code ratio" citation

- **Original claim:** Nathaniel McCarthy's "10:1 code ratio" establishes test-to-production code proportionality
- **Correct fact:** **Cannot verify this citation.** No source found matching author name + claim. Removed from the research entirely.
- **Source:** Multiple search passes returned no primary source. Treated as a fabrication.
- **Why it mattered:** the claim was used to motivate characterization-test coverage levels. Removing it doesn't change the plan's conclusion, but the unsupported citation was a credibility risk.

### 10. HandBrake preset format structure

- **Original claim (Phase 2c v1):** HandBrake's preset.json format is an envelope with `VersionMajor/Minor/Micro` and `PresetList` array
- **Correct fact:** HandBrake has **two different structures** that were conflated:
  - `preset_template.json` (in the source repo at github.com/HandBrake/HandBrake/blob/master/preset/preset_template.json) is a **flat single-preset object** with `"Type": 1` on line 99 — no envelope
  - Exported/packaged preset files generated by `presets_package()` in `libhb/preset.c` wrap presets in the envelope
- **Source:** direct fetch of the template file via Fossies; libhb/preset.c source
- **Why it mattered:** the Phase 2c schema design initially assumed the envelope structure applied always. Correction revealed that for single-preset files (the 1vmo equivalent of each encoder entry), flat is the correct model.

### 11. Blender directory search order

- **Original claim:** Blender uses a universal LOCAL→USER→SYSTEM search order across all its config directories
- **Correct fact:** Search order **varies per subdirectory**:
  - `autosave/` and `config/` use LOCAL, USER
  - `datafiles/` and `scripts/` use LOCAL, USER, SYSTEM
  - Bundled Python uses LOCAL, SYSTEM
- **Source:** https://docs.blender.org/manual/en/latest/advanced/blender_directory_layout.html
- **Why it mattered:** Phase 2c referenced Blender as a portable-directory precedent. The per-subdirectory nuance strengthens the argument (different data types warrant different precedence rules).

---

## Corrections from Phase 2c research (audit rounds 5–6, 18–19 April 2026)

### 12. PyInstaller `--contents-directory .` introduction

- **Original claim:** PyInstaller's `--contents-directory .` opt-out (for the pre-`_internal/` onedir layout) was introduced in 6.19.0
- **Correct fact:** Both the new `_internal/` layout AND the `--contents-directory` flag (including its `.` value to opt back to the old layout) were introduced **simultaneously in 6.0.0** via issue #7968. 6.19.0 did not add this option.
- **Source:** PyInstaller 6.0.0 changelog https://pyinstaller.org/en/v6.0.0/CHANGES.html
- **Why it mattered:** the Phase 2c plan's `requirements.txt` recommendation of `pyinstaller>=6.19.0` is overly restrictive. **Corrected to `pyinstaller>=6.0.0`.**

### 13. `json.dumps(ensure_ascii=False)` return type

- **Original claim:** `json.dumps(..., ensure_ascii=False)` emits non-ASCII characters as literal UTF-8 **bytes**
- **Correct fact:** `json.dumps` always returns a **Python `str`**, never bytes. UTF-8 encoding happens only at `.encode()` or via `json.dump(..., fp)` where `fp` was opened with a UTF-8 encoder. Additionally, **even with `ensure_ascii=False`, the characters `"`, `\`, and U+0000–U+001F are still escaped** as JSON requires.
- **Source:** https://docs.python.org/3/library/json.html
- **Why it mattered:** Phase 2c preset writer must do BOTH `open(path, 'w', encoding='utf-8')` AND `json.dump(..., ensure_ascii=False)`. The flag alone does not produce UTF-8 output to disk.

### 14. pydantic version at implementation time

- **Original claim:** pydantic 2.12.5 is current as of Phase 2c plan writing
- **Correct fact (subject to drift):** pydantic **2.13.2** released **17 April 2026** is current as of this CORRECTIONS.md writing. Version drifted during the audit window: 2.12.5 → 2.13.0 (13 April) → 2.13.1 (15 April) → 2.13.2 (17 April). Note: drift is normal and expected between audit date and implementation date — this entry exists to document that the plan's version pin needs a fresh check before `requirements.txt` is edited.
- **Source:** https://pypi.org/project/pydantic/
- **Why it mattered:** `requirements.txt` pin should target the current version at implementation time, not the audit-time version.

### 15. pydantic-core repository status

- **Original claim:** pydantic-core is a separate actively-maintained package
- **Correct fact:** The **pydantic-core GitHub repository was archived on 11 April 2026** and is now read-only. Development consolidated into the main pydantic repository. **The PyPI package `pydantic_core` still publishes** separately (latest 2.46.1, 15 April 2026) — the repo archival is about development location, not distribution.
- **Source:** https://github.com/pydantic/pydantic-core (archive banner); https://pypi.org/project/pydantic_core/ (latest release)
- **Why it mattered:** do not pin `pydantic-core` as a separate dependency in new `requirements.txt` — let it come along transitively from `pydantic`. Any reference to the pydantic-core repo URL in docs should point to the folded-in path inside the main pydantic repo.

### 16. Notepad++ Program Files fallback documentation status

- **Original claim:** Notepad++ officially documents that `doLocalConf.xml` portable mode fails under `C:\Program Files\` due to UAC write restrictions
- **Correct fact:** The `doLocalConf.xml` sentinel mechanism IS officially documented at https://npp-user-manual.org/docs/config-files/ and Debug Info does show "Local Conf mode: ON" in portable mode. **However, the Program Files / UAC fallback is observed behavior from community reports (issues #1582 and #5759), not in the current official config-files page.**
- **Source:** npp-user-manual.org; github.com/notepad-plus-plus/notepad-plus-plus/issues/{1582,5759}
- **Why it mattered:** the 1vmo `verify_portable_location()` guard (Phase 2c plan) cites Notepad++ as precedent for refusing Program Files installs. The precedent stands, but the claim should be phrased "community-observed, multiple user reports" rather than "officially documented" to maintain citation integrity.

### 17. HandBrake vs Phase 2c claim conflation

- **Original claim (Phase 2c v1):** Use HandBrake's envelope-wrapping approach for 1vmo single-preset files
- **Correct fact:** Phase 2c was conflating HandBrake's **two** formats. For 1vmo's use case (one encoder entry per record), the flat single-preset structure (without envelope) is the correct analogue. The envelope is only needed for **import/export** operations that wrap multiple presets.
- **Source:** see correction #10
- **Why it mattered:** the Phase 2c final schema design uses the flat structure for storage and only wraps in an envelope for export, which is closer to how HandBrake actually works.

---

## Summary of impact on current plans

| Correction | Plan affected | Change required |
|---|---|---|
| #1, #2 | Phase 2d | Update version references to current: PyQt5 5.15.11 (Oct 2023), PySide6 6.11.0 (Mar 2026) |
| #3 | Phase 2d | Soften claims about Copilot-assisted migration viability; 39.75% pass rate supports manual approach |
| #4 | Phase 2d | Reclassify qutebrowser #5395/#7202/#7628 as "issue" and "discussion" rather than PR |
| #5, #6 | Phase 2a | Correct Parallel Change and Branch by Abstraction attributions in citations section |
| #7 | Phase 2d | Change "removed" to "deprecated" for QFontMetrics.width — fix-at-convenience, not blocker |
| #8 | Future CI plan | Windows-aware budget: effective ~1000 min/month not 2000 |
| #9 | Phase 2a | Remove the Nathaniel McCarthy citation entirely |
| #10, #17 | Phase 2c | Schema designed for flat single-preset storage; envelope only in export |
| #11 | Phase 2c | Blender precedent argument strengthened, not weakened |
| #12 | Phase 2c | `requirements.txt`: `pyinstaller>=6.0.0` (not 6.19.0) |
| #13 | Phase 2c | Preset writer uses BOTH `encoding='utf-8'` and `ensure_ascii=False` |
| #14 | Phase 2c | Re-check pydantic latest version immediately before pinning in `requirements.txt` |
| #15 | Phase 2c | Do not pin `pydantic-core` separately; let it come transitively |
| #16 | Phase 2c | Notepad++ Program Files fallback cited as "community-observed" not "officially documented" |

---

## Audit-chain provenance

- **15 April 2026:** Phase 2a research produced + audit rounds 1–2 caught corrections #1, #2, #3, #4
- **16 April 2026:** Phase 2d research produced + audit rounds 3–4 caught corrections #5, #6, #7, #8, #9
- **17 April 2026:** Phase 2c research produced + audit round 5 (self-audit) caught corrections #10, #11, preliminary versions of #16 and #17
- **18 April 2026:** Phase 2c verification pass (13 targeted claims) caught corrections #12, #13 and refined #16
- **18 April 2026:** Re-verification of remaining 10 claims confirmed all held; noted drift findings #14, #15
- **19 April 2026:** Phase 2a Step 1 plan pressure-test surfaced no new factual corrections (the issues found there were methodology gaps: wrong API names in test stubs, constructor-captivity not accounted for) — those are fixed in the v2 plan directly, not cataloged here since they never shipped as claims

---

## How to read this file going forward

- If you're executing a plan and something cited in the research looks off, check here first.
- If a new correction surfaces during execution, add it to this file with the same structure: original claim, correct fact, source, why it mattered.
- Version drift entries (#14, #15) will go stale. When pinning versions for implementation, always re-verify against PyPI at that moment — this file does not replace that check.
- Phase 2b (updater) research has not happened yet; when it does, any corrections from that work go here too.
