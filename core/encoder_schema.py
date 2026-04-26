"""Pydantic schema for encoder library JSON files (sub-phase 2c-c-1, 2c-c-4).

schema_version=2 (bumped from v1 in 2c-c-4): adds required `id` field on
EncoderPreset. See ADR-0006 for ID format, slug derivation rules, and
lazy migration semantics. v1 files with no `id` are loaded via the
legacy load path that auto-derives ids; this schema strictly accepts v2.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ID_PATTERN enforces:
#   builtin:foo                ✓
#   builtin:group/foo          ✓
#   builtin:group/foo-3        ✓
#   user:foo                   ✓
#   user:foo-2                 ✓
#   user:group/foo             ✗ (user namespace is flat)
ID_PATTERN = r"^(builtin:([a-z0-9-]+/)?[a-z0-9-]+(-\d+)?|user:[a-z0-9-]+(-\d+)?)$"


class EncoderPreset(BaseModel):
    """Single preset definition (2c-c-1 baseline; 2c-c-4 added `id`)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., pattern=ID_PATTERN)
    group: str
    name: str
    description: str
    details: str
    params: list[str]


class EncoderLibrary(BaseModel):
    """Top-level envelope for encoder library JSON.

    schema_version=2 (sub-phase 2c-c-4): id field required on every preset.
    Library-level uniqueness validation enforces ids are unique across
    presets list.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    presets: list[EncoderPreset]

    @model_validator(mode="after")
    def _ids_unique(self) -> "EncoderLibrary":
        seen: dict[str, int] = {}
        for idx, preset in enumerate(self.presets):
            if preset.id in seen:
                raise ValueError(
                    f"Duplicate preset id '{preset.id}' at indices "
                    f"{seen[preset.id]} and {idx}"
                )
            seen[preset.id] = idx
        return self
