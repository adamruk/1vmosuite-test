"""Smoke tests for `core.orchestration.diagnostic_bundle`. ADR-0003 narrow."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from core.orchestration.diagnostic_bundle import export_diagnostic_zip


def test_export_with_no_files(tmp_path: Path):
    target = tmp_path / "out" / "bundle.zip"
    export_diagnostic_zip(tmp_path, target)
    assert target.is_file()
    with zipfile.ZipFile(target) as zf:
        assert zf.namelist() == []


def test_export_includes_queue_and_scores(tmp_path: Path):
    (tmp_path / "queue.json").write_text('{"a":1}', "utf-8")
    (tmp_path / "scores.json").write_text('{"b":2}', "utf-8")
    target = tmp_path / "bundle.zip"
    export_diagnostic_zip(tmp_path, target)
    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
    assert "queue.json" in names
    assert "scores.json" in names


def test_config_sanitized_strips_output_dir(tmp_path: Path):
    raw = {
        "output_dir": "/secret/path",
        "input_files": ["/secret/clip.mp4"],
        "num_threads": 3,
    }
    (tmp_path / "config_video_renderer.json").write_text(json.dumps(raw), "utf-8")
    target = tmp_path / "bundle.zip"
    export_diagnostic_zip(tmp_path, target)
    with zipfile.ZipFile(target) as zf:
        content = json.loads(zf.read("config_video_renderer.json"))
    assert content["output_dir"] == "<redacted>"
    assert content["input_files"] == ["clip.mp4"]
    assert content["num_threads"] == 3


def test_logs_dir_recursively_included(tmp_path: Path):
    logs = tmp_path / "logs" / "batchA"
    logs.mkdir(parents=True)
    (logs / "task1.log").write_text("hello", "utf-8")
    target = tmp_path / "bundle.zip"
    export_diagnostic_zip(tmp_path, target)
    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
    assert any(n.endswith("batchA/task1.log") for n in names)
