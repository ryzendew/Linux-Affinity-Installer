"""Hosting the installer inside the manager window.

The real AffinityInstallerGUI is 19,000 lines and downloads things when it
starts, so what is tested here is the hosting -- the overrides, the guard on
which prefix got targeted, and the lock -- against a stand-in with the same
shape. The one-process run against a real installer is done by hand; this is
what stops it regressing silently afterwards.

The guard worth the most is test_a_window_that_settled_elsewhere_is_refused.
Driving the wrong prefix is the failure this whole application exists to
prevent.
"""
import os
import sys
import threading
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtCore import pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton  # noqa: E402

from affinity_manager import aol, hosted, oplock, prefixlog, registry  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


class FakeInstaller(QMainWindow):
    """As much of AffinityInstallerGUI as the hosting touches."""

    progress_signal = pyqtSignal(float)
    progress_text_signal = pyqtSignal(str)
    refresh_status_signal = pyqtSignal()

    settle_at = None                 # set by a test to fake ignoring the env

    def __init__(self):
        super().__init__()
        self.setMinimumSize(900, 700)          # the real one does this too
        self.directory = self.settle_at or os.environ.get("AFFINITY_INSTALL_DIR", "")
        self.operation_in_progress = False
        self.messages = []
        self.logged = []
        self.donations = 0
        self.dxvk_checks = 0
        self.operations = []
        self.refreshes = 0
        self._all_action_buttons = [QPushButton("One"), QPushButton("Two")]
        self.refresh_status_signal.connect(self._count_refresh)

    def _count_refresh(self):
        self.refreshes += 1

    def log(self, message, level="info"):
        self.logged.append((message, level))

    def show_message(self, title, message, kind="info"):
        self.messages.append((title, message, kind))

    def show_donation_dialog(self):
        self.donations += 1

    def _check_and_update_dxvk_vkd3d(self):
        self.dxvk_checks += 1

    def start_operation(self, name):
        self.operations.append(name)
        self.operation_in_progress = True

    def end_operation(self):
        self.operation_in_progress = False

    def _save_install_location(self, directory):
        raise AssertionError("the hosted installer must not persist this")


@pytest.fixture
def hosting(qapp, tmp_path, monkeypatch):
    """A manager stand-in, a fake installer, and a prefix to point at."""
    monkeypatch.setattr(registry, "manager_dir", lambda: tmp_path)
    monkeypatch.setattr(hosted, "_hosted_cls", None)
    monkeypatch.setattr(hosted, "_live_pages", [])
    FakeInstaller.settle_at = None

    killed = []
    fake_module = types.SimpleNamespace(
        ENV_INSTALL_DIR="AFFINITY_INSTALL_DIR",
        ENV_INSTALLER_FILE="AFFINITY_INSTALLER_FILE",
        kill_stalled_wine_processes=lambda prefix=None: (killed.append(prefix),
                                                        ["[Cleanup] nothing to do"])[1],
    )
    monkeypatch.setattr(aol, "module", lambda script=None: fake_module)
    monkeypatch.setattr(aol, "cls", lambda: FakeInstaller)
    monkeypatch.delenv("AFFINITY_INSTALL_DIR", raising=False)

    prefix = tmp_path / "Scratch"
    (prefix / "drive_c").mkdir(parents=True)
    (prefix / "dosdevices").mkdir(parents=True)

    manager = types.SimpleNamespace(
        lock=oplock.OperationLock(),
        status=types.SimpleNamespace(setText=lambda *_: None),
        progress=types.SimpleNamespace(maximum=lambda: 100, setValue=lambda *_: None),
        show_list=lambda: None,
        _busy_start=None, _busy_done=None,
    )
    started, finished = [], []

    def busy_start(message, maximum=0, *, prefix=None, operation=None, alive=None,
                   already_held=False):
        if not already_held:
            manager.lock.claim(prefix, operation or message, alive=alive)
        started.append((prefix, operation))

    def busy_done(message="", owner=None):
        manager.lock.release(owner)
        finished.append(message)

    manager._busy_start = busy_start
    manager._busy_done = busy_done

    entry = {"name": "Scratch", "path": str(prefix)}
    return types.SimpleNamespace(manager=manager, entry=entry, prefix=prefix,
                                 killed=killed, started=started,
                                 finished=finished)


def page_for(h):
    return hosted.SetupPage(h.manager, h.entry)


# -- which prefix -----------------------------------------------------------

def test_the_page_points_the_installer_at_its_own_prefix(hosting):
    page = page_for(hosting)
    assert Path(page.installer.directory) == hosting.prefix


def test_a_window_that_settled_elsewhere_is_refused(hosting, tmp_path):
    """The installer remembers the last location it was told to use. A copy
    that ignored the environment would drive that one instead, and for somebody
    with a working prefix and a test prefix that is the worst thing this
    application could do."""
    FakeInstaller.settle_at = str(tmp_path / "SomewhereElse")
    with pytest.raises(hosted.WrongTarget) as caught:
        page_for(hosting)
    assert "SomewhereElse" in str(caught.value)
    assert str(hosting.prefix) in str(caught.value)


def test_the_environment_is_put_back(hosting):
    """Left set, it would leak the last-entered prefix into every subprocess
    the manager spawned afterwards."""
    os.environ["AFFINITY_INSTALL_DIR"] = "/somewhere/of/its/own"
    try:
        page_for(hosting)
        assert os.environ["AFFINITY_INSTALL_DIR"] == "/somewhere/of/its/own"
    finally:
        os.environ.pop("AFFINITY_INSTALL_DIR", None)


def test_the_environment_goes_away_again_when_it_was_not_set(hosting):
    page_for(hosting)
    assert "AFFINITY_INSTALL_DIR" not in os.environ


# -- window-ness removed ----------------------------------------------------

def test_the_installer_stops_being_a_window(hosting):
    page = page_for(hosting)
    assert page.installer.isWindow() is False
    assert page.installer.minimumSize().width() == 0
    assert page.installer.minimumSize().height() == 0


# -- deferred tasks ---------------------------------------------------------

def test_the_dxvk_check_waits_for_the_page_to_be_entered(hosting):
    page = page_for(hosting)
    page.installer._check_and_update_dxvk_vkd3d()   # the constructor's timer
    assert page.installer.dxvk_checks == 0
    page.entered()
    page.installer._check_and_update_dxvk_vkd3d()
    assert page.installer.dxvk_checks == 1


def test_the_automatic_donation_dialog_is_suppressed_once(hosting):
    """The 700ms timer's call is dropped; the Donate button still works."""
    page = page_for(hosting)
    page.installer.show_donation_dialog()          # the timer
    assert page.installer.donations == 0
    page.installer.show_donation_dialog()          # the button
    assert page.installer.donations == 1


def test_entering_a_page_kills_nothing(hosting):
    """Looking is not doing. This used to SIGKILL every Wine helper in the
    prefix, so opening a page closed a winecfg the user had left open."""
    page = page_for(hosting)
    page.entered()
    assert hosting.killed == []


def test_starting_an_operation_clears_stalled_wine_in_this_prefix_only(hosting, qapp):
    page = page_for(hosting)
    page.entered()
    page.installer.start_operation("Setup Wine Environment")
    qapp.processEvents()
    assert hosting.killed == [str(hosting.prefix)]


def test_a_nested_step_does_not_clear_again(hosting, qapp):
    page = page_for(hosting)
    page.installer.start_operation("One-Click Full Setup")
    page.installer.start_operation("Setting up Wine environment")
    qapp.processEvents()
    assert hosting.killed == [str(hosting.prefix)]


def test_the_dxvk_check_runs_once_on_the_first_entry(hosting):
    """The constructor arms a 500ms timer for it and nothing returns to the
    event loop before the page is entered, so calling it on entry as well ran
    it twice."""
    page = page_for(hosting)
    page.entered()
    assert page.installer.dxvk_checks == 0      # the timer will do it
    page.installer._check_and_update_dxvk_vkd3d()
    assert page.installer.dxvk_checks == 1
    page.entered()                              # coming back later
    assert page.installer.dxvk_checks == 2


def test_the_install_location_is_not_persisted(hosting):
    """FakeInstaller raises if the base implementation is reached."""
    page = page_for(hosting)
    page.installer._save_install_location("/anywhere")


# -- the lock ---------------------------------------------------------------

def test_an_operation_claims_the_lock(hosting):
    page = page_for(hosting)
    page.installer.start_operation("Setup Wine Environment")
    assert hosting.manager.lock.held.prefix == "Scratch"
    assert page.installer.operations == ["Setup Wine Environment"]


def test_an_operation_is_refused_while_another_prefix_works(hosting):
    page = page_for(hosting)
    hosting.manager.lock.claim("Other", "Install Affinity")
    with pytest.raises(oplock.InUse):
        page.installer.start_operation("Setup Wine Environment")
    # Refused, and the installer never started it.
    assert page.installer.operations == []
    assert page.installer.messages and "running" in page.installer.messages[0][0]


def test_finishing_an_operation_releases_the_lock_after_the_settle(hosting):
    """Not immediately. The installer's ends do not pair with its starts, so
    releasing on the first one would open the lock between two halves of a
    One-Click Full Setup."""
    page = page_for(hosting)
    page.installer.start_operation("Setup Wine Environment")
    page.installer.end_operation()
    assert page.installer.operation_in_progress is False
    assert hosting.manager.lock.held is not None      # settle pending
    assert page._settle.isActive()

    page._release_after_settle()
    assert hosting.manager.lock.held is None


def test_a_nested_operation_does_not_re_claim_and_does_not_refuse(hosting):
    """This is the bug that made One-Click Full Setup unable to install Wine.

    _one_click_setup_thread claims, then calls setup_wine, whose own first
    statement claims again. claim() raised InUse naming the prefix's own
    operation, and the raise killed the worker thread."""
    page = page_for(hosting)
    page.installer.start_operation("One-Click Full Setup")
    page.installer.start_operation("Setting up Wine environment")
    held = hosting.manager.lock.held
    assert held is not None and held.prefix == "Scratch"
    assert held.label == "Setting up Wine environment"
    assert page.installer.operations == ["One-Click Full Setup",
                                         "Setting up Wine environment"]


def test_a_nested_end_does_not_open_the_lock_to_another_prefix(hosting, qapp):
    """setup_wine ends its own operation with four one-click steps still to
    run. If that released, a clone of another prefix could start mid-install."""
    page = page_for(hosting)
    page.installer.start_operation("One-Click Full Setup")
    page.installer.start_operation("Setting up Wine environment")
    page.installer.end_operation()                # setup_wine's own end
    qapp.processEvents()
    assert hosting.manager.lock.held is not None

    page.installer.start_operation("Installing Winetricks dependencies")
    qapp.processEvents()
    assert not page._settle.isActive(), "a further start must cancel the settle"
    assert hosting.manager.lock.held.label == "Installing Winetricks dependencies"


def test_a_slot_that_raises_does_not_abort_the_process(hosting, qapp):
    """PyQt6 calls qFatal() on an exception escaping a slot. Adding one keyword
    argument to a manager method once aborted the whole test suite this way."""
    page = page_for(hosting)

    def explode(*a, **k):
        raise TypeError("unexpected keyword argument")

    hosting.manager._busy_start = explode
    page.installer.start_operation("Setup Wine Environment")   # must not abort
    qapp.processEvents()
    assert any("failed" in line for line, _ in page.installer.logged)


def test_the_watchdog_oracle_follows_the_installers_own_flag(hosting):
    page = page_for(hosting)
    page.installer.start_operation("Setup Wine Environment")
    operation = hosting.manager.lock.held
    assert operation.finished() is False
    page.installer.operation_in_progress = False
    assert operation.finished() is True


# -- availability -----------------------------------------------------------

def test_another_prefix_working_greys_this_pages_buttons(hosting):
    page = page_for(hosting)
    page.set_actions_enabled(False)
    assert all(not b.isEnabled() for b in page.installer._all_action_buttons)


def test_re_enabling_puts_every_button_back_as_it_was(hosting, qapp):
    """check_installation_status manages only a handful of these. Handing
    re-enabling to it left every other action button dead for the life of the
    page, so one clone of another prefix permanently disabled most of Setup."""
    page = page_for(hosting)
    one, two = page.installer._all_action_buttons
    one.setEnabled(False)               # the installer's own decision
    two.setEnabled(True)

    page.set_actions_enabled(False)
    assert not one.isEnabled() and not two.isEnabled()

    page.set_actions_enabled(True)
    qapp.processEvents()
    assert not one.isEnabled(), "the installer's own decision was overridden"
    assert two.isEnabled(), "a button the installer does not manage stayed dead"
    assert page.installer.refreshes == 1


def test_disabling_twice_does_not_lose_the_original_state(hosting, qapp):
    page = page_for(hosting)
    one, two = page.installer._all_action_buttons
    one.setEnabled(False)
    page.set_actions_enabled(False)
    page.set_actions_enabled(False)     # a second prefix starts working too
    page.set_actions_enabled(True)
    qapp.processEvents()
    assert not one.isEnabled() and two.isEnabled()


def test_re_enabling_does_nothing_when_nothing_was_disabled(hosting, qapp):
    page = page_for(hosting)
    page.set_actions_enabled(True)
    qapp.processEvents()
    assert page.installer.refreshes == 0


# -- the record -------------------------------------------------------------

def test_log_lines_reach_the_prefixs_own_log(hosting):
    page = page_for(hosting)
    page.installer.log("Setting up Wine", "info")
    assert "Setting up Wine" in prefixlog.tail("Scratch")


def test_a_thread_that_died_is_reported_and_the_old_hook_still_runs(hosting):
    page = page_for(hosting)
    hosted.own_thread_exceptions(page)
    seen = []
    try:
        previous = hosted._previous_excepthook
        hosted._previous_excepthook = seen.append
        args = threading.ExceptHookArgs(
            (RuntimeError, RuntimeError("wine exploded"), None, None))
        hosted._thread_excepthook(args)
    finally:
        hosted._previous_excepthook = previous
    assert "wine exploded" in prefixlog.tail("Scratch")
    assert seen == [args]


def test_a_thread_exception_after_disposal_reaches_nobody(hosting):
    page = page_for(hosting)
    hosted.own_thread_exceptions(page)
    page.dispose()
    assert page not in hosted._live_pages
    args = threading.ExceptHookArgs(
        (RuntimeError, RuntimeError("too late"), None, None))
    try:
        previous = hosted._previous_excepthook
        hosted._previous_excepthook = lambda _a: None
        hosted._thread_excepthook(args)          # must not raise
    finally:
        hosted._previous_excepthook = previous
    assert "too late" not in prefixlog.tail("Scratch")


def test_a_thread_still_running_after_disposal_cannot_reach_the_page(hosting, qapp):
    """The installer starts daemon threads in its CONSTRUCTOR -- background
    probing, the patcher fetch, the icon download -- and those have nothing to
    do with the lock that decides whether a page may be dropped. One of them
    calling start_operation after dispose() would claim the lock for a prefix
    with no page, and touch a widget Qt has been told to delete."""
    page = page_for(hosting)
    installer = page.installer
    page.dispose()
    qapp.processEvents()

    assert installer._page is None
    installer.start_operation("Late arrival")     # must not raise, must not claim
    installer.end_operation()
    qapp.processEvents()
    assert hosting.manager.lock.held is None
    assert hosting.started == []


def test_disposal_disconnects_the_progress_signals(hosting, qapp):
    page = page_for(hosting)
    installer = page.installer
    page.dispose()
    qapp.processEvents()
    installer.progress_text_signal.emit("still going")   # must reach nobody
    installer.progress_signal.emit(0.5)
    qapp.processEvents()


# -- the closing message ------------------------------------------------------

def test_the_closing_message_sends_a_non_default_prefix_to_the_manager(hosting, monkeypatch):
    """Hosted, the install writes no menu entry, so "launch it from your
    application menu" pointed at an entry that starts another prefix, or none."""
    from affinity_manager import defaultentry
    monkeypatch.setattr(defaultentry, "current", lambda: "Everyday")
    text = page_for(hosting).installer.launch_instructions()
    assert '"Scratch"' in text and "Launch" in text
    assert "Make Default" in text and 'instead of "Everyday"' in text
    assert "Add to menu" in text
    assert "application menu starts it" not in text


def test_the_closing_message_for_the_default_prefix_points_at_the_menu(hosting, monkeypatch):
    from affinity_manager import defaultentry
    monkeypatch.setattr(defaultentry, "current", lambda: "Scratch")
    text = page_for(hosting).installer.launch_instructions()
    assert "is the Default prefix" in text and "application menu starts it" in text
    assert "Make Default" not in text


def test_the_closing_message_without_any_default(hosting, monkeypatch):
    from affinity_manager import defaultentry
    monkeypatch.setattr(defaultentry, "current", lambda: None)
    text = page_for(hosting).installer.launch_instructions()
    assert "Make Default" in text and "instead of" not in text


def test_the_closing_message_survives_an_unreadable_default(hosting, monkeypatch):
    from affinity_manager import defaultentry

    def broken():
        raise OSError("unreadable")
    monkeypatch.setattr(defaultentry, "current", broken)
    assert "Make Default" in page_for(hosting).installer.launch_instructions()


# -- the offer after an install -----------------------------------------------

class FakeBox:
    """QMessageBox stand-in: records the text and clicks the named button."""
    click = "Make Default"
    shown = []
    from PyQt6.QtWidgets import QMessageBox as _Real
    Icon, ButtonRole = _Real.Icon, _Real.ButtonRole

    def __init__(self, parent=None):
        self.buttons = {}
        self.clicked = None

    def setIcon(self, *_): pass
    def setWindowTitle(self, *_): pass
    def setDefaultButton(self, *_): pass

    def setText(self, text):
        FakeBox.shown.append(text)

    def addButton(self, label, role):
        self.buttons[label] = object()
        return self.buttons[label]

    def exec(self):
        self.clicked = self.buttons.get(FakeBox.click)

    def clickedButton(self):
        return self.clicked


def _offer(hosting, qapp, monkeypatch, default, click):
    from affinity_manager import defaultentry
    monkeypatch.setattr(defaultentry, "current", lambda: default)
    monkeypatch.setattr(defaultentry, "plan", lambda name, path: ("plan", name))
    monkeypatch.setattr(hosted, "QMessageBox", FakeBox)
    FakeBox.click, FakeBox.shown = click, []
    applied = []
    hosting.manager._apply_default = lambda plan, quiet=False: applied.append(plan)
    page = page_for(hosting)
    page.installer.offer_after_install()
    qapp.processEvents()
    _offer.logged = [line for line, _ in page.installer.logged if "failed" in line]
    return applied


def test_an_install_offers_to_make_the_prefix_the_default(hosting, qapp, monkeypatch):
    """The closing message said how, as its last paragraph, and a new install
    went unused: the menu entry kept starting the old Default prefix."""
    applied = _offer(hosting, qapp, monkeypatch, "Everyday", "Make Default")
    assert applied == [("plan", "Scratch")], _offer.logged
    assert '"Everyday"' in FakeBox.shown[0] and '"Scratch"' in FakeBox.shown[0]


def test_not_now_leaves_the_default_alone(hosting, qapp, monkeypatch):
    assert _offer(hosting, qapp, monkeypatch, "Everyday", "Not now") == []


def test_no_offer_when_the_prefix_is_the_default_already(hosting, qapp, monkeypatch):
    assert _offer(hosting, qapp, monkeypatch, "Scratch", "Make Default") == []
    assert FakeBox.shown == []


def test_the_offer_says_when_there_is_no_default():
    text = hosted.default_offer_text("Scratch", None)
    assert "No prefix is the Default yet" in text and '"Scratch"' in text
