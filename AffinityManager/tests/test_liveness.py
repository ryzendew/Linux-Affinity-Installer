"""Telling a running Affinity from what an earlier session left behind.

The fake /proc below is modelled on the working prefix as found on 2026-10-01:
Affinity closed for two weeks, and 22 processes still there -- two stranded
AffinityHook launchers with their services and crash handlers, a third set of
services, a diagnostic tool, and no wineserver. The manager called that
"running", refused every operation, and asked for an Affinity to be closed that
had not been open for a fortnight.
"""
import os
import signal
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import liveness  # noqa: E402

TICKS = os.sysconf("SC_CLK_TCK")
BOOT = 1_700_000_000


@pytest.fixture
def proc(tmp_path):
    root = tmp_path / "proc"
    root.mkdir()
    (root / "stat").write_text(f"cpu 1 2 3\nbtime {BOOT}\n")
    prefix = tmp_path / ".AffinityLinux"
    prefix.mkdir()
    other = tmp_path / ".AffinityLinux-winetest"
    other.mkdir()
    pids = iter(range(1000, 2000))

    def spawn(comm, started, where=prefix):
        pid = next(pids)
        d = root / str(pid)
        d.mkdir()
        (d / "environ").write_bytes(
            b"HOME=/home/x\0WINEPREFIX=" + str(where).encode() + b"\0")
        (d / "comm").write_text(comm + "\n")
        ticks = int((started - BOOT) * TICKS)
        (d / "stat").write_text(f"{pid} ({comm}) S " + " ".join(["0"] * 18)
                                + f" {ticks} 0 0\n")
        return pid

    return type("Proc", (), {"root": root, "prefix": prefix, "other": other,
                             "spawn": staticmethod(spawn)})()


def scan(proc, prefix=None):
    return liveness.scan(prefix or proc.prefix, proc_root=proc.root)


TWO_WEEKS_AGO = time.time() - 14 * 86400


def leftovers_like_the_working_prefix(proc):
    for comm in ("services.exe", "explorer.exe", "svchost.exe", "plugplay.exe",
                 "rpcss.exe", "AffinityHook.ex", "conhost.exe", "crashpad_handle"):
        proc.spawn(comm, TWO_WEEKS_AGO)
    proc.spawn("keyspy.exe", TWO_WEEKS_AGO + 1000)


# ── what counts as running ─────────────────────────────────────────────────

def test_leftovers_are_not_running(proc):
    leftovers_like_the_working_prefix(proc)
    a = scan(proc)
    assert a.state == liveness.LEFTOVERS
    assert a.running_pids == []
    assert [p.name for p in a.of(liveness.HOOK)] == ["AffinityHook.exe"]
    assert [p.name for p in a.of(liveness.OTHER)] == ["keyspy.exe"]


def test_affinity_exe_is_running(proc):
    pid = proc.spawn("Affinity.exe", time.time() - 600)
    a = scan(proc)
    assert a.state == liveness.RUNNING and a.running_pids == [pid]


def test_a_launcher_that_has_just_started_counts_as_running(proc):
    """For the first moments of a launch the hook is all there is, and a
    second launch then would kill the first."""
    pid = proc.spawn("AffinityHook.ex", time.time() - 10)
    assert scan(proc).running_pids == [pid]


def test_a_launcher_long_left_alone_is_a_leftover(proc):
    proc.spawn("AffinityHook.ex", time.time() - liveness.HOOK_GRACE_SECONDS - 60)
    assert scan(proc).state == liveness.LEFTOVERS


def test_nothing_at_all_is_quiet(proc):
    assert scan(proc).state == liveness.QUIET


def test_without_a_wineserver_they_are_orphaned(proc):
    leftovers_like_the_working_prefix(proc)
    assert scan(proc).orphaned
    proc.spawn("wineserver", time.time())
    assert not scan(proc).orphaned


# ── whose processes ────────────────────────────────────────────────────────

def test_another_prefix_whose_name_starts_the_same_is_not_counted(proc):
    """.AffinityLinux is a prefix of .AffinityLinux-winetest."""
    proc.spawn("Affinity.exe", time.time(), where=proc.other)
    assert scan(proc).state == liveness.QUIET


def test_a_prefix_reached_through_a_symlink_is_the_same_prefix(proc, tmp_path):
    link = tmp_path / "work-link"
    link.symlink_to(proc.prefix)
    proc.spawn("Affinity.exe", time.time(), where=link)
    assert scan(proc).state == liveness.RUNNING


# ── what the banner says ───────────────────────────────────────────────────

def test_the_summary_says_what_is_there_and_since_when(proc):
    leftovers_like_the_working_prefix(proc)
    text = scan(proc).summary()
    assert "Affinity is not running" in text
    assert "1 Affinity launcher;" in text
    assert "keyspy.exe" in text
    assert time.strftime("%Y-%m-%d", time.localtime(TWO_WEEKS_AGO)) in text
    assert "will not exit by themselves" in text


# ── ending them ────────────────────────────────────────────────────────────

def test_ending_leftovers_terms_then_kills_only_this_prefix(proc):
    leftovers_like_the_working_prefix(proc)
    elsewhere = proc.spawn("services.exe", TWO_WEEKS_AGO, where=proc.other)
    sent = []

    def kill(pid, sig):
        sent.append((pid, sig))
        if sig == signal.SIGTERM and pid % 2 == 0:
            import shutil
            shutil.rmtree(proc.root / str(pid))      # exits on TERM

    notes = liveness.end_leftovers(proc.prefix, proc_root=proc.root, kill=kill,
                                   sleep=lambda s: None)
    termed = {p for p, s in sent if s == signal.SIGTERM}
    killed = {p for p, s in sent if s == signal.SIGKILL}
    assert elsewhere not in termed | killed, "touched another prefix"
    assert len(termed) == 9
    assert killed == {p for p in termed if p % 2}, "forced only what survived TERM"
    assert any("had to be forced" in n for n in notes)


def test_ending_refuses_if_affinity_started_meanwhile(proc):
    """Scanned again at the moment of ending: whatever the dialog showed may
    be out of date, and ending Affinity loses what is open in it."""
    leftovers_like_the_working_prefix(proc)
    proc.spawn("Affinity.exe", time.time())
    sent = []
    with pytest.raises(liveness.StillRunning):
        liveness.end_leftovers(proc.prefix, proc_root=proc.root,
                               kill=lambda p, s: sent.append(p),
                               sleep=lambda s: None)
    assert sent == []


def test_a_hung_affinity_is_ended_only_when_asked_for_explicitly(proc):
    pid = proc.spawn("Affinity.exe", time.time() - 300)
    sent = []
    liveness.end_leftovers(proc.prefix, include_affinity=True,
                           proc_root=proc.root,
                           kill=lambda p, s: sent.append((p, s)),
                           sleep=lambda s: None)
    assert (pid, signal.SIGTERM) in sent
