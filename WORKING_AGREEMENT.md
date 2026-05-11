# Working Agreement

**Between:** Adam (project lead) and Junaid (part-time developer)
**Project:** 1vmo Suite

This is the social contract between us. Read once, reference when questions arise, update together when something isn't working.

---

## Communication

| Channel | Use for | Response time |
|---|---|---|
| **WhatsApp / Teams** | Quick questions, blockers, daily updates | Same day usually |
| **GitHub PR comments** | Code review feedback, design discussion tied to code | Adam: 24h. Junaid: 48h. |
| **GitHub issues** | Architecture discussions, bug reports, feature proposals | 48h substantive response |
| **Sync call** | Progress review, voice/screen-share things | Every 3 days, ~30 min |

**Default mode is async.** Don't expect immediate responses. If something is genuinely urgent, mark it: "URGENT — blocking my work."

The 3-day sync is the regular touchpoint. Skip when there's nothing to discuss; reschedule when one of us can't make it.

---

## The Stuck Rule

**If you're blocked on any single problem for more than 2 hours, message Adam.**

Doesn't matter if it feels like a "dumb question." 2 hours stuck usually means missing context, not missing skill. A 5-minute conversation often unblocks 5 hours of frustration.

What "stuck" looks like:
- Spec is ambiguous on a specific point
- Environment issue (Python version, dep, OS quirk)
- Can't reproduce a bug Adam described
- Disagree with the spec but unsure if you should override
- Not sure if a behavior is in-scope or scope creep

**Silent blocking is the single biggest failure mode of remote async work.** Worse than asking "too many" questions. Just message — Adam responds when he can; you continue on something else while waiting.

---

## Verification — both of us check our work

**Mistakes happen on both sides.** Adam, Junaid, and AI assistants (Claude, Copilot) all make them. The defense is verification habits.

**Before you push code:**
1. Re-read your own diff line by line. Ask: "Did anything change that I didn't intend?"
2. Run the tests. Don't trust "should work" — actually run them.
3. Manually exercise the new behavior on a real input.
4. Check `git status` for files you didn't mean to add.

**About AI-generated code:** AI suggestions look confident and right but can be subtly wrong — invented function calls, missed edge cases, silent "improvements" you didn't ask for. **Read what you ship.** You're responsible for what's in your PR, not the AI.

Same on Adam's side. PR review is line-by-line, not rubber-stamping based on "looks reasonable."

The verification habit is the difference between shipping clean and shipping bugs.

---

## Decision authority

| Topic | Decided by |
|---|---|
| Architecture, module boundaries | Adam |
| Public API signatures | Adam |
| Integration into 1vmo | Adam |
| ADRs, governance, phase sequencing | Adam |
| Whether a PR merges | Adam |
| Implementation choices inside the module | Junaid |
| Internal organization, helpers, naming | Junaid |
| Library choices for internal helpers | Junaid |
| Test design beyond minimums | Junaid |
| Performance optimizations within the module | Junaid |

**When you disagree with Adam:**
1. Surface it: "I think X is wrong because Y."
2. Adam responds with reasoning. Counter-arguments welcome.
3. If still disagreement, Adam's call wins for now. Junaid implements it.
4. If the decision later proves wrong, Adam owns that — no "I told you so." Update and move forward.

This isn't authoritarian. One person makes the final call so things ship.

---

## Freedom inside the module

The scope rule is about **file boundaries**, not creative restrictions. Inside your module, you have wide latitude.

**You decide:** implementation approach (1, 2, or 3 from the spec), internal helpers, code organization, test cases beyond the minimum, library choices for internal helpers, error message wording (as long as `error_type` categories match the spec), performance optimizations, internal data structures, sync vs threading vs async internally (as long as the public function is sync), refactoring within your file across iterations.

**Be opinionated.** If you think Approach 2 is better than Approach 1 for reasons specific to your past experience, go with Approach 2 and document why. The spec gives guidance, not handcuffs.

The only firm constraints: scope protection (file boundaries), public interface stability, and the verification habit.

---

## Scope protection

**The hard rule:** you may only modify files explicitly listed in your spec.

For Phase A:
- ✅ CREATE `core/url_downloader.py`
- ✅ CREATE `tests/smoke/test_url_downloader.py`
- ✅ MODIFY `requirements.txt` (add yt-dlp only)

**Forbidden:** modifying any other file (including auto_render.py, other core/ files, assets, docs, CHANGELOG, .gitignore, .claude, tooling configs). No reformatting / re-styling existing code.

If you want to change something outside scope:
1. **Stop.**
2. Ask Adam.
3. Either he amends the spec to authorize, or it goes to `IDEAS_BACKLOG.md` for later.

This isn't trust issues — it's how clean PRs work. Each change does one thing. Mixed changes make review hard and rollback risky.

---

## API usage and rate limits

Phase A doesn't need API keys (yt-dlp is free). For future phases that may use APIs (Anthropic, ElevenLabs, Deepgram):

- **Cost guards in code from day one** — log per-call cost, check daily/monthly cap
- **Mock-first dev, real API second** — never hammer real APIs during dev
- **Cache identical inputs** — don't pay for the same call twice
- **Exponential backoff on errors** — failed retries capped at 3
- **Surface unexpected costs** — if spend looks weird, message Adam immediately
- **Test mode / dry run** — every API integration has a way to run without making real calls

For 1vmo specifically: Anthropic API key (when needed) gets a $50/month spending cap from day one. ElevenLabs Enterprise key is prepaid — use credits sparingly.

When in doubt about whether something is "too many API calls," ask Adam before running.

---

## Code review process

### Junaid opens a PR

1. **Title format:** `[Phase A] <module>: <short summary>`
2. **Fill out the PR template** (below).
3. **Notify Adam** on WhatsApp/Teams: "PR #N is ready."

### Adam reviews within 24 hours

One of three outcomes:
- **Approve & merge** — code is good
- **Approve with comments** — minor non-blocking feedback, merging now, follow-up if you agree
- **Request changes** — blocking issues, please address

### Junaid responds within 48 hours

Either with code changes or a counter-argument explaining why the feedback might be wrong.

If Adam sees scope creep in the PR (changes outside the spec), he'll ask you to revert those parts and either amend the spec or add to `IDEAS_BACKLOG.md`. Out-of-scope changes mixed in make review hard.

---

## PR template

```markdown
## What this PR does

[1-3 sentences]

## Spec reference

Implements [URL_DOWNLOADER_SPEC.md sections X, Y, Z]

## How I tested

- [ ] Manual test on Mac: [describe]
- [ ] Smoke tests pass: `pytest tests/smoke/test_url_downloader.py`
- [ ] Edge cases verified: [list]

## Self-review checklist

- [ ] Re-read my own diff line by line
- [ ] Module signature matches spec
- [ ] Did NOT modify any existing 1vmo files (only new files + requirements.txt)
- [ ] No `auto_render.py` touches
- [ ] No Qt / UI imports (post-Phase-2d the binding is PySide6; the rule is "no UI bindings at all in this module")
- [ ] All new code in `core/url_downloader.py` and `tests/smoke/test_url_downloader.py`
- [ ] Module docstring documents implementation choice
- [ ] Type hints on public functions
- [ ] No `print()` statements (use logger)

## Anything I'm unsure about

[Optional: design choices that could go either way, things wanting Adam's input]

## Out of scope (intentionally NOT done)

[Optional: things noticed but explicitly NOT done]

## Ideas for IDEAS_BACKLOG.md

[Optional: ideas that came up while working]
```

If any checkbox is unchecked, explain in the PR description.

### Example: a good PR description

```markdown
## What this PR does

Initial implementation of `core/url_downloader.py` per spec. Approach 1 (yt-dlp library
with progress_hooks). Includes the 7 internal exception classes, DownloadResult
dataclass, all 6 quality levels, subtitle support with silent skip, and cancellation.

## Spec reference

Implements URL_DOWNLOADER_SPEC.md sections: Public Interface, Quality Mapping,
Subtitles, Cancellation, Edge Cases, Module Structure.

## How I tested

- [x] Manual test on Mac: 5 URLs (YouTube, Shorts, TikTok, IG Reel, invalid) at
  quality='720p'. All returned expected Result types.
- [x] Smoke tests pass: 12/12 passing locally (online tests skipped without network)
- [x] Edge cases verified: invalid URL, playlist rejection, cancellation mid-batch,
  subtitles unavailable (silent skip)

## Self-review checklist

- [x] Re-read my own diff line by line
- [x] Module signature matches spec
- [x] Did NOT modify any existing 1vmo files (only new files + requirements.txt)
- [x] No auto_render.py touches
- [x] No Qt / UI imports (post-2d the binding is PySide6; the rule is "no UI bindings at all in this module")
- [x] All new code in core/url_downloader.py and tests/smoke/test_url_downloader.py
- [x] Module docstring documents implementation choice
- [x] Type hints on public functions
- [x] No print() statements

## Anything I'm unsure about

For `error_type='unknown'` I'm using yt-dlp's raw exception message in `error.args[0]`.
Curious whether you want a sanitized version that strips internal yt-dlp jargon.

## Out of scope (intentionally NOT done)

Noticed `core/preset_loader.py` has a small docstring typo ("the the"). Didn't fix
since out of scope. Worth a follow-up commit by you.

## Ideas for IDEAS_BACKLOG.md

While testing TikTok URLs I noticed yt-dlp can fetch metadata-only without downloading.
Could be useful for the "preview thumbnails before download" idea (#8 in backlog).
```

---

## Code conventions

- **Python 3.13** baseline
- **PEP 8** style, `black` if you want, 100-char line length (loose guideline)
- **Type hints** on all public functions
- **Docstrings** on all public functions (Google or NumPy style)
- **Logger, not print()** — `logger = logging.getLogger('core.<module>')`. No custom handlers in module code.
- **Tests in `tests/smoke/test_<module>.py`**. Mark online tests with `@pytest.mark.online`.
- **No new tooling without asking** — no new linters, formatters, type checkers, pre-commit hooks, or CI configs without Adam's sign-off.

---

## Definition of done (per PR)

A PR is ready for review when ALL true:

1. Module/feature implements everything in the spec's "Definition of done" section
2. All required smoke tests pass on your local machine
3. PR template filled out
4. **You self-reviewed** — re-read your own diff, looked for accidents, checked nothing scope-creeped
5. You've manually tested at least the MUST-work edge cases
6. Commits are descriptive (one thing per commit when possible)
7. You're available for review feedback within the next 48 hours

If any aren't true, mark the PR as Draft.

---

## Conflict & changes to this agreement

**Friction surfaces directly.** "I'm frustrated but I won't say anything and just be slow on PRs" is bad. "Hey, the 24-hour PR review is making me hesitant to open PRs. Can we talk?" is good.

**This document is a living contract.** Either of us proposes changes via WhatsApp/Teams or 3-day sync. Both agree → Adam updates the document. Disagree → keep the old version, revisit later.

---

## What happens after Phase A

- **Phase B:** Apple Silicon Mac compatibility port (your work, after Adam's Phase 2 stabilization)
- **Phase 2.5:** Port of Phase 1 features (Settings dialog, naming_utils, GPU pipeline). Mostly Adam, possibly some assists from you.
- **Beyond:** see `IDEAS_BACKLOG.md` for things on our radar

Phase B specs come when Phase A ships. No need to think about Phase B yet.

---

Welcome to 1vmo. Let's ship something good.
