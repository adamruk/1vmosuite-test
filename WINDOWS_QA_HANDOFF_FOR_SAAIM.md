# Windows QA Handoff for Saaim

Branch: phase2d-pyside6-migration  
Latest expected commit: 51815a0 or newer

## Must test on Windows

1. App startup
- launches cleanly
- no DLL/plugin errors
- no updater popup on startup
- resize/maximize works

2. Video table
- local videos visible immediately
- URL videos visible immediately
- no blank rows until click
- filenames with spaces/emojis work

3. URL workflow
- YouTube
- YouTube Shorts
- TikTok
- invalid URL
- cancel download
- Add URL again after success/cancel
- no QThread deleted RuntimeError

4. Render workflow
- CPU render
- cancel render
- render after cancel
- output file plays

5. NVIDIA/NVENC
- NVENC preset render
- cancel GPU render
- multiple GPU renders
- no stuck ffmpeg/GPU process

6. Preset audit checks
- 9:16 Bitrate
- 5s Cycle Zoom
- Cycle 100x with audio
- Layer Overlay presets
- presets with spaces/quotes

7. Windows path checks
- Desktop
- Downloads
- OneDrive
- paths with spaces
- long filenames
- non-English filenames

Send screenshots/videos/logs for every PASS/FAIL.
