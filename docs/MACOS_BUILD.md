# macOS Build Guide — 1vmo Suite

**Audience:** Junaid (build operator) — and any future maintainer producing a macOS `.app` bundle from this repo.

**Scope:** macOS Apple Silicon (M1/M2/M3/M4) targeting macOS 12 (Monterey) and later. Intel Macs are out of scope for this build recipe.

**Status of macOS support:** the source tree is now macOS-runtime-stable after the Step 1–5 stabilization batch:

- Window minimum size reduced to **1280×800** so the apps fit on 13" MacBooks.
- QSS tree visibility patched in `auto_render.py`, `cutter.py`, `merge.py`, `mixer.py` so rows are visible in Dark Mode without selection.
- `open_output_directory` now tries the platform-correct opener first (`open` on macOS, `xdg-open` on Linux, `os.startfile` on Windows).
- Updater on macOS surfaces a "manual update required" dialog instead of attempting the Windows batch self-replace.
- `core/url_downloader.py` pins yt-dlp's muxer to the bundled `ffmpeg/` directory whenever one is present (both source-mode and frozen `.app`).

What this document does NOT cover: code signing, notarisation, App Store submission, Sparkle auto-update integration, or any Phase 3 features. Those are out of scope.

---

## 1. Source-mode launch (no build)

Before building, confirm the source mode runs cleanly on your Mac. This is what the QA checklist below also validates.

```bash
cd ~/Desktop/1vmo-junaid-onboarding-2026-04-25
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python auto_render.py     # 1vmo Auto Render
python cutter.py          # 1vmo Cutter
python merge.py           # 1vmo Merge
python mixer.py           # 1vmo Mixer
```

Requirements: Python 3.11+ (3.13 recommended; the pin in `requirements.txt` works on 3.13/3.14 on Apple Silicon).

If any of the four apps fails to launch in source mode, **stop and fix that first**. The frozen `.app` flow below cannot work if source-mode fails.

---

## 2. Required assets before building

### 2.1 Bundled ffmpeg + ffprobe

The repo's `ffmpeg/` directory is what gets shipped inside the `.app` bundle. Today it contains **broken symlinks** to `/opt/homebrew/bin/ffmpeg` (Junaid's local homebrew install) and is not portable.

**Action required before any build:**

1. Download static Apple Silicon binaries from <https://www.osxexperts.net/> (Justin Ruggles' builds) or build from source with `--enable-static` + `--enable-libx264 --enable-libx265 --enable-libfdk-aac --enable-libfreetype` + the codecs your presets actually use.
2. Place the two binaries directly at `ffmpeg/ffmpeg` and `ffmpeg/ffprobe`. No subdirectory. No `.exe` suffix on macOS.
3. Mark them executable: `chmod +x ffmpeg/ffmpeg ffmpeg/ffprobe`.
4. Verify they run: `./ffmpeg/ffmpeg -version` should print a version banner.
5. Remove the duplicate symlinks: `rm -f "ffmpeg/ffmpeg 2" "ffmpeg/ffprobe 2"` if present.

If the bundled ffmpeg is missing or unreadable, the renderer will fail with "FFmpeg not found at …" on first launch and exit with code 1 (`auto_render.py::_check_dependencies`).

### 2.2 Icon files (.icns)

The repo currently ships **Windows `.ico` icons only**:

```
assets/Auto_Render.ico
assets/Cutter.ico
assets/Merge.ico
assets/Mixer.ico
assets/Downloader.ico
```

macOS `.app` bundles require **.icns** format for the Dock badge and the Finder thumbnail. Without `.icns`, the bundle launches with a generic Python rocket icon.

**Conversion recipe** (run from repo root, requires only macOS-native `iconutil` and `sips`):

```bash
# Example for Auto_Render.icns — repeat for Cutter, Merge, Mixer, Downloader
mkdir -p assets/Auto_Render.iconset
sips -z 16 16     assets/Auto_Render.ico --out assets/Auto_Render.iconset/icon_16x16.png
sips -z 32 32     assets/Auto_Render.ico --out assets/Auto_Render.iconset/icon_16x16@2x.png
sips -z 32 32     assets/Auto_Render.ico --out assets/Auto_Render.iconset/icon_32x32.png
sips -z 64 64     assets/Auto_Render.ico --out assets/Auto_Render.iconset/icon_32x32@2x.png
sips -z 128 128   assets/Auto_Render.ico --out assets/Auto_Render.iconset/icon_128x128.png
sips -z 256 256   assets/Auto_Render.ico --out assets/Auto_Render.iconset/icon_128x128@2x.png
sips -z 256 256   assets/Auto_Render.ico --out assets/Auto_Render.iconset/icon_256x256.png
sips -z 512 512   assets/Auto_Render.ico --out assets/Auto_Render.iconset/icon_256x256@2x.png
sips -z 512 512   assets/Auto_Render.ico --out assets/Auto_Render.iconset/icon_512x512.png
sips -z 1024 1024 assets/Auto_Render.ico --out assets/Auto_Render.iconset/icon_512x512@2x.png
iconutil -c icns assets/Auto_Render.iconset
rm -rf assets/Auto_Render.iconset
ls -la assets/Auto_Render.icns
```

Repeat for `Cutter.icns`, `Merge.icns`, `Mixer.icns`. The `.ico` originals stay in `assets/` for the Windows build.

If `sips` complains about the source format, use Pillow:

```python
from PIL import Image
img = Image.open("assets/Auto_Render.ico")
img.save("assets/Auto_Render.iconset/icon_512x512.png")
```

### 2.3 Runtime assets

Beyond ffmpeg + icons, the build must include:

- `assets/Encoder.json` — the preset library.
- `assets/Encoder.txt` — the source-of-truth preset file (kept for regenerability).
- `assets/README *.md` — the in-app help dialogs read these.
- `assets/*.ico` AND `assets/*.icns` — both kept; the spec picks the right one per platform.

---

## 3. PyInstaller `.spec` approach

There is **no `.spec` file in the repo yet** (Salman audit A8). It needs to be authored. Use FastFlix's `FastFlix_Nix_OneFile.spec` as a structural reference; do not copy it verbatim.

### 3.1 Recommended layout

Author one spec per app (4 specs) — easier debugging than multipackage, and Adam's apps are intentionally separate processes:

```
1vmo-auto-render-mac.spec
1vmo-cutter-mac.spec
1vmo-merge-mac.spec
1vmo-mixer-mac.spec
```

Each spec produces `dist/1vmo Auto Render.app/` etc.

### 3.2 Required `Analysis()` parameters

For each spec:

```python
a = Analysis(
    ['auto_render.py'],                    # entry point
    pathex=['.'],
    binaries=[],
    datas=[
        ('assets', 'assets'),              # 108 presets + icons + README
        ('ffmpeg', 'ffmpeg'),              # bundled ffmpeg + ffprobe
        ('core', 'core'),                  # shared modules
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',
        'yt_dlp',
        'yt_dlp.extractor',
        'yt_dlp.postprocessor',
        'pydantic',
        'pydantic._internal',
        'pydantic.v1',
        'platformdirs.macos',
        'requests',
        'PIL.Image',
        'PIL.ImageQt',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'tkinter',                          # save ~5 MB
        'IPython',
        'jupyter',
        'matplotlib',                       # not used at runtime
        'scipy',
        'numpy.distutils',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)
```

### 3.3 `BUNDLE()` parameters

```python
app = BUNDLE(
    coll,
    name='1vmo Auto Render.app',
    icon='assets/Auto_Render.icns',
    bundle_identifier='com.1vmo.autorender',
    version='3.8.0',
    info_plist={
        'CFBundleName': '1vmo Auto Render',
        'CFBundleDisplayName': '1vmo Auto Render',
        'CFBundleShortVersionString': '3.8',
        'CFBundleVersion': '3.8.0',
        'CFBundleIdentifier': 'com.1vmo.autorender',
        'LSMinimumSystemVersion': '12.0',
        'NSHighResolutionCapable': 'True',
        # Required for the file picker to access user folders
        'NSDocumentsFolderUsageDescription':
            '1vmo Auto Render needs access to your Documents folder '
            'to read and write video files.',
        'NSDownloadsFolderUsageDescription':
            '1vmo Auto Render needs access to your Downloads folder '
            'to read source videos.',
        'NSDesktopFolderUsageDescription':
            '1vmo Auto Render needs access to your Desktop to read '
            'and write video files.',
        'NSAppleEventsUsageDescription':
            '1vmo Auto Render needs Apple Events permission to '
            'reveal output folders in Finder.',
        # Tells macOS not to throttle the app under App Nap
        'LSUIElement': False,
        # Avoid the "fetching" delay on App Translocation
        'LSEnvironment': {'PYTHONIOENCODING': 'utf-8'},
    },
)
```

Repeat with `name='1vmo Cutter.app'`, `bundle_identifier='com.1vmo.cutter'`, `icon='assets/Cutter.icns'`, etc. for the other three apps.

### 3.4 Hidden imports — running list

Start with the list above. After your first successful build, run the app and watch the Console.app log for `ModuleNotFoundError` lines. Each missed module gets added to `hiddenimports`. Common additions:

- `pydantic_core` (Pydantic 2.x internal)
- `yt_dlp.YoutubeDL` (sometimes needed explicitly)
- `requests.packages` (some installations)
- `nvidia_ml_py` — exclude on macOS via `excludes` (no NVIDIA on Mac)

### 3.5 Architecture decision: arm64 vs universal2

**Recommendation: arm64-only.**

- Apple Silicon is Adam's target deployment.
- `pynvml` (`nvidia-ml-py`) is x86-only on macOS and would break a universal2 build. On Mac there is no NVIDIA GPU anyway, so the dependency is irrelevant.
- arm64-only build is ~40% smaller (~250 MB vs ~400 MB).
- If Intel Mac support is later required, add a second spec with `--target-arch=x86_64` and ship two separate `.dmg` files.

Add to your build env: `PYINSTALLER_TARGET_ARCH=arm64`.

---

## 4. Build script

Create `scripts/build_mac.sh`:

```bash
#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Pre-flight checks
test -f assets/Auto_Render.icns || { echo "FAIL: missing assets/Auto_Render.icns — see docs/MACOS_BUILD.md §2.2"; exit 1; }
test -f ffmpeg/ffmpeg            || { echo "FAIL: missing ffmpeg/ffmpeg — see docs/MACOS_BUILD.md §2.1"; exit 1; }
test -f ffmpeg/ffprobe           || { echo "FAIL: missing ffmpeg/ffprobe — see docs/MACOS_BUILD.md §2.1"; exit 1; }
test -x ffmpeg/ffmpeg            || chmod +x ffmpeg/ffmpeg
test -x ffmpeg/ffprobe           || chmod +x ffmpeg/ffprobe

# Sanity: arm64 host
uname_m="$(uname -m)"
if [ "$uname_m" != "arm64" ]; then
    echo "FAIL: build requires an arm64 host. uname -m = $uname_m"
    exit 1
fi

# Activate venv if present
if [ -d .venv ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

# Build all four apps
for spec in 1vmo-auto-render-mac.spec 1vmo-cutter-mac.spec 1vmo-merge-mac.spec 1vmo-mixer-mac.spec; do
    test -f "$spec" || { echo "FAIL: missing $spec — author per docs/MACOS_BUILD.md §3"; exit 1; }
    echo "=== Building $spec ==="
    pyinstaller --noconfirm --clean "$spec"
done

# Post-build sanity
for app in "dist/1vmo Auto Render.app" "dist/1vmo Cutter.app" "dist/1vmo Merge.app" "dist/1vmo Mixer.app"; do
    test -d "$app" || { echo "FAIL: $app was not produced"; exit 1; }
    test -f "$app/Contents/MacOS/"*ffmpeg* 2>/dev/null || \
        find "$app" -name "ffmpeg" -type f -print -quit | grep -q . || \
        echo "WARN: ffmpeg binary not found in $app — investigate Analysis(datas=)"
    echo "OK: $app"
done

echo "Build complete. Test by double-clicking each .app in dist/."
echo "First-launch Gatekeeper: Cmd-click each .app, choose Open, confirm trust."
```

Make it executable: `chmod +x scripts/build_mac.sh`.

---

## 5. Optional: `.dmg` packaging

For distribution, package each `.app` into a `.dmg`:

```bash
hdiutil create -volname "1vmo Auto Render" \
               -srcfolder "dist/1vmo Auto Render.app" \
               -ov -format UDZO \
               "dist/1vmo Auto Render.dmg"
```

For a fancier layout with `Applications` symlink:

```bash
mkdir -p dist/dmg_staging
cp -R "dist/1vmo Auto Render.app" dist/dmg_staging/
ln -s /Applications dist/dmg_staging/Applications
hdiutil create -volname "1vmo Auto Render" \
               -srcfolder dist/dmg_staging \
               -ov -format UDZO \
               "dist/1vmo Auto Render.dmg"
rm -rf dist/dmg_staging
```

---

## 6. First-launch Gatekeeper flow (unsigned builds)

Without an Apple Developer ID + notarization, the first launch will say "macOS cannot verify the developer". Workaround:

1. Right-click (or Cmd-click) the `.app` in Finder.
2. Choose Open.
3. Click Open in the confirmation dialog.
4. After the first allowed launch, future double-clicks work normally.

If signing/notarization becomes a requirement, that's a separate workstream (Apple Developer Program $99/yr + `codesign` + `notarytool` + stapling). Not in scope for this build recipe.

---

## 7. Manual QA checklist (run after every build)

### 7.1 Environment

- [ ] macOS 12+ on Apple Silicon (verified `uname -m` returns `arm64`)
- [ ] Test in both **Light Mode** and **Dark Mode** (System Settings → Appearance)
- [ ] Test on at least one 13" / 14" MacBook screen (1440×900 effective or smaller)

### 7.2 Launch + icon

- [ ] Double-click `1vmo Auto Render.app` → Gatekeeper Cmd-click → Open works
- [ ] Window opens within 5 s, no spinning beachball
- [ ] Dock icon shows the `.icns` (not the generic Python rocket)
- [ ] Cmd-Tab switcher shows the `.icns`
- [ ] Window title reads "1vmo Auto Render vX.Y (Assets vA.B)"
- [ ] Repeat for Cutter / Merge / Mixer

### 7.3 UI scaling

- [ ] All toolbar buttons visible without horizontal scroll on 13" MBP
- [ ] Step 1 video tree shows full filenames
- [ ] Resolution column fits "3840×2160" without truncation
- [ ] Settings dialog opens fully (no clipped OK/Cancel buttons)
- [ ] Help dialog Markdown renders correctly

### 7.4 Dark mode visibility (Step 2 of stabilization)

- [ ] Step 1 video tree rows appear immediately on add (no need to click to reveal text)
- [ ] Step 2 encoder tree rows visible
- [ ] Step 4 output tree rows visible
- [ ] All dropdowns (Codec / Preset / Concurrent) show readable text when popped open
- [ ] QSpinBox / QLineEdit text visible
- [ ] Settings dialog text visible in every tab
- [ ] URL input dialog text visible
- [ ] **Repeat in Light Mode** (should be identical)
- [ ] Repeat for Cutter / Merge / Mixer

### 7.5 ffmpeg path resolution

- [ ] On first launch the renderer does NOT show "FFmpeg not found" error
- [ ] GPU status bar reads "No NVIDIA GPU detected" (correct on Apple Silicon)
- [ ] Pick a local mp4 in Step 1 → "Loading…" turns into duration + resolution within ~10 s (ffprobe timeout)

### 7.6 URL download (Step 5)

- [ ] Click 🌐 Add URL → dialog opens
- [ ] Paste a short public YouTube URL → OK → progress dialog appears
- [ ] Progress bar moves smoothly between 0 and 100 (not 0 → 100 jump)
- [ ] Downloaded file appears in Step 1 tree with metadata
- [ ] Cancel mid-download → dialog closes within ~5 s
- [ ] Click 🌐 Add URL again immediately after cancel → opens without RuntimeError

### 7.7 Render lifecycle

- [ ] Pick a local mp4 + a libx264 preset → ▶️ Start → renders to completion
- [ ] Output file plays in QuickTime
- [ ] Output filename ends in `_final.mp4` (not `.partial`)
- [ ] Start a long render → ❌ Cancel → no `_final.mp4` left on disk (Issue 1 fix)
- [ ] After cancel → Start again → renders cleanly (queue lifecycle Issue 6 fix)

### 7.8 Close-during-operation

- [ ] Start render → click red X → "rendering process is running" modal → Yes → app closes within 5 s
- [ ] Start URL download → click red X → "URL download is in progress" modal → Yes → app closes within 5 s

### 7.9 Drag/drop (Step 1 audit only — sibling apps still pending)

- [ ] Drag 1 mp4 from Finder onto `1vmo Auto Render.app` window → appears in Step 1 tree
- [ ] Drag 5 mp4s at once → all appear with metadata
- [ ] Drag a folder → no crash, no spurious rows
- [ ] Drag a .pdf → ignored gracefully
- [ ] Drag a path with spaces "/Users/me/My Videos/clip.mp4" → works
- [ ] Drag a path with emoji "/Users/me/🎬 Renders/clip.mp4" → works

### 7.10 Output-folder open (Step 3 fix)

- [ ] Click 📁 Select → pick a folder → label updates
- [ ] Click 📂 Open → Finder opens the folder
- [ ] Repeat with output dir containing spaces and emojis
- [ ] Repeat for Cutter / Merge / Mixer (must use macOS `open` first now)

### 7.11 Updater on macOS (Step 4 fix)

- [ ] Click 🔄 Updates with no update available → "[Updates] Checking…" appears + completes
- [ ] If a version manifest later says "new version available," confirm the **macOS-specific** dialog appears, not the Windows batch self-replace
- [ ] No `delete_old.bat` is ever written next to the .app

### 7.12 Regression checks

- [ ] All four apps still launch from source mode with `python <app>.py`
- [ ] py_compile sweep is clean
- [ ] ruff check . is clean

---

## 8. Known limitations on macOS

Items NOT addressed by this stabilization batch — explicitly deferred:

- **No NVENC.** macOS has no NVIDIA GPU driver. The renderer auto-detects this and offers only CPU encoders. Performance is bounded by the CPU.
- **No Apple Silicon hardware encode wiring.** VideoToolbox (h264_videotoolbox / hevc_videotoolbox) is not wired into the preset library. Could be added in Phase 3 but is intentionally out of scope here.
- **Unsigned build.** First launch requires Cmd-click → Open. For signed + notarised builds, see Apple's `codesign` + `notarytool` docs.
- **Updater is read-only on Mac.** Manual update only — re-download + re-build from source.
- **Drag/drop not wired in Cutter / Merge / Mixer.** Auto-render has it; the three siblings still don't. Deferred polish.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "FFmpeg not found at …" on launch | `ffmpeg/ffmpeg` missing / not executable / `2`-suffixed duplicate | §2.1 — re-place the binaries + `chmod +x` |
| Generic Python rocket icon in Dock | `.icns` not produced or not referenced in `BUNDLE(icon=)` | §2.2 — produce .icns + verify spec |
| App immediately closes after Gatekeeper "Open" | Missing `Info.plist` permissions entries | §3.3 — add NS*UsageDescription keys |
| QTreeWidget rows blank in Dark Mode | Sibling QSS not patched | Confirm cutter/merge/mixer have the Step 2 QSS additions |
| "Cannot open directory" QMessageBox | macOS lacks `xdg-open` and the legacy fallback ladder was used | Confirm Step 3 applied to that app |
| `ModuleNotFoundError` after launch | Missing `hiddenimports` | §3.4 — add module, rebuild |
| URL download mux failure | yt-dlp using a system ffmpeg with different codec support | Confirm `_BUNDLED_FFMPEG_DIR` resolves; ffmpeg/ffmpeg must exist in source-mode AND in `sys._MEIPASS/ffmpeg/` in frozen mode |

---

*End of macOS build guide. Phase 3 features (VMAF / originality / cloud) are deliberately not addressed here.*
