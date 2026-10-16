"""Startup's three answers: refuse, warn, or go ahead.

The one that must not be got wrong in either direction. Too strict and a stale
lock leaves an application that will not start until somebody deletes a file
they do not know exists; too loose and two managers write the prefix list.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import registry, singleinstance as si  # noqa: E402


@pytest.fixture
def manager_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "manager_dir", lambda: tmp_path)
    return tmp_path


def write_lock(path, pid, version):
    (path / "manager.lock").write_text(
        json.dumps({"pid": pid, "version": version, "started": "now"}))


def test_nothing_running_is_clear(manager_dir, monkeypatch):
    monkeypatch.setattr(si, "find_standalone_installer", lambda *a, **k: [])
    c = si.check("1.0")
    assert c.action == si.CLEAR and c.may_start


def test_same_version_already_running_is_refused(manager_dir, monkeypatch):
    write_lock(manager_dir, os.getpid(), "1.0")     # our own pid: certainly alive
    c = si.check("1.0")
    assert c.action == si.REFUSE and not c.may_start
    assert str(os.getpid()) in c.detail


def test_a_different_version_only_warns(manager_dir, monkeypatch):
    """Refusing would make a half-upgraded machine unusable."""
    write_lock(manager_dir, os.getpid(), "0.9")
    c = si.check("1.0")
    assert c.action == si.WARN and c.may_start
    assert "0.9" in c.detail and "1.0" in c.detail


def test_a_stale_lock_is_taken_over_not_treated_as_a_conflict(manager_dir, monkeypatch):
    """A pid that is gone must not lock the application out forever."""
    dead = 999999
    while si._alive(dead):
        dead -= 1
    write_lock(manager_dir, dead, "1.0")
    monkeypatch.setattr(si, "find_standalone_installer", lambda *a, **k: [])
    assert si.check("1.0").action == si.CLEAR


def test_a_recycled_pid_is_not_mistaken_for_us(manager_dir, monkeypatch):
    """The pid is alive but is some unrelated program -- not a manager."""
    write_lock(manager_dir, os.getpid(), "1.0")
    monkeypatch.setattr(si, "_cmdline", lambda pid: "/usr/bin/some-other-thing")
    monkeypatch.setattr(si, "find_standalone_installer", lambda *a, **k: [])
    assert si.check("1.0").action == si.CLEAR


def test_a_standalone_installer_warns_and_names_its_prefix(manager_dir, monkeypatch):
    monkeypatch.setattr(si, "find_standalone_installer",
                        lambda *a, **k: [(4242, "/home/x/.AffinityLinux")])
    c = si.check("1.0")
    assert c.action == si.WARN and c.kind == "installer" and c.may_start
    assert "4242" in c.detail and "/home/x/.AffinityLinux" in c.detail


def test_acquire_then_release_leaves_nothing_behind(manager_dir, monkeypatch):
    monkeypatch.setattr(si, "find_standalone_installer", lambda *a, **k: [])
    si.acquire("1.0")
    assert si.read_lock()["pid"] == os.getpid()
    si.release()
    assert si.read_lock() is None


def test_release_does_not_delete_somebody_elses_lock(manager_dir):
    """A crashed manager's lock may already have been taken over."""
    write_lock(manager_dir, os.getpid() + 1, "1.0")
    si.release()
    assert si.read_lock() is not None


def test_a_corrupt_lock_file_does_not_stop_startup(manager_dir, monkeypatch):
    (manager_dir / "manager.lock").write_text("{not json")
    monkeypatch.setattr(si, "find_standalone_installer", lambda *a, **k: [])
    assert si.check("1.0").action == si.CLEAR


def test_installer_scan_cannot_match_this_process(manager_dir):
    """It scans command lines, so it must exclude itself -- the same
    self-matching trap that afprocs.sh had."""
    assert all(pid != os.getpid() for pid, _ in si.find_standalone_installer())
