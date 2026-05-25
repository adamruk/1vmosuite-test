# 1vmo Video Suite

Four PySide6 desktop apps for batch video processing — backed by FFmpeg. (Migrated from PyQt5 in Phase 2d; see CHANGELOG and ADR-0001.)

| App | Purpose |
|---|---|
| `auto_render.py` | Batch re-encode videos through chained encoder presets (Ultimate / Gaming / Movie / Music / Social) with single or X-mode sequential render |
| `cutter.py` | Split videos — by time, by parts, trim start/end, or specific range |
| `merge.py` | Composite multiple videos in layouts (horizontal / vertical / 2x2 grid / overlay) |
| `mixer.py` | Concatenate videos end-to-end (no re-encoding) |

## Requirements

- Windows 10/11
- Python 3.11 or newer (tested on 3.13)

FFmpeg/FFprobe are bundled in `ffmpeg/`.

## Setup

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

Each app is a standalone script:

```
python auto_render.py
python cutter.py
python merge.py
python mixer.py
```

## Project layout

```
1vmo-suite/
  auto_render.py, cutter.py, merge.py, mixer.py   # 4 app entry points
  help_dialog.py                                  # shared: markdown help viewer
  assets/                                         # icons, encoder preset library, README md, version json
    data/                                         # image assets (qr, overlay, samples)
  ffmpeg/                                         # ffmpeg.exe + ffprobe.exe
  config_video_renderer.json                      # AutoRender config (input_files, output_dir, num_threads)
  config_video_cutter.json                        # Cutter config
  config_video_merge.json                         # Merge config
  config_video_mixer.json                         # Mixer config
  requirements.txt                                # PySide6 + requests + (see file for full list)
```

## Encoder presets

`assets/Encoder.txt` is the encoder library used by AutoRender. Pipe-delimited format:

```
<group>|<name>|<short description>|<tooltip details>|<ffmpeg args>
```

Groups: `🕹️ 1vmo Ultimate`, `🎮 1vmo Gaming`, `🎬 1vmo Movie`, `🎵 1vmo Music`, `🎥 1vmo Social`.

## CPU vs GPU rendering — production guidance

AutoRender supports two render paths. Pick based on the work, not by reflex.

- **CPU path (libx264).** Quality-stable. This is the reference. Output is reproducible run-to-run on identical inputs/params. Slower, especially on long videos or `-preset slow` presets. Use this for client-final masters, archival renders, A/B reference encodes, and anything where the output must match the original as closely as possible.
- **GPU path (NVENC: h264_nvenc / hevc_nvenc / av1_nvenc).** Faster (often 10×+ on RTX-class cards) but quality is hardware/driver-dependent and sits at a measurable but small ceiling below libx264 — empirically VMAF ~1–3 points lower on the 1vmo content profile (see ADR-0008). Use this for iterating, previews, internal review, social-format batches, and anything where speed matters more than the last 1–2 VMAF points.
- **Quality-sensitive renders.** When using the GPU path on sensitive material, enable the **Max Quality Mode** toggle in Settings (preset `p7` + `-multipass 2`, per ADR-0007 D7). It is slightly slower than the default NVENC settings but recovers most of the gap to libx264. For client-final masters, prefer CPU regardless of speed.

Defaults: `gpu_enabled=False`, `gpu_codec=h264_nvenc`, `gpu_preset=p4`, `gpu_max_concurrent=2` (matches `settings_dialog.py::DEFAULTS`, `RenderWorker.__init__`, and `core/preset_translator.translate_to_nvenc`). Settings dialog OK applies these keys on next render without restart (B-014 partial fix).

## Updates

There is no in-app updater. The previous Google-Sheet + Dropbox
download-and-relaunch channel was removed (ADR-0017, resolving B-051): the
audience is source-based developers, so fetching and executing a remote binary
whose source of truth was an editable spreadsheet was pure attack surface.
**Update by pulling the source — `git pull`.**

The app still shows its version in the window title; that string is read from
`assets/Version AutoRender.json` by `core/version_state.py` (a local,
network-free read). If a real distribution audience (`.exe`-only users) appears
later, a signed update channel — preferably GitHub Releases with signature /
checksum verification from a channel independent of the binary host — can be
added back under a new ADR.

## Notes

- **Architecture.** The four apps share a modular `core/` library. AutoRender's
  render pipeline is built from local-only subsystems (no cloud, no telemetry):
  - `core/preset_translator.py` — single-knob NVENC codec routing
    (h264/hevc/av1_nvenc) and CPU↔GPU preset translation (ADR-0015).
  - `core/encoder_intel/` — encoder capability analysis + graceful fallback (ADR-0012).
  - `core/scoring/` — quality scoring: VMAF, SSIM/PSNR, and perceptual-hash
    runners with a local score store (ADR-0009).
  - `core/optimization/` — batch analyzer, failure/quality classifiers, and a
    render recommendation layer (ADR-0010).
  - `core/orchestration/` — scheduler, retry policy, persistent queue, sleep
    inhibitor, system monitor, task logger, diagnostic bundle (ADR-0011).
  - `core/url_downloader.py` — hardened yt-dlp batch downloader (per-call
    timeout, concurrency cap, live-stream refusal, structured error categories);
    bundles Deno + yt-dlp-ejs for YouTube JS challenges (ADR-0016).
- **Decisions & history.** Design decisions are recorded as ADRs in
  `docs/decisions/`; every change is tracked per-commit in `CHANGELOG.md`. The
  codebase originated as a recovered port of the original packaged app and has
  since been rebuilt into the structure above.
- **Quality gates.** All subsystems are covered by smoke tests in `tests/smoke/`
  (28 suites); CI runs ruff + the smoke suite on every push and pull request.
- **Configs** persist per-app state (last output dir, last input files, mode).
  Committed empty — safe to delete locally; apps recreate them on first save.
- **Default encoder** is `libx264 + aac`. Change it via the encoder tree in
  AutoRender or by editing `assets/Encoder.txt`.
