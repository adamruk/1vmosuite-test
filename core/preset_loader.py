"""Shared encoder preset loading for 1vmo Suite apps.

Currently used only by auto_render.py. The other 3 apps use hardcoded
ffmpeg parameters and do not parse Encoder.txt.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata as _unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

SCHEMA_VERSION = 2

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def derive_slug(name: str) -> str:
    """5-step slug transform per ADR-0006.

    NFKD-normalize → strip combining marks → lowercase → replace runs
    of non-alphanumeric with single hyphen → strip leading/trailing
    hyphens. Returns "" if input has no alphanumeric content.
    """
    decomposed = _unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not _unicodedata.combining(c))
    lowered = stripped.lower()
    hyphenated = _SLUG_RE.sub("-", lowered)
    return hyphenated.strip("-")


def derive_ids_for_presets(
    name_pairs: list[tuple[str, str]],
    *,
    kind: str = "builtin",
) -> list[str]:
    """Derive ids from (group, name) tuples per ADR-0006.

    Args:
        name_pairs: list of (group, name) tuples in file order.
        kind: "builtin" (group-prefixed; allows '/') or "user" (flat;
            never has '/' regardless of group).

    Returns:
        list[str] of ids, 1:1 with name_pairs. Conditional suffix on
        collisions: unique base slugs receive no suffix; collision
        clusters receive 1-indexed -N suffix in file order.
    """
    assert kind in ("builtin", "user")
    base_ids: list[str] = []
    for group, name in name_pairs:
        name_slug = derive_slug(name) or "preset"
        if kind == "builtin" and group:
            group_slug = derive_slug(group)
            if group_slug:
                base_ids.append(f"builtin:{group_slug}/{name_slug}")
            else:
                base_ids.append(f"builtin:{name_slug}")
        elif kind == "builtin":
            base_ids.append(f"builtin:{name_slug}")
        else:
            base_ids.append(f"user:{name_slug}")

    counts: dict[str, int] = {}
    for bid in base_ids:
        counts[bid] = counts.get(bid, 0) + 1

    result: list[str] = []
    seen_count: dict[str, int] = {}
    for bid in base_ids:
        if counts[bid] == 1:
            result.append(bid)
        else:
            seen_count[bid] = seen_count.get(bid, 0) + 1
            result.append(f"{bid}-{seen_count[bid]}")
    return result


@dataclass(frozen=True)
class Preset:
    """A single encoder preset parsed from Encoder.txt.

    2c-c-4: id is the load-bearing identity. full_name is DEPRECATED
    and retained as a property for the load-time selected_encoders
    migration shim only; may be removed once that migration ships and
    is verified.
    """

    id: str  # 2c-c-4 stable identity (e.g., "builtin:group/name", "user:name")
    group: str  # column 1, may be '' for ungrouped
    name: str  # column 2, required non-empty
    description: str  # column 3
    details: str  # column 4, may be ''
    params: tuple[str, ...]  # column 5, whitespace-tokenized

    @property
    def full_name(self) -> str:
        """Concatenated '{group}|{name}' form used historically.

        DEPRECATED with 2c-c-4; identity is now id. Kept for migration
        shim and may be removed once selected_encoders migration is
        verified in production.
        """
        return f"{self.group}|{self.name}"


def load_presets(
    path: Path,
    on_error: Optional[Callable[[int, str, str], None]] = None,
) -> list[Preset]:
    """Parse 5-column pipe-delimited presets from a file.

    Tolerates '|' inside FFmpeg filter_complex (uses rsplit+split).
    Skip conditions: blank line, missing trailing '|' separator (rsplit
    does not yield exactly 2 parts), fewer than 3 header parts, empty
    preset name after strip.

    On skip, invokes on_error(line_number, line_content, reason) if
    provided. Otherwise falls back to print() using the exact legacy
    auto_render.load_encoder_options messages for backward compatibility.

    Returns presets in file order. Does NOT append app-specific defaults
    — callers merge those in.
    """
    parsed: list[tuple[str, str, str, str, tuple[str, ...]]] = []
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            try:
                if raw_line.strip():
                    parts = raw_line.strip().rsplit("|", 1)
                    if len(parts) != 2:
                        _report(
                            on_error, line_number, raw_line.strip(), "no pipe separator"
                        )
                        continue
                    header_parts = parts[0].split("|", 3)
                    if len(header_parts) < 3:
                        _report(
                            on_error,
                            line_number,
                            raw_line.strip(),
                            "fewer than 3 header parts",
                        )
                        continue
                    group = header_parts[0].strip()
                    name = header_parts[1].strip()
                    description = header_parts[2].strip()
                    details = header_parts[3].strip() if len(header_parts) > 3 else ""
                    code = parts[1].strip()
                    if not name:
                        _report(on_error, line_number, raw_line.strip(), "empty name")
                        continue
                    parsed.append(
                        (group, name, description, details, tuple(code.split()))
                    )
            except Exception as e:
                _report(on_error, line_number, raw_line.strip(), f"exception: {str(e)}")
                continue
    ids = derive_ids_for_presets([(g, n) for g, n, _, _, _ in parsed], kind="builtin")
    return [
        Preset(id=ids[i], group=g, name=n, description=d, details=dd, params=p)
        for i, (g, n, d, dd, p) in enumerate(parsed)
    ]


def _report(
    on_error: Optional[Callable[[int, str, str], None]],
    line_num: int,
    line: str,
    reason: str,
) -> None:
    """Report a parse skip. Defaults to the exact legacy print() format
    used by auto_render.load_encoder_options so observable behavior is
    unchanged for callers that don't supply on_error."""
    if on_error is not None:
        on_error(line_num, line, reason)
        return
    if reason in ("no pipe separator", "fewer than 3 header parts"):
        print(f"Skipping invalid encoder option at line {line_num}: {line}")
    elif reason == "empty name":
        print(f"Skipping encoder option with empty name at line {line_num}")
    elif reason.startswith("exception: "):
        exc = reason[len("exception: ") :]
        print(f"Error parsing line {line_num}: {exc}")
    else:
        print(f"[preset_loader] line {line_num}: {reason}")


def group_presets(presets: list[Preset]) -> dict[str, list[Preset]]:
    """Bucket presets by .group, preserving first-seen group order."""
    grouped: dict[str, list[Preset]] = {}
    for p in presets:
        grouped.setdefault(p.group, []).append(p)
    return grouped


def unique_groups(presets: list[Preset]) -> list[str]:
    """Return non-empty group names in first-seen order.

    Matches the existing get_encoder_groups filter (`if group:`) but
    preserves encounter order rather than sorting. Callers that need
    sorted output wrap with sorted(unique_groups(...)).
    """
    seen: list[str] = []
    seen_set: set[str] = set()
    for p in presets:
        if p.group and p.group not in seen_set:
            seen.append(p.group)
            seen_set.add(p.group)
    return seen


def load_presets_json(path: Path) -> list[Preset]:
    """Parse presets from a JSON file written by save_presets_json.

    Schema v1: {"schema_version": 1, "presets": [{"group": str, "name": str,
    "description": str, "details": str, "params": list[str]}, ...]}

    Missing file returns [] (matches load_presets() contract).
    Corrupt JSON, schema mismatch, or structural errors raise ValueError
    with specific context. params is reconstructed as tuple to preserve
    Preset's frozen-dataclass hashability.
    """
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Encoder JSON at {path} is syntactically invalid "
                f"at line {e.lineno} col {e.colno}: {e.msg}. "
                f"Restore from git or re-run tools/generate_encoder_json.py."
            ) from e

    if not isinstance(data, dict):
        raise ValueError(
            f"Encoder JSON root must be an object, got {type(data).__name__}"
        )
    sv = data.get("schema_version")
    if sv not in (1, 2):
        raise ValueError(
            f"Encoder JSON schema_version is {sv!r}, expected 1 or 2. "
            f"Explicit migration required."
        )
    if not isinstance(data.get("presets"), list):
        raise ValueError(
            f"Encoder JSON 'presets' key must be a list, "
            f"got {type(data.get('presets')).__name__}"
        )

    required_fields = ("group", "name", "description", "details", "params")
    for i, entry in enumerate(data["presets"]):
        if not isinstance(entry, dict):
            raise ValueError(
                f"Preset at index {i} must be an object, got {type(entry).__name__}"
            )
        for field in required_fields:
            if field not in entry:
                raise ValueError(
                    f"Preset at index {i} missing required field {field!r}"
                )
        if not isinstance(entry["params"], list):
            raise ValueError(
                f"Preset at index {i}: 'params' must be a list, "
                f"got {type(entry['params']).__name__}"
            )

    raw_entries = data["presets"]
    if sv == 2:
        return [
            Preset(
                id=p["id"],
                group=p["group"],
                name=p["name"],
                description=p["description"],
                details=p["details"],
                params=tuple(p["params"]),
            )
            for p in raw_entries
        ]
    ids = derive_ids_for_presets(
        [(p["group"], p["name"]) for p in raw_entries], kind="builtin"
    )
    return [
        Preset(
            id=ids[i],
            group=p["group"],
            name=p["name"],
            description=p["description"],
            details=p["details"],
            params=tuple(p["params"]),
        )
        for i, p in enumerate(raw_entries)
    ]


def save_presets_json(path: Path, presets: list[Preset]) -> None:
    """Atomically write presets to a JSON file.

    Serialization byte-matches tools/generate_encoder_json.py output:
    schema_version=1, ensure_ascii=False, indent=2, sort_keys=False,
    newline='\\n', trailing '\\n' after json.dump. Field order via asdict().

    Atomic via .tmp -> flush -> fsync -> os.replace (atomic on POSIX via
    rename(2); atomic on Windows since Python 3.3 via MoveFileEx). On
    failure the .tmp is cleaned up; original file never partially overwritten.
    Directory fsync deliberately omitted — not justified for desktop app.
    """
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "presets": [asdict(p) for p in presets],
    }
    try:
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def load_builtin_json(path: Path) -> list[Preset]:
    """Load and validate encoder presets from JSON via the Pydantic schema.

    Read-only loader for the dark-release path (ENCODER_USE_JSON=1).
    Validation failures raise pydantic.ValidationError.
    Returns the existing Preset frozen-dataclass type so callers see the
    same interface as load_presets() and load_presets_json().
    """
    from core.encoder_schema import EncoderLibrary

    raw = json.loads(path.read_text(encoding="utf-8"))
    library = EncoderLibrary.model_validate(raw)
    return [
        Preset(
            id=p.id,
            group=p.group,
            name=p.name,
            description=p.description,
            details=p.details,
            params=tuple(p.params),
        )
        for p in library.presets
    ]


def load_user_presets_json(path: Path) -> list[Preset]:
    """Load user presets from encoder.user.json with .bak fallback.

    On JSONDecodeError or ValidationError, attempts <path>.bak. On second
    failure, logs warning, renames corrupt file to <path>.corrupt for
    manual recovery, and returns []. Never raises — never blocks startup.

    Returns [] if path does not exist (file optional, created on first save).
    """
    from core.encoder_schema import EncoderLibrary

    logger = logging.getLogger(__name__)

    if not path.exists():
        return []

    def _try_load(candidate: Path) -> list[Preset] | None:
        try:
            raw = json.loads(candidate.read_text(encoding="utf-8"))
            sv = raw.get("schema_version", 1)
            if sv == 2:
                library = EncoderLibrary.model_validate(raw)
                return [
                    Preset(
                        id=p.id,
                        group=p.group,
                        name=p.name,
                        description=p.description,
                        details=p.details,
                        params=tuple(p.params),
                    )
                    for p in library.presets
                ]
            entries = raw["presets"]
            ids = derive_ids_for_presets(
                [(p["group"], p["name"]) for p in entries], kind="user"
            )
            logger.info(
                "Migrated %d user preset(s) from schema v1 to v2 "
                "(will rewrite on next save)",
                len(entries),
            )
            return [
                Preset(
                    id=ids[i],
                    group=p["group"],
                    name=p["name"],
                    description=p["description"],
                    details=p["details"],
                    params=tuple(p["params"]),
                )
                for i, p in enumerate(entries)
            ]
        except Exception:
            return None

    result = _try_load(path)
    if result is not None:
        return result

    logger.warning("Failed to parse %s; attempting .bak fallback", path)
    bak_path = path.with_suffix(path.suffix + ".bak")
    if bak_path.exists():
        result = _try_load(bak_path)
        if result is not None:
            logger.warning("Loaded user presets from %s after main failed", bak_path)
            return result

    corrupt_path = path.with_suffix(path.suffix + ".corrupt")
    try:
        os.replace(path, corrupt_path)
        logger.error(
            "Both %s and %s.bak failed to parse; renamed main to %s; returning [] presets",
            path,
            path,
            corrupt_path,
        )
    except OSError:
        logger.error(
            "Both %s and %s.bak failed to parse; could not rename for recovery; returning [] presets",
            path,
            path,
        )
    return []


def save_user_presets_json(path: Path, presets: list[Preset]) -> None:
    """Atomically save user presets to encoder.user.json.

    Uses core.atomic_write.save_json_atomic for .bak rotation + retry.
    Schema matches load_user_presets_json (envelope: schema_version=1,
    presets=list).
    """
    from core.atomic_write import save_json_atomic

    payload = {
        "schema_version": SCHEMA_VERSION,
        "presets": [asdict(p) for p in presets],
    }
    save_json_atomic(path, payload, indent=2)
