"""Shared QFileDialog wrappers for 1vmo Suite apps."""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QFileDialog, QWidget

# Named filter constants — keep in sync with dialog titles users see.
VIDEO_FILTER = 'Video Files (*.mp4 *.avi *.mkv)'
MEDIA_FILTER = (
    'Media Files (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm '
    '*.jpg *.jpeg *.png *.bmp *.gif *.tiff)'
)
AUDIO_FILTER = 'Audio Files (*.mp3 *.wav *.m4a *.aac *.ogg *.flac *.wma)'


def pick_files(
    parent: Optional[QWidget],
    title: str,
    initial_dir: str,
    filter_str: str,
) -> list[str]:
    """Show a multi-select file dialog. Returns [] on cancel.

    The caller is responsible for persisting `initial_dir` source state
    (e.g. updating config with os.path.dirname(result[0]) on success).
    This function is pure UI — no config side effects.
    """
    paths, _ = QFileDialog.getOpenFileNames(parent, title, initial_dir, filter_str)
    return list(paths)


def pick_directory(
    parent: Optional[QWidget],
    title: str,
    initial_dir: str,
) -> str:
    """Show a directory picker. Returns '' on cancel."""
    return QFileDialog.getExistingDirectory(parent, title, initial_dir)
