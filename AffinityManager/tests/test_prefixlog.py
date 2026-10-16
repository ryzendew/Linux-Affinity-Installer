"""One log per prefix, and an offset that means something.

The offset is the load-bearing part: it is what lets a recovery message quote
where an operation stopped instead of wherever the file happens to end.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import prefixlog, registry  # noqa: E402


@pytest.fixture
def logs(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "manager_dir", lambda: tmp_path)
    return tmp_path / "logs"


def test_two_prefixes_do_not_share_a_file(logs):
    prefixlog.write("Working", "one")
    prefixlog.write("3.3 Test", "two")
    assert prefixlog.path_for("Working") != prefixlog.path_for("3.3 Test")
    assert "two" not in prefixlog.path_for("Working").read_text()


def test_names_that_differ_only_by_spacing_do_not_collapse(logs):
    assert prefixlog.path_for("Affinity 33") != prefixlog.path_for("Affinity33")


def test_begin_returns_the_offset_the_operation_started_at(logs):
    prefixlog.write("Working", "before the operation")
    start = prefixlog.begin("Working", "Install Affinity")
    prefixlog.write("Working", "during the operation")
    text = prefixlog.read_from("Working", start)
    assert "Install Affinity" in text and "during" in text
    assert "before the operation" not in text


def test_writing_never_raises_even_when_the_directory_cannot_be_made(logs, monkeypatch):
    """Losing a log line must not take down the operation it describes."""
    monkeypatch.setattr(prefixlog.Path, "mkdir",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no")))
    prefixlog.write("Working", "this should vanish quietly")


def test_offset_of_an_absent_log_is_zero(logs):
    assert prefixlog.offset("Never Used") == 0


def test_a_large_log_is_rotated_once(logs, monkeypatch):
    monkeypatch.setattr(prefixlog, "MAX_BYTES", 200)
    for i in range(60):
        prefixlog.write("Working", f"line {i} padding padding padding")
    path = prefixlog.path_for("Working")
    assert path.with_suffix(".log.1").exists()
    assert path.stat().st_size < 2000          # the live one started over


def test_tail_returns_the_end(logs):
    for i in range(50):
        prefixlog.write("Working", f"line {i}")
    assert "line 49" in prefixlog.tail("Working", lines=3)
    assert "line 10" not in prefixlog.tail("Working", lines=3)
