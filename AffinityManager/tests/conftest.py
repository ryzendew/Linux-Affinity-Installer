"""A ManagerWindow with the Qt taken out.

Several things worth testing hang off _busy_start / _busy_step / _busy_done --
the durable operation record, and the operation lock -- and all of them are
bookkeeping rather than painting. Building the real window to reach them would
mean probing the real home directory and starting real threads, so the methods
are bound to a stand-in instead: real code, real registry, real lock, stubs
only where a widget would be.
"""
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from affinity_manager import oplock, prefixlog, registry
    monkeypatch.setattr(registry, "manager_dir", lambda: tmp_path)

    import AffinityLinuxManager as app
    monkeypatch.setattr(app.QApplication, "processEvents", staticmethod(lambda *a: None))

    managed = tmp_path / "Managed"
    (managed / "drive_c").mkdir(parents=True)
    (managed / "dosdevices").mkdir(parents=True)
    reg = registry.Registry(tmp_path / "prefixes.json")
    reg.entries = [{"name": "Managed", "path": str(managed)}]
    reg.save()

    # The lock is real -- it is in-process and has no Qt in it, so there is
    # nothing to stand in for. The caution row is not: a QWidget here would
    # drag the whole window in, and what these tests are about is the
    # bookkeeping.
    shown = []
    w = types.SimpleNamespace(
        reg=reg,
        lock=oplock.OperationLock(),
        lock_row=types.SimpleNamespace(show=lambda: shown.append(True),
                                       hide=lambda: shown.append(False)),
        lock_banner=types.SimpleNamespace(setText=lambda *_: None),
        status=types.SimpleNamespace(setText=lambda *_: None),
        progress=types.SimpleNamespace(
            setRange=lambda *_: None, setValue=lambda *_: None,
            show=lambda: None, hide=lambda: None, maximum=lambda: 0),
        BUSY_BUTTONS=(),
        _setup_pages={},
        current_prefix=lambda: None,
        _selection_changed=lambda: None,
        refresh=lambda: None,
    )
    for name in ("_busy_start", "_busy_step", "_busy_progress", "_show_step",
                 "_busy_done", "_sync_lock_ui", "_lock_tick"):
        setattr(w, name, types.MethodType(getattr(app.ManagerWindow, name), w))
    return w, reg, prefixlog
