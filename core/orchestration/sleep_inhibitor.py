"""Phase 3.4 — cross-platform sleep inhibitor.

Context manager that prevents the OS from sleeping during a
long batch. Per-platform best-effort:

  Windows: SetThreadExecutionState(ES_SYSTEM_REQUIRED |
           ES_CONTINUOUS)
  macOS:   spawn `caffeinate -i -w <pid>` child; terminate on exit
  Linux:   spawn `systemd-inhibit --what=idle --who=1vmo
           --why=render sleep infinity`; terminate on exit

All paths wrapped in try/except so a missing platform tool
silently degrades to "no sleep prevention" without breaking the
render. Default is OFF — auto_render calls `acquire()` only when
the user has opted in via Settings.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from typing import Optional

logger = logging.getLogger("core.orchestration.sleep_inhibitor")


class SleepInhibitor:
    """Best-effort cross-platform keep-awake helper.

    Usage:
        si = SleepInhibitor(reason="1vmo render")
        si.acquire()
        try:
            ... long batch ...
        finally:
            si.release()
    """

    def __init__(self, reason: str = "1vmo render"):
        self._reason = reason
        self._acquired = False
        self._helper_proc: Optional[subprocess.Popen] = None
        self._prev_exec_state: Optional[int] = None
        self._system = platform.system()

    @property
    def is_active(self) -> bool:
        return self._acquired

    def acquire(self) -> bool:
        """Engage sleep prevention. Returns True on success, False otherwise."""
        if self._acquired:
            return True
        try:
            if self._system == "Windows":
                self._acquired = self._acquire_windows()
            elif self._system == "Darwin":
                self._acquired = self._acquire_macos()
            elif self._system == "Linux":
                self._acquired = self._acquire_linux()
            else:
                logger.info(
                    "sleep_inhibitor: no-op on unsupported platform %s",
                    self._system,
                )
        except Exception as exc:
            logger.warning("sleep_inhibitor: acquire failed: %s", exc)
            self._acquired = False
        return self._acquired

    def release(self) -> None:
        """Restore default sleep behaviour. Idempotent."""
        if not self._acquired:
            return
        try:
            if self._system == "Windows":
                self._release_windows()
            else:
                self._release_helper()
        except Exception as exc:
            logger.warning("sleep_inhibitor: release failed: %s", exc)
        finally:
            self._acquired = False

    def __enter__(self) -> "SleepInhibitor":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    # ----- per-platform paths -----

    def _acquire_windows(self) -> bool:
        import ctypes

        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        prev = kernel32.SetThreadExecutionState(flags)
        if prev == 0:
            return False
        self._prev_exec_state = prev
        return True

    def _release_windows(self) -> None:
        import ctypes

        ES_CONTINUOUS = 0x80000000
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        # Clearing flags returns to default.
        kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        self._prev_exec_state = None

    def _acquire_macos(self) -> bool:
        pid = os.getpid()
        try:
            self._helper_proc = subprocess.Popen(
                ["caffeinate", "-i", "-w", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except FileNotFoundError:
            logger.info("sleep_inhibitor: caffeinate not found on macOS")
            return False

    def _acquire_linux(self) -> bool:
        try:
            self._helper_proc = subprocess.Popen(
                [
                    "systemd-inhibit",
                    "--what=idle",
                    "--who=1vmo",
                    f"--why={self._reason}",
                    "sleep",
                    "infinity",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except FileNotFoundError:
            logger.info("sleep_inhibitor: systemd-inhibit not found on Linux")
            return False

    def _release_helper(self) -> None:
        proc = self._helper_proc
        self._helper_proc = None
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except (subprocess.TimeoutExpired, ProcessLookupError, OSError):
            try:
                proc.kill()
            except (OSError, ProcessLookupError):
                pass


__all__ = ["SleepInhibitor"]
