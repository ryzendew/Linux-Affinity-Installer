"""Progress from a worker thread, as fast as rsync gives it.

The first backup of a real prefix died 2026-10-01 with a RecursionError and a
core dump: each queued progress report called processEvents, which delivered
the next report, which called processEvents ... a thousand deep. These run the
real methods against a real event loop and a real thread.
"""
import inspect
import re
from pathlib import Path

import pytest
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
QAPP = QApplication.instance() or QApplication([])
REPORTS = 5000                  # well past Python's recursion limit


class Flood(QThread):
    progress = pyqtSignal(int)

    def run(self):
        for i in range(REPORTS):
            self.progress.emit(i * 100 // REPORTS)


@pytest.fixture
def live_window(window, monkeypatch):
    """The stand-in window, but with the real processEvents put back."""
    import AffinityLinuxManager as app
    from PyQt6.QtCore import QCoreApplication
    monkeypatch.setattr(app.QApplication, "processEvents",
                        staticmethod(QCoreApplication.processEvents))
    w, reg, prefixlog = window
    written = []
    monkeypatch.setattr(prefixlog, "write", lambda name, text: written.append(text))
    w.progress.maximum = lambda: 100
    w._busy_prefix = "Managed"
    return w, written, app


def drain(thread):
    thread.start()
    while not thread.isFinished():
        QAPP.processEvents()
    QAPP.processEvents()


def test_a_flood_of_progress_does_not_recurse(live_window):
    w, written, _ = live_window
    errors = []
    flood = Flood()

    def slot(pct):
        try:
            w._busy_progress(pct, f"Backing up — {pct}%")
        except RecursionError as exc:          # what used to abort the process
            errors.append(exc)

    flood.progress.connect(slot)
    drain(flood)
    assert errors == []
    # Every tenth percent, once each -- not five thousand lines in the log.
    assert written == [f"Backing up — {p}%" for p in range(0, 100, 10)]


def test_even_a_signal_wired_to_busy_step_cannot_nest(live_window):
    """The wrong method, connected anyway: the guard keeps it flat."""
    w, _, _ = live_window
    depth = {"now": 0, "max": 0}
    real = w._show_step

    def counting(*a, **k):
        depth["now"] += 1
        depth["max"] = max(depth["max"], depth["now"])
        try:
            return real(*a, **k)
        finally:
            depth["now"] -= 1

    w._show_step = counting
    errors = []
    flood = Flood()

    def slot(pct):
        try:
            w._busy_step(pct, f"Copying — {pct}%")
        except RecursionError as exc:
            errors.append(exc)

    flood.progress.connect(slot)
    drain(flood)
    assert errors == [] and depth["max"] <= 2


def test_no_signal_is_connected_to_busy_step():
    """_busy_step processes events, so it is only for work on the UI thread."""
    source = (ROOT / "AffinityLinuxManager.py").read_text()
    wired = re.findall(r"\.connect\(\s*(?:lambda[^:]*:\s*)?self\._busy_step", source)
    assert wired == []
