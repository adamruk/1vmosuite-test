"""Shared widget construction helpers for 1vmo Suite apps."""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QTreeWidget, QWidget,
)


# ========== Output tree (all 4 apps) ==========

def create_output_tree(
    headers: Sequence[str],
    column_widths: Optional[Sequence[int]] = None,
    parent: Optional[QWidget] = None,
) -> QTreeWidget:
    """Construct a results-tree widget with the suite-wide default styling.

    Sets header labels, enables alternating row colors, centers header text,
    and optionally applies per-column widths. Callers that size columns
    dynamically (e.g. auto_render.on_resize) pass column_widths=None.
    Returns the QTreeWidget; caller wraps in tree_frame and adds to layout.
    """
    tree = QTreeWidget(parent)
    tree.setHeaderLabels(list(headers))
    tree.setAlternatingRowColors(True)
    tree.header().setDefaultAlignment(Qt.AlignCenter)
    if column_widths:
        for i, w in enumerate(column_widths):
            tree.setColumnWidth(i, w)
    return tree


# ========== Boost button (cutter + merge) ==========

# Stylesheets copied byte-for-byte from cutter.py:531 (OFF, construction site)
# and cutter.py:918 (ON, toggle_boost if-branch). Semantically identical to
# the equivalents in merge.py; verified byte-equivalent during Phase B.
_BOOST_OFF_STYLE = '\n            QPushButton {\n                background-color: #6c757d;\n                color: white;\n                border: none;\n                border-radius: 4px;\n                padding: 5px 10px;\n                font-weight: bold;\n            }\n            QPushButton:hover {\n                background-color: #5a6268;\n            }\n        '
_BOOST_ON_STYLE = '\n                QPushButton {\n                    background-color: #28a745;\n                    color: white;\n                    border: none;\n                    border-radius: 4px;\n                    padding: 5px 10px;\n                    font-weight: bold;\n                }\n                QPushButton:hover {\n                    background-color: #218838;\n                }\n            '


def create_boost_button(
    on_click: Callable[[], None],
    parent: Optional[QWidget] = None,
) -> QPushButton:
    """Construct the '⚡ Boost: OFF' toggle button used by cutter + merge.

    Caller is responsible for flipping state via set_boost_on_style() on click.
    Returns the QPushButton; caller adds to layout.
    """
    btn = QPushButton('⚡ Boost: OFF', parent)
    btn.setFixedWidth(150)
    btn.setFixedHeight(30)
    btn.setToolTip('Toggle Boost Mode')
    btn.clicked.connect(on_click)
    btn.setStyleSheet(_BOOST_OFF_STYLE)
    return btn


def set_boost_on_style(btn: QPushButton, on: bool) -> None:
    """Apply ON (green) or OFF (gray) styling + label to a boost button."""
    if on:
        btn.setText('⚡ Boost: ON')
        btn.setStyleSheet(_BOOST_ON_STYLE)
    else:
        btn.setText('⚡ Boost: OFF')
        btn.setStyleSheet(_BOOST_OFF_STYLE)


# ========== Thread row (cutter + merge + mixer; NOT auto_render) ==========

def create_thread_row_with_status_class(
    index: int,
    parent: Optional[QWidget] = None,
) -> tuple[QHBoxLayout, QLabel, QLabel, QProgressBar]:
    """Construct one row of the thread-status frame used by cutter, merge, mixer.

    Returns (row_layout, index_label, status_label, progress_bar). Callers
    add row_layout to the parent frame's QVBoxLayout (e.g. via addLayout)
    and store status_label + progress_bar in self.thread_labels / self.thread_bars.

    auto_render.py does NOT use this helper — its thread row has different
    sizes, different text format, and no status_label CSS class.
    """
    row = QHBoxLayout()
    row.setSpacing(8)
    label = QLabel(f'IDLE #{index + 1}', parent)
    label.setFixedWidth(70)
    label.setProperty('class', 'status_label')
    status = QLabel('Waiting', parent)
    status.setFixedWidth(250)
    status.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    status.setProperty('class', 'status_label')
    progress = QProgressBar(parent)
    progress.setFixedHeight(25)
    row.addWidget(label)
    row.addWidget(status)
    row.addWidget(progress, stretch=1)
    return row, label, status, progress
