# Ideas Backlog

Future work for 1vmo. **Nothing here is committed scope.** Parking lot for things either of us thought about but isn't building now.

**Current scope:** Phase A (URL downloader, Junaid) + Phase 2 stabilization (Adam). Everything below is "maybe someday."

Either of us appends ideas as they come up. We review during sync calls and decide what (if anything) graduates to the next phase.

---

## Discussed and held for later

Came up in earlier planning. Evaluated. Not the next thing, but not dead either.

**1. AI captions (Submagic-style)** — Whisper or Deepgram for transcription, FFmpeg for caption rendering. TikTok-style word-level timing.

**2. AI preset picker** — Claude API analyzes video, recommends from the 111-preset library. Embedding-based matching may be more cost-effective than per-call API.

**3. AI voiceover** — ElevenLabs Enterprise integration for TTS narration. Adam already has access.

**4. Phase 2.5 features port** — Settings dialog, naming_utils, GPU/NVENC pipeline, polish features. Mostly Adam's work; possible Junaid assists. Documented in `docs/PHASE_2_PORT_NOTES.md`.

---

## Natural extensions of Phase A (URL downloader)

If URL downloader works well, these become obvious next steps.

**5. URL input in cutter, merge, mixer** — extend the same `download_videos()` to the other 3 apps after auto_render integration validates the pattern.

**6. Batch URL list import** — paste 50 URLs from a spreadsheet, download them all at once.

**7. Save/recall URL playlists** — save groups of URLs the user downloads regularly.

**8. Preview thumbnails before download** — fetch metadata only, show user what they're about to download.

**9. Per-platform default settings** — different default quality for TikTok vs YouTube based on typical use.

---

## Natural extensions of Phase B (Mac compat)

After Apple Silicon Mac support ships, these become possible.

**10. Mac build/distribution pipeline** — `.app` bundle, code signing, notarization, DMG.

**11. VideoToolbox preset library** — full Mac-native hardware encoding to match NVENC presets.

**12. Cross-platform CI** — automated build verification on Windows + Mac via GitHub Actions.

---

## Bigger directional shifts

Larger ideas. Not in scope per ADR-0002 (personal/team-internal use), but possibilities if direction changes.

**13. API-mode for power users** — expose 1vmo as a Python library, scriptable by power users.

**14. Watch-folder mode** — drop videos in a folder, auto-render with default preset.

**15. Output upload** — after render, optionally upload result to YouTube / cloud storage.

---

## Quality-of-life

Polish on existing functionality.

**16. Render history / undo** — keep last N renders accessible for re-application.

**17. Preset preview** — show a sample-frame transformation before applying a preset.

**18. Per-user preference profiles** — Adam's defaults vs Junaid's defaults within the same install.

---

## Junaid-driven ideas

Add ideas as you discover them while working in the code: refactor opportunities you spotted but couldn't act on (scope discipline), feature ideas based on user needs, process improvements, doc gaps.

(Empty for now — fill in as you go.)

---

## Adam-driven ideas

Same for Adam.

(Empty for now — fill in as you go.)

---

## How we use this list

- Anyone appends. Add to a relevant section, or create a new section.
- Don't delete entries. Mark rejected ones `[REJECTED — reason]`.
- Review every few weeks during sync calls. Decide what graduates to next phase.
- Items staying in backlog isn't a failure — most good ideas don't fit current scope.
