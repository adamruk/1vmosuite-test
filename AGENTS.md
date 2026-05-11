# AGENTS.md — Engineering workflow rules for the 1vmo Suite

Contractual operating rules for any contributor who uses, drives, or supervises an AI coding agent (Claude Code, Codex, Cursor, Copilot CLI, others) on this repo. Humans contributing without AI assistance are not bound by every rule here, but the verification gate (§4), scope discipline (§3), and commit discipline (§5) still apply.

Precedence: this file is subordinate to `CLAUDE.md`. Where `CLAUDE.md` is silent or this file is more specific, `AGENTS.md` applies. Where they conflict, `CLAUDE.md` wins.

---

## 1. Read these before touching code

Order matters. Skipping any of these is a violation.

1. `CLAUDE.md` — non-negotiables, rule precedence, scope discipline, byte-by-byte fidelity, two-terminal workflow.
2. `docs/ROADMAP.md` — phase status, observations canon (lettered Open/Triaged/Fixed list), strategic context.
3. The most recent `docs/decisions/ADR-*.md` files. ADRs are binding once Accepted; do not contradict them in code or docs without writing an amending ADR.
4. `BACKLOG.md` — deferred items. If the work you are about to do touches a B-NNN, link it in the commit body.
5. `CHANGELOG.md` `[Unreleased]` section — to understand what has shipped since the last tag and to add your own entry (see §6).

---

## 2. AI verification discipline

For every AI-driven change, the human supervisor MUST verify, BEFORE accepting the suggestion, that:

1. **Cited facts are real.** Every ADR reference, commit hash, line number, file path, and test result the AI cites in commit messages, CHANGELOG, BACKLOG, or comments has been independently confirmed by the human. Hallucinated citations (e.g. "per ADR-0008 fix-2 best speed/quality knee" when ADR-0008 says no such thing) are a Sev-1 review failure and require a forced revert.
2. **Defaults are not silently changed.** If a kwarg default, config default, or class constant moves, the human checks the diff against `core.config.AppDefaults` (§3 below) and the relevant ADR. AI agents are not authorized to change a default with the justification "I think this is better."
3. **Reverts are exact, not paraphrased.** When the request is "revert X to origin/main," the human diffs against `origin/main` and confirms zero residual edits. An AI agent rewriting the wording while reverting is not a revert.
4. **No "while I'm here" changes.** Per `CLAUDE.md` §6, every change in a diff must serve the prompted goal. Drive-by formatting changes, comment rewrites, or unrelated refactors must be split out and surfaced for the human to accept separately.
5. **AI-asserted authority is not real authority.** When an AI agent writes "Adam said this is mandatory" or "per Codex review" without the human pasting the actual upstream message, treat it as the AI's interpretation and re-confirm with the actual author.

The human is the source of truth, not the agent. The agent's confidence does not raise its accuracy.

---

## 3. Scope control

This repo is in active migration and bug-fix phases. Scope creep is the most common failure mode.

- **One goal per change.** If a prompt asks for "fix B-014," the diff fixes B-014 and only B-014. Cleanup of unrelated files belongs in a separate change.
- **Defaults are centralized.** Runtime-tunable defaults live in `core.config.AppDefaults` (Phase 1). Any literal default for `gpu_enabled`, `gpu_preset`, `gpu_max_concurrent`, `gpu_codec`, `gpu_error_action`, or `output_collision` outside that dataclass is a drift bug and is caught by `scripts/check_default_drift.py`. Add a new field to `AppDefaults` rather than re-introducing a literal.
- **No architectural changes in tooling/governance PRs.** The Phase 2 governance setup explicitly does not change rendering logic, GPU defaults, or runtime behavior.
- **No new ADR-binding decisions in code.** If a change would alter behavior an ADR specified (e.g. CRF→CQ offset table per ADR-0007 D3, VMAF thresholds per ADR-0008), an amending or superseding ADR must land in the same change.
- **No silent additions to project policy.** `CLAUDE.md` is not amended without explicit owner sign-off and a CHANGELOG entry per `CLAUDE.md` §4.

---

## 4. Verification requirements (the gate)

Before any commit lands on `main` or a PR branch is opened for review, ALL of the following must pass on the working tree:

1. **`py_compile` sweep** — every `*.py` outside `.venv/`, `.git/`, `__pycache__/` compiles cleanly.
2. **Phase 2d rule check** — zero matches for `from PyQt5`, `import PyQt5`, `pyqtSignal`, `pyqtSlot`, `pyqtProperty`, `.exec_(`, `QRegExp`, `QStringList` in source `*.py`; no `qt_compat*` / `qtpy*` / `qt_shim*` files anywhere.
3. **`ruff check`** — exit 0.
4. **`ruff format --check`** — exit 0 (canonical formatting).
5. **`mypy`** — exit 0 against the modules covered by strict config (see `pyproject.toml [tool.mypy]`).
6. **Validation scripts** — `scripts/adr_lint.py` (existing), `scripts/check_changelog.py` (existing), and the Phase 2 additions `scripts/check_adr_references.py`, `scripts/check_default_drift.py`, `scripts/check_repo_consistency.py` all exit 0 against the staged change.
7. **Smoke** — at minimum `python3 tools/check_encoder_schema.py` exits 0 (preset library still parses against schema).
8. **`pre-commit run --all-files`** — passes for at least the touched files in the change.

If any check fails, fix the failure or revert; do not bypass. Pre-commit framework supports `--no-verify`; using it on `main` or a review branch is a process violation.

---

## 5. Commit discipline

- **Conventional Commits** (per `.cz.toml` / commitizen). Type prefixes: `feat`, `fix`, `refactor`, `revert`, `perf`, `style`, `docs`, `test`, `chore`, `ci`, `build`.
- **One concern per commit.** Do not batch a refactor + a behavior change + a doc update into one commit. If your working tree spans multiple concerns, stage and commit them separately.
- **Small commits.** Aim for a diff a reviewer can read in one sitting. If a commit needs more than ~5 paragraphs of body to explain, it should probably be split.
- **CHANGELOG entry mandatory** for any commit that adds tooling, creates user-visible files, or changes behavior. The `scripts/check_changelog.py` hook enforces this. Pure internal refactors may skip a CHANGELOG entry with explicit owner confirmation in the commit body, per `CLAUDE.md` §4.
- **No reverts without context.** Revert commits state what is being reverted, the prior commit hash, and why.
- **No silent merge commits.** If you need to merge, write a `merge:` commit body explaining the merge.

---

## 6. Review expectations

- Every non-trivial PR gets at least one human reviewer who has independently verified §4.
- AI-generated review reports (e.g. Codex audit, Claude-side audit) are advisory inputs to the human reviewer, not substitutes for human review.
- A reviewer who finds a fabricated citation (§2) escalates to the project owner before approving.
- Reviewers check the BACKLOG and ROADMAP for items the change implicitly closes or invalidates; if anything, the PR description lists them.

---

## 7. Two-terminal workflow

Reiterated from `CLAUDE.md` §1 for AI agents:

- 🔴 **MAIN** — writes, refactors, commits.
- 🟢 **PARALLEL** — read-only surveys.
- Audits and reviews run in PARALLEL.
- Writes run in MAIN.

AI agents must echo the terminal label in their summary blocks per `CLAUDE.md` §3.

---

## 8. Sandbox limitations (operational note)

Some AI agents run in sandboxes that mount the repo via virtiofs or similar. Known limitations observed during Phase 1 / Phase 2:

- The sandbox may be unable to unlink `.git/index.lock`, leftover `tmp_obj_*` files, `__pycache__/`, `*.pyc`, or files the host created. When this happens, the agent stages the changes and produces a Terminal script for the human to finalize the commit locally. This is a sandbox constraint, not a permission denial — the agent is not bypassing rules.
- The sandbox may not have GPU/PySide6 at runtime. Static AST + py_compile is the substitute; runtime smoke is the human's job.

---

## 9. Phase status

Active phase: **Phase 2 — Tooling & Governance Setup** (governance-only; no runtime/architecture changes).

Active branch: `phase2d-pyside6-migration` (Phase 1 work also lands here pending push).

When this phase ships, this section updates to point at the next phase. The historical phase trail lives in `docs/ROADMAP.md`.
