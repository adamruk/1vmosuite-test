"""F-001: partial_path() must insert .partial BEFORE the extension
so FFmpeg can infer the muxer from the file's actual extension."""
from core.naming_utils import partial_path


def test_mp4_extension_preserved():
    assert partial_path("out.mp4") == "out.partial.mp4"


def test_path_with_directory():
    assert partial_path("/tmp/sub/out.mp4") == "/tmp/sub/out.partial.mp4"


def test_no_extension_appends_partial():
    assert partial_path("out") == "out.partial"


def test_double_extension_keeps_only_last():
    # .tar.gz collapses; only the last segment is treated as ext.
    # Acceptable for video files.
    assert partial_path("clip.tar.gz") == "clip.tar.partial.gz"


def test_windows_path():
    assert partial_path(r"C:\Users\adamm\out.mp4") == r"C:\Users\adamm\out.partial.mp4"
