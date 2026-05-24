"""Smoke test for the Clone preset id-derivation helper (B-018).

B-018 adds a Clone button so a user can turn a read-only built-in preset
(ADR-0006) into an editable user-namespace copy. The id-minting logic is
factored into the pure module-level helper
`auto_render._allocate_user_preset_id`, shared by Add and Clone, so it can
be exercised without constructing the QWidget. This test pins:

  - a cloned built-in always yields a `user:<slug>` id (flat user
    namespace, never `builtin:` / never group-prefixed);
  - the slug matches ADR-0006 derivation (via `core.preset_loader.derive_slug`);
  - the 2c-c-4 disambiguation suffix (`-2`, `-3`, ...) is applied only on
    collision with an existing user id.

The UI wiring itself (Clone button always enabled, EncoderDialog rename
flow, source preset left untouched) is exercised by hand — see the
MANUAL-VERIFIED note in the B-018 CHANGELOG entry.

ADR-0003 narrow exception: pure-Python, deterministic, single-purpose.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from auto_render import _allocate_user_preset_id  # noqa: E402
from core.preset_loader import derive_slug  # noqa: E402


def test_clone_yields_user_namespace_id():
    """A built-in preset name clones to a user:-prefixed id (never builtin:)."""
    new_id = _allocate_user_preset_id("Line", set())
    assert new_id == "user:line"
    assert new_id.startswith("user:")
    assert not new_id.startswith("builtin:")


def test_slug_matches_adr0006_derivation():
    """The slug body equals core.preset_loader.derive_slug (ADR-0006)."""
    name = "5s Cycle Zoom"
    new_id = _allocate_user_preset_id(name, set())
    assert new_id == f"user:{derive_slug(name)}"
    assert new_id == "user:5s-cycle-zoom"


def test_disambiguation_on_collision():
    """A -N suffix (N>=2) is appended only when the bare id already exists."""
    existing = {"user:line"}
    assert _allocate_user_preset_id("Line", existing) == "user:line-2"
    existing = {"user:line", "user:line-2"}
    assert _allocate_user_preset_id("Line", existing) == "user:line-3"
    # No collision -> no suffix.
    assert _allocate_user_preset_id("Line", {"user:other"}) == "user:line"


def test_empty_slug_falls_back_to_preset():
    """A name with no alphanumeric content falls back to user:preset."""
    assert _allocate_user_preset_id("!!!", set()) == "user:preset"
