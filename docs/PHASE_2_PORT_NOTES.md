# What to port to Phase 2

A handoff of everything we changed in this Phase 1 folder. Apply to your
Phase 2 folder **after** Phase 2 is in a stable state — not before. This
document is a checklist, not a diff; you'll be cherry-picking changes.

---

## Status — what has already shipped in v2

This section is amended-on-pickup (Phase 2.5 entry, 2026-04-27). The original
Phase 1 -> v2 port spec below is preserved as historical context; the Status
block here records what is already in v2 and does NOT need re-porting.

**Bug fixes table — port status:**

| # | Bug | v2 status |
|---|---|---|
| 1 | Trailing `-c:v` overrode preset codec | SHIPPED in v2 via Path B [c03433a] (`_has_vcodec` helper) |
| 2 | `gpu_error_action='skip_file'` hung batch | TO PORT in Phase 2.5 (depends on Settings dialog F1) |
| 3 | `closeEvent` crashed on None workers | SHIPPED in v2 via Path B [c03433a] (None-worker guard) |
| 4 | `output_collision` setting had no effect | TO PORT in Phase 2.5 (depends on Settings dialog F1) |
| 5 | `QThread.started` double-spawn / RuntimeError | SHIPPED in v2 via Path B [c03433a] (`started.disconnect`) |
| 6 | Out-of-order completion stamped wrong row | SHIPPED in v2 via Path B [c03433a] (`tree_item`/`task_index` stamp) |
| 7 | `output_text` (FFmpeg log) unbounded growth | SHIPPED in v2 via Path B [c03433a] (`setMaximumBlockCount(2000)`) |
| 8 | Config files cp1252 -> utf-8 | SHIPPED in v2 via core/config.py (lines 26 + 46 use `encoding='utf-8'`) |

**Known issues — port status:**

| Issue | v2 status |
|---|---|
| 1. Bug 9 TOCTOU in `naming_utils.avoid_collision` | STILL OPEN — port to Phase 2.5 with naming_utils (F2). Only true open deferred issue. |
| 2. `-c:a copy` overridden by `-c:a aac` | SHIPPED in v2 via Path B [c03433a] (`_has_acodec` helper) |
| 3. `gblur=sigma=20` perf bottleneck | SHIPPED in v2 via [89dcdce] + [2629ffe] (`boxblur=20:2` in 14 presets across .txt and .json) |

**Baseline drift since spec was written:** EncoderDialog has been rewired in
2c-c-3 + 2c-c-4 (preset ID schema v2, prefix-namespaced IDs). The PORT_NOTES
spec below predates this work; some integration points may have shifted. Port
work in Phase 2.5 should treat the current EncoderDialog as the v2 baseline,
not the Phase 1 source referenced in this spec.

---


## TL;DR

- Big GPU/NVENC story, Settings dialog, onboarding polish, 59-char filename
  limit, 8 bug fixes, default X-Render slots bundled with the .exe.
- **2 new files** to copy into Phase 2: `settings_dialog.py`, `naming_utils.py`.
- **1 preset rewritten** in `assets/Encoder.txt` (`9:16 CRF High`).
- **~700 lines added/changed** across `auto_render.py`.
- **3 known issues** flagged but not fixed — see bottom of this doc.

---

## New files to drop in (whole-file copy)

| File | Purpose |
|---|---|
| `settings_dialog.py` | Tabbed Settings dialog (General / Rendering / Advanced) with OK/Cancel + JSON persistence + reset-to-defaults. Imported by `auto_render.py` as `from settings_dialog import SettingsDialog`. |
| `naming_utils.py` | 59-char output filename limit. Public API: `timestamp()`, `safe_part(name, max_len)`, `clip_to_limit(filename, max_total)`, `avoid_collision(path)`. Imported by `auto_render.py` as `import naming_utils`. |

Both are self-contained — no dependencies beyond stdlib (`os`, `re`,
`datetime`) and PyQt5 (settings_dialog only).

---

## auto_render.py — what changed, by area

### GPU / NVENC pipeline

- **`RenderWorker.__init__`** new params (with defaults that preserve
  current behavior): `use_gpu=False`, `nvenc_quality_offset=3`,
  `gpu_error_action='retry_cpu'`, `output_collision='overwrite'`,
  `show_ffmpeg_command=True`. Stored as `self.<name>`.
- **New signal** on `RenderWorker`: `batch_stop_requested = pyqtSignal()`.
  Emitted when `gpu_error_action == 'stop_batch'`.
- **New method `_translate_to_nvenc(params)`** on `RenderWorker`:
  `libx264 → h264_nvenc`, `libx265 → hevc_nvenc`, `-crf N → -cq (N + offset)`,
  `-preset` mapped (`ultrafast→p1`, `veryfast→p2`, `fast→p3`, `medium→p5`,
  `slow/slower/veryslow→p7`).
- **New method `_run_ffmpeg_command(command)`** on `RenderWorker`: extracts
  the subprocess.Popen + stderr-progress-streaming loop into a helper so
  it can be called twice (initial attempt + CPU retry). Returns
  `(returncode, was_cancelled)`.
- **New method `_has_vcodec(params)`** on `RenderWorker`: returns True if
  the preset already specifies `-c:v` or `-vcodec`. Used to gate the
  trailing-codec append.
- **CPU fallback** in `process()`: if GPU encode returns non-zero AND
  `use_gpu` AND not image-encoder, branch on `gpu_error_action`:
  - `retry_cpu` (default): rebuild command with **original untranslated
    params** + `-c:v libx264` + `-c:a aac`, run once. Use a flag to prevent
    infinite recursion.
  - `skip_file`: emit `error_occurred` (so the existing handler advances
    the batch — see Bug 2) and return.
  - `stop_batch`: emit `batch_stop_requested` and return.
- **`_gpu` filename suffix** when `use_gpu and not is_image_encoder`.
  Applied to the `_final` and `_step{N}` mp4 forms; image (`%03d.jpg`)
  branch untouched.

### Settings dialog wiring

- New attributes loaded in `__init__` after the existing config load:
  `nvenc_quality_offset`, `gpu_error_action`, `output_collision`,
  `show_ffmpeg_command`, `open_output_when_done`. All have safe defaults
  matching pre-existing behavior.
- New methods on the main window:
  - `open_settings()` — modal `SettingsDialog`; on OK calls `_reload_config_settings()`.
  - `_reload_config_settings()` — re-reads `config_video_renderer.json`
    and applies output dir, GPU toggle (gated by capability), all five
    runtime keys. Note: thread count change requires restart.
- **`save_config` rewritten as a merge** instead of overwrite — load
  existing JSON first, `dict.update(...)` with current state, write back.
  Critical: this prevents SettingsDialog-managed keys from being wiped
  when the main window saves its own state. Also persists
  `'sequential_slots'` (see "Default slots" section below).
- ⚙️ **Settings button** added to the `video_controls` toolbar between
  GPU button and Help.

### GPU status indicator (was: bottom statusBar; now: toolbar button)

- `_init_gpu_status_bar()` rebuilt as a clickable QPushButton, returned
  from the method so the caller can add it to a layout. Green
  (`#e8f5e9`/`#2e7d32`) when NVENC is usable; gray (`#f5f5f5`/`#777`)
  otherwise. Clicked → `_show_gpu_report` (existing diagnostic dialog).
- Removed the `self.statusBar()` call from `__init__`. The bottom status
  bar no longer shows up.
- `_show_gpu_report` signature relaxed to `(self, _arg=None)` so it
  accepts both `clicked(bool)` and the prior `mouseDoubleClickEvent` arg.

### Filename pipeline (Phase 7 / 59-char hard limit)

- Add `import naming_utils` at top.
- Remove `from datetime import datetime` (no longer used after the
  rewrite — verify before deleting).
- In `process()`, **replace the entire timestamp + safe_video_name +
  safe_encoder_name + output_filename + output_file construction block**
  with the budget-split pipeline:
  - `ts = naming_utils.timestamp()` (15-char `YYYYMMDD_HHMMSS`)
  - Compute `tail` (`_final{gpu_suffix}.mp4`, `_step{N}{gpu_suffix}.mp4`,
    `_%03d.jpg`, etc.) the same way as before.
  - `fixed = len(ts) + 2 + len(tail)`; `avail = MAX_FILENAME - fixed`;
    `enc_budget = max(3, avail // 3)`; `vid_budget = avail - enc_budget`.
  - `safe_part(encoder_name, enc_budget)`, `safe_part(video_name, vid_budget)`.
  - `clip_to_limit(filename)` as a final guard.
  - `naming_utils.avoid_collision(output_file)` for non-image outputs.
- **Honor `output_collision`** (3-way branch, see Bug 4 fix): `'overwrite'`
  → no-op (ffmpeg `-y` handles it), `'skip'` → check existence, emit
  error_occurred + return if exists, otherwise (`'rename'` default) →
  `avoid_collision`.

### Onboarding & polish (Phase 4 + 5)

- **Step 1-4 bold gray QLabels** above each panel. Style:
  `font-size: 13px; color: #555; font-weight: bold; padding: 4px 2px 2px 2px`.
- **Empty-state hints**:
  - `self.empty_videos_hint` — child of `self.tree_videos.viewport()`,
    centered, faint gray italic. Repositioned in `on_resize` via
    `setGeometry(self.tree_videos.viewport().rect())`.
  - `self.empty_slots_hint` — sibling label in `mode_layout` above
    `sequential_frame`. Visible when `sequential_mode` is on AND no slot
    has text.
  - `_update_empty_hints()` toggles visibility; called from
    `update_video_list`, `on_mode_changed`, `_on_slot_text_changed`.
- **Tooltips on every button**: Select/Delete/Help (file row),
  Add/Edit/Delete/Refresh (preset row), Directory/Open/Start/Stop, GPU
  toggle. Match the spec text exactly so keyboard shortcut hints
  (`(Ctrl+O)`, `(F5)`, `(Esc)`, `(Del)`) appear in the tooltip.
- **Keyboard shortcuts** via `_setup_shortcuts()`:
  - Ctrl+O → `select_videos` (app-wide)
  - F1 → `show_help` (app-wide)
  - F5 → `_on_start_shortcut` → calls `start_render` only if
    `btn_start.isEnabled()` (so disabled-state respected)
  - Esc → `_on_stop_shortcut` → calls `cancel_render` only if
    `btn_cancel.isEnabled()`
  - Del → `delete_videos` with `setContext(Qt.WidgetShortcut)` on
    `tree_videos` so it only fires when that tree has focus
- **Smart Start button** — `_update_start_button_state()`:
  - If `is_rendering`: skip (let the rendering controls govern state).
  - If no videos: disable + tooltip "Add videos first".
  - If no preset (single mode: tree selection / sequential mode: any slot
    has text): disable + tooltip "Pick a preset first".
  - If output dir empty or invalid: disable + tooltip "Choose output
    folder first".
  - Otherwise enable + tooltip "Begin rendering (F5)".
  - Wired to: `update_video_list`, `select_output_directory`,
    `tree_encoders.itemSelectionChanged`, `on_mode_changed`,
    each slot's `currentTextChanged`, end of `setup_ui`.
- **Delete confirmations** (Bug 6 fix counterpart): wrap both delete
  handlers with `QMessageBox.question(... 'Remove N selected items?'
  ... QMessageBox.No)` and early-return on No.
- **Worker thread labels** with per-thread state dict
  (`self._worker_state[i]` dict of `state` / `basename` / `percent` / `error`):
  - `_render_worker_label(idx)` formats: 🟢 Ready / 🟡 Rendering
    `{basename}` ({percent}%) / ✅ Completed `{basename}` /
    ❌ Failed: `{error}` / ⏹ Cancelled.
  - `update_thread_status` parses the existing emitted strings
    (`Idle` / `Processing:` / `Completed` / `Error` / `Cancelled`) into
    state. **Don't change what the worker emits** — only the receiver-side
    interpretation.
  - `update_thread_progress` updates `percent` and re-renders if state is `running`.
  - `on_render_error` captures the actual error message via `sender()`.
  - All workers reset to Ready at the start of every batch in `start_render`.
- **Filename middle-truncation** in `update_video_list`:
  `_truncate_middle(s, limit=45, head=20, tail=20)` — for filenames
  > 45 chars, display `first[:20] + '…' + last[-20:]`. Set the **full
  path** as tooltip on every column of every row.
- **Search bars** above both trees: `QLineEdit` with placeholder
  `"🔍 Search files..."` / `"🔍 Search presets..."` and clear-button
  enabled. Static helper `_filter_tree(tree, query)` does
  case-insensitive substring match across visible columns; thin wrappers
  `_filter_videos` / `_filter_encoders` connect via `textChanged`.
- **Sortable columns**: `setSortingEnabled(True)` on both `tree_videos`
  and `tree_encoders`. Caveat: "No." column sorts lexicographically
  (1, 10, 11, 2, 3...) — not fixed, accept or set numeric sort role.
- **Slot ✕ clear buttons + placeholder**:
  - `self.sequential_clear_btns = []` initialized alongside
    `sequential_combos`.
  - Each slot's QVBoxLayout now contains a horizontal sub-layout with
    the combo + a 20×25 white "✕" QPushButton hidden by default.
    Lambda-bound `clicked` → `combo.setCurrentIndex(0)` (the empty
    placeholder item).
  - `_update_slot_clear_buttons()` toggles visibility based on
    `combo.currentText()` truthiness. Called from `_on_slot_text_changed`.
  - Placeholder text changed from `f'Encoder {i + 1}'` to `'Drop preset here'`.
- **Renames** (display only, internal logic unchanged):
  - `Single Render` radio → `Render Once`
  - `X Render` radio → `Render All Variants`
  - Step 3 label updated to match new naming
  - Filter dropdown shows count: `🕹️ 1vmo Ultimate (78)`. The
    `addItems(current_groups)` line skips Ultimate to avoid the
    pre-existing duplicate. `on_group_changed` strips a trailing `" (N)"`
    suffix before passing to `load_encoders_to_tree`.

### Default X-Render slots (this session's last big change)

- New method `_apply_slot_defaults()`: reads `sequential_slots` (a list
  of preset names) from `self.config`, calls
  `combo.findText(name)` + `combo.setCurrentIndex(idx)` per slot.
  Early-returns if `sequential_slots` is empty.
- Called once in `__init__` immediately after `self.load_encoders_to_tree()`
  so combos are populated before lookup.
- `save_config` now also writes
  `'sequential_slots': [c.currentText() for c in self.sequential_combos]`
  so user changes persist.
- **Local impact: zero** — local config has no `sequential_slots` key
  unless user customizes once, so blank slots remain on local launches.

---

## Bug fixes — one-line summaries

| # | Bug | Fix |
|---|---|---|
| 1 | Trailing `-c:v` overrode preset's codec (libx265 silently became h264) | `_has_vcodec` gate on the default-codec append in both initial and CPU-fallback command builds. `-c:a aac` still always appended. |
| 2 | `gpu_error_action='skip_file'` hung the batch — no signal advanced state | Emit `error_occurred(f'Skipped (GPU failed): ...')` before return so the existing handler decrements active_threads + starts next task |
| 3 | `closeEvent` crashed on None workers (after some completed) | Add `if worker is not None:` guard inside `for worker in self.render_workers:` loop |
| 4 | `output_collision` setting had no effect (always renamed) | Replaced unconditional `avoid_collision` with 3-way branch: `'overwrite'` no-op, `'skip'` → check + emit + return, else (`'rename'`) → avoid_collision |
| 5 | `QThread.started` connections accumulated → double-spawn / RuntimeError | `try: thread.started.disconnect() except TypeError: pass` immediately before each `quit()` in `on_render_completed` and `on_render_error` |
| 6 | Output tree rows matched by completion COUNT — out-of-order completion stamped wrong row | Stamp `worker.tree_item = item` and `worker.task_index = self.current_task_index` in `_start_next_task`. In completion / error handlers, use `getattr(worker, 'tree_item', None)` lookup and `box_index = getattr(worker, 'task_index', self.completed_tasks)` |
| 7 | `output_text` (FFmpeg log) grew unbounded across long batches | `self.output_text.document().setMaximumBlockCount(2000)` immediately after creation |
| 8 | Config files opened with cp1252 — Vietnamese / emoji could fail to round-trip | `encoding='utf-8'` on both `open(self.CONFIG_FILE, ...)` calls. Don't touch ENCODER_FILE — already utf-8. |

---

## Asset changes

### `assets/Encoder.txt`

**Line 100, `9:16 CRF High`** rewritten:

- **Was:** `-vf scale=-2:ih*9/16 -c:v libx264 -crf 16 -preset slow -pix_fmt yuv420p -c:a copy`
  (downscaled to 9/16 of input height regardless of aspect — buggy)
- **Now:** `-vf scale=1080:1920:flags=lanczos,hqdn3d=1.5:1.5:6.0:6.0,unsharp=5:5:1.0:5:5:0.0 -c:v libx264 -crf 16 -preset slow -pix_fmt yuv420p -c:a copy`
  (upscales to TikTok/Reels native 1080×1920 with denoise + sharpen)

Description and details strings updated to match new behavior.

---

## Bundled with the .exe (in `dist/AutoRender/`)

| Path | Purpose |
|---|---|
| `_internal/config_video_renderer.json` | Pre-fills X-Render slots: Clear All / Cycle 10s (4-3-3) 100x Zoom / 80% Center / 9:16 CRF High / Noise Reduction / Volume Normalize / empty / empty. Recipient gets these on first launch; user customization persists thereafter via `save_config`. |
| `README.txt` | User-facing readme: getting started, how to use, key features, common questions, troubleshooting, contact `[ ADAM tele - @YIIII56]`. |

**Important when rebuilding**: `rm -rf dist/AutoRender` wipes README.txt
because PyInstaller doesn't recreate it. Either keep a master copy at
project root and copy it in post-build, OR write a small post-build
script that regenerates both this file and the bundled config.

---

## Known issues — flagged but NOT fixed

### 1. Bug 9 — TOCTOU race in `naming_utils.avoid_collision`

When two input filenames share their first ~22 characters AND multiple
workers start in the same second, the avoid_collision check passes for
both (neither has written yet) → both ffmpeg processes target the same
file → one fails with WinError-style code, the other succeeds.

User saw 1-of-8 batch fail because of this. Diagnosis confirmed by
reproducing the filename construction on identically-prefixed inputs.

**Fix sketch:** make `avoid_collision` atomic via exclusive file create:

```python
def avoid_collision(path):
    candidates = [path] + [...]  # _1, _2, ... _9999
    for candidate in candidates:
        try:
            open(candidate, 'x').close()  # OS-atomic exclusive create
            return candidate
        except FileExistsError:
            continue
    return candidates[-1]
```

Trade-off: leaves a 0-byte placeholder if ffmpeg crashes between
create-and-write. Cosmetic; ffmpeg's `-y` overwrites it normally.

### 2. `-c:a copy` in presets is overridden by trailing `-c:a aac`

Bug 1 only fixed `-c:v`. Audio codec is still unconditionally appended.
Presets that say `-c:a copy` (e.g., several Resolution and Blur presets)
get their audio re-encoded to AAC anyway. Pre-existing behavior, not a
regression. Trivial to fix with a `_has_acodec` helper following the same
pattern as `_has_vcodec`.

### 3. `gblur=sigma=20` in Blur presets is the dominant render bottleneck

`80% Center`, `80% Bottom`, `80% Top`, `80% Height Center`,
`80% Width Center` (line 34-38), and `9:16 Blur*` presets (line 90-92)
all use `gblur=sigma=20`. At sigma 20 the kernel is ~120×120 pixels —
~30 billion multiply-adds per 1080p frame, single-threaded CPU.
Slows the whole 6-slot chain to ~0.16x speed.

**Fix options:**
- Replace `gblur=sigma=20` with `boxblur=20:2` (2 passes ≈ Gaussian via
  central-limit theorem, ~5-10× faster, visually indistinguishable for
  background-blur use case).
- Or reduce sigma to 8-10 (~4× speedup, slightly weaker blur).

Single Encoder.txt edit per preset, no source change needed.

---

## Suggested port order (when you start)

1. **Drop in new files first**: `settings_dialog.py`, `naming_utils.py`.
2. **Imports + `__init__` config keys** in auto_render.py:
   - `from settings_dialog import SettingsDialog`
   - `import naming_utils`
   - Five new attributes from config with defaults.
3. **RenderWorker changes**: ctor params + `_translate_to_nvenc` +
   `_run_ffmpeg_command` + `_has_vcodec` + `batch_stop_requested` signal.
4. **`process()` body rewrite**: filename pipeline (naming_utils) +
   collision branch + GPU/CPU branch + run helper + retry + success/fail
   routing. **This is the biggest single change** — ~80 lines.
5. **Apply Bugs 1-8 in order** as you go through `process()` /
   completion handlers / `closeEvent` / config IO.
6. **UI work**: GPU button refactor, Settings button, toolbar tooltips,
   step labels, search bars, sortable trees, slot ✕ buttons, smart
   Start, keyboard shortcuts, worker-label state dict, empty-state
   hints, middle-truncation.
7. **Renames + filter dropdown count** (Phase 5 polish).
8. **Default slot persistence**: `_apply_slot_defaults` + `save_config`
   merge + `sequential_slots` key.
9. **Asset edit**: `assets/Encoder.txt` line 100 (`9:16 CRF High`).
10. **Build artifacts**: bundled config, README.txt at top of dist.
11. **PyInstaller build** with the recipe below.
12. **Decide on Bug 9 TOCTOU atomicity** (only remaining open issue — gblur swap shipped via [89dcdce] + [2629ffe], `_has_acodec` shipped via Path B [c03433a]).

Most invasive single edit is the `process()` rewrite. Take a backup
before that one specifically. The rest are additive.

---

## Build / zip recipe

```
.venv/Scripts/python.exe -m PyInstaller \
  --name=AutoRender \
  --onedir \
  --windowed \
  --icon=assets/Auto_Render.ico \
  --add-data="assets;assets" \
  --add-data="ffmpeg;ffmpeg" \
  --hidden-import=pynvml \
  --hidden-import=PyQt5.sip \
  --collect-submodules=PyQt5 \
  --noconfirm \
  --clean \
  auto_render.py
```

Then:
```
powershell -Command "Compress-Archive -Path dist/AutoRender -DestinationPath '1vmo-AutoRender-vX.Y.zip' -CompressionLevel Optimal -Force"
```

Watch for these **harmless** warnings (don't block on them):
- `Hidden import 'PyQt5.uic.port_v2.*' not found` — Python 2 compat shims.
- `Hidden import "sip" not found!` — old top-level name; we use `PyQt5.sip`.
- `Library not found: LIBPQ.dll` — PostgreSQL driver, unused.
- `could not find translations with base name 'designer'` — Qt Designer, unused.

Build folder size: ~402 MB. Zip: ~162 MB (40% compression).

---

## Backup files left in this folder (Phase 1)

`auto_render.py.bak`, `auto_render.py.bak2` … `auto_render.py.bak5`,
`assets/Encoder.txt.bak` — checkpoints from each major edit pass.
Combined ~500 KB. Useful if you want to diff specific phases against
each other when porting.
