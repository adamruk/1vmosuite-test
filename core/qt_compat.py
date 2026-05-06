"""Qt compatibility shim: PyQt5 → PySide6.

PySide6 uses `Signal`/`Slot` instead of PyQt5's `pyqtSignal`/`pyqtSlot`.
This thin shim provides the PyQt5 names so the app files don't need
per-framework code.
"""

from PySide6.QtCore import Signal as pyqtSignal
from PySide6.QtCore import Slot as pyqtSlot

__all__ = ["pyqtSignal", "pyqtSlot"]
