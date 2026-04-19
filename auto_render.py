# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'Code AutoRender.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import re
import json
from typing import List, Dict, Any, Optional
import tempfile
import requests
import shutil
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QTreeWidget, QTreeWidgetItem, QSpinBox, QFileDialog, QTextEdit, QFrame, QMessageBox, QDialog, QDialogButtonBox, QLineEdit, QComboBox, QRadioButton, QSizePolicy
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QIcon
from help_dialog import HelpDialog
from updater import DriveUpdater
import gpu_detect
from core import config as core_config
from core import file_picker as core_file_picker
def resource_path(relative_path):
    """Lấy đường dẫn tuyệt đối cho tài nguyên, hoạt động cả khi chạy từ source và từ file exe"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath('.')
    return os.path.join(base_path, relative_path)
class RenderWorker(QObject):
    progress_updated = pyqtSignal(int, int)
    status_updated = pyqtSignal(int, str)
    output_updated = pyqtSignal(str)
    render_completed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    def __init__(self, video_path: str, encoder_names: List[str], thread_index: int, ffmpeg_path: str, output_dir: str, encoder_params_list: List[List[str]]):
        super().__init__()
        self.video_path = video_path
        self.encoder_names = encoder_names
        self.thread_index = thread_index
        self.ffmpeg_path = ffmpeg_path
        self.output_dir = output_dir
        self.encoder_params_list = encoder_params_list
        self.is_cancelled = False
    def process(self):
        current_input = self.video_path
        current_output = None
        final_output = None
        try:
            for i, (encoder_name, encoder_params) in enumerate(zip(self.encoder_names, self.encoder_params_list)):
                if not encoder_name:
                    continue
                progress_info = f'Step {i + 1}/{len(self.encoder_names)}'
                self.status_updated.emit(self.thread_index, f'Processing: {os.path.basename(current_input)} with {encoder_name} ({progress_info})')
                self.progress_updated.emit(self.thread_index, 0)
                timestamp = datetime.now().strftime('%y%m%d_%H%M%S')
                video_name = os.path.splitext(os.path.basename(self.video_path))[0]
                encoder_parts = encoder_name.split('|', 1)
                encoder_name = encoder_parts[1] if len(encoder_parts) > 1 else encoder_name
                safe_video_name = ''.join((c for c in video_name if c.isalnum() or c in [' ', '-', '_']))
                safe_encoder_name = ''.join((c for c in encoder_name if c.isalnum() or c in [' ', '-', '_']))
                is_image_encoder = any((param in ['-f', 'image2'] for param in encoder_params))
                if i == len(self.encoder_names) - 1:
                    if is_image_encoder:
                        output_filename = f'{timestamp}_{safe_encoder_name}_{safe_video_name}_%03d.jpg'
                    else:
                        output_filename = f'{timestamp}_{safe_encoder_name}_{safe_video_name}_final.mp4'
                else:
                    if is_image_encoder:
                        output_filename = f'{timestamp}_{safe_encoder_name}_{safe_video_name}_step{i + 1}_%03d.jpg'
                    else:
                        output_filename = f'{timestamp}_{safe_encoder_name}_{safe_video_name}_step{i + 1}.mp4'
                output_file = os.path.join(self.output_dir, output_filename)
                command = [str(self.ffmpeg_path), '-i', str(Path(current_input))] + encoder_params
                if not is_image_encoder:
                    command.extend(['-c:v', 'libx264', '-c:a', 'aac'])
                command.extend(['-y', str(Path(output_file))])
                self.output_updated.emit(f'\n[Thread {self.thread_index + 1}] {progress_info}: Processing {os.path.basename(current_input)} with {encoder_name}\n')
                self.output_updated.emit(f"Command: {' '.join((str(x) for x in command))}\n\n")
                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.dwFlags |= subprocess.STARTF_USESTDHANDLES
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, encoding='utf-8', errors='replace')
                duration = None
                time = 0
                while True:
                    if self.is_cancelled:
                        process.terminate()
                        process.wait()
                        self.status_updated.emit(self.thread_index, 'Cancelled')
                        self.progress_updated.emit(self.thread_index, 0)
                        return
                    line = process.stderr.readline()
                    if not line and process.poll() is not None:
                        if process.returncode == 0 and (not self.is_cancelled):
                            self.status_updated.emit(self.thread_index, f'Completed Step {i + 1}/{len(self.encoder_names)}')
                            self.progress_updated.emit(self.thread_index, 100)
                            self.output_updated.emit(f'\n[Thread {self.thread_index + 1}] Completed Step {i + 1}/{len(self.encoder_names)}: {os.path.basename(current_input)} with {encoder_name}\n')
                            if current_input!= self.video_path:
                                try:
                                    os.remove(current_input)
                                except:
                                    pass
                            current_input = output_file
                            current_output = output_file
                            if i == len(self.encoder_names) - 1:
                                final_output = output_filename
                        else:
                            error_msg = f'Error processing {os.path.basename(current_input)} with {encoder_name} (Step {i + 1}/{len(self.encoder_names)}): Return code {process.returncode}'
                            self.error_occurred.emit(error_msg)
                            self.status_updated.emit(self.thread_index, 'Error')
                            self.progress_updated.emit(self.thread_index, 0)
                            return
                        break
                    if line:
                        self.output_updated.emit(line)
                        if duration is None and 'Duration:' in line:
                            duration_match = re.search('Duration: (\\d{2}):(\\d{2}):(\\d{2})', line)
                            if duration_match:
                                h, m, s = map(int, duration_match.groups())
                                duration = h * 3600 + m * 60 + s
                        time_match = re.search('time=(\\d{2}):(\\d{2}):(\\d{2})', line)
                        if time_match and duration:
                            h, m, s = map(int, time_match.groups())
                            time = h * 3600 + m * 60 + s
                            progress = min(int(time / duration * 100), 100)
                            self.progress_updated.emit(self.thread_index, progress)
            if final_output:
                self.render_completed.emit(final_output)
        except Exception as e:
            error_msg = f'Error processing {os.path.basename(current_input)}: {str(e)}'
            self.error_occurred.emit(error_msg)
            self.status_updated.emit(self.thread_index, 'Error')
            self.progress_updated.emit(self.thread_index, 0)
class VideoRendererTool(QMainWindow):
    def __init__(self, app_name: str='1vmo Auto Render'):
        super().__init__()
        self.app_name = app_name
        self.updater = DriveUpdater()
        self.current_version = self.updater._load_current_version('1vmo Auto Render')
        if self.current_version is None:
            self.current_version = '3.1'
            self.updater._save_current_version(self.current_version, '1vmo Auto Render')
        self.current_assets_version = self.updater._load_current_version('1vmo Auto Render Assets')
        if self.current_assets_version is None:
            self.current_assets_version = '1.0'
            self.updater._save_current_version(self.current_assets_version, '1vmo Auto Render Assets')
        self.setWindowTitle(f'{self.app_name} v{self.current_version} (Assets v{self.current_assets_version})')
        self.setGeometry(100, 100, 1600, 900)
        # Allow resize and maximize — set a reasonable minimum so layouts don't
        # collapse below their designed size, and use resize() for initial geometry.
        self.setMinimumSize(1600, 900)
        self.resize(1600, 900)
        self.updater.check_and_update('1vmo Auto Render')
        self.updater.check_and_update('1vmo Auto Render Assets')
        try:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'Auto_Render.ico')
            if os.path.exists(icon_path):
                app_icon = QIcon(icon_path)
                self.setWindowIcon(app_icon)
                QApplication.setWindowIcon(app_icon)
                if os.name == 'nt':
                    import ctypes
                    myappid = f'1vmo.Auto.Render.v{self.current_version}'
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception as e:
            print(f'Error setting icon: {str(e)}')
        self.videos = []
        self.output_directory = ''
        self.encoder_options = []
        self.selected_encoders = []
        self.encoder_params = {}
        self.output_mapping = {}
        self.is_rendering = False
        self.num_threads = 3
        self.sequential_mode = False
        self.sequential_encoders = [None] * 5
        self.SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
        self.FFMPEG_PATH = self.SCRIPT_DIR / 'ffmpeg' / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
        self.FFPROBE_PATH = self.SCRIPT_DIR / 'ffmpeg' / ('ffprobe.exe' if os.name == 'nt' else 'ffprobe')
        self.CONFIG_FILE = self.SCRIPT_DIR / 'config_video_renderer.json'
        self.ENCODER_FILE = self.SCRIPT_DIR / 'assets' / 'Encoder.txt'
        self._check_dependencies()

        # Phase 1: detect NVENC capabilities once at startup. Cached on
        # self.gpu_caps for UI and (Phase 2) encoder filter logic.
        self.gpu_caps = gpu_detect.detect(self.FFMPEG_PATH)

        self.config = self.load_config()
        self.num_threads = self.config.get('num_threads', 3)
        self.encoder_options = self.load_encoder_options()
        self.setup_ui()
        self.setup_style()

        # Surface GPU status in the built-in QMainWindow status bar.
        self._init_gpu_status_bar()
        ultimate_dir = self.SCRIPT_DIR / '🕹️ 1vmo Ultimate'
        if ultimate_dir.exists():
            self.output_directory = str(ultimate_dir)
            self.dir_label.setText(f'Output Directory: {self.output_directory}')
        else:
            last_output = self.config.get('output_dir', '')
            if last_output and os.path.isdir(last_output):
                    self.output_directory = last_output
                    self.dir_label.setText(f'Output Directory: {self.output_directory}')
        last_videos = self.config.get('input_files', [])
        if last_videos:
            valid_videos = [video for video in last_videos if os.path.isfile(video)]
            if valid_videos:
                self.videos = valid_videos
                self.update_video_list()
                self.btn_delete.setEnabled(True)
        self.load_encoders_to_tree()
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        top_frame = QFrame(objectName='top_frame')
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(5, 5, 5, 5)
        top_layout.setSpacing(5)
        input_frame = QFrame(objectName='input_frame')
        input_frame.setFrameStyle(QFrame.StyledPanel)
        input_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        input_frame.setMinimumWidth(780)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setSpacing(2)
        input_layout.setContentsMargins(5, 2, 5, 2)
        config_frame = QFrame(objectName='config_frame')
        config_frame.setFrameStyle(QFrame.StyledPanel)
        config_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        config_frame.setMinimumWidth(780)
        config_layout = QVBoxLayout(config_frame)
        config_layout.setSpacing(2)
        config_layout.setContentsMargins(5, 2, 5, 2)
        top_layout.addWidget(input_frame)
        top_layout.addWidget(config_frame)
        bottom_frame = QFrame(objectName='bottom_frame')
        bottom_frame.setFrameStyle(QFrame.StyledPanel)
        bottom_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        bottom_frame.setMinimumHeight(450)
        bottom_layout = QHBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(5, 5, 5, 5)
        bottom_layout.setSpacing(5)
        progress_frame = QFrame(objectName='progress_frame')
        progress_frame.setFrameStyle(QFrame.StyledPanel)
        progress_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        progress_frame.setMinimumWidth(780)
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setSpacing(2)
        progress_layout.setContentsMargins(5, 2, 5, 2)
        output_frame = QFrame(objectName='output_frame')
        output_frame.setFrameStyle(QFrame.StyledPanel)
        output_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        output_frame.setMinimumWidth(780)
        output_layout = QVBoxLayout(output_frame)
        output_layout.setSpacing(5)
        output_layout.setContentsMargins(5, 5, 5, 5)
        bottom_layout.addWidget(progress_frame)
        bottom_layout.addWidget(output_frame)
        main_layout.addWidget(top_frame)
        main_layout.addWidget(bottom_frame)
        video_controls = QHBoxLayout()
        select_btn = self.create_video_button('📥 Select (0)', self.select_videos, '#e3f2fd', '#1976d2', '#bbdefb')
        select_btn.setObjectName('select_btn')
        delete_btn = self.create_video_button('🗑️ Delete', self.delete_videos, '#ffcdd2', '#c62828', '#ef9a9a', delete=True)
        delete_btn.setEnabled(False)
        self.btn_delete = delete_btn
        video_controls.addWidget(select_btn)
        video_controls.addWidget(delete_btn)
        video_controls.addStretch()
        help_btn = self.create_video_button('❓ Help', self.show_help, '#e3f2fd', '#1976d2', '#bbdefb')
        video_controls.addWidget(help_btn)
        input_layout.addLayout(video_controls)
        self.tree_videos = QTreeWidget()
        self.tree_videos.setHeaderLabels(['No.', 'Filename', 'Duration', 'Resolution'])
        self.tree_videos.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree_videos.setAlternatingRowColors(True)
        self.tree_videos.header().setDefaultAlignment(Qt.AlignCenter)
        input_layout.addWidget(self.tree_videos)
        encoder_controls = QHBoxLayout()
        add_btn = self.create_video_button('♻️ Add', self.add_encoder, '#e3f2fd', '#1976d2', '#bbdefb')
        edit_btn = self.create_video_button('🛠️ Edit', self.edit_encoder, '#fff3e0', '#e65100', '#ffe0b2')
        del_btn = self.create_video_button('🗑️ Delete', self.delete_encoder, '#ffcdd2', '#c62828', '#ef9a9a', delete=True)
        update_btn = self.create_video_button('🔄 Refresh', self.reload_all, '#e8f5e9', '#2e7d32', '#c8e6c9')
        self.group_combo = QComboBox()
        self.group_combo.setFixedWidth(150)
        self.group_combo.setFixedHeight(25)
        self.group_combo.addItem('🕹️ 1vmo Ultimate')
        self.group_combo.addItem('All Groups')
        self.group_combo.currentTextChanged.connect(self.on_group_changed)
        encoder_controls.addWidget(add_btn)
        encoder_controls.addWidget(edit_btn)
        encoder_controls.addWidget(del_btn)
        encoder_controls.addWidget(update_btn)
        encoder_controls.addStretch()
        encoder_controls.addWidget(QLabel('Filter'))
        encoder_controls.addWidget(self.group_combo)
        config_layout.addLayout(encoder_controls)
        self.tree_encoders = QTreeWidget()
        self.tree_encoders.setHeaderLabels(['No.', 'Group', 'Name', 'Description', 'Details'])
        self.tree_encoders.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree_encoders.setAlternatingRowColors(True)
        self.tree_encoders.header().setDefaultAlignment(Qt.AlignCenter)
        config_layout.addWidget(self.tree_encoders)
        mode_frame = QFrame(objectName='mode_frame')
        mode_frame.setFrameStyle(QFrame.StyledPanel)
        mode_layout = QVBoxLayout(mode_frame)
        mode_layout.setContentsMargins(5, 5, 5, 5)
        mode_layout.setSpacing(5)
        render_mode_frame = QFrame()
        render_mode_layout = QHBoxLayout(render_mode_frame)
        render_mode_layout.setContentsMargins(0, 0, 0, 0)
        self.mode_all = QRadioButton('Single Render')
        self.mode_all.setChecked(True)
        self.mode_all.toggled.connect(self.on_mode_changed)
        self.mode_sequential = QRadioButton('X Render')
        self.mode_sequential.toggled.connect(self.on_mode_changed)
        render_mode_layout.addWidget(self.mode_all)
        render_mode_layout.addWidget(self.mode_sequential)
        render_mode_layout.addStretch()
        mode_layout.addWidget(render_mode_frame)
        self.sequential_combos = []
        sequential_frame = QFrame()
        sequential_layout = QHBoxLayout(sequential_frame)
        sequential_layout.setContentsMargins(0, 0, 0, 0)
        sequential_layout.setSpacing(20)
        combo_colors = ['#FFCDD2', '#C8E6C9', '#BBDEFB', '#E1BEE7', '#FFECB3']
        for i in range(5):
            combo_container = QFrame()
            combo_container.setStyleSheet(f'background-color: {combo_colors[i]}; border-radius: 4px; padding: 2px;')
            combo_layout = QVBoxLayout(combo_container)
            combo_layout.setContentsMargins(5, 5, 5, 5)
            combo_layout.setSpacing(2)
            label = QLabel(f'{i + 1}')
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet('font-weight: bold;')
            combo_layout.addWidget(label)
            combo = QComboBox()
            combo.setEnabled(False)
            combo.setFixedWidth(120)
            combo.setFixedHeight(25)
            combo.setPlaceholderText(f'Encoder {i + 1}')
            combo.setStyleSheet('\n                QComboBox {\n                    background-color: white;\n                    border: 1px solid #ccc;\n                    border-radius: 3px;\n                    padding: 2px;\n                }\n                QComboBox::drop-down {\n                    border: none;\n                }\n                QComboBox::down-arrow {\n                    image: url(down_arrow.png);\n                    width: 12px;\n                    height: 12px;\n                }\n            ')
            self.sequential_combos.append(combo)
            combo_layout.addWidget(combo)
            sequential_layout.addWidget(combo_container)
        sequential_layout.addStretch()
        mode_layout.addWidget(sequential_frame)
        config_layout.addWidget(mode_frame)
        progress_info_frame = QFrame(objectName='progress_info_frame')
        progress_info_layout = QHBoxLayout(progress_info_frame)
        progress_info_layout.setContentsMargins(10, 2, 10, 2)
        self.progress_label = QLabel('Progress: 0/0')
        self.current_label = QLabel('Idle')
        progress_info_layout.addWidget(self.progress_label)
        progress_info_layout.addWidget(self.current_label)
        progress_layout.addWidget(progress_info_frame)
        self.canvas = QFrame(objectName='canvas')
        self.canvas.setFixedHeight(80)
        progress_layout.addWidget(self.canvas)
        canvas_width = 780
        box_size = 15
        padding = 2
        self.boxes_per_row = (canvas_width - padding) // (box_size + padding)
        self.box_size = box_size
        self.padding = padding
        self.progress_boxes = []
        thread_frame = QFrame()
        thread_frame.setFixedHeight(120)
        thread_layout = QVBoxLayout(thread_frame)
        thread_layout.setSpacing(2)
        thread_layout.setContentsMargins(5, 2, 5, 2)
        self.thread_bars = []
        self.thread_labels = []
        for i in range(self.num_threads):
            thread_row = QHBoxLayout()
            thread_row.setSpacing(5)
            label = QLabel(f'#{i + 1}')
            label.setFixedWidth(30)
            thread_row.addWidget(label)
            status = QLabel('Idle')
            status.setFixedWidth(200)
            status.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            thread_row.addWidget(status)
            progress = QProgressBar()
            thread_row.addWidget(progress, stretch=1)
            thread_layout.addLayout(thread_row)
            self.thread_bars.append(progress)
            self.thread_labels.append(status)
        progress_layout.addWidget(thread_frame)
        self.output_text = QTextEdit()
        self.output_text.setFixedHeight(180)
        self.output_text.setReadOnly(True)
        progress_layout.addWidget(self.output_text)
        controls_frame = QFrame(objectName='sub_frame')
        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.setContentsMargins(5, 5, 5, 5)
        controls_layout.setSpacing(5)
        top_controls = QHBoxLayout(spacing=5)
        dir_btn = QPushButton('📍 Directory')
        dir_btn.setFixedWidth(150)
        dir_btn.setFixedHeight(35)
        dir_btn.setToolTip('Select Output Directory')
        dir_btn.clicked.connect(self.select_output_directory)
        self.dir_label = QLabel('Not selected')
        self.dir_label.setStyleSheet('padding-left: 10px; padding-right: 10px;')
        open_btn = QPushButton('📂 Open')
        open_btn.setFixedWidth(150)
        open_btn.setFixedHeight(35)
        open_btn.setToolTip('Open Output Directory')
        open_btn.clicked.connect(self.open_output_directory)
        top_controls.addWidget(dir_btn)
        top_controls.addWidget(self.dir_label, stretch=1)
        top_controls.addWidget(open_btn)
        bottom_controls = QHBoxLayout(spacing=5)
        bottom_controls.addStretch(1)
        self.btn_start = QPushButton('🚀 Start')
        self.btn_start.setFixedWidth(150)
        self.btn_start.setFixedHeight(30)
        self.btn_start.setToolTip('Start Rendering')
        self.btn_start.clicked.connect(self.start_render)
        self.btn_cancel = QPushButton('🛑 Stop')
        self.btn_cancel.setFixedWidth(150)
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.setToolTip('Stop Rendering')
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setProperty('delete', True)
        self.btn_cancel.clicked.connect(self.cancel_render)
        bottom_controls.addWidget(self.btn_start)
        bottom_controls.addWidget(self.btn_cancel)
        bottom_controls.addStretch(1)
        controls_layout.addLayout(top_controls)
        controls_layout.addLayout(bottom_controls)
        output_layout.addWidget(controls_frame)
        self.tree_output = QTreeWidget()
        self.tree_output.setHeaderLabels(['No.', 'Original Filename', 'Output Filename', 'Duration', 'Resolution', 'Status'])
        self.tree_output.setAlternatingRowColors(True)
        self.tree_output.header().setDefaultAlignment(Qt.AlignCenter)
        output_layout.addWidget(self.tree_output)
        self.resizeEvent = self.on_resize
    def on_resize(self, event):
        """Căn chỉnh kích thước các cột khi cửa sổ thay đổi kích thước"""
        total_width = self.tree_videos.width()
        self.tree_videos.setColumnWidth(0, int(total_width * 0.1))
        self.tree_videos.setColumnWidth(1, int(total_width * 0.7))
        self.tree_videos.setColumnWidth(2, int(total_width * 0.15))
        self.tree_videos.setColumnWidth(3, int(total_width * 0.15))
        total_width = self.tree_encoders.width()
        self.tree_encoders.setColumnWidth(0, int(total_width * 0.1))
        self.tree_encoders.setColumnWidth(1, int(total_width * 0.2))
        self.tree_encoders.setColumnWidth(2, int(total_width * 0.2))
        self.tree_encoders.setColumnWidth(3, int(total_width * 0.55))
        self.tree_encoders.setColumnWidth(4, int(total_width * 0.1))
        total_width = self.tree_output.width()
        self.tree_output.setColumnWidth(0, int(total_width * 0.1))
        self.tree_output.setColumnWidth(1, int(total_width * 0.25))
        self.tree_output.setColumnWidth(2, int(total_width * 0.35))
        self.tree_output.setColumnWidth(3, int(total_width * 0.15))
        self.tree_output.setColumnWidth(4, int(total_width * 0.15))
        self.tree_output.setColumnWidth(5, int(total_width * 0.15))
        super().resizeEvent(event)
    def setup_style(self):
        self.setStyleSheet('\n            QMainWindow { background-color: #f8f9fa; }\n            QFrame#top_frame, QFrame#bottom_frame { background-color: transparent; border: none; }\n            QFrame#input_frame, QFrame#config_frame, QFrame#progress_frame, QFrame#output_frame, QFrame#mode_frame {\n                background-color: white; border: 2px solid #dee2e6; border-radius: 8px;\n            }\n            QFrame#progress_info_frame { \n                background-color: #e3f2fd; \n                border: 1px solid #bbdefb; \n                border-radius: 4px;\n            }\n            QFrame#canvas { background-color: #f0f0f0; border: none; }\n            QPushButton {\n                background-color: #007bff; \n                color: white; \n                border: none; \n                border-radius: 4px; \n                padding: 4px 8px;\n                min-width: 120px; \n                max-width: 120px; \n                font-weight: bold;\n                font-size: 12px;\n            }\n            QPushButton:hover { background-color: #0056b3; }\n            QPushButton:disabled { background-color: #6c757d; }\n            QPushButton[delete=\"true\"] { background-color: #dc3545; }\n            QPushButton[delete=\"true\"]:hover { background-color: #c82333; }\n            QTreeWidget { \n                border: 1px solid #dee2e6; \n                border-radius: 4px;\n                background-color: white;\n            }\n            QTreeWidget::item { \n                padding: 2px; \n                border-bottom: 1px solid #dee2e6;\n                height: 25px;\n                min-height: 25px;\n            }\n            QTreeWidget::item:selected { \n                background-color: #007bff; \n                color: white; \n            }\n            QHeaderView::section { \n                background-color: #e3f2fd; \n                padding: 2px; \n                border: 1px solid #bbdefb; \n                font-weight: bold; \n                text-align: center; \n                color: #1976d2;\n                height: 25px;\n            }\n            QProgressBar { \n                border: 1px solid #dee2e6; \n                border-radius: 2px; \n                text-align: center; \n                height: 15px; \n            }\n            QProgressBar::chunk { background-color: #007bff; }\n            QTextEdit { \n                background-color: black; \n                color: white; \n                font-family: Consolas; \n                border-radius: 4px;\n                border: 2px solid #1976d2;  /* Thêm viền xanh */\n                padding: 5px;  /* Thêm padding */\n            }\n            QLabel {\n                color: #1976d2;\n                font-weight: bold;\n                padding: 5px;\n            }\n            QComboBox {\n                border: 1px solid #ced4da;\n                border-radius: 4px;\n                padding: 2px 4px;\n                background-color: white;\n                font-size: 12px;\n            }\n            QComboBox:hover { border: 1px solid #80bdff; }\n            QComboBox:focus { border: 1px solid #80bdff; outline: none; }\n            QComboBox::drop-down {\n                border: none;\n                width: 20px;\n            }\n            QComboBox::down-arrow {\n                width: 12px;\n                height: 12px;\n                margin-right: 5px;\n            }\n            QSpinBox {\n                border: 1px solid #ced4da;\n                border-radius: 4px;\n                padding: 5px;\n                background-color: white;\n            }\n            QSpinBox:hover { border: 1px solid #80bdff; }\n            QSpinBox:focus { border: 1px solid #80bdff; outline: none; }\n        ')
    def _check_dependencies(self) -> None:
        """Kiểm tra sự tồn tại của FFmpeg và FFprobe"""
        if not self.FFMPEG_PATH.is_file():
            QMessageBox.critical(self, 'Error', f'FFmpeg not found at {self.FFMPEG_PATH}. Please ensure FFmpeg is in the \'ffmpeg\' directory.')
            sys.exit(1)
        if not self.FFPROBE_PATH.is_file():
            QMessageBox.critical(self, 'Error', f'FFprobe not found at {self.FFPROBE_PATH}. Please ensure FFprobe is in the \'ffmpeg\' directory.')
            sys.exit(1)

    def _init_gpu_status_bar(self) -> None:
        """Show NVENC capability in the main window's status bar.

        Clickable: double-click opens a detailed diagnostic dialog. Colored
        so GPU-available state is visually distinct from CPU-only fallback.
        """
        status = gpu_detect.format_status(self.gpu_caps)
        bar = self.statusBar()
        self._gpu_status_label = QLabel(status)
        self._gpu_status_label.setToolTip(
            'Double-click for full GPU / NVENC diagnostic report'
        )
        if self.gpu_caps.nvenc_available:
            self._gpu_status_label.setStyleSheet('color: #2e7d32; padding: 2px 6px;')
        else:
            self._gpu_status_label.setStyleSheet('color: #777; padding: 2px 6px;')
        bar.addPermanentWidget(self._gpu_status_label)
        self._gpu_status_label.mouseDoubleClickEvent = self._show_gpu_report

    def _show_gpu_report(self, _event) -> None:
        """Popup the detailed GPU diagnostic report."""
        report = gpu_detect.format_detailed_report(self.gpu_caps)
        dlg = QMessageBox(self)
        dlg.setWindowTitle('GPU Detection Report')
        dlg.setIcon(QMessageBox.Information)
        dlg.setText(report)
        dlg.setStyleSheet('QLabel { font-family: Consolas, monospace; }')
        dlg.exec_()

    def load_config(self) -> Dict[str, Any]:
        """Tải cấu hình từ config_video_renderer.json nếu tồn tại."""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    json.load(f)
            except json.JSONDecodeError:
                QMessageBox.warning(self, 'Error', 'Configuration file is corrupted. Loading default settings.')
                return {}
        return core_config.load(Path(self.CONFIG_FILE), default={})
    def save_config(self) -> None:
        """Lưu cấu hình vào config_video_renderer.json."""
        try:
            config = {'input_files': self.videos, 'output_dir': self.output_directory, 'encoder_options': self.selected_encoders, 'num_threads': self.num_threads}
            core_config.save(Path(self.CONFIG_FILE), config)
        except (OSError, TypeError) as e:
            QMessageBox.warning(self, 'Error', f'Failed to save configuration: {str(e)}')
    def load_encoder_options(self) -> List[Dict[str, Any]]:
        """Đọc các tùy chọn render từ file Encoder.txt và bỏ qua các dòng lỗi."""
        options = []
        if self.ENCODER_FILE.exists():
            with open(self.ENCODER_FILE, 'r', encoding='utf-8') as file:
                for line_number, line in enumerate(file, start=1):
                    try:
                        if line.strip():
                            parts = line.strip().rsplit('|', 1)
                            if len(parts)!= 2:
                                print(f'Skipping invalid encoder option at line {line_number}: {line.strip()}')
                                continue
                            header_parts = parts[0].split('|', 3)
                            if len(header_parts) < 3:
                                print(f'Skipping invalid encoder option at line {line_number}: {line.strip()}')
                                continue
                            group = header_parts[0].strip()
                            name = header_parts[1].strip()
                            description = header_parts[2].strip()
                            details = header_parts[3].strip() if len(header_parts) > 3 else ''
                            code = parts[1].strip()
                            if not name:
                                print(f'Skipping encoder option with empty name at line {line_number}')
                                continue
                            options.append({'name': f'{group}|{name}', 'description': description, 'details': details, 'params': code.split()})
                    except Exception as e:
                        print(f'Error parsing line {line_number}: {str(e)}')
        default_options = [{'name': 'Text|Text Bottom Basic', 'description': 'Thêm chữ ở dưới với nền đen mờ', 'details': 'Thêm chữ ở dưới video với nền đen mờ, font Arial, size 35px', 'params': ['-vf', 'drawtext=fontfile=Arial:text=\'THAY_THẾ_NỘI_DUNG\':x=(w-text_w)/2:y=(h-text_h)/1.05:fontsize=35:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=10']}, {'name': 'Text|Text Top Basic', 'description': 'Thêm chữ ở trên với nền đen mờ', 'details': 'Thêm chữ ở trên video với nền đen mờ, font Arial, size 35px', 'params': ['-vf', 'drawtext=fontfile=Arial:text=\'THAY_THẾ_NỘI_DUNG\':x=(w-text_w)/2:y=(h-text_h)/15:fontsize=35:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=10']}]
        options.extend(default_options)
        return options
    def select_videos(self):
        """Chọn nhiều video từ thư mục đầu vào."""
        try:
            initial_dir = os.path.dirname(self.videos[0]) if self.videos else os.getcwd()
            file_paths = core_file_picker.pick_files(self, 'Select Videos', initial_dir, core_file_picker.VIDEO_FILTER)
            if file_paths:
                new_files = [fp for fp in file_paths if fp not in self.videos]
                if not new_files:
                    QMessageBox.information(self, 'Info', 'No new videos were added.')
                    return
                self.videos.extend(new_files)
                self.update_video_list()
                self.btn_delete.setEnabled(True)
                print(f'Added {len(new_files)} videos.')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Cannot select videos: {str(e)}')
    def update_video_list(self):
        """Cập nhật danh sách video."""
        self.tree_videos.clear()
        for idx, video_path in enumerate(self.videos, start=1):
            item = QTreeWidgetItem(self.tree_videos)
            item.setText(0, str(idx))
            item.setText(1, os.path.basename(video_path))
            try:
                duration = self.get_video_duration(video_path)
                item.setText(2, duration)
                resolution = self.get_video_resolution(video_path)
                item.setText(3, resolution)
            except Exception as e:
                item.setText(2, 'Loading...')
                item.setText(3, 'Loading...')
                print(f'Error getting video info for {video_path}: {str(e)}')
        select_btn = self.findChild(QPushButton, 'select_btn')
        if select_btn:
            select_btn.setText(f'📥 Select ({len(self.videos)})')
    def get_video_duration(self, video_path: str) -> str:
        """Lấy thời lượng video sử dụng FFprobe."""
        command = [str(self.FFPROBE_PATH), '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.dwFlags |= subprocess.STARTF_USESTDHANDLES
            result = subprocess.run(command, capture_output=True, text=True, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            duration_seconds = float(result.stdout.strip())
            hours = int(duration_seconds // 3600)
            minutes = int(duration_seconds % 3600 // 60)
            seconds = int(duration_seconds % 60)
            return f'{hours:02d}:{minutes:02d}:{seconds:02d}'
        except Exception as e:
            raise Exception(f'Failed to get video duration: {str(e)}')
    def get_video_resolution(self, video_path: str) -> str:
        """Lấy độ phân giải video sử dụng FFprobe."""
        command = [str(self.FFPROBE_PATH), '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0', video_path]
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.dwFlags |= subprocess.STARTF_USESTDHANDLES
            result = subprocess.run(command, capture_output=True, text=True, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            return result.stdout.strip() or 'Loading...'
        except Exception as e:
            print(f'Failed to get video resolution: {str(e)}')
            return 'Loading...'
    def delete_videos(self):
        """Xóa các video đã chọn."""
        try:
            selected_items = self.tree_videos.selectedItems()
            if not selected_items:
                QMessageBox.information(self, 'Info', 'No videos selected to delete.')
                return
            indices = []
            for item in selected_items:
                idx = int(item.text(0)) - 1
                indices.append(idx)
            for idx in sorted(indices, reverse=True):
                self.videos.pop(idx)
            self.update_video_list()
            if not self.videos:
                self.btn_delete.setEnabled(False)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Cannot delete selected videos: {str(e)}')
    def select_output_directory(self):
        """Chọn thư mục đầu ra."""
        try:
            output_dir = core_file_picker.pick_directory(self, 'Select Output Directory', self.output_directory or os.getcwd())
            if output_dir:
                self.output_directory = output_dir
                self.dir_label.setText(f'{self.output_directory}')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Cannot select output directory: {str(e)}')
    def create_progress_box(self, index: int) -> QFrame:
        """Tạo một progress box."""
        box = QFrame(self.canvas)
        box.setGeometry(index % self.boxes_per_row * (self.box_size + self.padding), index // self.boxes_per_row * (self.box_size + self.padding), self.box_size, self.box_size)
        box.setStyleSheet('\n            background-color: lightgray; border: 1px solid #666666; border-radius: 2px;\n        ')
        box.show()
        return box
    def update_box_color(self, index: int, color: str):
        """Cập nhật màu của progress box"""
        if 0 <= index < len(self.progress_boxes):
            if color == 'green':
                self.progress_boxes[index].setStyleSheet('\n                    background-color: #4CAF50;\n                    border: 1px solid #2E7D32;\n                    border-radius: 2px;\n                ')
            else:
                if color == 'yellow':
                    self.progress_boxes[index].setStyleSheet('\n                    background-color: #FFC107;\n                    border: 1px solid #FFA000;\n                    border-radius: 2px;\n                ')
                else:
                    if color == 'red':
                        self.progress_boxes[index].setStyleSheet('\n                    background-color: #F44336;\n                    border: 1px solid #D32F2F;\n                    border-radius: 2px;\n                ')
                    else:
                        self.progress_boxes[index].setStyleSheet('\n                    background-color: lightgray;\n                    border: 1px solid #666666;\n                    border-radius: 2px;\n                ')
    def clear_progress_boxes(self):
        """Xóa tất cả progress boxes"""
        for box in self.progress_boxes:
            box.deleteLater()
        self.progress_boxes.clear()
    def start_render(self):
        """Bắt đầu quá trình render."""
        if self.is_rendering:
            reply = QMessageBox.question(self, 'Confirm', 'A rendering process is already running. Do you want to cancel and start a new one?', QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.cancel_render()
            else:
                return None
        if not self.validate_inputs():
            return
        else:
            if self.sequential_mode:
                self.sequential_encoders = [combo.currentText() for combo in self.sequential_combos if combo.currentText()]
                if not self.sequential_encoders:
                    QMessageBox.warning(self, 'Warning', 'Please select at least one Encoder in sequential mode.')
                    return
            else:
                selected_items = self.tree_encoders.selectedItems()
                if not selected_items:
                    QMessageBox.warning(self, 'Warning', 'Please select at least one Encoder option.')
                    return
                else:
                    selected_encoders = []
                    encoder_params = {}
                    for item in selected_items:
                        name = item.text(2)
                        code = item.data(0, Qt.UserRole).split()
                        selected_encoders.append(name)
                        encoder_params[name] = code
                    self.selected_encoders = selected_encoders
                    self.encoder_params = encoder_params
            self.is_rendering = True
            self.btn_start.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            if self.sequential_mode:
                total_tasks = len(self.videos)
            else:
                total_tasks = len(self.videos) * len(self.selected_encoders)
            self.progress_label.setText(f'Progress: 0/{total_tasks} renders')
            self.current_label.setText('Currently Rendering: None')
            self.tree_output.clear()
            self.output_mapping.clear()
            self.clear_progress_boxes()
            for i in range(total_tasks):
                box = self.create_progress_box(i)
                self.progress_boxes.append(box)
            self.render_threads = []
            self.render_workers = []
            self.current_task_index = 0
            self.total_tasks = total_tasks
            self.active_threads = 0
            self.completed_tasks = 0
            self.all_tasks = []
            if self.sequential_mode:
                for video_idx, video_path in enumerate(self.videos):
                    self.all_tasks.append((video_path, self.sequential_encoders, video_idx))
            else:
                for video_idx, video_path in enumerate(self.videos):
                    for encoder_idx, encoder_name in enumerate(self.selected_encoders):
                        self.all_tasks.append((video_path, [encoder_name], video_idx))
            for i in range(self.num_threads):
                thread = QThread()
                self.render_threads.append(thread)
                self.render_workers.append(None)
            for i in range(min(self.num_threads, total_tasks)):
                self._start_next_task()
    def _start_next_task(self):
        """Khởi chạy task tiếp theo nếu còn."""
        if not self.is_rendering:
            return
        else:
            if self.current_task_index >= len(self.all_tasks) and self.completed_tasks >= self.total_tasks:
                for thread in self.render_threads:
                    if thread.isRunning():
                        thread.quit()
                        thread.wait()
                self.render_threads.clear()
                self.render_workers.clear()
                self.is_rendering = False
                self.btn_start.setEnabled(True)
                self.btn_cancel.setEnabled(False)
                self.current_label.setText('Idle')
                QMessageBox.information(self, 'Success', f'Completed processing {self.total_tasks} video(s)!')
                self.save_config()
                return None
            else:
                thread_index = (-1)
                for i in range(len(self.render_threads)):
                    if self.render_workers[i] is None:
                        thread_index = i
                        break
                if thread_index == (-1):
                    return
                else:
                    video_path, encoder_names, video_idx = self.all_tasks[self.current_task_index]
                    box_index = self.current_task_index
                    self.update_box_color(box_index, 'yellow')
                    item = QTreeWidgetItem(self.tree_output)
                    item.setText(0, str(self.current_task_index + 1))
                    item.setText(1, os.path.basename(video_path))
                    if self.sequential_mode:
                        encoder_names_str = ' ➡️ '.join(encoder_names) if encoder_names else 'No encoders'
                        item.setText(2, f'Processing... ({encoder_names_str})')
                    else:
                        item.setText(2, 'Processing...')
                    item.setText(3, 'Loading...')
                    item.setText(4, 'Loading...')
                    item.setText(5, '🟡 Processing')
                    self.output_mapping[f'Processing - {os.path.basename(video_path)}'] = item
                    encoder_params_list = []
                    for encoder_name in encoder_names:
                        if not encoder_name:
                            continue
                        else:
                            if self.sequential_mode:
                                for encoder in self.encoder_options:
                                    name_parts = encoder['name'].split('|', 1)
                                    if len(name_parts) > 1 and name_parts[1] == encoder_name:
                                            encoder_params_list.append(encoder['params'])
                                            break
                            else:
                                params = self.encoder_params.get(encoder_name)
                                if params:
                                    encoder_params_list.append(params)
                    if not encoder_params_list:
                        self.on_render_error(f'Encoder parameters not found for {encoder_names}')
                        return
                    else:
                        worker = RenderWorker(video_path, encoder_names, thread_index, str(self.FFMPEG_PATH), self.output_directory, encoder_params_list)
                        worker.progress_updated.connect(self.update_thread_progress)
                        worker.status_updated.connect(self.update_thread_status)
                        worker.output_updated.connect(self.update_ffmpeg_output)
                        worker.render_completed.connect(self.on_render_completed)
                        worker.error_occurred.connect(self.on_render_error)
                        thread = self.render_threads[thread_index]
                        worker.moveToThread(thread)
                        thread.started.connect(worker.process)
                        self.render_workers[thread_index] = worker
                        if self.sequential_mode:
                            self.current_label.setText(f'Currently Rendering: {os.path.basename(video_path)} ({encoder_names_str})')
                        else:
                            self.current_label.setText(f'Currently Rendering: {os.path.basename(video_path)}')
                        thread.start()
                        self.active_threads += 1
                        self.current_task_index += 1
    def cancel_render(self):
        """Hủy quá trình render."""
        if self.is_rendering:
            self.is_rendering = False
            if hasattr(self, 'render_workers'):
                for worker in self.render_workers:
                    if worker is not None:
                        worker.is_cancelled = True
            if hasattr(self, 'render_threads'):
                for thread in self.render_threads:
                    if thread.isRunning():
                        thread.quit()
                        thread.wait()
                self.render_threads.clear()
                self.render_workers.clear()
            if hasattr(self, 'progress_boxes'):
                for i in range(len(self.progress_boxes)):
                    if i >= self.completed_tasks:
                        self.update_box_color(i, 'red')
            for i in range(len(self.thread_labels)):
                self.thread_labels[i].setText('Cancelled')
                self.thread_bars[i].setValue(0)
            self.btn_cancel.setEnabled(False)
            self.btn_start.setEnabled(True)
            self.output_text.append('\nThe rendering process has been canceled.')
            QMessageBox.information(self, 'Info', 'The rendering process has been canceled.')
    def validate_inputs(self) -> bool:
        """Xác thực đầu vào."""
        if not self.videos:
            QMessageBox.warning(self, 'Warning', 'Please select at least one video.')
            return False
        else:
            if not self.output_directory:
                QMessageBox.warning(self, 'Warning', 'Please select an output directory.')
                return False
            else:
                return True
    def update_thread_progress(self, thread_index: int, progress: int):
        """Cập nhật tiến độ của thread."""
        if 0 <= thread_index < len(self.thread_bars):
            self.thread_bars[thread_index].setValue(progress)
    def update_thread_status(self, thread_index: int, status: str):
        """Cập nhật trạng thái của thread."""
        if 0 <= thread_index < len(self.thread_labels):
            self.thread_labels[thread_index].setText(status)
    def update_ffmpeg_output(self, output: str):
        """Cập nhật output của FFmpeg."""
        self.output_text.append(output)
        self.output_text.verticalScrollBar().setValue(self.output_text.verticalScrollBar().maximum())
    def on_render_completed(self, output_filename: str):
        """Xử lý khi render hoàn thành."""
        if not self.is_rendering:
            return
        worker = self.sender()
        original_filename = os.path.basename(worker.video_path)
        output_path = os.path.join(self.output_directory, output_filename)
        resolution = self.get_video_resolution(output_path)
        duration = self.get_video_duration(output_path)
        task_number = str(self.completed_tasks + 1)
        found = False
        for i in range(self.tree_output.topLevelItemCount()):
            item = self.tree_output.topLevelItem(i)
            if item.text(0) == task_number and item.text(5) == '🟡 Processing':
                    found = True
                    item.setText(2, output_filename)
                    item.setText(3, duration)
                    item.setText(4, resolution)
                    item.setText(5, '🟢 Completed')
                    break
        if not found:
            print(f'Warning: Could not find item number {task_number} in tree output')
        box_index = self.completed_tasks
        self.update_box_color(box_index, 'green')
        self.completed_tasks += 1
        self.progress_label.setText(f'Progress: {self.completed_tasks}/{self.total_tasks} renders')
        self.active_threads -= 1
        thread_index = worker.thread_index
        if 0 <= thread_index < len(self.render_workers):
                self.render_workers[thread_index] = None
                if thread_index < len(self.render_threads):
                    self.render_threads[thread_index].quit()
                    self.render_threads[thread_index].wait()
        if self.current_task_index < self.total_tasks:
            self._start_next_task()
        if self.completed_tasks >= self.total_tasks:
            for thread in self.render_threads:
                if thread.isRunning():
                    thread.quit()
                    thread.wait()
            self.render_threads.clear()
            self.render_workers.clear()
            self.is_rendering = False
            self.btn_start.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.current_label.setText('Idle')
            QMessageBox.information(self, 'Success', f'Successfully rendered {self.total_tasks} video(s)!')
            self.save_config()
    def on_render_error(self, error_message: str):
        """Xử lý khi có lỗi render."""
        self.output_text.append(f'\n[ERROR] {error_message}\n')
        self.output_text.verticalScrollBar().setValue(self.output_text.verticalScrollBar().maximum())
        worker = self.sender()
        if worker:
            original_filename = os.path.basename(worker.video_path)
            encoder_name = worker.encoder_names[0] if worker.encoder_names else 'Loading...'
            error_detail = error_message.split(':')[(-1)].strip()
            if len(error_detail) > 50:
                error_detail = error_detail[:47] + '...'
            task_number = str(self.completed_tasks + 1)
            found = False
            for i in range(self.tree_output.topLevelItemCount()):
                item = self.tree_output.topLevelItem(i)
                if item.text(0) == task_number and item.text(5) == '🟡 Processing':
                        found = True
                        item.setText(2, f'Error - {encoder_name} ({error_detail})')
                        item.setText(3, 'Loading...')
                        item.setText(4, 'Loading...')
                        item.setText(5, '🔴 Error')
                        break
            if not found:
                print(f'Warning: Could not find item number {task_number} in tree output')
        box_index = self.completed_tasks
        self.update_box_color(box_index, 'red')
        self.completed_tasks += 1
        self.progress_label.setText(f'Progress: {self.completed_tasks}/{self.total_tasks} renders')
        thread_index = worker.thread_index
        if 0 <= thread_index < len(self.render_workers):
                self.render_workers[thread_index] = None
                if thread_index < len(self.render_threads):
                    self.render_threads[thread_index].quit()
                    self.render_threads[thread_index].wait()
        self.active_threads -= 1
        self._start_next_task()
    def closeEvent(self, event):
        """Xử lý khi đóng ứng dụng."""
        if self.is_rendering:
            reply = QMessageBox.question(self, 'Exit', 'A rendering process is running. Do you really want to exit?', QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.is_rendering = False
                if hasattr(self, 'render_workers'):
                    for worker in self.render_workers:
                        worker.is_cancelled = True
                if hasattr(self, 'render_threads'):
                    for thread in self.render_threads:
                        thread.quit()
                        thread.wait()
                    self.render_threads.clear()
                    self.render_workers.clear()
                self.save_config()
                event.accept()
            else:
                event.ignore()
        else:
            self.save_config()
            event.accept()
    def load_encoders_to_tree(self, selected_group: str='🕹️ 1vmo Ultimate'):
        """Load encoder options vào TreeWidget với lọc theo nhóm"""
        self.tree_encoders.clear()
        current_groups = self.get_encoder_groups()
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem('🕹️ 1vmo Ultimate')
        self.group_combo.addItem('All Groups')
        self.group_combo.addItems(current_groups)
        if selected_group in current_groups or selected_group == '🕹️ 1vmo Ultimate':
            self.group_combo.setCurrentText(selected_group)
        self.group_combo.blockSignals(False)
        sorted_encoders = sorted(self.encoder_options, key=lambda x: (x['name'].split('|')[0] if '|' in x['name'] else '', x['name']))
        counter = 1
        for combo in self.sequential_combos:
            combo.blockSignals(True)
            combo.clear()
            combo.addItem('')
            for encoder in sorted_encoders:
                name_parts = encoder['name'].split('|', 1)
                name = name_parts[1] if len(name_parts) > 1 else encoder['name']
                combo.addItem(name)
            combo.blockSignals(False)
        for encoder in sorted_encoders:
            name_parts = encoder['name'].split('|', 1)
            group = name_parts[0] if len(name_parts) > 1 else ''
            name = name_parts[1] if len(name_parts) > 1 else encoder['name']
            if selected_group == 'All Groups' or group == selected_group:
                item = QTreeWidgetItem(self.tree_encoders)
                item.setText(0, str(counter))
                item.setText(1, group)
                item.setText(2, name)
                item.setText(3, encoder['description'])
                if encoder.get('details'):
                    tooltip_text = encoder['details'].replace(',', ',<br>')
                    tooltip_html = f'\n                    <div style=\'min-width:280px; max-width:350px; background:#e3f2fd; color:#1976d2; font-family:Consolas,monospace; font-size:13px; padding:8px; border-radius:8px;\'>\n                        {tooltip_text}\n                    </div>\n                    '
                    item.setText(4, 'ℹ️')
                    item.setTextAlignment(4, Qt.AlignCenter)
                    for col in range(5):
                        item.setToolTip(col, tooltip_html)
                else:
                    item.setText(4, '')
                item.setData(0, Qt.UserRole, ' '.join(encoder['params']))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                counter += 1
        self.tree_encoders.setHeaderLabels(['No.', 'Group', 'Name', 'Description', 'Details'])
    def add_encoder(self) -> None:
        """Thêm encoder mới"""
        dialog = EncoderDialog(self)
        if dialog.exec_() == QDialog.Accepted and dialog.result:
                item = QTreeWidgetItem(self.tree_encoders)
                item.setText(0, str(len(self.encoder_options) + 1))
                name_parts = dialog.result['name'].split('|', 1)
                group = name_parts[0] if len(name_parts) > 1 else ''
                name = name_parts[1] if len(name_parts) > 1 else dialog.result['name']
                item.setText(1, group)
                item.setText(2, name)
                item.setText(3, dialog.result['description'])
                item.setData(0, Qt.UserRole, ' '.join(dialog.result['params']))
                self.encoder_options.append(dialog.result)
                self.save_encoder_changes()
    def edit_encoder(self) -> None:
        """Chỉnh sửa encoder đã chọn"""
        selection = self.tree_encoders.selectedItems()
        if not selection:
            QMessageBox.warning(self, 'Warning', 'Please select an encoder to edit')
            return
        else:
            item = selection[0]
            current_group = item.text(1)
            current_name = item.text(2)
            current_desc = item.text(3)
            current_params = item.data(0, Qt.UserRole).split()
            initial_values = {'name': f'{current_group}|{current_name}', 'description': current_desc, 'params': current_params}
            dialog = EncoderDialog(self, 'Edit Encoder', initial_values)
            if dialog.exec_() == QDialog.Accepted:
                if dialog.result:
                    name_parts = dialog.result['name'].split('|', 1)
                    group = name_parts[0] if len(name_parts) > 1 else ''
                    name = name_parts[1] if len(name_parts) > 1 else dialog.result['name']
                    item.setText(1, group)
                    item.setText(2, name)
                    item.setText(3, dialog.result['description'])
                    item.setData(0, Qt.UserRole, ' '.join(dialog.result['params']))
                    idx = self.get_encoder_index_by_name(f'{current_group}|{current_name}')
                    if idx is not None:
                        self.encoder_options[idx] = dialog.result
                        self.save_encoder_changes()
    def delete_encoder(self) -> None:
        """Xóa encoder đã chọn"""
        selection = self.tree_encoders.selectedItems()
        if not selection:
            QMessageBox.warning(self, 'Warning', 'Please select encoder(s) to delete')
            return
        else:
            reply = QMessageBox.question(self, 'Confirm Delete', 'Are you sure you want to delete the selected encoder(s)?', QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                for item in selection:
                    group = item.text(1)
                    name = item.text(2)
                    full_name = f'{group}|{name}' if group else name
                    idx = self.get_encoder_index_by_name(full_name)
                    if idx is not None:
                        self.encoder_options.pop(idx)
                    self.tree_encoders.takeTopLevelItem(self.tree_encoders.indexOfTopLevelItem(item))
                self.save_encoder_changes()
    def save_encoder_changes(self) -> None:
        """Lưu tất cả thay đổi vào file"""
        try:
            with open(self.ENCODER_FILE, 'w', encoding='utf-8') as file:
                for encoder in self.encoder_options:
                    name_parts = encoder['name'].split('|', 1)
                    group = name_parts[0] if len(name_parts) > 1 else ''
                    name = name_parts[1] if len(name_parts) > 1 else encoder['name']
                    details = encoder.get('details', '')
                    file.write(f"{group}|{name}|{encoder['description']}|{details}|{' '.join(encoder['params'])}\n")
            QMessageBox.information(self, 'Success', 'Encoder settings saved successfully')
        except Exception as e:
            QMessageBox.warning(self, 'Warning', f'Failed to save encoder settings: {str(e)}')
    def get_encoder_index_by_name(self, name: str) -> Optional[int]:
        """Tìm index của encoder trong list theo tên"""
        for i, encoder in enumerate(self.encoder_options):
            if encoder['name'] == name:
                return i
    def open_output_directory(self):
        """Mở thư mục output directory trong file explorer"""
        if not self.output_directory:
            QMessageBox.warning(self, 'Warning', 'Please select an output directory first.')
            return
        try:
            if os.name == 'nt':
                os.startfile(self.output_directory)
            elif os.name == 'posix':
                if sys.platform == 'darwin':
                    subprocess.call(['open', self.output_directory])
                else:
                    subprocess.call(['xdg-open', self.output_directory])
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Cannot open directory: {str(e)}')
    def reload_all(self):
        """Reload tất cả các thay đổi từ file và thư mục"""
        try:
            self.tree_output.clear()
            self.output_text.clear()
            self.output_mapping.clear()
            self.encoder_options = self.load_encoder_options()
            self.load_encoders_to_tree()
            if self.videos:
                self.update_video_list()
            QMessageBox.information(self, 'Success', 'Successfully refreshed all data!')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Error while refreshing: {str(e)}')
    def get_encoder_groups(self) -> List[str]:
        """Lấy danh sách các nhóm encoder duy nhất"""
        groups = set()
        for encoder in self.encoder_options:
            name_parts = encoder['name'].split('|', 1)
            group = name_parts[0] if len(name_parts) > 1 else ''
            if group:
                groups.add(group)
        return sorted(list(groups))
    def on_group_changed(self, group: str):
        """Xử lý khi chọn nhóm khác"""
        self.load_encoders_to_tree(group)
    def create_video_button(self, text: str, callback, bg_color: str, text_color: str, border_color: str, delete: bool=False) -> QPushButton:
        """Tạo nút video với style tùy chỉnh."""
        button = QPushButton(text)
        button.clicked.connect(callback)
        button.setStyleSheet(f'\n            QPushButton {{\n                background-color: {bg_color};\n                color: {text_color};\n                border: 1px solid {border_color};\n            }}\n            QPushButton:hover {{\n                background-color: {border_color};\n            }}\n        ')
        if delete:
            button.setProperty('delete', True)
        return button
    def on_mode_changed(self):
        """Xử lý khi chọn chế độ ghép"""
        self.sequential_mode = self.mode_sequential.isChecked()
        for combo in self.sequential_combos:
            combo.setEnabled(self.sequential_mode)
        if self.sequential_mode:
            self.sequential_encoders = [self.sequential_combos[i].currentText() for i in range(5)]
        else:
            self.sequential_encoders = [None] * 5
    def show_help(self):
        """Hiển thị dialog help"""
        readme_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'README AutoRender.md')
        dialog = HelpDialog(self, 'Help - 1vmo Auto Render', readme_path)
        dialog.exec_()
class EncoderDialog(QDialog):
    def __init__(self, parent=None, title='Add New Encoder', initial_values=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(500, 400)
        self.result = None
        self.initial_values = initial_values or {'name': '', 'description': '', 'params': []}
        self.setup_ui()
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Name:'))
        self.name_edit = QLineEdit()
        self.name_edit.setText(self.initial_values['name'])
        layout.addWidget(self.name_edit)
        layout.addWidget(QLabel('Description:'))
        self.desc_edit = QTextEdit()
        self.desc_edit.setText(self.initial_values['description'])
        layout.addWidget(self.desc_edit)
        layout.addWidget(QLabel('Parameters:'))
        self.params_edit = QTextEdit()
        self.params_edit.setText(' '.join(self.initial_values['params']))
        layout.addWidget(self.params_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    def accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, 'Warning', 'Name is required')
            return
        else:
            self.result = {'name': name, 'description': self.desc_edit.toPlainText().strip(), 'params': self.params_edit.toPlainText().strip().split()}
            super().accept()
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = VideoRendererTool()
    window.show()
    sys.exit(app.exec_())