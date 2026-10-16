"""The window's half of the operation lock.

oplock itself is tested in test_oplock.py. What is tested here is the wiring:
that the manager's own operations actually go through the lock, that the
watchdog tick releases work which stopped without saying so, and that a
refusal or a hand release leaves the window in a coherent state.

The `window` fixture (conftest.py) is a ManagerWindow with the Qt removed --
real registry, real lock, real _busy_* methods.
"""
import inspect
import types
from pathlib import Path

import pytest

from affinity_manager import oplock


@pytest.fixture
def two_prefixes(window, tmp_path):
    """A second managed prefix, so "somewhere else" is a real place."""
    w, reg, _ = window
    other = tmp_path / "Other"
    (other / "drive_c").mkdir(parents=True)
    (other / "dosdevices").mkdir(parents=True)
    reg.add("Other", str(other))
    return window


# -- the manager's own operations go through it -----------------------------

def test_starting_an_operation_claims_the_lock(window):
    w, _, _ = window
    w._busy_start("Cleaning Managed", 3, prefix="Managed", operation="Clean")
    assert w.lock.held is not None and w.lock.held.label == "Clean"


def test_a_second_operation_is_refused(two_prefixes):
    w, _, _ = two_prefixes
    w._busy_start("Cleaning Managed", 3, prefix="Managed", operation="Clean")
    with pytest.raises(oplock.InUse):
        w._busy_start("Cloning Other", 100, prefix="Other", operation="Clone")


def test_the_refused_operation_leaves_the_first_one_alone(two_prefixes):
    """A refusal must not half-start: no registry row, no log offset, and the
    prefix that was working is still the one recorded as working."""
    w, reg, _ = two_prefixes
    w._busy_start("Cleaning Managed", 3, prefix="Managed", operation="Clean")
    with pytest.raises(oplock.InUse):
        w._busy_start("Cloning Other", 100, prefix="Other", operation="Clone")
    assert reg.by_name("Other").get("state") != "working"
    assert reg.by_name("Managed")["state"] == "working"
    assert w._busy_prefix == "Managed"


def test_finishing_releases_it(window):
    w, _, _ = window
    w._busy_start("Cleaning Managed", 3, prefix="Managed", operation="Clean")
    w._busy_done("Done")
    assert w.lock.held is None
    w._busy_start("Cleaning Managed", 3, prefix="Managed", operation="Clean")


def test_an_operation_with_no_prefix_claims_nothing(window):
    """Some indication is just indication -- a scan, a refresh -- and has no
    prefix to name. Those must not take the lock."""
    w, _, _ = window
    w._busy_start("Looking around")
    assert w.lock.held is None


# -- the watchdog -----------------------------------------------------------

def test_the_tick_releases_work_that_stopped_without_saying_so(window, monkeypatch):
    w, reg, prefixlog = window
    running = {"yes": True}
    w._busy_start("Cloning", 100, prefix="Managed", operation="Clone",
                  alive=lambda: running["yes"])
    past_grace = w.lock.held.started + oplock.OperationLock.SWEEP_GRACE + 1
    monkeypatch.setattr(oplock, "_now", lambda: past_grace)

    w._lock_tick()
    assert w.lock.held is not None      # still running, still held

    running["yes"] = False
    w._lock_tick()
    assert w.lock.held is None
    assert reg.by_name("Managed").get("state") != "working"
    assert "without reporting" in prefixlog.tail("Managed")


def test_the_tick_leaves_a_live_operation_alone(window, monkeypatch):
    w, reg, _ = window
    w._busy_start("Cloning", 100, prefix="Managed", operation="Clone",
                  alive=lambda: True)
    later = w.lock.held.started + 3600
    monkeypatch.setattr(oplock, "_now", lambda: later)
    w._lock_tick()
    assert w.lock.held is not None
    assert reg.by_name("Managed")["state"] == "working"


def test_the_tick_does_nothing_when_nothing_is_held(window):
    w, _, _ = window
    w._lock_tick()
    assert w.lock.held is None


# -- the caution row --------------------------------------------------------

def test_the_caution_row_follows_the_lock(window):
    w, _, _ = window
    shown = []
    w.lock_row.show = lambda: shown.append(True)
    w.lock_row.hide = lambda: shown.append(False)
    w._busy_start("Cleaning Managed", 3, prefix="Managed", operation="Clean")
    assert shown[-1] is True
    w._busy_done("Done")
    assert shown[-1] is False


def test_the_banner_names_the_operation_and_its_prefix(window):
    w, _, _ = window
    said = []
    w.lock_banner.setText = said.append
    w._busy_start("Cleaning Managed", 3, prefix="Managed", operation="Clean")
    assert "Clean" in said[-1] and "Managed" in said[-1]


def test_an_unchanged_line_is_not_repainted(window):
    """The watchdog ticks forever; an idle manager should do no work in it."""
    w, _, _ = window
    said = []
    w.lock_row.show = lambda: said.append("show")
    w.lock_row.hide = lambda: said.append("hide")
    w._sync_lock_ui()
    w._sync_lock_ui()
    w._sync_lock_ui()
    assert said.count("hide") <= 1


# -- releasing by hand ------------------------------------------------------

def test_release_by_hand_frees_the_lock_and_says_so(window, monkeypatch):
    import AffinityLinuxManager as app
    w, reg, prefixlog = window
    monkeypatch.setattr(app.QMessageBox, "question",
                        staticmethod(lambda *a, **k: app.QMessageBox.StandardButton.Ok))
    w._busy_start("Cloning", 100, prefix="Managed", operation="Clone",
                  alive=lambda: True)
    types.MethodType(app.ManagerWindow._release_lock, w)()
    assert w.lock.held is None
    assert reg.by_name("Managed").get("state") != "working"
    assert "released by hand" in prefixlog.tail("Managed")


def test_declining_the_question_keeps_the_lock(window, monkeypatch):
    import AffinityLinuxManager as app
    w, _, _ = window
    monkeypatch.setattr(app.QMessageBox, "question",
                        staticmethod(lambda *a, **k: app.QMessageBox.StandardButton.Cancel))
    w._busy_start("Cloning", 100, prefix="Managed", operation="Clone",
                  alive=lambda: True)
    types.MethodType(app.ManagerWindow._release_lock, w)()
    assert w.lock.held is not None


# -- the list cannot hand its buttons back mid-operation --------------------

def test_a_refresh_during_an_operation_does_not_re_enable_the_list():
    """refresh() calls _selection_changed, so the guard has to live there too
    and not only in _sync_lock_ui."""
    import AffinityLinuxManager as app

    class Button:
        def __init__(self):
            self.enabled = True

        def setEnabled(self, value):
            self.enabled = value

    def must_not_be_reached():
        raise AssertionError("_selection_changed went past the lock guard")

    stub = types.SimpleNamespace(
        lock=oplock.OperationLock(),
        BUSY_BUTTONS=("clone_button", "delete_button"),
        clone_button=Button(),
        delete_button=Button(),
        selected_entry=must_not_be_reached,
    )
    stub.lock.claim("Managed", "Clone")
    types.MethodType(app.ManagerWindow._selection_changed, stub)()
    assert stub.clone_button.enabled is False
    assert stub.delete_button.enabled is False


# -- the footer belongs to the window, not to the list page -----------------

def test_the_status_row_sits_outside_the_stack():
    """Read off the source rather than built, because building the window
    probes the real home. The point is that Setup keeps the status line: a
    status row added to the list page would vanish on the way into it."""
    import AffinityLinuxManager as app
    source = inspect.getsource(app.ManagerWindow._build)
    assert "shell_layout.addWidget(status_row" in source
    assert "middle_layout.addWidget(status_row" not in source
    assert source.index("shell_layout.addWidget(self.stack") < \
           source.index("shell_layout.addWidget(status_row")


# ── a late finish must not release somebody else's lock ────────────────────

def test_a_late_finish_from_another_prefix_releases_nothing(two_prefixes):
    """_busy_prefix is one piece of window state, so without an owner the
    sequence is: prefix A's operation is swept, prefix B takes the lock, A's
    thread finally reaches end_operation -- and releases B's claim mid-clone.
    That is the collision the lock exists to prevent, performed by the lock."""
    w, reg, _ = two_prefixes
    w._busy_start("Cloning Other", 100, prefix="Other", operation="Clone")
    held = w.lock.held

    w._busy_done("Managed — finished", owner="Managed")   # A, arriving late

    assert w.lock.held is held, "another prefix's operation was released"
    assert reg.by_name("Other")["state"] == "working"
    assert w._busy_prefix == "Other"


def test_a_finish_naming_its_own_prefix_still_releases(two_prefixes):
    """The other half, so the test above cannot pass by never releasing."""
    w, _, _ = two_prefixes
    w._busy_start("Cloning Other", 100, prefix="Other", operation="Clone")
    w._busy_done("Other — finished", owner="Other")
    assert w.lock.held is None


# ── one unreadable prefix must not cost the window ─────────────────────────

def test_a_prefix_that_cannot_be_read_does_not_abort_the_probe():
    """iterdir raises for a directory that can be traversed but not listed: a
    prefix installed under sudo, mode 0111, an sshfs mount whose connection
    dropped. Unguarded that left QThread.run and Qt aborted the process -- the
    manager vanished, with no message, because one row could not be measured."""
    import AffinityLinuxManager as app

    thread = app.ProbeThread([{"name": "Broken", "path": "/does/not/matter"},
                              {"name": "Fine", "path": "/also/not"}])
    emitted = []
    thread.done = types.SimpleNamespace(emit=emitted.append)

    def explode(path):
        raise PermissionError(13, "Permission denied")

    original = app.probe.describe
    app.probe.describe = explode
    try:
        thread.run()                      # must not raise
    finally:
        app.probe.describe = original

    assert len(emitted) == 1 and len(emitted[0]) == 2
    entry, info = emitted[0][0]
    assert info["exists"] is False and "Permission denied" in info["unreadable"]
    assert info["size"] == 0


# ── a cached Setup page belongs to the directory it was built for ──────────

def test_a_reused_prefix_name_does_not_reuse_the_old_setup_page(tmp_path):
    """The only guard against installing into the wrong prefix is a check in
    SetupPage's constructor. A page taken from the cache skips the constructor,
    so it skips the guard -- and forget-then-add under the same name is enough
    to get one."""
    import AffinityLinuxManager as app

    built, disposed = [], []

    class FakePage:
        def __init__(self, manager, entry):
            self.name = entry["name"]
            self.path = Path(entry["path"])
            built.append(self.path)

        def dispose(self):
            disposed.append(self.path)

        def deleteLater(self):
            pass

    stub = types.SimpleNamespace(
        _setup_pages={},
        lock=oplock.OperationLock(),
        stack=types.SimpleNamespace(addWidget=lambda w: None,
                                    removeWidget=lambda w: None),
    )
    stub._drop_spare_setup_pages = types.MethodType(
        app.ManagerWindow._drop_spare_setup_pages, stub)
    setup_page = types.MethodType(app.ManagerWindow._setup_page, stub)

    original = app.hosted.SetupPage
    app.hosted.SetupPage = FakePage
    try:
        first = setup_page({"name": "Working", "path": str(tmp_path / "one")})
        again = setup_page({"name": "Working", "path": str(tmp_path / "one")})
        assert again is first, "the cache should still work for the same path"

        moved = setup_page({"name": "Working", "path": str(tmp_path / "two")})
    finally:
        app.hosted.SetupPage = original

    assert moved is not first
    assert moved.path == tmp_path / "two"
    assert disposed == [tmp_path / "one"]


# ── an interrupted clone leaves something to recover ───────────────────────

def test_the_clone_destination_is_recorded_before_the_copy_starts(window):
    """set_working raises KeyError for a prefix the registry does not know,
    and that was every clone: the destination was only added when the copy
    finished. So an interrupted 40GB clone left a partial multi-gigabyte tree
    that nothing knew about -- no working row for the next startup to recover,
    and no row to say the directory sitting there is not a prefix."""
    w, reg, _ = window
    reg.add("Copy of Managed", str(reg.path.parent / "Copy"))

    w._busy_start("Copying", 100, prefix="Copy of Managed", operation="Clone")
    row = reg.by_name("Copy of Managed")
    assert row["state"] == "working" and row["operation"] == "Clone"


def test_recording_failure_is_written_to_the_log_not_swallowed(window):
    w, reg, prefixlog = window
    w._busy_start("Copying", 100, prefix="Nonexistent", operation="Clone")
    assert "Could not record the operation" in prefixlog.tail("Nonexistent")


# -- back to a working Setup, and the settings chosen at creation --------------

def test_the_banner_offers_the_way_back_to_a_working_setup(window):
    """On the list every button that could reopen Setup is disabled while it
    works, so the banner has to carry the way back."""
    w, _, _ = window
    shown = []
    w.lock_show_button = types.SimpleNamespace(setVisible=shown.append)
    w._setup_pages = {"Managed": types.SimpleNamespace(name="Managed", set_actions_enabled=lambda *_: None)}
    w._busy_start("Managed — Setup", 100, prefix="Managed", operation="Setup")
    w._sync_lock_ui(force=True)
    assert shown[-1] is True


def test_no_way_back_is_offered_for_work_that_is_not_a_setup(window):
    w, _, _ = window
    shown = []
    w.lock_show_button = types.SimpleNamespace(setVisible=shown.append)
    w._busy_start("Cleaning Managed", 3, prefix="Managed", operation="Clean")
    w._sync_lock_ui(force=True)
    assert shown[-1] is False


@pytest.fixture
def carry(window, monkeypatch):
    """A prefix created with "Copy from" chosen: the choice is on the entry."""
    import AffinityLinuxManager as app
    from affinity_manager import probe
    w, reg, _ = window
    offered = []
    running = []
    monkeypatch.setattr(probe, "running_pids", lambda p: list(running))
    w.offer_settings_copy = lambda entry, preselect=None: offered.append((entry["name"], preselect)) or True
    w._maybe_offer_carry = types.MethodType(app.ManagerWindow._maybe_offer_carry, w)
    reg.set_carry("Managed", "/somewhere/Old")
    return w, reg, offered, running


def _make_ready(reg, *, wine=True, affinity=True):
    path = Path(reg.by_name("Managed")["path"])
    if wine:
        (path / "dosdevices" / "c:").symlink_to("../drive_c")
    if affinity:
        exe = path / "drive_c/Program Files/Affinity/Affinity/Affinity.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_text("")


def test_the_copy_waits_for_wine_and_for_affinity(carry):
    w, reg, offered, _ = carry
    w._maybe_offer_carry()
    _make_ready(reg, affinity=False)
    w._maybe_offer_carry()
    assert offered == [] and reg.by_name("Managed")["carry_from"] == "/somewhere/Old"


def test_the_copy_is_offered_once_when_the_prefix_is_ready(carry):
    w, reg, offered, _ = carry
    _make_ready(reg)
    w._maybe_offer_carry()
    w._maybe_offer_carry()
    assert offered == [("Managed", Path("/somewhere/Old"))]
    assert "carry_from" not in reg.by_name("Managed")


def test_the_copy_waits_while_affinity_runs_there(carry):
    w, reg, offered, running = carry
    _make_ready(reg)
    running.append(1234)
    w._maybe_offer_carry()
    assert offered == []
    running.clear()
    w._maybe_offer_carry()
    assert offered == [("Managed", Path("/somewhere/Old"))]


def test_the_copy_waits_while_an_operation_holds_the_lock(carry):
    w, reg, offered, _ = carry
    _make_ready(reg)
    w._busy_start("Configuring", 100, prefix="Managed", operation="Configure")
    w._maybe_offer_carry()
    assert offered == []


def test_the_choice_survives_a_restart_of_the_manager(carry, tmp_path):
    from affinity_manager import registry
    w, reg, offered, _ = carry
    reloaded = registry.Registry(reg.path)
    assert reloaded.by_name("Managed")["carry_from"] == "/somewhere/Old"


def test_a_setup_ended_by_the_watchdog_still_offers_the_settings_copy(window, monkeypatch):
    """The installer's flag drops before the page settles, so the watchdog is
    what usually ends a Setup -- and the copy chosen at creation was never offered."""
    w, _, _ = window
    import AffinityLinuxManager as app
    settled = []
    w.setup_settled = settled.append
    w._setup_pages = {"Managed": types.SimpleNamespace(name="Managed", set_actions_enabled=lambda *_: None)}
    running = {"yes": True}
    w._busy_start("Managed — Setup", 100, prefix="Managed", operation="Setup", alive=lambda: running["yes"])
    running["yes"] = False
    monkeypatch.setattr(w.lock, "sweep", lambda: w.lock.held)
    w._lock_tick()
    assert settled == ["Managed"]


def test_a_setup_ended_by_the_watchdog_is_reported_as_finished(window, monkeypatch):
    """The usual end of a hosted installer step, often with the installer's next
    question already on screen: "stopped without reporting a result" read as a failure."""
    w, _, prefixlog = window
    w.setup_settled = lambda *_: None
    w._setup_pages = {"Managed": types.SimpleNamespace(name="Managed", set_actions_enabled=lambda *_: None)}
    running = {"yes": True}
    w._busy_start("Managed — Setup", 100, prefix="Managed", operation="Setup", alive=lambda: running["yes"])
    running["yes"] = False
    monkeypatch.setattr(w.lock, "sweep", lambda: w.lock.held)
    w._lock_tick()
    assert "without reporting" not in prefixlog.tail("Managed")
    assert "finished" in prefixlog.tail("Managed")
