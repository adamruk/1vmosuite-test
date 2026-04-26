"""User data directory resolver (sub-phase 2c-c-2).

Default: platform-standard user data dir via platformdirs.
  Windows: %LOCALAPPDATA%\\1vmo-suite
  macOS:   ~/Library/Application Support/1vmo-suite
  Linux:   ~/.local/share/1vmo-suite

Opt-in portable mode: place a `portable.txt` sentinel file alongside
the install directory and the resolver returns ``<install_dir>/UserData``
instead. Portable mode is guarded against Windows-protected directories
(Program Files, Windows, ProgramData) which would silently redirect
writes via VirtualStore.

Pure resolution: this module does NOT create directories or write any
files. Callers (sub-phase 2c-c-3) are responsible for mkdir on first write.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from platformdirs import user_data_path

APP_NAME = "1vmo-suite"
PORTABLE_SENTINEL = "portable.txt"


class PortableLocationError(Exception):
    """Raised when portable mode is requested but install dir is unsafe.

    Triggered when ``portable.txt`` exists alongside the install but the
    install lives under a Windows-protected location (Program Files,
    Windows, ProgramData) where writes would be silently redirected to
    ``%LOCALAPPDATA%\\VirtualStore`` via UAC redirection.
    """


def _portable_mode_requested(install_dir: Path) -> bool:
    """Return True if a portable.txt sentinel exists in install_dir."""
    return (install_dir / PORTABLE_SENTINEL).is_file()


def _is_protected_dir(install_dir: Path) -> bool:
    """Return True if install_dir is under a Windows-protected location.

    Path-prefix match (case-insensitive) against environment-variable-
    resolved %ProgramFiles%, %ProgramFiles(x86)%, %ProgramW6432%,
    %WINDIR%, %ProgramData%. Returns False on non-Windows platforms.
    """
    if sys.platform != "win32":
        return False

    protected_envs = (
        "ProgramFiles",
        "ProgramFiles(x86)",
        "ProgramW6432",
        "WINDIR",
        "ProgramData",
    )
    try:
        install_resolved = str(install_dir.resolve()).lower()
    except (OSError, RuntimeError):
        return False

    for env_name in protected_envs:
        protected = os.environ.get(env_name)
        if not protected:
            continue
        try:
            protected_resolved = str(Path(protected).resolve()).lower()
        except (OSError, RuntimeError):
            continue
        if install_resolved.startswith(protected_resolved):
            return True
    return False


def resolve_user_data_dir(install_dir: Path) -> Path:
    """Resolve the user data directory for 1vmo Suite.

    Returns the platform-standard user data path by default. If a
    ``portable.txt`` sentinel file exists in ``install_dir``, returns
    ``install_dir / "UserData"`` instead — unless the install is under
    a Windows-protected directory, in which case PortableLocationError
    is raised.

    No directory creation; pure path resolution. Callers create the
    directory on first write (sub-phase 2c-c-3).

    Args:
        install_dir: The install directory of the running app
            (typically derived from ``Path(__file__).parent`` or
            ``sys._MEIPASS`` for frozen builds).

    Returns:
        A Path object pointing to the resolved user data directory.

    Raises:
        PortableLocationError: portable mode requested but install dir
            is under a Windows-protected location.
    """
    if _portable_mode_requested(install_dir):
        if _is_protected_dir(install_dir):
            raise PortableLocationError(
                f"Portable mode requested ({PORTABLE_SENTINEL} present) but "
                f"install directory '{install_dir}' is under a Windows-protected "
                f"location. Writes would be silently redirected to "
                f"%LOCALAPPDATA%\\VirtualStore by UAC. "
                f"Either move the install (e.g. to C:\\Tools\\1vmo or "
                f"%USERPROFILE%\\1vmo) or remove {PORTABLE_SENTINEL} to use "
                f"platform-standard user data storage."
            )
        return install_dir / "UserData"

    return user_data_path(APP_NAME, appauthor=False)
