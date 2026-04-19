"""Shared encoder preset loading for 1vmo Suite apps.

Currently used only by auto_render.py. The other 3 apps use hardcoded
ffmpeg parameters and do not parse Encoder.txt.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


@dataclass(frozen=True)
class Preset:
    """A single encoder preset parsed from Encoder.txt.

    The legacy name field used in auto_render's UI was the concatenated
    form '{group}|{name}'. Use .full_name when that exact form is needed
    (e.g., comparing against persisted self.selected_encoders strings).
    """
    group: str            # column 1, may be '' for ungrouped
    name: str             # column 2, required non-empty
    description: str      # column 3
    details: str          # column 4, may be ''
    params: tuple[str, ...]   # column 5, whitespace-tokenized

    @property
    def full_name(self) -> str:
        """Concatenated '{group}|{name}' form used historically."""
        return f'{self.group}|{self.name}'


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
    presets: list[Preset] = []
    if not path.exists():
        return presets
    with open(path, 'r', encoding='utf-8') as f:
        for line_number, raw_line in enumerate(f, start=1):
            try:
                if raw_line.strip():
                    parts = raw_line.strip().rsplit('|', 1)
                    if len(parts) != 2:
                        _report(on_error, line_number, raw_line.strip(), 'no pipe separator')
                        continue
                    header_parts = parts[0].split('|', 3)
                    if len(header_parts) < 3:
                        _report(on_error, line_number, raw_line.strip(), 'fewer than 3 header parts')
                        continue
                    group = header_parts[0].strip()
                    name = header_parts[1].strip()
                    description = header_parts[2].strip()
                    details = header_parts[3].strip() if len(header_parts) > 3 else ''
                    code = parts[1].strip()
                    if not name:
                        _report(on_error, line_number, raw_line.strip(), 'empty name')
                        continue
                    presets.append(Preset(
                        group=group,
                        name=name,
                        description=description,
                        details=details,
                        params=tuple(code.split()),
                    ))
            except Exception as e:
                _report(on_error, line_number, raw_line.strip(), f'exception: {str(e)}')
                continue
    return presets


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
    if reason in ('no pipe separator', 'fewer than 3 header parts'):
        print(f'Skipping invalid encoder option at line {line_num}: {line}')
    elif reason == 'empty name':
        print(f'Skipping encoder option with empty name at line {line_num}')
    elif reason.startswith('exception: '):
        exc = reason[len('exception: '):]
        print(f'Error parsing line {line_num}: {exc}')
    else:
        print(f'[preset_loader] line {line_num}: {reason}')


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
