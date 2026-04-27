"""Settings dialog for the 1vmo Auto Render app.

Reads/writes ``config_video_renderer.json``. Loads the *whole* existing
config so unknown keys (e.g. ``input_files``, ``encoder_options``) round-trip
unchanged. Three tabs — General / Rendering / Advanced — plus OK/Cancel.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QMessageBox,
    QDialogButtonBox,
)


# Defaults — must not change current behavior when applied to a fresh config.
DEFAULTS = {
    "output_dir": "",
    "num_threads": 3,
    "use_gpu": True,
    "gpu_error_action": "retry_cpu",
    "output_collision": "overwrite",
    "show_ffmpeg_command": True,
    "open_output_when_done": False,
    "tour_seen": True,
    # Phase 2.5b GPU pipeline keys per ADR-0007 D8.
    "gpu_enabled": False,
    "gpu_codec": "h264_nvenc",
    "gpu_preset": "p4",
    "gpu_max_concurrent": 2,
    "gpu_container_override": None,
    "gpu_max_quality_mode": False,
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
        self.use_gpu_check.setChecked(bool(self._get("use_gpu")))
        self.use_gpu_check.setToolTip(
            "Mirrors the toolbar 'Use GPU (NVENC)' checkbox. "
            "Effective only if a supported NVIDIA GPU is detected."
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

    def _build_gpu_pipeline_tab(self):
        """Build the GPU Pipeline tab with NVENC controls per ADR-0007 D2/D3/D4/D6/D7/D8."""
        page = QWidget()
        form = QFormLayout(page)

        # Master enable (canonical key per ADR-0007 D8; mirrors legacy use_gpu)
        self.gpu_enabled_check = QCheckBox("Enable GPU encoding (NVENC)")
        self.gpu_enabled_check.setChecked(bool(self._get("gpu_enabled")))
        form.addRow("", self.gpu_enabled_check)

        # Codec dropdown per ADR-0007 D4
        self.gpu_codec_combo = QComboBox()
        for value, label in [
            ("h264_nvenc", "H.264 (NVENC) - fast, universal"),
            ("hevc_nvenc", "HEVC (NVENC) - smaller files"),
            ("av1_nvenc", "AV1 (NVENC) - smallest, experimental"),
        ]:
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

    # --- save --------------------------------------------------------------

    def _on_ok(self):
        self.config["output_dir"] = self.output_dir_edit.text().strip()
        self.config["num_threads"] = self.threads_spin.value()
        self.config["use_gpu"] = self.use_gpu_check.isChecked()
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
        if self._tour_reset_flag:
            self.config["tour_seen"] = False
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Could not save settings: {exc}")
            return
        self.accept()
