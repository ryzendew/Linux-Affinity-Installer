"""renderer.restore_vulkan: a prefix that lost renderer=vulkan gets it back.

The prefixes here are fake (a user.reg and an Affinity.exe); liveness is
stubbed, since what matters is that a running prefix is never edited.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import liveness, renderer  # noqa: E402

HEADER = "WINE REGISTRY Version 2\n;; All keys relative to \\\\User\\\\S-1-5-21-0-0-0-1000\n\n#arch=win64\n"


STATE = {}


@pytest.fixture
def prefix(tmp_path, monkeypatch):
    app = tmp_path / "drive_c" / "Program Files" / "Affinity" / "Affinity"
    app.mkdir(parents=True)
    (app / "Affinity.exe").write_bytes(b"MZ")
    state = {"value": liveness.QUIET}

    class Activity:
        @property
        def state(self):
            return state["value"]

    monkeypatch.setattr(liveness, "scan", lambda p, **k: Activity())
    STATE.clear(); STATE.update(state)
    STATE["ref"] = state
    return tmp_path


def test_a_missing_key_is_added(prefix):
    (prefix / "user.reg").write_text(HEADER + '\n[Software\\\\Wine] 1\n"Version"="win11"\n')
    assert renderer.restore_vulkan(prefix) is True
    assert renderer.renderer_setting(prefix) == "vulkan"
    text = (prefix / "user.reg").read_text()
    assert text.startswith(HEADER) and '"Version"="win11"' in text


def test_a_value_missing_from_an_existing_key_is_added_to_it(prefix):
    (prefix / "user.reg").write_text(
        HEADER + '\n[Software\\\\Wine\\\\Direct3D] 1792152235\n#time=1dd5d666af3775a\n"csmt"=dword:00000001\n')
    assert renderer.restore_vulkan(prefix) is True
    text = (prefix / "user.reg").read_text()
    assert text.count("[Software\\\\Wine\\\\Direct3D]") == 1
    assert '#time=1dd5d666af3775a\n"renderer"="vulkan"\n"csmt"' in text


def test_a_chosen_renderer_is_kept(prefix):
    original = HEADER + '\n[Software\\\\Wine\\\\Direct3D] 1\n"renderer"="gl"\n'
    (prefix / "user.reg").write_text(original)
    assert renderer.restore_vulkan(prefix) is False
    assert (prefix / "user.reg").read_text() == original


def test_a_running_prefix_is_not_edited(prefix):
    original = HEADER
    (prefix / "user.reg").write_text(original)
    STATE["ref"]["value"] = liveness.RUNNING
    assert renderer.restore_vulkan(prefix) is False
    assert (prefix / "user.reg").read_text() == original


def test_a_prefix_without_affinity_is_not_edited(tmp_path, monkeypatch):
    (tmp_path / "user.reg").write_text(HEADER)
    assert renderer.restore_vulkan(tmp_path) is False
    assert (tmp_path / "user.reg").read_text() == HEADER


def test_the_file_mode_is_kept(prefix):
    reg = prefix / "user.reg"
    reg.write_text(HEADER)
    reg.chmod(0o640)
    assert renderer.restore_vulkan(prefix) is True
    assert reg.stat().st_mode & 0o777 == 0o640
