#!/usr/bin/env python3
"""Affinity on Linux Manager -- several Affinity prefixes, tracked.

AffinityOnLinux installs one Affinity, into ~/.AffinityLinux, and remembers one
custom location. That is the right shape for most people and the wrong shape as
soon as you need two: a working install you cannot afford to break, and a new
release to try.

This manages the set. It does not install anything itself -- it runs the
AffinityOnLinux installer against a prefix you name, which is the only part
that was missing.

    ./AffinityLinuxManager.py
"""

from __future__ import annotations

import contextlib
import html
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt6 import sip
from PyQt6.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QButtonGroup,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from affinity_manager import (
    __version__,
    aol,
    backups,
    coldstart,
    commands as commands_mod,
    defaultentry,
    desktopentry,
    discover,
    hosted,
    installer,
    liveness,
    prefsseed,
    removal,
    renaming,
    snapshots,
    oplock,
    prefixlog,
    prefixstate,
    probe,
    release,
    renderer,
    singleinstance,
    registry,
    ui,
    maintenance,
)


class ProbeThread(QThread):
    """Prefix inspection off the UI thread.

    disk_usage walks the tree, and a prefix is several gigabytes across tens of
    thousands of files on a disk that may be spun down. Doing that inline froze
    the window for seconds at a time."""

    done = pyqtSignal(list)

    def __init__(self, entries):
        super().__init__()
        self.entries = list(entries)

    def run(self):
        """One unreadable prefix must not cost the others, or the window.

        probe.describe walks the prefix, and iterdir raises for a directory
        that can be traversed but not listed: a prefix installed under sudo, a
        mode-0111 directory, an sshfs or NFS mount whose connection has
        dropped so is_dir() answers from cache and iterdir() returns ESTALE.
        Unguarded, that exception left QThread.run and Qt aborted the process
        -- the manager vanished, with no message, because one row in a list
        could not be measured."""
        rows = []
        for entry in self.entries:
            try:
                info = probe.describe(entry["path"])
                info["size"] = (probe.disk_usage(entry["path"])
                                if info["exists"] else 0)
                # A prefix that lost renderer=vulkan stays on OpenGL however
                # it is started; put it back while nothing runs in it.
                try:
                    info["renderer_restored"] = renderer.restore_vulkan(entry["path"])
                except OSError:
                    info["renderer_restored"] = False
            except Exception as exc:
                info = {"path": entry["path"], "exists": False,
                        "is_prefix": False, "has_affinity": False,
                        "affinity_version": None, "wine": None,
                        "wine_builds": [], "running": False, "pids": [],
                        "size": 0, "unreadable": str(exc)}
            rows.append((entry, info))
        self.done.emit(rows)


class CloneThread(QThread):
    """Copying a prefix off the UI thread.

    Several gigabytes across tens of thousands of files. Inline, the window
    stops answering the compositor and the desktop offers to kill it."""

    done = pyqtSignal(list, str)
    progress = pyqtSignal(int)

    def __init__(self, plan):
        super().__init__()
        self.plan = plan

    def run(self):
        try:
            problems = maintenance.clone(self.plan, progress=self.progress.emit)
        except Exception as exc:                      # surfaced, not swallowed
            self.done.emit([], str(exc))
            return
        self.done.emit(problems, "")


def fit_to_contents(dialog, *, min_width=420):
    """Size a dialog to what it holds, once, on first show.

    Every dialog here used to carry a hand-picked setMinimumWidth, which is a
    guess that is wrong as soon as the content changes -- a prefix with five
    Wine builds and long names needs a wider box than one with two, and the
    fixed width either clipped the text or left half the dialog empty.

    Qt will do it: adjustSize() asks the layout what it wants. The parts worth
    adding are a floor, so a nearly empty dialog is not a postage stamp, and a
    ceiling at the available screen, so a list of thirty items does not open
    taller than the display and put its buttons out of reach."""
    dialog.adjustSize()
    want = dialog.sizeHint()
    screen = dialog.screen() or QApplication.primaryScreen()
    avail = screen.availableGeometry() if screen else None

    width = max(want.width(), min_width)
    height = want.height()
    if avail:
        width = min(width, int(avail.width() * 0.9))
        height = min(height, int(avail.height() * 0.85))
    dialog.resize(width, height)


class SizedDialog(QDialog):
    """A dialog that sizes itself to its contents the first time it is shown.

    Done in showEvent rather than at the end of __init__ because a layout does
    not know what it wants until its widgets have been polished by the
    stylesheet -- font sizes and padding come from ui.apply(), and asking
    before that gives a box sized for the wrong font."""

    FIT_MIN_WIDTH = 420

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_fitted", False):
            self._fitted = True
            fit_to_contents(self, min_width=self.FIT_MIN_WIDTH)


class ConfirmDialog(SizedDialog):
    """A destructive action, behind a deliberate tick and a button.

    This replaces typing the prefix name to confirm. Retyping a name proves
    dexterity, not intent -- and the name was printed on the same screen, so it
    was a copying exercise. A tick that arms the button is two deliberate acts
    against the same question, which is the thing actually worth requiring, and
    it does not punish anyone whose prefix is called
    AffinityLinux_26-09-16_-_Working_3.3_Test."""

    def __init__(self, parent, title, message, *, tick="Yes, I really want to do this",
                 confirm="Delete"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        ui.apply(self)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        body = QLabel(message)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(body)

        self.tick = ArmBox(tick, f"Required — {confirm} stays off until this is ticked.")
        layout.addWidget(self.tick)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText(confirm)
        self.ok.setEnabled(False)
        self.ok.setProperty("class", "danger")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # The tick arms the button; unticking disarms it again.
        self.tick.toggled.connect(self.ok.setEnabled)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
        fit_to_contents(self, min_width=520)

    @staticmethod
    def ask(parent, title, message, **kwargs) -> bool:
        dialog = ConfirmDialog(parent, title, message, **kwargs)
        return dialog.exec() == QDialog.DialogCode.Accepted and dialog.tick.isChecked()


class ArmBox(QFrame):
    """The tick that arms a destructive button -- made impossible to miss.

    It was a plain checkbox among the other rows, and the button it arms was
    greyed out with nothing to say why; the dialog looked broken. Now it sits
    in its own bordered box with a REQUIRED line under it, turns green when
    ticked, and the line says what is still missing when something else (a
    running prefix, nothing chosen) is what keeps the button off."""

    toggled = pyqtSignal(bool)

    def __init__(self, text, required="Required — the button stays off until "
                                      "this is ticked.", parent=None):
        super().__init__(parent)
        self.setObjectName("armBox")
        self.required = required
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)
        self.box = QCheckBox(text)
        font = self.box.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.15)
        self.box.setFont(font)
        layout.addWidget(self.box)
        self.line = QLabel(required)
        self.line.setWordWrap(True)
        layout.addWidget(self.line)
        self.box.toggled.connect(self._paint)
        self.box.toggled.connect(self.toggled.emit)
        self._note = None
        self._paint()

    def isChecked(self) -> bool:
        return self.box.isChecked()

    def setChecked(self, value: bool):
        self.box.setChecked(value)

    def set_note(self, note):
        self._note = note
        self._paint()

    def _paint(self, *_):
        on = self.box.isChecked()
        edge, fill = ("#3FBF6F", "rgba(63, 191, 111, 0.12)") if on \
            else ("#F5A623", "rgba(245, 166, 35, 0.12)")
        self.setStyleSheet(
            f"QFrame#armBox {{ border: 2px solid {edge}; border-radius: 8px; "
            f"background: {fill}; }}"
            "QFrame#armBox QLabel, QFrame#armBox QCheckBox "
            "{ background: transparent; border: none; }")
        if self._note:
            self.line.setText(f"<b>{html.escape(self._note)}</b>")
        else:
            self.line.setText("Ticked." if on else
                              f"<b>{html.escape(self.required)}</b>")


class ActivityBanner(QFrame):
    """What is running in a prefix, in a coloured band, checked every second
    and a half.

    This replaces a line of small amber text that was worked out once, when a
    dialog opened, and never again. Two things were wrong with it. It was easy
    to read past -- and it was what was stopping the button from working. And
    it went on saying Affinity was running after Affinity had been closed, so
    the only way out was to close the dialog and open it again, which did not
    help either, because what it had counted were processes left behind by
    sessions weeks old (see liveness).

    Three states, each its own colour, so the state reads before the words do:

      running    red. Affinity is open; what this dialog does must wait.
                 Offers to end it, behind a tick -- for one that has hung.
      leftovers  amber. Affinity is closed, but Wine processes from earlier
                 sessions are still there. Offers to end them.
      quiet      nothing shown -- except, straight after one of the others, a
                 green "closed" for a few seconds, so that what was blocking
                 visibly goes away rather than just vanishing.

    `blocking` says what the owner does about leftovers: a backup can be
    taken with them there, a restore over the prefix cannot. The owner listens
    to `changed` and re-checks its own buttons; the banner says why."""

    changed = pyqtSignal(str)

    INTERVAL_MS = 1500
    CLOSED_MS = 6000
    STYLE = {
        liveness.RUNNING: ("#5C1A1E", "#E5484D"),
        liveness.LEFTOVERS: ("#4A3410", "#F5A623"),
        "closed": ("#143D28", "#3FBF6F"),
    }

    def __init__(self, parent, prefix, *, name=None, waiting_for="",
                 leftovers_block=False):
        super().__init__(parent)
        self.setObjectName("activityBanner")
        self.prefix = Path(prefix) if prefix else None
        self.name = name or (self.prefix.name if self.prefix else "")
        self.waiting_for = waiting_for
        self.leftovers_block = leftovers_block
        self.activity = liveness.Activity(str(prefix or ""))
        self._shown = None
        self._gone = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(14)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.heading = QLabel("")
        self.heading.setWordWrap(True)
        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        text.addWidget(self.heading)
        text.addWidget(self.detail)
        layout.addLayout(text, 1)
        self.end_button = QPushButton("End them…")
        self.end_button.setToolTip("End the leftover Wine processes in this prefix")
        self.end_button.clicked.connect(self._end)
        layout.addWidget(self.end_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.hide()

        self._closed_timer = QTimer(self)
        self._closed_timer.setSingleShot(True)
        self._closed_timer.timeout.connect(
            lambda: None if self._gone_away() else self._paint())
        self._timer = QTimer(self)
        self._timer.setInterval(self.INTERVAL_MS)
        self._timer.timeout.connect(self.check)
        self._timer.start()
        self.check()

    # -- what the owner asks -------------------------------------------------

    @property
    def state(self) -> str:
        return self.activity.state

    def blocks(self) -> bool:
        if self.state == liveness.RUNNING:
            return True
        return self.leftovers_block and self.state == liveness.LEFTOVERS

    def set_leftovers_block(self, block: bool):
        if block != self.leftovers_block:
            self.leftovers_block = block
            self._paint()

    def set_prefix(self, prefix, name=None):
        self.prefix = Path(prefix) if prefix else None
        self.name = name or (self.prefix.name if self.prefix else "")
        self._shown = None
        self._closed_timer.stop()
        self.check()

    # -- polling -------------------------------------------------------------

    def check(self):
        # A slot: an exception escaping it makes PyQt abort the whole manager.
        # That happened (2026-10-14, after a settings copy): this ran with its
        # _closed_timer already deleted. Whatever the cause, a banner whose
        # parts are gone stops checking instead of taking the manager with it.
        if self._gone_away():
            return
        try:
            self._check()
        except RuntimeError:
            if not self._gone_away():
                raise

    def _gone_away(self) -> bool:
        if not any(sip.isdeleted(o) for o in (self, self._timer, self._closed_timer)):
            return False
        if not sip.isdeleted(self._timer):
            self._timer.stop()
        return True

    def _check(self):
        try:
            now = (liveness.scan(self.prefix) if self.prefix
                   else liveness.Activity(""))
        except Exception:                       # never kill the event loop
            return
        before, self.activity = self.activity.state, now
        first = self._shown is None
        self._shown = now.state
        if not first and now.state == liveness.QUIET and before != liveness.QUIET:
            self._gone = before
            self._closed_timer.start(self.CLOSED_MS)
        elif now.state != liveness.QUIET:
            self._closed_timer.stop()
        self._paint()
        if first or now.state != before:
            self.changed.emit(now.state)

    def _paint(self):
        state = self.state
        closing = state == liveness.QUIET and self._closed_timer.isActive()
        if state == liveness.QUIET and not closing:
            self.hide()
            return
        if closing:
            heading = (f"Affinity has closed in {self.name}"
                       if self._gone == liveness.RUNNING
                       else f"The leftover processes in {self.name} have gone")
            detail = "Nothing is running there now."
            if self.waiting_for:
                detail += f" You can {self.waiting_for}."
            key = "closed"
        elif state == liveness.RUNNING:
            first = min(self.activity.of(liveness.AFFINITY), key=lambda p: p.started)
            heading = f"Affinity is running in {self.name}"
            detail = (f"pid {first.pid}, started {first.when()}. "
                      + (f"Close it to {self.waiting_for}. " if self.waiting_for else "")
                      + "This notice updates by itself.")
            key = state
        else:
            heading = (f"Leftover Wine processes in {self.name}"
                       + (" — end them to continue" if self.leftovers_block else ""))
            detail = self.activity.summary()
            if not self.leftovers_block:
                detail += " They do not stop this."
            key = state
        background, edge = self.STYLE[key]
        self.setStyleSheet(
            f"QFrame#activityBanner {{ background: {background}; "
            f"border: 2px solid {edge}; border-radius: 8px; }}"
            f"QFrame#activityBanner QLabel {{ background: transparent; "
            f"border: none; color: #FFFFFF; }}")
        self.heading.setText(f"<b style='font-size:14pt'>{heading}</b>")
        self.detail.setText(detail)
        self.end_button.setText("End Affinity…" if state == liveness.RUNNING
                                else "End them…")
        self.end_button.setToolTip(
            "Force Affinity and everything else in this prefix to close -- "
            "for when it has hung. Anything unsaved is lost."
            if state == liveness.RUNNING else
            "End the leftover Wine processes in this prefix")
        self.end_button.setVisible(state in (liveness.RUNNING, liveness.LEFTOVERS))
        self.show()

    # -- ending leftovers ----------------------------------------------------

    def _end(self):
        try:
            self._end_unguarded()
        except Exception as exc:                # a slot must never raise
            QMessageBox.warning(self, "Could not end them", str(exc))

    def _end_unguarded(self):
        activity = liveness.scan(self.prefix)
        if activity.state == liveness.RUNNING:
            self._end_affinity(activity)
            return
        if activity.state != liveness.LEFTOVERS:
            self.check()
            return
        lines = [f"  {p.name}  (pid {p.pid}, since {p.when()})"
                 for p in activity.leftovers]
        message = (
            f"{activity.summary()}\n\n" + "\n".join(lines) + "\n\n"
            "These are ended -- asked first, forced if they do not go. Only "
            f"processes whose Wine prefix is {self.prefix} are touched. "
            "Affinity is checked for again at the moment of ending, and if it "
            "has been started meanwhile nothing is ended.")
        box = QMessageBox(QMessageBox.Icon.Question, "End leftover processes",
                          message, QMessageBox.StandardButton.Cancel, self)
        go = box.addButton("End them", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is not go:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            notes = liveness.end_leftovers(self.prefix)
        except liveness.StillRunning as exc:
            notes = [f"Nothing was ended: {exc}"]
        finally:
            QApplication.restoreOverrideCursor()
        self.check()
        problems = [n for n in notes if not n.startswith("ended ")]
        if problems:
            QMessageBox.warning(self, "Leftover processes", "\n".join(notes))

    def _end_affinity(self, activity):
        """For an Affinity that has hung, or will not close.

        Behind a tick, like every other destructive action here: this loses
        whatever is open and unsaved. And bound to what was confirmed -- if by
        the time of ending a different Affinity is running (closed and started
        again while the dialog was up), nothing is touched, since that one is
        not the one the user agreed to end."""
        confirmed = activity.running_pids
        first = min(activity.of(liveness.AFFINITY), key=lambda p: p.started)
        lines = [f"  {p.name}  (pid {p.pid}, since {p.when()})"
                 for p in activity.procs]
        message = (
            f"Affinity is running in {self.name} (pid {first.pid}, started "
            f"{first.when()}).\n\n"
            "Ending it closes it at once, without asking to save. Anything "
            "unsaved in it is lost. Use this when it has hung or will not "
            "close -- otherwise close it from its own window.\n\n"
            "Everything in this prefix is ended:\n" + "\n".join(lines) + "\n\n"
            "Asked first, forced after a few seconds if it does not go. "
            f"Only processes whose Wine prefix is {self.prefix} are touched.")
        if not ConfirmDialog.ask(
                self, "End Affinity", message,
                tick="Yes, end Affinity — anything unsaved is lost",
                confirm="End Affinity"):
            return
        now = liveness.scan(self.prefix)
        if now.running_pids != confirmed:
            self.check()
            QMessageBox.information(
                self, "Nothing was ended",
                "What is running in this prefix changed while you were "
                "deciding, so nothing was ended.\n\n" + now.summary())
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            notes = liveness.end_leftovers(self.prefix, include_affinity=True,
                                           grace=5.0)
        finally:
            QApplication.restoreOverrideCursor()
        self.check()
        problems = [n for n in notes if not n.startswith("ended ")]
        if problems:
            QMessageBox.warning(self, "End Affinity", "\n".join(notes))


class BuildChoiceDialog(SizedDialog):
    FIT_MIN_WIDTH = 720

    """Which Wine builds to carry into the clone.

    This used to be a yes/no -- "copy only the one it uses?" -- and it was
    wrong twice over. A stopped prefix cannot say which Wine it uses; the
    question was answered from the ElementalWarriorWine symlink, which has been
    observed naming 11.12 while the prefix ran 11.16, so the clone kept the
    wrong Wine. And the user could not see which one the answer meant.

    So: every build, its size, and why it might matter, ticked or not according
    to the same evidence but visible and overridable."""

    def __init__(self, parent, name, builds):
        super().__init__(parent)
        self.setWindowTitle(f"Wine builds to copy from {name}")
        self.setModal(True)
        ui.apply(self)
        self.builds = builds
        self.boxes = []

        layout = QVBoxLayout(self)
        blurb = QLabel(
            "Which Wine builds should the copy get? A prefix only needs the one "
            "it runs, and each is roughly 800 MB.\n\n"
            "If nothing is running, the only evidence is the ElementalWarriorWine "
            "symlink, and that symlink can be stale -- so check this against what "
            "you know you launch."
        )
        blurb.setWordWrap(True)
        blurb.setObjectName("descriptionLabel")
        layout.addWidget(blurb)

        listing = QWidget()
        inner = QVBoxLayout(listing)
        inner.setContentsMargins(0, 0, 0, 0)
        for b in builds:
            box = QCheckBox(f"{b['name']}   {probe.human_size(b['size'])}   --  {b['note']}")
            box.setChecked(b["suggested"])
            inner.addWidget(box)
            self.boxes.append(box)
        inner.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(listing)
        scroll.setMinimumHeight(180)
        layout.addWidget(scroll)

        row = QHBoxLayout()
        all_button = QPushButton("Select all")
        none_button = QPushButton("Select none")
        all_button.clicked.connect(lambda: [b.setChecked(True) for b in self.boxes])
        none_button.clicked.connect(lambda: [b.setChecked(False) for b in self.boxes])
        row.addWidget(all_button)
        row.addWidget(none_button)
        row.addStretch(1)
        layout.addLayout(row)

        self.total = QLabel()
        self.total.setObjectName("descriptionLabel")
        layout.addWidget(self.total)
        for box in self.boxes:
            box.toggled.connect(self._retotal)
        self._retotal()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Copy with these")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _retotal(self):
        keep = sum(b["size"] for b, box in zip(self.builds, self.boxes) if box.isChecked())
        n = sum(1 for box in self.boxes if box.isChecked())
        warn = "" if n else "   -- a prefix with no Wine cannot be launched from here"
        self.total.setText(
            f"{n} of {len(self.builds)} builds, {probe.human_size(keep)} of Wine{warn}")

    def chosen(self):
        return [b["name"] for b, box in zip(self.builds, self.boxes) if box.isChecked()]


class FirstRunDialog(SizedDialog):
    """The first time this is opened, when something is already installed.

    The whole dialog exists to not do anything by itself. Somebody has a prefix
    they have been using for a year; the manager has just noticed it. Taking it
    over, or moving it, without being told to would be exactly the behaviour
    this application is meant to be the opposite of.

    So the two things it can do are offered separately, each with the
    explanation built by coldstart from the same facts the action uses, and
    neither is preselected."""

    FIT_MIN_WIDTH = 640

    IN_PLACE = "in-place"
    MOVE = "move"
    SKIP = "skip"

    def __init__(self, parent, situation):
        super().__init__(parent)
        self.setWindowTitle("Affinity is already installed here")
        self.setModal(True)
        ui.apply(self)
        self.situation = situation
        self.install = situation.installs[0]
        self.choice = self.SKIP
        self._sizes = {}

        layout = QVBoxLayout(self)
        several = len(situation.installs) > 1
        blurb = QLabel(
            ("These are Affinity installs this manager did not create."
             if several else
             f"<b>{Path(self.install['path'])}</b> is an Affinity install this "
             "manager did not create.")
            + "<br><br>Nothing has been changed. Choose what should happen"
              + (" to the one you pick" if several else " to it")
              + "; you can also do nothing now and decide later."
              + ("<br>The rest stay where they are and are offered again under "
                 "<i>Find installations</i>." if several else ""))
        blurb.setWordWrap(True)
        layout.addWidget(blurb)

        form = QFormLayout()
        # One dialog, one decision -- but say so by letting the user choose
        # WHICH, rather than silently acting on whichever was modified most
        # recently. Saying "3 installations found" and then only ever being
        # able to act on installs[0] was the previous behaviour.
        self.picker = None
        if several:
            self.picker = QComboBox()
            for item in situation.installs:
                self.picker.addItem(item["path"], item)
            self.picker.currentIndexChanged.connect(self._install_changed)
            form.addRow("Which one", self.picker)

        self.name_edit = QLineEdit(
            self.install.get("suggested_name") or "Affinity")
        form.addRow("Call it", self.name_edit)
        layout.addLayout(form)

        self.in_place_text = self._section("Manage it where it is")
        self.move_text = self._section(f"Move it into {situation.base}")
        # Debounced. _retell measures the prefix, and connecting it straight to
        # textChanged ran a several-gigabyte du on every keystroke.
        self._retell_timer = QTimer(self)
        self._retell_timer.setSingleShot(True)
        self._retell_timer.setInterval(350)
        self._retell_timer.timeout.connect(self._retell)
        self.name_edit.textChanged.connect(self._retell_timer.start)
        self._retell()

        row = QHBoxLayout()
        later = QPushButton("Decide later")
        later.clicked.connect(self.reject)
        row.addWidget(later)
        row.addStretch(1)
        in_place = QPushButton("Manage in place")
        in_place.clicked.connect(lambda: self._choose(self.IN_PLACE))
        row.addWidget(in_place)
        move = QPushButton("Move, then manage")
        move.clicked.connect(lambda: self._choose(self.MOVE))
        row.addWidget(move)
        layout.addLayout(row)

    def _section(self, title):
        self.layout().addSpacing(10)
        heading = QLabel(f"<b>{title}</b>")
        self.layout().addWidget(heading)
        body = QLabel("")
        body.setWordWrap(True)
        body.setObjectName("descriptionLabel")
        self.layout().addWidget(body)
        return body

    def _install_changed(self):
        chosen = self.picker.currentData()
        if chosen is None:
            return
        self.install = chosen
        self.name_edit.setText(chosen.get("suggested_name") or "Affinity")
        self._retell()

    def _size_of(self, install):
        """Measured once per install, not once per keystroke."""
        path = install["path"]
        if path not in self._sizes:
            self._sizes[path] = probe.disk_usage(Path(path))
        return self._sizes[path]

    def _retell(self):
        name = self.name_edit.text().strip() or "Affinity"
        self.in_place_text.setText(
            " ".join(coldstart.explain_in_place(self.install)))
        self.move_text.setText(
            " ".join(coldstart.explain_move(self.install, name,
                                            base=self.situation.base,
                                            size=self._size_of(self.install))))

    def _choose(self, choice):
        try:
            registry.validate_name(self.name_edit.text().strip())
        except registry.InvalidName as exc:
            QMessageBox.warning(self, "That name will not do", str(exc))
            return
        self.choice = choice
        self.accept()

    def chosen_name(self):
        return self.name_edit.text().strip()


def _settings_source_dirs(reg):
    """Where settings can be copied from: every managed prefix, and the
    default ~/.AffinityLinux when the manager does not list it -- the prefix an
    AppImage or a plain AffinityOnLinux install leaves, which is exactly what
    somebody moving to the manager wants their settings from."""
    dirs = [e["path"] for e in reg.entries]
    default = Path.home() / ".AffinityLinux"
    if default.is_dir() and reg.by_path(default) is None:
        dirs.append(str(default))
    return dirs


class CarrySettingsDialog(SizedDialog):
    """Bring preferences, recent files and drive letters across from another prefix.

    Run after Setup, before Affinity's first launch in the destination. After,
    because drive letters cannot exist until Wine has initialised the prefix --
    see prefsseed.is_initialised. Before first launch, because that is when the
    destination still holds only stock settings.

    Three things are shown, because each has been got wrong before:
      - what is copied, and what is deliberately left behind by name -- the
        source folder holds 200 MB of crash-recovery autosaves and a WebView2
        profile that are not settings;
      - the drive letters, each with how many recent files depend on it, since
        a recent file on W: is a dead link in a prefix without a W:;
      - whether the source is running, because Affinity rewrites
        preferences.dat and RecentFiles.xml as it goes."""

    FIT_MIN_WIDTH = 700

    def __init__(self, parent, dest_prefix, destination, sources, preselect=None):
        super().__init__(parent)
        self.setWindowTitle("Copy settings from another prefix")
        self.setModal(True)
        ui.apply(self)
        self.dest_prefix = Path(dest_prefix)
        self.destination = Path(destination)
        self.sources = list(sources)
        self.manual = None
        self.letter_boxes = []

        layout = QVBoxLayout(self)
        populated = bool(prefsseed.settings_in(self.dest_prefix))
        opening = ("This prefix already has Affinity settings in it; they will "
                   "be renamed aside, not deleted."
                   if populated else
                   "This prefix has no Affinity settings yet.")
        blurb = QLabel(
            opening + (
                " Your preferences, workspaces, shortcuts, recent files and "
                "drive letters can be brought across from another prefix."
                if self.sources else
                " No other managed prefix has any to copy, but a backup or a "
                "prefix on another disk works just as well."))
        blurb.setWordWrap(True)
        layout.addWidget(blurb)

        self.picker = QComboBox()
        for found in self.sources:
            self.picker.addItem(
                "%s — %s, %d files, %s" % (
                    found.prefix.name, found.version, found.files,
                    time.strftime("%Y-%m-%d", time.localtime(found.modified))),
                found)
        self.picker.addItem("Somewhere else…", None)
        for i, found in enumerate(self.sources):
            if preselect is not None and found.prefix == Path(preselect):
                self.picker.setCurrentIndex(i)
                break
        self.picker.currentIndexChanged.connect(self._picked)
        form = QFormLayout()
        form.addRow("Copy from", self.picker)
        layout.addLayout(form)

        self.chosen_label = QLabel("")
        self.chosen_label.setWordWrap(True)
        self.chosen_label.setObjectName("descriptionLabel")
        layout.addWidget(self.chosen_label)

        # Two banners, both live. Affinity running in the SOURCE is only a
        # caution: reading it is harmless, it just may not be the last word.
        # Running in the DESTINATION stops the copy, since it would write its
        # own settings over these when it exits.
        self.source_banner = ActivityBanner(
            self, None, waiting_for="copy exactly what it saves on exit -- "
            "copying now takes its settings as they are this second")
        layout.addWidget(self.source_banner)
        self.dest_banner = ActivityBanner(
            self, self.dest_prefix, waiting_for="copy settings into it")
        layout.addWidget(self.dest_banner)

        layout.addSpacing(6)
        layout.addWidget(QLabel("<b>Drive letters</b>"))
        self.letters_note = QLabel("")
        self.letters_note.setWordWrap(True)
        self.letters_note.setObjectName("descriptionLabel")
        layout.addWidget(self.letters_note)
        self.letters_holder = QWidget()
        self.letters_layout = QVBoxLayout(self.letters_holder)
        self.letters_layout.setContentsMargins(12, 0, 0, 0)
        layout.addWidget(self.letters_holder)

        self.replace = QCheckBox(
            "Replace what is in this prefix (what is there is renamed aside "
            "first, not deleted)")
        self.replace.setChecked(True)
        layout.addWidget(self.replace)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Copy")
        buttons.accepted.connect(self._confirm)
        buttons.rejected.connect(self.reject)
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        layout.addWidget(buttons)
        self.dest_banner.changed.connect(
            lambda *_: self.ok_button.setEnabled(not self.dest_banner.blocks()))
        self.ok_button.setEnabled(not self.dest_banner.blocks())
        self._picked()

    # -- the source ----------------------------------------------------------

    def _picked(self):
        source = self.picker.currentData()
        self.manual = None
        if source is None:
            self.chosen_label.setText(
                "Choose a prefix, or the Settings folder inside one. A backup "
                "or a copy on another disk works just as well.")
            self.source_banner.set_prefix(None)
            self._letters_for(None)
            return
        self._describe(source)

    def _describe(self, source):
        plan = prefsseed.plan(source, self.destination)
        left = []
        for entry, kind, label in (
                [(e, k, e.name) for e, k in source.left_behind]
                + [(e, k, "Common/" + e.name) for e, k in source.common_left_behind]):
            if kind == prefsseed.VOLATILE:
                files, size, _ = prefsseed._measure(entry) if entry.is_dir() \
                    else (1, entry.stat().st_size, 0)
                left.append("%s (%s)" % (label, probe.human_size(size))
                            if size > 1024 * 1024 else label)
            else:
                left.append(label + "?")
        self.chosen_label.setText(
            "%s\n%d setting file(s): %d new, %d replacing what is there.\n"
            "Also copied: %s.\nNot copied: %s.%s"
            % (source.path, len(plan.added) + len(plan.replaced),
               len(plan.added), len(plan.replaced),
               ", ".join(plan.extras) or "nothing else",
               ", ".join(left) or "nothing",
               "\n(Names ending in ? are not recognised as settings, so they "
               "are left where they are rather than guessed at.)"
               if any(n.endswith("?") for n in left) else ""))

        home = prefsseed.prefix_of(source.path)
        self.source_banner.set_prefix(home, name=f"{home.name} (the source)"
                                      if home else None)
        self._letters_for(source)

    # -- drive letters -------------------------------------------------------

    def _letters_for(self, source):
        for box in self.letter_boxes:
            box.setParent(None)
            box.deleteLater()
        self.letter_boxes = []

        home = prefsseed.prefix_of(source.path) if source else None
        letters = prefsseed.drive_letters(home) if home else []
        ready = prefsseed.is_initialised(self.dest_prefix)

        if source is None:
            self.letters_note.setText("")
            return
        if not letters:
            self.letters_note.setText(
                "The source has no drive letters beyond C: and Z:."
                if home else
                "This source is not inside a prefix, so it has no drive "
                "letters to bring.")
            return
        if not ready:
            self.letters_note.setText(
                "This prefix has not been set up by Wine yet, so drive letters "
                "cannot be added: Wine only creates C: when it creates the "
                "drive list itself. Run Configure first, then copy again.")
        else:
            self.letters_note.setText(
                "Recent files and paths inside documents are Windows paths, so "
                "these decide whether they still resolve. Existing letters in "
                "this prefix are never changed.")

        used = source.recents_by_drive()
        existing = {d.letter: d.target for d in prefsseed.drive_letters(self.dest_prefix)} \
            if ready else {}
        for d in letters:
            notes = []
            if used.get(d.label[0]):
                notes.append("%d recent file(s)" % used[d.label[0]])
            if not d.available:
                notes.append("not mounted now")
            clash = existing.get(d.letter)
            if clash == d.target:
                notes.append("already set here")
            elif clash:
                notes.append("already %s here; left alone" % clash)
            box = QCheckBox("%s  →  %s%s" % (d.label, d.target,
                            ("   (" + ", ".join(notes) + ")") if notes else ""))
            box.setChecked(ready and clash is None)
            box.setEnabled(ready and clash is None)
            box.setProperty("letter", d)
            self.letters_layout.addWidget(box)
            self.letter_boxes.append(box)

    def chosen_letters(self):
        return [b.property("letter") for b in self.letter_boxes
                if b.isEnabled() and b.isChecked()]

    # -- the answer ------------------------------------------------------------

    def _confirm(self):
        if self.dest_banner.blocks():
            return
        # chosen_source, not the picker: after "Somewhere else…" the picker
        # still says that, and asking it again re-opened the folder chooser
        # on every press of Copy.
        source = self.chosen_source()
        if source is None:
            chosen = QFileDialog.getExistingDirectory(
                self, "Prefix or Settings folder to copy from", str(Path.home()))
            if not chosen:
                return
            source = prefsseed.resolve_source(chosen)
            if source is None:
                QMessageBox.warning(
                    self, "Nothing to copy",
                    f"No Affinity settings were found in {chosen}.\n\n"
                    "Choose a prefix, or the Settings folder inside one.")
                return
            self.manual = source
            self._describe(source)
            return              # show what it found before copying it
        self.accept()

    def chosen_source(self):
        return self.manual or self.picker.currentData()

    def mode(self):
        return prefsseed.REPLACE if self.replace.isChecked() else prefsseed.FILL

class RemovalDialog(SizedDialog):
    """Everything removing one or more prefixes would take with them, as a list.

    The confirmation is the list. A yes/no on a summary is where "and 4 other
    items" hides the one you would have objected to -- and the things most
    easily forgotten here are the ones that bite later: a menu entry that
    launches nothing, and a document association that silently stops working
    because the prefix holding it has gone.

    Several prefixes at once, each its own group: ticking or unticking the
    group's row takes all of its items with it, and each item can still be
    chosen on its own. A file two prefixes both claim is listed once, under
    the first, so it is not removed twice and reported failed the second time.

    Two rows are not like the others. Settings snapshots are listed unticked,
    because losing the backups of a thing along with the thing is the wrong
    default. And anything without our marker is not offered at all -- it is
    named at the bottom as left alone, so the dialog can say what it will not
    do as well as what it will.
    """

    FIT_MIN_WIDTH = 900
    COLUMNS = ["What", "Where", "Size"]

    # Removing these actually frees the space. The rest are moved aside by
    # hoststate.delete, which keeps a copy, so counting them in a figure
    # labelled "freed" would be a promise the button does not keep.
    FREES_SPACE = ("prefix", "log", "settings-backup")

    def __init__(self, parent, plans):
        super().__init__(parent)
        self.plans = list(plans) if isinstance(plans, (list, tuple)) else [plans]
        names = [p.name for p in self.plans]
        self.setWindowTitle(f"Remove {names[0]}" if len(names) == 1
                            else f"Remove {len(names)} prefixes")
        self.setModal(True)
        ui.apply(self)
        self.groups = []            # (plan, group row, [item rows])

        layout = QVBoxLayout(self)
        who = (f"<b>{names[0]}</b> put" if len(names) == 1
               else f"These <b>{len(names)} prefixes</b> put")
        blurb = QLabel(
            f"{who} all of this on this machine. Choose what goes.<br><br>"
            "Prefixes, their logs and any snapshots are deleted outright. The "
            "small host-side files — menu entries, document type definitions, "
            "icons — are moved aside rather than deleted, so those are "
            "recoverable; the rest is not.")
        blurb.setWordWrap(True)
        layout.addWidget(blurb)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(self.COLUMNS))
        self.tree.setHeaderLabels(self.COLUMNS)
        self.tree.setRootIsDecorated(len(self.plans) > 1)
        self.tree.setMinimumHeight(300)
        # What and Size sized to what they hold, Where takes the rest -- with
        # fixed widths the Size column, the one people check, ran off the edge.
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        seen = set()
        for plan in self.plans:
            if len(self.plans) > 1:
                group = QTreeWidgetItem([plan.name, str(plan.path), ""])
                font = group.font(0)
                font.setBold(True)
                group.setFont(0, font)
                group.setFlags(group.flags() | Qt.ItemFlag.ItemIsUserCheckable
                               | Qt.ItemFlag.ItemIsAutoTristate)
                self.tree.addTopLevelItem(group)
            else:
                group = None
            rows = []
            for item in plan.items:
                key = (item.kind, str(item.path) if item.path else item.label,
                       item.value)
                if key in seen:
                    continue
                seen.add(key)
                row = QTreeWidgetItem([
                    item.label, item.detail,
                    probe.human_size(item.size) if item.size else ""])
                row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                row.setCheckState(0, Qt.CheckState.Checked if item.default
                                  else Qt.CheckState.Unchecked)
                row.setData(0, Qt.ItemDataRole.UserRole, item)
                if group is not None:
                    group.addChild(row)
                else:
                    self.tree.addTopLevelItem(row)
                rows.append(row)
            if group is not None:
                total = sum(i.size for i in plan.items)
                group.setText(2, probe.human_size(total) if total else "")
                group.setExpanded(len(self.plans) <= 3)
            self.groups.append((plan, group, rows))
        layout.addWidget(self.tree, 1)

        left_alone = [a for p in self.plans for a in p.left_alone]
        if left_alone:
            left = QLabel(
                "<b>Left alone, not ours:</b> "
                + ", ".join(str(a.path.name if a.path else a.detail)
                            for a in left_alone[:8]))
            left.setWordWrap(True)
            left.setObjectName("descriptionLabel")
            layout.addWidget(left)

        # Checked live, one per prefix: the plans were made when the dialog
        # opened, and closing Affinity with it open has to be noticed without
        # reopening it. A quiet prefix's banner takes no room.
        self.banners = {}
        for plan in self.plans:
            banner = ActivityBanner(self, plan.path if plan.path.exists() else None,
                                    name=plan.name, waiting_for="remove it")
            banner.changed.connect(lambda *_: self._retotal())
            layout.addWidget(banner)
            self.banners[plan.name] = banner

        self.arm = ArmBox("Yes, permanently remove the ticked items",
                          "Required — Remove stays off until this is ticked.")
        layout.addWidget(self.arm)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText("Remove")
        self.ok.setProperty("class", "danger")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
        layout.addWidget(self.buttons)

        self.arm.toggled.connect(lambda *_: self._retotal())
        self.tree.itemChanged.connect(lambda *_: self._retotal())
        self._retotal()

    # kept for the single-prefix callers and tests that read it
    @property
    def plan(self):
        return self.plans[0]

    def _retotal(self):
        chosen = self.chosen_by_plan()
        items = [i for _, its in chosen for i in its]
        blocked = []
        for plan, its in chosen:
            banner = self.banners.get(plan.name)
            if banner is None:
                continue
            # Leftovers stop only the deletion of the prefix itself -- they
            # have files in it open. The menu entry and the rest can go.
            banner.set_leftovers_block(any(i.kind == "prefix" for i in its))
            if its and banner.blocks():
                blocked.append(plan.name)
        freed = sum(i.size for i in items if i.kind in self.FREES_SPACE)
        label = f"Remove {len(items)} item(s)"
        if len(chosen) > 1:
            label += f" from {len(chosen)} prefixes"
        if freed:
            label += f"  (frees {probe.human_size(freed)})"
        self.ok.setText(label if items else "Remove")
        self.ok.setEnabled(bool(items) and self.arm.isChecked() and not blocked)
        if blocked:
            self.arm.set_note(f"Not while something runs in {', '.join(blocked)} "
                              "— see above.")
        elif not items:
            self.arm.set_note("Nothing is ticked in the list.")
        else:
            self.arm.set_note(None)

    def chosen_by_plan(self):
        """[(plan, [items])] for every prefix with anything ticked."""
        out = []
        for plan, _, rows in self.groups:
            its = [r.data(0, Qt.ItemDataRole.UserRole) for r in rows
                   if r.checkState(0) == Qt.CheckState.Checked]
            if its:
                out.append((plan, its))
        return out

    def chosen(self):
        return [i for _, its in self.chosen_by_plan() for i in its]


class SnapshotsDialog(SizedDialog):
    """Settings snapshots for one prefix: take, restore, delete.

    A snapshot is the prefix's configuration and not the prefix -- tens of
    kilobytes against several gigabytes -- which is what makes it something to
    take before every risky change rather than once a year.

    Restoring across prefixes is allowed and is the point: it is how the live
    prefix's settings get into a test one. So the confirmation names both sides
    and says when they differ, because restoring into the wrong prefix is the
    expensive mistake."""

    FIT_MIN_WIDTH = 760
    COLUMNS = ["Taken", "Label", "From", "Files", "Size"]

    def __init__(self, parent, entry):
        super().__init__(parent)
        self.entry = entry
        self.name = entry["name"]
        self.path = Path(entry["path"])
        self.setWindowTitle(f"Settings snapshots — {self.name}")
        self.setModal(True)
        ui.apply(self)

        layout = QVBoxLayout(self)
        layout.addWidget(kinds_legend("snapshot"))
        layout.addSpacing(6)
        blurb = QLabel(
            "Kept under a dated name, as a directory, so you can read one "
            "without restoring it. A snapshot cannot undo an install -- it "
            "holds no Wine, no Affinity and no desktop files. That is what a "
            "backup is for.")
        blurb.setWordWrap(True)
        blurb.setObjectName("descriptionLabel")
        layout.addWidget(blurb)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(self.COLUMNS))
        self.tree.setHeaderLabels(self.COLUMNS)
        self.tree.setRootIsDecorated(False)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.tree, 1)

        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setObjectName("descriptionLabel")
        layout.addWidget(self.detail)

        row = QHBoxLayout()
        take = QPushButton("Take a snapshot…")
        take.clicked.connect(self._take)
        row.addWidget(take)
        row.addStretch(1)
        self.restore_button = QPushButton("Restore…")
        self.restore_button.clicked.connect(self._restore)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        for b in (self.restore_button, self.delete_button, close):
            row.addWidget(b)
        layout.addLayout(row)

        self._reload()

    # -- the list ------------------------------------------------------------

    def _reload(self):
        self.tree.clear()
        for snap in snapshots.listing(self.name):
            item = QTreeWidgetItem([
                snap.when,
                snap.label or "—",
                snap.prefix,
                str(snap.files),
                probe.human_size(snap.bytes),
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, snap)
            self.tree.addTopLevelItem(item)
        for i in range(len(self.COLUMNS)):
            self.tree.resizeColumnToContents(i)
        self._selection_changed()

    def selected(self):
        rows = self.tree.selectedItems()
        return rows[0].data(0, Qt.ItemDataRole.UserRole) if rows else None

    def _selection_changed(self):
        snap = self.selected()
        self.restore_button.setEnabled(snap is not None)
        self.delete_button.setEnabled(snap is not None)
        if snap is None:
            self.detail.setText(
                "Nothing here yet." if not self.tree.topLevelItemCount()
                else "Choose one to restore or delete it.")
            return
        self.detail.setText(f"{snap.path}\n" + " ".join(snap.notes))

    # -- taking --------------------------------------------------------------

    def _take(self):
        label, ok = QInputDialog.getText(
            self, "Label this snapshot",
            "An optional name, so you can tell it apart later\n"
            "(\"before 3.3\", \"known good\"):")
        if not ok:
            return
        try:
            snap = snapshots.take(self.name, self.path, label)
        except (snapshots.NoSettings, snapshots.NotASnapshot, OSError) as exc:
            QMessageBox.warning(self, "Could not take a snapshot", str(exc))
            return
        self._reload()
        self.detail.setText(f"Took {snap.name} — {snap.files} file(s), "
                            f"{probe.human_size(snap.bytes)}.")

    # -- restoring -----------------------------------------------------------

    def _restore(self):
        snap = self.selected()
        if snap is None:
            return
        try:
            plan = snapshots.plan_restore(snap, self.name, self.path)
        except OSError as exc:
            QMessageBox.warning(self, "Cannot restore", str(exc))
            return

        box = QMessageBox(self)
        box.setWindowTitle("Restore these settings")
        box.setText("\n\n".join(plan.describe()))
        box.setInformativeText(
            "The settings currently in this prefix are snapshotted first, and "
            "the ones they replace are kept beside them with the date in the "
            "name. Nothing is deleted.")
        box.setStandardButtons(QMessageBox.StandardButton.Ok
                               | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Ok:
            return
        try:
            notes = snapshots.restore(plan)
        except (maintenance.Busy, OSError) as exc:
            QMessageBox.warning(self, "Could not restore", str(exc))
            return
        prefixlog.write(self.name, "Restored settings from " + str(snap))
        self._reload()
        QMessageBox.information(self, "Restored", "\n".join(notes))

    # -- deleting ------------------------------------------------------------

    def _delete(self):
        snap = self.selected()
        if snap is None:
            return
        if QMessageBox.question(
            self, "Delete this snapshot",
            f"Permanently delete {snap.name}?\n\n{snap.path}\n\n"
            "There is no undo, and a snapshot is the only copy of the "
            "preferences it holds.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) != QMessageBox.StandardButton.Ok:
            return
        try:
            snapshots.remove(snap)
        except (snapshots.NotASnapshot, OSError) as exc:
            QMessageBox.warning(self, "Could not delete it", str(exc))
            return
        self._reload()


class SizeSortItem(QTreeWidgetItem):
    """A row whose Size column sorts by bytes, not by the string.

    "9.9M" sorts after "787.2M" alphabetically, which makes a size column that
    cannot do the one thing it is for."""

    SIZE_COLUMN = 1

    def __lt__(self, other):
        column = self.treeWidget().sortColumn() if self.treeWidget() else 0
        if column == self.SIZE_COLUMN:
            return (self.data(column, Qt.ItemDataRole.UserRole) or 0) < \
                   (other.data(column, Qt.ItemDataRole.UserRole) or 0)
        return super().__lt__(other)


class CleanDialog(SizedDialog):
    FIT_MIN_WIDTH = 760

    """What can go, with what it costs, chosen item by item.

    Presented rather than decided. A Wine build this prefix is not running is
    still a build someone kept on purpose -- the sep04 build in the project's
    own prefix was there precisely as a fallback -- so nothing is ticked by
    default except what is unambiguously spoil: archives already unpacked,
    saved-aside copies, and temporary files."""

    SAFE_BY_DEFAULT = {"archive", "temp", "backup"}
    COLUMNS = ["Item", "Size", "What it is"]

    def __init__(self, parent, name, items):
        super().__init__(parent)
        self.setWindowTitle(f"Clean {name}")
        self.setModal(True)
        ui.apply(self)
        self.items = items

        layout = QVBoxLayout(self)
        blurb = QLabel(
            "Nothing here is needed to run Affinity. Wine builds are offered "
            "only when this prefix is neither running them nor pointing a "
            "launcher or its ElementalWarriorWine symlink at them.\n\n"
            "Click a column heading to sort."
        )
        blurb.setWordWrap(True)
        blurb.setObjectName("descriptionLabel")
        layout.addWidget(blurb)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(self.COLUMNS))
        self.tree.setHeaderLabels(self.COLUMNS)
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSortingEnabled(True)
        self.tree.setMinimumHeight(300)

        for item in items:
            row = SizeSortItem([item.path.name, probe.human_size(item.size), item.reason])
            row.setData(1, Qt.ItemDataRole.UserRole, item.size)
            row.setData(0, Qt.ItemDataRole.UserRole, item)
            row.setToolTip(0, str(item.path))
            row.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.setCheckState(
                0,
                Qt.CheckState.Checked if item.kind in self.SAFE_BY_DEFAULT
                else Qt.CheckState.Unchecked,
            )
            self.tree.addTopLevelItem(row)

        # Largest first: what is worth reclaiming is the reason the dialog is open.
        self.tree.sortItems(1, Qt.SortOrder.DescendingOrder)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tree.itemChanged.connect(lambda *_: self._retotal())
        layout.addWidget(self.tree, 1)

        row = QHBoxLayout()
        all_button = QPushButton("Select all")
        none_button = QPushButton("Select none")
        safe_button = QPushButton("Select the safe ones")
        safe_button.setToolTip(
            "Archives, saved-aside copies and temporary files -- everything "
            "except the Wine builds.")
        all_button.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        none_button.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        safe_button.clicked.connect(self._select_safe)
        row.addWidget(all_button)
        row.addWidget(none_button)
        row.addWidget(safe_button)
        row.addStretch(1)
        layout.addLayout(row)

        self.total = QLabel()
        self.total.setObjectName("descriptionLabel")
        layout.addWidget(self.total)
        self._retotal()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Remove selected")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _rows(self):
        return [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]

    def _set_all(self, state):
        self.tree.blockSignals(True)
        for row in self._rows():
            row.setCheckState(0, state)
        self.tree.blockSignals(False)
        self._retotal()

    def _select_safe(self):
        self.tree.blockSignals(True)
        for row in self._rows():
            item = row.data(0, Qt.ItemDataRole.UserRole)
            row.setCheckState(
                0,
                Qt.CheckState.Checked if item.kind in self.SAFE_BY_DEFAULT
                else Qt.CheckState.Unchecked,
            )
        self.tree.blockSignals(False)
        self._retotal()

    def _retotal(self):
        chosen = self.selected()
        total = sum(i.size for i in chosen)
        builds = sum(1 for i in chosen if i.kind == "wine-build")
        warn = f"   -- including {builds} Wine build(s)" if builds else ""
        self.total.setText(
            f"{len(chosen)} of {len(self.items)} selected, "
            f"{probe.human_size(total)}{warn}")

    def selected(self):
        return [
            row.data(0, Qt.ItemDataRole.UserRole)
            for row in self._rows()
            if row.checkState(0) == Qt.CheckState.Checked
        ]


class CollisionDialog(SizedDialog):
    FIT_MIN_WIDTH = 620

    """What to do about a directory that is already there.

    Offered rather than decided: only the user knows whether what is sitting at
    that path matters. Nothing here deletes anything -- "use it" installs
    alongside what is present and "rename the existing one" moves it aside,
    because what is usually in the way is a Wine prefix of several gigabytes
    that took an hour to build."""

    USE = "use"
    RENAME_OLD = "rename_old"
    RENAME_NEW = "rename_new"

    def __init__(self, parent, path, info):
        super().__init__(parent)
        self.choice = None
        self.setWindowTitle("That directory already exists")
        self.setModal(True)
        ui.apply(self)

        if info.get("empty"):
            what = "It is empty."
        elif info.get("has_affinity"):
            version = info.get("affinity_version") or "an unknown version"
            what = f"It is a Wine prefix with Affinity {version} installed."
        elif info.get("is_prefix"):
            what = "It is a Wine prefix with no Affinity in it."
        else:
            what = f"It holds {info.get('entry_count', 0)} item(s) and is not a Wine prefix."

        heading = QLabel(str(path))
        heading.setObjectName("sectionTitle")
        heading.setWordWrap(True)

        detail = QLabel(what + "\n\nNothing here deletes anything.")
        detail.setObjectName("descriptionLabel")
        detail.setWordWrap(True)

        use = QPushButton("Use it anyway")
        use.setToolTip("Install into this directory. Existing contents are left in place.")
        use.clicked.connect(lambda: self._pick(self.USE))

        rename_old = QPushButton("Rename the existing one")
        rename_old.setToolTip(f"Move it to {registry.aside_path(path).name}, then install fresh.")
        rename_old.clicked.connect(lambda: self._pick(self.RENAME_OLD))

        rename_new = QPushButton("Choose a different name")
        rename_new.setObjectName("okButton")
        rename_new.clicked.connect(lambda: self._pick(self.RENAME_NEW))

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)

        row = QHBoxLayout()
        for b in (use, rename_old, rename_new):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(cancel)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(detail)
        layout.addLayout(row)

    def _pick(self, choice):
        self.choice = choice
        self.accept()


class NewPrefixDialog(SizedDialog):
    FIT_MIN_WIDTH = 620

    def __init__(self, parent, reg: registry.Registry):
        super().__init__(parent)
        self.reg = reg
        self.setWindowTitle("New managed prefix")
        self.setModal(True)
        ui.apply(self)

        form = QFormLayout()
        self.name = QLineEdit(reg.suggest_name())
        self.name.textChanged.connect(self._name_changed)
        self.name.setMaxLength(64)
        form.addRow("Name", self.name)
        # Always shown, not only once a name is refused: knowing the rule
        # before typing beats finding it out from a button that will not press.
        self.name_rule = QLabel(self.NAME_RULE)
        self.name_rule.setWordWrap(True)
        self.name_rule.setObjectName("descriptionLabel")
        form.addRow("", self.name_rule)

        # Read-only: a managed prefix lives directly under the base directory,
        # named after itself. Somewhere else would be an adopted prefix, which
        # is a different action.
        #
        # A read-only field, not a label. The label was word-wrapped, and a
        # path has no spaces to wrap at: Qt laid it out narrower than the
        # text and clipped it, and widening the window did not bring it back.
        # A field always shows what fits, scrolls for the rest, and can be
        # selected and copied.
        self.path_field = QLineEdit()
        self.path_field.setReadOnly(True)
        self.path_field.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        form.addRow("Directory", self.path_field)
        self.path_note = QLabel("")
        self.path_note.setWordWrap(True)
        self.path_note.setObjectName("cautionText")
        self.path_note.hide()
        form.addRow("", self.path_note)

        # Says Affinity, and says what it is not: the manager also chooses
        # Wine builds, and "a specific build" alone read as one of those.
        self.pin = QCheckBox("Install an older version of Affinity, from an "
                             "installer you kept, instead of the current release")
        self.pin.toggled.connect(self._pin_toggled)
        form.addRow("", self.pin)

        prow = QHBoxLayout()
        self.installer_file = QLineEdit()
        self.installer_file.setEnabled(False)
        self.installer_file.setPlaceholderText("Affinity-x64-<version>.exe")
        self.pick = QPushButton("Choose\u2026")
        self.pick.setEnabled(False)
        self.pick.clicked.connect(self._pick_installer)
        prow.addWidget(self.installer_file, 1)
        prow.addWidget(self.pick)
        pholder = QWidget()
        pholder.setLayout(prow)
        form.addRow("Affinity installer", pholder)

        # Which Affinity this will actually be. "The current release" alone
        # does not say which one, and the download URL never changes.
        self.will_install = QLabel("Affinity: checking the current release…")
        self.will_install.setWordWrap(True)
        self.will_install.setTextFormat(Qt.TextFormat.RichText)
        form.addRow("Will install", self.will_install)

        # Asked here, done later: settings can only go in once Setup has had
        # Wine create the prefix (drive letters need its dosdevices), and
        # before Affinity first runs there. So this is remembered, and the copy
        # dialog opens with it chosen when this prefix's Setup finishes.
        self.carry = QComboBox()
        self.carry.addItem("Start with Affinity's stock settings", None)
        for found in prefsseed.sources(_settings_source_dirs(reg)):
            self.carry.addItem(
                "Copy from %s — %s, last changed %s" % (
                    found.prefix.name, found.version,
                    time.strftime("%Y-%m-%d", time.localtime(found.modified))),
                found.prefix)
        form.addRow("Settings", self.carry)
        self.carry_note = QLabel(
            "Preferences, workspaces, shortcuts, recent files and drive letters. "
            "They are copied when Configure has finished, before Affinity first "
            "starts here; you see what will be copied before it is.")
        self.carry_note.setWordWrap(True)
        self.carry_note.setObjectName("descriptionLabel")
        form.addRow("", self.carry_note)
        if self.carry.count() == 1:
            self.carry.setEnabled(False)
            self.carry_note.setText("No other managed prefix has settings to copy yet.")
        self.current_release = None
        self.release_problem = ""
        self.installer_file.textChanged.connect(lambda *_: self._show_version())

        self.note = QLabel(
            "This is Affinity's own installer (Affinity-x64-<version>.exe), "
            "not Wine — the Wine build is chosen in Configure. Affinity's "
            "download site only ever offers the current release, so to "
            "install an older Affinity, point this at an installer you kept."
        )
        self.note.setObjectName("descriptionLabel")
        self.note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText("Create and install")
        self.ok.setObjectName("okButton")

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.note)
        layout.addWidget(buttons)

        self.result_entry = None
        self._name_changed(self.name.text())

        thread = TaskThread(lambda progress: release.current())
        thread.done.connect(self._release_known)
        keep_until_finished(thread)
        thread.start()

    def carry_from(self):
        """The prefix whose settings to offer once Setup has finished, or None."""
        return self.carry.currentData()

    def _release_known(self, result, error):
        self.current_release = result
        self.release_problem = error
        self._show_version()

    def _show_version(self):
        if self.pin.isChecked():
            chosen = self.installer_file.text().strip()
            if not chosen:
                self.will_install.setText("Choose the Affinity installer to use.")
                return
            try:
                kept = release.of_file(chosen)
            except release.Unknown as exc:
                self.will_install.setText(
                    f"<b>Unknown version</b> — {html.escape(str(exc))}.")
                return
            self.will_install.setText(
                f"<b>{html.escape(str(kept))}</b>, from the installer you chose.")
            return
        r = self.current_release
        if r is not None:
            when = f", published {r.published}" if r.published else ""
            self.will_install.setText(
                f"<b>{html.escape(str(r))}</b> — the current release{when}, "
                "downloaded in Configure.")
        elif self.release_problem:
            self.will_install.setText(
                "The current release, downloaded in Configure. Which version "
                f"that is could not be checked: {html.escape(self.release_problem)}.")
        else:
            self.will_install.setText("Affinity: checking the current release…")

    def _name_changed(self, text):
        try:
            registry.validate_name(text)
            valid = True
        except registry.InvalidName:
            valid = False
        self.ok.setEnabled(valid)
        self.ok.setToolTip("" if valid else "The name is not usable — see the "
                           "line under Directory.")
        if valid:
            path = registry.path_for(text)
            self.path_field.setText(str(path))
            self.path_field.setCursorPosition(0)
            note = "A folder with this name already exists." if path.exists() else ""
        else:
            self.path_field.setText("")
            note = self._why_not(text)
        self.path_note.setText(note)
        if bool(note) != self.path_note.isVisible():
            self.path_note.setVisible(bool(note))
            # Grow to fit the line rather than squeeze the rows under it.
            if self.isVisible():
                self.layout().activate()
                want = self.sizeHint().height()
                if want > self.height():
                    self.resize(self.width(), want)

    NAME_RULE = ("Allowed: letters A–Z a–z, digits 0–9, space, dot ( . ), "
                 "underscore ( _ ) and hyphen ( - ). Up to 64 characters, "
                 "starting with a letter or digit. Spaces become underscores "
                 "in the folder name.")

    @staticmethod
    def _why_not(text):
        """What exactly is wrong with a name. The rule is on show already, so
        this names the offending character rather than repeating it."""
        text = text.strip()
        if not text:
            return "Give the prefix a name."
        bad = sorted({c for c in text if not re.match(r"[A-Za-z0-9 ._-]", c)})
        if bad:
            shown = "  ".join(f"“{c}”" for c in bad)
            return f"Not allowed in a name: {shown}"
        if not re.match(r"[A-Za-z0-9]", text):
            return f"A name has to start with a letter or digit, not “{text[0]}”."
        if len(text) > 64:
            return f"That is {len(text)} characters; the limit is 64."
        return "This name is not usable."

    def _pin_toggled(self, on):
        self.installer_file.setEnabled(on)
        self.pick.setEnabled(on)
        self._show_version()

    def _pick_installer(self):
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Affinity installer",
            str(Path.home()),
            "Installers (*.exe);;All files (*)",
        )
        if chosen:
            self.installer_file.setText(chosen)

    def _accept(self):
        name = self.name.text().strip()
        path = registry.path_for(name)
        pinned = self.installer_file.text().strip() if self.pin.isChecked() else None

        if pinned and not Path(pinned).expanduser().is_file():
            QMessageBox.warning(self, "Installer not found", f"{pinned} does not exist.")
            return

        if path.exists():
            info = registry.describe_collision(path)
            managed = self.reg.by_path(path)
            if managed:
                QMessageBox.warning(
                    self,
                    "Already managed",
                    f"{path} is already managed as {managed['name']!r}.\n\n"
                    "Pick a different name.",
                )
                return
            dialog = CollisionDialog(self, path, info)
            if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.choice:
                return
            if dialog.choice == CollisionDialog.RENAME_NEW:
                self.name.setFocus()
                self.name.selectAll()
                return
            if dialog.choice == CollisionDialog.RENAME_OLD:
                try:
                    moved = registry.rename_aside(path)
                except OSError as e:
                    QMessageBox.critical(self, "Could not rename", str(e))
                    return
                QMessageBox.information(
                    self, "Renamed", f"The existing directory is now:\n{moved}"
                )

        try:
            self.result_entry = self.reg.add(name, path, installer_file=pinned)
        except (registry.InvalidName, registry.DuplicateName, registry.PathInUse) as e:
            QMessageBox.warning(self, "Cannot add this prefix", str(e))
            return
        self.accept()


class CommandsDialog(SizedDialog):
    FIT_MIN_WIDTH = 900

    """Every way this prefix can be run -- copy it, run it, or put it in the menu.

    A prefix usually holds several Wine builds and three ways to start Affinity,
    and the difference between them is the difference between a meaningful test
    and a misleading one. Listing them beats remembering them."""

    def __init__(self, parent, entry):
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle(f"Commands — {entry['name']}")
        self.setModal(False)
        ui.apply(self)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Configuration", "In menu"])
        self.tree.setColumnWidth(0, 620)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.itemDoubleClicked.connect(self._double_clicked)

        self.detail = QLabel("")
        self.detail.setObjectName("descriptionLabel")
        self.detail.setWordWrap(True)
        self.detail.setMinimumHeight(52)

        self.command_line = QLineEdit()
        self.command_line.setReadOnly(True)

        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self.copy_selected)
        self.run_button = QPushButton("Run")
        self.run_button.setObjectName("okButton")
        self.run_button.clicked.connect(self.run_selected)
        self.menu_button = QPushButton("Add to menu")
        self.menu_button.clicked.connect(self.menu_selected)
        self.unmenu_button = QPushButton("Remove from menu")
        self.unmenu_button.clicked.connect(self.remove_menu_entry)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)

        row = QHBoxLayout()
        for b in (self.copy_button, self.run_button, self.menu_button, self.unmenu_button):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.detail)
        layout.addWidget(self.command_line)
        layout.addLayout(row)

        self.reload()

    def reload(self):
        self.tree.clear()
        self.commands = commands_mod.grouped(self.entry["path"])
        for group, items in self.commands.items():
            parent = QTreeWidgetItem([group, ""])
            parent.setFirstColumnSpanned(True)
            self.tree.addTopLevelItem(parent)
            for command in items:
                label = command.label + ("   (careful)" if command.risky else "")
                in_menu = "yes" if desktopentry.exists(self.entry["name"], command) else ""
                child = QTreeWidgetItem([label, in_menu])
                child.setData(0, Qt.ItemDataRole.UserRole, command)
                parent.addChild(child)
            parent.setExpanded(True)
        self._selection_changed()

    def selected_command(self):
        items = self.tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.ItemDataRole.UserRole)

    def _selection_changed(self):
        command = self.selected_command()
        enabled = command is not None
        for b in (self.copy_button, self.run_button, self.menu_button):
            b.setEnabled(enabled)
        if not command:
            self.detail.setText("")
            self.command_line.clear()
            self.unmenu_button.setEnabled(False)
            return
        self.detail.setText(command.detail)
        self.command_line.setText(command.shell)
        in_menu = desktopentry.exists(self.entry["name"], command)
        self.menu_button.setText("Edit menu entry" if in_menu else "Add to menu")
        self.unmenu_button.setEnabled(in_menu)

    def _double_clicked(self, item, _column):
        command = item.data(0, Qt.ItemDataRole.UserRole)
        # Double-click runs, except for the ones that end a session -- those
        # deserve a deliberate click on Run.
        if command and not command.risky:
            self.run_selected()

    def copy_selected(self):
        command = self.selected_command()
        if not command:
            return
        QApplication.clipboard().setText(command.shell)
        self.detail.setText("Copied to the clipboard.")

    def run_selected(self):
        command = self.selected_command()
        if not command:
            return
        if command.risky:
            reply = QMessageBox.question(
                self,
                command.label,
                f"{command.detail}\n\nRun it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        if "Affinity" in command.group and not command.risky:
            pids = probe.running_pids(self.entry["path"])
            if pids:
                QMessageBox.information(
                    self,
                    "Already running",
                    f"Affinity is already running in this prefix (pid {pids[0]}).\n\n"
                    "A second instance kills the first, so this was not started.",
                )
                return
        try:
            command.run()
        except OSError as e:
            QMessageBox.critical(self, "Could not run", str(e))
            return
        self.detail.setText(f"Started: {command.label}")

    def menu_selected(self):
        command = self.selected_command()
        if not command:
            return
        existing = desktopentry.read_name(self.entry["name"], command)
        suggested = existing or f"{command.label} ({self.entry['name']})"
        name, ok = _ask_name(self, suggested, title="Menu entry name", label="Shows in the menu as")
        if not ok or not name.strip():
            return
        try:
            path = desktopentry.write(self.entry["name"], command, name=name.strip())
        except (OSError, FileExistsError) as e:
            QMessageBox.critical(self, "Could not write the menu entry", str(e))
            return
        self.detail.setText(f"Menu entry written: {path}")
        self.reload()

    def remove_menu_entry(self):
        command = self.selected_command()
        if not command:
            return
        try:
            removed = desktopentry.remove(self.entry["name"], command)
        except (OSError, PermissionError) as e:
            QMessageBox.critical(self, "Could not remove the menu entry", str(e))
            return
        self.detail.setText("Menu entry removed." if removed else "There was no menu entry.")
        self.reload()


class FindDialog(SizedDialog):
    FIT_MIN_WIDTH = 940

    """Wine prefixes on this machine, and what to do with them.

    Unfiltered on purpose. An earlier version listed only prefixes with
    Affinity.exe in them, which meant the one prefix somebody most needed help
    with -- the one whose install was interrupted -- was the one the manager
    said it could not find. Everything found is listed, with what it is in the
    Affinity column, and only the complete ones are ticked to begin with.

    "Open folder" is here for the same reason. Deciding whether a path from a
    search is the prefix you think it is means looking inside it, and that
    should not require closing the dialog.
    """

    def __init__(self, parent, reg: registry.Registry):
        super().__init__(parent)
        self.reg = reg
        self.manager = parent
        self.setWindowTitle("Find existing installations")
        self.setModal(True)
        ui.apply(self)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["", "Name to use", "Affinity", "Wine", "Path"])
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0, 34)
        self.tree.setColumnWidth(1, 220)
        self.tree.itemSelectionChanged.connect(self._selection_changed)

        self.open_button = QPushButton("Open folder")
        self.open_button.setToolTip(
            "Show the selected prefix in the file manager, before deciding "
            "anything about it")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_selected)

        self.move_box = QCheckBox("Move them into the base directory")
        self.move_box.setToolTip(
            "A prefix is relocatable -- dosdevices/c: is relative and the "
            "registries hold no absolute prefix paths. Absolute symlinks "
            "inside it are repointed, and any launcher or desktop entry naming "
            "the old path is rewritten, with a copy of each kept beside it."
        )

        self.status = QLabel("Searching…")
        self.status.setObjectName("statusText")
        self.status.setWordWrap(True)

        self.adopt_button = QPushButton("Manage the ticked ones")
        self.adopt_button.setObjectName("okButton")
        self.adopt_button.clicked.connect(self._adopt)
        self.adopt_button.setEnabled(False)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)

        row = QHBoxLayout()
        row.addWidget(self.move_box)
        row.addStretch(1)
        row.addWidget(self.open_button)
        row.addWidget(self.adopt_button)
        row.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.status)
        layout.addLayout(row)

        self.found = []
        # Searched after the dialog is on screen, not before it exists. The
        # scan walks the home directory, /mnt, /opt and the removable-media
        # roots, and running it here meant several seconds in which the
        # application had simply stopped, with the window that explains what
        # is happening still unbuilt.
        self.status.setText("Searching…")

    @staticmethod
    def _what_it_is(item) -> str:
        """The Affinity column, for a row that may have no Affinity in it."""
        if item.get("has_affinity"):
            return item["affinity_version"] or "installed"
        if item.get("wine"):
            return "not installed yet"
        return "empty prefix"

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_searched", False):
            return
        self._searched = True
        QTimer.singleShot(0, self._search)

    def _search(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._do_search()
        finally:
            QApplication.restoreOverrideCursor()

    def _do_search(self):
        self.found = discover.find_installations()
        self.tree.clear()
        new = incomplete = 0
        for item in self.found:
            managed = item["managed_as"]
            row = QTreeWidgetItem(
                [
                    "",
                    managed or item["suggested_name"],
                    self._what_it_is(item),
                    item["wine"] or "—",
                    item["path"],
                ]
            )
            if managed:
                # Not tickable, but still selectable. setDisabled() was the
                # obvious way to say "nothing to do here" and took the row out
                # of selection with it -- so "Open folder" went dead on exactly
                # the prefixes somebody is most likely to want to look inside.
                row.setFlags(row.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                row.setText(1, f"{managed}  (already managed)")
                dim = QBrush(QColor("#8a8496"))
                for column in range(self.tree.columnCount()):
                    row.setForeground(column, dim)
            else:
                row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable
                             | Qt.ItemFlag.ItemIsEditable)
                # Complete installs start ticked. An incomplete one is listed
                # and tickable but not chosen for the user: adding a half-built
                # prefix to the list is a decision, not a default.
                row.setCheckState(0, Qt.CheckState.Checked if item.get("has_affinity")
                                  else Qt.CheckState.Unchecked)
                new += 1
                if not item.get("has_affinity"):
                    incomplete += 1
            row.setData(0, Qt.ItemDataRole.UserRole, item)
            self.tree.addTopLevelItem(row)
        self.adopt_button.setEnabled(new > 0)
        note = ""
        if incomplete:
            note = (f" {incomplete} of them has no Affinity installed yet — an "
                    "interrupted install looks like that, and managing it lets "
                    "Configure finish the job." if incomplete == 1 else
                    f" {incomplete} of them have no Affinity installed yet — an "
                    "interrupted install looks like that, and managing one lets "
                    "Configure finish the job.")
        self.status.setText(
            f"{len(self.found)} prefix(es) found, {new} not yet managed.{note} "
            "Names are editable — double-click one. Ticked entries are added to "
            "the list; nothing is moved unless you ask."
        )
        self._selection_changed()

    def _selection_changed(self):
        self.open_button.setEnabled(bool(self.tree.selectedItems()))

    def _open_selected(self):
        """Show the prefix in the file manager.

        QDesktopServices rather than xdg-open: it is the same mechanism without
        a subprocess, and it honours the desktop's own file manager."""
        rows = self.tree.selectedItems()
        if not rows:
            return
        data = rows[0].data(0, Qt.ItemDataRole.UserRole)
        path = Path(data["path"])
        if not path.is_dir():
            QMessageBox.warning(self, "Not there any more",
                                f"{path} no longer exists.")
            self._search()
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(
                self, "Could not open it",
                f"The desktop refused to open {path}. It is still there; open "
                "it by hand if you need to look.")

    def _adopt(self):
        move = self.move_box.isChecked()
        added, problems, moved = 0, [], []
        for i in range(self.tree.topLevelItemCount()):
            row = self.tree.topLevelItem(i)
            data = row.data(0, Qt.ItemDataRole.UserRole)
            if data["managed_as"] or row.checkState(0) != Qt.CheckState.Checked:
                continue
            name = row.text(1).strip()
            path = Path(data["path"])
            if move:
                # Through coldstart, which is the one place that knows how to
                # move a prefix: a rename where it can be one, no
                # copy-then-delete across filesystems unless it is asked for,
                # absolute symlinks inside repointed, and the launchers that
                # name the old path rewritten with a copy kept beside each.
                # This used to call discover.move_into_base, which did none of
                # that -- it did the copy-then-delete that maintenance.relocate
                # exists to refuse, and left every desktop entry pointing at a
                # directory that had gone.
                try:
                    self.manager.lock.claim(name, f"Move {path.name}")
                except oplock.InUse as exc:
                    problems.append(f"{name}: {exc}")
                    continue
                try:
                    _, notes = coldstart.adopt_by_moving(
                        self.reg, data, name, base=registry.base_dir())
                    added += 1
                    moved += notes
                except (maintenance.NotAPrefix, maintenance.DestinationInUse,
                        maintenance.NotEnoughSpace, maintenance.Busy,
                        maintenance.CloneFailed, registry.InvalidName,
                        registry.DuplicateName, registry.PathInUse, OSError) as e:
                    problems.append(f"{name}: {e}")
                finally:
                    self.manager.lock.release(name)
                continue
            try:
                self.reg.add(name, path)
                added += 1
            except (registry.InvalidName, registry.DuplicateName, registry.PathInUse) as e:
                problems.append(f"{name}: {e}")
        if problems:
            QMessageBox.warning(
                self,
                "Some were skipped" if added else "Nothing was added",
                "\n".join(problems[:12]),
            )
        if moved:
            QMessageBox.information(self, "Moved", "\n".join(moved[:14]))
        if added:
            self.accept()
        else:
            self._search()


# ── three kinds of copy ──────────────────────────────────────────────────────
#
# Snapshot, clone and backup all "copy a prefix", and picking the wrong one is
# how somebody finds out after an upgrade that what they kept cannot bring back
# what they lost. So every one of the three dialogs opens with the same table,
# with its own row marked, and the buttons that start them sit together with a
# line under each saying what it is for.

COPY_KINDS = (
    ("backup", "Back up",
     "An exact copy of the whole prefix, plus the desktop files around it: "
     "the menu entry, what opens .afphoto/.afdesign/.afpub, Wine's file-type "
     "definitions, and launchers that name the prefix. Kept wherever you "
     "choose. Never launched.",
     "Before an install or an upgrade. Restoring puts all of it back.",
     "The prefix's full size"),
    ("clone", "Clone",
     "A second prefix, added to the list, that you launch and change.",
     "To try something without touching the original. It is live: using it "
     "changes it, so it is not something to fall back to.",
     "The prefix's full size, in the base directory"),
    ("snapshot", "Snapshot",
     "Just the settings: preferences, workspaces, shortcuts, recent files.",
     "Before changing settings. Restores into the same or another prefix.",
     "A few MB, kept by the manager"),
)

COPY_CAPTIONS = {
    "backup": "Frozen copy of everything, kept where you choose. For undoing an install.",
    "clone": "A second prefix to launch and experiment in.",
    "snapshot": "Just the settings. Megabytes, not gigabytes.",
}


def kinds_legend(current: str) -> QLabel:
    rows = []
    for key, name, what, when, size in COPY_KINDS:
        mark = "▶ " if key == current else ""
        weight = "font-weight:600;" if key == current else "opacity:0.8;"
        rows.append(
            f"<tr style='{weight}'><td style='padding:4px 10px 4px 0;"
            f"white-space:nowrap;vertical-align:top'>{mark}<b>{name}</b></td>"
            f"<td style='padding:4px 0'>{what}<br><i>{when}</i> "
            f"&nbsp;·&nbsp; {size}</td></tr>")
    label = QLabel("<table>" + "".join(rows) + "</table>")
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setObjectName("descriptionLabel")
    return label


_RUNNING_THREADS = set()


def keep_until_finished(thread):
    """Hold a reference to a QThread until it ends.

    A dialog can be closed while its background check is still waiting on the
    network. If the dialog's reference was the only one, Python collects the
    QThread while it runs, and Qt aborts the whole process for that."""
    _RUNNING_THREADS.add(thread)
    thread.finished.connect(lambda: _RUNNING_THREADS.discard(thread))


class TaskThread(QThread):
    """One long job off the UI thread: fn(progress) -> result."""

    done = pyqtSignal(object, str)
    progress = pyqtSignal(int)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            result = self.fn(self.progress.emit)
        except Exception as exc:                  # surfaced, not swallowed
            self.done.emit(None, str(exc))
            return
        self.done.emit(result, "")


class KindConfirmDialog(SizedDialog):
    """A yes/no that says which of the three kinds of copy is being made."""

    FIT_MIN_WIDTH = 700

    def __init__(self, parent, title, kind, body, confirm):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        ui.apply(self)
        layout = QVBoxLayout(self)
        layout.addWidget(kinds_legend(kind))
        layout.addSpacing(8)
        text = QLabel(body)
        text.setWordWrap(True)
        layout.addWidget(text)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(confirm)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class BackupDialog(SizedDialog):
    """Choose where, then back up.

    Every location is shown with its free space and with whether it is on the
    same physical disk as the prefix. That second fact is the one people get
    wrong: /home and /mnt/work can be two partitions of one drive, and a backup
    that is "somewhere else" by filesystem is not somewhere else when that
    drive fails."""

    FIT_MIN_WIDTH = 760

    def __init__(self, parent, entry):
        super().__init__(parent)
        self.entry = entry
        self.prefix = Path(entry["path"])
        self.setWindowTitle(f"Back up {entry['name']}")
        self.setModal(True)
        ui.apply(self)
        self.plan = None

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.size = maintenance._du(self.prefix)
        finally:
            QApplication.restoreOverrideCursor()

        layout = QVBoxLayout(self)
        layout.addWidget(kinds_legend("backup"))
        layout.addSpacing(8)

        self.banner = ActivityBanner(self, self.prefix, name=entry["name"],
                                     waiting_for="back it up")
        layout.addWidget(self.banner)

        layout.addWidget(QLabel(
            f"<b>Where</b> — {entry['name']} needs about "
            f"{probe.human_size(self.size)}"))
        self.group = QButtonGroup(self)
        self.locations_box = QVBoxLayout()
        layout.addLayout(self.locations_box)
        for loc in backups.candidate_locations(self.prefix):
            self._add_location(loc)
        row = QHBoxLayout()
        other = QPushButton("Another folder…")
        other.clicked.connect(self._choose)
        row.addWidget(other)
        row.addStretch(1)
        layout.addLayout(row)
        self.make_default = QCheckBox("Make this the default backup location")
        layout.addWidget(self.make_default)

        layout.addSpacing(6)
        form = QFormLayout()
        self.label = QLineEdit()
        self.label.setPlaceholderText("optional, e.g. before 3.3")
        form.addRow("Label", self.label)
        layout.addLayout(form)

        self.host = QCheckBox(
            "Include the desktop files — the menu entry, document "
            "associations, Wine's file-type definitions and the launchers "
            "naming this prefix. Restoring them is what undoes an install.")
        self.host.setChecked(True)
        layout.addWidget(self.host)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setObjectName("descriptionLabel")
        layout.addWidget(self.status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText("Back up")
        buttons.accepted.connect(self._confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.group.buttonToggled.connect(lambda *_: self._check())
        if self.group.buttons():
            self.group.buttons()[0].setChecked(True)
        self.banner.changed.connect(lambda *_: self._check())
        self._check()

    def _add_location(self, loc):
        radio = QRadioButton(f"{loc.path}" + (f"   ({loc.why})" if loc.why else ""))
        radio.setProperty("location", loc)
        self.group.addButton(radio)
        self.locations_box.addWidget(radio)
        note = QLabel(loc.describe(self.size))
        note.setWordWrap(True)
        note.setObjectName("cautionText" if (loc.same_disk or not loc.usable
                                             or loc.free < self.size * 1.05)
                           else "descriptionLabel")
        note.setContentsMargins(26, 0, 0, 4)
        self.locations_box.addWidget(note)
        return radio

    def _choose(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "Where should the backup go?", str(Path.home()))
        if not chosen:
            return
        radio = self._add_location(
            backups.describe_location(chosen, self.prefix, "chosen now"))
        radio.setChecked(True)

    def chosen_location(self):
        button = self.group.checkedButton()
        return button.property("location") if button else None

    def _check(self):
        # Only Affinity itself stops a backup. Leftovers from old sessions
        # with no wineserver write nothing, so they cannot tear the copy.
        loc = self.chosen_location()
        ok = bool(loc) and not self.banner.blocks() and loc.usable and loc.free >= self.size * 1.05
        self.ok.setEnabled(ok)
        if loc and loc.same_disk:
            self.status.setText(
                "This location is on the same physical disk as the prefix. "
                "Fine for undoing an install; it will not survive the disk "
                "failing.")
        elif loc and loc.same_disk is False:
            self.status.setText(f"On a different disk ({loc.disk}): this also "
                                "survives the prefix's disk failing.")
        else:
            self.status.setText("")

    def _confirm(self):
        loc = self.chosen_location()
        if loc is None:
            return
        try:
            self.plan = backups.plan_backup(
                self.entry["name"], self.prefix, loc.path,
                label=self.label.text(), include_host=self.host.isChecked(),
                size=self.size)
        except (backups.BackupError, maintenance.NotEnoughSpace, OSError) as exc:
            QMessageBox.warning(self, "Cannot back up there", str(exc))
            return
        if self.make_default.isChecked():
            backups.set_default_location(loc.path)
        self.accept()


class RestoreBackupDialog(SizedDialog):
    """What a restore will do, spelled out, before anything happens."""

    FIT_MIN_WIDTH = 720

    def __init__(self, parent, backup):
        super().__init__(parent)
        self.backup = backup
        self.plan = None
        self.setWindowTitle(f"Restore {backup}")
        self.setModal(True)
        ui.apply(self)
        layout = QVBoxLayout(self)

        intro = QLabel(
            f"<b>{backup}</b><br>{backup.path}<br>"
            f"Back to <b>{backup.prefix_path}</b>. Nothing is deleted: "
            "whatever is replaced is kept aside, so a restore can itself be "
            "undone.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # Leftovers block here, unlike a backup: the prefix is about to be
        # moved aside, and they have files in it open.
        self.banner = ActivityBanner(self, backup.prefix_path,
                                     waiting_for="restore over it",
                                     leftovers_block=True)
        layout.addWidget(self.banner)

        self.do_prefix = QCheckBox("The prefix")
        self.do_prefix.setChecked(True)
        self.do_host = QCheckBox(
            "The desktop files — menu entry, document associations, Wine's "
            "file-type definitions, launchers")
        self.do_host.setChecked(bool(backup.host_files or backup.mimeapps))
        self.do_host.setEnabled(bool(backup.host_files or backup.mimeapps))
        for box in (self.do_prefix, self.do_host):
            box.toggled.connect(self._replan)
            layout.addWidget(box)

        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setObjectName("descriptionLabel")
        layout.addWidget(self.detail)
        self.caution = QLabel("")
        self.caution.setWordWrap(True)
        self.caution.setObjectName("cautionText")
        layout.addWidget(self.caution)

        self.arm = ArmBox("Yes, restore this backup",
                          "Required — Restore stays off until this is ticked.")
        self.arm.toggled.connect(self._arm)
        layout.addWidget(self.arm)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setText("Restore")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.banner.changed.connect(lambda *_: self._replan())
        self._replan()

    def _replan(self):
        self.plan, problem = None, ""
        if not (self.do_prefix.isChecked() or self.do_host.isChecked()):
            problem = "Choose at least one of the two."
        else:
            try:
                self.plan = backups.plan_restore(
                    self.backup, restore_prefix=self.do_prefix.isChecked(),
                    restore_host=self.do_host.isChecked())
            except (backups.BackupError, maintenance.NotEnoughSpace, OSError) as exc:
                problem = str(exc)
        self.detail.setText("\n".join(self.plan.describe()) if self.plan else "")
        if self.do_prefix.isChecked() and self.banner.blocks():
            problem = ("Not while anything is running in the prefix -- see "
                       "above.")
            self.plan = None
        self.caution.setText(problem)
        self._arm()

    def _arm(self):
        self.ok.setEnabled(self.plan is not None and self.arm.isChecked())


class BackupsDialog(SizedDialog):
    """Every backup the manager knows of -- including ones whose prefix is gone
    and ones on a disk that is not plugged in right now."""

    FIT_MIN_WIDTH = 900
    COLUMNS = ["Taken", "Prefix", "Label", "Size", "Where", "Status"]

    def __init__(self, parent, manager, prefix_name=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Backups")
        self.setModal(True)
        ui.apply(self)
        layout = QVBoxLayout(self)
        layout.addWidget(kinds_legend("backup"))
        layout.addSpacing(6)

        row = QHBoxLayout()
        row.addWidget(QLabel("Show"))
        self.filter = QComboBox()
        self.filter.addItem("All prefixes", None)
        for e in manager.reg.entries:
            self.filter.addItem(e["name"], e["name"])
        if prefix_name:
            index = self.filter.findData(prefix_name)
            if index >= 0:
                self.filter.setCurrentIndex(index)
        self.filter.currentIndexChanged.connect(self._reload)
        row.addWidget(self.filter)
        row.addStretch(1)
        layout.addLayout(row)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(self.COLUMNS))
        self.tree.setHeaderLabels(self.COLUMNS)
        self.tree.setRootIsDecorated(False)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.tree, 1)

        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setObjectName("descriptionLabel")
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.detail)

        buttons = QHBoxLayout()
        self.restore_button = QPushButton("Restore…")
        self.verify_button = QPushButton("Verify")
        self.open_button = QPushButton("Show folder")
        self.delete_button = QPushButton("Delete")
        close = QPushButton("Close")
        self.restore_button.clicked.connect(self._restore)
        self.verify_button.clicked.connect(self._verify)
        self.open_button.clicked.connect(self._open)
        self.delete_button.clicked.connect(self._delete)
        close.clicked.connect(self.reject)
        for b in (self.restore_button, self.verify_button, self.open_button,
                  self.delete_button):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self._reload()

    def _reload(self):
        self.tree.clear()
        for b in backups.listing(self.filter.currentData()):
            status = {"ok": "ok", "partial": "did not finish",
                      "unreachable": "not reachable", "damaged": "damaged"}[b.status]
            row = QTreeWidgetItem([
                b.when, b.prefix_name, b.label or "—",
                probe.human_size(b.bytes) if b.bytes else "—",
                str(b.location), status])
            row.setData(0, Qt.ItemDataRole.UserRole, b)
            self.tree.addTopLevelItem(row)
        for i in range(len(self.COLUMNS)):
            self.tree.resizeColumnToContents(i)
        self._selection_changed()

    WHY_NOT = {
        "partial": "this backup did not finish, so there is no record of what "
                   "it should contain to check it against, and it may be "
                   "missing files. Delete it and back up again.",
        "unreachable": "its folder cannot be reached -- a disk that is not "
                       "plugged in or mounted. Connect it and reopen this list.",
        "damaged": "its record cannot be read, so what it holds is unknown.",
    }

    def selected(self):
        rows = self.tree.selectedItems()
        return rows[0].data(0, Qt.ItemDataRole.UserRole) if rows else None

    def _selection_changed(self):
        b = self.selected()
        self.restore_button.setEnabled(bool(b) and b.status == "ok")
        self.verify_button.setEnabled(bool(b) and b.status == "ok")
        self.open_button.setEnabled(bool(b) and b.path.exists())
        self.delete_button.setEnabled(bool(b) and b.status != "unreachable")
        # A switched-off button says nothing about why, so the reason goes on
        # the button and in the detail line both.
        why = self.WHY_NOT.get(b.status, "") if b else "Choose a backup first."
        for button in (self.restore_button, self.verify_button):
            button.setToolTip(why)
        if not b:
            self.detail.setText("Nothing here yet." if not self.tree.topLevelItemCount()
                                else "Choose a backup.")
            return
        bits = [str(b.path)]
        if b.prefix_path:
            bits.append(f"Of {b.prefix_path}" + (f", on {b.machine}" if b.machine else ""))
        if b.host_files:
            bits.append(f"Includes {len(b.host_files)} desktop file(s) and the "
                        "Affinity document associations.")
        elif b.status == "ok":
            bits.append("The prefix only — no desktop files.")
        if b.prefix_path and b.path.exists():
            disk = backups.describe_location(b.location, b.prefix_path)
            if disk.same_disk:
                bits.append("On the same physical disk as the prefix.")
        bits += b.notes
        if why:
            bits.append(f"<b>Verify and Restore are not available:</b> {why}")
        self.detail.setText("<br>".join(html.escape(x) if not x.startswith("<b>")
                                        else x for x in bits))

    def _restore(self):
        b = self.selected()
        if not b:
            return
        dialog = RestoreBackupDialog(self, b)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.plan is None:
            return
        self.accept()
        self.manager.run_restore(dialog.plan)

    def _verify(self):
        b = self.selected()
        if not b:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            problems = backups.verify(b)
        finally:
            QApplication.restoreOverrideCursor()
        if problems:
            QMessageBox.warning(self, "This backup does not match its record",
                                "\n".join(problems[:10]))
        else:
            QMessageBox.information(
                self, "Verified",
                f"{b.files} files and {probe.human_size(b.bytes)}, as recorded.")

    def _open(self):
        b = self.selected()
        if b:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(b.path)))

    def _delete(self):
        b = self.selected()
        if not b:
            return
        if not ConfirmDialog.ask(
                self, "Delete this backup",
                f"Permanently delete <b>{b}</b>?<br><br>{b.path}<br>"
                f"{probe.human_size(b.bytes) if b.bytes else ''}<br><br>"
                "There is no undo, and a backup is the thing you would undo "
                "with.", confirm="Delete backup"):
            return
        try:
            backups.remove(b)
        except (backups.BackupError, OSError) as exc:
            QMessageBox.warning(self, "Could not delete it", str(exc))
        self._reload()


class SettingsDialog(SizedDialog):
    FIT_MIN_WIDTH = 620

    """Where prefixes live, and which theme to wear.

    The base directory defaults to ~/.AffinityLinuxManager and is changed here
    rather than demanded on first run -- most people never move it, and an
    install that opens with a directory chooser is an install that gets
    cancelled."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        ui.apply(self)

        self._original_base = registry.base_dir()
        self._original_theme = ui.current_theme()
        self.base_changed = False
        self.theme_changed = False

        form = QFormLayout()

        row = QHBoxLayout()
        self.base = QLineEdit(str(self._original_base))
        browse = QPushButton("Browse…")
        browse.setObjectName("actionButton")
        browse.clicked.connect(self._browse)
        row.addWidget(self.base, 1)
        row.addWidget(browse)
        holder = QWidget()
        holder.setLayout(row)
        form.addRow("Base directory", holder)

        row2 = QHBoxLayout()
        self.installer_script = QLineEdit(str(installer.describe().get("script") or ""))
        pick_installer = QPushButton("Browse\u2026")
        pick_installer.setObjectName("actionButton")
        pick_installer.clicked.connect(self._pick_installer)
        fetch = QPushButton("Fetch branch\u2026")
        fetch.setObjectName("actionButton")
        fetch.setToolTip(
            f"Clone or update {installer.PREFERRED_BRANCH} into the Manager "
            "directory and use that, so installs do not depend on a development "
            "checkout being on the right branch."
        )
        fetch.clicked.connect(self._fetch_branch)
        row2.addWidget(self.installer_script, 1)
        row2.addWidget(pick_installer)
        row2.addWidget(fetch)
        holder2 = QWidget()
        holder2.setLayout(row2)
        form.addRow("AffinityOnLinux installer", holder2)

        self.installer_state = QLabel(installer.summary())
        self.installer_state.setObjectName("descriptionLabel")
        self.installer_state.setWordWrap(True)
        form.addRow("", self.installer_state)

        row3 = QHBoxLayout()
        self._original_backups = backups.default_location()
        self.backup_location = QLineEdit(str(self._original_backups))
        pick_backups = QPushButton("Browse…")
        pick_backups.setObjectName("actionButton")
        pick_backups.clicked.connect(self._pick_backups)
        row3.addWidget(self.backup_location, 1)
        row3.addWidget(pick_backups)
        holder3 = QWidget()
        holder3.setLayout(row3)
        form.addRow("Backup location", holder3)
        backups_note = QLabel(
            "Where 'Back up' offers first. Any folder can still be chosen for "
            "a single backup. For a backup that survives a disk failing, pick "
            "one on a different physical disk -- the Back up dialog says which "
            "ones are.")
        backups_note.setObjectName("descriptionLabel")
        backups_note.setWordWrap(True)
        form.addRow("", backups_note)

        self.theme = QComboBox()
        for name in ui.THEMES:
            self.theme.addItem(ui.DISPLAY_NAMES[name], name)
        self.theme.setCurrentIndex(ui.THEMES.index(self._original_theme))
        form.addRow("Theme", self.theme)

        note = QLabel(
            f"Prefixes are created as subdirectories of the base directory, "
            f"alongside a '{registry.MANAGER_SUBDIR}' subdirectory holding this "
            "application's metadata. Prefixes already managed keep their own "
            "paths — changing this only affects new ones. Themes come from the "
            "AffinityOnLinux installer, so the two match."
        )
        note.setObjectName("descriptionLabel")
        note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def _browse(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "Base directory for managed prefixes", self.base.text() or str(Path.home())
        )
        if chosen:
            self.base.setText(chosen)

    def _pick_installer(self):
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "AffinityLinuxInstaller.py",
            self.installer_script.text() or str(Path.home()),
            "Python (*.py);;All files (*)",
        )
        if chosen:
            self.installer_script.setText(chosen)
            self._restate()

    def _fetch_branch(self):
        lines = []
        for line in installer.fetch_managed_checkout():
            lines.append(line)
        QMessageBox.information(self, "Fetch branch", "\n".join(lines) or "Nothing happened.")
        from affinity_manager import settings

        fetched = settings.get("installer_script")
        if fetched:
            self.installer_script.setText(fetched)
        self._restate()

    def _restate(self):
        path = self.installer_script.text().strip()
        info = installer.describe(Path(path)) if path else installer.describe()
        self.installer_state.setText(installer.summary(info))

    def _accept(self):
        chosen = Path(self.base.text().strip()).expanduser() if self.base.text().strip() else registry.DEFAULT_BASE
        if chosen != self._original_base:
            try:
                (chosen / registry.MANAGER_SUBDIR).mkdir(parents=True, exist_ok=True)
            except OSError as e:
                QMessageBox.critical(self, "Cannot use this directory", str(e))
                return
            registry.set_base_dir(chosen)
            self.base_changed = True
        script = self.installer_script.text().strip()
        if script:
            from affinity_manager import settings as _settings

            if not Path(script).expanduser().is_file():
                QMessageBox.warning(self, "Installer not found", f"{script} does not exist.")
                return
            _settings.set("installer_script", str(Path(script).expanduser()))

        chosen_backups = self.backup_location.text().strip()
        if chosen_backups and Path(chosen_backups).expanduser() != self._original_backups:
            backups.set_default_location(chosen_backups)

        theme = self.theme.currentData()
        if theme != self._original_theme:
            ui.set_theme(theme)
            self.theme_changed = True
        self.accept()

    def _pick_backups(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "Default backup location", self.backup_location.text())
        if chosen:
            self.backup_location.setText(chosen)


class ManagerWindow(QMainWindow):
    COLUMNS = ["Name", "Flags", "Affinity", "Wine", "Size", "State", "Path"]

    def __init__(self):
        super().__init__()
        self.reg = registry.Registry()
        self.probe_thread = None
        # Setup pages, one per prefix, built on first entry. Kept rather than
        # rebuilt because building one constructs the whole installer window;
        # bounded in _drop_spare_setup_pages, because keeping every prefix's is
        # not the same thing as keeping the useful ones.
        self._setup_pages = {}
        # One operation at a time, across every prefix. See oplock: two
        # prefixes provisioning at once collide in the distro package manager
        # whatever this application believes, so this is a correctness matter
        # and not a preference.
        self.lock = oplock.OperationLock()
        self.setWindowTitle(f"Affinity on Linux Manager {__version__}")
        self.resize(1080, 560)
        ui.apply(self)
        self._build()
        self._ensure_manager_dir()
        self.refresh()
        # The watchdog. Every release ought to be explicit and in this file it
        # is, but a hosted installer's work runs in daemon threads that can die
        # without reaching any release, so something has to notice. Two seconds
        # is also what keeps the elapsed time in the caution line moving.
        self._lock_timer = QTimer(self)
        self._lock_timer.setInterval(2000)
        self._lock_timer.timeout.connect(self._lock_tick)
        self._lock_timer.start()
        # After the window is up, so these have something to appear over and
        # the list behind them already shows what they name.
        QTimer.singleShot(0, self._report_interrupted)
        QTimer.singleShot(0, self._first_run)

    # ── the first run ────────────────────────────────────────────────────────

    def _first_run(self):
        """Offer something sensible when the prefix list is empty.

        Once, and then not again: coldstart records that the offer was made, so
        a machine-wide walk does not come back every time somebody forgets
        their last prefix. Nothing here acts on its own either -- an Affinity
        install that predates the manager is somebody's working setup, and the
        manager noticing it is not permission to change it."""
        if self.reg.entries:
            return
        self.status.setText("Looking for Affinity installations…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        # Painted before the walk, not after it. Both of the lines above only
        # schedule; without this the cursor and the sentence appear when the
        # search that they are there to explain has already finished.
        QApplication.processEvents()
        try:
            situation = coldstart.look(self.reg)
        except OSError as exc:
            self.status.setText(f"Could not search for installations: {exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        if situation.state == coldstart.FRESH:
            # Also recorded. Nothing was found, and walking the machine again
            # on every start in case something appears is not a trade worth
            # making -- "Find installations" is one click and is what somebody
            # who has just installed Affinity elsewhere would reach for.
            coldstart.mark_asked()
            self.status.setText(
                "No Affinity installation found. 'New prefix' creates one under "
                f"{situation.base}; 'Adopt existing' takes over one this search "
                "did not reach.")
            return
        if situation.state != coldstart.ADOPTABLE:
            return
        self._offer_adoption(situation)

    def _offer_adoption(self, situation):
        # Recorded before the answer, not after: the point is that the offer
        # was made. Whatever the user decides -- including "decide later", and
        # including closing the window -- this must not reappear on the next
        # start, and must not re-arm when the last prefix is forgotten.
        coldstart.mark_asked()
        dialog = FirstRunDialog(self, situation)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.status.setText(
                f"{len(situation.installs)} installation(s) found and left alone. "
                "'Find installations' offers them again.")
            return
        name = dialog.chosen_name()
        install = dialog.install

        if dialog.choice == dialog.IN_PLACE:
            try:
                coldstart.adopt_in_place(self.reg, install, name)
            except (registry.InvalidName, registry.DuplicateName,
                    registry.PathInUse) as exc:
                QMessageBox.warning(self, "Cannot manage this prefix", str(exc))
                return
            self.refresh()
            self.status.setText(f"{name} is managed where it is: {install['path']}")
            return

        try:
            self._busy_start(f"Moving {install['path']}", 100,
                             prefix=name, operation="Move into the base directory")
        except oplock.InUse as exc:
            self._refuse(exc)
            return
        try:
            entry, notes = coldstart.adopt_by_moving(
                self.reg, install, name, base=situation.base,
                progress=lambda pct: self._busy_step(pct, f"Moving {name} — {pct}%"))
        except (maintenance.NotAPrefix, maintenance.DestinationInUse,
                maintenance.NotEnoughSpace, maintenance.Busy,
                maintenance.CloneFailed, registry.InvalidName,
                registry.DuplicateName, registry.PathInUse) as exc:
            self._busy_done("Move failed")
            QMessageBox.critical(self, "Could not move it", str(exc))
            return
        self._busy_done(f"{name} moved to {entry['path']}")
        desktopentry.refresh_menu()
        self.refresh()
        QMessageBox.information(
            self, "Moved", f"{name} is now at {entry['path']}.\n\n"
            + "\n".join(notes[:10]))

    def copy_settings_selected(self):
        entry = self.selected_entry()
        if entry:
            self.offer_settings_copy(entry)

    def offer_settings_copy(self, entry, preselect=None):
        """Returns True when settings were copied, False when not (refused,
        cancelled, failed)."""
        return bool(self._offer_settings_copy(entry, preselect))

    def _offer_settings_copy(self, entry, preselect=None):
        """Bring settings, workspaces, recents and drive letters into a prefix.

        Refused while Affinity runs in the DESTINATION -- it would overwrite
        what was copied on exit. A running SOURCE is only a caution: reading it
        is harmless, it just may not be the last word."""
        path = Path(entry["path"])
        pids = probe.running_pids(path) if path.exists() else []
        if pids:
            QMessageBox.warning(
                self, "Affinity is running there",
                f"Affinity is running in {entry['name']} (pid {pids[0]}). Close "
                "it first: it would write its own settings over these when it "
                "exits.")
            return

        destination = prefsseed.destination_for(path)
        found = prefsseed.sources(_settings_source_dirs(self.reg), exclude=path)

        dialog = CarrySettingsDialog(self, path, destination, found, preselect=preselect)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source = dialog.chosen_source()
        if source is None:
            return
        letters = dialog.chosen_letters()

        try:
            self._busy_start(f"Copying settings into {entry['name']}",
                             prefix=entry["name"], operation="Copy settings")
        except oplock.InUse as exc:
            self._refuse(exc)
            return
        try:
            result = prefsseed.seed(source, destination, mode=dialog.mode())
        except OSError as exc:
            self._busy_done("Copying settings failed", owner=entry["name"])
            # In REPLACE mode the old settings have already been renamed aside
            # by now, so the prefix has no Settings folder at all and the only
            # copy is under a name the user has never seen.
            aside = prefsseed.aside_of(destination)
            where = (f"\n\nThe settings that were there are at {aside}. "
                     "Rename it back to 'Settings' to undo this."
                     if aside else "")
            QMessageBox.critical(self, "Could not copy the settings",
                                 f"{exc}{where}")
            return False

        drive_notes = []
        if letters:
            try:
                drive_notes = prefsseed.import_drive_letters(path, letters)
            except prefsseed.PrefixNotReady as exc:
                drive_notes = [str(exc)]

        prefixlog.write(entry["name"],
                        "Settings copied from %s: %d added, %d replaced, %d kept; "
                        "also %s; drive letters: %s"
                        % (source.path, len(result.added), len(result.replaced),
                           len(result.kept), ", ".join(result.extras) or "nothing",
                           "; ".join(drive_notes) or "none"))
        self._busy_done(f"Settings copied into {entry['name']}", owner=entry["name"])

        lines = [f"{len(result.added)} added and {len(result.replaced)} replaced "
                 f"in {destination}."]
        if result.extras:
            lines.append("Also copied: " + ", ".join(result.extras) + ".")
        if result.saved_aside:
            lines.append(f"What was there is kept at {result.saved_aside.name}.")
        if drive_notes:
            lines.append("Drive letters:\n  " + "\n  ".join(drive_notes))
        QMessageBox.information(self, "Settings copied", "\n\n".join(lines))
        return True

    # ── recovery ─────────────────────────────────────────────────────────────

    def _report_interrupted(self):
        """Say what did not finish, once, at startup.

        Anything still marked working was written by a manager that is gone --
        single-instance checking established that before this window existed --
        so the operation it was tracking cannot still be running. Recovering it
        quietly would be the easy thing and the wrong one: an interrupted
        install leaves a prefix that looks finished, and the only warning
        anybody gets is this."""
        changed = self.reg.recover()
        if not changed:
            return
        self.refresh()

        blocks = []
        for entry in changed:
            condition = prefixstate.classify(entry["path"], entry=entry)
            lines = [f"<b>{entry['name']}</b> — {condition.detail}"]
            if condition.suggestion:
                lines.append(condition.suggestion)
            tail = self._log_tail(entry)
            if tail:
                lines.append(f"<pre>{tail}</pre>")
            blocks.append("<br>".join(lines))

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Unfinished work")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(
            f"{len(changed)} prefix{'es' if len(changed) > 1 else ''} had an "
            "operation running when the manager last closed."
        )
        box.setInformativeText("<br><br>".join(blocks))
        ui.apply(box)
        box.exec()

    @staticmethod
    def _log_tail(entry, limit=1200):
        """What the log said after the operation began.

        log_offset was recorded when it started, so this is the part that
        matters rather than the end of a file that may have scrolled past it.
        Returns nothing when there is no log yet, which is the normal case
        until per-prefix logs exist."""
        path = entry.get("log")
        offset = entry.get("log_offset")
        if not path or offset is None:
            return ""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(offset)
                text = f.read(limit).strip()
        except OSError:
            return ""
        return text

    def _ensure_manager_dir(self):
        """Create <base>/Manager up front so the base directory looks managed
        before anything is installed, and so a base on an unwritable disk fails
        here rather than at the end of an install."""
        try:
            registry.manager_dir().mkdir(parents=True, exist_ok=True)
        except OSError as e:
            QMessageBox.critical(
                self,
                "Cannot use this base directory",
                f"{registry.base_dir()} could not be prepared:\n{e}",
            )

    def open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.base_changed:
            # Entries hold absolute paths, so prefixes registered under the old
            # base keep working; only new ones land under the new one.
            self.reg = registry.Registry()
            self._ensure_manager_dir()
        if dialog.theme_changed:
            self.apply_theme()
        self._check_installer()
        self.refresh()

    def apply_theme(self):
        ui.apply(self)
        # A dynamic-property selector is resolved when the widget is polished,
        # so a restyle after the fact needs the polish redone by hand.
        for button in self.findChildren(QPushButton):
            if button.property("class"):
                button.style().unpolish(button)
                button.style().polish(button)
        self.theme_button.setText(ui.DISPLAY_NAMES[ui.next_theme()])

    def cycle_theme(self):
        ui.set_theme(ui.next_theme())
        self.apply_theme()

    # ── the installer's own shape ────────────────────────────────────────────
    #
    # A top bar, then a content area split left-to-right: grouped cards of
    # stacked full-width actions on the left, the thing being worked on in the
    # middle. The button styles were drawn for exactly this -- #actionButton is
    # a 100px-radius pill with left-aligned text and generous padding, which
    # reads as an oversized lozenge in a toolbar row and as a proper menu button
    # stacked in a card.

    @staticmethod
    def _primary(button):
        """Mark a button as the accent action.

        The theme selects on QPushButton#actionButton[class="primary"], a Qt
        dynamic property rather than an object name. Set before the widget is
        shown, as the installer does; changing it later needs an unpolish and
        polish to take effect."""
        button.setObjectName("actionButton")
        button.setProperty("class", "primary")
        return button

    def _action(self, label, slot, description=None, primary=False):
        button = QPushButton(label)
        button.setObjectName("actionButton")
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setMinimumHeight(44)
        button.clicked.connect(slot)
        if description:
            button.setToolTip(description)
        if primary:
            self._primary(button)
        return button

    def _button_card(self, title, actions):
        """One grouped card of stacked actions, in the installer's vocabulary.

        Built here rather than borrowed: create_button_group is tangled with the
        installer's icon loading and its own label bookkeeping, while the object
        names -- which is what the theme actually styles -- are free to use."""
        card = QFrame()
        card.setObjectName("buttonCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(card)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)

        for button in actions:
            layout.addWidget(button)
        return card

    def _captioned_card(self, title, pairs):
        card = self._button_card(title, [])
        layout = card.layout()
        for button, caption in pairs:
            layout.addWidget(button)
            note = QLabel(caption)
            note.setWordWrap(True)
            note.setObjectName("cardCaption")
            note.setContentsMargins(4, 0, 4, 6)
            layout.addWidget(note)
        return card

    def _build(self):
        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── top bar ──────────────────────────────────────────────────────────
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(20, 10, 20, 10)

        title = QLabel("Affinity on Linux Manager")
        title.setObjectName("titleLabel")
        top_layout.addWidget(title)
        top_layout.addStretch(1)

        settings_button = QPushButton("Settings")
        settings_button.setObjectName("zoomButton")
        settings_button.setMinimumHeight(30)
        settings_button.clicked.connect(self.open_settings)
        top_layout.addWidget(settings_button)

        self.theme_button = QPushButton(ui.DISPLAY_NAMES[ui.next_theme()])
        self.theme_button.setObjectName("themeToggle")
        self.theme_button.setMinimumHeight(30)
        self.theme_button.setToolTip("Switch theme")
        self.theme_button.clicked.connect(self.cycle_theme)
        top_layout.addWidget(self.theme_button)

        main_layout.addWidget(top_bar)

        # ── content: cards on the left, the prefixes in the middle ───────────
        content = QWidget()
        content.setObjectName("contentArea")
        content_layout = QHBoxLayout(content)
        content_layout.setSpacing(20)
        content_layout.setContentsMargins(20, 20, 20, 20)

        self.new_button = self._action(
            "New prefix", self.new_prefix,
            "Create a prefix under the base directory and install into it", primary=True)
        self.find_button = self._action(
            "Find installations", self.find_installations,
            "Search this machine for Affinity installations already present")
        self.adopt_button = self._action(
            "Adopt existing", self.adopt,
            "Manage an install already on disk, wherever it is")

        self.launch_button = self._action(
            "Launch", self.launch_selected, "Start Affinity in the selected prefix")
        self.commands_button = self._action(
            "Commands", self.show_commands,
            "Every way this prefix can be run -- copy, run, or add to the menu")
        self.installer_button = self._action(
            "Configure", self.open_installer,
            "Install, update and configure this prefix -- AffinityOnLinux, "
            "inside this window")
        self.default_button = self._action(
            "Make Default", self.make_default_selected,
            "The menu's Affinity entry, double-clicked documents and the Canva "
            "sign-in all go to this prefix")
        self.menu_button = self._action(
            "Add to menu", self.toggle_menu_selected,
            "A menu entry named after this prefix, beside the Default one. It "
            "does not take the document types")
        self.copy_settings_button = self._action(
            "Copy settings…", self.copy_settings_selected,
            "Bring preferences, workspaces, recent files and drive letters in "
            "from another prefix. Use after Configure, before first launch")
        self.snapshots_button = self._action(
            "Snapshots…", self.show_snapshots,
            "Dated copies of this prefix's preferences, shortcuts and recent "
            "files -- take one before anything risky")
        self.protect_button = self._action(
            "Protect", self.toggle_protection, "Mark this prefix as not deletable")
        self.rename_button = self._action(
            "Rename / Move…", self.rename_selected,
            "Change the prefix's name, and optionally move its folder to match. "
            "Menu entries, launchers, the log, snapshots and the Default follow")
        self.forget_button = self._action(
            "Stop managing", self.forget_selected,
            "Remove from the list. The directory is left alone")
        self.clone_button = self._action(
            "Clone…", self.clone_selected,
            "A second prefix you can launch and experiment in. Not a backup: "
            "using it changes it")
        self.backup_button = self._action(
            "Back up…", self.backup_selected,
            "An exact copy of the whole prefix and its desktop files, kept "
            "wherever you choose and never launched. For undoing an install")
        self.backups_button = self._action(
            "Backups…", self.show_backups,
            "Every backup: restore, verify, delete -- including ones whose "
            "prefix has gone or whose disk is unplugged")
        self.clean_button = self._action(
            "Clean", self.clean_selected,
            "Reclaim space: Wine builds this prefix does not use, downloaded archives, saved-aside copies")
        self.delete_button = self._action(
            "Delete", self.delete_selected, "Permanently delete this prefix")
        self.fonts_button = self._action(
            "Check fonts", self.check_fonts_selected,
            "Make sure every font in the prefix is registered, and remove fonts "
            "left by a different Wine -- the fix for bold text drawn in the wrong face")

        self.refresh_button = self._action(
            "Refresh", self.refresh, "Re-read the registry and re-inspect every prefix")

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(16)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self._button_card(
            "Prefixes", [self.new_button, self.find_button, self.adopt_button,
                         self.backups_button]))
        left_layout.addWidget(self._button_card(
            "Selected prefix",
            [self.launch_button, self.installer_button,
             self.copy_settings_button, self.commands_button,
             self.default_button, self.menu_button]))
        # The three kinds of copy together, each with a line saying what it is
        # for. They all "copy a prefix", and choosing the wrong one is found out
        # at the worst moment. Above the maintenance card rather than below it:
        # the first version put this third, under eight buttons, where Back up
        # -- the thing to do before an install -- needed a scroll to find.
        left_layout.addWidget(self._captioned_card(
            "Copies of this prefix",
            [(self.backup_button, COPY_CAPTIONS["backup"]),
             (self.clone_button, COPY_CAPTIONS["clone"]),
             (self.snapshots_button, COPY_CAPTIONS["snapshot"])]))
        left_layout.addWidget(self._button_card(
            "Maintenance",
            [self.clean_button, self.fonts_button, self.rename_button,
             self.protect_button, self.forget_button, self.delete_button]))
        left_layout.addWidget(self._button_card("View", [self.refresh_button]))
        left_layout.addStretch(1)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setObjectName("leftScroll")
        left_scroll.setWidget(left)
        left_scroll.setMaximumWidth(340)
        content_layout.addWidget(left_scroll, 2)

        # ── the list, under a status card ────────────────────────────────────
        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        middle_layout.setSpacing(12)
        middle_layout.setContentsMargins(0, 0, 0, 0)

        status_card = QFrame()
        status_card.setObjectName("statusCard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(16, 14, 16, 14)
        status_layout.setSpacing(6)

        status_title = QLabel("Managed prefixes")
        status_title.setObjectName("statusTitle")
        status_layout.addWidget(status_title)

        self.base_label = QLabel()
        self.base_label.setObjectName("descriptionLabel")
        self.base_label.setWordWrap(True)
        status_layout.addWidget(self.base_label)

        # Its own line rather than the status bar: which installer builds new
        # prefixes is standing information, and the status bar is transient.
        self.installer_label = QLabel()
        self.installer_label.setObjectName("descriptionLabel")
        self.installer_label.setWordWrap(True)
        status_layout.addWidget(self.installer_label)

        middle_layout.addWidget(status_card)

        # What is running in the selected prefix, live. Above the list rather
        # than in its Status column: the column is filled by a probe that
        # runs on refresh, and the banner is what says the column is out of
        # date -- when it changes state the list is probed again.
        self.activity_banner = ActivityBanner(self, None)
        self.activity_banner.changed.connect(self._activity_changed)
        middle_layout.addWidget(self.activity_banner)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(self.COLUMNS))
        self.tree.setHeaderLabels(self.COLUMNS)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(False)
        # Ctrl- and Shift-click choose several, for Delete. Everything else
        # acts on one prefix and is off while more than one is selected.
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.itemDoubleClicked.connect(lambda *_: self.show_commands())
        self.tree.header().setSectionResizeMode(
            len(self.COLUMNS) - 1, QHeaderView.ResizeMode.Stretch
        )
        middle_layout.addWidget(self.tree, 1)

        # The action line: what is happening, and beside it how far along.
        # Determinate where there is something to count, indeterminate where
        # there is not -- a copy can report bytes, a prefix scan cannot, and a
        # bar that sits still reads as a hung application.
        #
        # Built here, but added at the foot of the window rather than to this
        # page, because it belongs to both states: an install running on the
        # Setup page reports through the same line the list uses, and a status
        # bar that vanished on the way into Setup would be the one moment it
        # was most wanted.
        status_row = QWidget()
        status_row_layout = QHBoxLayout(status_row)
        status_row_layout.setContentsMargins(20, 8, 20, 14)
        status_row_layout.setSpacing(12)

        self.status = QLabel("")
        self.status.setObjectName("statusText")
        self.status.setWordWrap(True)
        status_row_layout.addWidget(self.status, 1)

        self.progress = QProgressBar()
        self.progress.setObjectName("busyBar")
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(200)
        self.progress.setMaximumHeight(8)
        self.progress.hide()
        status_row_layout.addWidget(self.progress, 0)

        content_layout.addWidget(middle, 3)
        main_layout.addWidget(content, 1)

        # The list is page 0 of a stack rather than the central widget itself.
        # With one page a QStackedWidget lays out exactly as the widget it
        # holds. What it buys is that Setup can become a page later instead of
        # a second window, which is the whole point of the manager being the
        # main window.
        self.stack = QStackedWidget()
        self.stack.addWidget(central)
        self.list_page = central

        # What is holding the lock, and the way out if it is never going to
        # let go. Hidden whenever nothing is running, which is nearly always.
        self.lock_row = QWidget()
        lock_layout = QHBoxLayout(self.lock_row)
        lock_layout.setContentsMargins(20, 10, 20, 0)
        lock_layout.setSpacing(12)
        self.lock_banner = QLabel("")
        self.lock_banner.setObjectName("cautionText")
        self.lock_banner.setWordWrap(True)
        lock_layout.addWidget(self.lock_banner, 1)
        # The way back to a Setup that is working: on the list, every button
        # that could reopen it is disabled while anything runs.
        self.lock_show_button = QPushButton("Show Configure")
        self.lock_show_button.setToolTip("Go back to the Configure page doing this.")
        self.lock_show_button.clicked.connect(self._show_lock_owner)
        lock_layout.addWidget(self.lock_show_button, 0)
        self.lock_release_button = QPushButton("Release")
        self.lock_release_button.setToolTip(
            "Stop waiting for this operation. It does not stop the work.")
        self.lock_release_button.clicked.connect(self._release_lock)
        lock_layout.addWidget(self.lock_release_button, 0)
        self.lock_row.hide()

        # Stack, then caution, then status: the two lower rows sit outside the
        # stack so they read the same in either state.
        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(self.stack, 1)
        shell_layout.addWidget(self.lock_row, 0)
        shell_layout.addWidget(status_row, 0)
        self.setCentralWidget(shell)

        self._selection_changed()
        self._check_installer()

    # ── states ───────────────────────────────────────────────────────────────

    def show_list(self):
        """Back to the prefix list."""
        self.stack.setCurrentWidget(self.list_page)
        self.refresh()
        self._sync_lock_ui(force=True)

    def show_setup(self, entry):
        """Open Setup for one prefix, as a state of this window.

        The installer used to be a child process. Hosting it is what makes the
        manager the main window rather than a launcher for a second one, and it
        is also what lets the two agree about which prefix is being worked on
        and whether anything is already running."""
        # Building one takes a second or two -- it constructs the whole
        # installer window -- and it happens on this thread, so say so.
        self.status.setText(f"Opening Configure for {entry['name']}…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            page = self._setup_page(entry)
        except (aol.NotAvailable, hosted.WrongTarget) as exc:
            QMessageBox.critical(self, "Cannot open Configure", str(exc))
            return
        except Exception as exc:                  # a constructor is a lot of code
            QMessageBox.critical(
                self, "Cannot open Configure",
                f"The installer could not be built for {entry['name']}.\n\n{exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.stack.setCurrentWidget(page)
        hosted.own_thread_exceptions(page)
        page.entered()
        self._sync_lock_ui(force=True)

    def _setup_page(self, entry):
        name = entry["name"]
        page = self._setup_pages.get(name)
        # Keyed by name, but validated against the path. Forget a prefix and
        # add a different directory under the same name -- or move one -- and
        # the cached page still drives the OLD directory, with the installer
        # already built and the WrongTarget check long past. The one guard
        # against installing into the wrong prefix is a constructor check, so a
        # page that skips the constructor skips the guard.
        if page is not None and page.path != Path(entry["path"]).expanduser():
            self.stack.removeWidget(page)
            page.dispose()
            page.deleteLater()
            del self._setup_pages[name]
            page = None
        if page is None:
            page = hosted.SetupPage(self, entry)
            self.stack.addWidget(page)
            self._setup_pages[name] = page
        self._drop_spare_setup_pages(keep=name)
        return page

    def _drop_spare_setup_pages(self, keep):
        """Hold on to the one being looked at and the one that is working.

        Each page owns a whole installer window and the threads it started, so
        they are not free to keep. They are also not safe to throw away while
        an operation is running in one -- the threads are daemon threads with
        no join -- which is why the lock holder is exempt."""
        held = self.lock.held
        busy = held.prefix if held is not None else None
        for name, page in list(self._setup_pages.items()):
            if name in (keep, busy):
                continue
            self.stack.removeWidget(page)
            page.dispose()
            page.deleteLater()
            del self._setup_pages[name]

    def current_state(self) -> str:
        return "list" if self.stack.currentWidget() is self.list_page else "setup"

    def current_prefix(self):
        """The prefix the visible page is about, or None on the list."""
        return getattr(self.stack.currentWidget(), "name", None)


    # ── busy indication ──────────────────────────────────────────────────────
    #
    # Every action that can take longer than an eyeblink says so. Qt gives an
    # indeterminate bar for free by setting both ends of the range to zero,
    # which animates rather than sitting still, so "working" and "wedged" do
    # not look the same.

    BUSY_BUTTONS = ("new_button", "find_button", "adopt_button", "launch_button",
                    "commands_button", "installer_button", "clone_button",
                    "default_button", "menu_button",
                    "snapshots_button", "copy_settings_button",
                    "backup_button", "backups_button",
                    "clean_button", "fonts_button", "protect_button", "forget_button",
                    "delete_button", "refresh_button")

    def _busy_start(self, message, maximum=0, *, prefix=None, operation=None,
                    alive=None, already_held=False):
        """Begin an operation, or refuse because another one is running.

        Two things happen before any work does. The lock is claimed, which can
        raise oplock.InUse -- callers name a prefix, so callers handle that;
        there is no sensible way to carry on regardless. And the registry
        records that the prefix is working, along with the offset its log had
        reached. If the manager dies from here on, that record is what makes
        the interruption visible at the next startup instead of leaving a
        prefix that merely looks finished.

        `alive` is the watchdog's oracle -- a QThread's isRunning for work that
        outlives this call, None for work that does not, which is read as
        still running for as long as the lock is held.

        `already_held` is for the hosted Setup page. Its claim is taken on the
        installer's own worker thread, where the answer is needed immediately
        and nothing may touch a widget; this then runs on the GUI thread to do
        the recording and the painting. Claiming twice would refuse the
        operation that had already been allowed."""
        if prefix and not already_held:
            self.lock.claim(prefix, operation or message, alive=alive)
        self._busy_prefix = prefix
        self._last_step = None
        if prefix:
            label = operation or message
            try:
                offset = prefixlog.begin(prefix, label)
                entry = self.reg.by_name(prefix)
                if entry is not None:
                    entry["log"] = str(prefixlog.path_for(prefix))
                self.reg.set_working(prefix, label, log_offset=offset)
            except (KeyError, OSError) as exc:
                # Never block the work on bookkeeping -- but say so. This used
                # to be a bare pass, and it swallowed the one case that
                # mattered: set_working raises KeyError for a prefix the
                # registry does not know, which was every clone, because the
                # destination was not registered until the copy finished.
                prefixlog.write(prefix, f"Could not record the operation: {exc}")
        self.status.setText(message)
        self.progress.setRange(0, maximum)      # 0,0 == indeterminate
        self.progress.setValue(0)
        self.progress.show()
        self._sync_lock_ui()
        QApplication.processEvents()

    def _busy_step(self, value, message=None):
        """Progress from work running ON the UI thread -- a move, a clean --
        which has to let the window repaint between steps.

        Never connect a signal to this; use _busy_progress. processEvents
        delivers whatever is queued, and from a worker thread that is the next
        progress report, which called this, which processed events again: a
        backup's rsync reports many times a second, the calls nested a
        thousand deep and the manager died of a RecursionError mid-backup.
        The guard is for a caller that gets that wrong anyway."""
        self._show_step(value, message)
        if getattr(self, "_in_step", False):
            return
        self._in_step = True
        try:
            QApplication.processEvents()
        finally:
            self._in_step = False

    def _busy_progress(self, value, message):
        """A slot for progress arriving from a worker thread.

        Already on the event loop, so nothing to process. Written only to
        the prefix log every ten percent -- rsync repeats each percentage
        dozens of times, and the log was getting every one. And it never
        raises: an exception leaving a slot aborts the whole process."""
        try:
            self._show_step(value, message, log=value % 10 == 0)
        except Exception as exc:
            with contextlib.suppress(Exception):
                self.status.setText(f"{message} (progress display failed: {exc})")

    def _show_step(self, value, message=None, log=True):
        if message and message != getattr(self, "_last_step", None):
            self._last_step = message
            self.status.setText(message)
            if log and getattr(self, "_busy_prefix", None):
                prefixlog.write(self._busy_prefix, message)
        if self.progress.maximum():
            self.progress.setValue(value)

    def _busy_done(self, message="", owner=None):
        """End an operation, and give up the lock it took.

        `owner` names the prefix whose lock this is entitled to release, and
        defaults to whatever _busy_prefix says. That default is the dangerous
        one: _busy_prefix is a single piece of window state, so a late
        end_operation arriving from prefix A after the watchdog already swept
        it and prefix B took the lock would release B's claim mid-clone.
        OperationLock.release has the owner check that stops it; it was never
        being given anything to check against."""
        prefix = getattr(self, "_busy_prefix", None)
        if owner is not None and prefix is not None and owner != prefix:
            # Somebody else's operation finished late. Release only what is
            # actually theirs, and leave the current operation alone.
            self.lock.release(owner)
            return
        if prefix:
            # Released first, so that everything downstream -- _sync_lock_ui,
            # and _selection_changed under it -- sees a free lock and re-enables
            # what it disabled.
            self.lock.release(owner or prefix)
            if message:
                prefixlog.write(prefix, message)
            try:
                self.reg.clear_state(prefix)
            except KeyError:
                pass                     # forgotten or renamed while working
            self._busy_prefix = None
        self.progress.hide()
        self.progress.setRange(0, 0)
        if message:
            self.status.setText(message)
        self._sync_lock_ui()

    # ── the lock, as the window shows it ─────────────────────────────────────

    def _sync_lock_ui(self, force=False):
        """Make the window agree with the lock.

        One place decides, and it decides from the lock rather than from who
        called it, so a claim made on a Setup page disables the list's buttons
        without the two having to know about each other.

        Nothing happens unless the rendered line would change, or the caller
        says the state did. The watchdog calls this twice a second's worth of
        ticks and _selection_changed is not free -- it re-reads the protection
        flag off the selected entry -- so an idle manager should do no work
        here at all. Changing page is the case `force` exists for: the lock has
        not moved, but what should be said about it has."""
        held = self.lock.held
        here = self.current_prefix()
        line = "" if held is None else "%s on %s (%s)" % (
            held.label, held.prefix, held.elapsed)
        stamp = (line, here)
        if stamp == getattr(self, "_lock_shown", None) and not force:
            return
        self._lock_shown = stamp

        for page in self._setup_pages.values():
            page.set_actions_enabled(held is None or held.prefix == page.name)

        if held is None:
            self.lock_row.hide()
            for name in self.BUSY_BUTTONS:
                b = getattr(self, name, None)
                if b is not None:
                    b.setEnabled(True)
            self._selection_changed()
            return

        for name in self.BUSY_BUTTONS:
            b = getattr(self, name, None)
            if b is not None:
                b.setEnabled(False)

        # On the page that owns the operation there is nothing to caution
        # about: that page's own status line already says what it is doing.
        caution = self.lock.caution_for(here) if here else (
            line + " — other prefixes are unavailable until it finishes.")
        if caution is None:
            self.lock_row.hide()
            return
        self.lock_banner.setText(caution)
        show = getattr(self, "lock_show_button", None)
        if show is not None:
            show.setVisible(held.prefix in self._setup_pages and here != held.prefix)
        self.lock_row.show()

    def _show_lock_owner(self):
        held = self.lock.held
        entry = self.reg.by_name(held.prefix) if held is not None else None
        if entry is not None:
            self.show_setup(entry)

    def _lock_tick(self):
        """The watchdog, and the clock behind the elapsed time."""
        try:
            self._maybe_offer_carry()
        except Exception as exc:          # a slot: nothing may escape it
            print(f"settings copy check failed: {exc}", file=sys.stderr)
        swept = self.lock.sweep()
        if swept is not None:
            # Nothing released it, and whatever vouched for it says it has
            # stopped. Say so rather than quietly opening the lock: work that
            # ended without reporting a result is exactly the case where the
            # prefix needs looking at.
            note = "%s stopped without reporting a result." % swept.label
            if swept.prefix in getattr(self, "_setup_pages", {}):
                # The hosted installer's flag dropping is how its work normally
                # ends -- it reports its own results in its log -- and it may be
                # asking its next question right now. Not a failure to report.
                note = "%s finished." % swept.label
            if getattr(self, "_busy_prefix", None) == swept.prefix:
                self._busy_done(note)
            else:
                prefixlog.write(swept.prefix, note)
                self.status.setText("%s — %s" % (swept.prefix, note))
            # A Setup page's work usually ends here rather than through the
            # page's own settle -- the installer's flag drops first -- so the
            # settings copy chosen at creation is offered from here as well.
            if swept.prefix in getattr(self, "_setup_pages", {}):
                settled = getattr(self, "setup_settled", None)
                if settled is not None:
                    settled(swept.prefix)
        self._sync_lock_ui()

    def _release_lock(self):
        """The user's way out of a lock nothing is going to release."""
        held = self.lock.held
        if held is None:
            return
        if QMessageBox.question(
            self, "Release this operation",
            f"{held.label} on {held.prefix} has been running for "
            f"{held.elapsed}.\n\n"
            "Releasing tells the manager to stop waiting for it. It does not "
            "stop the work. If that operation is in fact still running, this "
            "lets a second one start alongside it — which is the collision the "
            "lock exists to prevent.\n\n"
            f"Release {held.prefix} anyway?",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) != QMessageBox.StandardButton.Ok:
            return
        released = self.lock.release()
        if released is None:
            return                       # finished while the question was up
        prefixlog.write(released.prefix,
                        "%s released by hand after %s." % (released.label,
                                                           released.elapsed))
        if getattr(self, "_busy_prefix", None) == released.prefix:
            self._busy_done("%s released." % released.label)
        else:
            self.status.setText("%s on %s released." % (released.label,
                                                        released.prefix))
            self._sync_lock_ui()

    def _refuse(self, exc):
        """Decline a click, naming what is in the way."""
        QMessageBox.warning(
            self, "Something else is running",
            f"{exc}\n\n"
            "Only one prefix can be worked on at a time: installing into two "
            "at once collides in the package manager and in wineserver, "
            "whichever prefixes they are.\n\n"
            "Wait for it to finish, or release it from the bar at the foot of "
            "the window if you are certain it has stopped.")

    def _check_installer(self):
        """Which installer new prefixes will be built with, said out loud.

        Not a detail worth hiding: until the work is upstream, a checkout on the
        wrong branch has an installer that ignores the prefix it is handed and
        installs into ~/.AffinityLinux instead."""
        info = installer.describe()
        usable = bool(info.get("found") and info.get("supports_install_dir"))
        text = installer.summary(info)
        if not usable:
            text += f"  Settings can point at one, or fetch {installer.PREFERRED_BRANCH}."
        self.installer_label.setText(text)
        self.new_button.setEnabled(usable)

    # ── listing ──────────────────────────────────────────────────────────────

    def refresh(self):
        self._check_installer()
        self.base_label.setText(
            f"Base directory: {registry.base_dir()}   "
            f"(metadata in {registry.MANAGER_SUBDIR}/)"
        )
        self.reg.load()
        self.tree.clear()
        if not self.reg.entries:
            self.status.setText(
                "Nothing managed yet. 'New prefix' creates one under the base "
                "directory and installs into it; 'Adopt existing' takes over an "
                "install you already have, wherever it is, such as ~/.AffinityLinux."
            )
            self._selection_changed()
            return
        default = defaultentry.current()
        for entry in self.reg.entries:
            flags = ", ".join(f for f, on in (
                ("Default", entry["name"] == default),
                ("in menu", defaultentry.has_menu_entry(entry["name"])),
                ("locked", registry.is_protected(entry))) if on)
            item = QTreeWidgetItem(
                [
                    entry["name"],
                    flags,
                    "…",
                    "…",
                    "…",
                    "checking…",
                    entry["path"],
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, entry["name"])
            self.tree.addTopLevelItem(item)
        for i in range(len(self.COLUMNS) - 1):
            self.tree.resizeColumnToContents(i)

        self.refresh_button.setEnabled(False)
        self.probe_thread = ProbeThread(self.reg.entries)
        self.probe_thread.done.connect(self._probed)
        self.probe_thread.start()

    def _probed(self, rows):
        self.refresh_button.setEnabled(True)
        by_name = {entry["name"]: info for entry, info in rows}
        restored = [name for name, info in by_name.items() if info.get("renderer_restored")]
        for name in restored:
            prefixlog.write(name, "Wine's renderer setting was missing (OpenGL); set it to Vulkan again")
        if restored:
            self.status.setText(
                "Wine's renderer was set back to Vulkan in " + ", ".join(restored)
                + ": the setting was missing, so Affinity drew with OpenGL.")
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            info = by_name.get(item.data(0, Qt.ItemDataRole.UserRole))
            if not info:
                continue
            # One place decides what condition a prefix is in -- prefixstate --
            # so the badge, the tooltip, whether buttons are enabled and what
            # the recovery message says can never disagree with each other.
            # This used to be four hand-written strings that knew nothing about
            # an operation having been interrupted.
            item.setText(2, info["affinity_version"] or "—")
            item.setText(3, info["wine"] or "—")
            item.setText(4, probe.human_size(info["size"]) if info["exists"] else "—")
            item.setData(4, Qt.ItemDataRole.UserRole, info)
            self._show_condition(item, info)
        for i in range(len(self.COLUMNS) - 1):
            self.tree.resizeColumnToContents(i)
        self._selection_changed()

    def _show_condition(self, item, info):
        entry = self.reg.by_name(item.data(0, Qt.ItemDataRole.UserRole)) or {}
        condition = prefixstate.classify(info["path"], entry=entry, facts=info)
        item.setText(5, condition.label)
        item.setData(5, Qt.ItemDataRole.UserRole, condition.name)

        tip = condition.detail
        if condition.suggestion:
            tip = f"{tip}\n\n{condition.suggestion}"
        # A prefix that could not be read reports as though it were not
        # there, which is a different problem with a different fix. Say
        # which it was.
        if info.get("unreadable"):
            tip = (f"{tip}\n\nThis prefix could not be read: "
                   f"{info['unreadable']}")
        for column in range(len(self.COLUMNS)):
            item.setToolTip(column, tip)

    # ── selection ────────────────────────────────────────────────────────────

    def selected_entry(self):
        """The one selected prefix -- None when none, or when several are.

        None for several on purpose: every action but Delete is about one
        prefix, and each already does nothing without one. Quietly acting on
        whichever row Qt lists first would be launching, cloning or backing
        up a prefix the user did not single out."""
        entries = self.selected_entries()
        return entries[0] if len(entries) == 1 else None

    def selected_entries(self):
        out = []
        for item in self.tree.selectedItems():
            entry = self.reg.by_name(item.data(0, Qt.ItemDataRole.UserRole))
            if entry is not None:
                out.append(entry)
        return out

    def _selection_changed(self):
        # Nothing in this list is actionable while an operation holds the
        # lock. The check lives here as well as in _sync_lock_ui because
        # refresh() calls this, and a refresh during a clone would otherwise
        # hand the buttons back mid-operation.
        if self.lock.held is not None:
            for name in self.BUSY_BUTTONS:
                b = getattr(self, name, None)
                if b is not None:
                    b.setEnabled(False)
            return
        entry = self.selected_entry()
        self._follow_selection(entry)
        for b in (
            self.launch_button,
            self.installer_button,
            self.forget_button,
            self.commands_button,
            self.snapshots_button,
            self.copy_settings_button,
            self.backup_button,
            self.protect_button,
            self.rename_button,
            self.delete_button,
            # Clone and Clean act on the selection too, and refresh() rebuilds
            # the tree without restoring it -- so these were clickable with
            # nothing selected and did nothing at all when clicked.
            self.clone_button,
            self.clean_button,
            self.fonts_button,
            self.default_button,
            self.menu_button,
        ):
            b.setEnabled(entry is not None)
        several = len(self.selected_entries())
        self.delete_button.setText(f"Delete {several}…" if several > 1 else "Delete")
        if several > 1:
            self.delete_button.setEnabled(True)
            self.status.setText(f"{several} prefixes selected — only Delete acts "
                                "on more than one.")
        if entry is None:
            self.protect_button.setText("Protect")
            return
        locked = registry.is_protected(entry)
        self.protect_button.setText("Unprotect" if locked else "Protect")
        self.menu_button.setText("Remove from menu"
                                 if defaultentry.has_menu_entry(entry["name"]) else "Add to menu")
        # Left enabled while locked so the refusal can explain itself, rather
        # than a greyed button leaving the user guessing why.
        self.delete_button.setEnabled(True)

    def _follow_selection(self, entry):
        path = Path(entry["path"]).expanduser() if entry else None
        if path is not None and not path.exists():
            path = None
        if path != self.activity_banner.prefix:
            self.activity_banner.set_prefix(path, name=entry["name"] if entry else None)

    def _activity_changed(self, state):
        """Bring the selected row's Status into line with the banner.

        Not a refresh: that rebuilds the list and loses the selection, and
        re-measures every prefix. The row keeps the facts its last probe
        found; only whether Affinity is running is replaced, and prefixstate
        classifies again from those -- the same one place as always."""
        try:
            items = self.tree.selectedItems()
            if len(items) != 1 or self.activity_banner.prefix is None:
                return              # the banner follows one prefix, or none
            item = items[0]
            info = item.data(4, Qt.ItemDataRole.UserRole)
            if not info:
                return
            pids = self.activity_banner.activity.running_pids
            facts = dict(info, running=bool(pids), pids=pids)
            item.setData(4, Qt.ItemDataRole.UserRole, facts)
            self._show_condition(item, facts)
        except Exception as exc:                # a slot must never raise
            self.status.setText(f"Could not update the status: {exc}")

    # ── actions ──────────────────────────────────────────────────────────────

    def new_prefix(self):
        dialog = NewPrefixDialog(self, self.reg)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.result_entry:
            return
        entry = dialog.result_entry
        carry = dialog.carry_from()
        if carry is not None:
            self.reg.set_carry(entry["name"], carry)
            prefixlog.write(entry["name"], f"Settings copy chosen at creation: from {carry}")
        self.refresh()
        # Settings are NOT copied here any more. This used to offer the copy
        # before Setup, into a prefix Wine had never run in -- fine for the
        # settings, and fatal for drive letters: Wine creates C: and Z: only
        # when it creates dosdevices itself, so a W: put there first leaves a
        # prefix with no C: drive. The copy is its own action now, after Setup
        # and before Affinity is first launched.
        self.show_setup(entry)
        if carry is not None:
            self.status.setText(
                f"The settings from {Path(carry).name} will be offered when "
                "Configure has finished.")
        else:
            self.status.setText(
                f"When Configure has finished, select {entry['name']} and use "
                "'Copy settings…' before launching Affinity in it.")

    def setup_settled(self, name):
        self._default_if_none(name)

    def _default_if_none(self, name):
        """With no Affinity menu entry at all, a prefix that has finished Setup
        becomes the Default without asking -- there is nothing to take it from.
        An entry somebody else wrote is left for Make Default, which asks."""
        entry = self.reg.by_name(name)
        if entry is None or defaultentry.main_entry().exists():
            return
        try:
            plan = defaultentry.plan(name, entry["path"])
        except FileNotFoundError:
            return                       # Affinity not installed yet
        self._apply_default(plan, quiet=True)

    def _maybe_offer_carry(self):
        """Offer a settings copy chosen when a prefix was created, as soon as
        the prefix is in the state the copy needs: nothing running in the
        manager, Wine has made the prefix, Affinity is installed and not
        running. Checked on the lock timer, so it does not depend on how
        Configure ended (its own settle, the watchdog, a restart of the
        manager); every reason for waiting goes to the prefix's log once."""
        if self.lock.held is not None or getattr(self, "_carry_open", False):
            return
        for entry in self.reg.entries:
            source = entry.get("carry_from")
            if not source:
                continue
            path = Path(entry["path"]).expanduser()
            if not prefsseed.is_initialised(path):
                reason = "waiting for Wine to set the prefix up"
            elif not (path / probe.AFFINITY_SUBDIR / "Affinity.exe").is_file():
                reason = "waiting for Affinity to be installed"
            elif probe.running_pids(path):
                reason = "waiting for Affinity to be closed there"
            else:
                reason = None
            if reason:
                noted = getattr(self, "_carry_noted", {})
                if noted.get(entry["name"]) != reason:
                    noted[entry["name"]] = reason
                    self._carry_noted = noted
                    prefixlog.write(entry["name"], f"Settings copy from {source}: {reason}")
                continue
            self._carry_open = True
            try:
                prefixlog.write(entry["name"], f"Settings copy from {source}: offering it")
                copied = self.offer_settings_copy(entry, preselect=Path(source))
                prefixlog.write(entry["name"], "Settings copy: " + ("done" if copied else "not done (declined or failed); 'Copy settings…' is still there"))
                self.reg.set_carry(entry["name"], None)
            finally:
                self._carry_open = False
            return

    def adopt(self):
        chosen = QFileDialog.getExistingDirectory(
            self, "Existing Affinity prefix", str(Path.home())
        )
        if not chosen:
            return
        if not probe.is_prefix(chosen):
            reply = QMessageBox.question(
                self,
                "Not a Wine prefix",
                f"{chosen} has no drive_c/dosdevices, so it does not look like a "
                "Wine prefix.\n\nManage it anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        suggested = Path(chosen).name.lstrip(".") or "Affinity"
        name, ok = _ask_name(self, suggested)
        if not ok:
            return
        try:
            self.reg.add(name, chosen)
        except (registry.InvalidName, registry.DuplicateName, registry.PathInUse) as e:
            QMessageBox.warning(self, "Cannot adopt this prefix", str(e))
            return
        self.refresh()

    def launch_selected(self):
        entry = self.selected_entry()
        if not entry:
            return
        pids = probe.running_pids(entry["path"])
        if pids:
            # Launching a second instance is not a nuisance here: the running
            # one dies, taking unsaved work with it.
            QMessageBox.information(
                self,
                "Already running",
                f"{entry['name']} is already running (pid {pids[0]}).\n\n"
                "Starting a second instance in the same prefix kills the first, "
                "so this was not done.",
            )
            return
        try:
            installer.launch_affinity(entry["path"])
        except FileNotFoundError as e:
            QMessageBox.warning(self, "Cannot launch", str(e))
            return
        self.status.setText(f"Started Affinity in {entry['name']}.")

    def open_installer(self):
        entry = self.selected_entry()
        if not entry:
            return
        self.show_setup(entry)

    def backup_selected(self):
        entry = self.selected_entry()
        if not entry:
            return
        dialog = BackupDialog(self, entry)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.plan is None:
            return
        plan = dialog.plan
        self._run_task(
            entry["name"], "Back up",
            f"Backing up {entry['name']} to {plan.dest.parent}",
            lambda progress: backups.create(plan, progress=progress),
            self._backup_finished)

    def _backup_finished(self, result, error):
        if error:
            QMessageBox.critical(
                self, "Backup failed",
                f"{error}\n\nWhat was copied so far is listed under Backups as "
                "unfinished, and can be deleted from there.")
            return
        problems = backups.verify(result)
        body = (f"{result}\n{result.path}\n\n{result.files} files, "
                f"{probe.human_size(result.bytes)}")
        if result.host_files:
            body += f", and {len(result.host_files)} desktop file(s)"
        if problems:
            QMessageBox.warning(self, "Backed up, but it does not verify",
                                body + ".\n\n" + "\n".join(problems[:8]))
        else:
            QMessageBox.information(self, "Backed up", body + ". Verified.")

    def show_backups(self):
        entry = self.selected_entry()
        BackupsDialog(self, self, entry["name"] if entry else None).exec()

    def run_restore(self, plan):
        name = plan.backup.prefix_name
        self._run_task(
            name, "Restore",
            f"Restoring {plan.backup}",
            lambda progress: backups.restore(plan, progress=progress),
            lambda result, error: self._restore_finished(plan, result, error))

    def _restore_finished(self, plan, notes, error):
        if error:
            QMessageBox.critical(
                self, "Restore failed",
                f"{error}\n\nThe prefix that was there has not been moved.")
            self.refresh()
            return
        # The prefix that was replaced goes into the list, so it can be
        # launched if the restore turns out to be the wrong one, or removed
        # with everything else it left on the host.
        extra = []
        if plan.moved_aside_to and plan.moved_aside_to.exists():
            aside_name = backups.aside_name(plan.backup.prefix_name)
            try:
                self.reg.add(aside_name, plan.moved_aside_to)
                extra.append(f"The prefix that was there is listed as "
                             f"'{aside_name}'.")
            except (registry.InvalidName, registry.DuplicateName,
                    registry.PathInUse) as exc:
                extra.append(f"The prefix that was there is at "
                             f"{plan.moved_aside_to} ({exc}).")
        if plan.restore_prefix and self.reg.by_path(plan.target) is None:
            for candidate in (plan.backup.prefix_name,
                              plan.backup.prefix_name + " restored"):
                try:
                    self.reg.add(candidate, plan.target)
                    break
                except (registry.InvalidName, registry.DuplicateName,
                        registry.PathInUse):
                    continue
        self.refresh()
        QMessageBox.information(self, "Restored",
                                "\n".join((notes or [])[:16] + extra))

    def _run_task(self, prefix, operation, message, fn, on_done):
        """A long job for one prefix: under the lock, off the UI thread, with
        the progress bar, and its result handed to on_done(result, error)."""
        thread = TaskThread(fn)
        try:
            self._busy_start(message, 100, prefix=prefix, operation=operation,
                             alive=thread.isRunning)
        except oplock.InUse as exc:
            self._refuse(exc)
            return
        self._task_thread = thread           # a live reference, or Qt deletes it
        thread.progress.connect(lambda pct: self._busy_progress(pct, f"{message} — {pct}%"))

        def finished(result, error):
            # A slot: anything escaping it aborts the process, and this one
            # runs at the end of an eleven-gigabyte copy.
            try:
                self._busy_done(f"{operation} {'failed' if error else 'finished'}",
                                owner=prefix)
                on_done(result, error)
            except Exception as exc:
                prefixlog.write(prefix, f"{operation}: reporting failed: {exc}")
                QMessageBox.warning(self, operation,
                                    f"{operation} ended, but reporting it failed: {exc}")

        thread.done.connect(finished)
        thread.start()

    def show_snapshots(self):
        entry = self.selected_entry()
        if not entry:
            return
        SnapshotsDialog(self, entry).exec()

    def show_commands(self):
        """One dialog at a time, and not while the prefix is being worked on.

        It is modeless on purpose -- copying a command while looking at the
        list is the point -- which also meant a fresh one per double-click,
        each of them live, and every one of them able to run winecfg or
        wineserver -k against a prefix in the middle of a clone or an install.
        The lock covers the manager's own buttons and knew nothing about
        these."""
        entry = self.selected_entry()
        if not entry:
            return
        held = self.lock.held
        if held is not None:
            QMessageBox.information(
                self, "Something is running",
                f"{held.label} is running on {held.prefix} ({held.elapsed}).\n\n"
                "The commands here start Wine processes and end Wine sessions, "
                "which is not safe against a prefix being worked on. Wait for "
                "it to finish.")
            return
        existing = getattr(self, "_commands_dialog", None)
        if existing is not None:
            existing.close()
            existing.deleteLater()
        self._commands_dialog = CommandsDialog(self, entry)
        self._commands_dialog.show()

    def find_installations(self):
        dialog = FindDialog(self, self.reg)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def make_default_selected(self):
        entry = self.selected_entry()
        if not entry:
            return
        try:
            plan = defaultentry.plan(entry["name"], entry["path"])
        except FileNotFoundError as exc:
            QMessageBox.information(self, "Not installed yet", f"{exc}\n\nRun Configure there first.")
            return
        reply = QMessageBox.question(
            self, f"Make {entry['name']} the Default?", plan.summary,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._apply_default(plan)

    def _apply_default(self, plan, quiet=False):
        try:
            notes = defaultentry.apply(plan)
        except OSError as exc:
            QMessageBox.critical(self, "Could not change the Default", str(exc))
            return
        self.refresh()
        self.status.setText(f"{plan.to_name} is the Default.")
        if notes and not quiet:
            QMessageBox.information(self, "Default changed", "\n\n".join(notes))

    def toggle_menu_selected(self):
        entry = self.selected_entry()
        if not entry:
            return
        name = entry["name"]
        try:
            if defaultentry.has_menu_entry(name):
                defaultentry.remove_menu_entry(name)
                self.status.setText(f"Removed '{defaultentry.menu_name(name)}' from the menu.")
            else:
                defaultentry.add_menu_entry(name, entry["path"])
                self.status.setText(f"Added '{defaultentry.menu_name(name)}' to the menu.")
        except (OSError, PermissionError) as exc:
            QMessageBox.warning(self, "Menu entry", str(exc))
            return
        self.refresh()

    def rename_selected(self):
        entry = self.selected_entry()
        if not entry:
            return
        old = entry["name"]
        held = self.lock.held
        if held is not None:
            # The running operation, its Setup page and its log are all keyed by
            # name and path; changing either under it would split one job in two.
            QMessageBox.information(
                self, "Not now",
                f"{held.operation} is running in {held.prefix}. Rename or move "
                f"{old} when it has finished.")
            return
        dialog = RenameMoveDialog(self, self.reg, entry)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new, dest = dialog.result()
        if dest is not None and probe.running_pids(entry["path"]):
            QMessageBox.warning(self, "Affinity is running",
                                f"Close Affinity in {old} first: its folder cannot "
                                "be moved while it runs.")
            return
        notes = []
        try:
            if new != old:
                notes += renaming.rename(self.reg, old, new)
            if dest is not None:
                notes += renaming.move(self.reg, new, dest)
        except (registry.InvalidName, registry.DuplicateName) as exc:
            QMessageBox.warning(self, "Cannot use that name", str(exc))
            return
        except (renaming.CannotMove, OSError) as exc:
            QMessageBox.warning(
                self, "Not moved",
                (f"{old} is now {new}, but its folder was not moved:\n\n{exc}"
                 if new != old else f"The folder was not moved:\n\n{exc}"))
        page = self._setup_pages.pop(old, None)
        if page is not None:
            # Built for the old name and path; the next Configure builds afresh.
            if self.stack.currentWidget() is page:
                self.stack.setCurrentWidget(self.list_page)
            self.stack.removeWidget(page)
            page.dispose()
            page.deleteLater()
        moved = self.reg.by_name(new)["path"] if self.reg.by_name(new) else entry["path"]
        what = ([f"renamed from {old}"] if new != old else []) + \
               ([f"moved to {moved}"] if moved != entry["path"] else [])
        if what:
            prefixlog.write(new, "Prefix " + " and ".join(what))
            self.status.setText(f"{new}: " + " and ".join(what) + ".")
        self.refresh()
        if notes:
            QMessageBox.information(self, "Rename / Move", "\n".join(notes))

    def toggle_protection(self):
        entry = self.selected_entry()
        if not entry:
            return
        locked = registry.is_protected(entry)
        if locked:
            # Unprotecting gets its own confirmation. The whole value of the
            # mark is that removing it has to be deliberate; a silent toggle
            # next to a Delete button would be worth nothing.
            reply = QMessageBox.warning(
                self,
                "Remove protection",
                f"{entry['name']} is protected from deletion.\n\n"
                "Removing the protection makes it deletable. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.reg.set_protected(entry["name"], not locked)
        self.refresh()
        self.status.setText(
            f"{entry['name']} is now {'deletable' if locked else 'protected from deletion'}."
        )

    def clone_selected(self):
        """Copy the selected prefix into a new managed one.

        The copy is registered like any other prefix, so it appears in the list
        and can be launched, cleaned or deleted from here."""
        entry = self.selected_entry()
        if not entry:
            return
        name, path = entry["name"], Path(entry["path"])

        pids = probe.running_pids(path)
        if pids:
            QMessageBox.warning(
                self, "Still running",
                f"Affinity is running in {name} (pid {pids[0]}).\n\n"
                "Close it first -- a prefix copied while it is running is "
                "copied mid-write, and the registry in the copy may not match "
                "the files beside it.",
            )
            return

        suggested = self.reg.suggest_name()
        new_name, ok = _ask_name(
            self, suggested,
            title=f"Clone {name}",
            label=f"Copy {path} to a new prefix under {registry.base_dir()}.\n\nName for the copy:",
        )
        if not ok or not new_name:
            return

        try:
            new_name = registry.validate_name(new_name)
        except registry.InvalidName as exc:
            QMessageBox.warning(self, "Not a usable name", str(exc))
            return
        if self.reg.by_name(new_name):
            QMessageBox.warning(self, "Already managed",
                                f"A prefix named {new_name!r} is already in the list.")
            return

        dest = self.reg.suggest_path(new_name)
        builds = maintenance.describe_builds(path)
        keep = None
        if builds:
            chooser = BuildChoiceDialog(self, name, builds)
            if chooser.exec() != QDialog.DialogCode.Accepted:
                return
            keep = chooser.chosen()

        try:
            plan = maintenance.plan_clone(path, dest, keep_builds=keep)
        except (maintenance.NotAPrefix, maintenance.DestinationInUse) as exc:
            QMessageBox.warning(self, "Cannot clone", str(exc))
            return

        dropped = (f"<br>Leaving out: {', '.join(plan.drop_builds)}"
                   if plan.drop_builds else "")
        if KindConfirmDialog(
            self, "Clone this prefix", "clone",
            f"Copy <b>{path}</b><br>to <b>{dest}</b><br><br>"
            f"About {probe.human_size(plan.est_size)}.{dropped}<br><br>"
            "This reads the original and writes only to the copy. The copy "
            "joins the list as a prefix of its own. If what you want is "
            "something to fall back to after an upgrade, use <b>Back up</b> "
            "instead.", "Clone",
        ).exec() != QDialog.DialogCode.Accepted:
            return

        # Built before the claim so the watchdog has something to ask about,
        # and claimed before start() so no work begins that the lock would have
        # refused. isRunning is bound to this thread object, not to the
        # attribute, so a later clone replacing it cannot make this operation
        # look alive.
        #
        # The lock refuses a second clone, but only once _busy_start is
        # reached -- and these three attributes are overwritten above it. A
        # second clone therefore dropped the first CloneThread's only Python
        # reference before finding out it was not allowed to run, and Qt
        # deleted a running QThread.
        running = getattr(self, "_clone_thread", None)
        if running is not None and running.isRunning():
            QMessageBox.information(
                self, "Already copying",
                f"{getattr(self, '_clone_name', 'A prefix')} is still being "
                "copied. Wait for that to finish before starting another.")
            return
        # Registered BEFORE the copy starts, not after it finishes. A clone
        # that was interrupted -- and this is the operation most likely to be,
        # since it is the long one -- left a partial multi-gigabyte tree at the
        # destination that nothing knew about: set_working raised KeyError for
        # a name the registry had never heard of, so there was no "working" row
        # for the next startup to recover, and no row to tell the user that the
        # directory sitting there is not a prefix.
        try:
            self.reg.add(new_name, dest)
        except (registry.InvalidName, registry.DuplicateName,
                registry.PathInUse) as exc:
            QMessageBox.warning(self, "Cannot clone", str(exc))
            return

        self._clone_name = new_name
        self._clone_dest = dest
        self._clone_thread = CloneThread(plan)
        try:
            self._busy_start(
                f"Copying {name} to {new_name} — {probe.human_size(plan.est_size)}",
                100, prefix=new_name, operation=f"Clone from {name}",
                alive=self._clone_thread.isRunning)
        except oplock.InUse as exc:
            self.reg.forget(new_name)    # nothing was copied; leave no row
            self._refuse(exc)
            return
        self._clone_thread.progress.connect(
            lambda pct: self._busy_progress(pct, f"Copying {name} to {new_name} — {pct}%"))
        self._clone_thread.done.connect(self._clone_finished)
        self._clone_thread.start()

    def _clone_finished(self, problems, error):
        if error:
            # The row stays, and stays marked, so the partial copy at the
            # destination is visible in the list as something to deal with
            # rather than an unexplained directory.
            self._busy_done("Clone failed", owner=self._clone_name)
            try:
                self.reg.set_working(self._clone_name, "Clone (failed)")
            except KeyError:
                pass
            self.refresh()
            QMessageBox.critical(
                self, "Clone failed",
                f"{error}\n\nWhatever was copied is still at "
                f"{self._clone_dest}. {self._clone_name} is in the list, marked "
                "unfinished, so you can look at it or remove it.")
            return

        repointed = [p for p in problems if "->" in p]
        failures = [p for p in problems if "->" not in p]
        # Already in the list -- it was added before the copy began, so an
        # interruption leaves something to recover. Nothing to add here, and
        # therefore nothing that can raise in a slot.
        self._busy_done(f"Cloned to {self._clone_name}", owner=self._clone_name)
        self.refresh()

        detail = ""
        if repointed:
            detail += "\n\nSymlinks repointed into the copy:\n  " + "\n  ".join(repointed[:6])
        if failures:
            detail += "\n\nProblems:\n  " + "\n  ".join(failures[:6])
        QMessageBox.information(
            self, "Cloned",
            f"{self._clone_name} is now managed.{detail}")

    def clean_selected(self):
        """Offer what can be reclaimed from the selected prefix."""
        entry = self.selected_entry()
        if not entry:
            return
        name, path = entry["name"], Path(entry["path"])

        try:
            items = maintenance.cleanable(path)
        except maintenance.NotAPrefix as exc:
            QMessageBox.warning(self, "Not a prefix", str(exc))
            return

        if not items:
            QMessageBox.information(
                self, "Nothing to clean",
                f"{name} has no spare Wine builds, archives or saved-aside copies.")
            return

        dialog = CleanDialog(self, name, items)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        chosen = dialog.selected()
        if not chosen:
            return

        size = probe.human_size(sum(i.size for i in chosen))
        if QMessageBox.question(
            self, "Remove these?",
            f"Permanently remove {len(chosen)} item(s) from {name}, freeing about {size}.\n\n"
            "There is no undo.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) != QMessageBox.StandardButton.Ok:
            return

        try:
            self._busy_start(f"Cleaning {name}", len(chosen),
                             prefix=name, operation="Clean")
        except oplock.InUse as exc:
            self._refuse(exc)
            return
        freed, problems = 0, []
        try:
            for n, item in enumerate(chosen, 1):
                self._busy_step(n, f"Cleaning {name} — {item.path.name}")
                got, trouble = maintenance.clean(path, [item])
                freed += got
                problems += trouble
        except maintenance.Busy as exc:
            self._busy_done("Nothing was removed")
            QMessageBox.warning(self, "Still running", str(exc))
            return

        self._busy_done(f"Freed {probe.human_size(freed)} from {name}")
        self.refresh()
        if problems:
            QMessageBox.warning(
                self, "Some items were kept",
                "Freed " + probe.human_size(freed) + ".\n\n" + "\n".join(problems[:8]))

    def delete_selected(self):
        entries = self.selected_entries()
        if not entries:
            return

        protected = [e["name"] for e in entries if registry.is_protected(e)]
        if protected:
            QMessageBox.information(
                self,
                "Protected",
                f"{', '.join(protected)} "
                f"{'is' if len(protected) == 1 else 'are'} protected from "
                "deletion.\n\nUse Unprotect first if you really mean to delete "
                + ("it." if len(protected) == 1 else "them.")
                + ("" if len(protected) == len(entries) else
                   "\n\nNothing was deleted. Select the others without "
                   f"{'it' if len(protected) == 1 else 'them'} to go on."),
            )
            return

        # Itemised, because the things most easily forgotten here are the ones
        # that bite later: a menu entry that launches nothing, and a document
        # association that silently stops working because the prefix holding it
        # has gone. The list is the confirmation. A running prefix is shown in
        # it, live, rather than refused here -- it may be closed while the
        # list is read.
        plans = []
        for e in entries:
            try:
                plans.append(removal.plan(self.reg, e["name"]))
            except KeyError:
                pass
        if not plans:
            self.refresh()
            return
        dialog = RemovalDialog(self, plans)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        chosen = dialog.chosen_by_plan()
        if not chosen:
            return

        # Through the lock like the others, one prefix at a time. Removing
        # several gigabytes takes long enough to overlap a clone, and a clone
        # reading the tree this is deleting from is the worst of the
        # collisions -- it would produce a copy that is quietly half a prefix.
        report = []
        for plan, items in chosen:
            name = plan.name
            try:
                self._busy_start(f"Removing {name}", prefix=name, operation="Remove")
            except oplock.InUse as exc:
                report.append(f"{name}: not removed -- {exc}")
                continue
            try:
                notes = removal.apply(self.reg, plan, items)
            finally:
                # Released before the refresh: the registry row may be gone,
                # and _busy_done clears the working state off an entry that
                # has to exist.
                self._busy_done(f"Removed {len(items)} item(s) belonging to {name}")
            report.append(f"{name}:")
            report += [f"  {n}" for n in notes[:14]]
        self.refresh()
        title = (f"{chosen[0][0].name} removed" if len(chosen) == 1
                 else f"{len(chosen)} prefixes removed")
        QMessageBox.information(self, title, "\n".join(report[:60]))

    def check_fonts_selected(self):
        """Repair the selected prefix's font registrations (installer code).

        Fresh prefixes have come out with the core fonts on disk but not
        registered in the 64-bit Fonts keys, and with Microsoft Yahei
        registered from another Wine's folder -- Affinity's bold text then
        falls back to Arial Narrow and Yahei. The installer now checks this at
        the end of an install; this is the same check for a prefix that
        already exists. Through the prefix's own Wine, and only while nothing
        runs in it: Wine reads fonts at startup, and a second Wine against a
        live prefix can disagree with the one already serving it."""
        entry = self.selected_entry()
        if not entry:
            return
        name, path = entry["name"], Path(entry["path"]).expanduser()
        activity = liveness.scan(path)
        if activity.state != liveness.QUIET:
            QMessageBox.information(
                self, "Close it first",
                f"{activity.summary()}\n\nFonts are read when Wine starts, so "
                f"close Affinity in {name} (and end any leftovers) and check again.")
            return
        wine = path / "ElementalWarriorWine" / "bin" / "wine"
        if not wine.exists():
            builds = [b for b in probe.wine_builds(path) if b != "ElementalWarriorWine"]
            wine = path / builds[-1] / "bin" / "wine" if builds else wine
        if not wine.exists():
            QMessageBox.warning(self, "No Wine found",
                                f"{name} has no Wine build to check its fonts with.")
            return
        try:
            repair = aol.module().repair_font_registrations
        except (aol.NotAvailable, AttributeError) as exc:
            QMessageBox.warning(
                self, "Installer too old",
                f"The font check lives in the installer, and the one found "
                f"does not have it: {exc}")
            return
        def work(progress):
            # The repair never raises -- an install must not fail over fonts
            # -- so its warnings are the only sign it did not run. Without
            # them a failed check would report "fonts are fine".
            problems = []
            notes = repair(path, wine, lambda message, level="info":
                           problems.append(message) if level != "info" else None)
            if problems and not notes:
                raise RuntimeError("; ".join(problems))
            return notes

        self._run_task(
            name, "Check fonts", f"Checking fonts in {name}", work,
            lambda notes, error: self._fonts_checked(name, notes, error))

    def _fonts_checked(self, name, notes, error):
        if error:
            QMessageBox.warning(self, "Check fonts", f"The check failed: {error}")
            return
        prefixlog.write(name, "Check fonts: " + ("; ".join(notes) if notes
                                                 else "nothing to repair"))
        if not notes:
            QMessageBox.information(
                self, "Fonts are fine",
                f"Every font in {name} is registered, and none is borrowed from "
                "another Wine. Nothing was changed.")
            return
        QMessageBox.information(
            self, "Fonts repaired",
            f"{len(notes)} change(s) in {name}:\n\n" + "\n".join(notes[:30])
            + ("\n…" if len(notes) > 30 else "")
            + "\n\nStart Affinity again to see them.")

    def forget_selected(self):
        entry = self.selected_entry()
        if not entry:
            return
        reply = QMessageBox.question(
            self,
            "Stop managing",
            f"Remove {entry['name']} from the list?\n\n"
            f"{entry['path']} is left exactly as it is — nothing is deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.reg.forget(entry["name"])
        self.refresh()


class RenameMoveDialog(SizedDialog):
    """A new name for a prefix, and whether its folder follows.

    Two separate things, said separately, because they differ in what they
    touch. The name is the manager's own: the list, the menu entries it wrote,
    the log and snapshots. The folder is the path every launcher, Wine file
    association and backup names -- moving it rewrites those (each kept beside
    itself as .before-move-*), and needs Affinity closed."""

    FIT_MIN_WIDTH = 560

    def __init__(self, parent, reg, entry):
        super().__init__(parent)
        self.setWindowTitle("Rename / Move prefix")
        self.setModal(True)
        ui.apply(self)
        self.reg = reg
        self.entry = entry
        self.path = Path(entry["path"]).expanduser()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Name</b>"))
        self.field = QLineEdit(entry["name"])
        layout.addWidget(self.field)
        note = QLabel(
            "The name is what this list, the menu entries and the log use. "
            "Renaming changes those, the prefix's snapshots, and the Default's "
            "entries if this is the Default. Nothing in the prefix changes.")
        note.setWordWrap(True)
        note.setObjectName("descriptionLabel")
        layout.addWidget(note)
        layout.addSpacing(8)
        self.move_box = QCheckBox("Also move the folder to match the name")
        layout.addWidget(self.move_box)
        self.move_note = QLabel("")
        self.move_note.setWordWrap(True)
        self.move_note.setObjectName("descriptionLabel")
        layout.addWidget(self.move_note)
        self.problem = QLabel("")
        self.problem.setWordWrap(True)
        layout.addWidget(self.problem)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.field.textChanged.connect(self._update)
        self.move_box.toggled.connect(self._update)
        self._update()

    def destination(self) -> Path:
        return self.path.parent / registry.dir_name(self.field.text().strip() or "x")

    def _update(self):
        name = self.field.text().strip()
        dest = self.destination()
        problem = ""
        try:
            registry.validate_name(name)
        except registry.InvalidName as exc:
            problem = str(exc)
        else:
            clash = self.reg.by_name(name)
            if clash is not None and clash is not self.entry:
                problem = f"A prefix named {name!r} is already managed."
        same_place = dest == self.path
        self.move_box.setEnabled(not same_place)
        if same_place:
            self.move_note.setText(f"The folder already matches: {self.path}")
        else:
            self.move_note.setText(
                f"{self.path}\n→ {dest}\n\nA rename on the same disk: instant, "
                "nothing is copied. Launchers and menu entries that name the old "
                "folder are rewritten, each kept beside itself as .before-move-*. "
                "Affinity must be closed in it.")
            if self.move_box.isChecked() and dest.exists():
                problem = problem or f"{dest} already exists."
        self.problem.setText(f"<span style='color:#E5484D'>{html.escape(problem)}</span>"
                             if problem else "")
        unchanged = name == self.entry["name"] and not (self.move_box.isChecked() and not same_place)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            not problem and not unchanged)

    def result(self):
        """(new name, destination folder or None)."""
        move = self.move_box.isChecked() and self.move_box.isEnabled()
        return self.field.text().strip(), (self.destination() if move else None)


def _ask_name(parent, suggested, *, title="Name this prefix", label="Name"):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setModal(True)
    dialog.setMinimumWidth(460)
    ui.apply(dialog)
    field = QLineEdit(suggested)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout = QVBoxLayout(dialog)
    prompt = QLabel(label)
    prompt.setWordWrap(True)
    layout.addWidget(prompt)
    layout.addWidget(field)
    layout.addWidget(buttons)
    fit_to_contents(dialog, min_width=460)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return field.text().strip(), accepted


def _log_unhandled(kind, value, tb):
    """PyQt aborts the process when an exception escapes a slot and
    sys.excepthook is the default one, so one bug in a timer callback took the
    whole manager down, mid-install. Log it instead and keep going."""
    import traceback
    text = "".join(traceback.format_exception(kind, value, tb))
    print(text, file=sys.stderr)
    try:
        log = registry.manager_dir() / "logs" / "manager-errors.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {__version__}\n{text}\n")
    except OSError:
        pass


def main():
    sys.excepthook = _log_unhandled
    app = QApplication(sys.argv)
    # The stylesheet only -- ui.apply() also sets WA_StyledBackground, which is
    # a widget attribute and not one a QApplication accepts. This is here so the
    # conflict dialogs below, which appear before any window exists, are not
    # system-default grey while the rest of the application is themed.
    app.setStyleSheet(ui.stylesheet())

    # Before the window, because the answer can be "do not open one". Two
    # managers means two writers to the prefix list and two of them driving the
    # same package manager; the standalone installer means something outside
    # this window is provisioning a prefix we think we own.
    conflict = singleinstance.check(__version__)
    if not conflict.may_start:
        QMessageBox.critical(None, "Already running", conflict.detail)
        return 1
    if conflict.action == singleinstance.WARN:
        answer = QMessageBox.warning(
            None, "Something else is running",
            conflict.detail + "\n\nStart anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return 1

    singleinstance.acquire(__version__)
    # aboutToQuit rather than a finally: Qt can leave sys.exit(app.exec())
    # by a path that does not unwind this frame.
    app.aboutToQuit.connect(singleinstance.release)

    window = ManagerWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
