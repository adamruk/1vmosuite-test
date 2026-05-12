# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'updater.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional, Tuple

import requests
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class UpdaterDialog(QDialog):
    def __init__(self, current_version: str, new_version: str, parent=None):
        super().__init__(parent)
        self.current_version = current_version
        self.new_version = new_version
        self.init_ui()

    def init_ui(self):
        """Khởi tạo giao diện người dùng"""
        self.setWindowTitle("Update Available")
        self.setFixedWidth(400)
        self.setStyleSheet(
            "\n            QDialog {\n                background-color: #f8f9fa;\n            }\n            QLabel {\n                color: #2c3e50;\n                font-size: 13px;\n            }\n            QLabel#titleLabel {\n                font-size: 18px;\n                font-weight: bold;\n                color: #2c3e50;\n                padding: 10px;\n            }\n            QPushButton {\n                padding: 8px 16px;\n                border-radius: 4px;\n                font-size: 13px;\n                font-weight: bold;\n            }\n            QPushButton#updateButton {\n                background-color: #2ecc71;\n                color: white;\n                border: none;\n            }\n            QPushButton#updateButton:hover {\n                background-color: #27ae60;\n            }\n            QPushButton#cancelButton {\n                background-color: #e74c3c;\n                color: white;\n                border: none;\n            }\n            QPushButton#cancelButton:hover {\n                background-color: #c0392b;\n            }\n        "
        )
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        title_label = QLabel("✨ New Version Available!")
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        version_info = QLabel(f"v{self.current_version} → v{self.new_version}")
        version_info.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_info)
        update_msg = QLabel(
            "📥 The tool will download and install the update automatically.\n\nDo you want to update now?"
        )
        update_msg.setAlignment(Qt.AlignCenter)
        update_msg.setWordWrap(True)
        layout.addWidget(update_msg)
        button_layout = QHBoxLayout()
        update_btn = QPushButton("🚀 Update Now")
        update_btn.setObjectName("updateButton")
        update_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("❌ Later")
        cancel_btn.setObjectName("cancelButton")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(update_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)


class DriveUpdater:
    def __init__(self):
        """\n        Khởi tạo updater\n"""
        self.progress_dialog = None
        self.progress_bar = None
        self.version_file = os.path.join(
            os.path.dirname(__file__), "assets", "Version AutoRender.json"
        )
        try:
            icon_path = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "assets", "update.ico")
            )
            if os.path.exists(icon_path):
                self.icon = QIcon(icon_path)
            else:
                print(f"Warning: Icon file not found at {icon_path}")
                self.icon = None
        except Exception as e:
            print(f"Error loading dialog icon: {str(e)}")
            self.icon = None

    def _load_current_version(self, app_name: str) -> str:
        """Đọc version hiện tại từ file JSON"""
        try:
            if os.path.exists(self.version_file):
                with open(self.version_file, "r") as f:
                    data = json.load(f)
                    return data.get("software", {}).get(app_name, {}).get("version")
        except Exception as e:
            print(f"Error reading version file: {str(e)}")
        return None

    def _save_current_version(self, version: str, app_name: str) -> None:
        """Lưu version hiện tại vào file JSON"""
        try:
            data = {}
            if os.path.exists(self.version_file):
                with open(self.version_file, "r") as f:
                    data = json.load(f)
            if "software" not in data:
                data["software"] = {}
            if app_name not in data["software"]:
                data["software"][app_name] = {}
            data["software"][app_name]["version"] = version
            with open(self.version_file, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving version file: {str(e)}")

    def check_and_update(self, app_name: str) -> None:
        """\n        Kiểm tra và cập nhật version nếu cần\n        \n        Args:\n            app_name: Tên ứng dụng (ví dụ: \"1vmo Auto Render\")\n"""
        try:
            saved_version = self._load_current_version(app_name)
            if saved_version is None:
                saved_version = "1.0"
                self._save_current_version(saved_version, app_name)
            version_info = self._get_version_info()
            if not version_info:
                print("Cannot read version information")
                return
            for exe_name, base_name, version, download_link in version_info:
                if base_name == app_name:
                    if self._compare_versions(version, saved_version) <= 0:
                        print("You are using the latest version")
                        return
                    dialog = UpdaterDialog(saved_version, version)
                    if self.icon:
                        dialog.setWindowIcon(self.icon)
                    if dialog.exec() == QDialog.Rejected:
                        print("Update postponed")
                        return
                    is_asset = "assets" in exe_name.lower()
                    success, status_message = self._download_and_install(
                        download_link,
                        f"{app_name} v{saved_version}.{('rar' if is_asset else 'exe')}",
                        exe_name,
                        is_asset,
                    )
                    if success:
                        self._save_current_version(version, app_name)
                        current_exe = sys.argv[0]
                        current_exe_name = os.path.basename(current_exe)
                        delete_msg = QMessageBox()
                        if self.icon:
                            delete_msg.setWindowIcon(self.icon)
                        delete_msg.setWindowTitle("Delete Old Version")
                        delete_msg.setText(
                            f"🗑️ Do you want to delete the old version?\n\n📂 {current_exe_name}"
                        )
                        delete_msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                        delete_msg.setIcon(QMessageBox.Question)
                        msg_box = QMessageBox()
                        if self.icon:
                            msg_box.setWindowIcon(self.icon)
                        msg_box.setWindowTitle("Update")
                        msg_box.setText(
                            f"✨ Update completed successfully!\n\nv{saved_version} → v{version}\n📥 {status_message}\n\n🔄 The new version will be launched automatically."
                        )
                        msg_box.setStandardButtons(QMessageBox.Ok)
                        msg_box.setIcon(QMessageBox.Information)
                        msg_box.exec()
                        if delete_msg.exec() == QMessageBox.Yes:
                            try:
                                import ctypes

                                kernel32 = ctypes.WinDLL(
                                    "kernel32", use_last_error=True
                                )
                                process = kernel32.OpenProcess(16, False, os.getpid())
                                kernel32.CloseHandle(process)
                                batch_content = f'@echo off\ntimeout /t 1 /nobreak >nul\ndel /f "{current_exe}"\ndel /f "%~f0"\n'
                                batch_file = "delete_old.bat"
                                with open(batch_file, "w") as f:
                                    f.write(batch_content)
                                subprocess.Popen(
                                    ["cmd", "/c", batch_file],
                                    creationflags=subprocess.CREATE_NO_WINDOW,
                                )
                            except Exception as e:
                                print(f"Error deleting old version: {str(e)}")
                        try:
                            subprocess.Popen([exe_name], shell=True)
                            sys.exit(0)
                        except Exception as e:
                            print(f"Error launching new version: {str(e)}")
                        return
                    else:
                        msg_box = QMessageBox()
                        if self.icon:
                            msg_box.setWindowIcon(self.icon)
                        msg_box.setWindowTitle("Update Error")
                        msg_box.setText(f"❌ Update failed!\n\n{status_message}")
                        msg_box.setStandardButtons(QMessageBox.Ok)
                        msg_box.setIcon(QMessageBox.Critical)
                        msg_box.exec()
                        return
            print(f"No version information found for {app_name}")
        except Exception as e:
            print(f"Error checking for updates: {str(e)}")

    def _get_version_info(self) -> Optional[list]:
        """Tải và đọc thông tin phiên bản từ Google Sheet"""
        try:
            spreadsheet_id = "1krEmBJDqA5GfHzBanaH-6r07G7qI2odAr-7wlpyQvgo"
            range_name = "Version!A2:Z"
            url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?tqx=out:csv&sheet={range_name}"
            response = requests.get(url)
            if response.status_code != 200:
                print(f"Lỗi khi truy cập Google Sheet: {response.status_code}")
                return
            content = response.text.strip()
            version_info = []
            for line in content.split("\n")[1:]:
                if line.strip():
                    parts = line.strip('"').split('","')
                    if len(parts) >= 3:
                        exe_name = parts[0].strip()
                        version = parts[1].strip()
                        download_link = parts[2].strip()
                        base_name = exe_name.split(" v")[0]
                        version_info.append(
                            (exe_name, base_name, version, download_link)
                        )
                        print(
                            f"Đã đọc được thông tin: {exe_name} - {version} - {download_link}"
                        )
            print(f"Đã đọc được {len(version_info)} phiên bản từ Google Sheet")
            return version_info
        except Exception as e:
            print(f"Lỗi khi đọc Google Sheet: {str(e)}")

    def _download_and_install(
        self,
        download_link: str,
        current_exe: str,
        new_exe_name: str,
        is_asset: bool = False,
    ) -> Tuple[bool, str]:
        """Tải file mới từ Dropbox\n        \n        Args:\n            download_link: Link tải file\n            current_exe: Tên file hiện tại\n            new_exe_name: Tên file mới\n            is_asset: True nếu là file assets (.rar), False nếu là file exe\n"""
        try:
            temp_dir = tempfile.mkdtemp()
            if is_asset:
                if not new_exe_name.lower().endswith(".rar"):
                    new_exe_name += ".rar"
            else:
                if not new_exe_name.lower().endswith(".exe"):
                    new_exe_name += ".exe"
            temp_file = os.path.join(temp_dir, new_exe_name)
            session = requests.Session()
            if "dropbox.com" in download_link:
                download_link = download_link.replace("dl=0", "dl=1")
                if "dl=" not in download_link:
                    download_link += "&dl=1"
            print(f"📥 Downloading from: {download_link}")
            response = session.get(download_link, stream=True, allow_redirects=True)
            print(f"📥 Response status: {response.status_code}")
            if response.status_code != 200:
                error_msg = f"Error downloading file: {response.status_code}"
                print(f"❌ {error_msg}")
                return (False, error_msg)
            total_size = int(response.headers.get("content-length", 0))
            print(f"📥 Total file size: {self._format_size(total_size)}")
            if total_size < 1048576:
                error_msg = "Downloaded file is too small"
                print(f"❌ {error_msg}")
                return (False, error_msg)
            block_size = 1024
            downloaded = 0
            with open(temp_file, "wb") as f:
                for chunk in response.iter_content(chunk_size=block_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
            print(f"✅ Download completed: {self._format_size(downloaded)}")
            if os.path.getsize(temp_file) < 1048576:
                error_msg = "Downloaded file is too small"
                print(f"❌ {error_msg}")
                return (False, error_msg)
            print("🔄 Moving new version to current directory...")
            shutil.move(temp_file, new_exe_name)
            print("✅ File moved successfully")
            try:
                os.rmdir(temp_dir)
                print("🧹 Cleaned up temporary directory")
            except Exception as e:
                print(f"⚠️ Error cleaning up temporary directory: {str(e)}")
            return (
                True,
                f"New version has been downloaded ({self._format_size(downloaded)})",
            )
        except Exception as e:
            error_msg = f"Error downloading: {str(e)}"
            print(f"❌ {error_msg}")
            return (False, error_msg)

    def _format_size(self, size_bytes: int) -> str:
        """Định dạng dung lượng file"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            else:
                size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

    def _compare_versions(self, v1: str, v2: str) -> int:
        """So sánh hai phiên bản"""
        v1_parts = [int(x) for x in v1.split(".")]
        v2_parts = [int(x) for x in v2.split(".")]
        for i in range(max(len(v1_parts), len(v2_parts))):
            v1_part = v1_parts[i] if i < len(v1_parts) else 0
            v2_part = v2_parts[i] if i < len(v2_parts) else 0
            if v1_part > v2_part:
                return 1
            else:
                if v1_part < v2_part:
                    return -1
        return 0
