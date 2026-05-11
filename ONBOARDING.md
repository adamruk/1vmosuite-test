# Onboarding — 1vmo Suite

Welcome, Junaid. This document gives you the context to start work on the URL downloader module. Read once before opening the codebase.

**Estimated reading time: 8 minutes.**

---

## What is 1vmo Suite?

1vmo is a desktop video editing tool — four PyQt5 apps wrapping a bundled FFmpeg binary to apply preset-based transformations. Internal tool for Adam and his small team.

The four apps are `auto_render.py`, `cutter.py`, `merge.py`, `mixer.py`. **You won't see them in your zip** — they're not needed for URL tool work. You'll get full repo access via GitHub once Phase A ships.

**Current platform:** Windows only (with NVIDIA NVENC).
**New platform target (Phase B):** Apple Silicon Mac — your future work.

---

## Why you're joining

Adam needs help with two pieces of work:

1. **URL input feature** — users want to paste YouTube / TikTok / Instagram Reel URLs and have videos download automatically before processing. **This is your Phase A work.**
2. **Cross-platform Mac support** — currently Windows-only. You have a Mac and prior cross-platform video tooling experience. **This is Phase B, after Phase A ships.**

Adam handles existing 1vmo (Phase 2 stabilization, future Phase 2.5). You handle URL input first, then Mac compat. Parallel tracks — neither blocks the other.

---

## Project state (Apr 2026)

Recent commits worth knowing:

- **`482ffcf` (Apr 22):** Phase 2 governance — ROADMAP, ADRs 0001-0003, planning docs
- **`c03433a` (Apr 23):** Path B — 6 bug fixes ported from Phase 1 to auto_render.py
- **`498c0e3` (Apr 23):** ADR-0004 — authorizes Apple Silicon Mac as a platform target

What's pending (Adam's, not yours):
- Phase 2 stabilization (preset identity, schema, save-path fix, cancellation cleanup, tests)
- Phase 2.5 (Phase 1 feature port: Settings dialog, naming_utils, GPU pipeline, polish)
- Integration of your URL downloader into auto_render.py

---

## Your roadmap

```
Phase A → Phase B → Phase done
  │         │
  │         └─ Mac compatibility port
  │            (after Phase A ships AND Adam's stabilization ships)
  │
  └─ URL downloader module
     (parallel with Adam's stabilization;
      no auto_render.py integration — that's Adam's work)
```

**Phase A — URL downloader module:**
- Create `core/url_downloader.py`
- Create `tests/smoke/test_url_downloader.py`
- Add `yt-dlp` to `requirements.txt`
- See `URL_DOWNLOADER_SPEC.md`

**Phase B — Apple Silicon Mac port:**
- Spec doesn't exist yet; comes after Phase A ships
- Will involve: Mac FFmpeg binary, VideoToolbox-equivalent presets, path handling, build pipeline
- You lead because you have the Mac

Don't think about Phase B yet. Focus on Phase A.

---

## What's in your zip

This zip is a focused subset of the 1vmo repo containing only what's needed for Phase A on your Mac:

```
1vmo-junaid-onboarding-2026-04-25/
├── README.md                          ← what's in this zip
├── URL_DOWNLOADER_SPEC.md             ← your contract
├── WORKING_AGREEMENT.md               ← collaboration rules
├── ONBOARDING.md                      ← this file
├── IDEAS_BACKLOG.md                   ← future ideas
├── CLAUDE.md                          ← project rules you must follow
├── requirements.txt                   ← Python dependencies (you add yt-dlp)
├── core/                              ← your module goes here
│   ├── __init__.py
│   ├── ffmpeg_runner.py               ← style reference (Adam's pattern)
│   ├── preset_loader.py               ← style reference (Adam's pattern)
│   └── ...                            ← other helpers (don't modify)
├── tests/                             ← your test goes in tests/smoke/
│   ├── fixtures/                      ← test video fixtures
│   └── smoke/                         ← (your test_url_downloader.py here)
└── docs/decisions/
    └── ADR-0004-cross-platform-mac-support.md   ← authorizes your Mac work
```

**What's NOT in the zip** (and why):
- The 4 main apps (`auto_render.py`, `cutter.py`, `merge.py`, `mixer.py`) — you don't touch them; excluding reinforces scope discipline
- `assets/` — Windows FFmpeg binary (~100MB) and preset data; not needed for URL work
- `tools/` — preset migration utilities; not needed
- Other ADRs and planning docs — historical or Phase 2.5 content; explicitly skip per the reading list
- `CHANGELOG.md` — Adam-managed
- `.git/` — you'll get repo access via GitHub after Phase A

You'll get full GitHub repo access once Phase A ships and Adam sets up collaborator permissions.

---

## Files YOU create

```
core/url_downloader.py             ← CREATE (your module)
tests/smoke/test_url_downloader.py ← CREATE (your tests)
requirements.txt                   ← MODIFY (add yt-dlp line only)
```

That's it. Three files. Nothing else.

---

## Reading list (in order)

**Required before coding:**

1. **`URL_DOWNLOADER_SPEC.md`** — your technical contract. Read it twice.
2. **`WORKING_AGREEMENT.md`** — how we collaborate. Reference when process questions come up.
3. **`ONBOARDING.md`** (this file) — once.

**Skim:**

4. **`CLAUDE.md`** — project rules. Don't memorize, just know it exists. Especially relevant: §6 (minimum-fix discipline) and §9 (CRLF on Windows).
5. **`docs/decisions/ADR-0004-cross-platform-mac-support.md`** — authorizes your Phase B work.

**Reference (read if relevant later):**

6. **`core/ffmpeg_runner.py`** — Adam's subprocess pattern. Worth glancing at to match project style.
7. **`core/preset_loader.py`** — file I/O patterns, `pathlib` usage, error translation.

---

## First 30 minutes after extracting the zip

A concrete checklist for getting from "downloaded the zip" to "ready to code":

```
[ ] Extract zip somewhere on your Mac
[ ] cd into the extracted folder
[ ] Read ONBOARDING.md (this file) — done if you're here
[ ] Open and read URL_DOWNLOADER_SPEC.md (twice)
[ ] Open and read WORKING_AGREEMENT.md
[ ] Skim CLAUDE.md
[ ] Set up Python venv (commands below)
[ ] Verify the existing core/ modules at least import cleanly
[ ] Message Adam: "got it, ready to start"
[ ] Message Adam: "I'm going with Approach 1 / 2 / 3 from the spec because [reason]"
[ ] Start coding
```

---

## Setup

**Prerequisites:**
- Python 3.13 (3.12+ acceptable; verify code runs on 3.13 before PR)
- Git (you'll need this once you get GitHub access; not strictly needed for the zip work)
- Code editor (VS Code, PyCharm, whatever)
- ffmpeg installed and in PATH (you have ffmpeg 8.1 on your Mac — perfect)

**Setup commands:**

```bash
cd ~/Downloads/1vmo-junaid-onboarding-2026-04-25  # or wherever you extracted

# Create Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install existing dependencies
pip install -r requirements.txt

# Verify core/ modules at least import (sanity check)
python -c "from core import ffmpeg_runner, preset_loader; print('OK')"
# (You may see warnings about missing display / FFmpeg path — that's fine,
#  you won't run the GUI. We're just verifying imports work.)

# Once you've added yt-dlp to requirements.txt, install it:
# pip install yt-dlp

# Run any existing smoke tests (these may be empty/minimal — that's fine):
pytest tests/smoke/ -v
```

If any setup step fails, message Adam.

---

## Code patterns to mirror

You're free to write your module in whatever clean style you like, but matching project conventions makes review faster.

**Look at `core/ffmpeg_runner.py` for:**
- Module docstring placement and style
- Logger setup pattern
- Type hints on public functions
- Docstring conventions

**Look at `core/preset_loader.py` for:**
- File I/O patterns
- `pathlib.Path` usage
- Error translation (catching low-level exceptions, raising domain-specific ones)

Don't slavishly copy. Just absorb the style.

---

## Git workflow (once you have GitHub access)

You'll get repo access after Phase A ships. For the initial PR, Adam may ask you to send him a patch file or zip of your changes — we'll figure that out when we're there.

When you do have repo access:

- **Branch:** `feature/url-downloader`
- **Commits:** each does one thing; descriptive messages
- **PR:** opened from your branch into `main`, fill out the template (see `WORKING_AGREEMENT.md`)

---

## How and when to ask questions

**Before coding:**

If anything in `URL_DOWNLOADER_SPEC.md` is ambiguous, ask BEFORE writing code. Examples:
- "Spec says X, does it really mean X or should I do Y?"
- "Edge case Z isn't covered — what should happen?"
- "I'd prefer Approach 2 because [reason]. Sound okay?"

These are good questions. Adam would rather answer 5 clarifying questions upfront than have you build something wrong and need to redo it.

**During coding:**

When stuck (see Stuck Rule in `WORKING_AGREEMENT.md`):
- Try for 2 hours
- If still stuck, message Adam: "Stuck on [specific thing]. Tried [approaches]. Current confusion is [what]."

**At PR time:**

Open the PR with the template filled out. Adam reviews within 24 hours.

---

## What success looks like for Phase A

Phase A is done when:

1. PR with `core/url_downloader.py` and `tests/smoke/test_url_downloader.py` is merged
2. Module satisfies the Definition of Done in `URL_DOWNLOADER_SPEC.md`
3. Adam can integrate it into `auto_render.py` without modifying your module's interface

After merge:
- You're done with Phase A
- Adam handles the auto_render integration
- Phase B (Mac compat) starts after Adam's Phase 2 stabilization ships
- You'll get a separate spec and onboarding update for Phase B

---

## Things you might wonder

**"Why such tight scope? I could do more."**

Yes, you probably could. Each scope expansion is a coordination cost. We're starting tight, shipping clean, building trust through delivery, then expanding. Phase B will be bigger. By then we'll know how to work together.

**"Why not just adopt rvhs-main?"**

Adam respects the work in rvhs-main, but 1vmo's constraints (solo + part-time, Windows-native, no API costs, personal/team-internal use) make a different architecture the right choice for this project. If specific patterns from rvhs-main fit 1vmo's needs, surface them — Adam may want to incorporate them.

**"What about AI features (captions, preset picker, voiceover)?"**

In the backlog, deferred. Adam evaluated them, decided they're not the next thing. They may come later as separate phases. For now, focus on URL input. See `IDEAS_BACKLOG.md`.

**"Can I read auto_render.py to understand context?"**

You won't see it in this zip — it's intentionally excluded. Your module is designed to be context-free; you don't need to understand auto_render to write a working URL downloader. After Phase A ships and you have GitHub access, browse if curious — but don't get attached, integration work is Adam's.

**"What if I find a bug in existing code?"**

Surface it via GitHub issue or message. **Don't fix it as part of your PR** — that's scope creep. If it's real, Adam decides whether to fix now or schedule.

---

## What to do right now

1. Read `URL_DOWNLOADER_SPEC.md` twice
2. Read `WORKING_AGREEMENT.md` once
3. Set up your dev environment (steps above)
4. Send Adam "got it, ready to start" via WhatsApp/Teams
5. Pick your implementation approach (1, 2, or 3 from the spec) — message Adam if unsure
6. Start coding

Welcome aboard. Let's ship something good.
