# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'help_dialog.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox
from PyQt5.QtCore import Qt
import os
class HelpDialog(QDialog):
    def __init__(self, parent=None, title='Help', help_file=None, width=800, height=600):
        """\n        Tạo dialog help để hiển thị nội dung markdown\n        \n        Args:\n            parent: Widget cha\n            title: Tiêu đề dialog\n            help_file: Đường dẫn đến file markdown\n            width: Chiều rộng dialog\n            height: Chiều cao dialog\n        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(width, height)
        self.help_file = help_file
        self.setup_ui()
    def setup_ui(self):
        layout = QVBoxLayout(self)
        content = self.load_help_content()
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setMarkdown(content)
        text_edit.setStyleSheet('\n            QTextEdit {\n                background-color: black;\n                color: white;\n                border: 1px solid #dee2e6;\n                border-radius: 4px;\n                padding: 10px;\n                font-size: 12px;\n            }\n            QTextEdit h1 { color: #1976d2; font-size: 18px; }\n            QTextEdit h2 { color: #2196f3; font-size: 16px; }\n            QTextEdit h3 { color: #0d47a1; font-size: 14px; }\n        ')
        layout.addWidget(text_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, Qt.Horizontal, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    def load_help_content(self) -> str:
        """Đọc nội dung help từ file markdown"""
        if not self.help_file:
            return 'No help content available'
        try:
            with open(self.help_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f'Error loading help content: {str(e)}'
    def set_help_file(self, help_file: str):
        """Thiết lập file help mới"""
        self.help_file = help_file
        self.setup_ui()