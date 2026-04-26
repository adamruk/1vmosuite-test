"""Pydantic schema for encoder preset validation (sub-phase 2c-c-1).

Read-only validation only; this module does NOT generate or modify
on-disk JSON. tools/generate_encoder_json.py remains the sole writer
to preserve the byte-identical-regen determinism contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class EncoderPreset(BaseModel):
    """Single encoder preset entry. Field set must match core.preset_loader.Preset.

    No uniqueness validator on (group, name): 13 known full_name collisions
    in current data are tolerated. Identity work deferred to sub-phase 2c-c-4.
    """

    model_config = ConfigDict(extra="forbid")

    group: str
    name: str
    description: str
    details: str
    params: list[str]


class EncoderLibrary(BaseModel):
    """Top-level envelope for assets/Encoder.json.

    schema_version pinned to Literal[1]; bumping requires a separate
    migration commit, not an in-place edit.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    presets: list[EncoderPreset]
