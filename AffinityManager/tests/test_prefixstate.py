"""A badge that cannot lie.

The two cases worth pinning are the ones where the disk and the record
disagree: a prefix that looks complete but whose install was interrupted must
not say Ready, and a prefix marked Working by a manager that is no longer
running must not still say Working.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import prefixstate  # noqa: E402


def facts(**over):
    base = dict(exists=True, is_prefix=True, has_affinity=True,
                affinity_version="3.3.0.4850", wine="ElementalWarrior-wine-11.16",
                wine_builds=["ElementalWarrior-wine-11.16"], running=False, pids=[])
    base.update(over)
    return base


def test_ready_reports_what_is_there(tmp_path):
    s = prefixstate.classify(tmp_path, facts=facts())
    assert s.name == prefixstate.READY
    assert "3.3.0.4850" in s.detail and not s.needs_attention
    assert not s.blocks_operations


def test_missing_directory(tmp_path):
    s = prefixstate.classify(tmp_path / "gone", facts=facts(exists=False))
    assert s.name == prefixstate.MISSING and s.blocks_operations and s.suggestion


def test_a_directory_that_is_not_a_prefix_is_not_told_to_install_affinity(tmp_path):
    s = prefixstate.classify(tmp_path, facts=facts(is_prefix=False))
    assert s.name == prefixstate.NOT_A_PREFIX
    assert "not a prefix" in s.suggestion.lower()


def test_worst_first_no_wine_outranks_no_affinity(tmp_path):
    s = prefixstate.classify(tmp_path, facts=facts(wine_builds=[], has_affinity=False))
    assert s.name == prefixstate.NO_WINE


def test_running_blocks_operations_and_names_the_pid(tmp_path):
    s = prefixstate.classify(tmp_path, facts=facts(running=True, pids=[4242]))
    assert s.name == prefixstate.RUNNING and s.blocks_operations
    assert "4242" in s.detail


def test_an_interrupted_install_does_not_report_ready(tmp_path):
    """The disk can look finished because the operation got most of the way
    through. Saying Ready is the lie this state exists to prevent."""
    entry = {"state": prefixstate.INCOMPLETE, "operation": "Install Affinity"}
    s = prefixstate.classify(tmp_path, entry=entry, facts=facts())
    assert s.name == prefixstate.INCOMPLETE
    assert s.needs_attention and s.last_operation == "Install Affinity"
    assert "did not finish" in s.detail


def test_the_suggestion_fits_the_operation_that_was_interrupted(tmp_path):
    entry = {"state": prefixstate.INCOMPLETE, "operation": "Clone prefix"}
    s = prefixstate.classify(tmp_path, entry=entry, facts=facts())
    assert "partial" in s.suggestion.lower()

    entry = {"state": prefixstate.INCOMPLETE, "operation": "Install Affinity"}
    s = prefixstate.classify(tmp_path, entry=entry,
                             facts=facts(has_affinity=False))
    assert "setup again" in s.suggestion.lower()


def test_working_blocks_operations_and_names_the_operation(tmp_path):
    entry = {"state": prefixstate.WORKING, "operation": "Install Affinity"}
    s = prefixstate.classify(tmp_path, entry=entry, facts=facts())
    assert s.name == prefixstate.WORKING and s.blocks_operations
    assert "Install Affinity" in s.detail


def test_recovery_turns_working_into_incomplete_and_reports_it():
    entries = [
        {"name": "A", "state": prefixstate.WORKING, "operation": "Install Affinity"},
        {"name": "B", "state": prefixstate.READY},
        {"name": "C"},
    ]
    changed = prefixstate.recover_interrupted(entries)
    assert [e["name"] for e in changed] == ["A"]
    assert entries[0]["state"] == prefixstate.INCOMPLETE
    assert entries[0]["operation"] == "Install Affinity"   # kept, for the suggestion
    assert entries[1]["state"] == prefixstate.READY        # untouched
    assert "state" not in entries[2]


def test_recovery_is_idempotent():
    entries = [{"state": prefixstate.WORKING, "operation": "x"}]
    prefixstate.recover_interrupted(entries)
    assert prefixstate.recover_interrupted(entries) == []


def test_the_declared_order_is_the_order_the_function_checks():
    """ORDER is both the display order and the precedence. It shipped
    disagreeing with classify() -- listing NO_WINE above INCOMPLETE while the
    function has always put an unfinished operation first -- so read the real
    order out of the source and pin the two together."""
    import ast
    import inspect

    source = inspect.getsource(prefixstate.classify)
    tree = ast.parse(source.lstrip())
    # ast.walk does not preserve source order, so sort by line -- reading the
    # order wrong would make this test pass against a function that is wrong.
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Call):
            call = node.value
            if getattr(call.func, "id", "") == "State" and call.args:
                first = call.args[0]
                if isinstance(first, ast.Name):
                    found.append((node.lineno, getattr(prefixstate, first.id)))
    checked = [name for _, name in sorted(found)]
    assert checked == list(prefixstate.ORDER), (
        f"classify() checks {checked}\nORDER declares {list(prefixstate.ORDER)}")


def test_a_new_entry_does_not_read_missing(tmp_path):
    """A prefix you have just added has no directory yet. "Missing from disk"
    is true and useless; "not set up yet" is what you want to read."""
    entry = {"state": prefixstate.NEW}
    s = prefixstate.classify(tmp_path / "nothing-here", entry=entry,
                             facts=facts(exists=False, is_prefix=False))
    assert s.name == prefixstate.NEW
    assert s.needs_setup and not s.needs_attention
    assert "setup" in s.suggestion.lower()


def test_new_stops_applying_once_the_prefix_exists(tmp_path):
    """The flag is left on the row; the disk is what stops it being true."""
    entry = {"state": prefixstate.NEW}
    s = prefixstate.classify(tmp_path, entry=entry, facts=facts())
    assert s.name == prefixstate.READY
