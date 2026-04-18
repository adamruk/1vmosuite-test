# Research Summary — Why the Plan Became Option 3

**Purpose:** single consolidated record of the findings from three research passes that reshaped the original Phase 2 refactoring plan. This is the "why" document that sits behind README.md's "what."

**Source material:** two full research artifacts produced in this session (April 18–19, 2026) plus four earlier audit rounds. The full research artifacts live in the claude.ai transcript; this file is the distilled output.

---

## Research Pass 1 — Pressure-test against 16 comparable projects

**Scope:** strategic pressure-test of the three active tracks (Phase 2a shared-core extraction, Phase 2c JSON preset migration, Phase 2d PyQt5→PySide6 migration) against real-world practice from comparable projects.

**Projects surveyed:** Anki (pylib/aqt), Calibre (qt.core facade), Picard (single package), HandBrake (preset system), OBS Studio (portable mode), Notepad++ (doLocalConf.xml), Sigil (plugin_utils), Hex-Rays IDA (PyQt5 shims), Shotcut, Kdenlive, JetBrains Rider (color scheme UI), VS Code, Adobe Substance Painter, Foundry Katana, Mu, pythonguis.com (Martin Fitzpatrick).

### Findings that stood up

**Phase 2c was the strongest track.** Your flat single-preset schema, builtin/user file split, portable UserData/ sibling, Program Files guard, atomic-write-with-rotation, archive-on-parse-error, UTF-8 with `ensure_ascii=False`, and JetBrains bold/lock-icon UI convention all aligned point-for-point with 5+ comparable projects. No material corrections needed.

**Phase 2a approach matched legacy-code best practice in form:** the combination of Branch by Abstraction + Mikado + Parallel Change + characterization tests is textbook-correct for "extract shared library from N apps" per Matthias Noback, Vinta Software, Nicolas Carlo (*Understand Legacy Code*), and Martin Fowler's bliki entries.

**Staggered per-app Qt migration** was validated against Sigil, Hex-Rays, qutebrowser, and Reddit r/QtFramework consensus.

### Findings that suggested a change

1. **Add a `core/qt.py` Qt binding facade before Phase 2a.** This was based on Calibre's `qt.core`, Anki's aqt.utils.tr indirection, Sigil's plugin_utils, and Hex-Rays' shim pattern. Research Pass 1 recommended this as the single highest-leverage change.

2. **Reconsider the qtpy rejection.** 2024–2026 writing from Hex-Rays, Martin Fitzpatrick, and Reddit r/QtFramework recommended qtpy as transitional scaffolding to be removed after migration completed.

3. **Scale calibration warning.** The plan's methodological rigor (Mikado + BBA + Parallel Change + Sprout Method + 11-seam snapshots) exceeded what comparable small-Python-desktop projects actually documented doing. Kovid Goyal wrote Calibre without ever using a debugger; Mu uses classic pytest not snapshots; none of Anki, Calibre, Picard, Mu published a pre-extraction characterization-test phase.

### Result after Pass 1

First adjustments made to the plan: added `core/qt.py` facade as a Phase 2a prerequisite, kept all other methodology. Scale concern flagged but not acted on.

---

## Research Pass 2 — Deeper strategic investigation, include failures

**Scope:** go deeper on the three Pass 1 findings. Specifically look for projects that tried these approaches and regretted/abandoned them. Correct for the survivor bias of Pass 1.

**Key new datapoints:**

### On qtpy vs hand-rolled (Area A)

**UCSF ChimeraX Trac #4120 (January 2021):** Tom Goddard surveyed both qtpy and mottosso/Qt.py, contacted both maintainers, and concluded *"we would be better off making a very simple shim of our own following the pattern of qtpy."* Five years later the ~100-line shim is still in use; ChimeraX successfully migrated PyQt5→PyQt6 with optional PySide6 daily builds. This is the **closest comparable-scale precedent** and it chose hand-rolled explicitly.

**qtpy-as-blocker counter-evidence:** ChimeraX's own Trac later records that the `qtconsole` package (which depends on qtpy) broke ChimeraX's Python shell after the Qt6 migration because qtpy's Qt6 support lagged. **qtpy can itself become a migration-blocker when its support trails the bindings you care about.**

**Foundry Katana migration guide:** *"It is discouraged to import the Qt modules using the widely known try/except ImportError pattern."* This warning applies equally to qtpy and hand-rolled shims.

**Marcus Ottosson (Qt.py):** *"Qt.py does not hide members from the original binding. This can be problematic if, for example, you accidentally use a member that only exists in PyQt5 and later try running your software with a different binding."*

**Revised conclusion:** hand-rolled is defensible. Size it at ~100 lines following ChimeraX, not 200+.

### On core/qt.py facade (Area B)

**PyInstaller 6.5+ (2024) explicit guard:** *"PyInstaller now explicitly disallows attempts to collect multiple Qt bindings packages (PySide2, PySide6, PyQt5, PyQt6) into a frozen application … the build process is aborted with error message."* A facade implemented as `try: from PySide6 except: from PyQt5` will abort your PyInstaller build whenever both bindings are present in the dev environment.

**Armin Ronacher (*Build It Yourself*, January 2025):** celebrates *"the code that doesn't need to be touched for years because it was done right once"* and is *"suspicious of platform abstraction libraries that constantly churn."*

**Armin Ronacher (*Agent Design Is Still Hard*, November 2025):** *"right now we would probably not use an abstraction … at least until things have settled down. The benefits do not yet outweigh the costs for us."*

**Fowler (YAGNI bliki):** *"any abstraction that makes it harder to understand the code for current requirements is presumed guilty."*

**Hynek Schlawack (EuroPython 2025, "Design Pressure"):** facades invite additional abstractions on top of themselves.

**BackInTime v1.5.0 (July 2024):** small Python+Qt app at comparable scale, did PyQt5→PyQt6 migration directly with no facade, shipped without notable incident. Post-release issues were ordinary Qt-version bugs that a facade would not have prevented.

**qtpy's own troubleshooting documentation:** tells users to *"use Qt5 bindings for removed modules, or migrate to Qt6 alternatives"* for whole classes of Qt6 API removals. **Ten years of maintained qtpy cannot fully hide the bindings.** A 200-line hand-rolled facade has zero chance of doing better.

**Calibre misread:** the prior recommendation assumed `qt.core` was a cross-binding facade. It's a single-binding re-export that pays off at 500k LOC. Different pattern entirely.

**Revised conclusion:** **reverse the Pass 1 recommendation.** Do not build `core/qt.py` before Phase 2a. Direct migration in Phase 2d, app-by-app. If repetition bites mid-migration, write a 10–30 line import-grouping file reactively.

### On methodological scale calibration (Area C)

**Kent Beck, *Tidy First?* (2024), sized for solo scale:** explicit three options are *"tidy first, tidy after, or **never tidy**"* — "never tidy" is treated as a real answer. Beck's warning: upfront refactoring design means *"decisions in conditions of maximum uncertainty and minimum of knowledge."*

**Martin Fowler (refactoring.com):** *"Refactoring isn't a special task that would show up in a project plan. Done well, it's a regular part of programming activity."*

**Fowler (Opportunistic Refactoring bliki):** *"There is a genuine danger of going down a rabbit hole here, as you fix one thing you spot another, and another, and before long you're deep in yak hair."*

**Michael Feathers (*Working Effectively with Legacy Code*):** explicitly pitched at *"large, untested legacy code bases."* The techniques assume team-scale, untested legacy context — not a solo dev's own 5000 LOC.

**Documented solo-dev failure mode — Naram Alkoht, "Ship Your Ugly Code" (April 2026):** set up PHPStan-max + Rector + Pint + 100% coverage from first commit, **abandoned in 4 days**, shipped in 2 months on three simple rules. Alkoht's sentence: *"Every rewrite article is written for teams and companies. For a solo developer, the biggest risk isn't bad architecture. It's never shipping."*

**Anki case (2026):** the actual public crisis was maintainer burnout leading to Damien Elmes handing stewardship to AnkiHub. **The scarce resource for small Python desktop projects is founder energy, not refactoring rigor.**

**Empirical snapshot-testing data (University of Nijmegen study, 1,487 JEST projects, 2023):** snapshot adoption is concentrated at module public-boundaries, not internal seams. Snapshots co-change with code in roughly 8.2% of commits. **Maintenance burden scales linearly with seam count.** 11 seams = 11× the maintenance drag of 3.

**AI-in-loop factor:** 2024–2026 evidence on AI regression testing (Tricentis, Parasoft) supports boundary snapshots for catching silent AI edits, but not the planning ceremony layer. AI regression protection argues for **snapshots at 3–4 app boundaries**, not Mikado graphs.

**Revised conclusion:** **the Pass 1 scale warning strengthens substantially.** Drop the methodology stack; keep a thin boundary-snapshot layer; defer shared-core extraction until Rule of Three fires with concrete feature pressure.

---

## The cross-cutting pattern

All three Pass 1 findings exhibited the same error: reading patterns from 10×–100× larger projects or fundamentally different consumer structures, and recommending them at 5000 LOC solo without scale adjustment.

- **Calibre's `qt.core` ≠ a 1vmo-shaped facade.** It's a 500k LOC consolidator.
- **Sigil's `plugin_utils` ≠ a 1vmo-shaped facade.** It's a plugin-API compatibility layer for external plugin authors.
- **Feathers' characterization-test stack ≠ a 1vmo-shaped technique.** It's a large-legacy-system rescue toolkit assuming code you didn't write.

The corrected direction is consistent across all three: **"smaller, reactive, and only what the code currently demands."** This isn't a rejection of discipline — it's the version of discipline that ships at solo scale.

The one 2024–2026 factor that unambiguously justifies retained rigor is the Claude-Code-in-loop factor: AI agents can change *how* they solve problems between model updates and can cascade edits through shared functions. Boundary snapshots are specifically responsive to that profile. This is the sole methodology element the evidence keeps.

## Meta-finding — why solo-dev decisions structurally diverge from large-project decisions

Three structural differences drive the consistent overshoot that Pass 1 exhibited:

**Motivation is finite and shipping is the scarcest resource.** Team projects distribute motivation across contributors; solo projects have one reservoir that drains against the *whole* plan. Overhead that is 5% of a team's time is 50% of a solo dev's feature-coding time. Alkoht's 4-days-to-abandonment is the extreme version; the median failure is slower erosion that still never ships.

**Coupling before decoupling is a predictable solo anti-pattern.** qtpy adoption, `core/qt.py` facade, and shared-core-before-migration all introduce new coupling as a precursor to later decoupling. At team scale, different people own different pieces in parallel. At solo scale, the same person lives with the coupling for the full duration and cannot parallelize past it. The staggered 4-app release plan is actively harmed by any pre-extraction layer that forces the apps to move together.

**Cargo-culting is the dominant failure mode, not under-engineering.** Large projects generate the published writing that dominates refactoring discourse (Calibre, Feathers, Fowler, Sigil, Hex-Rays blog more than small projects). This creates a systematic prior toward heavier methodology than small-project evidence would support on its own terms. The counter-evidence (BackInTime shipping PyQt5→PyQt6 without a facade; ChimeraX's 100-line shim beating qtpy for their needs; absence of heavy methodology across four successful small Python desktop projects) is empirically stronger but narratively weaker.

**Working heuristic:** when a big-project pattern is proposed for a small-project situation, ask what goes wrong if you don't do it. If the honest answer is "a few hours of `sed` later," skip it.

---

## Mapping from research to the plan

| Research finding | Plan decision |
|---|---|
| Area A: hand-rolled is defensible (ChimeraX) | Kept — no qtpy, hand-rolled if needed at all |
| Area B: do not build `core/qt.py` facade | Adopted — no facade layer planned |
| Area C: replace methodology stack with Beck's *Tidy First?* | Adopted — Option 3 |
| Area C: reduce 11 seam snapshots to 3–4 boundary snapshots | Adopted — Option 3 |
| Area C: defer shared-core until Rule of Three fires | Adopted — `core/` emerges reactively during Phase 2c |
| AI-in-loop justifies keeping boundary snapshots | Adopted — 4 boundary snapshots retained |

The five plan documents (README.md, CORRECTIONS.md, phase-2a-plan-v2.md, phase-2a-step-2-plan.md, phase-2c-execution-plan.md) were written during the heavy-methodology phase. They remain in the repo as **reference material** — correct about the *how* of specific techniques when needed, but not the *execution script*. README.md is the authoritative reconciliation document between the reference plans and Option 3.
