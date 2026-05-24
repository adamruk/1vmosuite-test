"""Smoke test for the "Group|Name" pipe-split strip fix (B-020).

B-020: the Add and Edit encoder handlers split the EncoderDialog name
field on "|" but did not `.strip()` the halves, so `"Test | My Preset"`
produced `group="Test "` / `name=" My Preset"`. Group lookups elsewhere
use exact string match and silently missed. The split is now factored
into the pure `auto_render._split_group_name`, exercised here directly
(no QWidget needed); both the Add/Clone helper and the Edit handler call it.

ADR-0003 narrow exception: pure-Python, deterministic, single-purpose.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from auto_render import _split_group_name  # noqa: E402


def test_strips_whitespace_around_pipe():
    """The backlog's canonical case: "Test | My Preset"."""
    group, name = _split_group_name("Test | My Preset")
    assert group == "Test"
    assert name == "My Preset"


def test_no_pipe_returns_empty_group_and_full_name():
    """No pipe -> group is empty, name is the full (unsplit) string."""
    group, name = _split_group_name("My Preset")
    assert group == ""
    assert name == "My Preset"


def test_pipe_without_adjacent_whitespace_unchanged():
    """The common no-whitespace case must be unaffected by the strip."""
    group, name = _split_group_name("Group|Name")
    assert group == "Group"
    assert name == "Name"


def test_only_first_pipe_splits():
    """split('|', 1): a second pipe stays inside the name half."""
    group, name = _split_group_name("Grp | a | b")
    assert group == "Grp"
    assert name == "a | b"
