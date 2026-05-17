# updater.py — passive updater (v3.9+).
# Opens GitHub releases page on user request. Local version tracking preserved.
# Auto-detection + signed manifest auto-install deferred to v3.10+.

from __future__ import annotations

import json
import os
from typing import Optional

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

RELEASES_URL = "https://github.com/adamruk/1vmosuite-test/releases"


class DriveUpdater:
    """Passive updater.

    Class name preserved for backward compat with auto_render / cutter /
    merge / mixer which import `DriveUpdater` directly.

    v3.8 behaviour: Google Sheet → Dropbox → auto-install.
    v3.9 behaviour: open GitHub releases page in the user's browser.
    v3.10+: signed-manifest auto-update planned (see BACKLOG.md).
    """

    def __init__(self) -> None:
        self.version_file = os.path.join(
            os.path.dirname(__file__), "assets", "Version AutoRender.json"
        )

    def _load_current_version(self, app_name: str) -> Optional[str]:
        """Read the stored installed version for app_name. Returns None if unset."""
        try:
            if os.path.exists(self.version_file):
                with open(self.version_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("software", {}).get(app_name, {}).get("version")
        except (json.JSONDecodeError, OSError):
            pass
        return None

    def _save_current_version(self, version: str, app_name: str) -> None:
        """Persist the installed version for app_name."""
        try:
            data: dict = {}
            if os.path.exists(self.version_file):
                with open(self.version_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data.setdefault("software", {}).setdefault(app_name, {})["version"] = version
            os.makedirs(os.path.dirname(self.version_file), exist_ok=True)
            with open(self.version_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except (json.JSONDecodeError, OSError):
            pass

    def check_and_update(self, app_name: str) -> None:
        """Open the GitHub releases page in the user's browser.

        Replaces the v3.8 auto-update flow. The `app_name` parameter is
        kept for caller compatibility but unused.
        """
        opened = QDesktopServices.openUrl(QUrl(RELEASES_URL))
        if not opened:
            QMessageBox.information(
                None,
                "Check for Updates",
                f"Could not open the browser automatically.\n\n"
                f"Open this URL manually:\n{RELEASES_URL}",
            )


# Optional forward-compat alias if any future code uses `Updater`.
Updater = DriveUpdater
