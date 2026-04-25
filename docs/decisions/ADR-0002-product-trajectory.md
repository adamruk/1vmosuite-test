# ADR-0002: Product Trajectory — Team-Internal, Commercial Not Currently Planned

**Status:** Accepted (2026-04-22). Platform-scope clause partially superseded by ADR-0004 (2026-04-23) — Apple Silicon Mac added to targets. All other clauses remain in force.
**Date:** 2026-04-21
**Decision makers:** Adam (project lead)
**Supersedes:** none

---

## Context

Project framing evolved during 2026-04 planning:

1. **2026-04-15 through 2026-04-19** — "decompiled college project being revived for personal use." Phase 1 completed under this framing.
2. **2026-04-20** — framing briefly escalated to "commercial product from today." Deep research across licensing, pricing, installers, support tooling produced ~200 hours of scoped commercial-prep work.
3. **2026-04-21 (this ADR)** — corrected after stated intent: *"I was planning to complete now for myself and my team and in the near future maybe sell it as commercial product."* Further refined same day to *"let's keep it personal use only, not a commercial one, let's skip that."*

The correction matters because engineering scope differs meaningfully between the three framings. Team context (5 distributed, 3 × Windows + 2 × macOS; Phase 2 development solo) is documented in `docs/ROADMAP.md`.

---

## Decision

**Treat 1vmo Suite as a team-internal tool. Commercial release is not currently planned.**

1. **Primary users:** the 5-person team.
2. **Quality target:** "good enough for team production work."
3. **Commercial decision:** not on the current roadmap. If the decision changes later, a new ADR (ADR-0003 or later) will activate commercial-prep scope.
4. **Engineering decisions are justified on team-internal grounds alone.** Anything that happens to also serve a commercial future (PySide6 migration, extensible schema) is fine; anything that only serves commercial is backlog or out of scope.

### In scope for Phase 2 (team-internal needs)

- Shared `core/` package (Phase 2a, done)
- JSON preset schema subset: 2c-c-1/2/3/6 (ROADMAP)
- Observation V fix
- PyQt5 → PySide6 migration (Phase 2d)

### Out of scope / Backlog (commercial-prep or quality polish)

- Windows/macOS installers (run from source)
- Code signing certificates
- Trademark search
- License/payment integration
- Multi-generation `.bak` rotation (single-gen is sufficient for team use)
- In-app preset export/import UX (share via git)
- Vietnamese → English translation (Observation T)
- Marketing, pricing, support tooling
- Prefix-namespaced preset IDs (2c-c-4)
- `extends:` schema field (2c-c-5)
- Zoom-cycle generator (2c-d)
- Inheritance UI + preset audit (2c-e Part B)
- Parameter validation layer (Phase 2e)

Backlog items are tracked in `docs/ROADMAP.md` with triggers for pickup.

---

## Rationale

**Team-internal-now is a real constraint, not a fallback.** 5 distributed users with production dependencies is already beyond hobby scope. Crash recovery, preset sharing across distributed teammates, and cross-platform support are real requirements today. But they're team-scale requirements, not market-scale.

**Commercial-from-today overshoots.** Installer work, signing, trademark, and support tooling running alongside JSON migration and PySide6 migration produced ~200 hours of combined scope for a solo-led project. Commercial-release items have their own sequencing (cert acquisition takes weeks; trademark search can force renames), and running them in parallel with active refactoring multiplied blast radius.

**"Not currently planned" preserves optionality without forcing a timeline.** Engineering decisions that happen to also serve a future commercial activation (PySide6 migration, schema that's extensible later via 2c-c-5) are made correctly now without being over-built. If commercial decision changes in 6 or 18 months, a new ADR activates the deferred scope from the backlog.

---

## Consequences

### Accepted

1. **Commercial-prep items stay open longer.** Multi-generation `.bak` rotation, signed installers, trademark clearance — all deferred. Team-internal use can recover via git if data issues arise.

2. **Team is the only user base for this project at current scope.** No external-user feedback informing defaults. If commercial activates later, team usage data informs but doesn't substitute for external research.

3. **PySide6 migration justified on Mac-quality alone.** 2 of 5 team members are Mac users; PyQt5 on modern macOS has known issues. The "commercial licensing headroom" argument is a secondary benefit, not the primary justification.

4. **Observation T (Vietnamese translation) stays Open backlog.** Translation only activates if commercial decision changes, or if team convenience becomes compelling enough to motivate the work independently.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| "Not currently planned" becomes "never" by inertia; no explicit revisit | When a backlog item's trigger fires (per ROADMAP backlog table), it forces a revisit of the commercial decision. Natural checkpoint. |
| Team uses the tool productively for a year, then commercial opportunity emerges with short fuse — backlog work becomes urgent | Backlog is scoped in ROADMAP and PHASE_2C_PLAN. Pickup is a structured process, not a from-scratch rewrite. Estimated pickup time for full commercial backlog: ~60-100 hours on top of Phase 3. |
| Engineering decisions during Phase 2 unknowingly foreclose commercial options | Major design decisions (schema, UserData location, ID format) are explicitly versioned and lazy-migrable. No decision during Phase 2 is architecturally one-way. |

### Reversal signals

Write a superseding ADR if:

- Team decides to activate commercial trajectory (new ADR captures the decision and activates backlog scope).
- External user demand becomes compelling (e.g., someone outside the 5-person team asks to pay to use it).
- Team formally closes the commercial possibility permanently (unlocks additional scope-reduction decisions, e.g., permanently dropping the `extends:` field design).

---

## Related

- `decisions/ADR-0001-phase-2-methodology-reconciliation.md` — Phase 2 methodology.
- `ROADMAP.md` — phase plan (blockers + backlog) derived from this trajectory.
- `PHASE_2C_PLAN.md` — Phase 2 execution sized to team-internal requirements.

This ADR records a framing decision, not a technical decision. Subsequent technical ADRs may reference it to justify scope.