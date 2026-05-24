"""Regression guard for B-050: RESULTS.md must grow, never shrink.

B-050: the manager-review skill overwrote RESULTS.md on every VERIFY run,
silently clobbering the cumulative audit history (672 lines lost in commit
7318ae4). The fix routes RESULTS.md writes through
`.claude/skills/manager-review/append_results.py::prepend_verdict_block`,
which reads-then-prepends. These tests prove a SECOND consecutive write does
not reduce the line count and that the first verdict's marker survives — the
exact property that was broken.

ADR-0003 narrow exception: pure-Python, deterministic, single-purpose.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_HELPER = (
    Path(__file__).resolve().parent.parent.parent
    / ".claude"
    / "skills"
    / "manager-review"
    / "append_results.py"
)


def _load_helper():
    spec = importlib.util.spec_from_file_location("append_results", _HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_second_run_does_not_reduce_line_count(tmp_path):
    """Two consecutive verdict writes: the file must grow, not shrink."""
    mod = _load_helper()
    results = tmp_path / "RESULTS.md"

    block1 = (
        "## VERDICT — branch-a @ aaaaaaa — 2026-05-24\n\nFirst verdict MARKER_ONE.\n"
    )
    mod.prepend_verdict_block(str(results), block1)
    after_1st = results.read_text(encoding="utf-8")
    lines_1 = len(after_1st.splitlines())

    block2 = (
        "## VERDICT — branch-b @ bbbbbbb — 2026-05-25\n\nSecond verdict MARKER_TWO.\n"
    )
    mod.prepend_verdict_block(str(results), block2)
    after_2nd = results.read_text(encoding="utf-8")
    lines_2 = len(after_2nd.splitlines())

    # The core B-050 invariant: never shrink.
    assert lines_2 > lines_1, f"file shrank: {lines_1} -> {lines_2}"
    # Both verdicts present; the first survived the second write.
    assert "MARKER_ONE" in after_2nd
    assert "MARKER_TWO" in after_2nd
    # Newest-first: the second (newest) block precedes the first.
    assert after_2nd.index("MARKER_TWO") < after_2nd.index("MARKER_ONE")
    # The separator was inserted between runs.
    assert "\n---\n" in after_2nd


def test_first_run_creates_file_with_block(tmp_path):
    """First write against a non-existent RESULTS.md just lays down the block."""
    mod = _load_helper()
    results = tmp_path / "RESULTS.md"
    assert not results.exists()
    mod.prepend_verdict_block(str(results), "## VERDICT — x @ ccccccc\n\nMARKER.\n")
    content = results.read_text(encoding="utf-8")
    assert "MARKER" in content
    # No dangling separator when there was no prior content.
    assert "---" not in content


def test_preexisting_history_survives(tmp_path):
    """A pre-existing (hand-written) history block is carried through verbatim."""
    mod = _load_helper()
    results = tmp_path / "RESULTS.md"
    history = "# RESULTS.md\n\nOld Phase 3 history HISTORY_MARKER kept here.\n"
    results.write_text(history, encoding="utf-8")
    lines_before = len(history.splitlines())

    mod.prepend_verdict_block(
        str(results), "## VERDICT — new @ ddddddd\n\nNEW_MARKER.\n"
    )
    after = results.read_text(encoding="utf-8")
    assert "HISTORY_MARKER" in after  # nothing clobbered
    assert "NEW_MARKER" in after
    assert len(after.splitlines()) > lines_before
