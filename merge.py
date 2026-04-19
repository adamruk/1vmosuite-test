# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'Code Merge.py'
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
import traceback
import requests
import shutil
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QTreeWidget, QTreeWidgetItem, QComboBox, QFileDialog, QTextEdit, QFrame, QMessageBox, QGridLayout, QSpacerItem, QSizePolicy, QDialog, QSlider
from PyQt5.QtCore import Qt, QThreadPool, QRunnable, pyqtSignal, QObject, QThread, QTimer
from PyQt5.QtGui import QIcon, QColor, QPainter, QPen, QBrush
from updater import DriveUpdater
from help_dialog import HelpDialog
from core import config as core_config
from core import file_picker as core_file_picker
from core import widgets as core_widgets
from core import ffmpeg_runner as core_ffmpeg_runner
SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
FFMPEG_PATH, FFPROBE_PATH = core_ffmpeg_runner.resolve_binaries(SCRIPT_DIR)
ICON_PATH = SCRIPT_DIR / 'assets' / 'Merge.ico'
CONFIG_FILE = SCRIPT_DIR / 'config_video_merge.json'
logging.basicConfig(filename='video_merge.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
    running_workers = []
    def __init__(self, input_files: List[str], output_path: str, thread_index: int, ffmpeg_path: Path, merge_mode: str, layout: str, opacity: float, audio_source: str, output_format: str='Free', video_ratio: int=5, custom_audio: str=None, is_boost_mode: bool=False):
        super().__init__()
        self.input_files = input_files
        self.output_path = output_path
        self.thread_index = thread_index
        self.ffmpeg_path = ffmpeg_path
        self.merge_mode = merge_mode
        self.layout = layout
        self.opacity = opacity
        self.audio_source = audio_source
        self.output_format = output_format
        self.video_ratio = video_ratio
        self.custom_audio = custom_audio
        self.is_boost_mode = is_boost_mode
        self.is_cancelled = False
        self.signals = WorkerSignals()
        self.logger = logging.getLogger(__name__)
        self.process = None
    def run(self):
        MergeWorker.running_workers.append(self)
        try:
            self.signals.status_updated.emit(self.thread_index, f'Bắt đầu xử lý: {os.path.basename(self.output_path)}')
            self.signals.progress_updated.emit(self.thread_index, 0)
            self.signals.output_updated.emit(f'\n[Thread {self.thread_index + 1}] Bắt đầu xử lý: {os.path.basename(self.output_path)}\n')
            if len(self.input_files) < 1:
                raise ValueError('Cần ít nhất 1 video để xử lý.')
            for video in self.input_files:
                if not os.path.exists(video):
                    raise FileNotFoundError(f'Không tìm thấy file: {video}')
                if os.path.getsize(video) == 0:
                    raise ValueError(f'File rỗng: {video}')
            if self.custom_audio:
                if not os.path.exists(self.custom_audio):
                    raise FileNotFoundError(f'Không tìm thấy file audio: {self.custom_audio}')
                if os.path.getsize(self.custom_audio) == 0:
                    raise ValueError(f'File audio rỗng: {self.custom_audio}')
            resolutions = []
            for file in self.input_files:
                ext = os.path.splitext(file)[1].lower()
                if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff']:
                    from PIL import Image
                    with Image.open(file) as img:
                        width, height = img.size
                        resolutions.append((width, height))
                else:
                    resolutions.append(self.get_video_resolution(file))
            max_width = max((r[0] for r in resolutions))
            max_height = max((r[1] for r in resolutions))
            if self.output_format!= 'Free' and self.layout in ['Horizontal', 'Vertical']:
                if self.output_format == '16:9':
                    aspect_ratio = 1.7777777777777777
                else:
                    if self.output_format == '9:16':
                        aspect_ratio = 0.5625
                    else:
                        aspect_ratio = 1
                total_ratio = self.video_ratio + (10 - self.video_ratio)
                ratio1 = self.video_ratio / total_ratio
                ratio2 = (10 - self.video_ratio) / total_ratio
                if self.layout == 'Horizontal':
                    total_width = max_height * aspect_ratio
                    width1 = int(total_width * ratio1)
                    width2 = int(total_width * ratio2)
                    new_widths = [width1, width2]
                    new_heights = [max_height, max_height]
                else:
                    total_height = max_width / aspect_ratio
                    height1 = int(total_height * ratio1)
                    height2 = int(total_height * ratio2)
                    new_widths = [max_width, max_width]
                    new_heights = [height1, height2]
            else:
                new_widths = [max_width] * len(self.input_files)
                new_heights = [max_height] * len(self.input_files)
            durations = []
            for file in self.input_files:
                ext = os.path.splitext(file)[1].lower()
                if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff']:
                    durations.append(5)
                else:
                    durations.append(self.get_video_duration_seconds(file))
            max_duration_idx = durations.index(max(durations))
            command = [str(self.ffmpeg_path), '-y']
            for file in self.input_files:
                ext = os.path.splitext(file)[1].lower()
                if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff']:
                    command.extend(['-loop', '1', '-i', file])
                else:
                    command.extend(['-hwaccel', 'auto', '-i', file])
            if self.custom_audio:
                command.extend(['-i', self.custom_audio])
            filter_complex = []
            stream_map = []
            for i in range(len(self.input_files)):
                ext = os.path.splitext(self.input_files[i])[1].lower()
                if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff']:
                    filter_complex.append(f'[{i}:v]scale={new_widths[i]}:{new_heights[i]}:force_original_aspect_ratio=decrease,pad={new_widths[i]}:{new_heights[i]}:(ow-iw)/2:(oh-ih)/2,setpts=PTS-STARTPTS,trim=duration=5[v{i}]')
                else:
                    filter_complex.append(f'[{i}:v]scale={new_widths[i]}:{new_heights[i]}:force_original_aspect_ratio=decrease,pad={new_widths[i]}:{new_heights[i]}:(ow-iw)/2:(oh-ih)/2[v{i}]')
            if len(self.input_files) == 1:
                filter_complex.append('[v0]copy[outv]')
            else:
                if self.layout == 'Horizontal':
                    filter_str = '[v0]'
                    for i in range(1, len(self.input_files)):
                        filter_str += f'[v{i}]'
                    filter_str += f'hstack=inputs={len(self.input_files)}[outv]'
                    filter_complex.append(filter_str)
                else:
                    if self.layout == 'Vertical':
                        filter_str = '[v0]'
                        for i in range(1, len(self.input_files)):
                            filter_str += f'[v{i}]'
                        filter_str += f'vstack=inputs={len(self.input_files)}[outv]'
                        filter_complex.append(filter_str)
                    else:
                        if self.layout == '2x2 Grid':
                            filter_complex.append('[v0][v1]hstack=inputs=2[row1]')
                            filter_complex.append('[v2][v3]hstack=inputs=2[row2]')
                            filter_complex.append('[row1][row2]vstack=inputs=2[outv]')
                        else:
                            filter_complex.append(f'[v1]format=yuva420p,geq=\'r=r(X,Y):g=g(X,Y):b=b(X,Y):a=255*{self.opacity / 100}\'[fg]')
                            filter_complex.append('[v0][fg]overlay=0:0[outv]')
            stream_map = ['[outv]']
            if self.custom_audio:
                stream_map.append(f'{len(self.input_files)}:a')
            else:
                if self.audio_source == 'Longest':
                    stream_map.append(f'{max_duration_idx}:a')
                else:
                    min_duration_idx = durations.index(min(durations))
                    stream_map.append(f'{min_duration_idx}:a')
            filter_complex = ';'.join(filter_complex)
            self.signals.output_updated.emit(f'\nFilter Complex: {filter_complex}\n')
            command.extend(['-filter_complex', filter_complex])
            command.extend(['-map', stream_map[0]])
            command.extend(['-map', stream_map[1]])
            command.extend(self.get_ffmpeg_params())
            command.append(self.output_path)
            self.signals.output_updated.emit(f"\nLệnh FFmpeg: {' '.join((str(x) for x in command))}\n\n")
            startupinfo = core_ffmpeg_runner.hidden_startupinfo()
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo, creationflags=core_ffmpeg_runner.hidden_creationflags(), text=True, encoding='utf-8', errors='replace')
            self.process = process
            duration, time = (None, 0)
            error_output = []
            while True:
                if self.is_cancelled:
                    if self.process:
                        self.process.terminate()
                        self.process.wait()
                    self.signals.status_updated.emit(self.thread_index, 'Đã hủy')
                    self.signals.progress_updated.emit(self.thread_index, 0)
                    if self in MergeWorker.running_workers:
                        MergeWorker.running_workers.remove(self)
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
        except Exception as e:
            error_msg = f'Lỗi khi xử lý {os.path.basename(self.output_path)}: {str(e)}\n{traceback.format_exc()}'
            print(f'Merge Error: {error_msg}')
            self.logger.error(error_msg)
            self.signals.error_occurred.emit(error_msg)
            self.signals.status_updated.emit(self.thread_index, 'Lỗi')
            self.signals.progress_updated.emit(self.thread_index, 0)
            self.signals.output_updated.emit(f'\n[Thread {self.thread_index + 1}] {error_msg}\n')
        finally:
            if self in MergeWorker.running_workers:
                MergeWorker.running_workers.remove(self)
    def get_video_duration_seconds(self, video_path: str) -> float:
        cmd = [str(FFPROBE_PATH), '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        return float(result.stdout.strip())
    def get_video_resolution(self, video_path: str) -> Tuple[int, int]:
        return core_ffmpeg_runner.probe_resolution(FFPROBE_PATH, Path(video_path))
    def get_ffmpeg_params(self):
        if self.is_boost_mode:
            return ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-c:a', 'aac', '-b:a', '128k', '-async', '1', '-vsync', '1', '-movflags', '+faststart', '-pix_fmt', 'yuv420p', '-max_muxing_queue_size', '1024', '-threads', '3', '-avoid_negative_ts', 'make_zero', '-max_muxing_queue_size', '4096', '-max_interleave_delta', '0', '-thread_queue_size', '512', '-analyzeduration', '2147483647', '-probesize', '2147483647']
        else:
            return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-c:a', 'aac', '-b:a', '192k', '-async', '1', '-vsync', '1', '-movflags', '+faststart', '-pix_fmt', 'yuv420p', '-max_muxing_queue_size', '1024', '-threads', '3', '-avoid_negative_ts', 'make_zero', '-max_muxing_queue_size', '4096', '-max_interleave_delta', '0', '-thread_queue_size', '512', '-analyzeduration', '2147483647', '-probesize', '2147483647']
class PreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout_mode = ''
        self.num_videos = 2
        self.ratio = 5
        self.output_format = 'Free'
        self.setFixedSize(300, 200)
    def update_preview(self, layout_mode: str, num_videos: int, ratio: int=5, output_format: str='Free'):
        self.layout_mode = layout_mode
        self.num_videos = num_videos
        self.ratio = ratio
        self.output_format = output_format
        self.update()
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor('#f0f0f0'))
        container_width, container_height = (self.width() - 20, self.height() - 20)
        width, height = (container_width, container_height)
        if self.output_format == '16:9':
            height = int(width * 9 / 16)
        else:
            if self.output_format == '9:16':
                width = int(height * 9 / 16)
            else:
                if self.output_format == '1:1':
                    size = min(width, height)
                    width = height = size
        x = (container_width - width) // 2 + 10
        y = (container_height - height) // 2 + 10
        pen = QPen(Qt.black, 1)
        painter.setPen(pen)
        if self.num_videos == 2:
            if self.layout_mode == 'Horizontal':
                total_ratio = self.ratio + (10 - self.ratio)
                w1 = int(width * self.ratio / total_ratio)
                w2 = width - w1
                painter.fillRect(x, y, w1, height, QColor('#007bff'))
                painter.drawText(x + w1 // 2 - 10, y + height // 2, '1')
                painter.fillRect(x + w1, y, w2, height, QColor('#28a745'))
                painter.drawText(x + w1 + w2 // 2 - 10, y + height // 2, '2')
            else:
                if self.layout_mode == 'Vertical':
                    total_ratio = self.ratio + (10 - self.ratio)
                    h1 = int(height * self.ratio / total_ratio)
                    h2 = height - h1
                    painter.fillRect(x, y, width, h1, QColor('#007bff'))
                    painter.drawText(x + width // 2 - 10, y + h1 // 2, '1')
                    painter.fillRect(x, y + h1, width, h2, QColor('#28a745'))
                    painter.drawText(x + width // 2 - 10, y + h1 + h2 // 2, '2')
                else:
                    painter.fillRect(x, y, width, height, QColor('#007bff'))
                    painter.drawText(x + width // 2 - 10, y + height // 2, '1')
                    painter.setOpacity(0.5)
                    painter.fillRect(x + width // 4, y + height // 4, width // 2, height // 2, QColor('#28a745'))
                    painter.drawText(x + width // 2 - 10, y + height // 2, '2')
                    painter.setOpacity(1.0)
        else:
            if self.num_videos == 3:
                if self.layout_mode == 'Horizontal':
                    w = width // 3
                    colors = ['#007bff', '#28a745', '#fd7e14']
                    for i in range(3):
                        painter.fillRect(x + i * w, y, w, height, QColor(colors[i]))
                        painter.drawText(x + i * w + w // 2 - 10, y + height // 2, str(i + 1))
                else:
                    h = height // 3
                    colors = ['#007bff', '#28a745', '#fd7e14']
                    for i in range(3):
                        painter.fillRect(x, y + i * h, width, h, QColor(colors[i]))
                        painter.drawText(x + width // 2 - 10, y + i * h + h // 2, str(i + 1))
            else:
                if self.num_videos == 4:
                    if self.layout_mode == 'Horizontal':
                        w = width // 4
                        colors = ['#007bff', '#28a745', '#fd7e14', '#dc3545']
                        for i in range(4):
                            painter.fillRect(x + i * w, y, w, height, QColor(colors[i]))
                            painter.drawText(x + i * w + w // 2 - 10, y + height // 2, str(i + 1))
                    else:
                        if self.layout_mode == 'Vertical':
                            h = height // 4
                            colors = ['#007bff', '#28a745', '#fd7e14', '#dc3545']
                            for i in range(4):
                                painter.fillRect(x, y + i * h, width, h, QColor(colors[i]))
                                painter.drawText(x + width // 2 - 10, y + i * h + h // 2, str(i + 1))
                        else:
                            w, h = (width // 2, height // 2)
                            colors = ['#007bff', '#28a745', '#fd7e14', '#dc3545']
                            for i in range(4):
                                painter.fillRect(x + i % 2 * w, y + i // 2 * h, w, h, QColor(colors[i]))
                                painter.drawText(x + i % 2 * w + w // 2 - 10, y + i // 2 * h + h // 2, str(i + 1))
class VideoMergeTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.is_boost_mode = False
        if not FFMPEG_PATH.exists() or not FFPROBE_PATH.exists():
            QMessageBox.critical(self, 'Error', 'FFmpeg or FFprobe not found. Please place them in the \'ffmpeg\' directory.')
            sys.exit(1)
        self.updater = DriveUpdater()
        self.current_version = self.updater._load_current_version('1vmo Merge')
        if self.current_version is None:
            self.current_version = '1.0'
            self.updater._save_current_version(self.current_version, '1vmo Merge')
        self.setWindowTitle(f'1vmo Merge v{self.current_version}')
        self.setGeometry(100, 100, 1600, 900)
        # Allow resize and maximize — set a reasonable minimum so layouts don't
        # collapse below their designed size, and use resize() for initial geometry.
        self.setMinimumSize(1600, 900)
        self.resize(1600, 900)
        self.updater.check_and_update('1vmo Merge')
        self.setup_icon()
        self.initialize_state()
        self.config = self.load_config()
        self.setup_ui()
        self.setup_style()
        self.load_last_paths()
    def setup_icon(self):
        try:
            if ICON_PATH.exists():
                app_icon = QIcon(str(ICON_PATH))
                self.setWindowIcon(app_icon)
                QApplication.setWindowIcon(app_icon)
                if os.name == 'nt':
                    import ctypes
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('1vmo.VideoMerge.1.0.0')
        except Exception as e:
            self.logger.error(f'Error setting up icon: {str(e)}')
    def initialize_state(self):
        self.group1_videos = []
        self.group2_videos = []
        self.group3_videos = []
        self.group4_videos = []
        self.audio_files = []
        self.output_directory = ''
        self.is_merging = False
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
        input_frame = QFrame(objectName='input_frame')
        input_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        input_frame.setMinimumWidth(780)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(5, 5, 5, 5)
        input_layout.setSpacing(5)
        video_controls_top = QHBoxLayout()
        self.btn_group1 = self.create_video_button('Group 1 (0)', self.select_group1_videos, '#e3f2fd', '#1976d2', '#bbdefb')
        self.btn_group2 = self.create_video_button('Group 2 (0)', self.select_group2_videos, '#c8e6c9', '#2e7d32', '#a5d6a7')
        self.btn_group3 = self.create_video_button('Group 3 (0)', self.select_group3_videos, '#ffe0b2', '#f57c00', '#ffb74d')
        self.btn_group4 = self.create_video_button('Group 4 (0)', self.select_group4_videos, '#ffcdd2', '#c62828', '#ef9a9a')
        self.btn_delete = self.create_video_button('Delete', self.delete_selected_videos, '#ffcdd2', '#c62828', '#ef9a9a', delete=True)
        self.btn_delete.setEnabled(False)
        help_btn = self.create_video_button('❓ Help', self.show_help, '#e3f2fd', '#1976d2', '#bbdefb')
        video_controls_top.addWidget(self.btn_group1)
        video_controls_top.addWidget(self.btn_group2)
        video_controls_top.addWidget(self.btn_group3)
        video_controls_top.addWidget(self.btn_group4)
        video_controls_top.addWidget(self.btn_delete)
        video_controls_top.addStretch()
        video_controls_top.addWidget(help_btn)
        video_controls_bottom = QHBoxLayout()
        self.btn_audio = self.create_video_button('🎵 Audio (0)', self.select_audio_files, '#e1bee7', '#7b1fa2', '#ce93d8')
        video_controls_bottom.addWidget(self.btn_audio)
        video_controls_bottom.addStretch()
        input_layout.addLayout(video_controls_top)
        input_layout.addLayout(video_controls_bottom)
        tree_frame = QFrame()
        tree_frame.setStyleSheet('QFrame { border: 1px solid #dee2e6; border-radius: 4px; }')
        tree_layout = QVBoxLayout(tree_frame)
        tree_layout.setContentsMargins(0, 0, 0, 0)
        tree_layout.setSpacing(0)
        self.tree_videos = QTreeWidget()
        self.tree_videos.setHeaderLabels(['Type', 'No.', 'Filename', 'Duration', 'Resolution', 'Format'])
        self.tree_videos.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree_videos.setAlternatingRowColors(True)
        self.tree_videos.header().setDefaultAlignment(Qt.AlignCenter)
        self.tree_videos.setColumnWidth(0, 80)
        self.tree_videos.setColumnWidth(1, 50)
        self.tree_videos.setColumnWidth(2, 400)
        self.tree_videos.setColumnWidth(3, 80)
        self.tree_videos.setColumnWidth(4, 80)
        self.tree_videos.setColumnWidth(5, 80)
        tree_layout.addWidget(self.tree_videos)
        input_layout.addWidget(tree_frame)
        return input_frame
    def create_video_button(self, text: str, callback, bg_color: str, text_color: str, border_color: str, delete: bool=False) -> QPushButton:
        button = QPushButton(text)
        button.setFixedWidth(150)
        button.setFixedHeight(30)
        button.clicked.connect(callback)
        button.setStyleSheet(f'\n            QPushButton {{\n                background-color: {bg_color};\n                color: {text_color};\n                border: 1px solid {border_color};\n                border-radius: 4px;\n                padding: 5px 10px;\n                font-weight: bold;\n            }}\n            QPushButton:hover {{\n                background-color: {border_color};\n            }}\n        ')
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
        row_container = QFrame()
        row_layout = QHBoxLayout(row_container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)
        num_videos_label = QLabel('Number of Videos')
        num_videos_label.setFixedWidth(150)
        num_videos_label.setFixedHeight(25)
        num_videos_label.setProperty('class', 'config_label')
        self.combo_num_videos = QComboBox()
        self.combo_num_videos.setFixedWidth(100)
        self.combo_num_videos.setFixedHeight(25)
        self.combo_num_videos.addItems(['1', '2', '3', '4'])
        self.combo_num_videos.currentTextChanged.connect(self.update_config_options)
        row_layout.addWidget(num_videos_label)
        row_layout.addWidget(self.combo_num_videos)
        row_layout.addStretch()
        form_layout.addWidget(row_container)
        layout_row = QFrame()
        layout_layout = QHBoxLayout(layout_row)
        layout_layout.setContentsMargins(0, 0, 0, 0)
        layout_layout.setSpacing(10)
        layout_label = QLabel('Layout Mode')
        layout_label.setFixedWidth(150)
        layout_label.setFixedHeight(25)
        layout_label.setProperty('class', 'config_label')
        self.combo_layout = QComboBox()
        self.combo_layout.setFixedWidth(200)
        self.combo_layout.setFixedHeight(25)
        self.combo_layout.addItems(['Horizontal', 'Vertical', 'Overlay'])
        self.combo_layout.currentTextChanged.connect(self.update_preview)
        layout_layout.addWidget(layout_label)
        layout_layout.addWidget(self.combo_layout)
        layout_layout.addStretch()
        form_layout.addWidget(layout_row)
        format_row = QFrame()
        format_layout = QHBoxLayout(format_row)
        format_layout.setContentsMargins(0, 0, 0, 0)
        format_layout.setSpacing(10)
        format_label = QLabel('Output Format')
        format_label.setFixedWidth(150)
        format_label.setFixedHeight(25)
        format_label.setProperty('class', 'config_label')
        self.combo_format = QComboBox()
        self.combo_format.setFixedWidth(200)
        self.combo_format.setFixedHeight(25)
        self.combo_format.addItems(['Free', '16:9', '9:16', '1:1'])
        self.combo_format.currentTextChanged.connect(self.update_preview)
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.combo_format)
        format_layout.addStretch()
        form_layout.addWidget(format_row)
        self.ratio_frame = QFrame()
        ratio_layout = QHBoxLayout(self.ratio_frame)
        ratio_layout.setContentsMargins(0, 0, 0, 0)
        ratio_layout.setSpacing(10)
        ratio_label = QLabel('Video Ratio')
        ratio_label.setFixedWidth(150)
        ratio_label.setFixedHeight(25)
        ratio_label.setProperty('class', 'config_label')
        self.slider_ratio = QSlider(Qt.Horizontal)
        self.slider_ratio.setMinimum(1)
        self.slider_ratio.setMaximum(9)
        self.slider_ratio.setValue(5)
        self.ratio_value = QLabel('5:5')
        ratio_layout.addWidget(ratio_label)
        ratio_layout.addWidget(self.slider_ratio)
        ratio_layout.addWidget(self.ratio_value)
        ratio_layout.addStretch()
        self.slider_ratio.valueChanged.connect(self.update_ratio_value)
        self.ratio_frame.setVisible(False)
        form_layout.addWidget(self.ratio_frame)
        self.overlay_frame = QFrame()
        overlay_layout = QHBoxLayout(self.overlay_frame)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setSpacing(10)
        overlay_group_label = QLabel('Overlay Group')
        overlay_group_label.setFixedWidth(150)
        overlay_group_label.setFixedHeight(25)
        overlay_group_label.setProperty('class', 'config_label')
        self.combo_overlay_group = QComboBox()
        self.combo_overlay_group.setFixedWidth(100)
        self.combo_overlay_group.setFixedHeight(25)
        self.combo_overlay_group.addItems(['Group 1', 'Group 2'])
        opacity_label = QLabel('Opacity (%)')
        opacity_label.setFixedWidth(100)
        opacity_label.setFixedHeight(25)
        opacity_label.setProperty('class', 'config_label')
        self.slider_opacity = QSlider(Qt.Horizontal)
        self.slider_opacity.setMinimum(0)
        self.slider_opacity.setMaximum(100)
        self.slider_opacity.setValue(50)
        self.opacity_value = QLabel('50')
        overlay_layout.addWidget(overlay_group_label)
        overlay_layout.addWidget(self.combo_overlay_group)
        overlay_layout.addWidget(opacity_label)
        overlay_layout.addWidget(self.slider_opacity)
        overlay_layout.addWidget(self.opacity_value)
        overlay_layout.addStretch()
        self.slider_opacity.valueChanged.connect(self.update_opacity_value)
        self.overlay_frame.setVisible(False)
        form_layout.addWidget(self.overlay_frame)
        row_container = QFrame()
        row_layout = QHBoxLayout(row_container)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)
        audio_label = QLabel('Audio Source')
        audio_label.setFixedWidth(150)
        audio_label.setFixedHeight(25)
        audio_label.setProperty('class', 'config_label')
        self.combo_audio = QComboBox()
        self.combo_audio.setFixedWidth(200)
        self.combo_audio.setFixedHeight(25)
        self.combo_audio.addItems(['Longest', 'Shortest', 'Custom Audio'])
        self.combo_audio.currentTextChanged.connect(self.update_audio_options)
        row_layout.addWidget(audio_label)
        row_layout.addWidget(self.combo_audio)
        row_layout.addStretch()
        form_layout.addWidget(row_container)
        self.audio_mode_frame = QFrame()
        audio_mode_layout = QHBoxLayout(self.audio_mode_frame)
        audio_mode_layout.setContentsMargins(0, 0, 0, 0)
        audio_mode_layout.setSpacing(10)
        audio_mode_label = QLabel('Audio Mode')
        audio_mode_label.setFixedWidth(150)
        audio_mode_label.setFixedHeight(25)
        audio_mode_label.setProperty('class', 'config_label')
        self.combo_audio_mode = QComboBox()
        self.combo_audio_mode.setFixedWidth(200)
        self.combo_audio_mode.setFixedHeight(25)
        self.combo_audio_mode.addItems(['🔁 Order', '🎲 Random'])
        self.combo_audio_mode.currentTextChanged.connect(self.update_audio_mode)
        audio_mode_layout.addWidget(audio_mode_label)
        audio_mode_layout.addWidget(self.combo_audio_mode)
        audio_mode_layout.addStretch()
        form_layout.addWidget(self.audio_mode_frame)
        form_layout.addStretch()
        config_layout.addWidget(merge_options)
        preview_frame = QFrame(objectName='sub_frame')
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(10, 5, 10, 5)
        preview_label = QLabel('Layout Preview')
        preview_label.setAlignment(Qt.AlignCenter)
        preview_label.setProperty('class', 'config_label')
        self.preview_widget = PreviewWidget()
        preview_widget_container = QHBoxLayout()
        preview_widget_container.addStretch(1)
        preview_widget_container.addWidget(self.preview_widget)
        preview_widget_container.addStretch(1)
        preview_layout.addWidget(preview_label)
        preview_layout.addLayout(preview_widget_container)
        preview_layout.addStretch()
        config_layout.addWidget(preview_frame)
        return config_frame
    def update_opacity_value(self, value):
        self.opacity_value.setText(str(value))
    def update_config_options(self):
        num_videos = int(self.combo_num_videos.currentText())
        self.combo_layout.clear()
        if num_videos == 1:
            self.combo_layout.setVisible(False)
            self.combo_layout.parent().setVisible(False)
            self.combo_audio.setCurrentText('Custom Audio')
        else:
            self.combo_layout.setVisible(True)
            self.combo_layout.parent().setVisible(True)
            if num_videos == 2:
                self.combo_layout.addItems(['Horizontal', 'Vertical', 'Overlay'])
            else:
                if num_videos == 3:
                    self.combo_layout.addItems(['Horizontal', 'Vertical'])
                else:
                    self.combo_layout.addItems(['Horizontal', 'Vertical', '2x2 Grid'])
        self.overlay_frame.setVisible(False)
        self.ratio_frame.setVisible(False)
        layout_mode = self.combo_layout.currentText() if num_videos > 1 else 'Single'
        if layout_mode == 'Overlay':
            self.overlay_frame.setVisible(True)
            self.ratio_frame.setVisible(False)
            self.combo_format.setCurrentText('Free')
            self.combo_format.setVisible(False)
            self.combo_format.parent().setVisible(False)
        else:
            if num_videos == 2 and layout_mode in ['Horizontal', 'Vertical']:
                self.overlay_frame.setVisible(False)
                self.ratio_frame.setVisible(True)
                self.combo_format.setVisible(True)
                self.combo_format.parent().setVisible(True)
            else:
                self.overlay_frame.setVisible(False)
                self.ratio_frame.setVisible(False)
                self.combo_format.setCurrentText('Free')
                self.combo_format.setVisible(False)
                self.combo_format.parent().setVisible(False)
        self.update_audio_options()
        self.update_preview()
    def update_preview(self):
        num_videos = int(self.combo_num_videos.currentText())
        layout_mode = self.combo_layout.currentText() if num_videos > 1 else 'Single'
        ratio = self.slider_ratio.value() if hasattr(self, 'slider_ratio') else 5
        output_format = self.combo_format.currentText() if self.combo_format.isVisible() else 'Free'
        if layout_mode == 'Overlay':
            self.overlay_frame.setVisible(True)
            self.ratio_frame.setVisible(False)
        else:
            if num_videos == 2 and layout_mode in ['Horizontal', 'Vertical']:
                self.overlay_frame.setVisible(False)
                self.ratio_frame.setVisible(True)
            else:
                self.overlay_frame.setVisible(False)
                self.ratio_frame.setVisible(False)
        if num_videos == 2:
            self.preview_widget.update_preview(layout_mode, num_videos, ratio, output_format)
        else:
            self.preview_widget.update_preview(layout_mode, num_videos, 5, 'Free')
        self.preview_widget.repaint()
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
        self.tree_output = core_widgets.create_output_tree(
            ['No.', 'Input Videos', 'Output Video', 'Duration', 'Resolution', 'Format', 'Status'],
            column_widths=[50, 100, 250, 80, 80, 80, 80]
        )
        tree_layout.addWidget(self.tree_output)
        output_layout.addWidget(tree_frame)
        return output_frame
    def setup_style(self):
        self.setStyleSheet('\n            QMainWindow { background-color: #f8f9fa; }\n            QFrame#top_frame, QFrame#bottom_frame { background-color: transparent; border: none; }\n            QFrame#input_frame, QFrame#config_frame, QFrame#progress_frame, QFrame#output_frame {\n                background-color: white; border: 2px solid #dee2e6; border-radius: 8px;\n            }\n            QFrame#sub_frame { background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; }\n            QLabel#sub_title { color: #495057; font-size: 14px; font-weight: bold; padding: 5px; }\n            QLabel { padding: 5px; }\n            QLabel#dir_label { padding-left: 10px; padding-right: 10px; }\n            QLabel.status_label { \n                color: #1976d2; \n                font-weight: bold; \n                background-color: #e3f2fd; \n                border: 1px solid #bbdefb; \n                border-radius: 4px; \n                padding: 4px 8px; \n            }\n            QLabel.config_label {\n                color: #1976d2;\n                font-weight: bold;\n                font-size: 11px;\n                padding: 2px 4px;\n                background-color: #e3f2fd;\n                border: 1px solid #bbdefb;\n                border-radius: 3px;\n            }\n            QPushButton {\n                background-color: #007bff; color: white; border: none; border-radius: 4px; padding: 5px 10px;\n                min-width: 100px; max-width: 120px; font-weight: bold; font-size: 12px;\n            }\n            QPushButton:hover { background-color: #0056b3; }\n            QPushButton:disabled { background-color: #6c757d; }\n            QPushButton[delete=\"true\"] { background-color: #dc3545; }\n            QPushButton[delete=\"true\"]:hover { background-color: #c82333; }\n            QTreeWidget { border: 1px solid #dee2e6; border-radius: 4px; }\n            QTreeWidget::item { padding: 5px; border-bottom: 1px solid #dee2e6; }\n            QTreeWidget::item:selected { background-color: #007bff; color: white; }\n            QHeaderView::section { \n                background-color: #e3f2fd; \n                padding: 5px; \n                border: 1px solid #bbdefb; \n                font-weight: bold; \n                text-align: center; \n                color: #1976d2; \n            }\n            QProgressBar { \n                border: 1px solid #dee2e6; \n                border-radius: 4px; \n                text-align: center; \n                background-color: #f8f9fa; \n                font-weight: bold; \n            }\n            QProgressBar::chunk { background-color: #e3f2fd; border-radius: 3px; }\n            QTextEdit { background-color: black; color: white; font-family: Consolas; border-radius: 4px; }\n            QFrame#progress_info_frame { background-color: #e3f2fd; border: 1px solid #bbdefb; border-radius: 4px; }\n            QFrame#canvas { background-color: #f0f0f0; border: none; }\n            QComboBox {\n                border: 1px solid #bdc3c7;\n                border-radius: 3px;\n                padding: 1px 12px 1px 3px;\n                background: white;\n                min-height: 20px;\n                font-size: 11px;\n            }\n            QComboBox:hover { \n                border-color: #3498db; \n            }\n            QComboBox:focus { \n                border-color: #2980b9; \n            }\n            QComboBox::drop-down {\n                border: none;\n                width: 12px;\n            }\n            QComboBox::down-arrow {\n                width: 4px;\n                height: 4px;\n                margin-right: 4px;\n                image: none;\n                border: none;\n                border-radius: 2px;\n                background-color: #3498db;\n                opacity: 0.7;\n            }\n            QComboBox::down-arrow:hover {\n                background-color: #2980b9;\n                opacity: 1;\n            }\n            QComboBox::down-arrow:on {\n                background-color: #2980b9;\n                opacity: 1;\n            }\n            QComboBox QAbstractItemView {\n                border: 1px solid #bdc3c7;\n                selection-background-color: #3498db;\n                selection-color: white;\n                background: white;\n                font-size: 11px;\n            }\n            QSlider::groove:horizontal {\n                border: 1px solid #bdc3c7;\n                height: 8px;\n                background: #f0f0f0;\n                margin: 2px 0;\n                border-radius: 4px;\n            }\n            QSlider::handle:horizontal {\n                background: #007bff;\n                border: 1px solid #0056b3;\n                width: 18px;\n                margin: -5px 0;\n                border-radius: 9px;\n            }\n        ')
    def load_config(self) -> dict:
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
        try:
            config = {'version': 1, 'last_output_dir': self.output_directory, 'group1_videos': self.group1_videos, 'group2_videos': self.group2_videos, 'group3_videos': self.group3_videos, 'group4_videos': self.group4_videos, 'audio_files': self.audio_files, 'num_videos': self.combo_num_videos.currentText(), 'layout_mode': self.combo_layout.currentText(), 'audio_source': self.combo_audio.currentText(), 'opacity': self.combo_overlay_group.currentText() if hasattr(self, 'slider_opacity') else 50, 'overlay_group': self.combo_overlay_group.currentText() if hasattr(self, 'combo_overlay_group') else 'Group 1'}
            core_config.save(Path(CONFIG_FILE), config)
        except (OSError, TypeError) as e:
            error_msg = f'Cannot save configuration: {str(e)}\n{traceback.format_exc()}'
            print(f'Config Error: {error_msg}')
            QMessageBox.warning(self, 'Warning', f'Cannot save configuration: {str(e)}')
    def update_video_counts(self):
        self.btn_group1.setText(f'Group 1 ({len(self.group1_videos)})')
        self.btn_group2.setText(f'Group 2 ({len(self.group2_videos)})')
        self.btn_group3.setText(f'Group 3 ({len(self.group3_videos)})')
        self.btn_group4.setText(f'Group 4 ({len(self.group4_videos)})')
        self.btn_audio.setText(f'🎵 Audio ({len(self.audio_files)})')
        self.btn_delete.setEnabled(bool(self.group1_videos or self.group2_videos or self.group3_videos or self.group4_videos or self.audio_files))
    def select_videos(self, video_list: List[str], title: str, config_key: str):
        try:
            initial_dir = self.config.get(config_key, os.getcwd())
            file_paths = core_file_picker.pick_files(self, title, initial_dir, core_file_picker.MEDIA_FILTER)
            if file_paths:
                new_files = [fp for fp in file_paths if fp not in video_list]
                if not new_files:
                    QMessageBox.information(self, 'Information', 'No new files added.')
                    return
                video_list.extend(new_files)
                self.config[config_key] = os.path.dirname(file_paths[0])
                self.save_config()
                self.update_video_tree()
                self.btn_delete.setEnabled(True)
                self.update_video_counts()
                self.logger.info(f'Added {len(new_files)} files to {title}.')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Cannot select files: {str(e)}')
    def select_group1_videos(self):
        self.select_videos(self.group1_videos, 'Select Group 1 Files', 'last_group1_dir')
    def select_group2_videos(self):
        self.select_videos(self.group2_videos, 'Select Group 2 Files', 'last_group2_dir')
    def select_group3_videos(self):
        self.select_videos(self.group3_videos, 'Select Group 3 Files', 'last_group3_dir')
    def select_group4_videos(self):
        self.select_videos(self.group4_videos, 'Select Group 4 Files', 'last_group4_dir')
    def delete_selected_videos(self):
        selected_items = self.tree_videos.selectedItems()
        if not selected_items:
            QMessageBox.information(self, 'Information', 'No file selected to delete.')
            return
        else:
            reply = QMessageBox.question(self, 'Confirm Delete', 'Are you sure you want to delete the selected files?', QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                for item in selected_items:
                    file_type = item.text(0)
                    file_path = item.text(2)
                    if file_type == 'Group 1':
                        self.group1_videos = [v for v in self.group1_videos if os.path.basename(v)!= file_path]
                    else:
                        if file_type == 'Group 2':
                            self.group2_videos = [v for v in self.group2_videos if os.path.basename(v)!= file_path]
                        else:
                            if file_type == 'Group 3':
                                self.group3_videos = [v for v in self.group3_videos if os.path.basename(v)!= file_path]
                            else:
                                if file_type == 'Group 4':
                                    self.group4_videos = [v for v in self.group4_videos if os.path.basename(v)!= file_path]
                                else:
                                    if file_type == 'Audio':
                                        self.audio_files = [a for a in self.audio_files if os.path.basename(a)!= file_path]
                self.update_video_tree()
                self.update_video_counts()
                self.btn_audio.setText(f'🎵 Audio ({len(self.audio_files)})')
                self.update_audio_options()
                self.btn_delete.setEnabled(bool(self.group1_videos or self.group2_videos or self.group3_videos or self.group4_videos or self.audio_files))
    def fetch_video_metadata(self, file_path: str) -> Tuple[str, str, str, str]:
        try:
            ext = os.path.splitext(file_path)[1].lower()
            format = os.path.splitext(file_path)[1].upper().replace('.', '')
            if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff']:
                return (file_path, 'Image', self.get_image_resolution(file_path), format)
            if ext in ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm']:
                return (file_path, self.get_video_duration(file_path), self.get_video_resolution(file_path), format)
            if ext in ['.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac', '.wma']:
                return (file_path, self.get_audio_duration(file_path), 'Audio File', format)
            return (file_path, 'Unknown', 'Unknown', format)
        except Exception as e:
            self.logger.error(f'Error getting file info for {file_path}: {str(e)}')
            return (file_path, 'Unknown', 'Unknown', 'Unknown')
    def get_image_resolution(self, image_path: str) -> str:
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                width, height = img.size
                return f'{width}x{height}'
        except Exception as e:
            self.logger.error(f'Error getting image resolution for {image_path}: {str(e)}')
            return 'Unknown'
    def get_audio_duration(self, audio_path: str) -> str:
        cmd = [str(FFPROBE_PATH), '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
        startupinfo = core_ffmpeg_runner.hidden_startupinfo()
        result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo, creationflags=core_ffmpeg_runner.hidden_creationflags(), encoding='utf-8', errors='replace')
        try:
            duration_seconds = float(result.stdout.strip())
            hours, remainder = divmod(int(duration_seconds), 3600)
            minutes, seconds = divmod(remainder, 60)
            return f'{hours:02d}:{minutes:02d}:{seconds:02d}'
        except Exception:
            return 'Unknown'
    def update_video_tree(self):
        self.tree_videos.clear()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            video_types = [(self.group1_videos, 'Group 1', '#007bff'), (self.group2_videos, 'Group 2', '#28a745'), (self.group3_videos, 'Group 3', '#fd7e14'), (self.group4_videos, 'Group 4', '#dc3545'), (self.audio_files, 'Audio', '#7b1fa2')]
            counters = {'Group 1': 1, 'Group 2': 1, 'Group 3': 1, 'Group 4': 1, 'Audio': 1}
            for files, file_type, color in video_types:
                for file in files:
                    futures.append((executor.submit(self.fetch_video_metadata, file), file_type, color))
            for future, file_type, color in futures:
                file_path, duration, resolution, format = future.result()
                item = QTreeWidgetItem(self.tree_videos)
                item.setText(0, file_type)
                item.setText(1, str(counters[file_type]))
                item.setText(2, os.path.basename(file_path))
                item.setText(3, duration)
                item.setText(4, resolution if file_type!= 'Audio' else 'Audio File')
                item.setText(5, format)
                item.setForeground(0, QColor(color))
                counters[file_type] += 1
    def get_video_duration(self, video_path: str) -> str:
        cmd = [str(FFPROBE_PATH), '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
        startupinfo = core_ffmpeg_runner.hidden_startupinfo()
        result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo, creationflags=core_ffmpeg_runner.hidden_creationflags(), encoding='utf-8', errors='replace')
        duration_seconds = float(result.stdout.strip())
        hours, remainder = divmod(int(duration_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}'
    def get_video_resolution(self, video_path: str) -> str:
        cmd = [str(FFPROBE_PATH), '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0', video_path]
        startupinfo = core_ffmpeg_runner.hidden_startupinfo()
        result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo, creationflags=core_ffmpeg_runner.hidden_creationflags(), encoding='utf-8', errors='replace')
        return result.stdout.strip() or 'Unknown'
    def select_output_directory(self):
        try:
            output_dir = core_file_picker.pick_directory(self, 'Select Output Directory', self.output_directory or os.getcwd())
            if output_dir:
                self.output_directory = output_dir
                self.dir_label.setText(f'{self.output_directory}')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Cannot select output directory: {str(e)}')
    def create_progress_box(self, index: int) -> QFrame:
        box = QFrame(self.canvas)
        box.setGeometry(index % self.boxes_per_row * (self.box_size + self.padding), index // self.boxes_per_row * (self.box_size + self.padding), self.box_size, self.box_size)
        box.setStyleSheet('\n            background-color: lightgray; border: 1px solid #666666; border-radius: 2px;\n        ')
        box.show()
        return box
    def update_box_color(self, index: int, color: str):
        if 0 <= index < len(self.progress_boxes):
            styles = {'green': 'background-color: #4CAF50; border: 1px solid #2E7D32;', 'yellow': 'background-color: #FFC107; border: 1px solid #FFA000;', 'red': 'background-color: #F44336; border: 1px solid #D32F2F;', 'default': 'background-color: lightgray; border: 1px solid #666666;'}
            self.progress_boxes[index].setStyleSheet(f"{styles.get(color, styles['default'])} border-radius: 2px;")
    def clear_progress_boxes(self):
        for box in self.progress_boxes:
            box.deleteLater()
        self.progress_boxes.clear()
    def start_merge(self):
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
            self.tree_output.clear()
            self.cancel_event.clear()
            self.clear_progress_boxes()
            num_videos = int(self.combo_num_videos.currentText())
            video_groups = [self.group1_videos, self.group2_videos]
            if num_videos >= 3:
                video_groups.append(self.group3_videos)
            if num_videos == 4:
                video_groups.append(self.group4_videos)
            max_videos = max((len(group) for group in video_groups))
            for i in range(max_videos):
                self.progress_boxes.append(self.create_progress_box(i))
                self.update_box_color(i, 'default')
            self.progress_label.setText(f'Progress: 0/{max_videos}')
            self.processed_output = 0
            threading.Thread(target=self.merge_videos, daemon=True).start()
    def merge_videos(self):
        try:
            num_videos = int(self.combo_num_videos.currentText())
            layout_mode = self.combo_layout.currentText()
            audio_source = self.combo_audio.currentText()
            opacity = self.slider_opacity.value() if layout_mode == 'Overlay' else 100
            overlay_group = self.combo_overlay_group.currentText() if layout_mode == 'Overlay' else ''
            audio_mode = getattr(self, 'audio_mode', 'Tuần tự')
            video_groups = [self.group1_videos]
            if num_videos >= 2:
                video_groups.append(self.group2_videos)
            if num_videos >= 3:
                video_groups.append(self.group3_videos)
            if num_videos == 4:
                video_groups.append(self.group4_videos)
            max_videos = max((len(group) for group in video_groups))
            if max_videos == 0:
                QMessageBox.warning(self, 'Warning', 'No videos in any group!')
                self.is_merging = False
                self.btn_start.setEnabled(True)
                self.btn_cancel.setEnabled(False)
                self.save_config()
                return
            group_indices = [0] * len(video_groups)
            for output_index in range(max_videos):
                if self.cancel_event.is_set():
                    break
                try:
                    videos_to_merge = []
                    for i, group in enumerate(video_groups):
                        if group:
                            video_index = group_indices[i] % len(group)
                            videos_to_merge.append(group[video_index])
                            group_indices[i] += 1
                    custom_audio = None
                    if audio_source == 'Custom Audio' and self.audio_files:
                        if self.combo_audio_mode.currentText() == '🔁 Order':
                            audio_index = output_index % len(self.audio_files)
                            custom_audio = self.audio_files[audio_index]
                        else:
                            import random
                            custom_audio = random.choice(self.audio_files)
                    current_time = datetime.now().strftime('%d%m%y_%H%M%S')
                    output_filename = f'merge_{current_time}_{output_index + 1}.mp4'
                    output_path = os.path.join(self.output_directory, output_filename)
                    output_duration = '00:00:00'
                    output_resolution = 'Unknown'
                    output_format = 'MP4'
                    durations = [self.get_video_duration(video) for video in videos_to_merge]
                    output_duration = max(durations, key=lambda x: sum((int(i) * j for i, j in zip(x.split(':'), [3600, 60, 1]))))
                    if layout_mode == 'Horizontal':
                        heights = []
                        widths = []
                        for video in videos_to_merge:
                            res = self.get_video_resolution(video)
                            if res!= 'Unknown':
                                w, h = map(int, res.split('x'))
                                heights.append(h)
                                widths.append(w)
                        if heights and widths:
                            max_height = max(heights)
                            total_width = sum(widths)
                            output_resolution = f'{total_width}x{max_height}'
                    else:
                        if layout_mode == 'Vertical':
                            heights = []
                            widths = []
                            for video in videos_to_merge:
                                res = self.get_video_resolution(video)
                                if res!= 'Unknown':
                                    w, h = map(int, res.split('x'))
                                    heights.append(h)
                                    widths.append(w)
                            if heights and widths:
                                max_width = max(widths)
                                total_height = sum(heights)
                                output_resolution = f'{max_width}x{total_height}'
                        else:
                            if layout_mode == '2x2 Grid':
                                res = self.get_video_resolution(videos_to_merge[0])
                                if res!= 'Unknown':
                                    w, h = map(int, res.split('x'))
                                    output_resolution = f'{w * 2}x{h * 2}'
                            else:
                                output_resolution = self.get_video_resolution(videos_to_merge[0])
                    item = QTreeWidgetItem(self.tree_output)
                    item.setText(0, str(output_index + 1))
                    item.setText(1, ', '.join((os.path.basename(v) for v in videos_to_merge)))
                    if custom_audio:
                        item.setText(1, item.text(1) + f' + {os.path.basename(custom_audio)}')
                    item.setText(2, output_filename)
                    item.setText(3, output_duration)
                    item.setText(4, output_resolution)
                    item.setText(5, output_format)
                    item.setText(6, '⏳ Waiting...')
                    worker = MergeWorker(videos_to_merge, output_path, output_index, FFMPEG_PATH, 'Random', layout_mode, opacity, audio_source, self.combo_format.currentText(), self.slider_ratio.value(), custom_audio, self.is_boost_mode)
                    worker.setAutoDelete(True)
                    worker.signals.progress_updated.connect(self.update_thread_progress)
                    worker.signals.status_updated.connect(self.update_thread_status)
                    worker.signals.output_updated.connect(self.update_ffmpeg_output)
                    worker.signals.merge_completed.connect(self.on_merge_completed)
                    worker.signals.error_occurred.connect(self.on_merge_error)
                    self.thread_pool.start(worker)
                except Exception as e:
                    error_msg = f'Lỗi khi xử lý video {output_index + 1}: {str(e)}'
                    print(f'Merge Error: {error_msg}')
                    self.logger.error(error_msg)
                    self.on_merge_error(error_msg)
        except Exception as e:
            error_msg = f'Error merging: {str(e)}\n{traceback.format_exc()}'
            print(f'Merge Error: {error_msg}')
            self.logger.error(error_msg)
            QMessageBox.critical(self, 'Error', f'Unexpected error occurred: {str(e)}')
        finally:
            self.is_merging = False
            self.btn_start.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.save_config()
    def cancel_merge(self):
        if self.is_merging:
            reply = QMessageBox.question(self, 'Confirm Stop', 'Are you sure you want to stop the merging process?', QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.cancel_event.set()
                self.btn_cancel.setEnabled(False)
                for worker in list(MergeWorker.running_workers):
                    if worker.process and worker.process.poll() is None:
                        try:
                            worker.is_cancelled = True
                            worker.process.terminate()
                        except Exception:
                            pass
                for i in range(self.tree_output.topLevelItemCount()):
                    item = self.tree_output.topLevelItem(i)
                    if item.text(5) == '⏳ Waiting...':
                        item.setText(3, 'Cancelled')
                        item.setText(4, 'Cancelled')
                        item.setText(5, '🟡 Cancelled')
                for i in range(self.processed_output, len(self.progress_boxes)):
                    self.update_box_color(i, 'red')
                for label, bar in zip(self.thread_labels, self.thread_bars):
                    label.setText('Cancelled')
                    bar.setValue(0)
                QMessageBox.information(self, 'Information', 'Merging process has been stopped.')
                self.is_merging = False
                self.btn_start.setEnabled(True)
                self.save_config()
    def validate_inputs(self) -> bool:
        try:
            num_videos = int(self.combo_num_videos.currentText())
            video_groups = [self.group1_videos]
            if num_videos >= 2:
                video_groups.append(self.group2_videos)
            if num_videos >= 3:
                video_groups.append(self.group3_videos)
            if num_videos == 4:
                video_groups.append(self.group4_videos)
            for i, group in enumerate(video_groups, 1):
                if not group:
                    error_msg = f'Please select at least one file for Group {i}.'
                    print(f'Validation Error: {error_msg}')
                    QMessageBox.warning(self, 'Warning', error_msg)
                    return False
            if self.combo_audio.currentText() == 'Custom Audio' and (not self.audio_files):
                error_msg = 'Please select at least one audio file when using Custom Audio.'
                print(f'Validation Error: {error_msg}')
                QMessageBox.warning(self, 'Warning', error_msg)
                return False
            if not self.output_directory:
                error_msg = 'Please select output directory.'
                print(f'Validation Error: {error_msg}')
                QMessageBox.warning(self, 'Warning', error_msg)
                return False
            return True
        except Exception as e:
            error_msg = f'Error validating inputs: {str(e)}\n{traceback.format_exc()}'
            print(f'Validation Error: {error_msg}')
            self.logger.error(error_msg)
            QMessageBox.critical(self, 'Error', f'Error validating inputs: {str(e)}')
            return False
    def update_thread_progress(self, thread_index: int, progress: int):
        if 0 <= thread_index < len(self.thread_bars):
            self.thread_bars[thread_index].setValue(progress)
    def update_thread_status(self, thread_index: int, status: str):
        if 0 <= thread_index < len(self.thread_labels):
                self.thread_labels[thread_index].setText(status)
        if 'Bắt đầu xử lý' in status:
            if 0 <= thread_index < len(self.progress_boxes):
                    self.update_box_color(thread_index, 'yellow')
            for i in range(self.tree_output.topLevelItemCount()):
                item = self.tree_output.topLevelItem(i)
                if item.text(6) == '⏳ Waiting...':
                    item.setText(6, '🔄 Processing...')
                    break
        if status == 'Hoàn thành':
            if 0 <= thread_index < len(self.progress_boxes):
                    self.update_box_color(thread_index, 'green')
        if status == 'Lỗi':
            if 0 <= thread_index < len(self.progress_boxes):
                    self.update_box_color(thread_index, 'red')
        if status == 'Đã hủy':
            if 0 <= thread_index < len(self.progress_boxes):
                self.update_box_color(thread_index, 'red')
    def update_ffmpeg_output(self, output: str):
        return
    def on_merge_completed(self, output_filename: str):
        self.processed_output += 1
        self.progress_label.setText(f'Progress: {self.processed_output}/{len(self.progress_boxes)}')
        for i in range(self.tree_output.topLevelItemCount()):
            item = self.tree_output.topLevelItem(i)
            if item.text(2) == output_filename:
                item.setText(6, '🟢 Completed')
                break
    def on_merge_error(self, error_message: str):
        print(f'Merge Worker Error: {error_message}')
        self.processed_output += 1
        self.progress_label.setText(f'Progress: {self.processed_output}/{len(self.progress_boxes)}')
        for i in range(self.tree_output.topLevelItemCount()):
            item = self.tree_output.topLevelItem(i)
            if item.text(6) in ['⏳ Waiting...', '🔄 Processing...']:
                item.setText(6, '🔴 Error')
                break
    def load_last_paths(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.group1_videos = config.get('group1_videos', [])
                    self.group2_videos = config.get('group2_videos', [])
                    self.group3_videos = config.get('group3_videos', [])
                    self.group4_videos = config.get('group4_videos', [])
                    self.audio_files = config.get('audio_files', [])
                    self.combo_num_videos.setCurrentText(config.get('num_videos', '2'))
                    self.combo_layout.setCurrentText(config.get('layout_mode', 'Horizontal'))
                    self.combo_audio.setCurrentText(config.get('audio_source', 'Longest'))
                    if hasattr(self, 'slider_opacity'):
                        self.slider_opacity.setValue(config.get('opacity', 50))
                        self.opacity_value.setText(str(config.get('opacity', 50)))
                    if hasattr(self, 'combo_overlay_group'):
                        self.combo_overlay_group.setCurrentText(config.get('overlay_group', 'Group 1'))
                    last_output = config.get('last_output_dir', '')
                    if last_output and os.path.isdir(last_output):
                        self.output_directory = last_output
                        self.dir_label.setText(f'Output Directory: {self.output_directory}')
                    self.update_video_tree()
                    self.update_video_counts()
                    self.update_config_options()
                    self.update_preview()
                    self.update_audio_options()
            except Exception as e:
                error_msg = f'Error loading configuration: {str(e)}\n{traceback.format_exc()}'
                print(f'Config Error: {error_msg}')
                QMessageBox.warning(self, 'Warning', f'Error loading configuration: {str(e)}')
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
        readme_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'README Merge.md')
        dialog = HelpDialog(self, 'Help - 1vmo Merge', readme_path)
        dialog.exec_()
    def update_ratio_value(self, value):
        self.ratio_value.setText(f'{value}:{10 - value}')
        self.update_preview()
    def toggle_boost(self):
        self.is_boost_mode = not self.is_boost_mode
        core_widgets.set_boost_on_style(self.btn_boost, self.is_boost_mode)
    def get_ffmpeg_params(self):
        if self.is_boost_mode:
            return ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28', '-c:a', 'aac', '-b:a', '128k', '-async', '1', '-vsync', '1', '-movflags', '+faststart', '-pix_fmt', 'yuv420p', '-max_muxing_queue_size', '1024', '-threads', '3', '-avoid_negative_ts', 'make_zero']
        else:
            return ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-c:a', 'aac', '-b:a', '192k', '-async', '1', '-vsync', '1', '-movflags', '+faststart', '-pix_fmt', 'yuv420p', '-max_muxing_queue_size', '1024', '-threads', '3', '-avoid_negative_ts', 'make_zero']
    def update_audio_options(self):
        """Cập nhật tùy chọn audio dựa trên lựa chọn"""
        if self.combo_audio.currentText() == 'Custom Audio':
            self.audio_mode_frame.setVisible(True)
        else:
            self.audio_mode_frame.setVisible(False)
    def select_audio_files(self):
        """Chọn file audio"""
        try:
            initial_dir = self.config.get('last_audio_dir', os.getcwd())
            file_paths = core_file_picker.pick_files(self, 'Select Audio Files', initial_dir, core_file_picker.AUDIO_FILTER)
            if file_paths:
                new_files = [fp for fp in file_paths if fp not in self.audio_files]
                if not new_files:
                    QMessageBox.information(self, 'Information', 'No new files added.')
                    return
                self.audio_files.extend(new_files)
                self.config['last_audio_dir'] = os.path.dirname(file_paths[0])
                self.save_config()
                self.update_video_tree()
                self.btn_audio.setText(f'🎵 Audio ({len(self.audio_files)})')
                self.update_audio_options()
                self.logger.info(f'Added {len(new_files)} audio files.')
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Cannot select audio files: {str(e)}')
    def update_audio_mode(self, value):
        self.audio_mode = value
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = VideoMergeTool()
    window.show()
    sys.exit(app.exec_())