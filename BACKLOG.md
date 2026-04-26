# Backlog

Deferred audit-fix items, surfaced during the toolchain install (commits 5e7e8c9 + dc0747c) on 2026-04-26. Strategy: defer-with-tracking. End-of-Phase-2 cleanup phase resolves all items below before Phase 2 ships.

Each item has a stable ID (B-NNN) referenceable in commit messages and CHANGELOG entries.

---

## Governance / ADR

**B-001** — ADR-0001 missing required field: Decision makers. adr-lint flagged 2026-04-26.

**B-002** — ADR-0002 inline status date mismatch: Status line shows `Accepted (2026-04-22)` but Date field shows `2026-04-21`. adr-lint flagged 2026-04-26. Reconciliation: pick canonical date, update both fields, add Revision History note.

**B-003** — ADR-0004 missing required fields: Date and Decision makers. adr-lint flagged 2026-04-26.

**B-004** — Audit findings M1-M16 from 2026-04-26 audit (see chat record). Includes deviation note errors in `bf4b636`, missing Observation V git tag, ADR-0004 format inconsistency, Path B bundling rollback impact, and other governance items.

## Code quality

**B-005** — 7 ruff lint errors remaining after auto-fix. Confirmed sample from `auto_render.py`:

- E722 bare except (line 106)
- F841 unused variable `current_output` (line 109)

Full list in `/tmp/precommit-baseline.txt` from 2026-04-26 baseline run.

## Documentation hygiene

**B-006** — Markdownlint violations repo-wide (365 total before MD013 bump to 200; expected reduction of approximately 200-300 with bump). Spans CHANGELOG.md, ROADMAP.md, PHASE_2C_PLAN.md, PHASE_2_PORT_NOTES.md, NVENC_PARAMETER_REFERENCE.md, PRESET_PHILOSOPHY.md, all 4 ADRs, all 5 README*.md, tests/README.md, scripts/. Auto-fixable rules remaining: MD022 (blanks around headings), MD031 (blanks around fences), MD032 (blanks around lists). Manual rule: MD040 (fenced code language tags).

**B-007** — Memory rule #13 cleanup: timeline / hours / fatigue language across multiple governance docs (ROADMAP.md lines 11/37 + table, PHASE_2C_PLAN.md lines 11/15/31/43/58/72/87/103/120/128/156/164/166/168, ADR-0002 lines 62/64/85, ADR-0003 lines 85/96). User finds this language patronizing; rule was added after these docs were written.

## Toolchain follow-ups

**B-008** — `pyproject.toml` decision deferred. Commitizen config currently in `.cz.toml`. If the project later needs `pyproject.toml` (packaging, ruff config, etc.), migrate `.cz.toml` content to `[tool.commitizen]` section.

**B-009** — Strict-mode commitizen-branch hook deferred. Currently `.pre-commit-config.yaml` uses lenient enforcement (commit-msg only, no commitizen-branch on pre-push). Flip to strict by adding commitizen-branch hook with `stages: [pre-push]` once team is comfortable with Conventional Commits.

---

## Resolution policy

- Items resolved: move to a "Resolved" section at bottom with commit hash and date.
- New deferrals during Phase 2 work: append here with new B-NNN ID.
- End-of-Phase-2 cleanup phase: every B-NNN must be resolved or explicitly downgraded to a future phase before Phase 2 ships.
