# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'Code Cutter.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

import os
import sys
import json
import subprocess
import threading
import logging
import re
import glob
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional
import requests
import tempfile
import shutil
import multiprocessing
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QTreeWidget, QTreeWidgetItem, QComboBox, QFileDialog, QFrame, QMessageBox, QLineEdit, QSpinBox, QDialog, QSizePolicy
from PyQt5.QtCore import Qt, QThreadPool, QRunnable, pyqtSignal, QObject, QThread, QTimer
from PyQt5.QtGui import QIcon, QColor
from updater import DriveUpdater
from help_dialog import HelpDialog
from core import config as core_config
from core import file_picker as core_file_picker
from core import widgets as core_widgets
SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
FFMPEG_PATH = SCRIPT_DIR / 'ffmpeg' / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
FFPROBE_PATH = SCRIPT_DIR / 'ffmpeg' / ('ffprobe.exe' if os.name == 'nt' else 'ffprobe')
ICON_PATH = SCRIPT_DIR / 'assets' / 'Cutter.ico'
CONFIG_FILE = SCRIPT_DIR / 'config_video_cutter.json'
logging.basicConfig(filename='video_cutter.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
class FFmpegError(Exception):
    # return None
    pass
class MetadataError(Exception):
    # return None
    pass
COMMON_STYLE = '\n    QMainWindow { background-color: #f8f9fa; }\n    QFrame#top_frame, QFrame#bottom_frame, QFrame#videos_frame, QFrame#options_frame,\n    QFrame#progress_frame, QFrame#output_frame {\n        background-color: white; border: 1px solid #dee2e6; border-radius: 4px;\n    }\n    QPushButton {\n        background-color: #007bff; color: white; border: none; border-radius: 4px;\n        padding: 8px 16px; min-width: 100px; max-width: 100px; font-weight: bold;\n    }\n    QPushButton:hover { background-color: #0056b3; }\n    QPushButton:disabled { background-color: #6c757d; }\n    QPushButton[delete=\"true\"] { background-color: #dc3545; }\n    QPushButton[delete=\"true\"]:hover { background-color: #c82333; }\n    QTreeWidget { border: 1px solid #dee2e6; }\n'
class WorkerSignals(QObject):
    progress_updated = pyqtSignal(int, int)
    status_updated = pyqtSignal(int, str)
    output_updated = pyqtSignal(str)
    cut_completed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
def sanitize_filename(filename: str) -> str:
    base_name, ext = os.path.splitext(filename)
    has_numbering = '_%03d' in base_name
    if has_numbering:
        base_name = base_name.replace('_%03d', '')
    base_name = re.sub('[^\\w\\s.]|_+|\\s+', '_', base_name).strip('_')[:200]
    return f'{base_name}_%03d{ext}' if has_numbering else f'{base_name}{ext}'
class CutWorker(QRunnable):
    def __init__(self, input_file: str, output_path: str, thread_index: int, ffmpeg_path: Path, cut_params: dict, ffmpeg_params: list):
        super().__init__()
        self.input_file = input_file
        self.output_path = output_path
        self.thread_index = thread_index
        self.ffmpeg_path = ffmpeg_path
        self.cut_params = cut_params
        self.ffmpeg_params = ffmpeg_params
        self.is_cancelled = False
        self.signals = WorkerSignals()
        self.logger = logging.getLogger(__name__)
    def get_startupinfo(self):
        startupinfo = subprocess.STARTUPINFO() if os.name == 'nt' else None
        if startupinfo:
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startupinfo
    def run(self):
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                self.signals.status_updated.emit(self.thread_index, f'Processing: {os.path.basename(self.output_path)}')
                self.signals.progress_updated.emit(self.thread_index, 0)
                self.signals.output_updated.emit(f'\n[Thread {self.thread_index + 1}] Processing: {os.path.basename(self.output_path)}\n')
                if not os.path.exists(self.input_file):
                    raise FileNotFoundError(f'Input file not found: {self.input_file}')
                output_dir = os.path.dirname(self.output_path)
                output_filename = sanitize_filename(os.path.basename(self.output_path))
                temp_output = os.path.join(temp_dir, output_filename)
                final_output = os.path.join(output_dir, output_filename)
                if not os.path.isdir(output_dir):
                    raise ValueError(f'Output directory does not exist: {output_dir}')
                command = [str(self.ffmpeg_path), '-y', '-i', self.input_file, '-progress', 'pipe:1']
                mode = self.cut_params.get('mode')
                total_duration = self.get_video_duration()
                command.extend(self.ffmpeg_params)
                if mode == 'split_by_time':
                    duration = self.cut_params['duration']
                    num_segments = max(1, int(total_duration // duration) + (1 if total_duration % duration >= 1 else 0))
                    command.extend(['-f', 'segment', '-segment_time', str(duration), '-segment_time_delta', '0.5', '-reset_timestamps', '1', '-segment_format', 'mp4', '-force_key_frames', f'expr:gte(t,n_forced*{duration})', temp_output])
                else:
                    if mode == 'split_by_parts':
                        parts = max(1, self.cut_params['parts'])
                        segment_time = total_duration / parts
                        command.extend(['-f', 'segment', '-segment_time', str(segment_time), '-reset_timestamps', '1', '-segment_format', 'mp4', '-force_key_frames', f'expr:gte(t,n_forced*{segment_time})', temp_output])
                    else:
                        if mode == 'trim_ends':
                            start = self.cut_params['start']
                            end = self.cut_params['end']
                            duration = total_duration - start - end
                            command.extend(['-ss', str(start), '-t', str(duration), temp_output])
                        else:
                            if mode == 'specific_range':
                                start = self.cut_params['start']
                                duration = self.cut_params['end'] - start
                                command.extend(['-ss', str(start), '-t', str(duration), temp_output])
                self.logger.info(f"FFmpeg command: {' '.join((str(x) for x in command))}")
                self.signals.output_updated.emit(f"FFmpeg command: {' '.join((str(x) for x in command))}\n")
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, startupinfo=self.get_startupinfo(), creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, text=True, encoding='utf-8', errors='replace')
                duration = self.get_video_duration()
                error_output = []
                while True:
                    if self.is_cancelled:
                        process.terminate()
                        process.wait()
                        self.signals.status_updated.emit(self.thread_index, 'Cancelled')
                        self.signals.progress_updated.emit(self.thread_index, 0)
                        return
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        return_code = process.wait()
                        if return_code == 0 and (not self.is_cancelled):
                            output_pattern = temp_output.replace('%03d', '*')
                            temp_files = glob.glob(output_pattern)
                            if temp_files and all((os.path.getsize(f) > 0 for f in temp_files)):
                                for temp_file in temp_files:
                                    segment_duration = self.get_segment_duration(temp_file)
                                    self.logger.info(f'Segment {temp_file}: Duration = {segment_duration}s')
                                    shutil.move(temp_file, final_output.replace('%03d', os.path.basename(temp_file)[(-7):(-4)]))
                                self.signals.status_updated.emit(self.thread_index, 'Completed')
                                self.signals.progress_updated.emit(self.thread_index, 100)
                                self.signals.output_updated.emit(f'\n[Thread {self.thread_index + 1}] Completed: {os.path.basename(self.output_path)}\n')
                                self.signals.cut_completed.emit(os.path.basename(self.output_path))
                            else:
                                raise RuntimeError(f'No valid output files created for: {self.output_path}')
                        else:
                            raise RuntimeError(f'FFmpeg error code {return_code}\n' + '\n'.join(error_output))
                        break
                    if line:
                        error_output.append(line)
                        self.signals.output_updated.emit(line)
                        time_match = re.search('out_time_ms=(\\d+)', line)
                        if time_match and duration:
                            time = int(time_match.group(1)) / 1000000
                            progress = min(int(time / duration * 100), 100)
                            self.signals.progress_updated.emit(self.thread_index, progress)
        except Exception as e:
            error_msg = f'Error processing {os.path.basename(self.output_path)}: {str(e)}'
            self.logger.error(error_msg)
            self.signals.error_occurred.emit(error_msg)
            self.signals.status_updated.emit(self.thread_index, 'Error')
            self.signals.progress_updated.emit(self.thread_index, 0)
            self.signals.output_updated.emit(f'\n[Thread {self.thread_index + 1}] {error_msg}\n')
    def get_video_duration(self) -> float:
        try:
            cmd = [str(FFPROBE_PATH), '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', self.input_file]
            result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=self.get_startupinfo(), creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, encoding='utf-8', errors='replace')
            if result.returncode!= 0:
                raise FFmpegError(f'FFprobe error: {result.stderr}')
            else:
                return float(result.stdout.strip())
        except Exception as e:
            self.logger.error(f'Error getting video duration: {str(e)}')
            raise MetadataError(f'Failed to get duration: {str(e)}')
    def get_segment_duration(self, file_path: str) -> float:
        try:
            cmd = [str(FFPROBE_PATH), '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=self.get_startupinfo(), creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, encoding='utf-8', errors='replace')
            if result.returncode!= 0:
                raise FFmpegError(f'FFprobe error: {result.stderr}')
            else:
                return float(result.stdout.strip())
        except Exception as e:
            self.logger.error(f'Error getting segment duration for {file_path}: {str(e)}')
            return 0.0
class VideoCutterTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.is_boost_mode = False
        if not FFMPEG_PATH.exists() or not FFPROBE_PATH.exists():
            QMessageBox.critical(self, 'Error', 'FFmpeg or FFprobe not found. Please place them in the \'ffmpeg\' directory.')
            sys.exit(1)
        self.updater = DriveUpdater()
        self.current_version = self.updater._load_current_version('1vmo Cutter') or '3.1'
        self.updater._save_current_version(self.current_version, '1vmo Cutter')
        self.setWindowTitle(f'1vmo Cutter v{self.current_version}')
        self.setGeometry(100, 100, 1600, 900)
        # Allow resize and maximize — set a reasonable minimum so layouts don't
        # collapse below their designed size, and use resize() for initial geometry.
        self.setMinimumSize(1600, 900)
        self.resize(1600, 900)
        self.updater.check_and_update('1vmo Cutter')
        self.setup_icon()
        self.initialize_state()
        self.config = self.load_config()
        self.setup_ui()
        self.setup_style()
        self.load_last_paths()
        self.progress_update_queue = []
        self.ui_update_timer = QTimer()
        self.ui_update_timer.timeout.connect(self.process_ui_updates)
        self.ui_update_timer.start(500)
    def setup_icon(self):
        try:
            if ICON_PATH.exists():
                app_icon = QIcon(str(ICON_PATH))
                self.setWindowIcon(app_icon)
                QApplication.setWindowIcon(app_icon)
                if os.name == 'nt':
                    import ctypes
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('1vmo.VideoCutter.1.0.0')
        except Exception as e:
            self.logger.error(f'Error setting up icon: {str(e)}')
    def initialize_state(self):
        self.video_list = []
        self.output_directory = ''
        self.is_processing = False
        self.total_output = 0
        self.processed_output = 0
        self.cancel_event = threading.Event()
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(min(multiprocessing.cpu_count(), 8))
        self.video_metadata_cache = {}
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
        input_frame = QFrame(objectName='input_frame')
        input_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        input_frame.setMinimumWidth(780)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(5, 5, 5, 5)
        input_layout.setSpacing(5)
        video_controls = QHBoxLayout()
        self.btn_videos = self.create_video_button('Videos (0)', self.select_videos, '#e3f2fd', '#1976d2', '#bbdefb')
        self.btn_delete = self.create_video_button('Delete', self.delete_selected_videos, '#ffcdd2', '#c62828', '#ef9a9a', delete=True)
        self.btn_delete.setEnabled(False)
        help_btn = self.create_video_button('❓ Help', self.show_help, '#e3f2fd', '#1976d2', '#bbdefb')
        video_controls.addWidget(self.btn_videos)
        video_controls.addWidget(self.btn_delete)
        video_controls.addStretch()
        video_controls.addWidget(help_btn)
        input_layout.addLayout(video_controls)
        tree_frame = QFrame()
        tree_frame.setStyleSheet('QFrame { border: 1px solid #dee2e6; border-radius: 4px; }')
        tree_layout = QVBoxLayout(tree_frame)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(0)
        self.tree_videos = QTreeWidget()
        self.tree_videos.setHeaderLabels(['No.', 'Filename', 'Duration', 'Resolution'])
        self.tree_videos.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree_videos.setAlternatingRowColors(True)
        self.tree_videos.header().setDefaultAlignment(Qt.AlignCenter)
        self.tree_videos.setColumnWidth(0, 50)
        self.tree_videos.setColumnWidth(1, 450)
        self.tree_videos.setColumnWidth(2, 100)
        self.tree_videos.setColumnWidth(3, 120)
        tree_layout.addWidget(self.tree_videos)
        input_layout.addWidget(tree_frame)
        return input_frame
    def create_video_button(self, text: str, callback, bg_color: str, text_color: str, border_color: str, delete: bool=False) -> QPushButton:
        button = QPushButton(text)
        button.setFixedWidth(200)
        button.setFixedHeight(30)
        button.clicked.connect(callback)
        button.setStyleSheet(f'\n            QPushButton {{\n                background-color: {bg_color};\n                color: {text_color};\n                border: 1px solid {border_color};\n                border-radius: 4px;\n                padding: 5px 10px;\n                font-weight: bold;\n            }}\n            QPushButton:hover {{\n                background-color: {border_color};\n            }}\n        ')
        if delete:
            button.setProperty('delete', True)
        return button
    def create_config_frame(self) -> QFrame:
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
        row_container = QFrame()
        row_layout = QHBoxLayout(row_container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)
        label = QLabel('Cutting Mode')
        label.setFixedWidth(200)
        label.setFixedHeight(25)
        label.setProperty('class', 'config_label')
        self.combo_cut_mode = QComboBox()
        self.combo_cut_mode.setFixedWidth(300)
        self.combo_cut_mode.setFixedHeight(25)
        self.combo_cut_mode.addItems(['Split by Time', 'Split by Parts', 'Trim Start/End', 'Specific Time Range'])
        self.combo_cut_mode.currentIndexChanged.connect(self.update_config_inputs)
        row_layout.addWidget(label)
        row_layout.addWidget(self.combo_cut_mode)
        row_layout.addStretch(1)
        form_layout.addWidget(row_container)
        self.split_time_frame = QFrame()
        self.split_time_layout = QHBoxLayout(self.split_time_frame)
        self.split_time_layout.setContentsMargins(0, 0, 0, 0)
        self.split_time_layout.setSpacing(10)
        time_label = QLabel('Segment Duration (seconds)')
        time_label.setFixedWidth(200)
        time_label.setFixedHeight(25)
        time_label.setProperty('class', 'config_label')
        self.time_input = QComboBox()
        self.time_input.setFixedWidth(100)
        self.time_input.setFixedHeight(25)
        self.time_input.setEditable(True)
        self.time_input.addItems(['1', '5', '10', '20', '30', '60', '120', '300', '600'])
        self.time_input.setCurrentText('10')
        self.split_time_layout.addWidget(time_label)
        self.split_time_layout.addWidget(self.time_input)
        self.split_time_layout.addStretch(1)
        self.split_parts_frame = QFrame()
        self.split_parts_layout = QHBoxLayout(self.split_parts_frame)
        self.split_parts_layout.setContentsMargins(0, 0, 0, 0)
        self.split_parts_layout.setSpacing(10)
        parts_label = QLabel('Number of Parts')
        parts_label.setFixedWidth(200)
        parts_label.setFixedHeight(25)
        parts_label.setProperty('class', 'config_label')
        self.parts_input = QComboBox()
        self.parts_input.setFixedWidth(100)
        self.parts_input.setFixedHeight(25)
        self.parts_input.setEditable(True)
        self.parts_input.addItems(['2', '3', '4', '5', '10', '20', '50', '100'])
        self.parts_input.setCurrentText('2')
        self.split_parts_layout.addWidget(parts_label)
        self.split_parts_layout.addWidget(self.parts_input)
        self.split_parts_layout.addStretch(1)
        self.trim_ends_frame = QFrame()
        self.trim_ends_layout = QHBoxLayout(self.trim_ends_frame)
        self.trim_ends_layout.setContentsMargins(0, 0, 0, 0)
        self.trim_ends_layout.setSpacing(10)
        start_label = QLabel('Start Trim (seconds)')
        start_label.setFixedWidth(200)
        start_label.setFixedHeight(25)
        start_label.setProperty('class', 'config_label')
        self.start_trim_input = QComboBox()
        self.start_trim_input.setFixedWidth(100)
        self.start_trim_input.setFixedHeight(25)
        self.start_trim_input.setEditable(True)
        self.start_trim_input.addItems(['0', '1', '2', '5', '10', '15', '20', '30', '60'])
        self.start_trim_input.setCurrentText('0')
        end_label = QLabel('End Trim (seconds)')
        end_label.setFixedWidth(200)
        end_label.setFixedHeight(25)
        end_label.setProperty('class', 'config_label')
        self.end_trim_input = QComboBox()
        self.end_trim_input.setFixedWidth(100)
        self.end_trim_input.setFixedHeight(25)
        self.end_trim_input.setEditable(True)
        self.end_trim_input.addItems(['0', '1', '2', '5', '10', '15', '20', '30', '60'])
        self.end_trim_input.setCurrentText('0')
        self.trim_ends_layout.addWidget(start_label)
        self.trim_ends_layout.addWidget(self.start_trim_input)
        self.trim_ends_layout.addWidget(end_label)
        self.trim_ends_layout.addWidget(self.end_trim_input)
        self.trim_ends_layout.addStretch(1)
        self.specific_range_frame = QFrame()
        self.specific_range_layout = QHBoxLayout(self.specific_range_frame)
        self.specific_range_layout.setContentsMargins(0, 0, 0, 0)
        self.specific_range_layout.setSpacing(10)
        start_range_label = QLabel('Start Time (seconds)')
        start_range_label.setFixedWidth(200)
        start_range_label.setFixedHeight(25)
        start_range_label.setProperty('class', 'config_label')
        self.start_range_input = QComboBox()
        self.start_range_input.setFixedWidth(100)
        self.start_range_input.setFixedHeight(25)
        self.start_range_input.setEditable(True)
        self.start_range_input.addItems(['0', '1', '2', '5', '10', '15', '20', '30', '60'])
        self.start_range_input.setCurrentText('0')
        end_range_label = QLabel('End Time (seconds)')
        end_range_label.setFixedWidth(200)
        end_range_label.setFixedHeight(25)
        end_range_label.setProperty('class', 'config_label')
        self.end_range_input = QComboBox()
        self.end_range_input.setFixedWidth(100)
        self.end_range_input.setFixedHeight(25)
        self.end_range_input.setEditable(True)
        self.end_range_input.addItems(['1', '5', '10', '20', '30', '60', '120', '300', '600'])
        self.end_range_input.setCurrentText('10')
        self.specific_range_layout.addWidget(start_range_label)
        self.specific_range_layout.addWidget(self.start_range_input)
        self.specific_range_layout.addWidget(end_range_label)
        self.specific_range_layout.addWidget(self.end_range_input)
        self.specific_range_layout.addStretch(1)
        self.split_time_frame.hide()
        self.split_parts_frame.hide()
        self.trim_ends_frame.hide()
        self.specific_range_frame.hide()
        form_layout.addWidget(self.split_time_frame)
        form_layout.addWidget(self.split_parts_frame)
        form_layout.addWidget(self.trim_ends_frame)
        form_layout.addWidget(self.specific_range_frame)
        form_layout.addStretch(1)
        config_layout.addWidget(merge_options)
        return config_frame
    def update_config_inputs(self):
        mode = self.combo_cut_mode.currentText()
        self.split_time_frame.hide()
        self.split_parts_frame.hide()
        self.trim_ends_frame.hide()
        self.specific_range_frame.hide()
        if mode == 'Split by Time':
            self.split_time_frame.show()
        else:
            if mode == 'Split by Parts':
                self.split_parts_frame.show()
            else:
                if mode == 'Trim Start/End':
                    self.trim_ends_frame.show()
                else:
                    if mode == 'Specific Time Range':
                        self.specific_range_frame.show()
    def create_progress_frame(self) -> QFrame:
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
            row, label, status, progress = core_widgets.create_thread_row_with_status_class(i)
            thread_layout.addLayout(row)
            self.thread_bars.append(progress)
            self.thread_labels.append(status)
        progress_layout.addWidget(thread_frame)
        progress_layout.addStretch(1)
        return progress_frame
    def create_output_frame(self) -> QFrame:
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
        self.btn_boost = core_widgets.create_boost_button(self.toggle_boost)
        bottom_controls.addWidget(self.btn_boost)
        self.btn_start = QPushButton('🚀 Start')
        self.btn_start.setFixedWidth(150)
        self.btn_start.setFixedHeight(30)
        self.btn_start.setToolTip('Start Cutting')
        self.btn_start.clicked.connect(self.start_cut)
        self.btn_cancel = QPushButton('🛑 Stop')
        self.btn_cancel.setFixedWidth(150)
        self.btn_cancel.setFixedHeight(30)
        self.btn_cancel.setToolTip('Stop Cutting')
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setProperty('delete', True)
        self.btn_cancel.clicked.connect(self.cancel_cut)
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
        self.tree_output = core_widgets.create_output_tree(
            ['No.', 'Input Video', 'Output Video', 'Duration', 'Resolution', 'Status'],
            column_widths=[50, 100, 250, 100, 100, 150]
        )
        tree_layout.addWidget(self.tree_output)
        output_layout.addWidget(tree_frame)
        return output_frame
    def setup_style(self):
        style = '\n            QMainWindow { \n                background-color: #f8f9fa; \n            }\n            QFrame#top_frame, QFrame#bottom_frame { \n                background-color: transparent; \n                border: none; \n            }\n            QFrame#input_frame, QFrame#config_frame, QFrame#progress_frame, QFrame#output_frame {\n                background-color: white; \n                border: 2px solid #dee2e6; \n                border-radius: 8px;\n            }\n            QFrame#sub_frame { \n                background-color: #f8f9fa; \n                border: 1px solid #dee2e6; \n                border-radius: 6px; \n            }\n            QLabel { \n                padding: 5px; \n            }\n            QLabel#dir_label { \n                padding-left: 10px; \n                padding-right: 10px; \n            }\n            QLabel.status_label { \n                color: #1976d2; \n                font-weight: bold; \n                background-color: #e3f2fd; \n                border: 1px solid #bbdefb; \n                border-radius: 4px; \n                padding: 4px 8px; \n            }\n            QLabel.config_label {\n                color: #1976d2;\n                font-weight: bold;\n                font-size: 11px;\n                padding: 2px 4px;\n                background-color: #e3f2fd;\n                border: 1px solid #bbdefb;\n                border-radius: 3px;\n            }\n            QPushButton {\n                background-color: #007bff; \n                color: white; \n                border: none; \n                border-radius: 4px; \n                padding: 5px 10px;\n                min-width: 100px; \n                max-width: 120px; \n                font-weight: bold; \n                font-size: 12px;\n            }\n            QPushButton:hover { \n                background-color: #0056b3; \n            }\n            QPushButton:disabled { \n                background-color: #6c757d; \n            }\n            QPushButton[delete=\"true\"] { \n                background-color: #dc3545; \n            }\n            QPushButton[delete=\"true\"]:hover { \n                background-color: #c82333; \n            }\n            QTreeWidget { \n                border: 1px solid #dee2e6; \n                border-radius: 4px; \n            }\n            QTreeWidget::item { \n                padding: 5px; \n                border-bottom: 1px solid #dee2e6; \n            }\n            QTreeWidget::item:selected { \n                background-color: #007bff; \n                color: white; \n            }\n            QHeaderView::section { \n                background-color: #e3f2fd; \n                padding: 5px; \n                border: 1px solid #bbdefb; \n                font-weight: bold; \n                text-align: center; \n                color: #1976d2; \n            }\n            QProgressBar { \n                border: 1px solid #dee2e6; \n                border-radius: 4px; \n                text-align: center; \n                background-color: #f8f9fa; \n                font-weight: bold; \n            }\n            QProgressBar::chunk { \n                background-color: #e3f2fd; \n                border-radius: 3px; \n            }\n            QFrame#progress_info_frame { \n                background-color: #e3f2fd; \n                border: 1px solid #bbdefb; \n                border-radius: 4px; \n            }\n            QFrame#canvas { \n                background-color: #f0f0f0; \n                border: none; \n            }\n            QComboBox {\n                border: 1px solid #bdc3c7;\n                border-radius: 3px;\n                padding: 1px 12px 1px 3px;\n                background: white;\n                min-height: 20px;\n                font-size: 11px;\n            }\n            QComboBox:hover { \n                border-color: #3498db; \n            }\n            QComboBox:focus { \n                border-color: #2980b9; \n            }\n            QComboBox::drop-down {\n                border: none;\n                width: 12px;\n            }\n            QComboBox::down-arrow {\n                width: 4px;\n                height: 4px;\n                margin-right: 4px;\n                image: none;\n                border: none;\n                border-radius: 2px;\n                background-color: #3498db;\n                opacity: 0.7;\n            }\n            QComboBox::down-arrow:hover {\n                background-color: #2980b9;\n                opacity: 1;\n            }\n            QComboBox::down-arrow:on {\n                background-color: #2980b9;\n                opacity: 1;\n            }\n            QComboBox QAbstractItemView {\n                border: 1px solid #bdc3c7;\n                selection-background-color: #3498db;\n                selection-color: white;\n                background: white;\n                font-size: 11px;\n            }\n        '
        self.setStyleSheet(style)
    def load_config(self) -> dict:
        default_config = {'version': 1}
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f'Failed to load config: {str(e)}')
                QMessageBox.warning(self, 'Warning', 'Configuration file corrupted. Using default.')
                return default_config
        config = core_config.load(Path(CONFIG_FILE), default=default_config)
        return config if config.get('version', 1) == 1 else default_config
    def save_config(self):
        try:
            config = {'version': 1, 'last_output_dir': self.output_directory, 'last_videos_dir': os.path.dirname(self.video_list[0]) if self.video_list else '', 'last_videos': self.video_list, 'cut_mode': self.combo_cut_mode.currentText()}
            core_config.save(Path(CONFIG_FILE), config)
        except (OSError, TypeError) as e:
            self.logger.warning(f'Failed to save config: {str(e)}')
            QMessageBox.warning(self, 'Warning', f'Cannot save configuration: {str(e)}')
    def update_video_counts(self):
        self.btn_videos.setText(f'Videos ({len(self.video_list)})')
    def select_videos(self):
        try:
            self.current_label.setText('Loading videos...')
            QApplication.processEvents()
            initial_dir = self.config.get('last_videos_dir', os.getcwd())
            file_paths = core_file_picker.pick_files(self, 'Select Videos', initial_dir, core_file_picker.VIDEO_FILTER)
            if file_paths:
                new_files = [fp for fp in file_paths if fp not in self.video_list]
                if not new_files:
                    QMessageBox.information(self, 'Information', 'No new videos added.')
                    return
                self.video_list.extend(new_files)
                self.update_video_tree()
                self.btn_delete.setEnabled(True)
                self.update_video_counts()
                self.logger.info(f'Added {len(new_files)} videos.')
            self.current_label.setText('Waiting')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Cannot select videos: {str(e)}')
    def delete_selected_videos(self):
        selected_items = self.tree_videos.selectedItems()
        if not selected_items:
            QMessageBox.information(self, 'Information', 'No video selected to delete.')
            return
        else:
            for item in selected_items:
                filename = item.text(1)
                self.video_list[:] = [v for v in self.video_list if os.path.basename(v)!= filename]
            self.update_video_tree()
            self.btn_delete.setEnabled(bool(self.video_list))
            self.update_video_counts()
    def fetch_video_metadata(self, video_path: str) -> Tuple[str, str, str]:
        if video_path in self.video_metadata_cache:
            return self.video_metadata_cache[video_path]
        else:
            try:
                duration = self.get_video_duration(video_path)
                resolution = self.get_video_resolution(video_path)
                self.video_metadata_cache[video_path] = (video_path, duration, resolution)
                return (video_path, duration, resolution)
            except Exception as e:
                self.logger.error(f'Error getting video info for {video_path}: {str(e)}')
                return (video_path, 'Unknown', 'Unknown')
    def update_video_tree(self):
        self.tree_videos.clear()
        for i, video in enumerate(self.video_list, 1):
            video_path, duration, resolution = self.fetch_video_metadata(video)
            item = QTreeWidgetItem(self.tree_videos)
            item.setText(0, str(i))
            item.setText(1, os.path.basename(video_path))
            item.setText(2, duration)
            item.setText(3, resolution)
    def get_video_duration(self, video_path: str) -> str:
        try:
            cmd = [str(FFPROBE_PATH), '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=self.get_startupinfo(), creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, encoding='utf-8', errors='replace')
            if result.returncode!= 0:
                raise FFmpegError(f'FFprobe error: {result.stderr}')
            else:
                duration_seconds = float(result.stdout.strip())
                hours, remainder = divmod(int(duration_seconds), 3600)
                minutes, seconds = divmod(remainder, 60)
                return f'{hours:02d}:{minutes:02d}:{seconds:02d}'
        except Exception as e:
            self.logger.error(f'Error getting duration for {video_path}: {str(e)}')
            raise MetadataError(f'Failed to get duration: {str(e)}')
    def get_video_resolution(self, video_path: str) -> str:
        try:
            cmd = [str(FFPROBE_PATH), '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0', video_path]
            result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=self.get_startupinfo(), creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, encoding='utf-8', errors='replace')
            return result.stdout.strip() or 'Unknown'
        except Exception as e:
            self.logger.error(f'Error getting resolution for {video_path}: {str(e)}')
            raise MetadataError(f'Failed to get resolution: {str(e)}')
    def get_startupinfo(self):
        startupinfo = subprocess.STARTUPINFO() if os.name == 'nt' else None
        if startupinfo:
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startupinfo
    def select_output_directory(self):
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
        box.setStyleSheet('\n            background-color: #f0f0f0; \n            border: 1px solid #dee2e6; \n            border-radius: 4px;\n        ')
        box.show()
        return box
    def update_box_color(self, index: int, color: str):
        """Cập nhật màu của progress box."""
        if 0 <= index < len(self.progress_boxes):
            styles = {'green': 'background-color: #28a745; border: 1px solid #218838;', 'yellow': 'background-color: #ffc107; border: 1px solid #d39e00;', 'red': 'background-color: #dc3545; border: 1px solid #bd2130;', 'default': 'background-color: #f0f0f0; border: 1px solid #dee2e6;'}
            self.progress_boxes[index].setStyleSheet(f"{styles.get(color, styles['default'])} border-radius: 4px;")
    def clear_progress_boxes(self):
        for box in self.progress_boxes:
            box.deleteLater()
        self.progress_boxes.clear()
    def start_cut(self):
        if self.is_processing:
            if QMessageBox.question(self, 'Confirm', 'Cutting in progress. Do you want to cancel and start new?', QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.cancel_cut()
            else:
                return None
        if not self.validate_inputs():
            return
        else:
            self.is_processing = True
            self.btn_start.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            self.total_output = len(self.video_list)
            self.processed_output = 0
            self.progress_label.setText(f'Progress: 0/{self.total_output}')
            self.current_label.setText('Cutting: None')
            self.tree_output.clear()
            self.cancel_event.clear()
            self.clear_progress_boxes()
            for i in range(self.total_output):
                box = self.create_progress_box(i)
                self.progress_boxes.append(box)
            threading.Thread(target=self.cut_videos, daemon=True).start()
    def cancel_cut(self):
        if self.is_processing:
            self.cancel_event.set()
            self.thread_pool.clear()
            self.btn_cancel.setEnabled(False)
            for i in range(self.processed_output, len(self.progress_boxes)):
                self.update_box_color(i, 'red')
            for label, bar in zip(self.thread_labels, self.thread_bars):
                label.setText('Cancelled')
                bar.setValue(0)
            QMessageBox.information(self, 'Information', 'Cutting cancelled.')
            self.is_processing = False
            self.btn_start.setEnabled(True)
    def validate_inputs(self) -> bool:
        if not self.video_list:
            QMessageBox.warning(self, 'Warning', 'Please select at least one video.')
            return False
        if not self.output_directory:
            QMessageBox.warning(self, 'Warning', 'Please select output directory.')
            return False
        mode = self.combo_cut_mode.currentText()
        try:
            if mode == 'Split by Time':
                duration = float(self.time_input.currentText())
                if duration <= 0:
                    QMessageBox.warning(self, 'Warning', 'Segment duration must be greater than 0.')
                    return False
            elif mode == 'Split by Parts':
                parts = int(self.parts_input.currentText())
                if parts < 1:
                    QMessageBox.warning(self, 'Warning', 'Number of parts must be at least 1.')
                    return False
            elif mode == 'Trim Start/End':
                start = float(self.start_trim_input.currentText())
                end = float(self.end_trim_input.currentText())
                if start == 0 and end == 0:
                    QMessageBox.warning(self, 'Warning', 'Please specify at least one trim value.')
                    return False
            elif mode == 'Specific Time Range':
                start = float(self.start_range_input.currentText())
                end = float(self.end_range_input.currentText())
                if start >= end:
                    QMessageBox.warning(self, 'Warning', 'End time must be greater than start time.')
                    return False
            return True
        except ValueError:
            QMessageBox.warning(self, 'Warning', 'Please enter valid numbers.')
            return False
    def cut_videos(self):
        try:
            mode = self.combo_cut_mode.currentText()
            cut_params = {}
            if mode == 'Split by Time':
                cut_params = {'mode': 'split_by_time', 'duration': float(self.time_input.currentText())}
            else:
                if mode == 'Split by Parts':
                    cut_params = {'mode': 'split_by_parts', 'parts': int(self.parts_input.currentText())}
                else:
                    if mode == 'Trim Start/End':
                        cut_params = {'mode': 'trim_ends', 'start': float(self.start_trim_input.currentText()), 'end': float(self.end_trim_input.currentText())}
                    else:
                        if mode == 'Specific Time Range':
                            cut_params = {'mode': 'specific_range', 'start': float(self.start_range_input.currentText()), 'end': float(self.end_range_input.currentText())}
            for i, video in enumerate(self.video_list):
                if self.cancel_event.is_set():
                    break
                else:
                    while self.thread_pool.activeThreadCount() >= 3:
                        if self.cancel_event.is_set():
                            break
                        QThread.msleep(100)
                    self.update_box_color(i, 'yellow')
                    self.current_label.setText(f'Cutting: {os.path.basename(video)}')
                    current_time = datetime.now().strftime('%d%m%y_%H%M%S')
                    base_name = os.path.splitext(os.path.basename(video))[0]
                    base_name = re.sub('[^\\w\\s-]', '', base_name)
                    base_name = re.sub('\\s+', '_', base_name.strip())
                    display_filename = f'{base_name}_{current_time}.mp4'
                    if cut_params['mode'] in ['split_by_time', 'split_by_parts']:
                        output_filename = os.path.join(self.output_directory, f'{base_name}_{current_time}_%03d.mp4')
                    else:
                        output_filename = os.path.join(self.output_directory, f'{base_name}_{current_time}.mp4')
                    item = QTreeWidgetItem(self.tree_output)
                    item.setText(0, str(i + 1))
                    item.setText(1, os.path.basename(video))
                    item.setText(2, display_filename)
                    item.setText(3, 'Processing')
                    item.setText(4, 'N/A')
                    item.setText(5, '🔄 Processing...')
                    worker = CutWorker(video, output_filename, i % 3, FFMPEG_PATH, cut_params, self.get_ffmpeg_params())
                    worker.setAutoDelete(True)
                    worker.signals.progress_updated.connect(self.update_thread_progress)
                    worker.signals.status_updated.connect(self.update_thread_status)
                    worker.signals.output_updated.connect(self.update_ffmpeg_output)
                    worker.signals.cut_completed.connect(self.on_cut_completed)
                    worker.signals.error_occurred.connect(self.on_cut_error)
                    self.thread_pool.start(worker)
        except Exception as e:
            self.logger.error(f'Error cutting: {str(e)}')
            QMessageBox.critical(self, 'Error', f'Unexpected error occurred: {str(e)}')
        finally:
            self.thread_pool.waitForDone()
            self.is_processing = False
            self.btn_start.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.current_label.setText('Completed')
            self.save_config()
    def update_thread_progress(self, thread_index: int, progress: int):
        self.progress_update_queue.append((thread_index, progress))
    def update_thread_status(self, thread_index: int, status: str):
        if 0 <= thread_index < len(self.thread_labels):
            self.thread_labels[thread_index].setText(status)
    def update_ffmpeg_output(self, output: str):
        for i in range(self.tree_output.topLevelItemCount()):
            item = self.tree_output.topLevelItem(i)
            if item.text(5) == '🔄 Processing...' and 'out_time_ms=' in output:
                    item.setText(5, '🔄 Processing...')
                    break
    def on_cut_completed(self, output_filename: str):
        self.processed_output += 1
        self.progress_label.setText(f'Progress: {self.processed_output}/{self.total_output}')
        self.update_box_color(self.processed_output - 1, 'green')
        base_output = output_filename.replace('%03d', '*')
        output_pattern = os.path.join(self.output_directory, base_output)
        output_files = glob.glob(output_pattern)
        for i in range(self.tree_output.topLevelItemCount()):
            item = self.tree_output.topLevelItem(i)
            display_name = item.text(2)
            if os.path.splitext(display_name)[0] in output_filename:
                if output_files:
                    first_output = output_files[0]
                    item.setText(3, self.get_video_duration(first_output))
                    item.setText(4, self.get_video_resolution(first_output))
                    item.setText(5, f'🟢 Completed ({len(output_files)} parts)')
                else:
                    item.setText(5, '🔴 Error')
                break
    def on_cut_error(self, error_message: str):
        self.update_box_color(self.processed_output, 'red')
        self.processed_output += 1
        for i in range(self.tree_output.topLevelItemCount()):
            item = self.tree_output.topLevelItem(i)
            if item.text(5) == '🔄 Processing...':
                item.setText(3, 'N/A')
                item.setText(4, 'N/A')
                item.setText(5, '🔴 Error')
                break
    def process_ui_updates(self):
        for thread_index, progress in self.progress_update_queue:
            if 0 <= thread_index < len(self.thread_bars):
                    self.thread_bars[thread_index].setValue(progress)
        self.progress_update_queue.clear()
    def load_last_paths(self):
        config = self.config
        self.combo_cut_mode.setCurrentText(config.get('cut_mode', 'Split by Time'))
        last_output = config.get('last_output_dir', '')
        if last_output and os.path.isdir(last_output):
                self.output_directory = last_output
                self.dir_label.setText(f'Output Directory: {self.output_directory}')
        valid_videos = [v for v in config.get('last_videos', []) if os.path.isfile(v)]
        if valid_videos:
            self.video_list = valid_videos
            self.btn_delete.setEnabled(True)
        self.update_video_tree()
        self.update_video_counts()
        self.update_config_inputs()
    def closeEvent(self, event):
        if self.is_processing:
            if QMessageBox.question(self, 'Exit', 'Cutting in progress. Do you really want to exit?', QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.cancel_cut()
                self.save_config()
                event.accept()
            else:
                event.ignore()
        else:
            self.save_config()
            event.accept()
    def open_output_directory(self):
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
        readme_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'README Cutter.md')
        dialog = HelpDialog(self, 'Help - 1vmo Cutter', readme_path)
        dialog.exec_()
    def toggle_boost(self):
        self.is_boost_mode = not self.is_boost_mode
        core_widgets.set_boost_on_style(self.btn_boost, self.is_boost_mode)
    def get_ffmpeg_params(self):
        if self.is_boost_mode:
            return ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-c:a', 'aac', '-b:a', '128k', '-async', '1', '-vsync', '1', '-movflags', '+faststart', '-pix_fmt', 'yuv420p', '-max_muxing_queue_size', '1024', '-threads', '3', '-avoid_negative_ts', 'make_zero']
        else:
            return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-c:a', 'aac', '-b:a', '192k', '-async', '1', '-vsync', '1', '-movflags', '+faststart', '-pix_fmt', 'yuv420p', '-max_muxing_queue_size', '1024', '-threads', '3', '-avoid_negative_ts', 'make_zero']
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = VideoCutterTool()
    window.show()
    sys.exit(app.exec_())