# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'Code Mixer.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

import os
import random
import threading
import json
import subprocess
import sys
import queue
import tempfile
import re
import logging
import multiprocessing
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple, Optional
import requests
import shutil
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QTreeWidget, QTreeWidgetItem, QComboBox, QFileDialog, QTextEdit, QFrame, QMessageBox, QGridLayout, QSpacerItem, QSizePolicy, QDialog
from PyQt5.QtCore import Qt, QThreadPool, QRunnable, pyqtSignal, QObject, QThread, QTimer
from PyQt5.QtGui import QIcon, QColor
from updater import DriveUpdater
from help_dialog import HelpDialog
from core import config as core_config
SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
FFMPEG_PATH = SCRIPT_DIR / 'ffmpeg' / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
FFPROBE_PATH = SCRIPT_DIR / 'ffmpeg' / ('ffprobe.exe' if os.name == 'nt' else 'ffprobe')
ICON_PATH = SCRIPT_DIR / 'assets' / 'Mixer.ico'
CONFIG_FILE = SCRIPT_DIR / 'config_video_merger.json'
logging.basicConfig(filename='video_merger.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
COMMON_STYLE = '\n    QMainWindow { background-color: #f8f9fa; }\n    QFrame#top_frame, QFrame#bottom_frame, QFrame#videos_frame, QFrame#options_frame,\n    QFrame#progress_frame, QFrame#output_frame {\n        background-color: white; border: 1px solid #dee2e6; border-radius: 4px;\n    }\n    QPushButton {\n        background-color: #007bff; color: white; border: none; border-radius: 4px;\n        padding: 8px 16px; min-width: 100px; max-width: 100px; font-weight: bold;\n    }\n    QPushButton:hover { background-color: #0056b3; }\n    QPushButton:disabled { background-color: #6c757d; }\n    QPushButton[delete=\"true\"] { background-color: #dc3545; }\n    QPushButton[delete=\"true\"]:hover { background-color: #c82333; }\n    QTreeWidget { border: 1px solid #dee2e6; }\n    QTextEdit { background-color: black; color: white; font-family: Consolas; }\n'
def escape_video_path(video: str) -> str:
    """Thoát đường dẫn video để sử dụng trong FFmpeg."""
    return str(video).replace('\\', '\\\\').replace('\'', '\'\\\'\'')
class WorkerSignals(QObject):
    progress_updated = pyqtSignal(int, int)
    status_updated = pyqtSignal(int, str)
    output_updated = pyqtSignal(str)
    merge_completed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
class MergeWorker(QRunnable):
    def __init__(self, input_files: List[str], output_path: str, thread_index: int, ffmpeg_path: Path):
        super().__init__()
        self.input_files = input_files
        self.output_path = output_path
        self.thread_index = thread_index
        self.ffmpeg_path = ffmpeg_path
        self.is_cancelled = False
        self.signals = WorkerSignals()
        self.logger = logging.getLogger(__name__)
    def run(self):
        try:
            self.signals.status_updated.emit(self.thread_index, f'Bắt đầu xử lý: {os.path.basename(self.output_path)}')
            self.signals.progress_updated.emit(self.thread_index, 0)
            self.signals.output_updated.emit(f'\n[Thread {self.thread_index + 1}] Bắt đầu xử lý: {os.path.basename(self.output_path)}\n')
            for video in self.input_files:
                if not os.path.exists(video):
                    raise FileNotFoundError(f'Không tìm thấy file: {video}')
                if os.path.getsize(video) == 0:
                    raise ValueError(f'File rỗng: {video}')
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as tmp_file:
                for video in self.input_files:
                    tmp_file.write(f'file \'{escape_video_path(video)}\'\n')
                temp_file_path = tmp_file.name
            os.chmod(temp_file_path, 438)
            command = [str(self.ffmpeg_path), '-y', '-f', 'concat', '-safe', '0', '-i', temp_file_path, '-c', 'copy', str(self.output_path)]
            self.signals.output_updated.emit(f"Lệnh thực thi: {' '.join((str(x) for x in command))}\n\n")
            startupinfo = subprocess.STARTUPINFO() if os.name == 'nt' else None
            if startupinfo:
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.dwFlags |= subprocess.STARTF_USESTDHANDLES
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, text=True, encoding='utf-8', errors='replace')
            duration, time = (None, 0)
            error_output = []
            while True:
                if self.is_cancelled:
                    process.terminate()
                    process.wait()
                    self.signals.status_updated.emit(self.thread_index, 'Đã hủy')
                    self.signals.progress_updated.emit(self.thread_index, 0)
                    try:
                        if os.path.exists(temp_file_path):
                            os.remove(temp_file_path)
                    except Exception as e:
                        self.logger.warning(f'Không thể xóa file tạm {temp_file_path}: {str(e)}')
                    return
                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    return_code = process.wait()
                    if return_code == 0 and (not self.is_cancelled):
                        if os.path.exists(self.output_path) and os.path.getsize(self.output_path) > 0:
                            self.signals.status_updated.emit(self.thread_index, 'Hoàn thành')
                            self.signals.progress_updated.emit(self.thread_index, 100)
                            self.signals.output_updated.emit(f'\n[Thread {self.thread_index + 1}] Hoàn thành: {os.path.basename(self.output_path)}\n')
                            self.signals.merge_completed.emit(os.path.basename(self.output_path))
                        else:
                            raise RuntimeError('File đầu ra không tồn tại hoặc rỗng')
                    else:
                        error_msg = '\n'.join(error_output[(-5):])
                        raise RuntimeError(f'FFmpeg trả về mã lỗi {return_code}\n{error_msg}')
                    break
                if line:
                    error_output.append(line)
                    self.signals.output_updated.emit(line)
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
                        self.signals.progress_updated.emit(self.thread_index, progress)
            try:
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
            except Exception as e:
                self.logger.warning(f'Không thể xóa file tạm {temp_file_path}: {str(e)}')
        except Exception as e:
            error_msg = f'Lỗi khi xử lý {os.path.basename(self.output_path)}: {str(e)}'
            self.logger.error(error_msg)
            self.signals.error_occurred.emit(error_msg)
            self.signals.status_updated.emit(self.thread_index, 'Lỗi')
            self.signals.progress_updated.emit(self.thread_index, 0)
            self.signals.output_updated.emit(f'\n[Thread {self.thread_index + 1}] {error_msg}\n')
class VideoMergerTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        if not FFMPEG_PATH.exists() or not FFPROBE_PATH.exists():
            QMessageBox.critical(self, 'Error', 'FFmpeg or FFprobe not found. Please place them in the \'ffmpeg\' directory.')
            sys.exit(1)
        self.updater = DriveUpdater()
        self.current_version = self.updater._load_current_version('1vmo Mixer')
        if self.current_version is None:
            self.current_version = '1.0'
            self.updater._save_current_version(self.current_version, '1vmo Mixer')
        self.setWindowTitle(f'1vmo Mixer v{self.current_version}')
        self.setGeometry(100, 100, 1600, 900)
        # Allow resize and maximize — set a reasonable minimum so layouts don't
        # collapse below their designed size, and use resize() for initial geometry.
        self.setMinimumSize(1600, 900)
        self.resize(1600, 900)
        self.updater.check_and_update('1vmo Mixer')
        self.setup_icon()
        self.initialize_state()
        self.config = self.load_config()
        self.setup_ui()
        self.setup_style()
        self.load_last_paths()
    def setup_icon(self):
        """Thiết lập biểu tượng ứng dụng."""
        try:
            if ICON_PATH.exists():
                app_icon = QIcon(str(ICON_PATH))
                self.setWindowIcon(app_icon)
                QApplication.setWindowIcon(app_icon)
                if os.name == 'nt':
                    import ctypes
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('1vmo.VideoMerger.1.0.0')
        except Exception as e:
            self.logger.error(f'Error setting up icon: {str(e)}')
    def initialize_state(self):
        """Khởi tạo trạng thái ban đầu."""
        self.video_list = []
        self.intro_videos = []
        self.outro_videos = []
        self.output_directory = ''
        self.is_merging = False
        self.total_output = 0
        self.processed_output = 0
        self.cancel_event = threading.Event()
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(3)
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        top_frame = QFrame(objectName='top_frame')
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(5, 5, 5, 5)
        top_layout.setSpacing(2)
        input_frame = self.create_input_frame()
        config_frame = self.create_config_frame()
        top_layout.addWidget(input_frame)
        top_layout.addWidget(config_frame)
        bottom_frame = QFrame(objectName='bottom_frame')
        bottom_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        bottom_frame.setMinimumHeight(420)
        bottom_layout = QHBoxLayout(bottom_frame)
        bottom_layout.setSpacing(2)
        bottom_layout.setContentsMargins(5, 5, 5, 5)
        progress_frame = self.create_progress_frame()
        output_frame = self.create_output_frame()
        bottom_layout.addWidget(progress_frame)
        bottom_layout.addWidget(output_frame)
        main_layout.addWidget(top_frame)
        main_layout.addWidget(bottom_frame)
    def create_input_frame(self) -> QFrame:
        """Tạo frame nhập liệu."""
        input_frame = QFrame(objectName='input_frame')
        input_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        input_frame.setMinimumWidth(780)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(5, 5, 5, 5)
        input_layout.setSpacing(5)
        video_controls = QHBoxLayout()
        self.btn_main = self.create_video_button('Main Videos (0)', self.select_main_videos, '#e3f2fd', '#1976d2', '#bbdefb')
        self.btn_intro = self.create_video_button('Intro Videos (0)', self.select_intro_videos, '#c8e6c9', '#2e7d32', '#a5d6a7')
        self.btn_outro = self.create_video_button('Outro Videos (0)', self.select_outro_videos, '#ffe0b2', '#f57c00', '#ffb74d')
        self.btn_delete = self.create_video_button('Delete', self.delete_selected_videos, '#ffcdd2', '#c62828', '#ef9a9a', delete=True)
        self.btn_delete.setEnabled(False)
        video_controls.addWidget(self.btn_main)
        video_controls.addWidget(self.btn_intro)
        video_controls.addWidget(self.btn_outro)
        video_controls.addWidget(self.btn_delete)
        video_controls.addStretch()
        help_btn = self.create_video_button('❓ Help', self.show_help, '#e3f2fd', '#1976d2', '#bbdefb')
        video_controls.addWidget(help_btn)
        input_layout.addLayout(video_controls)
        tree_frame = QFrame()
        tree_frame.setStyleSheet('QFrame { border: 1px solid #dee2e6; border-radius: 4px; }')
        tree_layout = QVBoxLayout(tree_frame)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(0)
        self.tree_videos = QTreeWidget()
        self.tree_videos.setHeaderLabels(['Type', 'No.', 'Filename', 'Duration', 'Resolution'])
        self.tree_videos.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree_videos.setAlternatingRowColors(True)
        self.tree_videos.header().setDefaultAlignment(Qt.AlignCenter)
        self.tree_videos.setColumnWidth(0, 80)
        self.tree_videos.setColumnWidth(1, 50)
        self.tree_videos.setColumnWidth(2, 400)
        self.tree_videos.setColumnWidth(3, 100)
        self.tree_videos.setColumnWidth(4, 120)
        tree_layout.addWidget(self.tree_videos)
        input_layout.addWidget(tree_frame)
        return input_frame
    def create_video_button(self, text: str, callback, bg_color: str, text_color: str, border_color: str, delete: bool=False) -> QPushButton:
        """Tạo nút video với style tùy chỉnh."""
        button = QPushButton(text)
        button.setFixedWidth(150)
        button.setFixedHeight(30)
        button.clicked.connect(callback)
        button.setStyleSheet(f'\n            QPushButton {{\n                background-color: {bg_color};\n                color: {text_color};\n                border: 1px solid {border_color};\n                border-radius: 4px;\n                padding: 5px 10px;  /* Giảm padding */\n                font-weight: bold;\n            }}\n            QPushButton:hover {{\n                background-color: {border_color};\n            }}\n        ')
        if delete:
            button.setProperty('delete', True)
        return button
    def create_config_frame(self) -> QFrame:
        """Tạo frame cấu hình."""
        config_frame = QFrame(objectName='config_frame')
        config_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        config_frame.setMinimumWidth(780)
        config_layout = QVBoxLayout(config_frame)
        config_layout.setContentsMargins(5, 5, 5, 5)
        config_layout.setSpacing(5)
        merge_options = QFrame(objectName='sub_frame')
        form_layout = QVBoxLayout(merge_options)
        form_layout.setContentsMargins(10, 5, 10, 5)
        form_layout.setSpacing(5)
        configs = [('Main Mix Mode', 'combo_merge_mode_main', ['Random', 'Sequential'], 200), ('Intro Mix Mode', 'combo_merge_mode_intro', ['Random', 'Sequential'], 200), ('Outro Mix Mode', 'combo_merge_mode_outro', ['Random', 'Sequential'], 200), ('Main Videos to Mix', 'combo_num_merge', [], 100, True), ('Total Output Videos', 'combo_num_output', [], 100, True), ('Output Name Option', 'combo_output_naming', ['Time + Index', 'First Video Name + Time + Index'], 400)]
        for config in configs:
            if len(config) == 5:
                label_text, attr_name, items, width, editable = config
            else:
                label_text, attr_name, items, width = config
                editable = False
            row_container = QFrame()
            row_layout = QHBoxLayout(row_container)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)
            label = QLabel(label_text)
            label.setFixedWidth(150)
            label.setFixedHeight(25)
            label.setProperty('class', 'config_label')
            combo = QComboBox()
            combo.setFixedWidth(width)
            combo.setFixedHeight(25)
            combo.addItems(items)
            if editable:
                combo.setEditable(True)
            row_layout.addWidget(label)
            row_layout.addWidget(combo)
            row_layout.addStretch(1)
            form_layout.addWidget(row_container)
            setattr(self, attr_name, combo)
        form_layout.addStretch(1)
        config_layout.addWidget(merge_options)
        return config_frame
    def create_progress_frame(self) -> QFrame:
        """Tạo frame tiến trình."""
        progress_frame = QFrame(objectName='progress_frame')
        progress_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        progress_frame.setMinimumWidth(780)
        progress_frame.setFrameStyle(QFrame.StyledPanel)
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setSpacing(5)
        progress_layout.setContentsMargins(5, 5, 5, 5)
        progress_info_frame = QFrame(objectName='progress_info_frame')
        progress_info_layout = QHBoxLayout(progress_info_frame)
        progress_info_layout.setContentsMargins(10, 5, 10, 5)
        self.progress_label = QLabel('Progress: 0/0')
        self.progress_label.setProperty('class', 'status_label')
        self.current_label = QLabel('Waiting')
        self.current_label.setProperty('class', 'status_label')
        progress_info_layout.addWidget(self.progress_label)
        progress_info_layout.addWidget(self.current_label)
        progress_layout.addWidget(progress_info_frame)
        self.canvas = QFrame(objectName='canvas')
        box_size, padding, boxes_per_row, num_rows = (12, 2, 50, 15)
        canvas_height = num_rows * (box_size + padding) + padding
        self.canvas.setFixedHeight(canvas_height)
        progress_layout.addWidget(self.canvas)
        self.boxes_per_row = boxes_per_row
        self.box_size = box_size
        self.padding = padding
        self.progress_boxes = []
        thread_frame = QFrame()
        thread_frame.setFixedHeight(150)
        thread_layout = QVBoxLayout(thread_frame)
        thread_layout.setSpacing(10)
        self.thread_bars = []
        self.thread_labels = []
        for i in range(3):
            thread_row = QHBoxLayout(spacing=8)
            label = QLabel(f'IDLE #{i + 1}')
            label.setFixedWidth(70)
            label.setProperty('class', 'status_label')
            status = QLabel('Waiting')
            status.setFixedWidth(250)
            status.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            status.setProperty('class', 'status_label')
            progress = QProgressBar()
            progress.setFixedHeight(25)
            thread_row.addWidget(label)
            thread_row.addWidget(status)
            thread_row.addWidget(progress, stretch=1)
            thread_layout.addLayout(thread_row)
            self.thread_bars.append(progress)
            self.thread_labels.append(status)
        progress_layout.addWidget(thread_frame)
        progress_layout.addStretch(1)
        return progress_frame
    def create_output_frame(self) -> QFrame:
        """Tạo frame đầu ra."""
        output_frame = QFrame(objectName='output_frame')
        output_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        output_frame.setMinimumWidth(780)
        output_frame.setFrameStyle(QFrame.StyledPanel)
        output_layout = QVBoxLayout(output_frame)
        output_layout.setSpacing(5)
        output_layout.setContentsMargins(5, 5, 5, 5)
        controls_frame = QFrame(objectName='sub_frame')
        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.setContentsMargins(5, 5, 5, 5)
        controls_layout.setSpacing(5)
        top_controls = QHBoxLayout(spacing=5)
        dir_btn = QPushButton('📍 Directory')
        dir_btn.setFixedWidth(150)
        dir_btn.setFixedHeight(30)
        dir_btn.setToolTip('Select Output Directory')
        dir_btn.clicked.connect(self.select_output_directory)
        self.dir_label = QLabel('Not selected')
        top_controls.addWidget(dir_btn)
        top_controls.addWidget(self.dir_label, stretch=1)
        open_btn = QPushButton('📂 Open')
        open_btn.setFixedWidth(150)
        open_btn.setFixedHeight(30)
        open_btn.setToolTip('Open Output Directory')
        open_btn.clicked.connect(self.open_output_directory)
        top_controls.addWidget(open_btn)
        bottom_controls = QHBoxLayout(spacing=5)
        bottom_controls.addStretch(1)
        self.btn_start = QPushButton('🚀 Start')
        self.btn_start.setFixedWidth(150)
        self.btn_start.setFixedHeight(30)
        self.btn_start.setToolTip('Start Merging')
        self.btn_start.clicked.connect(self.start_merge)
        self.btn_cancel = QPushButton('🛑 Stop')
        self.btn_cancel.setFixedWidth(150)
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.setToolTip('Stop Merging')
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setProperty('delete', True)
        self.btn_cancel.clicked.connect(self.cancel_merge)
        bottom_controls.addWidget(self.btn_start)
        bottom_controls.addWidget(self.btn_cancel)
        bottom_controls.addStretch(1)
        controls_layout.addLayout(top_controls)
        controls_layout.addLayout(bottom_controls)
        output_layout.addWidget(controls_frame)
        tree_frame = QFrame()
        tree_frame.setStyleSheet('QFrame { border: 1px solid #dee2e6; border-radius: 4px; }')
        tree_layout = QVBoxLayout(tree_frame)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(0)
        self.tree_output = QTreeWidget()
        self.tree_output.setHeaderLabels(['No.', 'Input Videos', 'Output Video', 'Duration', 'Resolution', 'Status'])
        self.tree_output.setAlternatingRowColors(True)
        self.tree_output.header().setDefaultAlignment(Qt.AlignCenter)
        self.tree_output.setColumnWidth(0, 50)
        self.tree_output.setColumnWidth(1, 100)
        self.tree_output.setColumnWidth(2, 300)
        self.tree_output.setColumnWidth(3, 100)
        self.tree_output.setColumnWidth(4, 100)
        self.tree_output.setColumnWidth(5, 100)
        tree_layout.addWidget(self.tree_output)
        output_layout.addWidget(tree_frame)
        return output_frame
    def setup_style(self):
        self.setStyleSheet('\n            QMainWindow { background-color: #f8f9fa; }\n            QFrame#top_frame, QFrame#bottom_frame { background-color: transparent; border: none; }\n            QFrame#input_frame, QFrame#config_frame, QFrame#progress_frame, QFrame#output_frame {\n                background-color: white; border: 2px solid #dee2e6; border-radius: 8px;\n            }\n            QFrame#sub_frame { background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; }\n            QLabel#sub_title { color: #495057; font-size: 14px; font-weight: bold; padding: 5px; }\n            QLabel { padding: 5px; }\n            QLabel#dir_label { padding-left: 10px; padding-right: 10px; }\n            QLabel.status_label { \n                color: #1976d2; \n                font-weight: bold; \n                background-color: #e3f2fd; \n                border: 1px solid #bbdefb; \n                border-radius: 4px; \n                padding: 4px 8px; \n            }\n            QLabel.config_label {\n                color: #1976d2;\n                font-weight: bold;\n                font-size: 11px;\n                padding: 2px 4px;\n                background-color: #e3f2fd;\n                border: 1px solid #bbdefb;\n                border-radius: 3px;\n            }\n            QPushButton {\n                background-color: #007bff; color: white; border: none; border-radius: 4px; padding: 5px 10px;\n                min-width: 100px; max-width: 120px; font-weight: bold; font-size: 12px;\n            }\n            QPushButton:hover { background-color: #0056b3; }\n            QPushButton:disabled { background-color: #6c757d; }\n            QPushButton[delete=\"true\"] { background-color: #dc3545; }\n            QPushButton[delete=\"true\"]:hover { background-color: #c82333; }\n            QTreeWidget { border: 1px solid #dee2e6; border-radius: 4px; }\n            QTreeWidget::item { padding: 5px; border-bottom: 1px solid #dee2e6; }\n            QTreeWidget::item:selected { background-color: #007bff; color: white; }\n            QHeaderView::section { \n                background-color: #e3f2fd; \n                padding: 5px; \n                border: 1px solid #bbdefb; \n                font-weight: bold; \n                text-align: center; \n                color: #1976d2; \n            }\n            QProgressBar { \n                border: 1px solid #dee2e6; \n                border-radius: 4px; \n                text-align: center; \n                background-color: #f8f9fa; \n                font-weight: bold; \n            }\n            QProgressBar::chunk { background-color: #e3f2fd; border-radius: 3px; }\n            QTextEdit { background-color: black; color: white; font-family: Consolas; border-radius: 4px; }\n            QFrame#progress_info_frame { background-color: #e3f2fd; border: 1px solid #bbdefb; border-radius: 4px; }\n            QFrame#canvas { background-color: #f0f0f0; border: none; }\n            QComboBox {\n                border: 1px solid #bdc3c7;\n                border-radius: 3px;\n                padding: 1px 12px 1px 3px;\n                background: white;\n                min-height: 20px;\n                font-size: 11px;\n            }\n            QComboBox:hover { \n                border-color: #3498db; \n            }\n            QComboBox:focus { \n                border-color: #2980b9; \n            }\n            QComboBox::drop-down {\n                border: none;\n                width: 12px;\n            }\n            QComboBox::down-arrow {\n                width: 4px;\n                height: 4px;\n                margin-right: 4px;\n                image: none;\n                border: none;\n                border-radius: 2px;\n                background-color: #3498db;\n                opacity: 0.7;\n            }\n            QComboBox::down-arrow:hover {\n                background-color: #2980b9;\n                opacity: 1;\n            }\n            QComboBox::down-arrow:on {\n                background-color: #2980b9;\n                opacity: 1;\n            }\n            QComboBox QAbstractItemView {\n                border: 1px solid #bdc3c7;\n                selection-background-color: #3498db;\n                selection-color: white;\n                background: white;\n                font-size: 11px;\n            }\n        ')
    def load_config(self) -> dict:
        """Tải cấu hình từ file."""
        default_config = {'version': 1}
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    json.load(f)
            except json.JSONDecodeError:
                QMessageBox.warning(self, 'Warning', 'Configuration file corrupted. Using default.')
                return default_config
        config = core_config.load(Path(CONFIG_FILE), default=default_config)
        return config if config.get('version', 1) == 1 else default_config
    def save_config(self):
        """Lưu cấu hình vào file."""
        try:
            config = {'version': 1, 'last_output_dir': self.output_directory, 'last_videos_dir': os.path.dirname(self.video_list[0]) if self.video_list else '', 'last_intro_video_dir': os.path.dirname(self.intro_videos[0]) if self.intro_videos else '', 'last_outro_video_dir': self.outro_videos, 'last_videos': os.path.dirname(self.combo_merge_mode_main.currentText()), 'last_intro_videos': self.combo_merge_mode_intro.currentText(), 'last_outro_videos': self.combo_merge_mode_outro.currentText(), 'merge_mode_main': self.combo_output_naming.currentText()}
            core_config.save(Path(CONFIG_FILE), config)
        except (OSError, TypeError) as e:
            QMessageBox.warning(self, 'Warning', f'Cannot save configuration: {str(e)}')
    def update_video_counts(self):
        """Cập nhật số lượng video trên các nút."""
        self.btn_main.setText(f'Main Videos ({len(self.video_list)})')
        self.btn_intro.setText(f'Intro Videos ({len(self.intro_videos)})')
        self.btn_outro.setText(f'Outro Videos ({len(self.outro_videos)})')
    def select_videos(self, video_list: List[str], title: str, config_key: str):
        """Chọn video từ hệ thống tệp."""
        try:
            initial_dir = self.config.get(config_key, os.getcwd())
            file_paths, _ = QFileDialog.getOpenFileNames(self, title, initial_dir, 'Video Files (*.mp4 *.avi *.mkv)')
            if file_paths:
                new_files = [fp for fp in file_paths if fp not in video_list]
                if not new_files:
                    QMessageBox.information(self, 'Information', 'No new videos added.')
                    return
                video_list.extend(new_files)
                self.update_video_tree()
                self.btn_delete.setEnabled(True)
                self.update_video_counts()
                self.logger.info(f'Added {len(new_files)} videos to {title}.')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Cannot select videos: {str(e)}')
    def select_main_videos(self):
        self.select_videos(self.video_list, 'Select Main Videos', 'last_videos_dir')
    def select_intro_videos(self):
        self.select_videos(self.intro_videos, 'Select Intro Videos', 'last_intro_video_dir')
    def select_outro_videos(self):
        self.select_videos(self.outro_videos, 'Select Outro Videos', 'last_outro_video_dir')
    def delete_selected_videos(self):
        """Xóa các video được chọn."""
        selected_items = self.tree_videos.selectedItems()
        if not selected_items:
            QMessageBox.information(self, 'Information', 'No video selected to delete.')
            return
        else:
            for item in selected_items:
                video_type, filename = (item.text(0), item.text(2))
                video_list = {'Main': self.video_list, 'Intro': self.intro_videos, 'Outro': self.outro_videos}.get(video_type)
                if video_list:
                    video_list[:] = [v for v in video_list if os.path.basename(v)!= filename]
            self.update_video_tree()
            self.btn_delete.setEnabled(bool(self.video_list or self.intro_videos or self.outro_videos))
            self.update_video_counts()
    def fetch_video_metadata(self, video_path: str) -> Tuple[str, str, str]:
        """Lấy metadata của video."""
        try:
            return (video_path, self.get_video_duration(video_path), self.get_video_resolution(video_path))
        except Exception as e:
            self.logger.error(f'Error getting video info for {video_path}: {str(e)}')
            return (video_path, 'Unknown', 'Unknown')
    def update_video_tree(self):
        """Cập nhật tree widget với danh sách video."""
        self.tree_videos.clear()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            video_types = [(self.video_list, 'Main', '#007bff'), (self.intro_videos, 'Intro', '#28a745'), (self.outro_videos, 'Outro', '#fd7e14')]
            counters = {'Main': 1, 'Intro': 1, 'Outro': 1}
            for videos, video_type, color in video_types:
                for video in videos:
                    futures.append((executor.submit(self.fetch_video_metadata, video), video_type, color))
            for future, video_type, color in futures:
                video_path, duration, resolution = future.result()
                item = QTreeWidgetItem(self.tree_videos)
                item.setText(0, video_type)
                item.setText(1, str(counters[video_type]))
                item.setText(2, os.path.basename(video_path))
                item.setText(3, duration)
                item.setText(4, resolution)
                item.setForeground(0, QColor(color))
                counters[video_type] += 1
        max_videos = len(self.video_list)
        self.combo_num_merge.clear()
        self.combo_num_merge.addItems((str(i) for i in range(1, max_videos + 1)))
        if max_videos > 0:
            self.combo_num_merge.setCurrentText('2')
        self.combo_num_output.clear()
        self.combo_num_output.addItems(['1', '5', '10', '20', '50', '100', '200', '500', '1000'])
        self.combo_num_output.setCurrentText('1')
    def get_video_duration(self, video_path: str) -> str:
        """Lấy thời lượng video."""
        cmd = [str(FFPROBE_PATH), '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
        startupinfo = subprocess.STARTUPINFO() if os.name == 'nt' else None
        if startupinfo:
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, encoding='utf-8', errors='replace')
        duration_seconds = float(result.stdout.strip())
        hours, remainder = divmod(int(duration_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}'
    def get_video_resolution(self, video_path: str) -> str:
        """Lấy độ phân giải video."""
        cmd = [str(FFPROBE_PATH), '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0', video_path]
        startupinfo = subprocess.STARTUPINFO() if os.name == 'nt' else None
        if startupinfo:
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, encoding='utf-8', errors='replace')
        return result.stdout.strip() or 'Unknown'
    def select_output_directory(self):
        """Chọn thư mục đầu ra."""
        try:
            output_dir = QFileDialog.getExistingDirectory(self, 'Select Output Directory', self.output_directory or os.getcwd())
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
        """Cập nhật màu của progress box."""
        if 0 <= index < len(self.progress_boxes):
            styles = {'green': 'background-color: #4CAF50; border: 1px solid #2E7D32;', 'yellow': 'background-color: #FFC107; border: 1px solid #FFA000;', 'red': 'background-color: #F44336; border: 1px solid #D32F2F;', 'default': 'background-color: lightgray; border: 1px solid #666666;'}
            self.progress_boxes[index].setStyleSheet(f"{styles.get(color, styles['default'])} border-radius: 2px;")
    def clear_progress_boxes(self):
        """Xóa tất cả progress boxes."""
        for box in self.progress_boxes:
            box.deleteLater()
        self.progress_boxes.clear()
    def start_merge(self):
        """Bắt đầu quá trình gộp video."""
        if self.is_merging:
            if QMessageBox.question(self, 'Confirm', 'Merging in progress. Do you want to cancel and start new?', QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.cancel_merge()
            else:
                return None
        if not self.validate_inputs():
            return
        else:
            self.is_merging = True
            self.btn_start.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.total_output = int(self.combo_num_output.currentText())
            self.processed_output = 0
            self.progress_label.setText(f'Progress: 0/{self.total_output}')
            self.current_label.setText('Merging: None')
            self.tree_output.clear()
            self.cancel_event.clear()
            self.clear_progress_boxes()
            self.progress_boxes.extend((self.create_progress_box(i) for i in range(self.total_output)))
            threading.Thread(target=self.merge_videos, daemon=True).start()
    def cancel_merge(self):
        """Hủy quá trình gộp video."""
        if self.is_merging:
            self.cancel_event.set()
            self.btn_cancel.setEnabled(False)
            for i in range(self.processed_output, len(self.progress_boxes)):
                self.update_box_color(i, 'red')
            for label, bar in zip(self.thread_labels, self.thread_bars):
                label.setText('Cancelled')
                bar.setValue(0)
            QMessageBox.information(self, 'Information', 'Merging cancelled.')
    def validate_inputs(self) -> bool:
        """Kiểm tra đầu vào hợp lệ."""
        if not self.video_list:
            QMessageBox.warning(self, 'Warning', 'Please select at least one main video.')
            return False
        if not self.output_directory:
            QMessageBox.warning(self, 'Warning', 'Please select output directory.')
            return False
        try:
            num_merge = int(self.combo_num_merge.currentText())
            if num_merge < 1 or num_merge > len(self.video_list):
                QMessageBox.warning(self, 'Warning', 'Invalid number of videos to mix.')
                return False
            num_output = int(self.combo_num_output.currentText())
            if num_output < 1:
                QMessageBox.warning(self, 'Warning', 'Total output videos must be at least 1.')
                return False
            if self.intro_videos and (not all((os.path.exists(v) for v in self.intro_videos))):
                QMessageBox.warning(self, 'Warning', 'Some intro videos are missing.')
                return False
            if self.outro_videos and (not all((os.path.exists(v) for v in self.outro_videos))):
                QMessageBox.warning(self, 'Warning', 'Some outro videos are missing.')
                return False
            return True
        except ValueError:
            QMessageBox.warning(self, 'Warning', 'Please enter valid numbers for mix options.')
            return False
    def merge_videos(self):
        """Thực hiện gộp video."""
        try:
            num_merge = int(self.combo_num_merge.currentText())
            num_output = int(self.combo_num_output.currentText())
            merge_modes = {'main': self.combo_merge_mode_main.currentText(), 'intro': self.combo_merge_mode_intro.currentText(), 'outro': self.combo_merge_mode_outro.currentText()}
            for i in range(num_output):
                if self.cancel_event.is_set():
                    break
                else:
                    videos_to_merge = self.select_videos_to_merge(merge_modes['main'], num_merge, i + 1, self.video_list)
                    if not videos_to_merge:
                        self.logger.warning(f'No videos to mix for output {i + 1}. Skipping.')
                        continue
                    else:
                        if self.intro_videos:
                            intro_videos = self.select_videos_to_merge(merge_modes['intro'], 1, i + 1, self.intro_videos)
                            if intro_videos:
                                videos_to_merge = intro_videos + videos_to_merge
                        if self.outro_videos:
                            outro_videos = self.select_videos_to_merge(merge_modes['outro'], 1, i + 1, self.outro_videos)
                            if outro_videos:
                                videos_to_merge.extend(outro_videos)
                        current_time = datetime.now().strftime('%d%m%y_%H%M%S')
                        output_naming = self.combo_output_naming.currentText()
                        if output_naming == 'First Video Name + Time + Index':
                            first_video_name = os.path.splitext(os.path.basename(videos_to_merge[0]))[0]
                            prefix = f'{first_video_name}_{current_time}'
                        else:
                            prefix = current_time
                        output_filename = f'{prefix}_{i + 1:03}.mp4'
                        output_path = os.path.join(self.output_directory, output_filename)
                        item = QTreeWidgetItem(self.tree_output)
                        item.setText(0, str(i + 1))
                        item.setText(1, ', '.join((os.path.basename(v) for v in videos_to_merge)))
                        item.setText(2, output_filename)
                        item.setText(3, 'Processing')
                        item.setText(4, 'N/A')
                        item.setText(5, '🔄 Processing...')
                        worker = MergeWorker(videos_to_merge, output_path, i % 3, FFMPEG_PATH)
                        worker.setAutoDelete(True)
                        worker.signals.progress_updated.connect(self.update_thread_progress)
                        worker.signals.status_updated.connect(self.update_thread_status)
                        worker.signals.output_updated.connect(self.update_ffmpeg_output)
                        worker.signals.merge_completed.connect(self.on_merge_completed)
                        worker.signals.error_occurred.connect(self.on_merge_error)
                        self.thread_pool.start(worker)
                        QThread.msleep(500)
        except Exception as e:
            self.logger.error(f'Error mixing: {str(e)}')
            QMessageBox.critical(self, 'Error', f'Unexpected error occurred: {str(e)}')
        finally:
            self.is_merging = False
            self.btn_start.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.save_config()
    def select_videos_to_merge(self, mode: str, num_merge: int, index: int, video_list: List[str]) -> List[str]:
        """Chọn video để gộp."""
        videos = video_list.copy()
        if mode == 'Random':
            return random.sample(videos, min(num_merge, len(videos)))
        else:
            if mode == 'Sequential':
                start = (index - 1) * num_merge
                selected = videos[start:start + num_merge]
                if len(selected) < num_merge and videos:
                        selected += videos[:num_merge - len(selected)]
                return selected
            else:
                return []
    def update_thread_progress(self, thread_index: int, progress: int):
        if 0 <= thread_index < len(self.thread_bars):
            self.thread_bars[thread_index].setValue(progress)
    def update_thread_status(self, thread_index: int, status: str):
        if 0 <= thread_index < len(self.thread_labels):
            self.thread_labels[thread_index].setText(status)
    def update_ffmpeg_output(self, output: str):
        for i in range(self.tree_output.topLevelItemCount()):
            item = self.tree_output.topLevelItem(i)
            if item.text(5) == 'Processing' and 'time=' in output:
                    item.setText(5, '🔄 Processing...')
                    break
    def on_merge_completed(self, output_filename: str):
        self.processed_output += 1
        self.progress_label.setText(f'Progress: {self.processed_output}/{self.total_output}')
        self.update_box_color(self.processed_output - 1, 'green')
        for i in range(self.tree_output.topLevelItemCount()):
            item = self.tree_output.topLevelItem(i)
            if item.text(2) == output_filename:
                output_path = os.path.join(self.output_directory, output_filename)
                item.setText(3, self.get_video_duration(output_path))
                item.setText(4, self.get_video_resolution(output_path))
                item.setText(5, '🟢 Completed')
                break
    def on_merge_error(self, error_message: str):
        self.update_box_color(self.processed_output, 'red')
        self.processed_output += 1
        for i in range(self.tree_output.topLevelItemCount()):
            item = self.tree_output.topLevelItem(i)
            if item.text(5) == 'Processing':
                item.setText(3, 'N/A')
                item.setText(4, 'N/A')
                item.setText(5, '🔴 Error')
                break
    def load_last_paths(self):
        """Tải các đường dẫn trước đó từ config."""
        config = self.config
        self.combo_merge_mode_main.setCurrentText(config.get('merge_mode_main', 'Random'))
        self.combo_merge_mode_intro.setCurrentText(config.get('merge_mode_intro', 'Random'))
        self.combo_merge_mode_outro.setCurrentText(config.get('merge_mode_outro', 'Random'))
        last_output = config.get('last_output_dir', '')
        if last_output and os.path.isdir(last_output):
                self.output_directory = last_output
                self.dir_label.setText(f'Output Directory: {self.output_directory}')
        for video_list, attr in [(config.get('last_videos', []), 'video_list'), (config.get('last_intro_videos', []), 'intro_videos'), (config.get('last_outro_videos', []), 'outro_videos')]:
            valid_videos = [v for v in video_list if os.path.isfile(v)]
            if valid_videos:
                setattr(self, attr, valid_videos)
                self.btn_delete.setEnabled(True)
        naming = config.get('output_naming', 'Time + Index')
        self.combo_output_naming.setCurrentText(naming)
        self.update_video_tree()
        self.update_video_counts()
    def closeEvent(self, event):
        if self.is_merging:
            if QMessageBox.question(self, 'Exit', 'Merging in progress. Do you really want to exit?', QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.cancel_merge()
                self.save_config()
                event.accept()
            else:
                event.ignore()
        else:
            self.save_config()
            event.accept()
    def open_output_directory(self):
        """Mở thư mục đầu ra."""
        if not (self.output_directory and os.path.exists(self.output_directory)):
            QMessageBox.warning(self, 'Warning', 'Please select output directory first')
            return
        if os.name == 'nt':
            os.startfile(self.output_directory)
        else:
            try:
                subprocess.run(['xdg-open', self.output_directory], check=True)
            except (FileNotFoundError, subprocess.CalledProcessError):
                try:
                    subprocess.run(['open', self.output_directory], check=True)
                except (FileNotFoundError, subprocess.CalledProcessError):
                    QMessageBox.warning(self, 'Error', 'Cannot open directory')
    def show_help(self):
        """Hiển thị dialog help"""
        readme_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'README Mixer.md')
        dialog = HelpDialog(self, 'Help - 1vmo Mixer', readme_path)
        dialog.exec_()
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = VideoMergerTool()
    window.show()
    sys.exit(app.exec_())