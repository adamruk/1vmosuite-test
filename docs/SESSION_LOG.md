# Session Log — 1vmo Suite Phase 2 Planning Session

**Session window:** 18–19 April 2026
**Status at start:** Phase 1 complete and shipped. Phase 2 research done (Phase 2a, 2c, 2d). Four audit rounds completed producing CORRECTIONS list. Pre-session summary of prior work available in the conversation transcript.
**Status at end:** Active execution plan is Option 3. Eight documents preserved in `docs/planning/`. Ready to execute Phase 2a Part 1 infrastructure at next laptop session.

## Why this log exists

The session covered several meaningful decision reversals. Without a trace, future-me reading the README will see "Option 3" without understanding what was rejected or why. This log captures the chain of reasoning so the decision is re-justifiable or reversible later with full context.

## The decision chain

### Starting state

Coming into the session, the plan was the "heavy" version:
- Phase 2a Step 1: 19–23 hours of characterization testing across 11 seams, using Mikado + Branch by Abstraction + Parallel Change + Sprout Method
- Phase 2a Step 2: 35–55 hours of shared-core extraction with tiered Mikado graph
- Phase 2c: JSON preset migration, 28–33 hours, depending on 2a Step 2 minimum
- Phase 2d: direct PyQt5→PySide6 migration, 30–50 hours
- Phase 2b: deferred

**Total estimated effort before shipping: 85–118 hours.**

### Step 1: regenerate Phase 2a plan with pressure-test fixes

User asked for the Phase 2a plan to be regenerated with 8 specific fixes from an earlier pressure-test. Produced `phase-2a-plan-v2.md` with all 8 fixes folded in:

1. Dropped `__main__` guards prep step (already present in all 4 apps)
2. Added Part 1.6 sprout refactors as mandatory step
3. Corrected `gpu_detect` API from `detect_gpu()` to `detect(ffmpeg_path)`
4. Corrected updater API from module function to sprouted `_compare_version_strings`
5. Narrowed version-compare tests to numeric-only + ValueError regression guard
6. Added `redirect_module_paths` fixture for module-level path constants
7. Downgraded Target 2 from "discovers Gap D" to "regression lock" (Gap D already confirmed by code inspection)
8. Revised estimate from 14–17 to 19–23 hours

**No reversal at this stage — just refinement.**

### Step 2: write remaining planning docs

User wanted the handoff complete before running execution. Wrote:
- `phase-2a-step-2-plan.md` — Mikado graph + detailed playbook for first 3 extractions
- `phase-2c-execution-plan.md` — preset migration assuming 2a Step 2 done
- `CORRECTIONS.md` — 17 cumulative audit findings
- `README.md` — initial terse handoff (heavy plan version)

### Step 3: user requested research pass to pressure-test the plan

Scope: small-scale Python desktop projects, focus on 2a/2c/2d, full spectrum (confirmation + alternatives + anti-patterns), skip GitHub sources.

Research Pass 1 covered 16 comparable projects. Produced three findings:
- **A.** qtpy rejection may be wrong; 2024–2026 consensus uses qtpy as transitional
- **B.** Build `core/qt.py` facade before Phase 2a (Calibre/Anki/Sigil/Hex-Rays precedent)
- **C.** Methodological rigor may be overkill at 5000 LOC solo

**First adjustment made:** Finding B was treated as a clear recommendation — `core/qt.py` facade added to plan conceptually. Findings A and C flagged but not acted on.

### Step 4: user requested deeper pass, include failure cases

User explicitly asked for (1) all three findings expanded, (2) strategic depth, (3) include projects that failed or abandoned.

Research Pass 2 reversed or modified all three Pass 1 conclusions:

- **Area A → wash.** UCSF ChimeraX Trac #4120 found: surveyed qtpy, rejected it, built ~100-line homegrown shim, kept it 5 years through successful Qt6 migration. qtpy can itself become a migration-blocker (ChimeraX's qtconsole broke because qtpy's Qt6 support lagged). User's hand-rolled approach is defensible.

- **Area B → reversed outright.** PyInstaller 6.5+ explicitly aborts builds with multiple Qt bindings — facades using try/except fail at bundle time. Calibre/Sigil/Hex-Rays facades serve needs 1vmo doesn't have. BackInTime did direct migration at comparable scale and shipped fine. Armin Ronacher 2025 writings and Fowler YAGNI explicitly argue against preemptive abstraction. Facade couples the 4 apps' Qt-version choices, which directly contradicts staggered-release goal.

- **Area C → strengthened.** Kent Beck *Tidy First?* (2024) explicitly sized for solo scale with "never tidy" as valid option. Fowler: "Refactoring isn't a special task that would show up in a project plan." Alkoht "Ship Your Ugly Code" (April 2026) documented solo-dev failure mode: set up heavy methodology, abandoned in 4 days. None of Calibre/Anki/Mu/Sigil public writing documents the Mikado+BBA+Parallel Change+Sprout stack. Empirical snapshot-testing study (Nijmegen, 1,487 JEST projects) showed maintenance burden scales linearly with seam count; 11 seams = 11× the drag of 3.

**Meta-finding:** Pass 1 had cargo-culted large-project patterns to 5000 LOC solo in all three areas. The corrected direction is "smaller, reactive, only what the code currently demands."

### Step 5: reconciling research against the plans

User asked to match research findings against the actual plans. Produced mapping:

| Area | Research says | Plan has | Match |
|---|---|---|---|
| A | Hand-rolled OK | We rejected qtpy | ✓ Aligned |
| B | No `core/qt.py` | Never added to plan | ✓ Aligned |
| C | 3–4 boundary snapshots, no methodology stack | 11 seams + Mikado/BBA/Parallel Change/Sprout | ✗ Diverge hard |

Area C was the divergence that needed resolution.

### Step 6: the Option 3 decision

Presented three options:

- **Option 1:** rewrite plans to lighter version
- **Option 2:** execute current heavy plan as-written (bets against documented failure mode)
- **Option 3:** hybrid — keep heavy plans as reference, execute lighter subset

User chose Option 3. Rationale: keeps institutional memory of the detailed work, executes what the evidence supports, preserves ability to reach deeper into the reference plans if a specific problem needs the detailed technique.

### Step 7: README updated to reflect Option 3

Rewrote `README.md` to make Option 3 the active plan. Key changes:

- Framed heavy plans as reference material, not execution script
- Specified the 4-boundary-snapshot subset (not 11 seams)
- Reclassified Phase 2a Step 2 from "planned" to "reactive"
- `core/` emerges during Phase 2c when actually needed, not preemptively
- Phase 2d: direct migration, no facade
- New effort budget: 64–91 hours (saves 20–30 hours vs original)
- Added "Why Option 3" section with primary references

### Step 8: session closeout — preserve everything

User asked to save everything from the session. Produced this log plus `RESEARCH_SUMMARY.md` (consolidated findings from both research passes). Verified all 7 files before handoff.

### Step 9: user uploaded the Phase 1 end state zip

Before starting execution, user uploaded the actual repo. This was the first time during this session the planning docs were compared against the real repo state. Three significant mismatches surfaced immediately:

1. **`tests/` folder has a different purpose than assumed.** The existing `tests/README.md` defines `tests/` as e2e smoke test logs, not pytest files. Quote: *"Unit test source code — that lives alongside the module being tested (conventional pytest layout)."* The entire Option 3 plan to put pytest files in `tests/` would have violated an existing convention.

2. **`docs/PHASE_2_ROADMAP.md` already exists with different 2a scope.** Phase 1 self had already written a roadmap:
   - Module names: `core/ffmpeg_runner.py`, `core/file_picker.py`, `core/config.py`, `core/widgets.py`, `core/preset_loader.py` (NOT our `core/paths.py`, `core/versioning.py`, `core/ffmpeg.py`, `core/encoders.py`, `core/config.py`, `core/presets.py`)
   - Estimate: 3–5 working days (NOT our 54–78 hours)
   - Pre-work: "ensure all four apps have working e2e smoke tests committed to `tests/` first"

3. **The existing roadmap explicitly out-of-scopes pytest for Phase 2.** Quote: *"Test framework adoption (pytest, etc.) — currently `tests/` holds smoke logs only; switching to a real test framework is its own decision."* Adopting pytest would have required its own ADR, which we skipped.

Critical realization: Phase 1 self's existing roadmap (3–5 days, smoke logs, explicit pytest out-of-scope) was already closer to what three rounds of pressure-testing concluded was correct than our Option 3 was. Our planning had been done in isolation from the repo's actual conventions.

### Step 10: Option A pivot

Presented four reconciliation options. User chose Option A: adopt existing roadmap, smoke logs not pytest, our plans become reference.

Then the follow-up decisions:

- **Preservation:** Option 3 variant — commit 3 research/audit files to `docs/research/`, keep the 4 deleted plan docs in local personal storage outside the repo
- **Next step:** start directly with 2a core/ extraction, deliberately skipping the smoke tests the existing roadmap recommended
- **ADR:** yes, write ADR-0001 for the reconciliation

### Step 11: ADR-0001 written

Produced `ADR-0001-phase-2-methodology-reconciliation.md` following the existing `docs/decisions/README.md` convention. Documents:
- The decision (keep existing roadmap as authoritative)
- Rationale (three research findings, cargo-cult critique, scale miscalibration)
- Consequences including three accepted risks (skipping smoke tests, no silent-AI-regression protection, non-reactive core emergence)
- Signals for reversing each accepted risk
- Alternatives considered and why rejected

## Final file set

### Committed to repo (`docs/research/`)

| File | Role |
|---|---|
| `CORRECTIONS.md` | 17 cumulative factual corrections across the research chain |
| `RESEARCH_SUMMARY.md` | Consolidated findings from both research passes |
| `SESSION_LOG.md` | This file — decision-chain trace |

### Committed to repo (`docs/decisions/`)

| File | Role |
|---|---|
| `ADR-0001-phase-2-methodology-reconciliation.md` | Architectural Decision Record for the Option A reconciliation |

### Kept in personal local storage, NOT committed

| File | Why kept |
|---|---|
| `README.md` (our Option 3 version) | Historical reference in case Option A needs reversing |
| `phase-2a-plan-v2.md` | Detailed Sprout Method / characterization test prose |
| `phase-2a-step-2-plan.md` | Detailed Mikado + extraction playbook |
| `phase-2c-execution-plan.md` | Detailed preset schema / atomic write / HandBrake reference |

### Authoritative Phase 2 plan (already in repo, untouched)

| File | Role |
|---|---|
| `docs/PHASE_2_ROADMAP.md` | The active Phase 2 execution plan, written by Phase 1 self |

## What the next session does

Direct Phase 2a extraction per `docs/PHASE_2_ROADMAP.md`. No pre-work smoke tests (deliberately waived in ADR-0001, signal for reversal documented).

Scope per the existing roadmap:
- Create `core/` directory with `__init__.py`
- Extract `core/ffmpeg_runner.py` first (subprocess wrapper, progress parsing, cancellation)
- Extract `core/file_picker.py`, `core/config.py`, `core/widgets.py`, `core/preset_loader.py` as 2a continues
- All 4 apps refactored to use `core/`
- Target 30% line-count reduction per app per roadmap
- Manual testing during execution (no formal test framework)
- Estimated 3–5 working days per existing roadmap

Before starting: copy the 4 committed research/decision docs into the repo, commit them with one message, then begin 2a.

## Reversals this session could later reverse again

Three decisions under ADR-0001 are listed as explicitly revisitable with signals:

1. **Skipping e2e smoke tests before 2a.** If the first 2a extraction produces any regression that manual testing doesn't catch immediately, pause and write smoke tests before continuing.

2. **Not adopting pytest.** If Claude Code is used heavily and any silent regression ships into a released version, the next phase should write a new ADR to adopt pytest and add boundary snapshots. The 4 locally-kept plan docs contain the detailed pytest plan that would accelerate this reversal.

3. **Adopting existing roadmap wholesale over the external heavy plan.** If mid-2a the existing roadmap's 5-module decomposition proves to have an unforeseen coupling problem, the external plan's alternative decomposition (with research-validated extraction ordering via Mikado) is preserved locally for reference.

All three are observable-at-the-time reversals, not speculative ones. If none of the signals fire, the current plan holds.
