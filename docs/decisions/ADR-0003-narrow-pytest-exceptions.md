# ADR-0003: Narrow Pytest Exceptions Within ADR-0001

**Status:** Accepted
**Date:** 2026-04-21
**Decision makers:** Adam (project lead)
**Amends:** ADR-0001 (does not supersede)

---

## Context

ADR-0001 established manual-smoke-only testing as the Phase 2 methodology. The rule has served well: it kept test infrastructure overhead out of solo-dev scope, matched the 5000-LOC project scale, and aligned with comparable small Python desktop projects (Anki, Calibre, Picard — none of which used pre-extraction characterization tests).

Phase 2c planning (2026-04-21) surfaced a failure mode where manual smoke is demonstrably inadequate: **atomic file-write retry behavior under OneDrive sync and antivirus file-lock contention.** Primary-source evidence:

- Python bugs.python.org issue 46003 documents `os.replace` raising `PermissionError [WinError 5]` under AV/sync-client contention. Documented fix: retry with backoff.
- VTK's `cmSystemTools::RenameFile` uses 5 retries over 5 seconds for this exact failure mode.
- Obsidian officially recommends against OneDrive storage because of this class of issue.

Manual smoke has near-zero catch-rate for retry-loop regressions because the failure mode isn't reproducible on demand. The regression class (retry stops too early, backoff timings wrong, non-transient errors get swallowed) requires mocking `os.replace` to produce controlled failures — which is exactly what pytest is for.

A second candidate exception — `extends:` schema field cycle detection — is currently deferred with sub-phase 2c-c-5 (backlog per ROADMAP.md). If 2c-c-5 is later picked up, that exception falls under this ADR without requiring a separate amendment.

---

## Decision

**Within ADR-0001's manual-smoke-only foundation, permit narrow pytest exceptions when all of the following conditions hold:**

1. The failure mode has near-zero manual-smoke catch-rate (verified against documented precedent where possible).
2. Automated testing catches a class of regression that would otherwise ship and surface in user bug reports or data loss.
3. The test surface is small and focused — single-digit lines of test code, single-purpose.
4. The exception is explicitly documented in `docs/PHASE_2C_PLAN.md` (or its phase equivalent) with rationale and size estimate.

**Testing infrastructure remains minimal:** pytest is invoked directly (`pytest tests/smoke/test_<name>.py`), no fixtures framework, no CI integration, no coverage tooling. Tests live alongside smoke-log directory (`tests/smoke/test_*.py`) and are runnable in under 5 seconds.

**Scope of exceptions.** This ADR does NOT re-open the general question of test strategy. ADR-0001's manual-smoke-only default stands for:

- UI behavior (remains manual — Phase 2d's pytest-qt consideration is out of scope here)
- Preset render-output correctness (manual smoke against reference video is sufficient)
- Pydantic schema roundtrip (framework's own tests cover this)
- Copy-on-write identity preservation after rename (visible to manual smoke)
- Any other failure mode not meeting all four conditions above

**Additional exceptions beyond those approved in this ADR require either:**
- An amendment to this ADR documenting the new exception and its conditions, or
- A superseding ADR

---

## Currently approved exceptions

### Exception 1 — Atomic write retry under contention

- **Location:** `tests/smoke/test_atomic_write_retry.py`
- **Introduced:** Phase 2c-c-3
- **Rationale:** OneDrive sync and AV file-locks aren't reliably reproducible on demand. Manual smoke has near-zero catch-rate for retry-loop regressions.
- **Test shape:** Mock `os.replace` to raise `PermissionError` N times then succeed. Assert correct retry count, backoff timing, and error propagation when N exceeds retry limit.
- **Size:** ~30 minutes of test code, ~15 lines.
- **Deletion trigger:** None. Keep-forever — the failure mode doesn't go away.

### Exception 2 — (Conditional, backlog)

`tests/smoke/test_extends_cycle_detection.py` would activate if sub-phase 2c-c-5 is picked up from backlog. 8-fixture corpus covering valid chain, self-reference, N-cycle, missing parent, deep chain, type-mismatched parent. ~60 lines. Meets all four conditions of this ADR.

---

## Rationale

**Why amend ADR-0001 instead of superseding it.** ADR-0001's core argument — that Mikado + BBA + Parallel Change + Sprout Method methodology stack is overkill for 5000-LOC solo — remains correct. The methodology-rejection is independent of this narrow question about file-system-level regression testing. Keeping ADR-0001 authoritative for methodology choices while amending only the testing-exception scope preserves the research-backed decision.

**Why not just write the tests without documenting the exception.** Two reasons:

1. Future-me (or a future collaborator) reading ADR-0001 and finding pytest files would legitimately ask "did someone violate the ADR?" Explicit exception-documentation answers that question permanently.
2. The four conditions above are the real rule. Without them, "narrow pytest exceptions" erodes into general pytest adoption over time. Stating the conditions explicitly is the defense against drift.

**Why not adopt pytest more broadly.** Nothing has changed about the scale calibration that drove ADR-0001. 5000 LOC, solo dev, no team-distributed review burden. General pytest adoption would import infrastructure overhead disproportionate to the regression-catch benefit for most of the codebase. The two exceptions permitted here are the cases where the overhead is genuinely worth it.

---

## Consequences

### Accepted

1. **Small test directory grows.** `tests/smoke/test_atomic_write_retry.py` ships with Phase 2c-c-3. If 2c-c-5 is picked up, `tests/smoke/test_extends_cycle_detection.py` joins it. Maximum expected size: 2 pytest files by end of Phase 2 (one if 2c-c-5 stays backlog).

2. **Running tests becomes part of CLAUDE.md §2 self-review.** Where applicable, "pytest output shows PASS" joins the evidence-based self-review list. Not a new rule — just an additional evidence source for existing §2.

3. **Future collaborators may argue for more exceptions.** The four conditions are the defense. If someone argues for a new exception that doesn't meet all four, reject or require an ADR amendment.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Exception list grows beyond narrow intent; "narrow pytest exceptions" becomes "pytest everywhere" via precedent drift | Four conditions are stated explicitly. Each new exception requires documentation. Annual review if this ever happens. |
| Pytest dependency adds install friction for Mac teammates running from source | `pytest` is a ~2MB install, lives in `requirements.txt`. Minor. |
| Tests break during other work (e.g., refactoring atomic_write.py) and get skipped rather than fixed | Self-review §2 requires running tests; skipping them without fixing is a protocol violation. CLAUDE.md §6 scope-discipline rule also applies. |

### Reversal signals

Revert this ADR (keep ADR-0001 pure manual-smoke-only) if:

- Atomic-write tests become flaky or high-maintenance enough that they're net-negative.
- Phase 2d's pytest-qt consideration (if any) goes badly and poisons the pytest-adoption narrative.
- Team size grows and a different testing strategy becomes appropriate (would likely be a broader ADR superseding both this and ADR-0001).

---

## Related

- `decisions/ADR-0001-phase-2-methodology-reconciliation.md` — foundation this ADR amends.
- `decisions/ADR-0002-product-trajectory.md` — team-internal framing.
- `PHASE_2C_PLAN.md` — where the atomic-write pytest exception is scheduled (sub-phase 2c-c-3).
- `ROADMAP.md` — phase plan.

This ADR is narrow by construction. It does not re-open ADR-0001's broader methodology question.
