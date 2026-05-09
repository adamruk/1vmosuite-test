# Architecture Decision Records (ADRs)

This directory holds ADRs for 1vmo Suite: architectural and strategic choices significant enough that future maintainers need to know **why**, not just **what**.

## When to write one

Write an ADR for decisions that are hard to reverse and have consequences beyond a single commit:

- Framework migrations (PyQt5 → PyQt6/PySide6)
- Encoder strategy (NVENC default policy, fallback rules, preset library structure)
- Distribution model (updater source, packaging format, platform targets)
- API or config-schema surface changes that affect users or extensions
- Cross-cutting refactors (shared core module extraction)

Don't write one for: bug fixes, dependency bumps, cosmetic changes, or anything git log can explain on its own.

## Naming convention

```
ADR-NNNN-slug.md
```

- `NNNN` — 4-digit zero-padded sequence, assigned at creation, **never reused or renumbered** even if the ADR is later superseded or rejected.
- `slug` — lowercase hyphenated, descriptive enough to identify without opening the file.

Examples:
- `ADR-0001-nvenc-migration.md`
- `ADR-0002-preset-library-split.md`
- `ADR-0003-updater-github-releases.md`

## Status lifecycle

Each ADR opens with a `Status:` line. Valid values:

- `Proposed` — under discussion, not yet in effect.
- `Accepted` — the current answer; code reflects it.
- `Superseded by ADR-NNNN` — replaced, but kept in place for historical context. **Do not delete superseded ADRs.**
- `Rejected` — considered and declined; kept so the rejection reasoning isn't lost.

## Referenced from CHANGELOG.md as

`[ADR-0001]` or `[ADR-0001-nvenc-migration]` inline in the entry.
