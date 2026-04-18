# ADR-0001 — Phase 2 Methodology Reconciliation

**Status:** Accepted

**Date:** 2026-04-19

**Context:** Phase 2 roadmap exists (`docs/PHASE_2_ROADMAP.md`). External planning session produced a heavier alternative plan. This ADR records the decision to keep the existing roadmap as authoritative and explains why.

## Context

During a planning session on 2026-04-18 to 2026-04-19, a separate Phase 2 execution plan was developed through conversations with Claude (Anthropic). This plan covered the same three sub-phases as the existing roadmap (2a shared core extraction, 2c JSON preset migration, 2d PyQt5→PySide6) but prescribed significantly heavier methodology:

- **2a:** pytest-based characterization test suite covering 11 code seams across all 4 apps (19–23 hours estimated), followed by `core/` extractions using Branch by Abstraction + Mikado Method + Parallel Change + Sprout Method (35–55 hours estimated). Total: 54–78 hours before any feature work.
- **2c:** dependent on 2a Step 2 completion; JSON preset migration plan at ~33 hours.
- **2d:** direct PyQt5→PySide6 migration, ~30–50 hours.

The external plan was pressure-tested three times through research passes against comparable projects (Anki, Calibre, Picard, HandBrake, OBS, Sigil, Hex-Rays IDA, UCSF ChimeraX, BackInTime, and others). The third pass, focused on strategic calibration for solo-developer scale, concluded that the heavier methodology was miscalibrated for a ~5000 LOC solo-authored codebase.

## Decision

**Keep `docs/PHASE_2_ROADMAP.md` (Phase 1 self's plan) as the authoritative Phase 2 execution plan.** The external plan becomes supplementary reference.

Specific implications:

1. **2a scope follows the existing roadmap**, not the external plan. Module names are `core/ffmpeg_runner.py`, `core/file_picker.py`, `core/config.py`, `core/widgets.py`, `core/preset_loader.py` (per roadmap) — not the external plan's `core/paths.py`, `core/ffmpeg.py`, `core/encoders.py`, etc.
2. **pytest is NOT adopted in Phase 2.** Per the existing roadmap's explicit out-of-scope clause: *"Test framework adoption (pytest, etc.) — currently `tests/` holds smoke logs only; switching to a real test framework is its own decision."* A separate ADR would be required to adopt pytest.
3. **`tests/` folder retains its existing convention:** e2e smoke test logs only, named `smoke-<app>-YYYYMMDD.log`. Not a pytest directory.
4. **The existing roadmap's pre-work requirement (e2e smoke tests before 2a) is waived for this execution.** See "Consequences → accepted risk" below.
5. **2a estimated effort follows the existing roadmap's 3–5 working days**, not the external plan's 54–78 hours.

## Rationale

Three rounds of strategic research on comparable small Python desktop apps (see `docs/research/RESEARCH_SUMMARY.md`) produced three convergent findings:

**Finding 1 (qtpy vs hand-rolled facade):** UCSF ChimeraX — the closest comparable-scale precedent — surveyed qtpy, rejected it, and built a ~100-line homegrown shim that survived a successful PyQt5→PyQt6 migration over 5 years. The "2024–2026 industry consensus to adopt qtpy" claim weakened substantially under inspection. Hand-rolled approaches are defensible at this scale.

**Finding 2 (preemptive `core/qt.py` Qt-binding facade):** Research reversed an earlier recommendation to build such a facade. PyInstaller 6.5+ explicitly aborts builds with multiple Qt bindings (breaking try/except facade patterns). BackInTime (comparable scale) did direct PyQt5→PyQt6 migration with no facade and shipped without incident. Armin Ronacher 2025 writings, Fowler YAGNI, and Kent Beck's *Tidy First?* all argue against preemptive abstractions. A facade before Phase 2a would couple the 4 apps' Qt-version choices, directly contradicting the staggered-release goal.

**Finding 3 (methodological rigor):** The external plan's stack (Mikado + Branch by Abstraction + Parallel Change + Sprout Method + characterization tests across 11 seams) was calibrated for team-scale legacy systems, not for 5000 LOC solo code the author wrote personally. Kent Beck's *Tidy First?* (2024) explicitly treats "never tidy" as a valid option at solo scale. Naram Alkoht's "Ship Your Ugly Code" (April 2026) documented a concrete solo-dev failure mode: set up heavy methodology, abandoned in 4 days, shipped in 2 months on three simple rules. None of Calibre, Anki, Mu, or Sigil's public writing documents the Mikado+BBA+Parallel Change+Sprout stack.

The consistent cross-cutting pattern: the external plan had cargo-culted large-project patterns (Calibre's 500k LOC `qt.core`, Feathers' *Working Effectively with Legacy Code* techniques) to 5000 LOC solo without scale adjustment. The corrected direction — "smaller, reactive, only what the code currently demands" — is closer to the existing roadmap than to the external plan.

**Critical insight:** the existing roadmap (written by Phase 1 self) independently arrived at a scope and methodology that matches what three rounds of pressure-testing research concluded was correct. 3–5 working days, smoke logs for pre-work, explicit out-of-scope for pytest, clean module names. The external planning exercise added value in research rigor (see CORRECTIONS.md for 17 factual fixes) but did not add value in execution prescription.

## Consequences

**Positive:**

- Single authoritative plan in the repo (`docs/PHASE_2_ROADMAP.md`), no parallel-universe confusion
- Respects existing conventions (ADR folder, smoke log `tests/`, CHANGELOG rules)
- Saves 20–30 hours of pre-execution work vs the external heavy plan
- Preserves research and audit value (three files in `docs/research/`) without prescribing conflicting execution
- ADR convention followed: cross-cutting methodology decision is documented as future-readable rationale

**Negative:**

- Loss of some detailed prose that was in the external plan-style docs (specific techniques for atomic writes, UTF-8 edge cases, HandBrake envelope format details). Mitigation: the knowledge gets implemented into code during execution, where it's more useful than in supplementary docs.
- If Option A proves wrong at execution time, reverting means regenerating the external plan docs. Mitigation: the four deleted plan docs are kept in local personal storage outside the repo.

**Accepted risks:**

1. **Skipping e2e smoke tests before 2a.** The existing roadmap says: *"ensure all four apps have working e2e smoke tests committed to tests/ first. Without baseline tests, regressions during refactor are invisible."* This is deliberately waived. The author has high familiarity with the codebase (authored it personally, decompiled + reconstructed), will do manual testing during 2a execution, and judges the formal smoke-log overhead unnecessary at this scale. **Signal to reverse this decision:** if the first 2a extraction (`core/ffmpeg_runner.py` or equivalent) produces any regression that manual testing doesn't catch immediately, pause and implement smoke tests before continuing.

2. **No silent-AI-regression protection layer.** Without pytest-based snapshots, silent regressions introduced by Claude Code during 2a/2c/2d execution must be caught by manual testing. **Signal to reverse:** if Claude Code is used heavily and any silent regression ships, the next phase should write an ADR to adopt pytest and add boundary snapshots.

3. **Reactive-core-emergence pattern not adopted.** The existing roadmap has Phase 2a creating all 5 `core/` modules up front. The external plan's "reactive emergence during 2c" approach is not used. This is simpler for the execution plan but means `core/preset_loader.py` exists before 2c touches it (consistent with existing roadmap's ordering).

## Alternatives considered

**B. Write ADR to adopt pytest, keep external Option 3 plan (4 boundary snapshots).** Rejected because it would override Phase 1 self's explicit decision to treat pytest as its own separate-ADR-worthy question. If pytest is to be adopted, that decision deserves its own thought process rather than bundled with Phase 2 execution.

**C. Hybrid — smoke logs for 2a pre-work now, pytest decision deferred.** Rejected in favor of Option A because the smoke-tests pre-work itself was waived (see accepted risk #1). A pure Option C without the smoke tests collapses into Option A.

## References

- Existing roadmap: `docs/PHASE_2_ROADMAP.md`
- Research summary: `docs/research/RESEARCH_SUMMARY.md`
- Cumulative corrections: `docs/research/CORRECTIONS.md`
- Session decision log: `docs/research/SESSION_LOG.md`
- UCSF ChimeraX Trac #4120 (hand-rolled shim precedent)
- Kent Beck, *Tidy First?* (2024) — solo-scale refactoring methodology
- Naram Alkoht, "Ship Your Ugly Code" (April 2026) — solo-dev methodology-abandonment case
- BackInTime v1.5.0 (July 2024) — comparable-scale direct Qt migration precedent
- Armin Ronacher, "Build It Yourself" (January 2025) and "Agent Design Is Still Hard" (November 2025)
