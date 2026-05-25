"""Version-state read/write for the app window-title version label.

Relocated from ``updater.py`` (``DriveUpdater._load_current_version`` /
``_save_current_version``) when the in-app update channel was removed — see
ADR-0017 (B-051). The semantics are preserved byte-for-byte: the same
``assets/Version AutoRender.json`` file, the same
``data["software"][app_name]["version"]`` shape, the same ``indent=4`` on
write, and the same broad-except-and-print error handling (a read failure or
missing file yields ``None``; the caller falls back to its default version).

Network-free by construction: this module only touches the local JSON file.
"""

from __future__ import annotations

import json
import os

# The version file lives under the repo/install ``assets/`` dir. From this
# module (``core/version_state.py``) the repo root is the parent's parent —
# mirrors the source-mode resolution used elsewhere in ``core/`` (e.g.
# ``core/url_downloader.py``'s bundled-ffmpeg lookup).
VERSION_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets",
    "Version AutoRender.json",
)


def load_current_version(app_name: str) -> str | None:
    """Read ``app_name``'s version string from the version file, or ``None``."""
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, "r") as f:
                data = json.load(f)
                return data.get("software", {}).get(app_name, {}).get("version")
    except Exception as e:
        print(f"Error reading version file: {str(e)}")
    return None


def save_current_version(version: str, app_name: str) -> None:
    """Persist ``version`` for ``app_name`` into the version file."""
    try:
        data = {}
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, "r") as f:
                data = json.load(f)
        if "software" not in data:
            data["software"] = {}
        if app_name not in data["software"]:
            data["software"][app_name] = {}
        data["software"][app_name]["version"] = version
        with open(VERSION_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving version file: {str(e)}")
