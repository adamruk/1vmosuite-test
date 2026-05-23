"""Settings dialog for the 1vmo Auto Render app.

Reads/writes ``config_video_renderer.json``. Loads the *whole* existing
config so unknown keys (e.g. ``input_files``, ``encoder_options``) round-trip
unchanged. Three tabs — General / Rendering / Advanced — plus OK/Cancel.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import APP_DEFAULTS

# Defaults — must not change current behavior when applied to a fresh config.
# Six fields below source from `core.config.AppDefaults` (single source of
# truth). The remaining fields are dialog-specific and stay as literals.
# `use_gpu` is the legacy alias of `gpu_enabled` (kept in sync at save time
# by SettingsDialog._on_ok); the literal `True` here is the pre-existing
# value and is left untouched in this scope.
DEFAULTS = {
    "output_dir": "",
    "num_threads": 3,
    "use_gpu": True,
    "gpu_error_action": APP_DEFAULTS.gpu_error_action,
    "output_collision": APP_DEFAULTS.output_collision,
    "show_ffmpeg_command": True,
    "open_output_when_done": False,
    "tour_seen": True,
    # Phase 2.5b GPU pipeline keys per ADR-0007 D8.
    "gpu_enabled": APP_DEFAULTS.gpu_enabled,
    "gpu_codec": APP_DEFAULTS.gpu_codec,
    "gpu_preset": APP_DEFAULTS.gpu_preset,
    "gpu_max_concurrent": APP_DEFAULTS.gpu_max_concurrent,
    "gpu_container_override": None,
    "gpu_max_quality_mode": False,
    # Phase 3.1 — local persistent queue. True means the in-progress
    # batch is saved to user_data_dir and offered for resume on the
    # next launch (if the app exits during a render). False disables
    # the feature; no queue.json is written. Default True preserves
    # the safer behavior for users who don't visit Settings.
    "queue_persistence_enabled": True,
    # Phase 3.2 — local-only originality / quality scoring. Default
    # OFF so a user who has not opted in never pays the VMAF cost.
    # Axes default to vmaf + phash; SSIM is opt-in. Max parallel
    # capped at 1 because libvmaf is internally multi-core already.
    "scoring_auto_enabled": False,
    "scoring_default_axes": ["vmaf", "phash"],
    "scoring_max_parallel": 1,
    "scoring_phash_frames": 20,
}


class SettingsDialog(QDialog):
    GPU_ERROR_OPTIONS = [
        ("retry_cpu", "Retry on CPU"),
        ("skip_file", "Skip file"),
    ]
    COLLISION_OPTIONS = [
        ("overwrite", "Overwrite"),
        ("rename", "Rename with _1, _2..."),
        ("skip", "Skip"),
    ]

    def __init__(self, parent, config_path):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self._tour_reset_flag = False

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_general_tab(), "General")
        self.tabs.addTab(self._build_rendering_tab(), "Rendering")
        self.tabs.addTab(self._build_advanced_tab(), "Advanced")
        self.tabs.addTab(self._build_gpu_pipeline_tab(), "GPU Pipeline")
        # v3.9 F-003 fix: wire bidirectional sync between the Rendering-tab
        # legacy `use_gpu_check` and the canonical GPU-Pipeline-tab
        # `gpu_enabled_check`. Without this, toggling one tab's checkbox
        # would silently lose its value on OK because _on_ok writes from
        # only one source. blockSignals() prevents the connections from
        # recursing infinitely.

        def _sync_from_use_gpu(state):
            self.gpu_enabled_check.blockSignals(True)
            self.gpu_enabled_check.setChecked(self.use_gpu_check.isChecked())
            self.gpu_enabled_check.blockSignals(False)

        def _sync_from_gpu_enabled(state):
            self.use_gpu_check.blockSignals(True)
            self.use_gpu_check.setChecked(self.gpu_enabled_check.isChecked())
            self.use_gpu_check.blockSignals(False)

        self.use_gpu_check.stateChanged.connect(_sync_from_use_gpu)
        self.gpu_enabled_check.stateChanged.connect(_sync_from_gpu_enabled)
        # Phase 3.2 — local scoring tab (5th, last). All controls
        # default-OFF / safe values so a user who doesn't open it
        # sees zero behavior change vs Phase 3.1.
        self.tabs.addTab(self._build_scoring_tab(), "Scoring")
        layout.addWidget(self.tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # --- config IO ---------------------------------------------------------

    def _load_config(self):
        if self.config_path.is_file():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _get(self, key):
        return self.config.get(key, DEFAULTS.get(key))

    # --- tab builders ------------------------------------------------------

    def _build_general_tab(self):
        page = QWidget()
        form = QFormLayout(page)

        dir_row = QHBoxLayout()
        self.output_dir_edit = QLineEdit(self._get("output_dir") or "")
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_output_dir)
        dir_row.addWidget(self.output_dir_edit)
        dir_row.addWidget(browse_btn)
        form.addRow("Default output directory:", dir_row)

        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 8)
        self.threads_spin.setValue(int(self._get("num_threads") or 3))
        self.threads_spin.setToolTip(
            "Number of parallel encode workers. Takes effect after restart."
        )
        form.addRow("Worker thread count:", self.threads_spin)

        tour_btn = QPushButton("Show first-launch tour again")
        tour_btn.clicked.connect(self._reset_tour)
        form.addRow("", tour_btn)

        return page

    def _build_rendering_tab(self):
        page = QWidget()
        form = QFormLayout(page)

        self.use_gpu_check = QCheckBox("Use GPU when available")
        # v3.9 F-003: prefer the canonical `gpu_enabled` key for the
        # initial value; fall back to the legacy `use_gpu` alias if
        # only the old key is present. This makes the Rendering-tab
        # checkbox reflect the same state the GPU Pipeline tab will
        # show, regardless of which key the config file used.
        initial_gpu = self._get("gpu_enabled")
        if initial_gpu is None:
            initial_gpu = self._get("use_gpu")
        self.use_gpu_check.setChecked(bool(initial_gpu))
        self.use_gpu_check.setToolTip(
            "Mirrors the GPU Pipeline tab's 'Enable GPU encoding' toggle. "
            "Changes here propagate to that tab automatically on OK."
        )
        form.addRow("", self.use_gpu_check)

        self.gpu_error_combo = QComboBox()
        for value, label in self.GPU_ERROR_OPTIONS:
            self.gpu_error_combo.addItem(label, value)
        self._set_combo_data(self.gpu_error_combo, self._get("gpu_error_action"))
        form.addRow("On GPU error:", self.gpu_error_combo)

        self.collision_combo = QComboBox()
        for value, label in self.COLLISION_OPTIONS:
            self.collision_combo.addItem(label, value)
        self._set_combo_data(self.collision_combo, self._get("output_collision"))
        form.addRow("If output file exists:", self.collision_combo)

        return page

    def _build_advanced_tab(self):
        page = QWidget()
        form = QFormLayout(page)

        self.show_cmd_check = QCheckBox("Show ffmpeg command in log")
        self.show_cmd_check.setChecked(bool(self._get("show_ffmpeg_command")))
        form.addRow("", self.show_cmd_check)

        self.open_done_check = QCheckBox("Open output folder when batch finishes")
        self.open_done_check.setChecked(bool(self._get("open_output_when_done")))
        form.addRow("", self.open_done_check)

        # Phase 3.1 — local persistent queue toggle.
        self.queue_persist_check = QCheckBox("Save queue for resume on next launch")
        self.queue_persist_check.setChecked(
            bool(self._get("queue_persistence_enabled"))
        )
        self.queue_persist_check.setToolTip(
            "When enabled, an interrupted render batch is saved locally and "
            "you'll be offered the option to resume it the next time you "
            "open the app. The queue file lives next to your config and is "
            "never sent anywhere — everything stays on this computer."
        )
        form.addRow("", self.queue_persist_check)

        reset_btn = QPushButton("Reset all settings to defaults")
        reset_btn.clicked.connect(self._reset_to_defaults)
        form.addRow("", reset_btn)

        return page

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _set_combo_data(combo, value):
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _browse_output_dir(self):
        current = self.output_dir_edit.text() or os.getcwd()
        d = QFileDialog.getExistingDirectory(
            self, "Select Default Output Directory", current
        )
        if d:
            self.output_dir_edit.setText(d)

    def _reset_tour(self):
        self._tour_reset_flag = True
        QMessageBox.information(
            self,
            "Tour Reset",
            "The first-launch tour will appear again on the next launch.",
        )

    def _reset_to_defaults(self):
        reply = QMessageBox.question(
            self,
            "Reset settings",
            "Reset all settings to their default values? Current values will be lost.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.output_dir_edit.setText(DEFAULTS["output_dir"])
        self.threads_spin.setValue(DEFAULTS["num_threads"])
        self.use_gpu_check.setChecked(DEFAULTS["use_gpu"])
        self._set_combo_data(self.gpu_error_combo, DEFAULTS["gpu_error_action"])
        self._set_combo_data(self.collision_combo, DEFAULTS["output_collision"])
        self.show_cmd_check.setChecked(DEFAULTS["show_ffmpeg_command"])
        self.open_done_check.setChecked(DEFAULTS["open_output_when_done"])
        self.queue_persist_check.setChecked(DEFAULTS["queue_persistence_enabled"])
        # Phase 3.2 — restore scoring defaults.
        self.scoring_auto_check.setChecked(DEFAULTS["scoring_auto_enabled"])
        default_axes = DEFAULTS["scoring_default_axes"]
        self.scoring_axis_vmaf_check.setChecked("vmaf" in default_axes)
        self.scoring_axis_phash_check.setChecked("phash" in default_axes)
        self.scoring_axis_ssim_check.setChecked("ssim" in default_axes)
        self.scoring_max_parallel_spin.setValue(DEFAULTS["scoring_max_parallel"])
        self.scoring_phash_frames_spin.setValue(DEFAULTS["scoring_phash_frames"])

    def _build_gpu_pipeline_tab(self):
        """Build the GPU Pipeline tab with NVENC controls per ADR-0007 D2/D3/D4/D6/D7/D8."""
        page = QWidget()
        form = QFormLayout(page)

        # Master enable (canonical key per ADR-0007 D8; mirrors legacy use_gpu)
        self.gpu_enabled_check = QCheckBox("Enable GPU encoding (NVENC)")
        self.gpu_enabled_check.setChecked(bool(self._get("gpu_enabled")))
        form.addRow("", self.gpu_enabled_check)

        # Codec dropdown per ADR-0007 D4.
        # Phase 2d production-hardening fix (Issue 8): hide codecs the
        # host GPU does not support. AV1 NVENC is Ada/Blackwell only;
        # offering it on an Ampere RTX 3050 (or any non-Ada card) leads
        # to ffmpeg failures at encode time. We read `gpu_caps` from
        # the parent VideoRendererTool — it is populated once at
        # startup by `gpu_detect.detect(FFMPEG_PATH)` and never
        # mutated. If gpu_caps is unavailable (e.g. tests instantiate
        # the dialog standalone) we leave the dropdown unfiltered so
        # the prior behaviour is preserved.
        gpu_caps = getattr(self.parent(), "gpu_caps", None)
        h264_ok = getattr(gpu_caps, "h264_available", True) if gpu_caps else True
        hevc_ok = getattr(gpu_caps, "hevc_available", True) if gpu_caps else True
        av1_ok = getattr(gpu_caps, "av1_available", True) if gpu_caps else True
        codec_choices = []
        if h264_ok:
            codec_choices.append(("h264_nvenc", "H.264 (NVENC) - fast, universal"))
        if hevc_ok:
            codec_choices.append(("hevc_nvenc", "HEVC (NVENC) - smaller files"))
        if av1_ok:
            codec_choices.append(("av1_nvenc", "AV1 (NVENC) - smallest, Ada+ only"))
        if not codec_choices:
            # Defensive: every NVENC codec disabled by gpu_caps. Fall
            # back to the full original list so the dialog still has
            # *something* selectable. AppDefaults.gpu_codec ("h264_nvenc")
            # remains the canonical default.
            codec_choices = [
                ("h264_nvenc", "H.264 (NVENC) - fast, universal"),
                ("hevc_nvenc", "HEVC (NVENC) - smaller files"),
                ("av1_nvenc", "AV1 (NVENC) - smallest, experimental"),
            ]
        self.gpu_codec_combo = QComboBox()
        for value, label in codec_choices:
            self.gpu_codec_combo.addItem(label, value)
        self._set_combo_data(self.gpu_codec_combo, self._get("gpu_codec"))
        form.addRow("Codec:", self.gpu_codec_combo)

        # Preset dropdown per ADR-0007 D2 (p1-p7)
        self.gpu_preset_combo = QComboBox()
        for p_value in ["p1", "p2", "p3", "p4", "p5", "p6", "p7"]:
            self.gpu_preset_combo.addItem(p_value, p_value)
        self._set_combo_data(self.gpu_preset_combo, self._get("gpu_preset"))
        form.addRow("Preset (p1=fast, p7=quality):", self.gpu_preset_combo)

        # Concurrent sessions per ADR-0007 D6
        self.gpu_max_concurrent_spin = QSpinBox()
        self.gpu_max_concurrent_spin.setRange(1, 8)
        self.gpu_max_concurrent_spin.setValue(int(self._get("gpu_max_concurrent") or 2))
        form.addRow("Max concurrent NVENC sessions:", self.gpu_max_concurrent_spin)

        # Container override per ADR-0007 D4
        self.gpu_container_combo = QComboBox()
        self.gpu_container_combo.addItem("Use codec default (mp4 / mkv)", None)
        for ext in ["mp4", "mkv", "mov"]:
            self.gpu_container_combo.addItem(f".{ext}", ext)
        current_override = self._get("gpu_container_override")
        idx = self.gpu_container_combo.findData(current_override)
        if idx >= 0:
            self.gpu_container_combo.setCurrentIndex(idx)
        form.addRow("Container override:", self.gpu_container_combo)

        # Max-quality mode per ADR-0007 D7 (multipass=2 + p7)
        self.gpu_max_quality_check = QCheckBox(
            "Max quality mode (multipass=2; slower but higher VMAF)"
        )
        self.gpu_max_quality_check.setChecked(bool(self._get("gpu_max_quality_mode")))
        form.addRow("", self.gpu_max_quality_check)

        return page

    def _build_scoring_tab(self):
        """Phase 3.2 — local-only originality / quality scoring tab.

        All defaults preserve current behavior: auto-scoring OFF,
        VMAF + pHash selected (only fired when auto-score is ON),
        max parallel 1.
        """
        page = QWidget()
        form = QFormLayout(page)

        # Master toggle — DEFAULT OFF.
        self.scoring_auto_check = QCheckBox(
            "Score every render automatically when it finishes"
        )
        self.scoring_auto_check.setChecked(bool(self._get("scoring_auto_enabled")))
        self.scoring_auto_check.setToolTip(
            "When ON, after each successful render the app spawns a "
            "background scoring pass for the configured axes. Cost "
            "varies by axis — VMAF can add ~30-60s of CPU per "
            "1-minute 1080p clip; pHash adds ~3-8s; SSIM ~5-10s. "
            "Scoring runs on its own thread pool and never blocks "
            "or slows the render itself. Off by default."
        )
        form.addRow("", self.scoring_auto_check)

        # Axes selection. pHash + VMAF default on (per design doc);
        # SSIM opt-in.
        axes = self._get("scoring_default_axes") or ["vmaf", "phash"]
        axes_lower = [str(a).lower() for a in axes]

        self.scoring_axis_vmaf_check = QCheckBox(
            "VMAF (visual fidelity; needs libvmaf in bundled ffmpeg)"
        )
        self.scoring_axis_vmaf_check.setChecked("vmaf" in axes_lower)

        self.scoring_axis_phash_check = QCheckBox(
            "pHash distance (originality — higher = more different from source)"
        )
        self.scoring_axis_phash_check.setChecked("phash" in axes_lower)

        self.scoring_axis_ssim_check = QCheckBox(
            "SSIM (structural similarity — fast, ffmpeg-native)"
        )
        self.scoring_axis_ssim_check.setChecked("ssim" in axes_lower)

        # Layout: vertical column of axis checkboxes under one label.
        axes_col = QVBoxLayout()
        axes_col.setContentsMargins(0, 0, 0, 0)
        axes_col.addWidget(self.scoring_axis_vmaf_check)
        axes_col.addWidget(self.scoring_axis_phash_check)
        axes_col.addWidget(self.scoring_axis_ssim_check)
        axes_holder = QWidget()
        axes_holder.setLayout(axes_col)
        form.addRow("Axes:", axes_holder)

        # Max parallel scoring (1-4, default 1).
        self.scoring_max_parallel_spin = QSpinBox()
        self.scoring_max_parallel_spin.setRange(1, 4)
        try:
            self.scoring_max_parallel_spin.setValue(
                int(self._get("scoring_max_parallel") or 1)
            )
        except (TypeError, ValueError):
            self.scoring_max_parallel_spin.setValue(1)
        self.scoring_max_parallel_spin.setToolTip(
            "How many scoring jobs may run at the same time. "
            "Default 1. libvmaf is already multi-core internally; "
            "raising this above 1 mostly thrashes cache."
        )
        form.addRow("Max parallel scoring jobs:", self.scoring_max_parallel_spin)

        # pHash sampling density (10-60 frames).
        self.scoring_phash_frames_spin = QSpinBox()
        self.scoring_phash_frames_spin.setRange(5, 120)
        try:
            self.scoring_phash_frames_spin.setValue(
                int(self._get("scoring_phash_frames") or 20)
            )
        except (TypeError, ValueError):
            self.scoring_phash_frames_spin.setValue(20)
        self.scoring_phash_frames_spin.setToolTip(
            "How many equally-spaced frame pairs are sampled for "
            "the pHash distance. 20 is enough for short clips; "
            "raise to 40-60 for long-form content."
        )
        form.addRow("pHash sample frames:", self.scoring_phash_frames_spin)

        return page

    # --- save --------------------------------------------------------------

    def _on_ok(self):
        self.config["output_dir"] = self.output_dir_edit.text().strip()
        self.config["num_threads"] = self.threads_spin.value()
        # v3.9 F-003 fix: the canonical GPU master is `gpu_enabled_check`
        # (GPU Pipeline tab, ADR-0007 D8). The Rendering-tab
        # `use_gpu_check` is a legacy mirror only — DO NOT write from
        # it here. Previously this line ran before the GPU-Pipeline
        # write below, which meant a user toggling the Rendering-tab
        # checkbox while the GPU-Pipeline checkbox stayed at its load-
        # time value would have their change silently reverted. Both
        # `gpu_enabled` and the `use_gpu` legacy alias are now written
        # from a single source below.
        self.config["gpu_error_action"] = self.gpu_error_combo.currentData()
        self.config["output_collision"] = self.collision_combo.currentData()
        self.config["show_ffmpeg_command"] = self.show_cmd_check.isChecked()
        self.config["open_output_when_done"] = self.open_done_check.isChecked()
        # Phase 2.5b GPU pipeline writes per ADR-0007 D8
        self.config["gpu_enabled"] = self.gpu_enabled_check.isChecked()
        self.config["use_gpu"] = self.gpu_enabled_check.isChecked()  # legacy alias
        self.config["gpu_codec"] = self.gpu_codec_combo.currentData()
        self.config["gpu_preset"] = self.gpu_preset_combo.currentData()
        self.config["gpu_max_concurrent"] = self.gpu_max_concurrent_spin.value()
        self.config["gpu_container_override"] = self.gpu_container_combo.currentData()
        self.config["gpu_max_quality_mode"] = self.gpu_max_quality_check.isChecked()
        # Phase 3.1 — persist queue-save toggle
        self.config["queue_persistence_enabled"] = self.queue_persist_check.isChecked()
        # Phase 3.2 — persist scoring settings.
        self.config["scoring_auto_enabled"] = self.scoring_auto_check.isChecked()
        chosen_axes = []
        if self.scoring_axis_vmaf_check.isChecked():
            chosen_axes.append("vmaf")
        if self.scoring_axis_phash_check.isChecked():
            chosen_axes.append("phash")
        if self.scoring_axis_ssim_check.isChecked():
            chosen_axes.append("ssim")
        self.config["scoring_default_axes"] = chosen_axes
        self.config["scoring_max_parallel"] = self.scoring_max_parallel_spin.value()
        self.config["scoring_phash_frames"] = self.scoring_phash_frames_spin.value()
        if self._tour_reset_flag:
            self.config["tour_seen"] = False
        # v3.9 F-004 fix: route through core.atomic_write.save_json_atomic
        # so a crash mid-write cannot corrupt config_video_renderer.json.
        # The old raw `open().write()` left a half-written file on
        # power loss / disk-full; the user lost ALL settings on the
        # next launch when json.load() returned a parse error. The
        # atomic-write helper writes to <path>.tmp then os.replace()s
        # over the canonical file and rotates the previous version to
        # <path>.bak — same contract used by queue_store + score_store.
        try:
            from core.atomic_write import save_json_atomic

            save_json_atomic(Path(self.config_path), self.config)
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Could not save settings: {exc}")
            return
        self.accept()
