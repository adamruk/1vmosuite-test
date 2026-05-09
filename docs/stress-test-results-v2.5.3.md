# v2.5.3 Stress Test Results — 2026-04-30

Post-v2.5.3 manual stress test of the encoder pipeline. All 4 designed
test presets passed. Verifies that v2.5.2's encoder fixes work end-to-end
on real hardware.

## Environment

- Python 3.13 (Microsoft Store) on Windows 11
- NVIDIA RTX 4080 Laptop GPU, driver 591.44
- NVENC capabilities: H.264 / HEVC / AV1
- Bundled ffmpeg 7.1+ (Lavc61.28.100)
- Portable mode active (UserData/ in install dir, opted in via portable.txt)

## Results

| Preset | Tests | Result |
|--------|-------|--------|
| P1 — Vanilla baseline | EncoderDialog Add flow, libx264 CPU + h264_nvenc GPU | PASS — both pipelines produce valid H.264/AAC |
| P2 — N51 confirmation | `Test \| name` pipe-adjacent whitespace handling | PASS as expected — bug fires per B-020 description; JSON stores `"group": "Test "` verbatim. Render output unaffected. |
| P3 — `_has_vcodec` (Observation V) | HEVC preset doesn't get libx264-overridden | PASS — output is hevc/hvc1, encoder tag is libx265 |
| P4 — GPU translator + `_has_acodec` | libx264 → h264_nvenc + `-c:a copy` preserves source audio | PASS — output encoder tag is h264_nvenc, audio codec is mp3 (preserved from source) |

## Verified v2.5.2 fixes (live on real hardware)

- `_has_vcodec` helper at `auto_render.py:106-110` — skips `-c:v` append
  correctly when preset already specifies a video codec. Verified by
  HEVC preset producing actual HEVC output (would have been silently
  overridden to H.264 before the fix).
- `_has_acodec` helper — skips `-c:a` append correctly when preset
  specifies `-c:a copy`. Verified by MP3 source audio passing through
  unmodified to output (would have been re-encoded to AAC before the fix).
- `core/preset_translator.translate_to_nvenc` — rewrites `libx264` to
  `h264_nvenc` and `-crf N` to `-cq N+2`. Verified by `gpu_enabled: true`
  preset producing `TAG:encoder=h264_nvenc` output and nvidia-smi showing
  encoder utilization > 0% during render.

## Confirmed open issues

- **B-020 / N51** fires as documented; JSON stores `"group": "Test "`
  with trailing space and `"name": " Trim trailing space"` with leading
  space when user types whitespace adjacent to the pipe character.
  Render output is unaffected — bug is metadata-layer only.
  Remains LOW priority for Phase 2d UX phase.
- **Observation S** confirmed: `EncoderDialog` has no Details field;
  the `details` key in `encoder.user.json` always round-trips as
  empty string regardless of user input.
- **B-018** confirmed: Edit and Delete buttons enabled when only user
  presets selected; grayed when any built-in is in selection. Behavior
  matches BACKLOG description.

## Synthetic test source

`test_source_mp3.mp4` — 8 second color-bars video + 1 kHz sine wave audio,
720p libx264 + 64kbps libmp3lame. Generated via:

```bash
ffmpeg -f lavfi -i testsrc=duration=8:size=1280x720:rate=30 \
       -f lavfi -i sine=frequency=1000:duration=8 \
       -c:v libx264 -preset fast -c:a libmp3lame -shortest \
       test_source_mp3.mp4
```

Required for `_has_acodec` testing because real social-media test clips
are typically AAC, which makes the test unfalsifiable: an AAC source
plus any worker behavior (correct copy, or incorrect re-encode to AAC)
both produce AAC output. A non-AAC source like this MP3 file is the
only way to distinguish the two outcomes.

## Methodology

The 4 presets were designed to exercise specific code paths added or
modified in v2.5.2:

- **P1** is the boring control case — must work or everything else is
  meaningless.
- **P2** is a deliberate-failure test — confirms the audit-discovered
  N51 bug (the basis for BACKLOG entry B-020) actually behaves as
  predicted in shipped code, validating the BACKLOG entry's accuracy.
- **P3** validates Observation V's fix specifically — needs a video
  codec other than libx264 to detect override-vs-preserve behavior.
- **P4** combines two checks (GPU translator + audio-copy preservation)
  into one render to minimize total test time without losing coverage.

Each preset was added through the EncoderDialog UI (not edited directly
in JSON) to also exercise the Add flow and `save_user_presets_json`
serialization. The resulting `encoder.user.json` was inspected after
each addition to verify field-by-field round-trip correctness.

## Conclusion

v2.5.2's encoder pipeline fixes are verified working on RTX 4080 + Windows
11 + Python 3.13 (Microsoft Store) under portable-mode user-data layout.
v2.5.3's preset library cleanup (108 presets, no broken `@t=fill` divider
duplicates, no empty-group placeholder entries) is verified loaded
correctly through migration. No regressions surfaced. Encoder pipeline
is considered ready for Phase 2d's PySide6 codemod and Nuitka packaging
work.
