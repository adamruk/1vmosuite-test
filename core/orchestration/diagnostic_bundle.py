"""Phase 3.4 — diagnostic bundle export.

Zips up the user's logs + queue.json + scores.json + sanitized
config so a support handoff is a single file. Local-only — the
zip lands on the user's chosen path. No upload, no remote share.
"""

from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("core.orchestration.diagnostic_bundle")

# Files we always try to include if present.
_DEFAULT_INCLUDES = (
    "queue.json",
    "queue_state.json",
    "scores.json",
    "encoder.user.json",
    "config_video_renderer.json",
    "gpu_caps_cache.json",  # Phase 3.5 — included if it exists
)

# Sensitive keys that get blanked in the config snapshot before
# inclusion (the user picked these output paths; the diagnostic
# bundle is usually shared and shouldn't leak Desktop/Downloads).
_SANITIZE_KEYS = ("output_dir", "input_files")


def _sanitize_config(text: str) -> str:
    """Strip user-specific paths from config_video_renderer.json text.

    Falls through to returning the raw text if the file is not
    valid JSON (defensive — we never raise on a malformed config).
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text
    if not isinstance(data, dict):
        return text
    # input_files is a list-of-paths; reduce to basenames before the
    # generic redaction loop (which would otherwise blank the list).
    if isinstance(data.get("input_files"), list):
        data["input_files"] = [Path(p).name for p in data["input_files"] if p]
    for key in _SANITIZE_KEYS:
        if key == "input_files":
            continue  # already handled above
        if key in data:
            data[key] = "<redacted>"
    return json.dumps(data, indent=2)


def export_diagnostic_zip(
    user_data_dir: Path,
    target_zip: Path,
    *,
    extra_files: Iterable[Path] = (),
) -> Path:
    """Bundle USER_DATA_DIR/{logs,queue.json,scores.json,...} into a zip.

    Returns the zip Path on success. Caller catches OSError to
    surface a user-visible warning.
    """
    user_data_dir = Path(user_data_dir)
    target_zip = Path(target_zip)
    target_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # default includes
        for name in _DEFAULT_INCLUDES:
            p = user_data_dir / name
            if not p.is_file():
                continue
            try:
                if name == "config_video_renderer.json":
                    text = p.read_text("utf-8")
                    zf.writestr(name, _sanitize_config(text))
                else:
                    zf.write(p, arcname=name)
            except OSError as exc:
                logger.debug("diagnostic_bundle: skip %s: %s", name, exc)
        # logs/ tree
        logs_dir = user_data_dir / "logs"
        if logs_dir.is_dir():
            for path in logs_dir.rglob("*"):
                if not path.is_file():
                    continue
                arc = "logs/" + str(path.relative_to(logs_dir)).replace("\\", "/")
                try:
                    zf.write(path, arcname=arc)
                except OSError as exc:
                    logger.debug("diagnostic_bundle: skip log %s: %s", path, exc)
        # explicit extras
        for extra in extra_files:
            try:
                ep = Path(extra)
                if ep.is_file():
                    zf.write(ep, arcname=ep.name)
            except OSError as exc:
                logger.debug("diagnostic_bundle: skip extra %s: %s", extra, exc)
    return target_zip


__all__ = ["export_diagnostic_zip"]
