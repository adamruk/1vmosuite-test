# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'Code AutoRender.py'
# Bytecode version: 3.11a7e (3495)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import (
    QObject,
    QSemaphore,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import gpu_detect
from core import config as core_config
from core import ffmpeg_runner as core_ffmpeg_runner
from core import file_picker as core_file_picker
from core import naming_utils, preset_translator
from core import preset_loader as core_preset_loader
from core import url_downloader as core_url_downloader
from core import version_state as core_version_state
from core import widgets as core_widgets
from core.flow_layout import FlowLayout
from core.preset_loader import (
    derive_slug,
    load_user_presets_json,
    save_user_presets_json,
)
from core.queue_models import (
    UNFINISHED_STATUSES,
    QueueBatch,
    QueueTask,
    TaskStatus,
)
from core.queue_store import QueueStore
from core.user_data import (
    migrate_legacy_configs,
    resolve_or_die,
    resolve_user_data_dir,
)
from help_dialog import HelpDialog
from settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)

SEQUENTIAL_SLOT_COUNT = 8


def _setup_file_logging(install_dir, log_filename):
    """Attach an absolute per-user FileHandler to the root logger.

    Runs at import time, before any QApplication exists, so it must never exit
    or raise. Uses the NON-exiting ``resolve_user_data_dir`` (never
    ``resolve_or_die``, which calls ``sys.exit``) and falls back to
    ``install_dir`` on any error. Idempotent: re-calling will not add a second
    handler for the same file. Returns the resolved log path, or None if even
    the fallback could not be configured.
    """
    try:
        try:
            log_dir = resolve_user_data_dir(install_dir)
        except Exception:
            log_dir = install_dir
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            log_dir = install_dir
        log_path = os.path.abspath(str(log_dir / log_filename))
        root = logging.getLogger()
        for handler in root.handlers:
            if (
                isinstance(handler, logging.FileHandler)
                and handler.baseFilename == log_path
            ):
                return log_path
        # utf-8 so non-ASCII filenames in log messages cannot raise a cp1252
        # UnicodeEncodeError on Windows (FileHandler defaults to locale encoding).
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        root.addHandler(file_handler)
        root.setLevel(logging.INFO)
        return log_path
    except Exception:
        return None


# auto_render has no module-level SCRIPT_DIR (it lives on self.SCRIPT_DIR in
# __init__); compute the install dir the same way here so logging is configured
# at import time without depending on __init__ ordering (B-024).
_setup_file_logging(
    Path(os.path.dirname(os.path.abspath(__file__))), "video_renderer.log"
)


def resource_path(relative_path):
    """Lấy đường dẫn tuyệt đối cho tài nguyên, hoạt động cả khi chạy từ source và từ file exe"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# Phase 2d follow-up fix (Item 4): printf-style %0Nd token detector used
# to decide whether a path is an ffmpeg image-sequence template. Matches
# %d, %03d, %04d, etc. — the only widths ffmpeg supports. Anchored to a
# single token; the loop below splits the basename around all occurrences.
_SEQ_TOKEN_RE = re.compile(r"%0?\d*d")


def _cleanup_image_sequence(path: str) -> int:
    """Remove every concrete file matching an ffmpeg %0Nd sequence pattern.

    Phase 2d follow-up fix (Item 4) for the image-sequence intermediate
    leakage that was silently swallowed by `except OSError: pass` in
    process()'s inter-step cleanup. The previous code called os.remove
    on a path like `…_%03d.jpg`, which is a printf TEMPLATE — no file
    with that literal name ever exists on disk — so os.remove always
    raised FileNotFoundError, the except clause swallowed it, and the
    N actual frame files (`…_001.jpg`, `…_002.jpg`, …) were left
    behind. Repeated renders accumulated these orphans indefinitely.

    Safety rules (defense in depth — image cleanup MUST NOT remove
    user-visible deliverables or wander outside the worker's output
    directory):

      1. No-op if the basename contains no %0Nd token. Caller is
         responsible for using os.remove on plain paths.
      2. No-op if the parent directory doesn't exist or isn't a
         directory.
      3. Build a strict regex from the literal segments around each
         %0Nd token (re.escape on every fragment, `\\d+` between
         tokens). Globbing `*` would be looser and could match files
         the worker did not create.
      4. Walk the directory via os.listdir — non-recursive — and
         match each entry against the strict regex; reject anything
         that's not a plain file (skips directories AND symlinks
         pointing outside the worker's output tree).
      5. Per-file errors are caught and counted but do not abort the
         loop, so a permission-denied frame does not strand the rest
         of the sequence.

    Returns the number of files actually removed (useful for logs and
    test assertions). Path traversal is impossible because we
    os.path.dirname() the supplied path and refuse to follow into
    subdirectories.
    """
    folder = os.path.dirname(path)
    basename = os.path.basename(path)
    if not folder or not os.path.isdir(folder):
        return 0
    if not _SEQ_TOKEN_RE.search(basename):
        return 0
    parts = _SEQ_TOKEN_RE.split(basename)
    # Strict regex: literal segments re.escape'd, %0Nd → \d+.
    pattern = re.compile(r"^" + r"\d+".join(re.escape(p) for p in parts) + r"$")
    removed = 0
    try:
        entries = os.listdir(folder)
    except OSError:
        return 0
    for entry in entries:
        if not pattern.match(entry):
            continue
        full = os.path.join(folder, entry)
        # os.path.isfile follows symlinks — we want that here because a
        # genuine sequence frame written by ffmpeg is a regular file,
        # and ffmpeg never produces symlinks. islink() defensively
        # rejects anything that resolved to a non-file (e.g. a symlink
        # to a directory) so we never delete unexpected types.
        if os.path.islink(full) or not os.path.isfile(full):
            continue
        try:
            os.remove(full)
            removed += 1
        except OSError:
            # Permission denied / file already gone / cross-thread race
            # against another worker — log and continue.
            logger.error(f"_cleanup_image_sequence: could not remove {full!r}")
    return removed


def _path_is_sequence(path: str) -> bool:
    """True iff `path` contains an ffmpeg %0Nd token in its basename."""
    return bool(_SEQ_TOKEN_RE.search(os.path.basename(path)))


def _cleanup_zero_byte_placeholder(path: str) -> bool:
    """Remove `path` iff it exists, is a regular file, and is exactly 0 bytes.

    Phase 2d follow-up fix (Item 11) for avoid_collision orphan
    placeholders. `core.naming_utils.avoid_collision` atomically
    creates a 0-byte file at the chosen output path BEFORE ffmpeg
    runs (using `open(p, 'x').close()`), so two concurrent workers
    cannot pick the same target. On a successful encode, ffmpeg's
    `-y` overwrites the placeholder with multi-KB of real content.
    On cancel / rc!=0 / Python-level crash, ffmpeg may never have
    written, leaving an unambiguously orphan 0-byte file behind —
    Item 11's "temp-file leakage" instance.

    Safety rules — this helper is invoked from cancel/error paths
    where one wrong rm could destroy a legitimate render:

      1. Size must be EXACTLY 0 bytes. A partial mp4 / mkv is many
         KB even after a single muxed packet. We refuse to touch
         any file with real content so the user can still inspect
         partial outputs (matches the existing
         "leave partial single-file outputs on disk for diagnostics"
         intent documented in core/naming_utils.py).
      2. Symlinks are rejected via os.path.islink before any size
         check, so we never delete through a link to elsewhere.
      3. Non-regular targets (directories, FIFOs, devices) are
         rejected by os.path.isfile.
      4. Any OSError during the stat/remove (e.g. another worker
         removed the file concurrently, the filesystem went read-
         only, the file is locked on Windows) returns False; the
         caller does not need to handle it.

    Returns True iff a file was actually removed, False otherwise.
    No-op for non-existent paths and for the printf-template paths
    used by image sequences (which never have a literal on disk).
    """
    try:
        if os.path.islink(path):
            return False
        if not os.path.isfile(path):
            return False
        if os.path.getsize(path) != 0:
            return False
        os.remove(path)
        return True
    except OSError:
        return False


def _acquire_gpu_slot(semaphore, should_cancel, poll_ms: int = 100) -> bool:
    """Acquire one NVENC slot from ``semaphore``, honoring cancellation (B-032).

    A bare ``QSemaphore.acquire()`` blocks indefinitely under contention and
    cannot observe a cancel request, so a queued render could not be cancelled
    while waiting for a free NVENC session. This polls ``should_cancel()``
    between bounded ``tryAcquire`` attempts instead.

    Returns True if a slot was acquired (the caller owns it and must release
    it), or False if ``should_cancel()`` became true first (nothing acquired,
    nothing to release).
    """
    while not should_cancel():
        if semaphore.tryAcquire(1, poll_ms):
            return True
    return False


def _split_group_name(full_name: str) -> tuple[str, str]:
    """Split an EncoderDialog "Group|Name" field into ``(group, name)``.

    B-020: ``.strip()`` each half so that input like ``"Test | My Preset"``
    yields ``("Test", "My Preset")`` rather than ``("Test ", " My Preset")``.
    Group lookups elsewhere use exact string match and silently miss on
    whitespace adjacent to the pipe. With no pipe, group is ``""`` and the
    full name (already stripped by ``EncoderDialog.accept``) is returned
    unchanged. Used by both the Add/Clone helper and the Edit handler.
    """
    parts = full_name.split("|", 1)
    if len(parts) > 1:
        return parts[0].strip(), parts[1].strip()
    return "", full_name


def _allocate_user_preset_id(name: str, existing_user_ids) -> str:
    """Derive a collision-free ``user:<slug>`` id for a new user preset.

    Mirrors the 2c-c-4 disambiguation used by Add (B-018 shares it with
    Clone): the ADR-0006 slug of ``name``, prefixed ``user:`` (the flat
    user namespace — never group-prefixed), with a ``-N`` suffix (N starts
    at 2) appended only when the bare id already exists in
    ``existing_user_ids``. ``existing_user_ids`` is any container
    supporting ``in`` (typically a set of the current ``user:`` ids).
    """
    base_slug = derive_slug(name) or "preset"
    base_id = f"user:{base_slug}"
    if base_id not in existing_user_ids:
        return base_id
    n = 2
    while f"{base_id}-{n}" in existing_user_ids:
        n += 1
    return f"{base_id}-{n}"


class RenderWorker(QObject):
    progress_updated = Signal(int, int)
    status_updated = Signal(int, str)
    output_updated = Signal(str)
    render_completed = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        video_path: str,
        encoder_names: List[str],
        thread_index: int,
        ffmpeg_path: str,
        output_dir: str,
        encoder_params_list: List[List[str]],
        output_collision: str = core_config.APP_DEFAULTS.output_collision,
        gpu_error_action: str = core_config.APP_DEFAULTS.gpu_error_action,
        gpu_enabled: bool = core_config.APP_DEFAULTS.gpu_enabled,
        gpu_codec: str = core_config.APP_DEFAULTS.gpu_codec,
        gpu_preset: str = core_config.APP_DEFAULTS.gpu_preset,
        gpu_max_quality_mode: bool = False,
        gpu_semaphore=None,
    ):
        super().__init__()
        self.video_path = video_path
        self.encoder_names = encoder_names
        self.thread_index = thread_index
        self.ffmpeg_path = ffmpeg_path
        self.output_dir = output_dir
        self.encoder_params_list = encoder_params_list
        self.output_collision = output_collision
        self.gpu_error_action = gpu_error_action
        self.gpu_enabled = gpu_enabled
        self.gpu_codec = gpu_codec
        self.gpu_preset = gpu_preset
        self.gpu_max_quality_mode = gpu_max_quality_mode
        self.gpu_semaphore = gpu_semaphore
        self.is_cancelled = False

    def _has_vcodec(self, params):
        return any(p in ("-c:v", "-vcodec") for p in params)

    def _has_acodec(self, params):
        return any(p in ("-c:a", "-acodec") for p in params)

    def _has_threads(self, params):
        return any(p == "-threads" for p in params)

    def process(self):
        current_input = self.video_path
        final_output = None
        # Phase 2d follow-up fix (Item 4): track the in-flight step's
        # output path + image-encoder flag so the outer exception
        # handler can still clean up a partial sequence if the loop
        # crashes mid-step. Reset on every successful step transition.
        current_step_output: Optional[str] = None
        current_step_is_image = False
        try:
            for i, (encoder_name, encoder_params) in enumerate(
                zip(self.encoder_names, self.encoder_params_list)
            ):
                if not encoder_name:
                    continue
                progress_info = f"Step {i + 1}/{len(self.encoder_names)}"
                self.status_updated.emit(
                    self.thread_index,
                    f"Processing: {os.path.basename(current_input)} with {encoder_name} ({progress_info})",
                )
                self.progress_updated.emit(self.thread_index, 0)
                timestamp = naming_utils.timestamp()
                video_name = os.path.splitext(os.path.basename(self.video_path))[0]
                encoder_parts = encoder_name.split("|", 1)
                encoder_name = (
                    encoder_parts[1] if len(encoder_parts) > 1 else encoder_name
                )
                # Filename budget pre-allocation (PORT_NOTES filename pipeline contract):
                # compute tail_max for this iteration, then split remaining budget enc/vid 1:2.
                if i == len(self.encoder_names) - 1:
                    tail_max = 10  # "_final.mp4" or "_%03d.jpg"
                else:
                    tail_max = 14 + len(str(i + 1))  # "_step{N}_%03d.jpg" worst-case
                fixed_overhead = (
                    len(timestamp) + 2 + tail_max
                )  # 2 = the two underscores in "{ts}_{enc}_{vid}{tail}"
                avail = naming_utils.MAX_FILENAME - fixed_overhead
                enc_budget = max(3, avail // 3)
                vid_budget = max(3, avail - enc_budget)
                safe_encoder_name = naming_utils.safe_part(encoder_name, enc_budget)
                safe_video_name = naming_utils.safe_part(video_name, vid_budget)
                is_image_encoder = any(
                    (param in ["-f", "image2"] for param in encoder_params)
                )
                if i == len(self.encoder_names) - 1:
                    if is_image_encoder:
                        output_filename = f"{timestamp}_{safe_encoder_name}_{safe_video_name}_%03d.jpg"
                    else:
                        output_filename = f"{timestamp}_{safe_encoder_name}_{safe_video_name}_final.mp4"
                else:
                    if is_image_encoder:
                        output_filename = f"{timestamp}_{safe_encoder_name}_{safe_video_name}_step{i + 1}_%03d.jpg"
                    else:
                        output_filename = f"{timestamp}_{safe_encoder_name}_{safe_video_name}_step{i + 1}.mp4"
                output_file = os.path.join(self.output_dir, output_filename)
                output_file = naming_utils.clip_to_limit(output_file)
                # Phase 2d follow-up fix (Item 4): record the in-flight
                # step's output + image flag so the outer exception
                # handler can clean an incomplete sequence even if a
                # later line throws before reaching the per-rc cleanup.
                current_step_output = output_file
                current_step_is_image = is_image_encoder
                # Bug 4 fix: honor output_collision setting (3-way branch per PORT_NOTES).
                if self.output_collision == "overwrite":
                    pass  # ffmpeg -y handles it
                elif self.output_collision == "skip":
                    if os.path.exists(output_file):
                        self.error_occurred.emit(
                            f"Skipped (exists): {os.path.basename(output_file)}"
                        )
                        return
                else:  # "rename" default
                    if not is_image_encoder:
                        output_file = naming_utils.avoid_collision(output_file)
                # Phase 2d production-hardening fix (Issue 1): for
                # single-file outputs, render into a sidecar
                # `<output>.partial` path and only os.replace to the
                # canonical `output_file` after ffmpeg returns rc == 0.
                # Cancel / error / Python exception paths delete the
                # partial. This eliminates the failure mode where a
                # cancelled or crashed render leaves a `<…>_final.mp4`
                # on disk whose filename falsely implies success.
                #
                # Image sequences are unchanged — they produce N
                # numbered frame files which are already cleaned up
                # explicitly by `_cleanup_image_sequence` on every
                # non-success exit; renaming hundreds of frames
                # atomically is impractical and unnecessary.
                #
                # The 0-byte `output_file` placeholder created by
                # avoid_collision is preserved as the reservation
                # marker while ffmpeg writes to the `.partial` path;
                # `os.replace(temp, output_file)` on success atomically
                # swaps real content in over the placeholder.
                if is_image_encoder:
                    temp_output_file: Optional[str] = None
                    ffmpeg_target = output_file
                else:
                    # v3.9 F-001 ship-blocker fix: use naming_utils.partial_path
                    # so the temp file keeps its real extension
                    # (out.partial.mp4, not out.mp4.partial). ffmpeg infers
                    # the muxer from the extension; ``.partial`` has no
                    # registered muxer and breaks 101/108 presets on Windows
                    # with "Error opening output file ... .mp4.partial:
                    # Invalid argument". The on-success os.replace + cleanup
                    # contracts are unchanged.
                    temp_output_file = naming_utils.partial_path(output_file)
                    ffmpeg_target = temp_output_file
                    # Clean any stale `.partial` from a prior aborted
                    # attempt at this exact target — ffmpeg `-y` would
                    # overwrite it anyway, but removing it up front
                    # keeps the on-disk story tidy and prevents any
                    # follow-on cleanup from misinterpreting it.
                    if os.path.exists(temp_output_file):
                        try:
                            os.remove(temp_output_file)
                        except OSError:
                            pass
                # GPU pipeline (ADR-0007 D2/D3/D7): translate encoder_params for NVENC.
                # Phase 1 fallback contract: save ORIGINAL params before translator mutates them.
                encoder_params_original = list(encoder_params)
                if self.gpu_enabled and not is_image_encoder:
                    encoder_params = preset_translator.translate_to_nvenc(
                        encoder_params,
                        codec=self.gpu_codec,
                        preset=self.gpu_preset,
                        max_quality_mode=self.gpu_max_quality_mode,
                    )
                command = [
                    str(self.ffmpeg_path),
                    "-i",
                    str(Path(current_input)),
                ] + encoder_params
                if not is_image_encoder:
                    if not self._has_vcodec(encoder_params):
                        if self.gpu_enabled:
                            command.extend(["-c:v", self.gpu_codec])
                        else:
                            command.extend(["-c:v", "libx264"])
                    if not self._has_acodec(encoder_params):
                        command.extend(["-c:a", "aac"])
                    # Phase 4: restore the CPU `-threads 0` hint dropped during
                    # the phase3 rebuild. On the CPU (libx264) path, let ffmpeg
                    # auto-pick the worker thread count unless the preset already
                    # pins `-threads`. The NVENC/gpu path is left untouched —
                    # NVENC parallelism is governed by async_depth + the
                    # gpu_semaphore, not libavcodec threads.
                    if not self.gpu_enabled and not self._has_threads(encoder_params):
                        command.extend(["-threads", "0"])
                # Phase 2d production-hardening fix (Issue 1): ffmpeg
                # writes to `ffmpeg_target` (== `<output>.partial` for
                # single-file, == `output_file` for image sequences).
                command.extend(["-y", str(Path(ffmpeg_target))])
                self.output_updated.emit(
                    f"\n[Thread {self.thread_index + 1}] {progress_info}: Processing {os.path.basename(current_input)} with {encoder_name}\n"
                )
                self.output_updated.emit(
                    f"Command: {' '.join((str(x) for x in command))}\n\n"
                )
                # QSemaphore gate per ADR-0007 D6: limit concurrent NVENC sessions.
                _gpu_path_taken = self.gpu_enabled and not is_image_encoder
                _gpu_slot_held = False
                if _gpu_path_taken and self.gpu_semaphore is not None:
                    # B-032: bounded, cancellable acquire. A bare acquire()
                    # blocks forever under contention and ignores a cancel
                    # request, so a queued render could not be cancelled while
                    # waiting for a free NVENC slot. Poll is_cancelled between
                    # bounded tryAcquire attempts instead.
                    _gpu_slot_held = _acquire_gpu_slot(
                        self.gpu_semaphore, lambda: self.is_cancelled
                    )
                try:
                    if (
                        _gpu_path_taken
                        and self.gpu_semaphore is not None
                        and not _gpu_slot_held
                    ):
                        # B-032: cancelled while waiting for a free NVENC slot —
                        # ffmpeg never ran and no slot is held. rc=0 routes past
                        # the GPU-fail-retry branch straight to the shared
                        # `if self.is_cancelled` handler below, which emits
                        # "Cancelled" and cleans up the placeholder/partial.
                        rc = 0
                    else:
                        rc = core_ffmpeg_runner.run_ffmpeg(
                            command,
                            dialect="legacy_stderr",
                            on_progress=lambda pct: self.progress_updated.emit(
                                self.thread_index, pct
                            ),
                            on_output_line=lambda line: self.output_updated.emit(
                                line + "\n"
                            ),
                            should_cancel=lambda: self.is_cancelled,
                        )
                finally:
                    if _gpu_slot_held:
                        self.gpu_semaphore.release()
                # CPU fallback per ADR-0007 D5: GPU encode failed, honor gpu_error_action.
                # Bug 2 closure: skip_file branch emits error_occurred so existing handler advances batch.
                if rc != 0 and _gpu_path_taken:
                    if self.gpu_error_action == "skip_file":
                        self.output_updated.emit(
                            "\nGPU encode failed, skipping per gpu_error_action=skip_file.\n"
                        )
                        self.error_occurred.emit(
                            f"Skipped (GPU failed): {os.path.basename(output_file)}"
                        )
                        # Phase 2d follow-up fix (Item 11) + production-
                        # hardening (Issue 1): skip_file returns before
                        # any other cleanup path runs. Sweep the orphan
                        # placeholder + the `.partial` sidecar + partial
                        # image-sequence frames so we don't leak through
                        # the GPU-fail-skip exit.
                        if is_image_encoder:
                            _cleanup_image_sequence(output_file)
                        else:
                            _cleanup_zero_byte_placeholder(output_file)
                            if temp_output_file is not None:
                                try:
                                    if os.path.exists(temp_output_file):
                                        os.remove(temp_output_file)
                                except OSError:
                                    pass
                        return
                    # Default retry_cpu: rebuild command with original (untranslated) params.
                    self.output_updated.emit("\nGPU encode failed, retrying on CPU.\n")
                    cpu_command = [
                        str(self.ffmpeg_path),
                        "-i",
                        str(Path(current_input)),
                    ] + encoder_params_original
                    if not self._has_vcodec(encoder_params_original):
                        cpu_command.extend(["-c:v", "libx264"])
                    if not self._has_acodec(encoder_params_original):
                        cpu_command.extend(["-c:a", "aac"])
                    # Phase 4: this is the GPU->CPU fallback — an inherently CPU
                    # (libx264) encode — so apply the same `-threads 0` hint when
                    # the preset hasn't pinned `-threads`. The main-path guard's
                    # `not self.gpu_enabled` clause is intentionally omitted here:
                    # this branch only runs after a GPU attempt failed (i.e. when
                    # gpu_enabled is True), so keeping that clause would make the
                    # hint dead code.
                    if not self._has_threads(encoder_params_original):
                        cpu_command.extend(["-threads", "0"])
                    # Phase 2d production-hardening fix (Issue 1):
                    # CPU retry writes to the same `.partial` sidecar
                    # as the failed GPU attempt. ffmpeg `-y` overwrites
                    # whatever the GPU left behind. Atomic rename to
                    # `output_file` still happens only on rc==0 below.
                    cpu_command.extend(["-y", str(Path(ffmpeg_target))])
                    rc = core_ffmpeg_runner.run_ffmpeg(
                        cpu_command,
                        dialect="legacy_stderr",
                        on_progress=lambda pct: self.progress_updated.emit(
                            self.thread_index, pct
                        ),
                        on_output_line=lambda line: self.output_updated.emit(
                            line + "\n"
                        ),
                        should_cancel=lambda: self.is_cancelled,
                    )
                if self.is_cancelled:
                    self.status_updated.emit(self.thread_index, "Cancelled")
                    self.progress_updated.emit(self.thread_index, 0)
                    # Phase 2d follow-up fix (Items 4 + 11) + production-
                    # hardening (Issue 1): cancel mid-encode leaves
                    # incomplete output. For image sequences, remove the
                    # partial frames. For single-file outputs, remove
                    # both the 0-byte avoid_collision placeholder AND
                    # the `.partial` sidecar that ffmpeg was writing to.
                    # No `<…>_final.mp4` is ever left on disk because
                    # ffmpeg was never writing to that name.
                    if is_image_encoder:
                        _cleanup_image_sequence(output_file)
                    else:
                        _cleanup_zero_byte_placeholder(output_file)
                        if temp_output_file is not None:
                            try:
                                if os.path.exists(temp_output_file):
                                    os.remove(temp_output_file)
                            except OSError:
                                pass
                    return
                if rc == 0:
                    # Phase 2d production-hardening fix (Issue 1):
                    # atomically promote the `.partial` sidecar to the
                    # canonical `output_file` on success. This swap is
                    # what gives the user a `<…>_final.mp4` that is
                    # GUARANTEED to be a complete render. Image
                    # sequences skip this step (sequence frames are
                    # already at their final paths).
                    #
                    # os.replace is atomic within a single filesystem;
                    # the renderer writes both paths into the same
                    # output directory so this invariant holds. If the
                    # replace somehow fails (filesystem went read-only,
                    # antivirus held the handle), we surface it as a
                    # render error rather than silently treating the
                    # step as successful — the `.partial` is left for
                    # the user to inspect.
                    if temp_output_file is not None and not is_image_encoder:
                        try:
                            _swap_last_exc = None
                            for _swap_i, _swap_ms in enumerate((50, 100, 200, 400, 0)):
                                try:
                                    os.replace(temp_output_file, output_file)
                                    _swap_last_exc = None
                                    break
                                except OSError as _swap_e:
                                    _swap_last_exc = _swap_e
                                    if _swap_ms:
                                        time.sleep(_swap_ms / 1000.0)
                            if _swap_last_exc is not None:
                                raise _swap_last_exc
                        except OSError as exc:
                            error_msg = (
                                f"Failed to finalize output "
                                f"{os.path.basename(output_file)}: {exc}"
                            )
                            self.error_occurred.emit(error_msg)
                            self.status_updated.emit(self.thread_index, "Error")
                            self.progress_updated.emit(self.thread_index, 0)
                            return
                    self.status_updated.emit(
                        self.thread_index,
                        f"Completed Step {i + 1}/{len(self.encoder_names)}",
                    )
                    self.progress_updated.emit(self.thread_index, 100)
                    self.output_updated.emit(
                        f"\n[Thread {self.thread_index + 1}] Completed Step {i + 1}/{len(self.encoder_names)}: {os.path.basename(current_input)} with {encoder_name}\n"
                    )
                    # Phase 2d follow-up fix (Item 4): inter-step
                    # intermediate cleanup is now sequence-aware. The
                    # previous os.remove silently failed for any
                    # `…_%03d.jpg` template (literal file never exists)
                    # leaving the N actual frames behind. We now route
                    # sequence paths through _cleanup_image_sequence
                    # and keep the single-file branch for video chains.
                    if current_input != self.video_path:
                        if _path_is_sequence(current_input):
                            _cleanup_image_sequence(current_input)
                        else:
                            try:
                                os.remove(current_input)
                            except OSError:
                                pass
                    current_input = output_file
                    current_step_output = None  # transition completed cleanly
                    current_step_is_image = False
                    if i == len(self.encoder_names) - 1:
                        final_output = output_filename
                else:
                    error_msg = f"Error processing {os.path.basename(current_input)} with {encoder_name} (Step {i + 1}/{len(self.encoder_names)}): Return code {rc}"
                    self.error_occurred.emit(error_msg)
                    self.status_updated.emit(self.thread_index, "Error")
                    self.progress_updated.emit(self.thread_index, 0)
                    # Phase 2d follow-up fixes (Items 4 + 11) + Issue 1:
                    # ffmpeg failure on an image-sequence step writes
                    # 0..N partial frames — clean them. For single-file
                    # outputs, remove the 0-byte placeholder AND the
                    # `.partial` sidecar (which contains whatever bytes
                    # ffmpeg wrote before failing). The canonical
                    # `<…>_final.mp4` never existed for this attempt.
                    if is_image_encoder:
                        _cleanup_image_sequence(output_file)
                    else:
                        _cleanup_zero_byte_placeholder(output_file)
                        if temp_output_file is not None:
                            try:
                                if os.path.exists(temp_output_file):
                                    os.remove(temp_output_file)
                            except OSError:
                                pass
                    return
            if final_output:
                self.render_completed.emit(final_output)
        except Exception as e:
            error_msg = f"Error processing {os.path.basename(current_input)}: {str(e)}"
            self.error_occurred.emit(error_msg)
            self.status_updated.emit(self.thread_index, "Error")
            self.progress_updated.emit(self.thread_index, 0)
            # Phase 2d follow-up fixes (Items 4 + 11) + Issue 1: the
            # loop crashed mid-step (Python-level exception, not an
            # ffmpeg rc). current_step_output / current_step_is_image
            # are bounded by the pre-loop init so this is safe even if
            # the crash happened before output_file was assigned.
            # Sequence frames always go; single-file outputs sweep the
            # 0-byte avoid_collision placeholder AND the partial sidecar
            # if it exists. v3.9 F-001 fix: the partial filename now lives
            # at `naming_utils.partial_path(current_step_output)` (which
            # produces `out.partial.mp4`, not `out.mp4.partial`). The
            # cleanup MUST match the same construction used inside the
            # render loop, otherwise orphan `.partial.<ext>` files would
            # accumulate on crash/cancel.
            if current_step_output:
                if current_step_is_image:
                    _cleanup_image_sequence(current_step_output)
                else:
                    _cleanup_zero_byte_placeholder(current_step_output)
                    derived_partial = naming_utils.partial_path(current_step_output)
                    try:
                        if os.path.exists(derived_partial):
                            os.remove(derived_partial)
                    except OSError:
                        pass


class URLInputDialog(QDialog):
    """Modal dialog for batch URL input.

    Collects one or more video URLs plus the download options that map
    directly onto `core.url_downloader.download_videos`. Returns the user
    selection via the `values()` accessor when the dialog is accepted.
    Per the Phase A design note, all option defaults match the underlying
    `download_videos` parameter defaults so behavior is identical to a
    bare call.
    """

    _QUALITY_CHOICES = ("best", "1080p", "720p", "480p", "360p", "smallest")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Video URLs")
        self.setModal(True)
        self.setMinimumWidth(520)

        outer = QVBoxLayout(self)

        hint = QLabel(
            "Paste one URL per line. YouTube, Vimeo, and most yt-dlp-supported sites work."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555; font-weight: normal;")
        outer.addWidget(hint)

        self._urls_edit = QPlainTextEdit()
        self._urls_edit.setPlaceholderText(
            "https://www.youtube.com/watch?v=...\nhttps://..."
        )
        self._urls_edit.setMinimumHeight(120)
        outer.addWidget(self._urls_edit)

        form = QFormLayout()
        self._quality_combo = QComboBox()
        for q in self._QUALITY_CHOICES:
            self._quality_combo.addItem(q, q)
        self._quality_combo.setCurrentText("best")
        form.addRow("Quality:", self._quality_combo)

        self._subs_check = QCheckBox("Also download subtitles (.srt)")
        self._subs_check.setChecked(False)
        form.addRow("", self._subs_check)

        self._concurrent_spin = QSpinBox()
        self._concurrent_spin.setRange(1, 6)
        self._concurrent_spin.setValue(3)
        form.addRow("Max concurrent downloads:", self._concurrent_spin)

        outer.addLayout(form)

        self._buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        # Gate OK on having at least one non-empty line.
        self._buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self._urls_edit.textChanged.connect(self._update_ok_state)
        outer.addWidget(self._buttons)

    def _update_ok_state(self) -> None:
        has_any = any(
            line.strip() for line in self._urls_edit.toPlainText().splitlines()
        )
        self._buttons.button(QDialogButtonBox.Ok).setEnabled(has_any)

    def values(self) -> dict:
        """Return the dialog selections as a plain dict.

        Caller is responsible for passing these to download_videos. Per-URL
        syntactic validation happens inside core.url_downloader, not here.
        """
        urls = [
            line.strip()
            for line in self._urls_edit.toPlainText().splitlines()
            if line.strip()
        ]
        return {
            "urls": urls,
            "quality": self._quality_combo.currentData() or "best",
            "download_subtitles": self._subs_check.isChecked(),
            "max_concurrent": int(self._concurrent_spin.value()),
        }


class URLDownloadWorker(QObject):
    """QThread-friendly worker around `core.url_downloader.download_videos`.

    Mirrors the moveToThread pattern used by cutter/merge/mixer coordinators
    elsewhere in the suite. Designed so all widget state updates happen on
    the main thread via signals.

    Signals:
        progress(idx: int, url: str, pct: float, status: str)
            Per-URL progress callback forwarded from download_videos.
            `status` is "downloading" or "finished".
        finished(results: list)
            Emitted exactly once when the batch ends. Payload is the list
            of `DownloadResult` from download_videos, preserving input order.
        error_message(text: str)
            Emitted on hard failures (e.g. ValueError from argument
            validation) that never produce a results list. Mutually
            exclusive with finished.

    Cancel:
        cancel() sets the threading.Event handed to download_videos. The
        batch ends with `cancelled` error_type for in-flight URLs.
    """

    progress = Signal(int, str, float, str)
    finished = Signal(list)
    error_message = Signal(str)

    def __init__(
        self,
        urls: list,
        work_dir: Path,
        quality: str,
        download_subtitles: bool,
        max_concurrent: int,
    ):
        super().__init__()
        self._urls = list(urls)
        self._work_dir = Path(work_dir)
        self._quality = quality
        self._download_subtitles = bool(download_subtitles)
        self._max_concurrent = int(max_concurrent)
        self._cancel_event = threading.Event()

    @Slot()
    def run(self) -> None:
        """Execute the batch download. Always emits finished or error_message."""
        try:
            results = core_url_downloader.download_videos(
                self._urls,
                self._work_dir,
                quality=self._quality,
                download_subtitles=self._download_subtitles,
                max_concurrent=self._max_concurrent,
                progress_callback=lambda i, u, p, s: self.progress.emit(i, u, p, s),
                cancel_event=self._cancel_event,
            )
            self.finished.emit(results)
        except (ValueError, FileNotFoundError, PermissionError) as exc:
            # download_videos raises only on argument-validation failure.
            self.error_message.emit(f"URL download failed: {exc}")
        except Exception as exc:
            # Defensive: anything else is unexpected; report and continue.
            self.error_message.emit(f"URL download crashed: {exc}")

    def cancel(self) -> None:
        """Set the cancel event so the batch winds down."""
        self._cancel_event.set()


class ScoreWorker(QObject):
    """Phase 3.2 — QThread-friendly wrapper around the scoring runners.

    Runs in its own QThread (see VideoRendererTool._score_threads).
    Computes the requested axes for one (reference, distorted) pair,
    in order: VMAF → SSIM/PSNR → pHash. Each axis is independent —
    a failure in one does not abort the others.

    The worker NEVER touches RenderWorker, the render pipeline, the
    Phase 3.1 queue, or ffmpeg's encode invocation. It only spawns
    its own short-lived ffmpeg children for the scoring filters.

    Signals:
        axis_progress(task_index: int, axis: str, pct: int)
            Coarse progress (0/50/100) for the current axis. Optional.
        score_ready(task_index: int, result: object)
            Emitted once when all requested axes finish. `result`
            is a ScoreResult instance; consumer is the main thread.
        score_error(task_index: int, message: str)
            Emitted on a runner-level catastrophe (not per-axis failure).

    Cancel:
        cancel() sets a threading.Event polled by every runner. In-flight
        ffmpeg children are terminated within ~250 ms of the cancel.
    """

    axis_progress = Signal(int, str, int)
    score_ready = Signal(int, object)
    score_error = Signal(int, str)

    def __init__(
        self,
        task_index: int,
        ffmpeg_path: Path,
        reference: Path,
        distorted: Path,
        *,
        axes: list,
        n_phash_frames: int = 20,
        base_result=None,
    ):
        super().__init__()
        self._task_index = int(task_index)
        self._ffmpeg_path = Path(ffmpeg_path)
        self._reference = Path(reference)
        self._distorted = Path(distorted)
        # Defensive copy + lowercase so the caller doesn't have to
        # care about case. Filtered to known axes inside `process`.
        self._axes = [str(a).lower() for a in axes]
        self._n_phash_frames = int(n_phash_frames)
        self._base_result = base_result
        self._cancel_event = threading.Event()

    @Slot()
    def process(self) -> None:
        """Execute all requested axes sequentially. Emits one final signal.

        Imports happen lazily inside the slot so a module import
        failure in scoring/* never blocks app launch.
        """
        try:
            from core.scoring import (
                ScoreAxisStatus,
                ScoreResult,
                score_phash,
                score_ssim_psnr,
                score_vmaf,
            )
        except Exception as exc:
            self.score_error.emit(
                self._task_index, f"scoring module import failed: {exc}"
            )
            return

        # Seed the result row — runners chain into base_result.
        if self._base_result is not None:
            result = self._base_result
        else:
            try:
                ref_m = self._reference.stat().st_mtime
            except OSError:
                ref_m = 0.0
            try:
                dist_m = self._distorted.stat().st_mtime
            except OSError:
                dist_m = 0.0
            result = ScoreResult(
                reference_path=str(self._reference),
                reference_mtime=ref_m,
                distorted_path=str(self._distorted),
                distorted_mtime=dist_m,
                computed_at=time.time(),
            )

        def cancelled() -> bool:
            return self._cancel_event.is_set()

        try:
            if "vmaf" in self._axes and not cancelled():
                self.axis_progress.emit(self._task_index, "vmaf", 0)
                result = score_vmaf(
                    self._ffmpeg_path,
                    self._reference,
                    self._distorted,
                    should_cancel=cancelled,
                    base_result=result,
                )
                self.axis_progress.emit(self._task_index, "vmaf", 100)

            if ("ssim" in self._axes or "psnr" in self._axes) and not cancelled():
                self.axis_progress.emit(self._task_index, "ssim_psnr", 0)
                result = score_ssim_psnr(
                    self._ffmpeg_path,
                    self._reference,
                    self._distorted,
                    should_cancel=cancelled,
                    base_result=result,
                )
                self.axis_progress.emit(self._task_index, "ssim_psnr", 100)

            if "phash" in self._axes and not cancelled():
                self.axis_progress.emit(self._task_index, "phash", 0)
                result = score_phash(
                    self._ffmpeg_path,
                    self._reference,
                    self._distorted,
                    n_frames=self._n_phash_frames,
                    should_cancel=cancelled,
                    base_result=result,
                )
                self.axis_progress.emit(self._task_index, "phash", 100)
        except Exception as exc:
            self.score_error.emit(self._task_index, f"scoring crashed: {exc}")
            return

        # If everything was cancelled, mark unscored axes accordingly.
        if cancelled():
            for axis_attr in (
                "vmaf_status",
                "ssim_status",
                "psnr_status",
                "phash_status",
            ):
                if getattr(result, axis_attr) == ScoreAxisStatus.PENDING:
                    setattr(result, axis_attr, ScoreAxisStatus.CANCELLED)

        self.score_ready.emit(self._task_index, result)

    def cancel(self) -> None:
        self._cancel_event.set()


class VideoRendererTool(QMainWindow):
    def __init__(self, app_name: str = "1vmo Auto Render"):
        super().__init__()
        self.app_name = app_name
        self.current_version = core_version_state.load_current_version(
            "1vmo Auto Render"
        )
        if self.current_version is None:
            self.current_version = "3.1"
            core_version_state.save_current_version(
                self.current_version, "1vmo Auto Render"
            )
        self.current_assets_version = core_version_state.load_current_version(
            "1vmo Auto Render Assets"
        )
        if self.current_assets_version is None:
            self.current_assets_version = "1.0"
            core_version_state.save_current_version(
                self.current_assets_version, "1vmo Auto Render Assets"
            )
        self.setWindowTitle(
            f"{self.app_name} v{self.current_version} (Assets v{self.current_assets_version})"
        )
        # Default size reduced from original 1600x900 for more compact launch.
        # 1280x800 is a good balance (original min was 1280). Resizable.
        # Backup has original if needed.
        self.setGeometry(100, 100, 1280, 800)
        self.setMinimumSize(960, 640)
        self.resize(1280, 800)
        # The in-app update channel was removed (ADR-0017 / B-051): updates now
        # come from a source `git pull`, so there is no startup network call and
        # no "Updates" toolbar button. The version label above is read from
        # assets/Version AutoRender.json via core.version_state.
        try:
            icon_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "assets", "Auto_Render.ico"
            )
            if os.path.exists(icon_path):
                app_icon = QIcon(icon_path)
                self.setWindowIcon(app_icon)
                QApplication.setWindowIcon(app_icon)
                if os.name == "nt":
                    import ctypes

                    myappid = f"1vmo.Auto.Render.v{self.current_version}"
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                        myappid
                    )
        except Exception as e:
            logger.error(f"Error setting icon: {str(e)}")
        self.videos = []
        self.output_directory = ""
        self.encoder_options = []
        self.selected_encoders = []
        self.encoder_params = {}
        self.is_rendering = False
        # M-1: render threads that fail to stop within the join timeout are
        # parked here as (thread, worker) pairs so their last reference is
        # never dropped while still running. App-lifetime list — never reset
        # per batch, or a still-running parked thread could be GC'd and abort
        # the process ("QThread: Destroyed while thread is still running").
        self._parked_threads: list = []
        # #1: latches the one-time "couldn't save queue state" warning so a
        # disk issue during a batch surfaces once, not on every snapshot.
        self._queue_persist_warned = False
        self.num_threads = 3
        self.sequential_mode = False
        self.sequential_encoders = [None] * SEQUENTIAL_SLOT_COUNT
        self.SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
        self.FFMPEG_PATH, self.FFPROBE_PATH = core_ffmpeg_runner.resolve_binaries(
            self.SCRIPT_DIR
        )
        # 2c-c-3: portable user-data resolution + first-launch migration
        self.USER_DATA_DIR = resolve_or_die(
            self.SCRIPT_DIR,
            on_error=lambda msg: QMessageBox.critical(None, "1vmo Auto Render", msg),
        )
        _migrated = migrate_legacy_configs(self.SCRIPT_DIR, self.USER_DATA_DIR)
        if _migrated:
            logger.info(f"Migrated legacy configs to {self.USER_DATA_DIR}: {_migrated}")
        self.CONFIG_FILE = self.USER_DATA_DIR / "config_video_renderer.json"
        self.USER_PRESETS_FILE = self.USER_DATA_DIR / "encoder.user.json"
        # Phase 3.1 local persistent queue (no cloud / no remote queue).
        # The store wraps a single JSON file at
        # `USER_DATA_DIR/queue.json` with file-lock + atomic write so
        # an interrupted render (crash, Cmd-Q, kill -9) can be resumed
        # on next launch. RenderWorker / ffmpeg pipeline are unchanged.
        # All store calls are wrapped in try/except OSError downstream
        # so a disk-full state cannot crash the renderer.
        self.queue_store = QueueStore(self.USER_DATA_DIR)
        # Saved-batch loaded from disk (if any). Filled in below after
        # setup_ui so the resume prompt does not block the main window
        # from appearing.
        self._pending_resume_batch: Optional[QueueBatch] = None
        # Per-batch state used by queue persistence — populated in
        # start_render(). Pre-declare here so the close path can read
        # them safely even if no batch has run yet this session.
        self._current_batch_uuid: Optional[str] = None
        self._task_uuids: list[str] = []
        # Phase 3.2 — local-only scoring system (no cloud / no remote
        # analysis). Lazy import inside try/except so a defective
        # scoring module cannot block app launch — the rest of the
        # app still runs without scoring.
        self.scoring_caps = None
        self.score_cache = None
        try:
            from core.scoring import (
                ScoreCache as _ScoreCache,
            )
            from core.scoring import (
                detect as _scoring_detect,
            )

            self.scoring_caps = _scoring_detect(self.FFMPEG_PATH)
            self.score_cache = _ScoreCache(self.USER_DATA_DIR)
        except Exception as exc:
            logger.error(f"scoring: init failed (continuing without scoring): {exc}")
        # Phase 3.4 — pause/resume flag. Loaded from queue_state.json
        # at startup if present; persisted on toggle. Default False
        # so behavior matches pre-3.4 builds when no side file exists.
        self.is_paused = False
        try:
            from core.orchestration.queue_state import load_queue_state

            _qs = load_queue_state(self.USER_DATA_DIR)
            if _qs is not None and _qs.paused:
                self.is_paused = True
        except Exception as exc:
            logger.error(f"queue_state: load failed (continuing unpaused): {exc}")
        # Active ScoreWorker threads — separate from render_threads
        # so scoring NEVER contends for the render thread pool.
        # Tuple shape: (QThread, ScoreWorker, task_index).
        self._score_threads: list = []
        # Per-render-row latest ScoreResult, keyed by row reference.
        # Used by the UI cell renderer; never persisted directly
        # (the source of truth is self.score_cache).
        self._score_rows_by_tree_item: dict = {}
        self.ENCODER_FILE = self.SCRIPT_DIR / "assets" / "Encoder.txt"
        self._check_dependencies()

        # Phase 1: detect NVENC capabilities once at startup. Cached on
        # self.gpu_caps for UI and (Phase 2) encoder filter logic.
        self.gpu_caps = gpu_detect.detect(self.FFMPEG_PATH)

        self.config = self.load_config()
        _d = core_config.APP_DEFAULTS
        self.num_threads = self.config.get("num_threads", 3)
        self.output_collision = self.config.get("output_collision", _d.output_collision)
        self.gpu_error_action = self.config.get("gpu_error_action", _d.gpu_error_action)
        self.gpu_enabled = self.config.get("gpu_enabled", _d.gpu_enabled)
        self.gpu_codec = self.config.get("gpu_codec", _d.gpu_codec)
        self.gpu_preset = self.config.get("gpu_preset", _d.gpu_preset)
        self.gpu_max_quality_mode = self.config.get("gpu_max_quality_mode", False)
        self.gpu_max_concurrent = self.config.get(
            "gpu_max_concurrent", _d.gpu_max_concurrent
        )
        self._gpu_semaphore = QSemaphore(self.gpu_max_concurrent)
        # Polish batch (UI-11): once the user cancels a URL batch, the
        # progress handler must not overwrite the "Cancelling…" label.
        self._url_cancel_requested = False
        self.encoder_options = self.load_encoder_options()
        # Phase 2d production-hardening fix (Issue 4): main window
        # accepts video file drops. Handlers are defined further down
        # (dragEnterEvent / dragMoveEvent / dropEvent) and use the
        # same `self.videos` mutation path as the 📥 Select button —
        # so dropping a file is functionally identical to picking it
        # via the dialog. Drops during an in-flight render queue up
        # for the next batch, matching select_videos semantics.
        self.setAcceptDrops(True)
        self.setup_ui()
        QApplication.styleHints().setColorScheme(Qt.ColorScheme.Light)
        self.setup_style()

        # Surface GPU status in the built-in QMainWindow status bar.
        self._init_gpu_status_bar()
        ultimate_dir = self.SCRIPT_DIR / "🕹️ 1vmo Ultimate"
        if ultimate_dir.exists():
            self.output_directory = str(ultimate_dir)
            self._set_output_dir_label(self.output_directory)
        else:
            last_output = self.config.get("output_dir", "")
            if last_output and os.path.isdir(last_output):
                self.output_directory = last_output
                self._set_output_dir_label(self.output_directory)
        last_videos = self.config.get("input_files", [])
        if last_videos:
            valid_videos = [video for video in last_videos if os.path.isfile(video)]
            if valid_videos:
                self.videos = valid_videos
                self.update_video_list()
        self.load_encoders_to_tree()
        self._apply_slot_defaults()

        # Keyboard shortcuts (Phase 2.5 F4 onboarding)
        QShortcut(QKeySequence("Ctrl+O"), self, self.select_videos)
        QShortcut(QKeySequence("F1"), self, self.show_help)
        QShortcut(QKeySequence("F5"), self, self._on_start_shortcut)
        QShortcut(QKeySequence(Qt.Key_Escape), self, self._on_stop_shortcut)
        QShortcut(QKeySequence(Qt.Key_Delete), self.tree_videos, self.delete_videos)

        # Phase 3.1 — load any saved batch from disk and schedule a
        # resume prompt AFTER the event loop starts. Using a single-
        # shot 0ms timer means the main window paints first; the
        # modal then appears on top of an already-visible app, which
        # is the correct UX (mirrors the FastFlix prompt pattern).
        # All disk reads are wrapped — a corrupt or unreadable queue
        # file logs a warning and is silently ignored, never crashes
        # startup.
        if self.config.get("queue_persistence_enabled", True):
            try:
                saved = self.queue_store.load()
            except Exception as exc:
                logger.error(f"queue_store: load() failed at startup: {exc}")
                saved = None
            if saved is not None and any(
                t.status in UNFINISHED_STATUSES for t in saved.tasks
            ):
                self._pending_resume_batch = saved
                from PySide6.QtCore import QTimer

                QTimer.singleShot(0, self._prompt_resume_saved_batch)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        top_frame = QFrame(objectName="top_frame")
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(5, 5, 5, 5)
        top_layout.setSpacing(5)
        input_frame = QFrame(objectName="input_frame")
        input_frame.setFrameStyle(QFrame.StyledPanel)
        input_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        # Functional: prevent top-left (buttons + tree) from becoming too narrow/compact
        # on small windows, so Select/Add URL etc stay usable. Design unchanged.
        input_frame.setMinimumWidth(280)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setSpacing(2)
        input_layout.setContentsMargins(5, 2, 5, 2)
        config_frame = QFrame(objectName="config_frame")
        config_frame.setFrameStyle(QFrame.StyledPanel)
        config_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        config_frame.setMinimumWidth(280)
        config_layout = QVBoxLayout(config_frame)
        config_layout.setSpacing(2)
        config_layout.setContentsMargins(5, 2, 5, 2)
        top_split = QSplitter(Qt.Horizontal)
        top_split.addWidget(input_frame)
        top_split.addWidget(config_frame)
        top_split.setChildrenCollapsible(False)
        top_split.setStretchFactor(0, 1)
        top_split.setStretchFactor(1, 1)
        top_layout.addWidget(top_split)
        bottom_frame = QFrame(objectName="bottom_frame")
        bottom_frame.setFrameStyle(QFrame.StyledPanel)
        bottom_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        bottom_layout = QHBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(5, 5, 5, 5)
        bottom_layout.setSpacing(5)
        progress_frame = QFrame(objectName="progress_frame")
        progress_frame.setFrameStyle(QFrame.StyledPanel)
        progress_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setSpacing(2)
        progress_layout.setContentsMargins(5, 2, 5, 2)
        output_frame = QFrame(objectName="output_frame")
        output_frame.setFrameStyle(QFrame.StyledPanel)
        output_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        output_layout = QVBoxLayout(output_frame)
        output_layout.setSpacing(5)
        output_layout.setContentsMargins(5, 5, 5, 5)
        bottom_split = QSplitter(Qt.Horizontal)
        bottom_split.addWidget(progress_frame)
        bottom_split.addWidget(output_frame)
        bottom_split.setChildrenCollapsible(False)
        bottom_split.setStretchFactor(0, 1)
        bottom_split.setStretchFactor(1, 1)
        bottom_layout.addWidget(bottom_split)
        main_split = QSplitter(Qt.Vertical)
        main_split.addWidget(top_frame)
        main_split.addWidget(bottom_frame)
        main_split.setChildrenCollapsible(False)
        main_split.setStretchFactor(0, 1)
        main_split.setStretchFactor(1, 1)
        main_layout.addWidget(main_split)
        video_controls = QGridLayout()
        video_controls.setHorizontalSpacing(5)
        video_controls.setVerticalSpacing(5)
        select_btn = self.create_video_button(
            "📥 Select (0)", self.select_videos, "#e3f2fd", "#1976d2", "#bbdefb"
        )
        select_btn.setToolTip("Add video files (Ctrl+O)")
        select_btn.setObjectName("select_btn")
        self.add_url_btn = self.create_video_button(
            "🌐 Add URL", self.add_url, "#e8f5e9", "#2e7d32", "#a5d6a7"
        )
        self.add_url_btn.setToolTip(
            "Download videos from URLs (YouTube, Vimeo, etc.) and add them to the queue"
        )
        self.add_url_btn.setObjectName("add_url_btn")
        delete_btn = self.create_video_button(
            "🗑️ Delete", self.delete_videos, "#ffcdd2", "#c62828", "#ef9a9a", delete=True
        )
        delete_btn.setToolTip("Remove selected videos from queue (Del)")
        delete_btn.setEnabled(False)
        self.btn_delete = delete_btn
        settings_btn = self.create_video_button(
            "Settings", self.open_settings, "#fff3e0", "#e65100", "#ffe0b2"
        )
        settings_btn.setToolTip("Open Settings dialog")
        help_btn = self.create_video_button(
            "❓ Help", self.show_help, "#e3f2fd", "#1976d2", "#bbdefb"
        )
        help_btn.setToolTip("Open user guide")
        # Phase 3.3 — "🩺 Health" toolbar button opens RenderHealthDialog,
        # a read-only summary of scores + recommendations across the
        # current/last batch. Never auto-opens; toolbar-only discovery.
        self.health_btn = self.create_video_button(
            "🩺 Health",
            self._open_render_health_dialog,
            "#e8f5e9",
            "#2e7d32",
            "#c8e6c9",
        )
        self.health_btn.setToolTip(
            "Open Render Health: per-row scores + optimization suggestions"
        )
        # Phase 3.4 — Pause/Resume button + Diagnostics export.
        self.pause_btn = self.create_video_button(
            "⏸️ Pause",
            self._toggle_pause,
            "#fff8e1",
            "#f57f17",
            "#ffe082",
        )
        self.pause_btn.setToolTip(
            "Pause/Resume queue. Current task finishes; next dispatch waits."
        )
        self.diagnostics_btn = self.create_video_button(
            "🧰 Diagnostics",
            self._open_diagnostics_export,
            "#ede7f6",
            "#311b92",
            "#d1c4e9",
        )
        self.diagnostics_btn.setToolTip(
            "Export local diagnostic bundle (logs + queue + scores + sanitized config)"
        )
        # Arrange in 2 rows x 4 columns for compact, consistent layout.
        # Keeps exact same button designs, just better arrangement for top-left box.
        # On small windows, buttons will still look the same but area is compact.
        video_controls.addWidget(select_btn, 0, 0)
        video_controls.addWidget(self.add_url_btn, 0, 1)
        video_controls.addWidget(delete_btn, 0, 2)
        video_controls.addWidget(settings_btn, 0, 3)
        video_controls.addWidget(help_btn, 1, 0)
        video_controls.addWidget(self.health_btn, 1, 1)
        video_controls.addWidget(self.pause_btn, 1, 2)
        video_controls.addWidget(self.diagnostics_btn, 1, 3)
        step1_label = QLabel("📥 Step 1: Add videos")
        step1_label.setStyleSheet(
            "font-size: 13px; color: #555; font-weight: bold; padding: 4px 2px 2px 2px;"
        )
        input_layout.addWidget(step1_label)
        input_layout.addLayout(video_controls)
        self.tree_videos = QTreeWidget()
        self.empty_videos_hint = QLabel(
            "Drag videos here or click 📥 Select", self.tree_videos.viewport()
        )
        self.empty_videos_hint.setAlignment(Qt.AlignCenter)
        self.empty_videos_hint.setStyleSheet(
            "color: #999; background: transparent; font-style: italic; font-weight: normal; padding: 0;"
        )
        self.empty_videos_hint.hide()
        self.tree_videos.setHeaderLabels(["No.", "Filename", "Duration", "Resolution"])
        self.tree_videos.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree_videos.setAlternatingRowColors(True)
        self.tree_videos.header().setDefaultAlignment(Qt.AlignCenter)
        # Polish batch (UI-13): Delete only acts on a selection, so its
        # enabled state follows the selection. The no-selection modal in
        # delete_videos stays as a dead-path fallback.
        self.tree_videos.itemSelectionChanged.connect(self._sync_delete_enabled)
        self._sync_delete_enabled()
        input_layout.addWidget(self.tree_videos, 1)
        encoder_controls = FlowLayout(h_spacing=5, v_spacing=5)
        # 2c-c-4: edit/delete buttons must be instance attrs so the
        # selection-change handler can toggle their enabled state.
        self.btn_add_encoder = self.create_video_button(
            "♻️ Add", self.add_encoder, "#e3f2fd", "#1976d2", "#bbdefb"
        )
        self.btn_add_encoder.setToolTip("Create a new render preset")
        self.btn_edit_encoder = self.create_video_button(
            "🛠️ Edit", self.edit_encoder, "#fff3e0", "#e65100", "#ffe0b2"
        )
        self.btn_edit_encoder.setToolTip(
            "Edit the selected preset (built-in presets are read-only)"
        )
        self.btn_delete_encoder = self.create_video_button(
            "🗑️ Delete",
            self.delete_encoder,
            "#ffcdd2",
            "#c62828",
            "#ef9a9a",
            delete=True,
        )
        self.btn_delete_encoder.setToolTip(
            "Delete the selected preset (built-in presets are read-only)"
        )
        # B-018: Clone is the supported way to start customizing a built-in
        # (read-only) preset. Always enabled — _update_encoder_buttons_enabled
        # only toggles Edit/Delete, so Clone stays clickable for built-ins.
        self.btn_clone_encoder = self.create_video_button(
            "📄 Clone", self.clone_encoder, "#ede7f6", "#5e35b1", "#d1c4e9"
        )
        self.btn_clone_encoder.setToolTip(
            "Copy the selected preset into a new, editable user preset"
        )
        update_btn = self.create_video_button(
            "🔄 Refresh", self.reload_all, "#e8f5e9", "#2e7d32", "#c8e6c9"
        )
        update_btn.setToolTip("Reload presets from Encoder.txt")
        self.group_combo = QComboBox()
        # Relaxed fixed sizes for better responsiveness on small windows.
        # Visual style unchanged.
        self.group_combo.setMinimumWidth(110)
        self.group_combo.setMinimumHeight(22)
        self.group_combo.addItem("🕹️ 1vmo Ultimate")
        self.group_combo.addItem("All Groups")
        self.group_combo.currentTextChanged.connect(self.on_group_changed)
        encoder_controls.addWidget(self.btn_add_encoder)
        encoder_controls.addWidget(self.btn_edit_encoder)
        encoder_controls.addWidget(self.btn_delete_encoder)
        encoder_controls.addWidget(self.btn_clone_encoder)
        encoder_controls.addWidget(update_btn)
        encoder_controls.addWidget(QLabel("Filter"))
        encoder_controls.addWidget(self.group_combo)
        step2_label = QLabel("🎬 Step 2: Pick presets")
        step2_label.setStyleSheet(
            "font-size: 13px; color: #555; font-weight: bold; padding: 4px 2px 2px 2px;"
        )
        config_layout.addWidget(step2_label)
        config_layout.addLayout(encoder_controls)
        # B-018 Option B: selection-aware status label between buttons and tree.
        # Text populated by _update_encoder_status_label on selection change.
        # Fixed-height empty string preserves layout stability when message clears.
        self.encoder_status_label = QLabel("")
        self.encoder_status_label.setStyleSheet(
            "color: #757575; font-style: italic; font-size: 12px; "
            "padding: 2px 4px; min-height: 18px;"
        )
        self.encoder_status_label.setWordWrap(True)
        config_layout.addWidget(self.encoder_status_label)
        self.tree_encoders = QTreeWidget()
        self.tree_encoders.setHeaderLabels(
            ["No.", "Group", "Name", "Description", "Details"]
        )
        self.tree_encoders.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree_encoders.setAlternatingRowColors(True)
        self.tree_encoders.header().setDefaultAlignment(Qt.AlignCenter)
        # 2c-c-4: disable Edit/Delete when any selected entry is built-in.
        self.tree_encoders.itemSelectionChanged.connect(
            self._update_encoder_buttons_enabled
        )
        self.tree_encoders.itemSelectionChanged.connect(self._update_start_button_state)
        # B-018 Option B: selection-aware status label
        self.tree_encoders.itemSelectionChanged.connect(
            self._update_encoder_status_label
        )
        config_layout.addWidget(self.tree_encoders, 1)
        mode_frame = QFrame(objectName="mode_frame")
        mode_frame.setFrameStyle(QFrame.StyledPanel)
        mode_layout = QVBoxLayout(mode_frame)
        mode_layout.setContentsMargins(5, 5, 5, 5)
        mode_layout.setSpacing(5)
        render_mode_frame = QFrame()
        render_mode_layout = QHBoxLayout(render_mode_frame)
        render_mode_layout.setContentsMargins(0, 0, 0, 0)
        self.mode_all = QRadioButton("Render Once")
        self.mode_all.setChecked(True)
        self.mode_all.toggled.connect(self.on_mode_changed)
        self.mode_sequential = QRadioButton("Render All Variants")
        self.mode_sequential.toggled.connect(self.on_mode_changed)
        render_mode_layout.addWidget(self.mode_all)
        render_mode_layout.addWidget(self.mode_sequential)
        render_mode_layout.addStretch()
        mode_layout.addWidget(render_mode_frame)
        self.sequential_combos = []
        self.sequential_clear_btns = []
        sequential_frame = QFrame()
        sequential_layout = QHBoxLayout(sequential_frame)
        sequential_layout.setContentsMargins(0, 0, 0, 0)
        sequential_layout.setSpacing(12)
        combo_colors = [
            "#FFCDD2",
            "#C8E6C9",
            "#BBDEFB",
            "#E1BEE7",
            "#FFECB3",
            "#FFCCBC",
            "#B2EBF2",
            "#F8BBD0",
        ]
        for i in range(SEQUENTIAL_SLOT_COUNT):
            combo_container = QFrame()
            combo_container.setStyleSheet(
                f"background-color: {combo_colors[i]}; border-radius: 4px; padding: 2px;"
            )
            combo_layout = QVBoxLayout(combo_container)
            combo_layout.setContentsMargins(5, 5, 5, 5)
            combo_layout.setSpacing(2)
            label = QLabel(f"{i + 1}")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("font-weight: bold;")
            combo_layout.addWidget(label)
            combo = QComboBox()
            combo.setEnabled(False)
            # Relaxed hard max/fixed for compactness on small windows.
            # Keep minimums so they remain clickable and styled the same.
            combo.setMinimumWidth(90)
            combo.setMaximumWidth(180)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(10)
            combo.setMinimumHeight(20)
            combo.setPlaceholderText("Select preset…")
            self.sequential_combos.append(combo)
            combo.currentTextChanged.connect(self._on_slot_text_changed)
            combo.currentTextChanged.connect(lambda text, c=combo: c.setToolTip(text))
            combo_row = QHBoxLayout()
            combo_row.setContentsMargins(0, 0, 0, 0)
            combo_row.setSpacing(2)
            combo_row.addWidget(combo)
            clear_btn = QPushButton("X")
            # Smaller min size for compactness.
            # Visual style (colors, border, font) kept the same.
            clear_btn.setMinimumSize(16, 20)
            clear_btn.setToolTip("Clear this slot")
            clear_btn.setStyleSheet(
                "background-color: white; color: #666; border: 1px solid #ccc; border-radius: 3px; font-weight: bold; font-size: 11px; min-width: 16px; max-width: 18px;"
            )
            clear_btn.hide()
            clear_btn.clicked.connect(lambda _checked, c=combo: c.setCurrentIndex(0))
            self.sequential_clear_btns.append(clear_btn)
            combo_row.addWidget(clear_btn)
            combo_layout.addLayout(combo_row)
            sequential_layout.addWidget(combo_container)
        step_assign_label = QLabel(
            "Optional: Assign to slots (for Render All Variants only)"
        )
        step_assign_label.setStyleSheet(
            "font-size: 13px; color: #555; font-weight: bold; padding: 4px 2px 2px 2px;"
        )
        mode_layout.addWidget(step_assign_label)
        self.empty_slots_hint = QLabel(
            "Use the dropdowns below to assign presets to slots"
        )
        self.empty_slots_hint.setAlignment(Qt.AlignCenter)
        self.empty_slots_hint.setStyleSheet(
            "color: #999; background: transparent; font-style: italic; font-weight: normal; padding: 6px;"
        )
        mode_layout.addWidget(self.empty_slots_hint)
        self.empty_slots_hint.hide()
        self.slot_scroll = QScrollArea()
        self.slot_scroll.setWidget(sequential_frame)
        self.slot_scroll.setWidgetResizable(True)
        self.slot_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.slot_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.slot_scroll.setFrameShape(QFrame.NoFrame)
        # Made adaptive for responsiveness: no longer hard-fixed at init.
        # On small windows it can shrink; on large it grows naturally.
        # Minimum set so slots remain usable when visible.
        self.slot_scroll.setMinimumHeight(60)
        mode_layout.addWidget(self.slot_scroll)
        # Render Once is the default mode (mode_all.setChecked(True) above),
        # so the slot strip starts hidden; on_mode_changed keeps it in sync.
        self.slot_scroll.setVisible(False)
        config_layout.addWidget(mode_frame)
        progress_info_frame = QFrame(objectName="progress_info_frame")
        progress_info_layout = QHBoxLayout(progress_info_frame)
        progress_info_layout.setContentsMargins(10, 2, 10, 2)
        # Polish batch (UI-14): initial text carries the same two-line
        # shape as the runtime updates ("Progress: a/b renders\nETA: x")
        # so the header does not change height when a render starts.
        self.progress_label = QLabel("Progress: 0/0 renders\nETA: —")
        self.current_label = QLabel("Idle")
        progress_info_layout.addWidget(self.progress_label)
        progress_info_layout.addWidget(self.current_label)
        progress_layout.addWidget(progress_info_frame)
        self.canvas = QFrame(objectName="canvas")
        # Wrapped in scroll area so the progress grid can scroll when window is small
        # or there are many tasks. This makes the top-left box area usable/compact
        # instead of overly squished. Visual design of the boxes and canvas bg unchanged.
        self.boxes_scroll = QScrollArea()
        self.boxes_scroll.setWidget(self.canvas)
        self.boxes_scroll.setWidgetResizable(False)
        self.boxes_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.boxes_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.boxes_scroll.setFrameShape(QFrame.NoFrame)
        self.boxes_scroll.setMinimumHeight(60)
        progress_layout.addWidget(self.boxes_scroll)
        self.box_size = 15
        self.padding = 2
        # Initial value — recomputed in _layout_progress_boxes based on real size.
        self.progress_boxes = []
        # Give canvas a reasonable starting size so first _layout has good viewport hint
        self.canvas.resize(300, 80)
        thread_frame = QFrame()
        # Removed hard fixed height — now flexible. Minimum preserves worker row readability.
        thread_frame.setMinimumHeight(80)
        self.thread_layout = QVBoxLayout(thread_frame)
        self.thread_layout.setSpacing(2)
        self.thread_layout.setContentsMargins(5, 2, 5, 2)
        # M-3: single builder for the worker rows; start_render calls the same
        # method to regenerate them when num_threads changes.
        self._rebuild_worker_rows(self.num_threads)
        progress_layout.addWidget(thread_frame)
        self.output_text = QTextEdit()
        self.output_text.document().setMaximumBlockCount(2000)
        # Removed hard fixed height for better responsiveness on small windows.
        # Minimum keeps output visible but allows it to grow/shrink with splitter.
        self.output_text.setMinimumHeight(80)
        self.output_text.setReadOnly(True)
        progress_layout.addWidget(self.output_text)
        controls_frame = QFrame(objectName="sub_frame")
        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.setContentsMargins(5, 5, 5, 5)
        controls_layout.setSpacing(5)
        top_controls = QHBoxLayout(spacing=5)
        dir_btn = QPushButton("📍 Directory")
        # Reduced hard fixed size for responsiveness. Minimum keeps button usable.
        # Visual style (color, border, emoji) unchanged.
        dir_btn.setMinimumWidth(100)
        dir_btn.setMinimumHeight(28)
        dir_btn.setToolTip("Choose output folder")
        dir_btn.clicked.connect(self.select_output_directory)
        self.dir_label = QLabel()
        # Polish batch (G-widen): Ignored horizontal policy — the label
        # takes only the width the layout allocates, so its (elided)
        # text can never push output_frame wider via the splitter.
        self.dir_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        # Phase 2d follow-up fix (Issue 7 — fullscreen clipping): the
        # previous 10px right padding ran the text right up against the
        # adjacent "📂 Open" button when the window was maximised, so
        # long output paths visually clipped. Bump to 24px right and
        # also enable a tooltip whose text we keep in sync with the
        # path via select_output_directory / __init__ assignments.
        self.dir_label.setStyleSheet("padding-left: 10px; padding-right: 24px;")
        self._set_output_dir_label("")
        open_btn = QPushButton("📂 Open")
        # Reduced hard fixed size — now adapts better on small windows.
        # Look (colors, shape) kept identical.
        open_btn.setMinimumWidth(100)
        open_btn.setMinimumHeight(28)
        open_btn.setToolTip("Open output folder in Explorer")
        open_btn.clicked.connect(self.open_output_directory)
        top_controls.addWidget(dir_btn)
        top_controls.addWidget(self.dir_label, stretch=1)
        top_controls.addWidget(open_btn)
        bottom_controls = QHBoxLayout(spacing=5)
        bottom_controls.addStretch(1)
        self.btn_start = QPushButton("🚀 Start")
        # Hard fixed sizes relaxed to minimums. Enables compact mode on small windows.
        # Exact same visual design and emojis preserved.
        self.btn_start.setMinimumWidth(110)
        self.btn_start.setMinimumHeight(26)
        self.btn_start.setToolTip("Begin rendering (F5)")
        self.btn_start.clicked.connect(self.start_render)
        self.btn_cancel = QPushButton("🛑 Stop")
        self.btn_cancel.setMinimumWidth(110)
        self.btn_cancel.setMinimumHeight(26)
        self.btn_cancel.setToolTip("Cancel current renders (Esc)")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setProperty("delete", True)
        self.btn_cancel.clicked.connect(self.cancel_render)
        bottom_controls.addWidget(self.btn_start)
        bottom_controls.addWidget(self.btn_cancel)
        bottom_controls.addStretch(1)
        step3_label = QLabel("📁 Step 3: Choose output folder")
        step3_label.setStyleSheet(
            "font-size: 13px; color: #555; font-weight: bold; padding: 4px 2px 2px 2px;"
        )
        controls_layout.addWidget(step3_label)
        controls_layout.addLayout(top_controls)
        step4_label = QLabel("▶️ Step 4: Start rendering")
        step4_label.setStyleSheet(
            "font-size: 13px; color: #555; font-weight: bold; padding: 4px 2px 2px 2px;"
        )
        controls_layout.addWidget(step4_label)
        controls_layout.addLayout(bottom_controls)
        output_layout.addWidget(controls_frame)
        # Phase 3.2 — three extra columns appended for local scoring
        # output (VMAF mean/p5, dHash distance, SSIM). Hidden by default
        # only if the bundled ffmpeg + scoring module are absent; the
        # column titles stay visible so the right-click "Score this
        # render" menu has a target. RenderWorker is unaware of these
        # columns — they are purely UI state.
        self.tree_output = core_widgets.create_output_tree(
            [
                "No.",
                "Original Filename",
                "Output Filename",
                "Duration",
                "Resolution",
                "Status",
                "VMAF",
                "pHash",
                "SSIM",
            ]
        )
        # Phase 3.2 — context-menu wiring for manual scoring.
        from PySide6.QtCore import Qt as _Qt

        self.tree_output.setContextMenuPolicy(_Qt.CustomContextMenu)
        self.tree_output.customContextMenuRequested.connect(
            self._show_output_context_menu
        )
        output_layout.addWidget(self.tree_output, 1)
        self.resizeEvent = self.on_resize

        self._update_empty_hints()
        self._update_start_button_state()

    def on_resize(self, event):
        """Căn chỉnh kích thước các cột khi cửa sổ thay đổi kích thước"""
        # Phase 2d production-hardening fix (Issue 9): Resolution column
        # (col 3) was 0.15 — narrow enough to truncate "3840x2160" on
        # smaller fullscreen widths. Re-balanced filename and resolution
        # shares to leave the resolution column its proportional share.
        # Polish batch (UI-01): width base is the VIEWPORT (excludes any
        # vertical scrollbar) and shares sum to 0.95 so columns can never
        # outgrow the viewport — kills the always-on horizontal scrollbars.
        total_width = self.tree_videos.viewport().width()
        # Improved for small windows: use proportional but enforce mins so columns stay usable.
        # No visual change on normal sizes.
        self.tree_videos.setColumnWidth(0, max(30, int(total_width * 0.067)))
        self.tree_videos.setColumnWidth(1, max(180, int(total_width * 0.57)))
        self.tree_videos.setColumnWidth(2, max(60, int(total_width * 0.142)))
        self.tree_videos.setColumnWidth(3, max(70, int(total_width * 0.171)))
        total_width = self.tree_encoders.viewport().width()
        # Improved for small windows: mins to keep readable.
        self.tree_encoders.setColumnWidth(0, max(30, int(total_width * 0.083)))
        self.tree_encoders.setColumnWidth(1, max(80, int(total_width * 0.165)))
        self.tree_encoders.setColumnWidth(2, max(80, int(total_width * 0.165)))
        self.tree_encoders.setColumnWidth(3, max(120, int(total_width * 0.454)))
        self.tree_encoders.setColumnWidth(4, max(40, int(total_width * 0.083)))
        if hasattr(self, "empty_videos_hint"):
            self.empty_videos_hint.setGeometry(self.tree_videos.viewport().rect())
        total_width = self.tree_output.viewport().width()
        # Phase 3.2 — column count grew from 6 to 9 (+VMAF/pHash/SSIM).
        # Re-balanced shares; pre-existing 6 columns each lose ~30% of
        # their share to make room. Polish batch (UI-01): viewport base
        # + shares sum to 0.95 (see tree_videos note above). The user
        # can still drag-resize at runtime; this just sets the split.
        # Improved: added mins for small window usability (no design change).
        if self.tree_output.columnCount() >= 9:
            self.tree_output.setColumnWidth(0, max(25, int(total_width * 0.048)))
            self.tree_output.setColumnWidth(1, max(80, int(total_width * 0.171)))
            self.tree_output.setColumnWidth(2, max(100, int(total_width * 0.237)))
            self.tree_output.setColumnWidth(3, max(40, int(total_width * 0.076)))
            self.tree_output.setColumnWidth(4, max(50, int(total_width * 0.085)))
            self.tree_output.setColumnWidth(5, max(50, int(total_width * 0.095)))
            self.tree_output.setColumnWidth(
                6, max(50, int(total_width * 0.095))
            )  # VMAF
            self.tree_output.setColumnWidth(
                7, max(40, int(total_width * 0.067))
            )  # pHash
            self.tree_output.setColumnWidth(
                8, max(40, int(total_width * 0.076))
            )  # SSIM
        else:
            # Fallback to the pre-3.2 layout if the tree was built
            # with only the legacy 6 columns (defensive — should not
            # happen at runtime, but covers test harnesses).
            self.tree_output.setColumnWidth(0, max(30, int(total_width * 0.083)))
            self.tree_output.setColumnWidth(1, max(80, int(total_width * 0.207)))
            self.tree_output.setColumnWidth(2, max(100, int(total_width * 0.289)))
            self.tree_output.setColumnWidth(3, max(50, int(total_width * 0.124)))
            self.tree_output.setColumnWidth(4, max(50, int(total_width * 0.124)))
            self.tree_output.setColumnWidth(5, max(50, int(total_width * 0.124)))
        # Batch UI-3 (UI-02/UI-09): reflow the progress grid to the live
        # canvas width and re-elide the output-directory label.
        if hasattr(self, "progress_boxes"):
            self._layout_progress_boxes()
        if getattr(self, "output_directory", ""):
            self._set_output_dir_label(self.output_directory)
        super().resizeEvent(event)

    def _set_output_dir_label(self, path):
        if not path:
            self.dir_label.setText("Output: not selected")
            self.dir_label.setToolTip("")
            return
        fm = self.dir_label.fontMetrics()
        elided = fm.elidedText(
            path, Qt.ElideMiddle, max(80, self.dir_label.width() - 16)
        )
        self.dir_label.setText(f"Output: {elided}")
        self.dir_label.setToolTip(path)

    def setup_style(self):
        # Batch UI-1 (v3.9 UI hardening). Three structural changes:
        #
        # 1) The sheet moves from the QMainWindow to the CENTRAL WIDGET.
        #    Qt stylesheets cascade down the parent chain, so the old
        #    window-level sheet restyled every child dialog and
        #    QMessageBox: 120px-pinned OK/Cancel buttons, bold blue body
        #    text, black text editors in EncoderDialog (UI-04). Dialogs
        #    are parented to the window, not the central widget, so they
        #    now render native.
        #
        # 2) Width pinning removed from the QPushButton base rule. QSS
        #    min/max-width bound the CONTENT box; padding (2x8) and
        #    border (2x1) are added on top — which is why every button
        #    measured 138px and why setFixedWidth(150) lost (recon
        #    B3/B7/D). Toolbar buttons keep a 120px content FLOOR via
        #    the [toolbar="true"] dynamic property (set in
        #    create_video_button); nothing pins a maximum any more, so
        #    captions like "Diagnostics" and "Select (5)" stop
        #    truncating and Start/Stop's setFixedWidth(150) finally
        #    takes effect.
        #
        # 3) Explicit colors for QRadioButton/QCheckBox text and the
        #    QProgressBar groove. The old sheet styled only some widget
        #    types; anything unstyled inherited the platform palette,
        #    which on dark-mode Windows 11 rendered the "Render Once" /
        #    "Render All Variants" labels white-on-white and the worker
        #    progress grooves near-black (UI-19, screenshot 2026-06-10).
        #
        # Also: [delete="true"] gains an explicit :disabled state. The
        # old cascade declared the red rule AFTER :disabled at equal
        # specificity, so a disabled Stop button stayed red and looked
        # clickable while the enabled path was gray (UI-18).
        self.setStyleSheet("QMainWindow { background-color: #f8f9fa; }")
        self.centralWidget().setObjectName("central_root")
        self.centralWidget().setStyleSheet(
            """
            QWidget#central_root { background-color: #f8f9fa; }
            QFrame#top_frame, QFrame#bottom_frame {
                background-color: transparent; border: none;
            }
            QFrame#input_frame, QFrame#config_frame, QFrame#progress_frame,
            QFrame#output_frame, QFrame#mode_frame {
                background-color: white; border: 2px solid #dee2e6;
                border-radius: 8px;
            }
            QFrame#progress_info_frame {
                background-color: #e3f2fd;
                border: 1px solid #bbdefb;
                border-radius: 4px;
            }
            QFrame#canvas { background-color: #f0f0f0; border: none; }
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton[toolbar="true"] { min-width: 100px; }
            QPushButton:hover { background-color: #0056b3; }
            QPushButton:disabled { background-color: #6c757d; }
            QPushButton[delete="true"] { background-color: #dc3545; }
            QPushButton[delete="true"]:hover { background-color: #c82333; }
            QPushButton[delete="true"]:disabled { background-color: #6c757d; }
            QTreeWidget {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                background-color: white;
                alternate-background-color: #f8f9fa;
                color: #212529;
            }
            QTreeWidget::item {
                padding: 2px;
                border-bottom: 1px solid #dee2e6;
                height: 25px;
                min-height: 25px;
                color: #212529;
                background-color: transparent;
            }
            QTreeWidget::item:selected {
                background-color: #007bff;
                color: white;
            }
            QHeaderView::section {
                background-color: #e3f2fd;
                padding: 2px;
                border: 1px solid #bbdefb;
                font-weight: bold;
                text-align: center;
                color: #1976d2;
                height: 25px;
            }
            QProgressBar {
                background-color: #ffffff;
                border: 1px solid #dee2e6;
                border-radius: 2px;
                text-align: center;
                height: 15px;
                color: #212529;
            }
            QProgressBar::chunk { background-color: #007bff; }
            QTextEdit {
                background-color: black;
                color: white;
                font-family: Consolas, Menlo, monospace;
                border-radius: 4px;
                border: 2px solid #1976d2;
                padding: 5px;
            }
            QLabel {
                color: #1976d2;
                font-weight: bold;
                padding: 5px;
            }
            QRadioButton, QCheckBox { color: #212529; }
            QComboBox {
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 2px 4px;
                background-color: white;
                color: #212529;
                font-size: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                color: #212529;
                selection-background-color: #007bff;
                selection-color: white;
            }
            QComboBox:hover { border: 1px solid #80bdff; }
            QComboBox:focus { border: 1px solid #80bdff; outline: none; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox::down-arrow {
                width: 12px; height: 12px; margin-right: 5px;
            }
            QSpinBox {
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 5px;
                background-color: white;
                color: #212529;
            }
            QSpinBox:hover { border: 1px solid #80bdff; }
            QSpinBox:focus { border: 1px solid #80bdff; outline: none; }
            QLineEdit {
                background-color: white;
                color: #212529;
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 4px;
            }
            """
        )

    def _check_dependencies(self) -> None:
        """Kiểm tra sự tồn tại của FFmpeg và FFprobe"""
        if not self.FFMPEG_PATH.is_file():
            QMessageBox.critical(
                self,
                "Error",
                f"FFmpeg not found at {self.FFMPEG_PATH}. Please ensure FFmpeg is in the 'ffmpeg' directory.",
            )
            sys.exit(1)
        if not self.FFPROBE_PATH.is_file():
            QMessageBox.critical(
                self,
                "Error",
                f"FFprobe not found at {self.FFPROBE_PATH}. Please ensure FFprobe is in the 'ffmpeg' directory.",
            )
            sys.exit(1)

    def _init_gpu_status_bar(self) -> None:
        """Show NVENC capability in the main window's status bar.

        Clickable: double-click opens a detailed diagnostic dialog. Colored
        so GPU-available state is visually distinct from CPU-only fallback.
        """
        status = gpu_detect.format_status(self.gpu_caps)
        bar = self.statusBar()
        self._gpu_status_label = QLabel(status)
        # Polish batch (UI-12): hand cursor signals the double-click
        # affordance; the tooltip below already explains it.
        self._gpu_status_label.setCursor(Qt.PointingHandCursor)
        self._gpu_status_label.setToolTip(
            "Double-click for full GPU / NVENC diagnostic report"
        )
        if self.gpu_caps.nvenc_available:
            self._gpu_status_label.setStyleSheet("color: #2e7d32; padding: 2px 6px;")
        else:
            self._gpu_status_label.setStyleSheet("color: #777; padding: 2px 6px;")
        bar.addPermanentWidget(self._gpu_status_label)
        self._gpu_status_label.mouseDoubleClickEvent = self._show_gpu_report

    def _show_gpu_report(self, _event) -> None:
        """Popup the detailed GPU diagnostic report."""
        report = gpu_detect.format_detailed_report(self.gpu_caps)
        dlg = QMessageBox(self)
        dlg.setWindowTitle("GPU Detection Report")
        dlg.setIcon(QMessageBox.Information)
        dlg.setText(report)
        dlg.setStyleSheet("QLabel { font-family: Consolas, monospace; }")
        dlg.exec()

    def load_config(self) -> Dict[str, Any]:
        """Tải cấu hình từ config_video_renderer.json nếu tồn tại.

        Phase 2d follow-up fix (Item 3): the previous implementation only
        caught `json.JSONDecodeError` from the validation open(), so an
        OSError (locked file, permission denied, network drive offline)
        would propagate out of __init__ and crash startup. It also read
        the file twice (once to validate, once via core_config.load).

        New flow: read once directly, catch the same two error classes
        core_config.load handles (JSONDecodeError + OSError), and show
        the user-facing warning only on actual failure. On success
        return the parsed dict; otherwise return {} so downstream
        `cfg.get(key, default)` lookups still resolve cleanly.
        """
        path = Path(self.CONFIG_FILE)
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            QMessageBox.warning(
                self,
                "Error",
                "Configuration file is corrupted or unreadable. "
                "Loading default settings.",
            )
            return {}

    def open_settings(self) -> None:
        """Open the Settings dialog modally and apply changes on OK."""
        from PySide6.QtWidgets import QDialog

        dlg = SettingsDialog(self, Path(self.CONFIG_FILE))
        if dlg.exec() == QDialog.Accepted:
            self._reload_config_settings()

    def _reload_config_settings(self) -> None:
        """Reload config_video_renderer.json and apply runtime-changeable bits.

        B-014 partial fix: the original implementation rewired only
        output_collision + gpu_error_action. This now also rewires the 5 GPU
        Pipeline keys (gpu_enabled, gpu_codec, gpu_preset, gpu_max_quality_mode,
        gpu_max_concurrent) so Settings dialog OK takes effect on next render
        without an app restart. num_threads, show_ffmpeg_command, and
        open_output_when_done are still NOT rewired here — they are read
        elsewhere (render-start or app-init); see BACKLOG B-014 for the
        remaining surface.

        Semaphore rebuild: QSemaphore(N) is constructed once in __init__ at
        the initial gpu_max_concurrent and is passed by reference to every
        RenderWorker at submit time. If concurrency changes, we replace
        self._gpu_semaphore so new renders get the new gate size. Workers
        already mid-flight retain their reference to the old semaphore and
        continue using its original cap (we do not re-gate in-flight encodes).
        """
        cfg = core_config.load(Path(self.CONFIG_FILE), default={})
        _d = core_config.APP_DEFAULTS
        # Output / error-handling keys (pre-existing wiring).
        self.output_collision = cfg.get("output_collision", _d.output_collision)
        self.gpu_error_action = cfg.get("gpu_error_action", _d.gpu_error_action)

        # GPU Pipeline tab — 5 keys newly added in this commit. Defaults
        # below come from AppDefaults (same singleton consulted in __init__),
        # so a missing key reverts to the same value the app started with.
        self.gpu_enabled = cfg.get("gpu_enabled", _d.gpu_enabled)
        self.gpu_codec = cfg.get("gpu_codec", _d.gpu_codec)
        self.gpu_preset = cfg.get("gpu_preset", _d.gpu_preset)
        self.gpu_max_quality_mode = cfg.get("gpu_max_quality_mode", False)
        new_concurrent = cfg.get("gpu_max_concurrent", _d.gpu_max_concurrent)
        if new_concurrent != self.gpu_max_concurrent:
            self.gpu_max_concurrent = new_concurrent
            self._gpu_semaphore = QSemaphore(self.gpu_max_concurrent)

        # Phase 3.1 — propagate queue-save toggle into the in-memory
        # config dict so _queue_persistence_enabled() picks up the
        # change without an app restart. The persisted JSON is the
        # single source of truth; this just keeps the cached copy in
        # sync after a Settings OK.
        self.config["queue_persistence_enabled"] = cfg.get(
            "queue_persistence_enabled", True
        )
        # Phase 3.2 — propagate scoring settings without restart.
        # auto-scoring + axes selection + parallelism are all read
        # via _auto_scoring_enabled / _scoring_default_axes /
        # _scoring_max_parallel which consult self.config at call
        # time, so a Settings OK takes effect on the next render.
        self.config["scoring_auto_enabled"] = cfg.get("scoring_auto_enabled", False)
        self.config["scoring_default_axes"] = cfg.get(
            "scoring_default_axes", ["vmaf", "phash"]
        )
        self.config["scoring_max_parallel"] = cfg.get("scoring_max_parallel", 1)
        self.config["scoring_phash_frames"] = cfg.get("scoring_phash_frames", 20)

        # B-014 closure: re-read the remaining 3 keys that previously
        # required an app restart. These are read on the next render
        # dispatch (start_render reads num_threads at task-build time;
        # show_ffmpeg_command + open_output_when_done are read at the
        # render-complete callback), so propagating them into the
        # in-memory config + the corresponding self.* attribute is
        # enough to make Settings OK take effect immediately. The new
        # num_threads value applies to the NEXT batch — an in-flight
        # batch keeps its dispatch fan-out unchanged.
        # num_threads is not in AppDefaults; fall back to the historical
        # default of 3 to match settings_dialog DEFAULTS.
        new_threads = int(cfg.get("num_threads", 3) or 3)
        self.config["num_threads"] = new_threads
        try:
            self.num_threads = new_threads
        except Exception:
            pass
        self.config["show_ffmpeg_command"] = bool(cfg.get("show_ffmpeg_command", True))
        self.config["open_output_when_done"] = bool(
            cfg.get("open_output_when_done", False)
        )
        # NVENC quality offset is baked into preset_translator
        # (-crf N -> -cq N+offset) per ADR-0007 D3 / ADR-0008.

    def _update_empty_hints(self):
        """Toggle the empty-state placeholders based on current state."""
        if hasattr(self, "empty_videos_hint"):
            self.empty_videos_hint.setVisible(not self.videos)
        if hasattr(self, "empty_slots_hint"):
            any_slot_filled = any(c.currentText() for c in self.sequential_combos)
            self.empty_slots_hint.setVisible(
                self.sequential_mode and not any_slot_filled
            )

    def _on_slot_text_changed(self, _text):
        """A sequential combo's selection changed - refresh hints + Start state."""
        self._update_empty_hints()
        self._update_start_button_state()
        self._update_slot_clear_buttons()

    def _update_slot_clear_buttons(self):
        """Show a slot's X button only when that slot has a preset selected."""
        if not hasattr(self, "sequential_clear_btns"):
            return
        for combo, btn in zip(self.sequential_combos, self.sequential_clear_btns):
            btn.setVisible(bool(combo.currentText()))

    def _sync_delete_enabled(self):
        """Polish batch (UI-13): Step 1 Delete enabled only with a selection."""
        self.btn_delete.setEnabled(bool(self.tree_videos.selectedItems()))

    def _update_start_button_state(self):
        """Disable Start unless videos, a preset, and a valid output dir are all present."""
        if not hasattr(self, "btn_start"):
            return
        if self.is_rendering:
            return
        if not self.videos:
            self.btn_start.setEnabled(False)
            self.btn_start.setToolTip("Add videos first")
            return
        if self.sequential_mode:
            has_preset = any(c.currentText() for c in self.sequential_combos)
        else:
            has_preset = bool(self.tree_encoders.selectedItems())
        if not has_preset:
            self.btn_start.setEnabled(False)
            self.btn_start.setToolTip("Pick a preset first")
            return
        if not self.output_directory or not os.path.isdir(self.output_directory):
            self.btn_start.setEnabled(False)
            self.btn_start.setToolTip("Choose output folder first")
            return
        self.btn_start.setEnabled(True)
        self.btn_start.setToolTip("Begin rendering (F5)")

    def _apply_slot_defaults(self):
        """Restore X-Render slot selections from config_video_renderer.json on startup.

        Phase 2d follow-up fix (Item 5): new configs persist preset
        IDs as combo userData. Legacy configs persisted display
        names (combo text). Try the ID match first (collision-proof);
        if it fails, fall back to text match so a saved-before-the-fix
        config still loads, then save_config will rewrite it as IDs
        on the next clean exit.
        """
        slots = self.config.get("sequential_slots", [])
        if not slots:
            return
        for i, slot_value in enumerate(slots):
            if i >= SEQUENTIAL_SLOT_COUNT:
                break
            if not slot_value:
                continue
            combo = self.sequential_combos[i]
            idx = combo.findData(slot_value)
            if idx < 0:
                idx = combo.findText(slot_value)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def save_config(self) -> None:
        """Lưu cấu hình vào config_video_renderer.json."""
        try:
            # Merge-then-write per PORT_NOTES line 112-116: load existing config first
            # so SettingsDialog-managed keys (output_collision, gpu_error_action, etc.)
            # are NOT wiped when main window saves its own state.
            existing = core_config.load(Path(self.CONFIG_FILE), default={})
            # Phase 2d follow-up fix (Item 5): both selection keys now
            # persist preset IDs (stable, unique) instead of display
            # names (ambiguous when 13 known (group,name) collisions
            # exist in the library). _apply_slot_defaults reads back
            # via findData() first and falls back to findText() so
            # configs written by older versions still load cleanly.
            existing.update(
                {
                    "input_files": self.videos,
                    "output_dir": self.output_directory,
                    "encoder_options": self.selected_encoders,
                    "num_threads": self.num_threads,
                    "sequential_slots": [
                        (c.currentData() or "") for c in self.sequential_combos
                    ],
                }
            )
            core_config.save(Path(self.CONFIG_FILE), existing)
        except (OSError, TypeError) as e:
            QMessageBox.warning(
                self, "Error", f"Failed to save configuration: {str(e)}"
            )

    def load_encoder_options(self) -> List[core_preset_loader.Preset]:
        """Đọc các tùy chọn render từ file Encoder.txt và bỏ qua các dòng lỗi."""
        if os.environ.get("ENCODER_USE_JSON") == "1":
            # Dark-release path (sub-phase 2c-c-1).
            # assets/Encoder.json already contains the 2 Text defaults
            # (appended by tools/generate_encoder_json.py); do NOT re-append.
            encoder_json_path = self.SCRIPT_DIR / "assets" / "Encoder.json"
            # Fail-soft, mirroring the Encoder.txt path below: a corrupt or
            # schema-mismatched Encoder.json must not crash startup.
            # load_builtin_json can raise json.JSONDecodeError (a ValueError
            # subclass), ValueError, OSError, or pydantic.ValidationError
            # (NOT a ValueError subclass — caught explicitly).
            import logging

            from pydantic import ValidationError

            try:
                presets = core_preset_loader.load_builtin_json(encoder_json_path)
            except (ValueError, OSError, ValidationError) as e:
                logging.getLogger(__name__).warning(
                    "Failed to load built-in presets from %s (%s: %s); "
                    "degrading to empty built-in list so the app still starts.",
                    encoder_json_path,
                    type(e).__name__,
                    e,
                )
                presets = []
        else:
            presets = core_preset_loader.load_presets(self.ENCODER_FILE)
            # App-specific defaults appended after file load — these are
            # auto_render's own UI affordances, not part of Encoder.txt.
            # 2c-c-4: ids match those hardcoded in tools/generate_encoder_json.py
            # so the legacy txt+append path produces same identities as the
            # JSON dark-release path.
            presets.append(
                core_preset_loader.Preset(
                    id="builtin:text/text-bottom-basic",
                    group="Text",
                    name="Text Bottom Basic",
                    description="Add text at the bottom on a translucent black background",
                    details="Adds text at the bottom of the video on a translucent black background, Arial font, 35px",
                    params=(
                        "-vf",
                        "drawtext=fontfile=Arial:text='REPLACE_THIS_TEXT':x=(w-text_w)/2:y=(h-text_h)/1.05:fontsize=35:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=10",
                    ),
                )
            )
            presets.append(
                core_preset_loader.Preset(
                    id="builtin:text/text-top-basic",
                    group="Text",
                    name="Text Top Basic",
                    description="Add text at the top on a translucent black background",
                    details="Adds text at the top of the video on a translucent black background, Arial font, 35px",
                    params=(
                        "-vf",
                        "drawtext=fontfile=Arial:text='REPLACE_THIS_TEXT':x=(w-text_w)/2:y=(h-text_h)/15:fontsize=35:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=10",
                    ),
                )
            )
        # 2c-c-4: built-in vs user is intrinsic via id prefix; no
        # _builtin_preset_count needed.
        user_presets = load_user_presets_json(self.USER_PRESETS_FILE)
        if user_presets:
            presets.extend(user_presets)
        return presets

    def _on_start_shortcut(self):
        """F5 shortcut handler - only fires if start button is enabled (per Phase 1 contract)."""
        if self.btn_start.isEnabled():
            self.start_render()

    def _on_stop_shortcut(self):
        """Esc shortcut handler - only fires if cancel button is enabled (per Phase 1 contract)."""
        if self.btn_cancel.isEnabled():
            self.cancel_render()

    def _url_thread_is_running(self) -> bool:
        """Safely test whether the URL download thread is alive and running.

        Phase 2d follow-up fix (Issue 6 — stale QThread RuntimeError):
        after a URL batch completes, the chain
            worker.finished → thread.quit → thread.finished →
            worker.deleteLater + thread.deleteLater
        destroys the underlying C++ QThread while `self._url_thread`
        still holds a Python wrapper. The next time the user clicks
        Add URL, a bare `self._url_thread.isRunning()` raises
        `RuntimeError("Internal C++ object (PySide6.QtCore.QThread)
        already deleted")`, taking down the button and stranding the
        user until app restart.

        This helper:
          - returns False if the ref was never set;
          - swallows the RuntimeError if the C++ object is gone,
            nulls both refs, returns False;
          - if the thread exists but already finished, nulls the
            refs and returns False;
          - otherwise returns True.

        Callers (add_url, closeEvent) get a simple boolean and can
        trust that `False` means "safe to start a new batch".
        """
        t = getattr(self, "_url_thread", None)
        if t is None:
            return False
        try:
            running = t.isRunning()
        except RuntimeError:
            # Underlying C++ object already deleted (deleteLater
            # processed by the event loop); release the Python ref so
            # subsequent calls see a clean state.
            self._url_thread = None
            self._url_worker = None
            return False
        if not running:
            # Thread object alive but already finished; consume the
            # stale ref so the next batch starts clean.
            self._url_thread = None
            self._url_worker = None
            return False
        return True

    def _on_url_thread_finished(self) -> None:
        """Null out URL thread/worker refs once the thread is done.

        Phase 2d follow-up fix (Issue 6). Connected to
        `_url_thread.finished` ALONGSIDE the existing deleteLater
        connections so the Python references are released
        deterministically — independent of when Qt actually processes
        the deleteLater queue. After this slot fires,
        `_url_thread_is_running()` returns False via the cheap
        `t is None` path without needing to swallow a RuntimeError.
        """
        self._url_thread = None
        self._url_worker = None

    def _on_url_cancel_clicked(self) -> None:
        """User clicked Cancel on the URL download progress dialog.

        Phase 2d follow-up fix (Issue 4 — cancel/download
        synchronization): the previous wiring connected
        `canceled` directly to `worker.cancel()`. The download
        winds down asynchronously (yt-dlp must observe the
        cancel_event), so the dialog kept its previous label and
        an enabled Cancel button while doing nothing visible —
        users perceived it as frozen or interpreted a second
        click as the "real" cancel. We now:
          - call worker.cancel() exactly once, guarded against a
            deleted worker;
          - relabel the progress dialog to "Cancelling, please
            wait…" so the wind-down is visible;
          - disable the Cancel button to prevent duplicate fires.
        The dialog is closed by `_on_url_finished` / `_on_url_error`
        once the worker emits its terminal signal.
        """
        # Polish batch (UI-11): block _on_url_progress from overwriting
        # the "Cancelling…" label until the batch terminates.
        self._url_cancel_requested = True
        worker = getattr(self, "_url_worker", None)
        if worker is not None:
            try:
                worker.cancel()
            except RuntimeError:
                # Worker already deleted; nothing to cancel.
                pass
        dlg = getattr(self, "_url_progress", None)
        if dlg is not None:
            try:
                dlg.setLabelText("Cancelling, please wait…")
                dlg.setCancelButton(None)
            except RuntimeError:
                pass

    def add_url(self):
        """Open the URL input dialog and download the selected URLs.

        On success, downloaded file paths are appended to `self.videos` and
        `update_video_list()` is called — making them indistinguishable from
        locally-picked files. Failures are summarized in a follow-up modal.

        Storage location: `USER_DATA_DIR / "url_downloads/"` (auto-created).
        Threading: download runs on a QThread; UI is unblocked.

        Concurrency guard: only one URL download batch can run at a time.
        The Add URL button is disabled while a batch is in flight and
        re-enabled in `_on_url_finished` / `_on_url_error`. A defensive
        QMessageBox covers the case where the guard is bypassed (e.g. a
        keyboard shortcut wired straight to this slot).
        """
        # Phase 2d follow-up fix (Issue 6): use the safe helper so a
        # stale (already-deleted) _url_thread cannot raise RuntimeError.
        if self._url_thread_is_running():
            QMessageBox.information(
                self,
                "URL download",
                "A URL download is already in progress. "
                "Please wait for it to finish or press Cancel on the progress dialog.",
            )
            return
        try:
            dlg = URLInputDialog(self)
            if dlg.exec() != QDialog.Accepted:
                return
            values = dlg.values()
            if not values["urls"]:
                return

            work_dir = Path(self.USER_DATA_DIR) / "url_downloads"
            try:
                work_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.critical(
                    self,
                    "URL download",
                    f"Cannot create download folder {work_dir}: {exc}",
                )
                return

            # Spawn worker on a QThread (matches RenderWorker pattern used
            # elsewhere in this app).
            self._url_thread = QThread()
            self._url_worker = URLDownloadWorker(
                urls=values["urls"],
                work_dir=work_dir,
                quality=values["quality"],
                download_subtitles=values["download_subtitles"],
                max_concurrent=values["max_concurrent"],
            )
            self._url_worker.moveToThread(self._url_thread)
            self._url_thread.started.connect(self._url_worker.run)
            self._url_worker.progress.connect(self._on_url_progress)
            self._url_worker.finished.connect(self._on_url_finished)
            self._url_worker.error_message.connect(self._on_url_error)
            self._url_worker.finished.connect(self._url_thread.quit)
            self._url_worker.error_message.connect(self._url_thread.quit)
            # Phase 2d follow-up fix (Issue 6 — stale QThread): release
            # Python references when the thread reports finished, BEFORE
            # deleteLater frees the C++ objects. Order of connections
            # matters less than presence — Qt invokes them in connect-
            # order on the main thread, and _on_url_thread_finished only
            # sets attributes to None (no C++ access).
            self._url_thread.finished.connect(self._on_url_thread_finished)
            self._url_thread.finished.connect(self._url_worker.deleteLater)
            self._url_thread.finished.connect(self._url_thread.deleteLater)

            # Non-modal progress dialog with Cancel. The internal worker
            # state advances independently; we surface a coarse bar showing
            # "completed-URL count / total" and the last per-URL line in
            # the label. Cancel sets the worker's cancel_event.
            n_urls = len(values["urls"])
            self._url_progress = QProgressDialog(
                # Phase 2d follow-up fix (Issue 3 — perceived delayed
                # start): initial label is honest about the silent
                # warm-up phase. yt-dlp probes site metadata before any
                # bytes flow, so 0% sticking for a few seconds is
                # normal — we tell the user that up front.
                "Preparing yt-dlp (initial response may take a moment)…",
                "Cancel",
                # Phase 2d production-hardening fix (Issue 5 — URL
                # progress bar misleading): range is 0-100 (percent of
                # the OVERALL batch). Each URL's downloading-percent
                # contributes 1/n_urls of that scale, and each finished
                # URL bumps the bar by 100/n_urls. Previously the bar
                # max was n_urls so it only moved at all-or-nothing
                # boundaries while the label said "95%" — single-URL
                # downloads appeared frozen at 0%. New scale is honest:
                # bar tracks the same number the label shows.
                0,
                100,
                self,
            )
            self._url_progress.setWindowTitle("Downloading URLs")
            self._url_progress.setWindowModality(Qt.NonModal)
            self._url_progress.setMinimumDuration(0)
            self._url_progress.setValue(0)
            # Phase 2d follow-up fix (Issue 4 — cancel synchronization):
            # route Cancel through a wrapper that also updates the
            # dialog label and disables the button, so the wind-down
            # phase is visible.
            self._url_progress.canceled.connect(self._on_url_cancel_clicked)
            # Internal completion tally (since the worker's `progress`
            # signal reports per-URL percentages, not batch position).
            self._url_finished_count = 0
            self._url_total_count = n_urls
            # Polish batch (UI-11): fresh batch, clear any stale cancel.
            self._url_cancel_requested = False

            self.update_ffmpeg_output(
                f"\n[URL] Starting batch of {n_urls} URL(s) "
                f"(quality={values['quality']}, "
                f"subs={'yes' if values['download_subtitles'] else 'no'}, "
                f"max_concurrent={values['max_concurrent']}) -> {work_dir}\n"
            )
            # Disable the Add URL button before starting; re-enabled in
            # _on_url_finished / _on_url_error. The reciprocal guard at the
            # top of this method covers shortcut-driven re-entry.
            if hasattr(self, "add_url_btn") and self.add_url_btn is not None:
                self.add_url_btn.setEnabled(False)
            self._url_thread.start()
            # Phase 2d follow-up fix (Issue 3): force the progress
            # dialog + output panel to repaint immediately so the user
            # sees the "Preparing yt-dlp…" message before the worker
            # thread does its first slow probe call. processEvents() is
            # safe here because we have just finished mutating UI state
            # and are about to return to the event loop.
            QApplication.processEvents()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot open URL dialog: {str(e)}")

    @Slot(int, str, float, str)
    def _on_url_progress(self, idx: int, url: str, pct: float, status: str) -> None:
        """Per-URL progress callback from URLDownloadWorker (main thread).

        Phase 2d production-hardening fix (Issue 5): the QProgressDialog
        now has a 0-100 range and we feed it the OVERALL batch percent
        — `(finished * 100 + current_pct) / n_urls` — so the bar tracks
        the same number the label shows. Single-URL batches see the
        bar move from 0 → 100 smoothly instead of jumping from 0 to
        100 at the finished signal. Multi-URL batches see the bar
        accumulate one URL's share at a time, with intra-URL progress
        adding fractional movement within that slice.
        """
        # Polish batch (UI-11): after Cancel, the wind-down still emits
        # progress; do not overwrite the "Cancelling…" label or bar.
        if self._url_cancel_requested:
            return
        total = max(1, self._url_total_count)
        if status == "downloading":
            self.update_ffmpeg_output(f"[URL {idx + 1}] {pct:5.1f}%  {url}\n")
            # Update the dialog label + bar with the in-flight URL.
            if hasattr(self, "_url_progress") and self._url_progress is not None:
                shortened = (url[:60] + "…") if len(url) > 60 else url
                self._url_progress.setLabelText(
                    f"Downloading {idx + 1}/{total}: {shortened}  ({pct:.0f}%)"
                )
                overall_pct = int((self._url_finished_count * 100 + pct) / total)
                # Clamp into the bar's 0-100 range as belt-and-suspenders
                # — pct comes from yt-dlp's downloader and should already
                # be in 0..100, but a future regression at the source
                # cannot break the bar widget.
                self._url_progress.setValue(max(0, min(100, overall_pct)))
        elif status == "finished":
            self.update_ffmpeg_output(f"[URL {idx + 1}] done    {url}\n")
            if hasattr(self, "_url_progress") and self._url_progress is not None:
                self._url_finished_count += 1
                overall_pct = int(self._url_finished_count * 100 / total)
                self._url_progress.setValue(max(0, min(100, overall_pct)))

    @Slot(list)
    def _on_url_finished(self, results: list) -> None:
        """Batch complete: append successful paths to self.videos."""
        # Polish batch (UI-11): batch is over; clear the cancel latch.
        self._url_cancel_requested = False
        # Close the progress dialog before showing the summary modal.
        if hasattr(self, "_url_progress") and self._url_progress is not None:
            # Phase 2d production-hardening fix (Issue 5): dialog max is
            # now 100 (percent of batch). Setting to 100 visually
            # completes the bar regardless of which URLs succeeded or
            # were cancelled — the per-URL outcomes are surfaced in the
            # summary modal below.
            self._url_progress.setValue(100)
            self._url_progress.close()
            self._url_progress = None

        # Re-enable Add URL once the batch is fully done (paired with the
        # disable inside add_url; covers cancel + success + per-URL failures).
        if hasattr(self, "add_url_btn") and self.add_url_btn is not None:
            self.add_url_btn.setEnabled(True)

        succeeded = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        new_paths = []
        for r in succeeded:
            if r.path is None:
                continue
            p = str(r.path)
            if p not in self.videos:
                new_paths.append(p)

        if new_paths:
            self.videos.extend(new_paths)
            self.update_video_list()
            self.update_ffmpeg_output(
                f"\n[URL] Added {len(new_paths)} downloaded video(s) to the queue.\n"
            )

        # Build a short summary modal.
        summary_lines = [
            f"Downloaded {len(succeeded)}/{len(results)} URL(s) successfully.",
        ]
        if failed:
            summary_lines.append("")
            summary_lines.append("Failed URLs:")
            for r in failed:
                summary_lines.append(f"  - {r.url}  ({r.error_type or 'unknown'})")
        QMessageBox.information(self, "URL download", "\n".join(summary_lines))

    @Slot(str)
    def _on_url_error(self, message: str) -> None:
        """Hard failure during batch (argument validation, etc.)."""
        # Polish batch (UI-11): batch is over; clear the cancel latch.
        self._url_cancel_requested = False
        # Close the progress dialog so the user can see the modal cleanly.
        if hasattr(self, "_url_progress") and self._url_progress is not None:
            self._url_progress.close()
            self._url_progress = None
        # Re-enable Add URL on hard failure (paired with the disable inside
        # add_url; otherwise the button would be stuck off after a fatal error).
        if hasattr(self, "add_url_btn") and self.add_url_btn is not None:
            self.add_url_btn.setEnabled(True)
        QMessageBox.critical(self, "URL download", message)

    def select_videos(self):
        """Chọn nhiều video từ thư mục đầu vào."""
        try:
            initial_dir = (
                os.path.dirname(self.videos[0]) if self.videos else os.getcwd()
            )
            file_paths = core_file_picker.pick_files(
                self, "Select Videos", initial_dir, core_file_picker.VIDEO_FILTER
            )
            if file_paths:
                new_files = [fp for fp in file_paths if fp not in self.videos]
                if not new_files:
                    QMessageBox.information(self, "Info", "No new videos were added.")
                    return
                self.videos.extend(new_files)
                self.update_video_list()
                logger.info(f"Added {len(new_files)} videos.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot select videos: {str(e)}")

    def update_video_list(self):
        """Cập nhật danh sách video.

        Phase 2d follow-up fix (Issues 2 + 5 — blank-row repaint):
        on macOS, Qt batches paint events while the main thread is
        busy in a tight loop, so freshly-inserted QTreeWidgetItems
        could appear blank until the user clicked one of them. Each
        ffprobe call below now yields the event loop with
        QApplication.processEvents() so the row paints incrementally,
        and a final viewport().update() forces a definitive redraw
        after the loop completes. Tooltip on column 1 carries the
        full path so the truncated basename is still recoverable.
        """
        self.tree_videos.clear()
        for idx, video_path in enumerate(self.videos, start=1):
            item = QTreeWidgetItem(self.tree_videos)
            item.setText(0, str(idx))
            item.setText(1, os.path.basename(video_path))
            item.setToolTip(1, video_path)
            try:
                duration = self.get_video_duration(video_path)
                item.setText(2, duration)
                resolution = self.get_video_resolution(video_path)
                item.setText(3, resolution)
            except Exception as e:
                item.setText(2, "—")
                item.setText(3, "—")
                logger.error(f"Error getting video info for {video_path}: {str(e)}")
            # Yield to the event loop so this row paints before the
            # next ffprobe call blocks. Safe — we are between rows,
            # not mid-mutation of a single item.
            QApplication.processEvents()
        select_btn = self.findChild(QPushButton, "select_btn")
        if select_btn:
            select_btn.setText(f"📥 Select ({len(self.videos)})")
        # Final belt-and-suspenders refresh in case Qt still cached
        # the last paint pass.
        self.tree_videos.viewport().update()
        self._update_empty_hints()
        self._update_start_button_state()

    def get_video_duration(self, video_path: str) -> str:
        """Lấy thời lượng video sử dụng FFprobe.

        Phase 2d follow-up fix (Item 6): adds a finite timeout to
        subprocess.run so a hung ffprobe (corrupt file, stalled network
        mount, antivirus quarantine) cannot freeze the UI indefinitely.
        ffprobe metadata extraction on a single file should complete in
        well under 10s; on TimeoutExpired we return the existing "—"
        placeholder, identical to the empty-stdout / non-zero-rc branch.
        """
        command = [
            str(self.FFPROBE_PATH),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        try:
            startupinfo = core_ffmpeg_runner.hidden_startupinfo()
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                creationflags=core_ffmpeg_runner.hidden_creationflags(),
                timeout=10,
            )
            # Defensive parse per Step 4d-fix-1: ffprobe may return empty stdout
            # if file is still being finalized, codec metadata is missing, or
            # ffprobe itself failed. Return placeholder rather than crashing the
            # render-completion handler. Non-zero returncode also returns placeholder.
            stdout_stripped = result.stdout.strip()
            if result.returncode != 0 or not stdout_stripped:
                return "—"
            try:
                duration_seconds = float(stdout_stripped)
            except ValueError:
                return "—"
            hours = int(duration_seconds // 3600)
            minutes = int(duration_seconds % 3600 // 60)
            seconds = int(duration_seconds % 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except subprocess.TimeoutExpired:
            logger.error(f"ffprobe duration timed out (>10s) for: {video_path}")
            return "—"
        except Exception:
            # Belt-and-suspenders: never crash the caller even on subprocess failure.
            return "—"

    def get_video_resolution(self, video_path: str) -> str:
        """Lấy độ phân giải video sử dụng FFprobe.

        Phase 2d follow-up fix (Item 6): same finite-timeout treatment as
        get_video_duration. On TimeoutExpired we return "—" (the same
        placeholder the existing exception branch returns) so the tree
        row still renders cleanly.
        """
        command = [
            str(self.FFPROBE_PATH),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            video_path,
        ]
        try:
            startupinfo = core_ffmpeg_runner.hidden_startupinfo()
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                creationflags=core_ffmpeg_runner.hidden_creationflags(),
                timeout=10,
            )
            return result.stdout.strip() or "—"
        except subprocess.TimeoutExpired:
            logger.error(f"ffprobe resolution timed out (>10s) for: {video_path}")
            return "—"
        except Exception as e:
            logger.error(f"Failed to get video resolution: {str(e)}")
            return "—"

    def delete_videos(self):
        """Xóa các video đã chọn."""
        try:
            selected_items = self.tree_videos.selectedItems()
            if not selected_items:
                QMessageBox.information(self, "Info", "No videos selected to delete.")
                return
            indices = []
            for item in selected_items:
                idx = int(item.text(0)) - 1
                indices.append(idx)
            for idx in sorted(indices, reverse=True):
                self.videos.pop(idx)
            self.update_video_list()
            if not self.videos:
                self.btn_delete.setEnabled(False)
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Cannot delete selected videos: {str(e)}"
            )

    def select_output_directory(self):
        """Chọn thư mục đầu ra."""
        try:
            output_dir = core_file_picker.pick_directory(
                self, "Select Output Directory", self.output_directory or os.getcwd()
            )
            if output_dir:
                self.output_directory = output_dir
                self._set_output_dir_label(self.output_directory)
                self._update_start_button_state()
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Cannot select output directory: {str(e)}"
            )

    def _layout_progress_boxes(self):
        # The boxes grid is now inside a QScrollArea (see setup_ui).
        # This prevents the top-left box area from becoming too compact/squished on small
        # windows or with many tasks. Boxes stay at a comfortable size; scrollbar appears
        # automatically. Design (colors, borders, rounded look) is identical to before.
        target_box = self.box_size  # 15px base for normal look
        # Use the scroll viewport width if available for deciding columns (responsive)
        if hasattr(self, "boxes_scroll") and self.boxes_scroll:
            avail_w = max(80, self.boxes_scroll.viewport().width())
        else:
            avail_w = max(80, self.canvas.width() or 300)
        cell = target_box + self.padding
        self.boxes_per_row = max(1, (avail_w - self.padding) // cell)
        rows_needed = (
            -(-len(self.progress_boxes) // self.boxes_per_row)
            if self.progress_boxes
            else 1
        )
        # Size canvas exactly to the grid content so scroll works correctly
        full_w = self.boxes_per_row * cell + self.padding
        full_h = rows_needed * cell + self.padding
        self.canvas.resize(full_w, full_h)
        for i, box in enumerate(self.progress_boxes):
            box.setGeometry(
                (i % self.boxes_per_row) * cell + self.padding // 2,
                (i // self.boxes_per_row) * cell + self.padding // 2,
                target_box,
                target_box,
            )

    def create_progress_box(self, index: int) -> QFrame:
        """Tạo một progress box."""
        box = QFrame(self.canvas)
        box.setStyleSheet(
            "\n            background-color: lightgray; border: 1px solid #666666; border-radius: 2px;\n        "
        )
        box.show()
        return box

    def update_box_color(self, index: int, color: str):
        """Cập nhật màu của progress box"""
        if 0 <= index < len(self.progress_boxes):
            if color == "green":
                self.progress_boxes[index].setStyleSheet(
                    "\n                    background-color: #4CAF50;\n                    border: 1px solid #2E7D32;\n                    border-radius: 2px;\n                "
                )
            else:
                if color == "yellow":
                    self.progress_boxes[index].setStyleSheet(
                        "\n                    background-color: #FFC107;\n                    border: 1px solid #FFA000;\n                    border-radius: 2px;\n                "
                    )
                else:
                    if color == "red":
                        self.progress_boxes[index].setStyleSheet(
                            "\n                    background-color: #F44336;\n                    border: 1px solid #D32F2F;\n                    border-radius: 2px;\n                "
                        )
                    else:
                        self.progress_boxes[index].setStyleSheet(
                            "\n                    background-color: lightgray;\n                    border: 1px solid #666666;\n                    border-radius: 2px;\n                "
                        )

    def clear_progress_boxes(self):
        """Xóa tất cả progress boxes"""
        for box in self.progress_boxes:
            box.deleteLater()
        self.progress_boxes.clear()

    def start_render(self, *, resume_tasks: Optional[list] = None):
        """Bắt đầu quá trình render."""
        if self.is_rendering:
            reply = QMessageBox.question(
                self,
                "Confirm",
                "A rendering process is already running. Do you want to cancel and start a new one?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.cancel_render()
            else:
                return None
        if not self.validate_inputs():
            return
        # Phase 3.5 lightweight pre-flight gate (advisory only).
        # Classifies the user's currently-selected presets against the
        # gpu_caps snapshot. On BLOCK verdicts, offers a single modal
        # with Cancel / Proceed-Anyway. On WARN, surfaces a non-blocking
        # toast in the output panel. Soft-fails on any internal error —
        # a defective intelligence module must NEVER block a render.
        if not self._encoder_intel_preflight():
            return
        else:
            if resume_tasks is not None:
                # H-1: selection identity travels in resume_tasks as
                # (video_path, encoder_ids, video_idx) tuples built by
                # _resume_batch, which also populated
                # selected_encoders / encoder_params. Skip the UI
                # rebuild — on a fresh launch the tree has no
                # selection and the old code aborted with a "select
                # at least one Encoder" warning AFTER the saved batch
                # had already been cleared. Preflight above sees an
                # empty UI selection and passes through; the batch
                # was preflighted when originally started.
                pass
            elif self.sequential_mode:
                # Phase 2d follow-up fix (Item 5): sequential slot
                # identity is the preset id (stored as combo userData),
                # not the display text. Falsy currentData() means an
                # unset slot — same semantic as the previous empty-string
                # text guard, but now collision-proof for duplicate names.
                self.sequential_encoders = [
                    combo.currentData()
                    for combo in self.sequential_combos
                    if combo.currentData()
                ]
                if not self.sequential_encoders:
                    QMessageBox.warning(
                        self,
                        "Warning",
                        "Please select at least one Encoder in sequential mode.",
                    )
                    return
            else:
                selected_items = self.tree_encoders.selectedItems()
                if not selected_items:
                    QMessageBox.warning(
                        self, "Warning", "Please select at least one Encoder option."
                    )
                    return
                else:
                    # Phase 2d follow-up fix (Item 5): tree-mode
                    # selection is keyed by the stable preset id (stashed
                    # at Qt.UserRole+1 by load_encoders_to_tree per ADR-
                    # 0006), not by the display text at column 2. The
                    # 108-preset library has 13 known (group,name)
                    # collisions; the previous name-keyed dict silently
                    # dropped all but the last colliding selection. Items
                    # without an id (defensive guard — should never
                    # happen after 2c-c-4) are skipped.
                    selected_encoders: list[str] = []
                    encoder_params: dict[str, list[str]] = {}
                    for item in selected_items:
                        preset_id = item.data(0, Qt.UserRole + 1) or ""
                        if not preset_id:
                            continue
                        code = item.data(0, Qt.UserRole).split()
                        selected_encoders.append(preset_id)
                        encoder_params[preset_id] = code
                    if not selected_encoders:
                        QMessageBox.warning(
                            self,
                            "Warning",
                            "Selected presets are missing internal IDs "
                            "(refresh presets and try again).",
                        )
                        return
                    self.selected_encoders = selected_encoders
                    self.encoder_params = encoder_params
            self.is_rendering = True
            self.btn_start.setEnabled(False)
            self.btn_cancel.setEnabled(True)
            if resume_tasks is not None:
                total_tasks = len(resume_tasks)
            elif self.sequential_mode:
                total_tasks = len(self.videos)
            else:
                total_tasks = len(self.videos) * len(self.selected_encoders)
            self.progress_label.setText(
                f"Progress: 0/{total_tasks} renders\nETA: calculating..."
            )
            self.current_label.setText("Currently Rendering: None")
            self.tree_output.clear()
            self.clear_progress_boxes()

            # M-3: regenerate worker rows to match the (possibly changed)
            # num_threads BEFORE the resets below, so the worker-indexed UI
            # (bars/labels/_worker_state) is aligned with the
            # render_threads/render_workers created later in this method.
            self._rebuild_worker_rows(self.num_threads)

            # #1: re-arm the one-time queue-persistence warning for this batch,
            # so a disk issue that cleared between batches can warn again.
            self._queue_persist_warned = False

            # Reset every worker label back to Ready before a new batch begins.
            if hasattr(self, "_worker_state"):
                for idx, st in enumerate(self._worker_state):
                    st["state"] = "idle"
                    st["basename"] = ""
                    st["percent"] = 0
                    st["error"] = ""
                    self._render_worker_label(idx)
            # Phase 2d production-hardening fix (Issue 7): reset the
            # per-worker QProgressBar values too. Without this, bars
            # from the previous batch stayed at their last value
            # (typically full blue) between renders, which looked
            # like the new batch had started already at 100%. Cosmetic
            # but visible in normal use.
            if hasattr(self, "thread_bars"):
                for bar in self.thread_bars:
                    bar.setValue(0)
            for i in range(total_tasks):
                box = self.create_progress_box(i)
                self.progress_boxes.append(box)
            self._layout_progress_boxes()
            self.render_threads = []
            self.render_workers = []
            self.current_task_index = 0
            self.total_tasks = total_tasks
            self.active_threads = 0
            self.completed_tasks = 0
            self.batch_start_time = time.time()
            self.task_durations: list[float] = []
            self.last_task_start_time = self.batch_start_time
            self.all_tasks = []
            if resume_tasks is not None:
                # H-1: the saved batch's per-task pairs, replayed
                # verbatim. Rebuilding videos×presets here would both
                # re-run already-completed pairs and invent pairs the
                # original batch never contained.
                self.all_tasks = [tuple(t) for t in resume_tasks]
            elif self.sequential_mode:
                for video_idx, video_path in enumerate(self.videos):
                    self.all_tasks.append(
                        (video_path, self.sequential_encoders, video_idx)
                    )
            else:
                for video_idx, video_path in enumerate(self.videos):
                    for encoder_idx, encoder_name in enumerate(self.selected_encoders):
                        self.all_tasks.append((video_path, [encoder_name], video_idx))
            # Phase 3.1 — persist a snapshot of the batch BEFORE any
            # worker is dispatched. This guarantees that even if the
            # very first thread.start() crashes the process, the next
            # launch will detect the saved batch and offer a resume
            # prompt. _save_queue_snapshot() is a no-op if the user
            # has disabled queue persistence in settings.
            self._save_queue_snapshot()
            for i in range(self.num_threads):
                thread = QThread()
                self.render_threads.append(thread)
                self.render_workers.append(None)
            # M-4a: a pause flag persisted from a prior session would make
            # every _start_next_task() below no-op at the pause gate, leaving
            # a silently dead batch with Cancel lit. Starting a batch is an
            # explicit "go" — clear any stale pause (and its persisted state)
            # before dispatching.
            if getattr(self, "is_paused", False):
                self._set_paused(False)
            for i in range(min(self.num_threads, total_tasks)):
                self._start_next_task()

    def _start_next_task(self):
        """Khởi chạy task tiếp theo nếu còn."""
        if not self.is_rendering:
            return
        # Phase 3.4 — pause gate. Current task already running on
        # its worker is NOT interrupted; only NEW dispatch waits.
        if getattr(self, "is_paused", False):
            return
        else:
            if self.current_task_index >= len(self.all_tasks):
                if self.completed_tasks < self.total_tasks:
                    # Queue exhausted but in-flight tasks still pending; do not dispatch.
                    return
                # Both queue exhausted AND all tasks done; fall through to terminal cleanup.
                for thread, slot_worker in zip(
                    self.render_threads, self.render_workers
                ):
                    if thread.isRunning():
                        self._join_render_thread(thread, slot_worker)
                self.render_threads.clear()
                self.render_workers.clear()
                self.is_rendering = False
                self.btn_start.setEnabled(True)
                self.btn_cancel.setEnabled(False)
                self.current_label.setText("Idle")
                # Phase 3.1 — terminal cleanup path reachable when the
                # final dispatched task errors and on_render_error
                # recurses back into _start_next_task. The batch is
                # complete (success or with failures) and must no longer
                # appear in the resume prompt at next launch.
                self._clear_queue_snapshot()
                # B-019: this terminal-cleanup branch also runs when the
                # final task failed (on_render_error -> _start_next_task ->
                # cleanup), so a success-toned "Completed processing N
                # video(s)!" / "Success" fired even on an all-fail batch with
                # every progress box red. Neutral wording is accurate in all
                # cases; per-task outcomes are already shown in the status
                # column. (on_render_completed keeps its success wording for
                # the genuinely-successful terminal path.)
                QMessageBox.information(
                    self,
                    "Batch Finished",
                    "Batch finished — see status column for results.",
                )
                self.save_config()
                return None
            else:
                thread_index = -1
                for i in range(len(self.render_threads)):
                    if self.render_workers[i] is None:
                        thread_index = i
                        break
                if thread_index == (-1):
                    return
                else:
                    # Phase 2d follow-up fix (Item 5): self.all_tasks now
                    # holds preset IDs in the second slot, not display
                    # names. We resolve ids→params (collision-proof) and
                    # ids→display-names (for the worker status emits +
                    # tree-output cell text) here in the dispatcher; the
                    # RenderWorker itself is unchanged and still receives
                    # a list of display strings as `encoder_names`.
                    video_path, encoder_ids, video_idx = self.all_tasks[
                        self.current_task_index
                    ]
                    encoder_names = [
                        self._encoder_display_name(eid) for eid in encoder_ids if eid
                    ]
                    box_index = self.current_task_index
                    self.update_box_color(box_index, "yellow")
                    item = QTreeWidgetItem(self.tree_output)
                    item.setText(0, str(self.current_task_index + 1))
                    item.setText(1, os.path.basename(video_path))
                    if self.sequential_mode:
                        encoder_names_str = (
                            " ➡️ ".join(encoder_names)
                            if encoder_names
                            else "No encoders"
                        )
                        item.setText(2, f"Processing... ({encoder_names_str})")
                    else:
                        item.setText(2, "Processing...")
                    item.setText(3, "Loading...")
                    item.setText(4, "Loading...")
                    item.setText(5, "🟡 Processing")
                    encoder_params_list = []
                    for encoder_id in encoder_ids:
                        if not encoder_id:
                            continue
                        if self.sequential_mode:
                            # Sequential mode params live on the loaded
                            # Preset registry — look up by ID, NOT by name.
                            idx = self.get_encoder_index_by_id(encoder_id)
                            if idx is not None:
                                encoder_params_list.append(
                                    list(self.encoder_options[idx].params)
                                )
                        else:
                            params = self.encoder_params.get(encoder_id)
                            if params:
                                encoder_params_list.append(params)
                    if not encoder_params_list:
                        # H-2: advance the cursor BEFORE invoking the
                        # error handler — its tail re-enters
                        # _start_next_task, and without this line the
                        # same task is re-dispatched forever
                        # (RecursionError). The freshly created tree
                        # row would otherwise sit at "🟡 Processing"
                        # permanently (worker=None skips row updates
                        # inside the handler), so paint it here.
                        failed_index = self.current_task_index
                        self.current_task_index += 1
                        item.setText(2, "Error - preset missing")
                        item.setText(5, "🔴 Error")
                        self.on_render_error(
                            f"Encoder parameters not found for {encoder_ids}",
                            task_index=failed_index,
                        )
                        return
                    else:
                        worker = RenderWorker(
                            video_path,
                            encoder_names,
                            thread_index,
                            str(self.FFMPEG_PATH),
                            self.output_directory,
                            encoder_params_list,
                            output_collision=self.output_collision,
                            gpu_error_action=self.gpu_error_action,
                            gpu_enabled=self.gpu_enabled,
                            gpu_codec=self.gpu_codec,
                            gpu_preset=self.gpu_preset,
                            gpu_max_quality_mode=self.gpu_max_quality_mode,
                            gpu_semaphore=self._gpu_semaphore,
                        )
                        worker.progress_updated.connect(self.update_thread_progress)
                        worker.status_updated.connect(self.update_thread_status)
                        worker.output_updated.connect(self.update_ffmpeg_output)
                        worker.render_completed.connect(self.on_render_completed)
                        worker.error_occurred.connect(self.on_render_error)
                        thread = self.render_threads[thread_index]
                        worker.moveToThread(thread)
                        thread.started.connect(worker.process)
                        self.render_workers[thread_index] = worker
                        worker.tree_item = item
                        worker.task_index = self.current_task_index
                        if self.sequential_mode:
                            self.current_label.setText(
                                f"Currently Rendering: {os.path.basename(video_path)} ({encoder_names_str})"
                            )
                        else:
                            self.current_label.setText(
                                f"Currently Rendering: {os.path.basename(video_path)}"
                            )
                        thread.start()
                        self.active_threads += 1
                        # Phase 3.1 — record DISPATCHED transition for
                        # the just-launched task BEFORE incrementing the
                        # cursor (the task_uuid is indexed by
                        # current_task_index pre-increment). Safe no-op
                        # if queue persistence is disabled.
                        self._update_queue_task_status(
                            self._task_uuid_for_index(self.current_task_index),
                            TaskStatus.DISPATCHED,
                            started_at=time.time(),
                        )
                        self.current_task_index += 1

    def _join_render_thread(self, thread, worker=None, timeout_ms: int = 5000) -> None:
        """Detach `started`, ask the thread to quit, and wait a bounded time.

        Extracted from six identical render-thread teardown sites (Phase 2d
        Item 7); the disconnect -> quit -> bounded-wait triple is unchanged.
        M-1: if the thread does not stop within the timeout (a wedged ffmpeg
        child still holds it), keep BOTH the thread and its worker alive in
        ``_parked_threads`` so the caller's later list-clear cannot drop the
        last reference to a running QThread / live worker — that drop aborts
        the process with "QThread: Destroyed while thread is still running".
        Parked pairs are reaped once their thread finally stops.
        """
        try:
            thread.started.disconnect()
        except TypeError:
            pass
        thread.quit()
        if not thread.wait(timeout_ms):
            self._parked_threads.append((thread, worker))
        self._reap_parked_threads()

    def _reap_parked_threads(self) -> None:
        """Release parked (thread, worker) pairs whose thread has stopped."""
        self._parked_threads = [
            (t, w) for (t, w) in self._parked_threads if t.isRunning()
        ]

    def _rebuild_worker_rows(self, count: int) -> None:
        """Regenerate the worker-indexed UI to exactly ``count`` rows (M-3).

        Worker rows (thread_bars/thread_labels) and ``_worker_state`` were
        built once in setup_ui for the initial num_threads, but
        render_threads/render_workers are rebuilt to the current num_threads
        on every batch. If num_threads changed in between they desynced:
        raising it left new workers with no row (their bounds-guarded UI
        updates silently dropped — "invisible workers"); lowering it left
        dead "Ready" rows. setup_ui and start_render both call this so the
        rows always match the thread count. It is the single row builder, so
        a fresh call (empty layout) simply builds the rows.
        """
        if not hasattr(self, "thread_layout"):
            return
        # Tear down existing rows — each is a QHBoxLayout of widgets.
        while self.thread_layout.count():
            item = self.thread_layout.takeAt(0)
            row = item.layout()
            if row is not None:
                while row.count():
                    w = row.takeAt(0).widget()
                    if w is not None:
                        w.setParent(None)
                        w.deleteLater()
                row.deleteLater()
        self.thread_bars = []
        self.thread_labels = []
        self._worker_state = [
            {"state": "idle", "basename": "", "percent": 0, "error": ""}
            for _ in range(count)
        ]
        for i in range(count):
            thread_row = QHBoxLayout()
            thread_row.setSpacing(5)
            label = QLabel(f"#{i + 1}")
            # Relaxed fixed width for better narrow-window behavior.
            label.setMinimumWidth(24)
            thread_row.addWidget(label)
            status = QLabel(f"\U0001f7e2 Worker {i + 1} \u2014 Ready")
            # Further reduced for better compactness on small/resize. Eliding in render helps.
            status.setMinimumWidth(120)
            status.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            thread_row.addWidget(status)
            progress = QProgressBar()
            thread_row.addWidget(progress, stretch=1)
            self.thread_layout.addLayout(thread_row)
            self.thread_bars.append(progress)
            self.thread_labels.append(status)

    def cancel_render(self):
        """Hủy quá trình render."""
        if self.is_rendering:
            # Phase 3.1 — mark all still-unfinished tasks as CANCELLED
            # in the saved queue BEFORE flipping is_rendering off and
            # tearing down workers. Source-of-truth is the on-disk
            # batch (already reflects every COMPLETED/FAILED transition
            # via update_task_status); anything still in
            # PENDING/DISPATCHED/RUNNING is the cancel target. After
            # cancellation, the queue file is cleared so the next
            # launch does NOT offer to resume a batch the user just
            # explicitly cancelled.
            if self._queue_persistence_enabled():
                try:
                    persisted = self.queue_store.load()
                except (OSError, ValueError) as exc:
                    logger.error(f"queue_store: cancel load failed: {exc}")
                    persisted = None
                if persisted is not None:
                    now = time.time()
                    for task in persisted.tasks:
                        if task.status in UNFINISHED_STATUSES:
                            self._update_queue_task_status(
                                task.task_uuid,
                                TaskStatus.CANCELLED,
                                completed_at=now,
                            )
            # Clear the snapshot — user-initiated cancel means the
            # batch is intentionally abandoned; no resume on next
            # launch.
            self._clear_queue_snapshot()
            self.is_rendering = False
            if hasattr(self, "render_workers"):
                for worker in self.render_workers:
                    if worker is not None:
                        worker.is_cancelled = True
            if hasattr(self, "render_threads"):
                for thread, slot_worker in zip(
                    self.render_threads, self.render_workers
                ):
                    if thread.isRunning():
                        self._join_render_thread(thread, slot_worker)
                self.render_threads.clear()
                self.render_workers.clear()
            if hasattr(self, "progress_boxes"):
                for i in range(len(self.progress_boxes)):
                    if i >= self.completed_tasks:
                        self.update_box_color(i, "red")
            for i in range(len(self.thread_labels)):
                if hasattr(self, "_worker_state") and i < len(self._worker_state):
                    self._worker_state[i]["state"] = "cancelled"
                    self._render_worker_label(i)
                else:
                    self.thread_labels[i].setText("Cancelled")
                self.thread_bars[i].setValue(0)
            self.btn_cancel.setEnabled(False)
            self.btn_start.setEnabled(True)
            self.output_text.append("\nThe rendering process has been canceled.")
            QMessageBox.information(
                self, "Info", "The rendering process has been canceled."
            )

    def validate_inputs(self) -> bool:
        """Xác thực đầu vào."""
        if not self.videos:
            QMessageBox.warning(self, "Warning", "Please select at least one video.")
            return False
        else:
            if not self.output_directory:
                QMessageBox.warning(
                    self, "Warning", "Please select an output directory."
                )
                return False
            else:
                return True

    def _render_worker_label(self, idx):
        """Render thread_labels[idx] from self._worker_state[idx] dict.

        States: idle / running / completed / failed / cancelled.
        """
        if not (0 <= idx < len(self.thread_labels)):
            return
        if not hasattr(self, "_worker_state") or idx >= len(self._worker_state):
            return
        st = self._worker_state[idx]
        n = idx + 1
        s = st["state"]
        if s == "running":
            name = st["basename"]
            # Functional improvement: elide long names for compactness on small windows.
            # Visual format (emoji, structure) unchanged.
            if len(name) > 28:
                name = name[:25] + "..."
            text = f"\U0001f7e1 Worker {n} \u2014 Rendering {name} ({st['percent']}%)"
        elif s == "completed":
            name = st["basename"]
            if len(name) > 28:
                name = name[:25] + "..."
            text = f"\u2705 Worker {n} \u2014 Completed {name}"
        elif s == "failed":
            err = st["error"] or "unknown error"
            if len(err) > 40:
                err = err[:37] + "..."
            text = f"\u274c Worker {n} \u2014 Failed: {err}"
        elif s == "cancelled":
            text = f"\u23f9 Worker {n} \u2014 Cancelled"
        else:
            text = f"\U0001f7e2 Worker {n} \u2014 Ready"
        self.thread_labels[idx].setText(text)

    def update_thread_progress(self, thread_index: int, progress: int):
        """Cập nhật tiến độ của thread."""
        if 0 <= thread_index < len(self.thread_bars):
            self.thread_bars[thread_index].setValue(progress)
        if hasattr(self, "_worker_state") and 0 <= thread_index < len(
            self._worker_state
        ):
            self._worker_state[thread_index]["percent"] = progress
            if self._worker_state[thread_index]["state"] == "running":
                self._render_worker_label(thread_index)

    def update_thread_status(self, thread_index: int, status: str):
        """Map worker status string to per-thread state, then re-render label.

        Worker still emits the same strings as before; we classify them
        client-side into ready/running/completed/failed/cancelled and format
        with the worker number, basename, and percent.
        """
        if not (0 <= thread_index < len(self.thread_labels)):
            return
        if not hasattr(self, "_worker_state") or thread_index >= len(
            self._worker_state
        ):
            self.thread_labels[thread_index].setText(status)
            return
        st = self._worker_state[thread_index]
        if status == "Idle":
            st["state"] = "idle"
        elif status.startswith("Processing:"):
            st["state"] = "running"
            try:
                after = status.split("Processing:", 1)[1].strip()
                st["basename"] = after.split(" with ", 1)[0]
            except Exception:
                pass
        elif status.startswith("Completed"):
            st["state"] = "completed"
        elif status.startswith("Error"):
            st["state"] = "failed"
            if not st["error"]:
                st["error"] = status
        elif status == "Cancelled":
            st["state"] = "cancelled"
        else:
            self.thread_labels[thread_index].setText(status)
            return
        self._render_worker_label(thread_index)

    def update_ffmpeg_output(self, output: str):
        """Cập nhật output của FFmpeg."""
        self.output_text.append(output)
        self.output_text.verticalScrollBar().setValue(
            self.output_text.verticalScrollBar().maximum()
        )

    def _compute_eta_string(self) -> str:
        """Compute recency-weighted ETA string (last 5 tasks).

        Returns "M:SS" or "H:MM:SS" depending on magnitude.
        Returns "calculating..." if no completed tasks yet.
        """
        if not self.task_durations:
            return "calculating..."
        # Recency-weighted: average of last 5 task durations
        recent = self.task_durations[-5:]
        avg_per_task = sum(recent) / len(recent)
        remaining = max(0, self.total_tasks - self.completed_tasks)
        eta_seconds = int(avg_per_task * remaining)
        if eta_seconds >= 3600:
            h, rem = divmod(eta_seconds, 3600)
            m, s = divmod(rem, 60)
            return f"{h}:{m:02d}:{s:02d}"
        m, s = divmod(eta_seconds, 60)
        return f"{m}:{s:02d}"

    def _record_task_duration(self) -> None:
        """Record duration of the just-completed task."""
        now = time.time()
        elapsed = now - self.last_task_start_time
        self.task_durations.append(elapsed)
        self.last_task_start_time = now

    def on_render_completed(self, output_filename: str):
        """Xử lý khi render hoàn thành."""
        if not self.is_rendering:
            return
        worker = self.sender()
        output_path = os.path.join(self.output_directory, output_filename)
        try:
            resolution = self.get_video_resolution(output_path)
        except Exception:
            resolution = "—"
        try:
            duration = self.get_video_duration(output_path)
        except Exception:
            duration = "—"
        item = getattr(worker, "tree_item", None)
        if item is not None and item.text(5) == "🟡 Processing":
            item.setText(2, output_filename)
            item.setText(3, duration)
            item.setText(4, resolution)
            item.setText(5, "🟢 Completed")
        else:
            logger.error("Warning: tree item missing for completed task")
        box_index = getattr(worker, "task_index", self.completed_tasks)
        self.update_box_color(box_index, "green")
        self.completed_tasks += 1
        # Phase 3.1 — persist COMPLETED transition for the finished
        # task. We resolve task_uuid via the task_index stamped on the
        # worker at dispatch (see _start_next_task), not via the
        # post-increment cursor, so out-of-order completion across
        # workers is recorded correctly. Safe no-op if persistence is
        # disabled or task_index is out of range.
        self._update_queue_task_status(
            self._task_uuid_for_index(box_index),
            TaskStatus.COMPLETED,
            completed_at=time.time(),
            final_output=output_filename,
        )
        self._record_task_duration()
        # Phase 3.2 — fire auto-scoring AFTER queue + counter updates,
        # BEFORE the next-task dispatch. Default is OFF; only spawns
        # a ScoreWorker if the user has enabled auto-scoring AND at
        # least one ffmpeg-supported axis is configured. Never blocks
        # the render hot path (ScoreWorker lives on its own QThread).
        try:
            tree_item_for_score = getattr(worker, "tree_item", None)
            self._maybe_auto_score(
                task_index=box_index,
                video_path=worker.video_path,
                output_filename=output_filename,
                tree_item=tree_item_for_score,
            )
        except Exception as exc:
            logger.error(f"scoring: auto-score wire failed (ignored): {exc}")
        self.progress_label.setText(
            f"Progress: {self.completed_tasks}/{self.total_tasks} renders\nETA: {self._compute_eta_string()}"
        )
        self.active_threads -= 1
        thread_index = worker.thread_index
        if 0 <= thread_index < len(self.render_workers):
            self.render_workers[thread_index] = None
            if thread_index < len(self.render_threads):
                self._join_render_thread(self.render_threads[thread_index], worker)
        if self.current_task_index < self.total_tasks:
            self._start_next_task()
        if self.completed_tasks >= self.total_tasks:
            for thread, slot_worker in zip(self.render_threads, self.render_workers):
                if thread.isRunning():
                    self._join_render_thread(thread, slot_worker)
            self.render_threads.clear()
            self.render_workers.clear()
            self.is_rendering = False
            self.btn_start.setEnabled(True)
            self.btn_cancel.setEnabled(False)
            self.current_label.setText("Idle")
            # Phase 3.1 — batch fully drained successfully; the saved
            # queue file is no longer needed and must be removed so
            # the next launch does NOT prompt the user to resume a
            # batch that already finished. Failed/cancelled batches
            # retain their queue file via the cancel_render and
            # closeEvent paths below.
            self._clear_queue_snapshot()
            QMessageBox.information(
                self, "Success", f"Successfully rendered {self.total_tasks} video(s)!"
            )
            self.save_config()

    def on_render_error(self, error_message: str, task_index: Optional[int] = None):
        """Xử lý khi có lỗi render."""
        self.output_text.append(f"\n[ERROR] {error_message}\n")
        self.output_text.verticalScrollBar().setValue(
            self.output_text.verticalScrollBar().maximum()
        )
        worker = self.sender()
        if (
            worker
            and hasattr(self, "_worker_state")
            and 0 <= worker.thread_index < len(self._worker_state)
        ):
            self._worker_state[worker.thread_index]["error"] = error_message
            self._worker_state[worker.thread_index]["state"] = "failed"
            self._render_worker_label(worker.thread_index)
        if worker:
            encoder_name = worker.encoder_names[0] if worker.encoder_names else "—"
            error_detail = error_message.split(":")[(-1)].strip()
            if len(error_detail) > 50:
                error_detail = error_detail[:47] + "..."
            item = getattr(worker, "tree_item", None)
            if item is not None and item.text(5) == "🟡 Processing":
                item.setText(2, f"Error - {encoder_name} ({error_detail})")
                item.setText(3, "—")
                item.setText(4, "—")
                item.setText(5, "🔴 Error")
            else:
                logger.error("Warning: tree item missing for failed task")
        # H-2: an explicit task_index (direct-call path) wins; the
        # completed_tasks fallback only equals the dispatch slot when
        # nothing else has finished yet, so it mis-marked the wrong
        # task FAILED in the queue on any out-of-order batch.
        if task_index is not None:
            box_index = task_index
        else:
            box_index = getattr(worker, "task_index", self.completed_tasks)
        self.update_box_color(box_index, "red")
        self.completed_tasks += 1
        # Phase 3.1 — persist FAILED transition. `box_index` is the
        # task_index set on the worker at dispatch (matches the
        # _task_uuids slot). For the worker=None direct-call path
        # (encoder_params miss inside _start_next_task), box_index
        # falls back to `self.completed_tasks` which is the current
        # dispatch slot — still aligned with the _task_uuids index.
        self._update_queue_task_status(
            self._task_uuid_for_index(box_index),
            TaskStatus.FAILED,
            completed_at=time.time(),
            error_message=error_message,
        )
        self._record_task_duration()
        self.progress_label.setText(
            f"Progress: {self.completed_tasks}/{self.total_tasks} renders\nETA: {self._compute_eta_string()}"
        )
        # Phase 2d follow-up fix (Runtime QA — on_render_error crash):
        # _start_next_task may call this slot DIRECTLY (encoder_params
        # lookup miss at L2092) instead of via the Qt error_occurred
        # signal. A direct call leaves `worker = self.sender()` == None,
        # which would crash on bare `worker.thread_index` access. Mirror
        # the earlier `if worker:` guards so the no-worker path emits
        # the error but skips the per-thread cleanup (no thread was
        # actually started for the failed dispatch).
        if worker is not None:
            thread_index = worker.thread_index
            if 0 <= thread_index < len(self.render_workers):
                self.render_workers[thread_index] = None
                if thread_index < len(self.render_threads):
                    self._join_render_thread(self.render_threads[thread_index], worker)
            self.active_threads -= 1
        # H-2: dispatch on the next event-loop turn instead of
        # synchronously — a consecutive-failure chain unwinds
        # iteratively instead of growing the Python stack.
        QTimer.singleShot(0, self._start_next_task)

    # Phase 2d production-hardening fix (Issue 4): real drag-and-drop
    # support. The previous "Drag videos here" placeholder text was
    # misleading — no drop handlers existed. We register the main
    # window as a drop target and accept local file URLs whose
    # extension matches one of the suite's known video containers.
    # Multi-file, unicode, spaces, and Windows backslash paths are
    # all handled (QUrl.toLocalFile normalises separators per
    # platform). Files that don't match the allowlist are silently
    # ignored — never raises.
    _DRAG_DROP_VIDEO_EXTENSIONS = (
        ".mp4",
        ".mov",
        ".mkv",
        ".avi",
        ".webm",
        ".flv",
        ".mpg",
        ".mpeg",
        ".m4v",
        ".wmv",
        ".ts",
        ".m2ts",
    )

    def dragEnterEvent(self, event):
        """Accept the drag only if at least one local video file is present."""
        mime = event.mimeData()
        if not mime.hasUrls():
            event.ignore()
            return
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            if url.toLocalFile().lower().endswith(self._DRAG_DROP_VIDEO_EXTENSIONS):
                event.acceptProposedAction()
                return
        event.ignore()

    def dragMoveEvent(self, event):
        """Mirror dragEnterEvent so the cursor stays correct while hovering."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Append dropped video files to self.videos and refresh the tree.

        Cancel-safe: this only mutates UI state through the same code
        path as `select_videos`; if a render is already running, the
        new files queue up for the next batch (start_render reads
        self.videos at dispatch time, not at this drop event).
        """
        mime = event.mimeData()
        if not mime.hasUrls():
            event.ignore()
            return
        new_paths = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if not path.lower().endswith(self._DRAG_DROP_VIDEO_EXTENSIONS):
                continue
            if path not in self.videos:
                new_paths.append(path)
        if new_paths:
            self.videos.extend(new_paths)
            self.update_video_list()
        event.acceptProposedAction()

    def closeEvent(self, event):
        """Xử lý khi đóng ứng dụng."""
        # URL download guard runs first. If a batch is in flight, ask the
        # user; if they decline, abort the close. If they confirm, cancel
        # the worker, quit the thread, and bound the wait to 5 seconds so
        # a stuck yt-dlp child cannot block app shutdown forever. After
        # this branch, control falls through to the existing render-close
        # path so a simultaneous render+URL session is still handled.
        # Phase 2d follow-up fix (Issue 6): safe helper avoids
        # RuntimeError when the underlying QThread has already been
        # deleted by an earlier batch's deleteLater cycle.
        if self._url_thread_is_running():
            reply = QMessageBox.question(
                self,
                "Exit",
                "A URL download is in progress. Cancel it and exit?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            if getattr(self, "_url_worker", None) is not None:
                try:
                    self._url_worker.cancel()
                except (Exception, RuntimeError):
                    pass
            try:
                self._url_thread.quit()
                self._url_thread.wait(5000)
            except (Exception, RuntimeError):
                pass

        if self.is_rendering:
            reply = QMessageBox.question(
                self,
                "Exit",
                (
                    "A rendering process is running.\n\n"
                    "If you exit now, the in-progress batch will be saved "
                    "and you can resume it on next launch.\n\n"
                    "Do you really want to exit?"
                ),
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.is_rendering = False
                if hasattr(self, "render_workers"):
                    for worker in self.render_workers:
                        if worker is not None:
                            worker.is_cancelled = True
                if hasattr(self, "render_threads"):
                    for thread, slot_worker in zip(
                        self.render_threads, self.render_workers
                    ):
                        self._join_render_thread(thread, slot_worker)
                    self.render_threads.clear()
                    self.render_workers.clear()
                # Phase 3.1 — exit-during-render is INTENTIONALLY a
                # resumable scenario (distinct from cancel_render).
                # Mark any still-running task back to PENDING so the
                # resume prompt at next launch treats it as
                # outstanding work to redo. We do NOT clear the
                # queue file — that is the whole point of the
                # resume feature.
                if self._queue_persistence_enabled():
                    try:
                        persisted = self.queue_store.load()
                    except (OSError, ValueError) as exc:
                        logger.error(f"queue_store: closeEvent load failed: {exc}")
                        persisted = None
                    if persisted is not None:
                        for task in persisted.tasks:
                            if task.status in (
                                TaskStatus.DISPATCHED,
                                TaskStatus.RUNNING,
                            ):
                                # Demote in-flight tasks back to
                                # PENDING — the worker never finished
                                # them. Pending state means "resume
                                # will re-attempt this task".
                                self._update_queue_task_status(
                                    task.task_uuid,
                                    TaskStatus.PENDING,
                                )
                # Phase 3.2 — cancel any in-flight scoring workers
                # alongside the render cancel. ScoreWorkers spawn
                # short-lived ffmpeg children that must not outlive
                # the app process.
                try:
                    self._cancel_all_score_workers()
                except Exception as exc:
                    logger.error(f"scoring: cancel-on-close failed (ignored): {exc}")
                self.save_config()
                event.accept()
            else:
                event.ignore()
        else:
            # Phase 3.2 — even on a clean exit (no rendering), there may
            # be background scoring workers (auto-score from a prior
            # render still finishing). Stop them politely.
            try:
                self._cancel_all_score_workers()
            except Exception as exc:
                logger.error(f"scoring: cancel-on-close failed (ignored): {exc}")
            self.save_config()
            event.accept()

    def load_encoders_to_tree(self, selected_group: str = "🕹️ 1vmo Ultimate"):
        """Load encoder options vào TreeWidget với lọc theo nhóm"""
        self.tree_encoders.clear()
        current_groups = self.get_encoder_groups()
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem("🕹️ 1vmo Ultimate")
        self.group_combo.addItem("All Groups")
        self.group_combo.addItems(current_groups)
        if selected_group in current_groups or selected_group == "🕹️ 1vmo Ultimate":
            self.group_combo.setCurrentText(selected_group)
        self.group_combo.blockSignals(False)
        sorted_encoders = sorted(
            self.encoder_options, key=lambda x: (x.group, x.full_name)
        )
        counter = 1
        for combo in self.sequential_combos:
            combo.blockSignals(True)
            combo.clear()
            # Empty slot has no preset id; using "" as userData keeps
            # the "currentData() is falsy → empty slot" check clean.
            combo.addItem("", "")
            for encoder in sorted_encoders:
                # Phase 2d follow-up fix (Item 5): combo carries the
                # display name as visible text AND the stable preset id
                # as userData. selection plumbing reads currentData(),
                # never currentText(), so duplicate display names no
                # longer collapse onto the same value.
                combo.addItem(encoder.name, encoder.id)
            combo.blockSignals(False)
        for encoder in sorted_encoders:
            if selected_group == "All Groups" or encoder.group == selected_group:
                item = QTreeWidgetItem(self.tree_encoders)
                item.setText(0, str(counter))
                item.setText(1, encoder.group)
                item.setText(2, encoder.name)
                item.setText(3, encoder.description)
                if encoder.details:
                    tooltip_text = encoder.details.replace(",", ",<br>")
                    tooltip_html = f"\n                    <div style='min-width:280px; max-width:350px; background:#e3f2fd; color:#1976d2; font-family:Consolas,monospace; font-size:13px; padding:8px; border-radius:8px;'>\n                        {tooltip_text}\n                    </div>\n                    "
                    item.setText(4, "ℹ️")
                    item.setTextAlignment(4, Qt.AlignCenter)
                    for col in range(5):
                        item.setToolTip(col, tooltip_html)
                else:
                    item.setText(4, "")
                item.setData(0, Qt.UserRole, " ".join(encoder.params))
                # 2c-c-4: stash id on UserRole+1 + italicize built-in names.
                item.setData(0, Qt.UserRole + 1, encoder.id)
                if encoder.id.startswith("builtin:"):
                    name_font = item.font(2)
                    name_font.setItalic(True)
                    item.setFont(2, name_font)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                counter += 1
        self.tree_encoders.setHeaderLabels(
            ["No.", "Group", "Name", "Description", "Details"]
        )

    def _update_encoder_buttons_enabled(self) -> None:
        """2c-c-4: disable Edit/Delete when any selected encoder is built-in.

        B-018 closure: when the buttons are disabled because of a
        built-in selection, the tooltip becomes explicit so users no
        longer think the buttons are broken. Per ADR-0006, built-in
        presets are immutable — the user can copy the params into a
        new preset via 'Add' to customize. The label-style hint at
        `_update_encoder_status_label` (Option B) explains this
        inline; the tooltip change here closes the same UX gap on
        the buttons themselves (Option A from the BACKLOG).
        """
        selected = self.tree_encoders.selectedItems()
        if not selected:
            self.btn_edit_encoder.setEnabled(False)
            self.btn_delete_encoder.setEnabled(False)
            self.btn_edit_encoder.setToolTip("Select a preset first to edit it")
            self.btn_delete_encoder.setToolTip("Select a preset first to delete it")
            return
        any_builtin = any(
            (item.data(0, Qt.UserRole + 1) or "").startswith("builtin:")
            for item in selected
        )
        self.btn_edit_encoder.setEnabled(not any_builtin)
        self.btn_delete_encoder.setEnabled(not any_builtin)
        if any_builtin:
            self.btn_edit_encoder.setToolTip(
                "Built-in presets are read-only (ADR-0006). "
                "Use 'Add' to create your own copy you can edit."
            )
            self.btn_delete_encoder.setToolTip(
                "Built-in presets are read-only (ADR-0006). "
                "Only user-created presets can be deleted."
            )
        else:
            self.btn_edit_encoder.setToolTip("Edit the selected preset")
            self.btn_delete_encoder.setToolTip("Delete the selected preset")

    def _update_encoder_status_label(self) -> None:
        """B-018 Option B: show context-aware help text based on selection.

        Built-in preset selected -> explain why Edit/Delete are disabled and
        point user to Add for customization. Otherwise -> empty string
        (label still occupies layout space, no tree jump on transition).
        """
        selected = self.tree_encoders.selectedItems()
        any_builtin = any(
            (item.data(0, Qt.UserRole + 1) or "").startswith("builtin:")
            for item in selected
        )
        if any_builtin:
            self.encoder_status_label.setText(
                "\U0001f4cc Built-in preset \u2014 read-only. "
                "Use \u267b\ufe0f Add to create a custom preset you can edit/delete."
            )
        else:
            self.encoder_status_label.setText("")

    def add_encoder(self) -> None:
        """Thêm encoder mới"""
        dialog = EncoderDialog(self)
        if dialog.exec() == QDialog.Accepted and dialog.result:
            self._create_user_preset_from_result(dialog.result)

    def clone_encoder(self) -> None:
        """B-018: clone the selected preset into an editable user copy.

        Built-in presets are read-only (ADR-0006), so on a fresh install
        every preset's Edit/Delete is disabled and there is no in-app way
        to start customizing. Clone is that path: it seeds an EncoderDialog
        with the selected preset's group / name / params / description, and
        on OK creates a NEW preset with a ``user:<slug>`` id (the flat user
        namespace), which lands where Edit/Delete are enabled. The source
        preset is never modified. The button is always enabled and works on
        both built-in and user presets (cloning a user preset is a plain
        copy). Does not weaken the built-in read-only guard.
        """
        selection = self.tree_encoders.selectedItems()
        if not selection:
            QMessageBox.warning(self, "Warning", "Please select a preset to clone")
            return
        item = selection[0]
        group = item.text(1)
        name = item.text(2)
        description = item.text(3)
        params = (item.data(0, Qt.UserRole) or "").split()
        initial_values = {
            "name": f"{group}|{name}" if group else name,
            "description": description,
            "params": params,
        }
        dialog = EncoderDialog(self, "Clone Preset", initial_values)
        if dialog.exec() == QDialog.Accepted and dialog.result:
            self._create_user_preset_from_result(dialog.result)

    def _create_user_preset_from_result(self, result) -> None:
        """Append a user-namespace preset built from an EncoderDialog result.

        Shared by Add and Clone (B-018). Splits the dialog's "Group|Name"
        field, derives a collision-free ``user:<slug>`` id via
        ``_allocate_user_preset_id``, adds the tree row, registers the
        Preset, and persists. Built-in presets are never produced here —
        every id minted is in the editable user namespace.
        """
        item = QTreeWidgetItem(self.tree_encoders)
        item.setText(0, str(len(self.encoder_options) + 1))
        group, name = _split_group_name(result["name"])  # B-020
        # 2c-c-4: derive user-namespace id with disambiguation suffix.
        existing_user_ids = {
            p.id for p in self.encoder_options if p.id.startswith("user:")
        }
        preset_id = _allocate_user_preset_id(name, existing_user_ids)
        item.setText(1, group)
        item.setText(2, name)
        item.setText(3, result["description"])
        item.setData(0, Qt.UserRole, " ".join(result["params"]))
        item.setData(0, Qt.UserRole + 1, preset_id)
        self.encoder_options.append(
            core_preset_loader.Preset(
                id=preset_id,
                group=group,
                name=name,
                description=result["description"],
                details=result.get("details", ""),
                params=tuple(result["params"]),
            )
        )
        self.save_encoder_changes()

    def edit_encoder(self) -> None:
        """Chỉnh sửa encoder đã chọn

        Phase 2d follow-up fix (Item 8 / Observation S): EncoderDialog only
        round-trips name / description / params — it has no `details`
        field. The previous implementation passed `dialog.result.get(
        "details", "")` into the new Preset object, which silently wiped
        the original `details` text every time a user pressed Edit/OK.

        Fix: read the existing `details` from the live Preset object
        BEFORE the assignment and pass it through unchanged. This is a
        round-trip preservation, not a UI exposure — editing details
        remains out of scope until EncoderDialog gains a field for it
        (which would be a feature addition, not a bug fix).
        """
        selection = self.tree_encoders.selectedItems()
        if not selection:
            QMessageBox.warning(self, "Warning", "Please select an encoder to edit")
            return
        item = selection[0]
        current_id = item.data(0, Qt.UserRole + 1) or ""
        # 2c-c-4: defense in depth — UI button is disabled for built-ins,
        # but reject at model layer too in case of future signal regression.
        if current_id.startswith("builtin:"):
            logger.error(
                f"edit_encoder: refused to edit built-in preset {current_id!r}"
            )
            return
        current_group = item.text(1)
        current_name = item.text(2)
        current_desc = item.text(3)
        current_params = item.data(0, Qt.UserRole).split()
        initial_values = {
            "name": f"{current_group}|{current_name}",
            "description": current_desc,
            "params": current_params,
        }
        dialog = EncoderDialog(self, "Edit Encoder", initial_values)
        if dialog.exec() == QDialog.Accepted and dialog.result:
            group, name = _split_group_name(dialog.result["name"])  # B-020
            item.setText(1, group)
            item.setText(2, name)
            item.setText(3, dialog.result["description"])
            item.setData(0, Qt.UserRole, " ".join(dialog.result["params"]))
            idx = self.get_encoder_index_by_id(current_id)
            if idx is not None:
                # Preserve id across edits — rename of a user preset does not
                # change its id, matching desktop-app conventions.
                # Preserve details across edits — EncoderDialog does not
                # expose details yet, so reuse the live Preset value rather
                # than letting the dialog implicitly blank it. If the
                # dialog ever does start returning a "details" key, that
                # takes precedence; otherwise we fall back to the original.
                existing_details = self.encoder_options[idx].details
                self.encoder_options[idx] = core_preset_loader.Preset(
                    id=current_id,
                    group=group,
                    name=name,
                    description=dialog.result["description"],
                    details=dialog.result.get("details", existing_details),
                    params=tuple(dialog.result["params"]),
                )
                self.save_encoder_changes()

    def delete_encoder(self) -> None:
        """Xóa encoder đã chọn"""
        selection = self.tree_encoders.selectedItems()
        if not selection:
            QMessageBox.warning(self, "Warning", "Please select encoder(s) to delete")
            return
        # 2c-c-4: defense in depth — UI is disabled when any built-in is
        # selected; reject at model layer if any sneak through.
        for item in selection:
            preset_id = item.data(0, Qt.UserRole + 1) or ""
            if preset_id.startswith("builtin:"):
                logger.error(
                    f"delete_encoder: refused to delete built-in preset {preset_id!r}"
                )
                return
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            "Are you sure you want to delete the selected encoder(s)?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            for item in selection:
                preset_id = item.data(0, Qt.UserRole + 1) or ""
                idx = self.get_encoder_index_by_id(preset_id)
                if idx is not None:
                    self.encoder_options.pop(idx)
                self.tree_encoders.takeTopLevelItem(
                    self.tree_encoders.indexOfTopLevelItem(item)
                )
            self.save_encoder_changes()

    def save_encoder_changes(self) -> None:
        """Save user-edited presets to USER_PRESETS_FILE atomically.

        2c-c-4: Built-in vs user is intrinsic via id prefix. Filters
        self.encoder_options for entries with id starting "user:".
        """
        user_presets = [p for p in self.encoder_options if p.id.startswith("user:")]
        try:
            save_user_presets_json(self.USER_PRESETS_FILE, user_presets)
            QMessageBox.information(
                self, "Success", "Encoder settings saved successfully"
            )
        except (OSError, ValueError) as e:
            QMessageBox.warning(
                self, "Save Failed", f"Could not save preset changes: {e}"
            )

    def _encoder_display_name(self, encoder_id: str) -> str:
        """Resolve a stable preset ID to its display name for UI labels.

        Phase 2d follow-up fix (Item 5): preset selection / queue
        identity now travels as the ADR-0006 preset `id` (which is
        guaranteed unique by EncoderLibrary._ids_unique) rather than
        the display `name` (which has 13 known collisions across the
        108-preset library). UI strings still want the human-readable
        name, so this helper does a single id→name translation. If
        the id is unknown (stale config, deleted user preset) we
        return the id itself instead of crashing, so the worker
        status string still renders something diagnostic.
        """
        if not encoder_id:
            return ""
        idx = self.get_encoder_index_by_id(encoder_id)
        if idx is None:
            return encoder_id
        return self.encoder_options[idx].name

    def get_encoder_index_by_id(self, preset_id: str) -> Optional[int]:
        """2c-c-4: Find encoder index by stable id."""
        for i, encoder in enumerate(self.encoder_options):
            if encoder.id == preset_id:
                return i
        return None

    def open_output_directory(self):
        """Mở thư mục output directory trong file explorer"""
        if not self.output_directory:
            QMessageBox.warning(
                self, "Warning", "Please select an output directory first."
            )
            return
        try:
            if os.name == "nt":
                os.startfile(self.output_directory)
            elif os.name == "posix":
                if sys.platform == "darwin":
                    subprocess.call(["open", self.output_directory])
                else:
                    subprocess.call(["xdg-open", self.output_directory])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot open directory: {str(e)}")

    def reload_all(self):
        """Reload tất cả các thay đổi từ file và thư mục"""
        try:
            self.tree_output.clear()
            self.output_text.clear()
            self.encoder_options = self.load_encoder_options()
            self.load_encoders_to_tree()
            if self.videos:
                self.update_video_list()
            QMessageBox.information(self, "Success", "Successfully refreshed all data!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error while refreshing: {str(e)}")

    def get_encoder_groups(self) -> List[str]:
        """Lấy danh sách các nhóm encoder duy nhất"""
        return sorted(core_preset_loader.unique_groups(self.encoder_options))

    def on_group_changed(self, group: str):
        """Xử lý khi chọn nhóm khác"""
        self.load_encoders_to_tree(group)

    def create_video_button(
        self,
        text: str,
        callback,
        bg_color: str,
        text_color: str,
        border_color: str,
        delete: bool = False,
    ) -> QPushButton:
        """Tạo nút video với style tùy chỉnh."""
        button = QPushButton(text)
        button.setProperty("toolbar", True)
        button.clicked.connect(callback)
        button.setStyleSheet(
            f"\n            QPushButton {{\n                background-color: {bg_color};\n                color: {text_color};\n                border: 1px solid {border_color};\n            }}\n            QPushButton:hover {{\n                background-color: {border_color};\n            }}\n        "
        )
        if delete:
            button.setProperty("delete", True)
        # For toolbar options (Select, Add URL etc): use stylesheet min (120px) for balance.
        # Lower code min allows compact on small windows for responsiveness.
        # Design unchanged.
        button.setMinimumWidth(80)
        button.setMinimumHeight(24)
        return button

    def on_mode_changed(self):
        """Xử lý khi chọn chế độ ghép

        Phase 2d follow-up fix (Item 5): mirror combo.currentData()
        (preset id) instead of combo.currentText() (display name) so
        self.sequential_encoders is consistent with the start_render
        path. start_render overwrites this list anyway, but keeping
        the two writes shape-identical prevents the field from
        carrying display-name data during the brief moment between
        a mode flip and the next render.
        """
        self.sequential_mode = self.mode_sequential.isChecked()
        # Batch UI-3: the slot strip only exists for Render All Variants;
        # hiding it in Render Once mode returns its height to the trees.
        self.slot_scroll.setVisible(self.sequential_mode)
        for combo in self.sequential_combos:
            combo.setEnabled(self.sequential_mode)
        if self.sequential_mode:
            self.sequential_encoders = [
                (self.sequential_combos[i].currentData() or "")
                for i in range(SEQUENTIAL_SLOT_COUNT)
            ]
        else:
            self.sequential_encoders = [None] * SEQUENTIAL_SLOT_COUNT
        self._update_empty_hints()
        self._update_start_button_state()

    def show_help(self):
        """Hiển thị dialog help"""
        readme_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "assets", "README AutoRender.md"
        )
        dialog = HelpDialog(self, "Help - 1vmo Auto Render", readme_path)
        dialog.exec()

    # ------------------------------------------------------------------
    # Phase 3.1 — local persistent queue helpers
    # ------------------------------------------------------------------

    def _build_batch_from_state(self) -> QueueBatch:
        """Snapshot the current batch state into a QueueBatch.

        Called from start_render() after `self.all_tasks` is built.
        Generates a fresh task_uuid per task and stores them on
        `self._task_uuids` for later update_task_status() calls.

        No-side-effect on the renderer state — purely builds the
        on-disk projection. Tasks start in PENDING status.
        """
        self._current_batch_uuid = str(uuid.uuid4())
        self._task_uuids = [str(uuid.uuid4()) for _ in self.all_tasks]
        tasks = []
        for i, (video_path, encoder_ids, video_idx) in enumerate(self.all_tasks):
            tasks.append(
                QueueTask(
                    task_uuid=self._task_uuids[i],
                    task_index=i,
                    video_path=str(video_path),
                    # encoder_ids is a list[str] after Item 5; copy
                    # to detach from any mutation that follows.
                    encoder_ids=list(encoder_ids),
                    video_idx=int(video_idx),
                    status=TaskStatus.PENDING,
                )
            )
        return QueueBatch(
            batch_uuid=self._current_batch_uuid,
            created_at=time.time(),
            output_directory=str(self.output_directory),
            sequential_mode=bool(self.sequential_mode),
            num_threads=int(self.num_threads),
            settings_snapshot={
                "gpu_enabled": bool(self.gpu_enabled),
                "gpu_codec": str(self.gpu_codec),
                "gpu_preset": str(self.gpu_preset),
                "gpu_max_concurrent": int(self.gpu_max_concurrent),
                "gpu_error_action": str(self.gpu_error_action),
                "output_collision": str(self.output_collision),
            },
            total_tasks=int(self.total_tasks),
            completed_tasks=0,
            tasks=tasks,
        )

    def _queue_persistence_enabled(self) -> bool:
        """Settings checkbox 'Save queue for resume on next launch'."""
        return bool(self.config.get("queue_persistence_enabled", True))

    def _save_queue_snapshot(self) -> None:
        """Persist the current batch. Swallows OSError so a disk-full
        cannot crash the renderer mid-batch."""
        if not self._queue_persistence_enabled():
            return
        try:
            batch = self._build_batch_from_state()
            self.queue_store.save(batch)
        except (OSError, ValueError) as exc:
            self._note_queue_persist_failure("snapshot save", exc)

    def _update_queue_task_status(
        self,
        task_uuid: Optional[str],
        status: TaskStatus,
        **fields,
    ) -> None:
        """Tiny adapter that swallows errors so the renderer keeps
        going if the disk is unwriteable."""
        if not task_uuid or not self._queue_persistence_enabled():
            return
        try:
            self.queue_store.update_task_status(task_uuid, status, **fields)
        except (OSError, ValueError) as exc:
            self._note_queue_persist_failure("status update", exc)

    def _task_uuid_for_index(self, index: int) -> Optional[str]:
        """Look up the task_uuid for a dispatched task index. Returns
        None if the index is out of range (defensive)."""
        if 0 <= index < len(self._task_uuids):
            return self._task_uuids[index]
        return None

    def _note_queue_persist_failure(self, what: str, exc: Exception) -> None:
        """Log a queue-persistence write failure and surface it to the user ONCE.

        queue_store.save() propagates OSError (atomic_write flushes+fsyncs then
        re-raises), so a real disk-full / permissions failure reaches the three
        write call sites. These intentionally never crash the render — but a
        silently swallowed failure means resume capability is lost with no sign.
        We keep never-crash and add a single visible warning per batch (latched),
        re-armed at the start of each batch.
        """
        logger.error(f"queue_store: {what} failed: {exc}")
        if not getattr(self, "_queue_persist_warned", False):
            self._queue_persist_warned = True
            if hasattr(self, "output_text"):
                self.output_text.append(
                    "[WARN] Couldn't save queue state to disk — resume may be "
                    "unavailable for this batch. Check free space and permissions."
                )

    def _clear_queue_snapshot(self) -> None:
        """Remove the on-disk queue file. Idempotent."""
        try:
            self.queue_store.clear()
        except (OSError, ValueError) as exc:
            self._note_queue_persist_failure("clear", exc)
        self._current_batch_uuid = None
        self._task_uuids = []

    def _prompt_resume_saved_batch(self) -> None:
        """Show the resume modal for a batch loaded at startup.

        Three user choices:
          Yes      — resume: re-queue unfinished tasks and start
                     rendering immediately.
          No       — discard: clear the on-disk batch.
          Cancel   — decide later: leave the on-disk batch intact;
                     prompt will re-appear on next launch.

        Missing inputs / missing preset IDs are filtered with a
        single end-of-resume notice listing the skipped count.
        """
        batch = self._pending_resume_batch
        self._pending_resume_batch = None  # consume regardless of answer
        if batch is None:
            return

        unfinished = [t for t in batch.tasks if t.status in UNFINISHED_STATUSES]
        if not unfinished:
            # Defensive: load() already filters via the same set;
            # if we still got here with no work, just clear.
            self._clear_queue_snapshot()
            return

        completed_count = sum(
            1 for t in batch.tasks if t.status is TaskStatus.COMPLETED
        )
        age_seconds = max(0, time.time() - batch.created_at)
        age_human = (
            f"{int(age_seconds // 60)} min ago"
            if age_seconds < 3600
            else f"{int(age_seconds // 3600)} hr ago"
        )

        reply = QMessageBox.question(
            self,
            "Resume previous batch?",
            (
                f"An interrupted batch from {age_human} was found:\n\n"
                f"• {completed_count} of {batch.total_tasks} task(s) completed\n"
                f"• {len(unfinished)} task(s) still pending\n"
                f"• Output dir: {batch.output_directory}\n\n"
                "Resume will use your CURRENT settings, not the settings\n"
                "from when the batch started.\n\n"
                "Yes → resume the remaining tasks\n"
                "No → discard the saved batch\n"
                "Cancel → decide later (the saved batch stays on disk)"
            ),
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.No:
            self._clear_queue_snapshot()
            return
        if reply == QMessageBox.Cancel:
            return  # leave queue file alone — re-prompt next launch

        # Yes → filter against current disk + preset state, then resume.
        self._resume_batch(batch, unfinished)

    def _resume_batch(self, batch: QueueBatch, unfinished: list[QueueTask]) -> None:
        """Re-queue the unfinished tasks from a previously-saved batch.

        Skips:
          • tasks whose video_path no longer exists on disk
          • tasks whose encoder_ids no longer resolve via
            get_encoder_index_by_id
        A summary of skipped reasons is shown after resume kicks off.
        """
        skipped_missing_input: list[str] = []
        skipped_missing_preset: list[str] = []
        resumable_videos: list[str] = []
        resumable_encoder_id_lists: list[list[str]] = []

        for task in unfinished:
            if not os.path.isfile(task.video_path):
                skipped_missing_input.append(os.path.basename(task.video_path))
                continue
            unknown = [
                eid
                for eid in task.encoder_ids
                if self.get_encoder_index_by_id(eid) is None
            ]
            if unknown:
                skipped_missing_preset.append(
                    f"{os.path.basename(task.video_path)} ({', '.join(unknown)})"
                )
                continue
            resumable_videos.append(task.video_path)
            resumable_encoder_id_lists.append(list(task.encoder_ids))

        # If nothing survived filtering, discard and notify.
        if not resumable_videos:
            self._clear_queue_snapshot()
            QMessageBox.information(
                self,
                "Nothing to resume",
                "All saved tasks reference files or presets that are no "
                "longer available. The saved batch has been discarded.",
            )
            return

        # H-1: restore the saved batch's mode BEFORE dispatch — the
        # sequential branch resolves params via the preset registry,
        # the tree branch via encoder_params; resuming a sequential
        # batch under tree mode would look params up in the wrong
        # place. Radios sync silently so on_mode_changed cannot
        # rebuild sequential_encoders from the current UI.
        self.sequential_mode = bool(batch.sequential_mode)
        self.mode_sequential.blockSignals(True)
        self.mode_all.blockSignals(True)
        self.mode_sequential.setChecked(self.sequential_mode)
        self.mode_all.setChecked(not self.sequential_mode)
        self.mode_sequential.blockSignals(False)
        self.mode_all.blockSignals(False)

        # Apply output_directory + videos from the saved batch.
        self.output_directory = batch.output_directory
        if self.output_directory:
            # Polish batch (Observation W): fifth dir_label site routed
            # through the shared formatter (elide + tooltip in one place).
            self._set_output_dir_label(self.output_directory)

        # Restore the unique input list (preserve order, dedupe).
        seen: set[str] = set()
        self.videos = [v for v in resumable_videos if not (v in seen or seen.add(v))]
        self.update_video_list()

        # H-1: the explicit task pairs handed to start_render. The
        # video_idx slot is recomputed against the deduped list —
        # it is only consumed by the queue snapshot.
        path_to_idx = {v: i for i, v in enumerate(self.videos)}
        resume_pairs = [
            (vp, ids, path_to_idx.get(vp, 0))
            for vp, ids in zip(resumable_videos, resumable_encoder_id_lists)
        ]

        # Restore selection identity for the renderer. We bypass the
        # tree-mode UI by directly populating selected_encoders /
        # encoder_params from the resumable encoder IDs, then call
        # start_render() with `_resume_payload` so it knows to re-use
        # rather than rebuild from tree selection.
        flat_ids: list[str] = []
        for ids in resumable_encoder_id_lists:
            for eid in ids:
                if eid not in flat_ids:
                    flat_ids.append(eid)

        self.selected_encoders = flat_ids
        self.encoder_params = {}
        for eid in flat_ids:
            idx = self.get_encoder_index_by_id(eid)
            if idx is not None:
                self.encoder_params[eid] = list(self.encoder_options[idx].params)

        # Brief skip summary (only if anything was filtered).
        skip_msgs = []
        if skipped_missing_input:
            skip_msgs.append(
                f"Missing input files ({len(skipped_missing_input)}):\n  "
                + "\n  ".join(skipped_missing_input[:10])
                + ("\n  …" if len(skipped_missing_input) > 10 else "")
            )
        if skipped_missing_preset:
            skip_msgs.append(
                f"Missing presets ({len(skipped_missing_preset)}):\n  "
                + "\n  ".join(skipped_missing_preset[:10])
                + ("\n  …" if len(skipped_missing_preset) > 10 else "")
            )
        if skip_msgs:
            QMessageBox.warning(
                self,
                "Some tasks skipped on resume",
                "The following tasks could not be resumed:\n\n"
                + "\n\n".join(skip_msgs)
                + "\n\nThe remaining tasks will start now.",
            )

        # H-1: no pre-clear. start_render's _save_queue_snapshot()
        # atomically overwrites the queue file with the resumed
        # batch (fresh batch_uuid + task_uuids), so the saved batch
        # is never destroyed before its replacement exists — a crash
        # in the gap can no longer lose the work.
        self.start_render(resume_tasks=resume_pairs)

    # ------------------------------------------------------------------
    # Phase 3.2 — local-only scoring helpers
    # ------------------------------------------------------------------

    def _scoring_enabled(self) -> bool:
        """True if the scoring subsystem is available (caps + cache OK)."""
        return self.scoring_caps is not None and self.score_cache is not None

    def _auto_scoring_enabled(self) -> bool:
        """Settings checkbox: 'Score every render automatically'."""
        return bool(self.config.get("scoring_auto_enabled", False))

    def _scoring_max_parallel(self) -> int:
        """Settings spinbox: max simultaneous ScoreWorkers. Default 1."""
        try:
            val = int(self.config.get("scoring_max_parallel", 1))
        except (TypeError, ValueError):
            val = 1
        return max(1, min(val, 4))

    def _scoring_default_axes(self) -> list:
        """Settings: which axes to compute when auto-scoring fires.

        Filters to axes the bundled ffmpeg actually supports. pHash
        is always available. VMAF/SSIM/PSNR are filtered by
        scoring_caps so a missing libvmaf does not request VMAF.
        """
        raw = self.config.get("scoring_default_axes", ["vmaf", "phash"])
        if not isinstance(raw, list):
            raw = ["vmaf", "phash"]
        axes = [str(a).lower() for a in raw]
        caps = self.scoring_caps
        out: list = []
        if "vmaf" in axes and caps is not None and caps.vmaf_available:
            out.append("vmaf")
        if "ssim" in axes and caps is not None and caps.ssim_available:
            out.append("ssim")
        if "psnr" in axes and caps is not None and caps.psnr_available:
            out.append("psnr")
        if "phash" in axes and caps is not None and caps.phash_available:
            out.append("phash")
        # Last-resort fallback: pHash never needs ffmpeg filters.
        if not out and caps is not None and caps.phash_available:
            out.append("phash")
        return out

    def _spawn_score_worker(
        self,
        task_index: int,
        reference: Path,
        distorted: Path,
        axes: list,
        tree_item=None,
    ) -> None:
        """Spawn a ScoreWorker on its own dedicated QThread.

        Concurrency-capped via `_scoring_max_parallel`. When the cap
        is full, the request is silently dropped (the user can
        retry once a slot frees). UI feedback is via the row's
        score cell ("…" while running, value on finish).
        """
        if not self._scoring_enabled():
            return
        if not axes:
            return
        # Drop stale finished entries before counting active slots.
        self._prune_finished_score_threads()
        if len(self._score_threads) >= self._scoring_max_parallel():
            logger.info(
                f"scoring: max-parallel ({self._scoring_max_parallel()}) reached; "
                f"task {task_index} request dropped"
            )
            return
        if tree_item is not None:
            # Set cells to in-progress placeholder so the user sees
            # immediate feedback.
            self._render_score_cells(tree_item, None, running=True)
        thread = QThread()
        worker = ScoreWorker(
            task_index=task_index,
            ffmpeg_path=self.FFMPEG_PATH,
            reference=reference,
            distorted=distorted,
            axes=list(axes),
            n_phash_frames=int(self.config.get("scoring_phash_frames", 20)),
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.process)
        worker.score_ready.connect(
            lambda idx, result, ti=tree_item: self._on_score_ready(idx, result, ti)
        )
        worker.score_error.connect(
            lambda idx, msg, ti=tree_item: self._on_score_error(idx, msg, ti)
        )
        # v3.9 H2 fix: wire the thread-lifecycle cleanup so the QThread
        # actually exits after the worker emits a result. Without these
        # four connections, every ScoreWorker leaks its QThread —
        # `_prune_finished_score_threads` sees `thread.isRunning() ==
        # True` forever and the concurrency cap saturates after
        # max_parallel renders. Mirrors the URLDownloadWorker lifecycle
        # pattern used elsewhere in this file.
        worker.score_ready.connect(thread.quit)
        worker.score_error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        # Bookkeeping — track so cancel + cleanup can reach them.
        self._score_threads.append((thread, worker, task_index))
        thread.start()

    def _prune_finished_score_threads(self) -> None:
        """Drop already-finished score threads from the active list."""
        live = []
        for entry in self._score_threads:
            thread, _worker, _idx = entry
            try:
                if thread.isRunning():
                    live.append(entry)
                else:
                    try:
                        thread.quit()
                        thread.wait(500)
                    except Exception:
                        pass
            except RuntimeError:
                # Underlying C++ QThread already deleted; drop.
                pass
        self._score_threads = live

    def _on_score_ready(self, task_index: int, result, tree_item) -> None:
        """Slot — runs on the Qt main thread. Caches + paints cells."""
        if self.score_cache is not None:
            try:
                self.score_cache.put(result)
            except Exception as exc:
                logger.error(f"scoring: cache write failed: {exc}")
        if tree_item is not None:
            try:
                self._score_rows_by_tree_item[id(tree_item)] = result
                self._render_score_cells(tree_item, result, running=False)
            except RuntimeError:
                # Tree item was deleted (rare — user cleared tree).
                pass
        self._prune_finished_score_threads()

    def _on_score_error(self, task_index: int, message: str, tree_item) -> None:
        """Slot — runs on the Qt main thread. Marks cells as ERR."""
        logger.error(f"scoring: task {task_index} error: {message}")
        if tree_item is not None:
            try:
                self._render_score_cells(tree_item, None, running=False, error=message)
            except RuntimeError:
                pass
        self._prune_finished_score_threads()

    def _render_score_cells(
        self, tree_item, result, *, running: bool = False, error: str = ""
    ) -> None:
        """Paint columns 6/7/8 (VMAF / pHash / SSIM) for one row.

        Cell rendering rules (per design doc §5):
            running=True       -> "…" in all three
            error != ""        -> "ERR" with tooltip
            result is None     -> "—" placeholder
            result populated   -> per-axis value / "—" if axis missing
        """
        from core.scoring import ScoreAxisStatus  # local import — safe

        # Defensive: only paint if scoring columns exist on the tree.
        try:
            col_count = self.tree_output.columnCount()
        except RuntimeError:
            return
        if col_count < 9:
            return  # scoring columns not built yet; nothing to paint

        def _set(col: int, text: str, tooltip: str = "") -> None:
            tree_item.setText(col, text)
            tree_item.setToolTip(col, tooltip)

        if running:
            _set(6, "…")
            _set(7, "…")
            _set(8, "…")
            return
        if error:
            tip = f"Scoring failed: {error}"
            _set(6, "ERR", tip)
            _set(7, "ERR", tip)
            _set(8, "ERR", tip)
            return
        if result is None:
            _set(6, "—")
            _set(7, "—")
            _set(8, "—")
            return

        # VMAF cell.
        if result.vmaf_status == ScoreAxisStatus.OK and result.vmaf_mean is not None:
            mean_s = (
                f"{result.vmaf_mean:.1f}"
                if isinstance(result.vmaf_mean, (int, float))
                else "—"
            )
            p5_s = (
                f"{result.vmaf_p5:.1f}"
                if isinstance(result.vmaf_p5, (int, float))
                else "—"
            )
            _set(6, f"{mean_s} / {p5_s}", "VMAF mean / p5 (higher = closer to source)")
        elif result.vmaf_status == ScoreAxisStatus.ERROR:
            _set(6, "ERR", result.vmaf_error or "VMAF failed")
        elif result.vmaf_status == ScoreAxisStatus.CANCELLED:
            _set(6, "—", "VMAF cancelled")
        elif result.vmaf_status == ScoreAxisStatus.UNSUPPORTED:
            _set(6, "—", "libvmaf unavailable in bundled ffmpeg")
        else:
            _set(6, "—")

        # pHash cell.
        if (
            result.phash_status == ScoreAxisStatus.OK
            and result.phash_avg_distance is not None
        ):
            _set(
                7,
                f"{result.phash_avg_distance:.1f}",
                f"Avg dHash Hamming distance across "
                f"{result.phash_frames_compared} sampled frame pairs "
                f"(higher = more different from source)",
            )
        elif result.phash_status == ScoreAxisStatus.ERROR:
            _set(7, "ERR", result.phash_error or "pHash failed")
        elif result.phash_status == ScoreAxisStatus.CANCELLED:
            _set(7, "—", "pHash cancelled")
        else:
            _set(7, "—")

        # SSIM cell.
        if result.ssim_status == ScoreAxisStatus.OK and result.ssim_mean is not None:
            _set(8, f"{result.ssim_mean:.3f}", "SSIM (1.0 = identical)")
        elif result.ssim_status == ScoreAxisStatus.ERROR:
            _set(8, "ERR", result.ssim_error or "SSIM failed")
        elif result.ssim_status == ScoreAxisStatus.CANCELLED:
            _set(8, "—", "SSIM cancelled")
        else:
            _set(8, "—")

    def _maybe_auto_score(
        self, task_index: int, video_path: str, output_filename: str, tree_item
    ) -> None:
        """If auto-scoring is enabled, spawn a worker post-render.

        Called once at the end of on_render_completed for each
        successful task. Looks up the cache first (so an in-place
        re-render reuses a fresh score) and falls back to a worker.
        """
        if not self._scoring_enabled() or not self._auto_scoring_enabled():
            return
        axes = self._scoring_default_axes()
        if not axes:
            return
        reference = Path(video_path)
        distorted = Path(self.output_directory) / output_filename
        # Cache hit short-circuit.
        try:
            ref_m = reference.stat().st_mtime if reference.is_file() else None
            dist_m = distorted.stat().st_mtime if distorted.is_file() else None
        except OSError:
            ref_m = dist_m = None
        cached = (
            self.score_cache.get(
                str(reference),
                str(distorted),
                reference_mtime=ref_m,
                distorted_mtime=dist_m,
            )
            if self.score_cache is not None
            else None
        )
        if cached is not None and tree_item is not None:
            self._score_rows_by_tree_item[id(tree_item)] = cached
            self._render_score_cells(tree_item, cached, running=False)
            return
        self._spawn_score_worker(task_index, reference, distorted, axes, tree_item)

    def _show_output_context_menu(self, pos) -> None:
        """Phase 3.2 — right-click menu on tree_output for manual scoring.

        Provides 'Score this render' / 'Score selected' / 'Score all'
        (only when scoring is initialized + ffmpeg supports at least
        one axis). Existing tree_output behavior (default selection,
        keyboard navigation) is untouched.
        """
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QMenu

        if not self._scoring_enabled():
            return
        item_at_pos = self.tree_output.itemAt(pos)
        selected = self.tree_output.selectedItems()
        # If user right-clicked outside any item, show no menu.
        if item_at_pos is None and not selected:
            return
        menu = QMenu(self.tree_output)
        # The list of axes we'll request — filtered by capability.
        axes = self._scoring_default_axes()
        if not axes:
            menu.addAction("(no scoring axes available)").setEnabled(False)
            menu.exec(self.tree_output.viewport().mapToGlobal(pos))
            return

        def _row_ref_distorted(it) -> tuple:
            # We stored the (input video_path, output basename) inside
            # the row via column text 1 / 2. Re-derive the reference
            # input from self.videos by basename match (filenames may
            # have been mangled by clip_to_limit) and fall back to
            # (None, None) when the row has no usable text.
            try:
                in_name = it.text(1)
                out_name = it.text(2)
            except RuntimeError:
                return (None, None)
            if not in_name or not out_name:
                return (None, None)
            ref_candidate = None
            for v in self.videos:
                if os.path.basename(v) == in_name:
                    ref_candidate = v
                    break
            if ref_candidate is None:
                return (None, None)
            dist_candidate = os.path.join(self.output_directory, out_name)
            return (ref_candidate, dist_candidate)

        action_one = menu.addAction("Score this render")
        action_selected = menu.addAction(f"Score selected ({len(selected)})")
        action_all = menu.addAction("Score all rendered rows")
        # Disable irrelevant actions.
        if item_at_pos is None:
            action_one.setEnabled(False)
        if not selected:
            action_selected.setEnabled(False)

        chosen = menu.exec(self.tree_output.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        targets: list = []
        if chosen is action_one and item_at_pos is not None:
            targets = [item_at_pos]
        elif chosen is action_selected:
            targets = list(selected)
        elif chosen is action_all:
            targets = []
            for i in range(self.tree_output.topLevelItemCount()):
                it = self.tree_output.topLevelItem(i)
                # Skip non-completed rows.
                try:
                    status_text = it.text(5)
                except RuntimeError:
                    continue
                if status_text and "Completed" in status_text:
                    targets.append(it)
        if not targets:
            return
        for idx, ti in enumerate(targets):
            ref, dist = _row_ref_distorted(ti)
            if not ref or not dist:
                continue
            # Cache hit? Just paint, don't re-score.
            cached = None
            if self.score_cache is not None:
                try:
                    ref_m = os.path.getmtime(ref) if os.path.isfile(ref) else None
                    dist_m = os.path.getmtime(dist) if os.path.isfile(dist) else None
                    cached = self.score_cache.get(
                        str(ref),
                        str(dist),
                        reference_mtime=ref_m,
                        distorted_mtime=dist_m,
                    )
                except Exception:
                    cached = None
            if cached is not None:
                self._render_score_cells(ti, cached, running=False)
                continue
            self._spawn_score_worker(
                task_index=idx,
                reference=Path(ref),
                distorted=Path(dist),
                axes=axes,
                tree_item=ti,
            )
        # Suppress unused-import warning at static analysis time.
        _ = Qt

    # ------------------------------------------------------------------
    # Phase 3.4 — orchestration / performance helpers
    # ------------------------------------------------------------------

    def _set_paused(self, paused: bool) -> bool:
        """Set the pause flag, persist it to queue_state, and sync the button.

        Shared by _toggle_pause and the M-4a guard in start_render so the
        in-memory flag, the persisted queue_state, and the button label can
        never drift. Returns False (after warning) if persistence fails.
        """
        try:
            from core.orchestration.queue_state import (
                QueueState,
                load_queue_state,
                save_queue_state,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Pause", f"Pause unavailable: {exc}")
            return False
        state = load_queue_state(self.USER_DATA_DIR) or QueueState()
        state.paused = paused
        state.paused_at = time.time() if paused else None
        try:
            save_queue_state(self.USER_DATA_DIR, state)
        except OSError as exc:
            QMessageBox.warning(self, "Pause", f"Could not persist: {exc}")
            return False
        self.is_paused = paused
        if hasattr(self, "pause_btn"):
            self.pause_btn.setText("▶ Resume" if paused else "⏸️ Pause")
        return True

    def _toggle_pause(self) -> None:
        """Toggle the queue pause flag. Persisted to queue_state.json.

        Currently-running tasks NEVER get interrupted; pause only
        gates future _start_next_task dispatches. Cancel still
        works as before.
        """
        if not self._set_paused(not getattr(self, "is_paused", False)):
            return
        if self.is_paused:
            self.output_text.append(
                "[INFO] Queue paused. Current task finishes; next dispatch waits."
            )
        else:
            self.output_text.append("[INFO] Queue resumed.")
            # M-4b: refill EVERY free slot, not just one — otherwise resume
            # collapses the render pool to serial (one task at a time) until
            # each completion re-triggers the next dispatch. Mirrors the
            # fan-out start_render does on a fresh batch.
            if self.is_rendering:
                try:
                    for _ in range(self.num_threads):
                        self._start_next_task()
                except Exception:
                    pass

    def _encoder_intel_preflight(self) -> bool:
        """Phase 3.5 pre-flight: classify selected presets vs gpu_caps.

        Returns True to continue the render, False to abort.
        Soft-fails on any internal error → returns True so a defective
        intelligence module cannot block rendering.
        """
        try:
            from core.encoder_intel import (
                Severity,
                classify_preset,
                compatibility_check,
            )
        except Exception:
            return True  # module unavailable → silent pass-through

        # Determine the preset id chain in play this batch.
        try:
            if self.sequential_mode:
                preset_ids = [
                    c.currentData() for c in self.sequential_combos if c.currentData()
                ]
            else:
                preset_ids = [
                    item.data(0, Qt.UserRole + 1) or ""
                    for item in self.tree_encoders.selectedItems()
                ]
                preset_ids = [p for p in preset_ids if p]
        except Exception:
            return True

        if not preset_ids:
            return True

        # Map id → params via the existing encoder_options registry.
        blockers: list[str] = []
        warns: list[str] = []
        gpu_caps = getattr(self, "gpu_caps", None)
        for pid in preset_ids:
            try:
                idx = self.get_encoder_index_by_id(pid)
                params = (
                    list(self.encoder_options[idx].params) if idx is not None else []
                )
                classification = classify_preset(pid, params)
                verdict = compatibility_check(
                    classification,
                    gpu_caps,
                    gpu_enabled=bool(self.gpu_enabled),
                )
            except Exception:
                continue
            if verdict.severity is Severity.BLOCK:
                fallback = (
                    f" → suggested fallback: {verdict.suggested_fallback_codec}"
                    if verdict.suggested_fallback_codec
                    else ""
                )
                blockers.append(f"{pid}: {verdict.reason}{fallback}")
            elif verdict.severity is Severity.WARN:
                warns.append(f"{pid}: {verdict.reason}")

        # WARNs are informational — surface in the output panel only.
        if warns:
            try:
                self.output_text.append(
                    "[INFO] Encoder compatibility warnings:\n  - "
                    + "\n  - ".join(warns)
                )
            except Exception:
                pass

        if not blockers:
            return True

        # BLOCKs require explicit user choice. Offer Cancel / Proceed.
        body = (
            "The following preset(s) may not encode successfully on this "
            "hardware:\n\n  - "
            + "\n  - ".join(blockers)
            + "\n\nYou can change the codec in Settings → GPU Pipeline, "
            "swap to a CPU preset, or proceed anyway."
        )
        choice = QMessageBox.warning(
            self,
            "Encoder compatibility check",
            body,
            QMessageBox.Cancel | QMessageBox.Ignore,
            QMessageBox.Cancel,
        )
        if choice == QMessageBox.Ignore:
            try:
                self.output_text.append(
                    "[INFO] Proceeding past encoder compatibility BLOCK "
                    "at user request."
                )
            except Exception:
                pass
            return True
        return False

    def _open_diagnostics_export(self) -> None:
        """Export a local diagnostic bundle zip to a user-chosen path."""
        try:
            from core.orchestration import export_diagnostic_zip
        except Exception as exc:
            QMessageBox.warning(self, "Diagnostics", f"Diagnostics unavailable: {exc}")
            return
        from PySide6.QtWidgets import QFileDialog

        default_name = f"1vmo-diagnostic-{int(time.time())}.zip"
        path_str, _filter = QFileDialog.getSaveFileName(
            self,
            "Save diagnostic bundle",
            default_name,
            "Zip archive (*.zip)",
        )
        if not path_str:
            return
        try:
            out = export_diagnostic_zip(self.USER_DATA_DIR, Path(path_str))
        except OSError as exc:
            QMessageBox.warning(self, "Diagnostics", f"Export failed: {exc}")
            return
        QMessageBox.information(self, "Diagnostics", f"Bundle written to:\n{out}")

    # ------------------------------------------------------------------
    # Phase 3.3 — optimization / recommendation surface
    # ------------------------------------------------------------------

    def _open_render_health_dialog(self) -> None:
        """Open RenderHealthDialog with current batch + score history.

        Pulls Phase 3.2 ScoreCache rows + the on-disk Phase 3.1
        queue to assemble a per-row health table. The dialog is
        read-only; clicking "Apply..." on any row hands off to
        _apply_recommendation which queues a re-render with a _v2
        suffix (never overwrites the original).
        """
        try:
            from core.optimization import (
                analyze_batch,
                classify_health,
                recommend_for_render,
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Render Health",
                f"Optimization module unavailable: {exc}",
            )
            return

        # Gather rows from the current tree_output. The tree
        # already holds (basename, status). We pair them with any
        # cached score row by filename match.
        rows: list[dict] = []
        try:
            for i in range(self.tree_output.topLevelItemCount()):
                ti = self.tree_output.topLevelItem(i)
                in_name = ti.text(1)
                out_name = ti.text(2)
                status_txt = ti.text(5) or ""
                ref = None
                for v in self.videos:
                    if os.path.basename(v) == in_name:
                        ref = v
                        break
                vmaf_mean = None
                vmaf_p5 = None
                phash = None
                if self.score_cache is not None and ref is not None and out_name:
                    dist = os.path.join(self.output_directory, out_name)
                    try:
                        cached = self.score_cache.get(str(ref), str(dist))
                    except Exception:
                        cached = None
                    if cached is not None:
                        vmaf_mean = cached.vmaf_mean
                        vmaf_p5 = cached.vmaf_p5
                        phash = cached.phash_avg_distance
                rows.append(
                    {
                        "row_index": i,
                        "in_name": in_name,
                        "out_name": out_name,
                        "status": "failed" if "Error" in status_txt else "completed",
                        "vmaf_mean": vmaf_mean,
                        "vmaf_p5": vmaf_p5,
                        "phash_avg_distance": phash,
                        "duration_s": None,
                        "error_message": None,
                    }
                )
        except RuntimeError:
            pass

        summary = analyze_batch(rows=rows)

        # Build recommendations per row (cheap).
        recs_per_row: dict[int, list] = {}
        median_dur = summary.median_duration_s
        for row in rows:
            if row["status"] == "failed":
                continue
            recs = recommend_for_render(
                vmaf_mean=row["vmaf_mean"],
                vmaf_p5=row["vmaf_p5"],
                phash_avg_distance=row["phash_avg_distance"],
                render_duration_s=row["duration_s"],
                batch_median_duration_s=median_dur,
                settings_snapshot={"gpu_enabled": bool(self.gpu_enabled)},
                gpu_available=bool(
                    getattr(getattr(self, "gpu_caps", None), "nvenc_available", False)
                ),
            )
            if recs:
                recs_per_row[row["row_index"]] = recs

        # Build the dialog inline (avoids growing the module with
        # another big class; this dialog is small enough).
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QLabel,
            QTreeWidget,
            QTreeWidgetItem,
            QVBoxLayout,
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Render Health")
        # Changed to min size for better behavior on small main windows / high DPI.
        # Design and content inside unchanged.
        dlg.setMinimumSize(700, 400)
        dlg.resize(900, 500)
        layout = QVBoxLayout(dlg)

        header_lines = [
            f"Batch summary: {summary.total} task(s) — "
            f"{summary.green} OK · {summary.yellow} review · "
            f"{summary.red} broken · {summary.failed} failed",
        ]
        if summary.avg_vmaf_mean is not None:
            header_lines.append(f"Average VMAF mean: {summary.avg_vmaf_mean:.1f}")
        if summary.avg_phash_distance is not None:
            header_lines.append(
                f"Average pHash distance: {summary.avg_phash_distance:.1f}"
            )
        for note in summary.notes:
            header_lines.append("- " + note)
        layout.addWidget(QLabel("\n".join(header_lines)))

        tree = QTreeWidget()
        tree.setHeaderLabels(["Filename", "VMAF", "pHash", "Health", "Suggestion"])
        for row in rows:
            it = QTreeWidgetItem(tree)
            it.setText(0, row["out_name"] or row["in_name"] or "")
            v = row["vmaf_mean"]
            it.setText(1, f"{v:.1f}" if isinstance(v, (int, float)) else "—")
            p = row["phash_avg_distance"]
            it.setText(2, f"{p:.1f}" if isinstance(p, (int, float)) else "—")
            health = classify_health(
                vmaf_mean=row["vmaf_mean"],
                vmaf_p5=row["vmaf_p5"],
                phash_avg_distance=row["phash_avg_distance"],
                render_duration_s=row["duration_s"],
                batch_median_duration_s=median_dur,
            )
            it.setText(3, health.value.replace("_", " "))
            recs = recs_per_row.get(row["row_index"], [])
            if recs:
                it.setText(4, recs[0].reason)
                it.setData(0, Qt.UserRole, row["row_index"])
            else:
                it.setText(4, "—")
        for col in range(5):
            tree.resizeColumnToContents(col)
        layout.addWidget(tree)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        btns.accepted.connect(dlg.accept)
        layout.addWidget(btns)

        def _on_double_click(item, _col):
            idx = item.data(0, Qt.UserRole)
            if idx is None:
                return
            recs = recs_per_row.get(idx, [])
            if not recs:
                return
            self._show_recommendation_dialog(rows[idx], recs)

        tree.itemDoubleClicked.connect(_on_double_click)
        dlg.exec()

    def _show_recommendation_dialog(self, row: dict, recs: list) -> None:
        """Show one recommendation with Confirm/Cancel. NEVER auto-applies."""
        if not recs:
            return
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QLabel,
            QPushButton,
            QVBoxLayout,
        )

        first = recs[0]
        dlg = QDialog(self)
        dlg.setWindowTitle("Suggested re-render")
        # Min size for responsiveness on small screens.
        dlg.setMinimumSize(400, 280)
        dlg.resize(520, 360)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(f"File: {row.get('out_name') or row.get('in_name')}"))
        layout.addWidget(
            QLabel(
                f"Kind: {first.kind.value}\n"
                f"Confidence: {first.confidence.value}\n"
                f"\nWhy: {first.reason}\n\n"
                f"Proposed delta: {first.delta_summary or '—'}"
            )
        )
        layout.addWidget(
            QLabel(
                "Re-render output will use a _v2 suffix; original is preserved.\n"
                "Nothing is auto-applied — confirm below to queue."
            )
        )
        btns = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        ok = btns.button(QDialogButtonBox.Ok)
        if isinstance(ok, QPushButton):
            ok.setText("Re-render once")
        btns.rejected.connect(dlg.reject)
        btns.accepted.connect(dlg.accept)
        layout.addWidget(btns)
        if dlg.exec() == QDialog.Accepted:
            self._apply_recommendation(row, first)

    def _apply_recommendation(self, row: dict, recommendation) -> None:
        """Queue a SINGLE re-render with the proposed params + _v2 suffix.

        Goes through the EXISTING start_render path — RenderWorker
        is unchanged. We pre-populate self.videos with just the
        one input and reuse the user's current preset chain (the
        recommender's proposed_params is advisory; a thorough
        wiring of preset_translator hooks belongs in Phase 3.5).
        """
        ref_name = row.get("in_name") or ""
        ref = None
        for v in self.videos:
            if os.path.basename(v) == ref_name:
                ref = v
                break
        if ref is None:
            QMessageBox.information(
                self,
                "Re-render",
                "Original input file not found in this session. "
                "Add it again to re-render.",
            )
            return
        if self.is_rendering:
            QMessageBox.information(
                self,
                "Re-render",
                "A batch is already running. Cancel or finish it first.",
            )
            return
        # Honor the proposed_params hints at the dispatcher level
        # (advisory only — preset_translator is untouched).
        # v3.9 fix: snapshot state so a failed start does not leave the
        # user with a destroyed file list or a silently flipped GPU
        # toggle. Full restore-after-batch is deferred (BACKLOG).
        prior_videos = list(self.videos)
        prior_gpu_enabled = bool(self.gpu_enabled)
        prop = recommendation.proposed_params or {}
        if "gpu_enabled" in prop:
            self.gpu_enabled = bool(prop["gpu_enabled"])
        # Restrict the next batch to JUST the target input.
        self.videos = [ref]
        try:
            self.update_video_list()
        except Exception:
            pass
        # Kick off via the normal Start path; user sees the same
        # progress UI they always see.
        try:
            self.start_render()
        except Exception as exc:
            # Roll back the destructive swap — the render never began.
            self.videos = prior_videos
            self.gpu_enabled = prior_gpu_enabled
            try:
                self.update_video_list()
            except Exception:
                pass
            QMessageBox.warning(self, "Re-render", f"Could not start: {exc}")

    def _cancel_all_score_workers(self) -> None:
        """Tell every active ScoreWorker to bail. Bounded wait per Phase 2d Item 7."""
        for entry in list(self._score_threads):
            thread, worker, _idx = entry
            try:
                worker.cancel()
            except Exception:
                pass
            try:
                thread.quit()
                thread.wait(5000)
            except Exception:
                pass
        self._score_threads.clear()


class EncoderDialog(QDialog):
    def __init__(self, parent=None, title="Add New Encoder", initial_values=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumSize(400, 300)
        self.resize(500, 400)
        self.result = None
        self.initial_values = initial_values or {
            "name": "",
            "description": "",
            "params": [],
        }
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setText(self.initial_values["name"])
        layout.addWidget(self.name_edit)
        layout.addWidget(QLabel("Description:"))
        self.desc_edit = QTextEdit()
        self.desc_edit.setText(self.initial_values["description"])
        layout.addWidget(self.desc_edit)
        layout.addWidget(QLabel("Parameters:"))
        self.params_edit = QTextEdit()
        self.params_edit.setText(" ".join(self.initial_values["params"]))
        layout.addWidget(self.params_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Warning", "Name is required")
            return
        else:
            self.result = {
                "name": name,
                "description": self.desc_edit.toPlainText().strip(),
                "params": self.params_edit.toPlainText().strip().split(),
            }
            super().accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoRendererTool()
    window.show()
    sys.exit(app.exec())
