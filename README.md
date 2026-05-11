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
  updater.py                                      # shared: version check against Google Sheet
  help_dialog.py                                  # shared: markdown help viewer
  assets/                                         # icons, encoder preset library, README md, version json
    data/                                         # image assets (qr, overlay, samples)
  ffmpeg/                                         # ffmpeg.exe + ffprobe.exe
  config_video_renderer.json                      # AutoRender config (input_files, output_dir, num_threads)
  config_video_cutter.json                        # Cutter config
  config_video_merge.json                         # Merge config
  config_video_merger.json                        # Mixer config (note: historical name is "merger")
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

## Updater

`updater.py` checks a public Google Sheet (anonymous gviz endpoint) for new versions and downloads updates from Dropbox. Version state is tracked in `assets/Version AutoRender.json`.

## Notes

- Source was recovered by decompiling the original PyInstaller-packaged `.exe` with pylingual. 43 control-flow artifacts from the decompiler were manually fixed. All 4 apps pass end-to-end smoke tests (real video → real FFmpeg cut → real output).
- Configs persist per-app state (last output dir, last input files, mode selection). They're committed empty — safe to delete locally while testing; apps recreate them on first save.
- Default encoder settings use `libx264 + aac`. Change via the encoder tree in AutoRender or edit `assets/Encoder.txt`.
