"""The AffinityOnLinux installer, hosted as a page of the manager window.

Not launched as a child process any more. The manager is the main window and
Setup is a state of it, which means the installer's window has to stop being a
window: reparented into the manager's QStackedWidget it keeps its layout and
loses its title bar, its own size constraints and its independent lifetime.

Four things follow from that, and each is handled here rather than upstream,
because upstream is still a single file that people run with `curl | python3`
and it has to keep working that way.

  * Size. The constructor sets a minimum of half the screen, which is right for
    a window of its own and would make the manager unresizable. Cleared after
    construction, and the page scrolls, so a tall installer UI stays reachable
    in a short window.

  * Which prefix. AFFINITY_INSTALL_DIR is read once, in the constructor. As a
    child process that was the child's environment; here it is ours, so it is
    set for the length of the construction and put back afterwards -- and the
    directory the window settled on is checked against the one asked for before
    the page is shown at all. An installer pointed at the wrong prefix is the
    failure this whole project exists to prevent.

  * Time. Three deferred tasks are scheduled 50ms, 500ms and 700ms after the
    constructor returns: background probing, a DXVK/vkd3d check, and a donation
    dialog. Hosted, the first is fine, the second belongs to entering the page
    rather than to building it, and the third is a modal appearing over a
    manager the user did not ask a question of.

  * One operation at a time. The installer's own start_operation /
    end_operation are the choke point -- not every button click is an operation,
    and a theme toggle must not be refused -- so the lock is taken and given up
    there.

    And those run on the installer's own worker threads.
    _one_click_setup_thread's first statement is a start_operation, so the
    claim has to be thread-safe and answer immediately, while everything it
    causes to be painted has to happen on the GUI thread. The two halves are
    split accordingly: the claim is taken where the call lands, and a signal
    carries the rest across.

    They also nest, and not in a balanced way -- one installer method has one
    start_operation and eleven end_operations -- so the lock is held for the
    page rather than counted, and given up after a short settle that any
    further start_operation cancels. Releasing on the first end_operation
    would open the lock between the steps of a One-Click Full Setup.
"""

from __future__ import annotations

import contextlib
import functools
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import aol, oplock, prefixlog, prefixstate


def never_escapes(method):
    """Wrap a Qt slot so nothing can leave it.

    PyQt6 calls qFatal() on an exception that escapes a slot, and qFatal
    aborts the process -- no traceback the user will see, no chance to save
    anything, in the middle of an install. Every slot on the page below does
    real work against the manager and the installer, so every one of them gets
    this.

    Learned twice. The first time was reasoning about oplock.InUse; the second
    was adding one keyword argument to a manager method, which made a
    TypeError in a slot abort the whole test suite. A slot that swallows and
    logs is recoverable; a slot that raises is not."""

    @functools.wraps(method)
    def guarded(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except Exception as exc:
            note = "%s failed: %s: %s" % (method.__name__, type(exc).__name__, exc)
            with contextlib.suppress(Exception):
                prefixlog.write(self.name, note)
            with contextlib.suppress(Exception):
                self.installer.log(note, "error")

    return guarded


class WrongTarget(RuntimeError):
    """The installer did not end up pointing at the prefix it was given.

    Shown rather than worked around. The installer remembers the last location
    it was told to use, and a version that ignored the environment would
    silently drive that one instead -- which, for somebody with a working
    prefix and a test prefix, is the worst thing this application could do."""


# ── thread exceptions ────────────────────────────────────────────────────────
#
# The installer does its work in daemon threads. On its own that is fine: a
# thread that dies prints a traceback to the terminal it was started from.
# Hosted there may be no terminal, and a dead thread is also a lock nobody will
# release, so the death has to reach the log that belongs to the prefix.

_previous_excepthook = None
_live_pages = []            # every page that still has an installer in it


def _thread_excepthook(args):
    """Report a dead worker to the prefix it most likely belongs to.

    Nothing in threading.ExceptHookArgs says which installer started the
    thread, and there can be two pages alive at once. Pointing a single global
    at whichever page is visible was worse than not guessing: a thread dying in
    the prefix being installed would be logged against the prefix the user had
    just navigated to. So the page with an operation in flight gets it, and if
    that is ambiguous every live page is told, with the doubt stated."""
    if args.exc_type is not SystemExit:
        pages = list(_live_pages)
        working = [p for p in pages
                   if bool(getattr(getattr(p, "installer", None),
                                   "operation_in_progress", False))]
        targets = working or pages
        uncertain = len(targets) > 1
        for page in targets:
            with contextlib.suppress(Exception):
                page.thread_died(args, uncertain=uncertain)
    if _previous_excepthook is not None:
        _previous_excepthook(args)


def _install_thread_excepthook():
    global _previous_excepthook
    if _previous_excepthook is None:
        _previous_excepthook = threading.excepthook
        threading.excepthook = _thread_excepthook


# ── the window, made hostable ────────────────────────────────────────────────

_hosted_cls = None


def hosted_class():
    """AffinityInstallerGUI with the window-ness taken out.

    Built on first use rather than at import, because the base class does not
    exist until the installer has been located and loaded, and a manager whose
    import fails because no installer is on disk would be useless for the one
    thing that could fix it."""
    global _hosted_cls
    if _hosted_cls is not None:
        return _hosted_cls

    base = aol.cls()

    class HostedInstaller(base):
        """One installer window, living inside the manager."""

        def __init__(self, page):
            super().__init__()
            # Set after super(), which is the only order sip allows, so the
            # deferred tasks scheduled in there read these through getattr.
            self._page = page
            self._donation_suppressed = True
            # The constructor's minimum is half the screen. Right for a window,
            # wrong for a page: it would set the floor for the whole manager.
            self.setMinimumSize(0, 0)

        def manages_host_entries(self):
            """The manager keeps the Default entry and the per-prefix ones
            (defaultentry); an install here must not rewrite the fixed-name
            Affinity.desktop, desktop icon or affinity:// handler, which
            belong to whichever prefix is the Default."""
            return False

        def launch_instructions(self):
            """Where to start this prefix: the manager writes the menu entry
            and the document handlers only for the Default."""
            from . import defaultentry
            name = self._page.name
            try:
                default = defaultentry.current()
            except Exception:  # noqa: BLE001 -- only the wording depends on it
                default = None
            return launch_instructions_text(name, default)

        def offer_after_install(self):
            """After an install: offer to make this prefix the Default. Called
            from the installer's worker thread; the page asks on the GUI thread."""
            page = getattr(self, "_page", None)
            if page is not None:
                page.install_finished.emit()

        # -- deferred tasks that belong to entering, not to building ---------

        def _check_and_update_dxvk_vkd3d(self):
            """Skip the constructor's 500ms call; the page runs this on entry.

            Building the page and entering it are the same moment the first
            time and different moments every time after, and this check should
            happen on every entry -- a prefix can gain a Wine installation
            while the manager is looking at something else."""
            if not getattr(self, "_entered", False):
                return
            super()._check_and_update_dxvk_vkd3d()

        def show_donation_dialog(self):
            """Suppress the automatic one; keep the button.

            The 700ms timer would put a modal over a manager window the user
            was in the middle of using, on every entry into Setup. The Donate
            button calls this same method and is left working, which is the
            part that was ever the user's own choice."""
            if getattr(self, "_donation_suppressed", False):
                self._donation_suppressed = False
                return
            super().show_donation_dialog()

        # -- the lock -------------------------------------------------------

        def start_operation(self, operation_name):
            page = getattr(self, "_page", None)
            if page is not None:
                try:
                    page.operation_started(operation_name)
                except oplock.InUse as exc:
                    # Said twice on purpose: show_message is the dialog the
                    # user sees, and the raise is what stops the caller from
                    # starting the thread it was about to start.
                    self.show_message("Something else is running", str(exc),
                                      "warning")
                    raise
            super().start_operation(operation_name)

        def end_operation(self):
            super().end_operation()
            page = getattr(self, "_page", None)
            if page is not None:
                page.operation_finished()

        # -- the record -----------------------------------------------------

        def log(self, message, level="info"):
            """Mirror into the prefix's own log as well as the installer's.

            ~/AffinitySetup.log is shared by every run and is where upstream
            puts this; the per-prefix log is what the manager reads back when
            it has to say what an interrupted operation was doing."""
            super().log(message, level)
            page = getattr(self, "_page", None)
            if page is not None and str(message).strip():
                with contextlib.suppress(Exception):
                    prefixlog.write(page.name, str(message))

        def _save_install_location(self, directory):
            """Not persisted from here.

            This writes the installer's remembered location, which a later
            standalone run would open on. The manager already knows which
            prefix is which, and a look at a scratch prefix inside the manager
            should not move where the installer opens by itself afterwards."""
            self.log("Install location not persisted: the manager holds it.",
                     "info")

    _hosted_cls = HostedInstaller
    return _hosted_cls


# ── the page ─────────────────────────────────────────────────────────────────

def launch_instructions_text(name, default):
    """The closing message of an install in prefix `name`, when `default` is
    the Default prefix (None when there is none)."""
    if default == name:
        return (f'"{name}" is the Default prefix: the Affinity entry in your '
                "application menu starts it, and double-clicked Affinity documents "
                "open in it. In the manager, Launch starts it too.")
    instead = f' instead of "{default}"' if default else ""
    return (
        f'Start it from the manager: select "{name}" in the prefix list and '
        "click Launch.\n\n"
        "To start it from your application menu, select it and click Make "
        "Default. The menu's Affinity entry, double-clicked Affinity documents "
        f"and the Canva sign-in then all go to this prefix{instead}.\n\n"
        "Or click Add to menu for a menu entry of its own, named after the "
        "prefix. Double-clicked documents always open in the Default prefix.")


def default_offer_text(name, default):
    """The question after an install in prefix `name`, when `default` is the
    Default prefix (None when there is none)."""
    if default:
        now = (f'The Affinity entry in your application menu, double-clicked '
               f'Affinity documents and the Canva sign-in still start "{default}".')
    else:
        now = ("No prefix is the Default yet, so your application menu has no "
               "Affinity entry and double-clicked Affinity documents do not open.")
    return (f'Affinity is installed in "{name}".\n\n{now}\n\n'
            f'Make "{name}" the Default, so they start it instead? You can change '
            "this later with Make Default in the prefix list.")


class SetupPage(QWidget):
    """Setup for one prefix: a header, and the installer under it."""

    # Emitted from the installer's worker threads; the slots run on the GUI
    # thread because this object lives there and Qt queues across threads.
    # (label, is_the_start_of_real_work). The second is decided where the
    # claim is taken, not in the slot: by the time the slot runs the lock is
    # already held by this page, so "is the lock ours" can no longer tell a
    # first start from a nested one.
    operation_began = pyqtSignal(str, bool)
    operation_ended = pyqtSignal()
    # An Affinity install finished (emitted from the installer's thread).
    install_finished = pyqtSignal()

    # How long to wait after an end_operation before giving up the lock. Long
    # enough to cover the gap between a nested step finishing and the next one
    # starting, short enough that nobody notices it on a real finish.
    SETTLE_MS = 2000

    def __init__(self, manager, entry):
        super().__init__()
        self.manager = manager
        self.entry = entry
        self.name = entry["name"]
        self.path = Path(entry["path"])
        self._last_progress_text = None

        self._working = False
        self._disabled_state = None
        self.operation_began.connect(self._operation_began)
        self.operation_ended.connect(self._operation_ended)
        self.install_finished.connect(self._offer_default)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(self.SETTLE_MS)
        self._settle.timeout.connect(self._release_after_settle)

        _install_thread_excepthook()

        # Built with the environment pointed at this prefix, and only this
        # prefix, for exactly as long as the constructor runs.
        with aol.target_env(self.path, entry.get("installer_file")):
            self.installer = hosted_class()(self)

        settled = Path(self.installer.directory).expanduser()
        if settled.resolve() != self.path.resolve():
            self.installer.close()
            self.installer.deleteLater()
            raise WrongTarget(
                "The installer was given %s and settled on %s. It has not been "
                "shown, because driving the wrong prefix is worse than not "
                "being able to drive one." % (self.path, settled))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 12, 20, 12)
        header_layout.setSpacing(12)
        self.back_button = QPushButton("← Affinity on Linux Prefix Manager")
        self.back_button.setToolTip("Back to the prefix list")
        self.back_button.clicked.connect(manager.show_list)
        header_layout.addWidget(self.back_button, 0)
        title = QLabel("Configure — %s" % self.name)
        title.setObjectName("sectionTitle")
        header_layout.addWidget(title, 0)
        where = QLabel(str(self.path))
        where.setObjectName("descriptionLabel")
        where.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        header_layout.addWidget(where, 1)
        layout.addWidget(header, 0)

        # Scrolled, because the installer lays out for a window of its own and
        # the manager can be shorter than that. widgetResizable so it uses the
        # full width when there is width to use.
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setWidget(self.installer)      # reparents: no longer a window
        layout.addWidget(area, 1)

        # Connected once, for the life of the page. These are Qt signals from
        # a QObject in this thread, so an emit from a worker is queued and the
        # slots run here -- which is why they may touch the manager's widgets.
        # Connecting and disconnecting them per operation was the first
        # version and accumulated duplicate connections whenever an end did
        # not pair with its start.
        self.installer.progress_text_signal.connect(self._progress_text)
        self.installer.progress_signal.connect(self._progress)

    # -- entering and leaving -------------------------------------------------

    def entered(self):
        """Called every time this page becomes the visible one.

        Looking is not doing. This used to clear stalled Wine processes here,
        which meant that merely opening a prefix's Setup page SIGKILLed
        whatever Wine helpers were running in it -- a winecfg the user had left
        open, a winetricks started from a terminal. The clearing belongs to the
        moment work actually starts, and that is where it is now."""
        first = not getattr(self.installer, "_entered", False)
        self.installer._entered = True
        self._say_where_we_are()
        # Not on the first entry. The constructor armed a 500ms timer for this
        # and nothing returns to the event loop between building the page and
        # entering it, so calling it here as well simply ran it twice.
        if not first:
            self.installer._check_and_update_dxvk_vkd3d()

    def _say_where_we_are(self):
        """The shared status line still holds whatever the list left on it.

        One line, two states: the same bar that said "nothing managed yet" a
        moment ago is now the Setup page's, and leaving the list's sentence
        there would describe the wrong thing entirely."""
        if self.manager.lock.held is not None:
            return                      # an operation's own reporting outranks this
        condition = prefixstate.classify(self.path, entry=self.entry)
        self.manager.status.setText("%s — %s" % (self.name, condition.detail))

    def _clear_stalled_wine(self):
        """Clear leftover Wine helpers in THIS prefix, and no other.

        Upstream runs this from main(), which the manager never calls. It
        scopes itself by /proc/<pid>/environ and refuses entirely if Affinity
        is live in the target, so it cannot end a session.

        Called when an operation starts, not when the page is opened. It
        returns its report rather than printing it -- capturing stdout meant
        swapping sys.stdout for the whole process, which caught whatever other
        threads wrote while it was in place and filed it under this prefix."""
        try:
            for line in aol.module().kill_stalled_wine_processes(
                    prefix=str(self.path)) or []:
                self.installer.log(line, "info")
        except Exception as exc:
            self.installer.log("Could not check for stalled Wine processes: %s"
                               % exc, "warning")

    # -- the lock, and the manager's status line ------------------------------

    def operation_started(self, label):
        """Take the lock, from whichever thread asked. Raises oplock.InUse.

        This runs on the installer's worker thread as often as not, so it does
        exactly two things: it answers the question the caller needs answered
        now -- may this operation run -- and it hands the rest to the GUI
        thread. Nothing here touches a widget.

        hold() rather than claim(), because the installer's operations nest and
        a second claim from the same page is the same operation carrying on,
        not a collision."""
        fresh = not self._working
        self._working = True
        self.manager.lock.hold(
            self.name, label,
            # The installer's own flag is the oracle. It is set by the
            # start_operation this call precedes, so for a moment it still
            # reads False -- which is what OperationLock.SWEEP_GRACE covers.
            alive=lambda: bool(getattr(self.installer, "operation_in_progress",
                                       False)))
        self.operation_began.emit(label, fresh)

    def operation_finished(self):
        """Also called from a worker thread; also does nothing but signal."""
        self.operation_ended.emit()

    # -- the GUI-thread halves ------------------------------------------------

    @never_escapes
    def _offer_default(self):
        """Ask whether the prefix just installed should be the Default.

        The closing message says how, but it is the last paragraph of a long
        box, and a new install then went unused: the menu entry, which belongs
        to the Default, kept starting the old prefix. Asked after that box has
        been closed, and only when this prefix is not the Default already."""
        if QApplication.activeModalWidget() is not None:
            QTimer.singleShot(500, self._offer_default)
            return
        from . import defaultentry
        try:
            default = defaultentry.current()
        except Exception:  # noqa: BLE001 -- then there is just nothing to offer
            return
        if default == self.name:
            return
        try:
            plan = defaultentry.plan(self.name, str(self.path))
        except (FileNotFoundError, OSError):
            return
        box = QMessageBox(self.window())
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(f"Make {self.name} the Default?")
        box.setText(default_offer_text(self.name, default))
        make = box.addButton("Make Default", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Not now", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(make)
        box.exec()
        if box.clickedButton() is make:
            self.manager._apply_default(plan)

    @never_escapes
    def _operation_began(self, label, fresh=True):
        self._settle.stop()             # a nested step cancels the release
        self._last_progress_text = None
        if fresh:
            # The start of real work, which is the only moment a stalled
            # wineserver in this prefix is in the way.
            self._clear_stalled_wine()
        self.manager._busy_start(
            "%s — %s" % (self.name, label), 100,
            prefix=self.name, operation=label, already_held=True,
            alive=lambda: bool(getattr(self.installer,
                                       "operation_in_progress", False)))

    @never_escapes
    def _operation_ended(self):
        """Start the settle, rather than releasing now.

        The installer's ends do not pair with its starts. setup_wine ends its
        own operation in the middle of a One-Click Full Setup that has four
        more steps to run, so releasing here would open the lock to another
        prefix between two halves of one install."""
        self._settle.start()

    @never_escapes
    def _release_after_settle(self):
        self._working = False
        if self.manager.lock.held is None:
            return                      # the watchdog got there first
        self.manager._busy_done("%s — finished" % self.name, owner=self.name)
        settled = getattr(self.manager, "setup_settled", None)
        if settled is not None:
            settled(self.name)

    @never_escapes
    def _progress_text(self, text):
        """The installer's progress line, shown on the manager's status bar.

        Deliberately not manager._busy_step: that calls processEvents, and this
        arrives on a queued signal from a worker thread, so processing events
        from inside it would be re-entering the event loop from a slot."""
        if not text or text == self._last_progress_text:
            return
        self._last_progress_text = text
        self.manager.status.setText("%s — %s" % (self.name, text))

    @never_escapes
    def _progress(self, fraction):
        bar = self.manager.progress
        top = bar.maximum()
        if top:
            bar.setValue(max(0, min(top, int(fraction * top))))

    # -- availability ---------------------------------------------------------

    def set_actions_enabled(self, enabled):
        """Grey the installer's own buttons while another prefix is working.

        What each button was is remembered, and put back. The first version
        disabled them one at a time and then handed re-enabling to
        check_installation_status, on the reasoning that the installer disables
        buttons for its own reasons and should have the last word. It does --
        but only over the handful of buttons it manages. Every other action
        button had no way back on at all and stayed dead for the life of the
        page, so one clone of another prefix permanently disabled most of
        Setup.

        The installer is still asked to recompute afterwards, so its own rules
        still win where it has any."""
        buttons = getattr(self.installer, "_all_action_buttons", None) or []
        if not enabled:
            if self._disabled_state is None:
                state = []
                for button in buttons:
                    with contextlib.suppress(Exception):
                        state.append((button, button.isEnabled()))
                        button.setEnabled(False)
                self._disabled_state = state
            return
        if self._disabled_state is None:
            return
        for button, was_enabled in self._disabled_state:
            with contextlib.suppress(Exception):
                button.setEnabled(was_enabled)
        self._disabled_state = None
        with contextlib.suppress(Exception):
            self.installer.refresh_status_signal.emit()

    # -- a thread that died ---------------------------------------------------

    def thread_died(self, args, uncertain=False):
        """A worker thread raised and nobody caught it.

        Logged rather than absorbed: the lock's watchdog will notice within a
        few seconds that the operation has stopped, but it cannot say why, and
        this is the only place that can."""
        note = "A background task ended with %s: %s" % (
            args.exc_type.__name__, args.exc_value)
        if uncertain:
            note += (" (more than one Configure page was open; this may belong to "
                     "another prefix)")
        prefixlog.write(self.name, note)
        with contextlib.suppress(Exception):
            self.installer.log(note, "error")

    # -- teardown -------------------------------------------------------------

    def dispose(self):
        """Close the installer this page holds, and make it unreachable first.

        The page is only dropped when its prefix is not the one holding the
        lock -- but the installer starts daemon threads in its CONSTRUCTOR, and
        those have nothing to do with the lock. Background probing, the patcher
        fetch, the icon download: all of them still running, all of them about
        to touch a window Qt has been told to delete.

        So the order matters. The signals come apart, the installer's back
        reference to this page is cleared -- every override checks it, so they
        all become no-ops -- and only then is the widget closed. A thread that
        wakes up afterwards finds nothing to write into rather than a deleted
        C++ object."""
        if self in _live_pages:
            _live_pages.remove(self)
        self._settle.stop()
        for signal, slot in ((self.installer.progress_text_signal, self._progress_text),
                             (self.installer.progress_signal, self._progress)):
            with contextlib.suppress(TypeError, RuntimeError):
                signal.disconnect(slot)
        with contextlib.suppress(Exception):
            self.installer._page = None
        with contextlib.suppress(Exception):
            self.installer.close()
        self.installer.deleteLater()


def own_thread_exceptions(page):
    """Register a page as one a dying thread could belong to."""
    if page not in _live_pages:
        _live_pages.append(page)
