"""An operation is recorded before it starts, and cleared when it ends.

_busy_start / _busy_step / _busy_done are the manager's own choke point, so the
durable record hangs off them rather than off each operation. Tested against
the real methods with a stand-in for the Qt parts -- the logic under test is
the bookkeeping, not the widgets.

The stand-in is the `window` fixture in conftest.py. The operation lock, which
hangs off the same methods, is tested in test_manager_lock.py.
"""


def test_the_record_exists_before_the_work_does(window):
    w, reg, _ = window
    w._busy_start("Cleaning Managed", 3, prefix="Managed", operation="Clean")
    row = reg.by_name("Managed")
    assert row["state"] == "working" and row["operation"] == "Clean"
    assert row["log"] and "log_offset" in row


def test_finishing_clears_it(window):
    w, reg, _ = window
    w._busy_start("Cleaning", 1, prefix="Managed", operation="Clean")
    w._busy_done("Done")
    row = reg.by_name("Managed")
    assert "state" not in row and "operation" not in row


def test_an_interrupted_operation_survives_as_incomplete(window):
    """_busy_done is never reached. That is the case the record exists for."""
    from affinity_manager import prefixstate, registry
    w, reg, plog = window
    w._busy_start("Cleaning", 3, prefix="Managed", operation="Clean")
    w._busy_step(1, "removing wine-11.12")
    w._busy_step(2, "removing an old archive")

    fresh = registry.Registry(reg.path)
    assert fresh.recover()
    row = fresh.by_name("Managed")
    assert row["state"] == "incomplete" and row["operation"] == "Clean"

    written = plog.read_from("Managed", row["log_offset"])
    assert "Clean" in written and "removing wine-11.12" in written

    condition = prefixstate.classify(row["path"], entry=row)
    assert condition.name == prefixstate.INCOMPLETE
    assert "left" in condition.suggestion.lower() or "Clean" in condition.suggestion


def test_progress_messages_go_to_that_prefix_and_no_other(window):
    w, reg, plog = window
    reg.entries.append({"name": "Other", "path": "/tmp/other"})
    reg.save()
    w._busy_start("Cleaning", 2, prefix="Managed", operation="Clean")
    w._busy_step(1, "a message about Managed")
    w._busy_done("Done")
    assert "a message about Managed" in plog.tail("Managed")
    assert "a message about Managed" not in plog.tail("Other")


def test_an_operation_with_no_prefix_records_nothing(window):
    """Not everything the manager does belongs to one prefix."""
    w, reg, _ = window
    w._busy_start("Scanning for installations")
    w._busy_done("Found 3")
    assert "state" not in reg.by_name("Managed")


def test_bookkeeping_failure_does_not_stop_the_work(window, monkeypatch):
    w, reg, _ = window
    monkeypatch.setattr(reg, "set_working",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")))
    w._busy_start("Cleaning", 1, prefix="Managed", operation="Clean")
    w._busy_done("Done")
