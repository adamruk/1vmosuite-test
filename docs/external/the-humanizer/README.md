# The Humanizer — Skill Package

A Claude skill that auto-detects content type (blog/LinkedIn/email/Slack), scans for AI-writing patterns, scores the draft, and rewrites it in an authentic human voice.

**Author:** Avem1984 (r/ClaudeAI)
**Version:** v2.4 (2026-04-19)
**Source:** https://www.reddit.com/r/ClaudeAI/comments/1s3i8nc/the_humanizer_a_claude_skill_that_catches_ai/

## Install (Claude.ai web/desktop)

1. Go to **Settings → Capabilities → Skills**
2. Click **Upload skill**
3. Select this zip file (`the-humanizer.zip`)
4. Done — the skill will auto-trigger on phrases like "humanize this", "does this sound like AI", "review this LinkedIn post", "rewrite in my voice", etc.

You can also invoke it explicitly by typing `/the-humanizer` in a chat.

## Auto-trigger

The skill activates automatically when the user mentions any of:
- "humanize", "AI detection", "sounds like AI", "make it sound human"
- "voice check", "blog review", "rewrite in my voice"
- "LinkedIn post review", "email review", "does this sound like AI"

Or any close paraphrase. No need to call it by name.

## What it does

1. Auto-detects content type from the draft (blog post, LinkedIn post, email, Slack message)
2. Scans for universal AI patterns + channel-specific patterns
3. Runs originality check + Hook vs. Value Calibration (LinkedIn only)
4. Scores on 4 dimensions (different rubric per channel)
5. Generates a structured review report
6. Produces a rewrite preserving all original ideas and substance

## Voice calibration (optional but recommended)

To get rewrites in *your* voice rather than a generic "human" tone, paste 1–3 paragraphs of your own writing the first time you use it. The skill will calibrate to your sentence rhythm, openings, closings, and word choices.

## Update cadence

Avem1984 refreshes the skill weekly with new patterns observed in the wild. Check the source Reddit post for the latest version. A v2.5 update was teased for May 2026.

## Known limitation

Step 6 ("Auto-Improvement Loop / Skill Self-Update") asks Claude to edit this file after every review. In practice this doesn't write back to your installed skill — Claude.ai doesn't auto-persist skill edits to disk. Treat the output of Step 6 as a suggestion log; manually edit the file when you want to add a pattern permanently.
