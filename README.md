# 1vmo Video Suite

Four PySide6 desktop apps for batch video processing — backed by FFmpeg.

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
  requirements.txt                                # PyQt5 + requests
```

## Encoder presets

`assets/Encoder.txt` is the encoder library used by AutoRender. Pipe-delimited format:

```
<group>|<name>|<short description>|<tooltip details>|<ffmpeg args>
```

Groups: `🕹️ 1vmo Ultimate`, `🎮 1vmo Gaming`, `🎬 1vmo Movie`, `🎵 1vmo Music`, `🎥 1vmo Social`.

## Updater

`updater.py` checks a public Google Sheet (anonymous gviz endpoint) for new versions and downloads updates from Dropbox. Version state is tracked in `assets/Version AutoRender.json`.

## Notes

- Source was recovered by decompiling the original PyInstaller-packaged `.exe` with pylingual. 43 control-flow artifacts from the decompiler were manually fixed. All 4 apps pass end-to-end smoke tests (real video → real FFmpeg cut → real output).
- Configs persist per-app state (last output dir, last input files, mode selection). They're committed empty — safe to delete locally while testing; apps recreate them on first save.
- Default encoder settings use `libx264 + aac`. Change via the encoder tree in AutoRender or edit `assets/Encoder.txt`.
