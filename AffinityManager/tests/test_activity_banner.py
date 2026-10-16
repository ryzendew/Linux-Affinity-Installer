"""The banner that says what is running in a prefix, and keeps saying it.

The real widget, offscreen. What stands in is liveness.scan -- the world is
whatever the test says /proc holds at each tick -- and the two ways of ending
processes, so nothing is ever signalled.
"""
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import AffinityLinuxManager as app  # noqa: E402
from affinity_manager import liveness  # noqa: E402

QAPP = QApplication.instance() or QApplication([])


def activity(*procs):
    return liveness.Activity("/p", [liveness.Proc(pid, comm, time.time() - 3600, group)
                                    for pid, comm, group in procs])


AFFINITY = (4242, "Affinity.exe", liveness.AFFINITY)
LEFTOVER = (77, "services.exe", liveness.SERVICE)


@pytest.fixture
def world(monkeypatch, tmp_path):
    state = {"now": activity(), "ended": [], "confirm": False}
    monkeypatch.setattr(app.liveness, "scan", lambda prefix, *a, **k: state["now"])

    def end(prefix, *, include_affinity=False, **kw):
        state["ended"].append(include_affinity)
        state["now"] = activity()
        return ["ended Affinity.exe (pid 4242, from x)"]

    monkeypatch.setattr(app.liveness, "end_leftovers", end)
    monkeypatch.setattr(app.ConfirmDialog, "ask",
                        staticmethod(lambda *a, **k: state["confirm"]))
    monkeypatch.setattr(app.QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(app.QMessageBox, "warning", lambda *a, **k: None)
    state["prefix"] = tmp_path
    return state


def banner(world, **kw):
    b = app.ActivityBanner(None, world["prefix"], name="Work", **kw)
    seen = []
    b.changed.connect(seen.append)
    return b, seen


# ── it checks again, by itself ───────────────────────────────────────────────

def test_running_is_shown_and_blocks(world):
    world["now"] = activity(AFFINITY)
    b, _ = banner(world, waiting_for="back it up")
    assert b.blocks() and not b.isHidden()
    assert "Affinity is running in Work" in b.heading.text()
    assert "Close it to back it up" in b.detail.text()


def test_closing_affinity_is_noticed_without_reopening_anything(world):
    """The bug: closed Affinity, and the dialog still said it was running."""
    world["now"] = activity(AFFINITY)
    b, seen = banner(world)
    world["now"] = activity()
    b.check()                                   # what the timer does
    assert not b.blocks()
    assert seen[-1] == liveness.QUIET
    assert "Affinity has closed" in b.heading.text() and not b.isHidden()
    b._closed_timer.stop()
    b._paint()
    assert b.isHidden(), "the green confirmation should go away"


def test_a_banner_whose_timer_is_gone_stops_instead_of_raising(world):
    """The crash of 2026-10-14: check ran with _closed_timer already deleted,
    the RuntimeError escaped the slot, and PyQt aborted the manager."""
    from PyQt6 import sip
    world["now"] = activity(AFFINITY)
    b, _ = banner(world)
    world["now"] = activity()
    sip.delete(b._closed_timer)
    b.check()                                   # must not raise
    assert not b._timer.isActive(), "a banner missing its parts stops polling"


def test_it_polls(world):
    b, _ = banner(world)
    assert b._timer.isActive() and b._timer.interval() <= 2000


def test_nothing_running_shows_nothing(world):
    b, _ = banner(world)
    assert b.isHidden() and not b.blocks()


# ── leftovers ───────────────────────────────────────────────────────────────

def test_leftovers_block_only_where_the_owner_says(world):
    world["now"] = activity(LEFTOVER)
    b, _ = banner(world)
    assert not b.blocks() and "do not stop this" in b.detail.text()
    b.set_leftovers_block(True)
    assert b.blocks() and "end them to continue" in b.heading.text()


def test_leftovers_offer_to_end_them(world):
    world["now"] = activity(LEFTOVER)
    b, _ = banner(world)
    assert not b.end_button.isHidden() and b.end_button.text() == "End them…"


# ── ending a running Affinity ───────────────────────────────────────────────

def test_a_running_affinity_can_be_ended_from_the_banner(world):
    world["now"] = activity(AFFINITY)
    b, _ = banner(world)
    assert not b.end_button.isHidden() and b.end_button.text() == "End Affinity…"
    world["confirm"] = True
    b._end()
    assert world["ended"] == [True], "Affinity itself must be included"
    assert not b.blocks()


def test_ending_affinity_needs_the_confirmation(world):
    world["now"] = activity(AFFINITY)
    b, _ = banner(world)
    world["confirm"] = False
    b._end()
    assert world["ended"] == [] and b.blocks()


def test_a_different_affinity_than_the_one_confirmed_is_not_ended(world, monkeypatch):
    """Closed and started again while the confirmation was up: the new one is
    not the one the user agreed to end."""
    world["now"] = activity(AFFINITY)
    b, _ = banner(world)

    def confirm_then_restart(*a, **k):
        world["now"] = activity((5151, "Affinity.exe", liveness.AFFINITY))
        return True

    monkeypatch.setattr(app.ConfirmDialog, "ask", staticmethod(confirm_then_restart))
    b._end()
    assert world["ended"] == []


def test_leftovers_are_ended_without_touching_affinity(world, monkeypatch):
    world["now"] = activity(LEFTOVER)
    b, _ = banner(world)
    monkeypatch.setattr(app.QMessageBox, "exec", lambda self: None)
    monkeypatch.setattr(app.QMessageBox, "clickedButton",
                        lambda self: next(x for x in self.buttons()
                                          if x.text() == "End them"))
    b._end()
    assert world["ended"] == [False]
