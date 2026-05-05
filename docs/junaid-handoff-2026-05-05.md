# 1vmo Suite — Handoff to Junaid

**Date:** 2026-05-05
**From:** Adam (Telegram: @YIIII56)
**To:** Junaid
**Effective:** Immediate
**Scope:** Full ownership of the 1vmo Suite codebase, build process, and ongoing maintenance.

---

## What you're inheriting

Full ownership of the 1vmo Suite — four PyQt5 desktop apps (auto_render, cutter, merge, mixer)
wrapping bundled FFmpeg for video editing.
As of today, you own:

- The codebase (private repo, you have collaborator access)
- The v3.8 distribution build (just shipped to teammates, 1-2 week testing window running)
- All in-flight work: Phase 2d migration (PyQt5 → PySide6), v2.5.4 hotfix bucket, Mac migration (Phase 2.6, scheduled per ADR-0004)
- Teammate feedback triage during the v3.8 testing window
- All future technical decisions about direction

I'll be available for questions via Telegram or teams or whatapp (@YIIII56).
I'm not driving anything — that's you now.

---

## Day-1 priorities (read these first)

Three things to internalize before you write any code.

### 1. Test under real workload, not just "it opens"

Auto Render in particular has a failure mode where the app launches fine, the UI loads, the GPU badge shows green —
but actual rendering through it breaks.
**A successful launch is not proof of correctness.**
When you change anything in the render pipeline, run real videos through it end-to-end and verify the output plays.
The whole testing window with teammates is set up specifically because issues only surface under real workloads.

### 2. Be skeptical of Claude's claims

I've used Claude (and you will too) extensively for this project.
It's productive but has real failure modes you need to manage:

- **Demand evidence for "verified" claims.** When Claude says "I verified X works," ask for the actual artifact — command output, file contents, test logs. Don't accept the claim alone.
- **Cross-check with another tool.** ChatGPT, Grok, official docs, web search —
  when Claude tells you something non-trivial about a library, framework, or API, verify it independently before betting code on it.
- **Watch for sycophancy.** Claude will tell you what you want to hear.
  If you ask "did this work?" you'll often get "yes!" even when it didn't.
  Phrase questions to surface failures, not confirm successes.
- **Recently it's been less rigorous about verification on its own.**
  I've had to repeatedly ask Claude to re-verify claims it had already moved past.
  Build that into your workflow — verify before trusting.

This isn't "don't use Claude." It's "use Claude with explicit ground rules and skepticism."

### 3. Keep Windows and Mac as separate distributions

When you start Mac work (Phase 2.6 per ADR-0004), keep the two distributions separate.
**Same Python codebase** (per the ADR), but **separate builds, separate .zip files, separate release cadences, separate testing.**
Don't try to ship one combined artifact.
Don't conflate Windows bug reports with Mac bug reports.
They're parallel platforms with their own gotchas.

---

## Current state — what just shipped (v3.8)

### What's in the v3.8 distribution

The build is at `dist/1vmo Auto Render v3.8/` with these contents:

- `_internal/` — PyInstaller runtime (don't touch)
- `Code/assets/data/` — 16 PNG assets used by overlay presets
- `1vmo Auto Render v3.8.exe`, `1vmo Cutter v3.8.exe`, `1vmo Merge v3.8.exe`, `1vmo Mixer v3.8.exe`
- `portable.txt` (0 bytes — see B-022, currently a no-op in frozen builds)
- `README.txt` (~6 KB, plain ASCII, teammate-facing)

The zip is `dist/1vmo Auto Render v3.8.zip` (~173 MB).

### What changed in v3.8 vs v3.5/3.6/3.7

- **Encoder library:** 108 presets (down from 111 — removed 3 broken duplicates)
- **HEVC fix:** HEVC presets now actually produce HEVC output (previously could be silently overridden to H.264)
- **Audio-copy fix:** `-c:a copy` presets preserve source audio (previously could re-encode to AAC)
- **GPU NVENC pipeline:** wired correctly with the preset translator (per ADR-0007)
- **Stability:** all 4 apps no longer crash on videos with corrupt/missing duration metadata
- **Mixer typo fix:** logs to `video_mixer.log` and saves config to `config_video_mixer.json` (was incorrectly `*_merger.*` in earlier builds)

### What's NOT in v3.8 (deferred to v2.5.4 or later)

- Logs go to install dir, not `UserData/` — see B-021
- `portable.txt` doesn't engage in frozen builds, falls back to `%LOCALAPPDATA%/1vmo-suite/` — see B-022
- Mixer event handler `on_video_merge_started` (internal name only, no user impact) — see B-023
- Auto Render has no log file (uses in-UI panel) — see B-024
- Vietnamese docstrings in auto_render.py L857/L954 — see B-025

### Testing window status

Testing window started 2026-05-04 (yesterday, when zip was sent to teammates).
Window is 1-2 weeks.
Feedback comes to you (redirect any teammates messaging me to message you directly).

---

## The codebase — what you're looking at

### Decompiled vs. original code

This is the most important orientation point.
The codebase is a mix:

**DECOMPILED via PyLingual (treat with caution):**

- `auto_render.py`
- `cutter.py`
- `merge.py`
- `mixer.py`
- `help_dialog.py`
- `updater.py`

**ORIGINAL source (clean Python):**

- `bench.py`
- `gpu_detect.py`
- `settings_dialog.py`
- All of `core/` (extracted in Phase 2a — config.py, file_picker.py, widgets.py, preset_loader.py, ffmpeg_runner.py,
  atomic_write.py, encoder_schema.py, user_data.py, naming_utils.py, preset_translator.py)
- `core/url_downloader.py` (yours from Phase A)

**Why this matters:**

When you see weird patterns in the decompiled files — `float(subprocess.run(...).stdout)` with no try/except,
unusual control flow, inline ffprobe calls without error handling, oddly-structured try/except blocks —
your first reaction should NOT be "this is a bug, let me fix it."
Check first if it's a PyLingual decompilation artifact.

PyLingual sometimes emits Python that's syntactically valid but stylistically weird.
The 43 control-flow reconstruction artifacts from the original decompile (commit a225831) addressed Python correctness —
but stylistic weirdness survived.
Phase 2d (your current work) will rationalize many of these via libcst codemods.

### The Phase A integration you'll do

Your `core/url_downloader.py` is in the repo (414 lines, 17 tests, 13 offline-passing).
It was scoped as a **module** that ships independently.
The integration into `auto_render.py` was originally specced as MY work in the Phase A contract.

Now it's yours. Recommended:

1. Read your own module again with fresh eyes
2. Decide how it should integrate into `auto_render.py` — that's your design call
3. Wire it up
4. Test before/after — verify integrating it doesn't break existing render flows
5. The before/after comparison is interesting because you can validate your Phase A work works in the real app context, not just in isolation

This is also a good first integration exercise to learn `auto_render.py`'s structure before you do the bigger PyQt5→PySide6 migration.

### Updater

`updater.py` reads from a Google Sheet:

- Sheet ID: `1krEmBJDqA5GfHzBanaH-6r07G7qI2odAr-7wlpyQvgo`
- Currently a silent no-op because the sheet has no v3.9+ entries
- You can leave it alone, or modernize it (move to GitHub Releases per the original Phase 2 plan)
- Your call — not blocking anything

---

## PyInstaller build runbook

The full runbook is in `CLAUDE.md` Section 12 (just added in commit `fcee19a`).
Five rules learned the hard way during v3.8 packaging.
Read them before your first build attempt — they encode lessons that aren't obvious from PyInstaller docs.

The canonical spec is `1vmo-suite.spec` (multipackage).
Currently untracked in git pending decision (see B-026).
It's in your project root, just not committed yet.
Suggest committing it as the canonical build artifact for now (B-026 Option A).

---

## Open issues you should know about

The full BACKLOG is in `BACKLOG.md` (B-006 through B-026 are mostly open; B-001, B-002, B-003, B-005, plus B-017 are resolved; B-004 is still open).
These five are worth flagging specifically:

1. **B-021: Logs go to install dir, not UserData/** — architectural fix, three options documented in the entry. Probably touch this when you do Phase 2d since you'll be in the apps' init paths.

2. **B-022: portable.txt no-op in frozen builds** — the sentinel mechanism works in script execution but not in frozen PyInstaller bundles.
   Root cause likely `__file__` resolves to `_internal/` in onedir mode.
   Mac migration will need similar `sys.frozen` handling, so this is good preparation.

3. **B-020 [N51]: EncoderDialog `Group|Name` pipe-split doesn't strip whitespace** — silent bug.
   User types "Test | name" and gets `group="Test "` (trailing space). Group lookups silently miss.
   Two-line fix at `auto_render.py:1841` and `auto_render.py:1898`.

4. **B-018: Edit/Delete buttons grayed for ALL presets in fresh install** — UX gap, documented per ADR-0006.
   Four fix options ranked. Tooltip clarification (Option 1) was applied in commit `3d82182` but was insufficient
   because Qt suppresses tooltips on disabled buttons.
   A status label fix (Option B from the entry) was shipped in `6419ee8`.
   Option 4 (Clone button) remains for future UX work.

5. **B-017 RESOLVED: 11 stale `Code/assets/data/` paths in Encoder.txt presets** — fixed in `c60baf5`.
   Mentioned because the path semantics note in the entry matters: paths are RELATIVE, ffmpeg resolves them against process CWD.
   Fragile under shortcut launches with non-install Start-in dir.

For each B-NNN entry, the format is consistent: Status, Priority, Surfaced, Locations, Context, Resolution, Trigger for pickup.
Read the ones marked HIGH or MEDIUM priority before changing anything in those files.

---

## What's currently in flight

### v3.8 testing window (1-2 weeks)

Teammates have the zip.
They'll send feedback your way (route through Telegram or whatever channel you set up).
Triage:

- **Crashes / broken renders / data loss:** v2.5.4 hotfix priority, fix immediately
- **Settings don't save / wrong values:** v2.5.4 priority
- **UX papercuts:** queue for later, not blocking
- **Already-known issues** (B-018 button states, antivirus warnings, first-launch slowness): no action needed, they're documented

### Phase 2d (PyQt5 → PySide6 migration) — YOUR FIRST DELIVERABLE

**Soft 7-day target.** I'd rather you do it right than rush it.

Scope:

- Migrate auto_render.py, cutter.py, merge.py, mixer.py from PyQt5 imports to PySide6 imports
- Verify signal/slot connections still work (mostly identical syntax; some edge cases differ)
- Update `core/widgets.py` and `core/file_picker.py` if they have PyQt5-specific imports
- Update `requirements.txt` (replace PyQt5 with PySide6)
- Verify PyInstaller still bundles correctly (PySide6 has different bundle requirements)
- Test all 4 apps end-to-end on Windows
- No `qtpy` shim allowed (per CLAUDE.md §7 / ADR-0001)

Day-7 checkpoint call: we'll review where you are, what's working, what's stuck.
If 7 days isn't realistic for full migration, we revise.
Don't kill yourself hitting an arbitrary deadline.

### v2.5.4 hopper (post-testing-window)

After v3.8 testing window closes, fold in:

- Teammate-reported bugs from the window
- B-021 logs-to-UserData (combined fix across all 4 apps)
- B-022 portable.txt frozen-build detection
- Anything else that surfaced

### Phase 2.6 (Mac migration) — AFTER 2d

Per ADR-0004.
Add VideoToolbox encoder presets, system FFmpeg detection on Mac, .app bundling, code-signing for distribution.
**Separate distributions from Windows** (your guidance) but **shared codebase**.

Don't start this until Phase 2d is done and v2.5.4 hotfixes are folded in.
Otherwise you're juggling three platform states simultaneously.

---

## Recommended first 2 weeks

**Week 1:**

- Day 1-2: Read the codebase. Don't change anything. Build a mental model. Run all existing manual smoke tests. Try building v3.8 yourself end-to-end (clone, install, build, smoke test).
- Day 3-7: Start Phase 2d. Suggest migrating a smaller app first (cutter.py or mixer.py — both are smaller and simpler than auto_render).
  Verify it works end-to-end. Then merge.py, then auto_render.py last (largest, most complex with the GPU pipeline).
- Day 7: Checkpoint call with me.

**Week 2:**

- Continue Phase 2d if not done
- Process v3.8 testing window feedback as it arrives
- Start url_downloader integration into auto_render.py (your Phase A integration)

Day-7 call is the formal checkpoint.
Outside of that, ping me when you're stuck or want a sanity check on a non-obvious decision.

---

## How to reach me

- **Telegram:** @YIIII56
- **Available:** I'll respond to questions whenever you ping me; pace varies depending on my other project
- **Response time:** 24-48 hours typical, faster if urgent
- **Format:** batch your questions when possible — "here are 4 things I'm stuck on" beats four messages an hour apart
- **Video calls:** happy to do them for context-heavy stuff
- **Decision authority:** yours after handoff. I'll give opinions when asked, but I'm not approving anything

I'll be working on another project, so my response time degrades over time.
Plan accordingly.

---

## Closing

You delivered Phase A on spec.
That's why this handoff is happening — it's earned trust.
Keep the same rigor (sound exception categorization, lazy imports, well-bounded modules, real test coverage) and you'll do well.

The codebase isn't perfect.
There's decompiled code that needs rationalization.
There are 21 open backlog items (out of 26 total — B-001 through B-005 mostly resolved).
There's a soft 7-day target on Phase 2d that you can negotiate at the day-7 call.
You're inheriting a real system with real warts, not a polished product.

But it works.
The 4 apps run.
The render pipeline produces good output.
The encoder library has 108 working presets.
There's a decent testing window.
There's documentation.
There's an architecture (ADRs 0001-0008).

The 1vmo Suite is yours.
Make it better.

Welcome aboard properly.

— Adam
2026-05-05
