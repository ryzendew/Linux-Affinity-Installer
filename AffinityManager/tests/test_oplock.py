"""One operation at a time.

The interesting cases are the refusals and the non-refusals: a lock that lets
a second claim through has failed, and so has one that releases itself because
nobody happened to be watching.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import oplock  # noqa: E402


@pytest.fixture
def clock(monkeypatch):
    """A monotonic clock that only moves when the test says so."""
    now = {"t": 1000.0}
    monkeypatch.setattr(oplock, "_now", lambda: now["t"])
    return lambda seconds: now.__setitem__("t", now["t"] + seconds)


# -- claiming ---------------------------------------------------------------

def test_a_claim_is_held():
    lock = oplock.OperationLock()
    op = lock.claim("3.3 Test", "Install Affinity")
    assert lock.held is op and op.prefix == "3.3 Test"


def test_a_second_claim_is_refused_and_names_the_first():
    lock = oplock.OperationLock()
    lock.claim("3.3 Test", "Install Affinity")
    with pytest.raises(oplock.InUse) as caught:
        lock.claim("Working", "Clean")
    assert caught.value.operation.prefix == "3.3 Test"
    assert "Install Affinity" in str(caught.value)


def test_the_same_prefix_is_refused_too():
    """No same-prefix exemption: a clone reading what a clean is deleting from
    is the collision in its purest form."""
    lock = oplock.OperationLock()
    lock.claim("Working", "Clone")
    with pytest.raises(oplock.InUse):
        lock.claim("Working", "Clean")


def test_in_use_is_catchable_as_exception():
    """PyQt6 calls qFatal() on an exception that escapes a slot, so this must
    not be a bare BaseException -- a refusal would abort the process."""
    assert issubclass(oplock.InUse, Exception)


# -- releasing --------------------------------------------------------------

def test_release_gives_back_what_it_released():
    lock = oplock.OperationLock()
    lock.claim("Working", "Clean")
    released = lock.release()
    assert released.label == "Clean" and lock.held is None


def test_releasing_somebody_elses_lock_releases_nothing():
    lock = oplock.OperationLock()
    lock.claim("Working", "Clean")
    assert lock.release("3.3 Test") is None
    assert lock.held is not None


def test_releasing_when_nothing_is_held_is_not_an_error():
    """The common caller is a finally on a path that may not have claimed."""
    assert oplock.OperationLock().release("Working") is None


# -- the watchdog -----------------------------------------------------------

def test_sweep_leaves_alone_what_nobody_vouched_for(clock):
    """No oracle means no opinion, and no opinion means still running. A lock
    that opens itself on silence is not a lock."""
    lock = oplock.OperationLock()
    lock.claim("Working", "Clean")
    clock(3600)
    assert lock.sweep() is None and lock.held is not None


def test_sweep_releases_an_operation_whose_thread_has_stopped(clock):
    lock = oplock.OperationLock()
    running = {"yes": True}
    lock.claim("3.3 Test", "Install", alive=lambda: running["yes"])
    clock(oplock.OperationLock.SWEEP_GRACE)
    assert lock.sweep() is None           # still going
    running["yes"] = False
    swept = lock.sweep()
    assert swept is not None and swept.label == "Install"
    assert lock.held is None


def test_an_oracle_that_raises_counts_as_finished(clock):
    """Qt deletes the C++ side of a finished QThread; isRunning then raises."""
    def gone():
        raise RuntimeError("wrapped C/C++ object has been deleted")

    lock = oplock.OperationLock()
    lock.claim("3.3 Test", "Install", alive=gone)
    clock(oplock.OperationLock.SWEEP_GRACE)
    assert lock.sweep() is not None and lock.held is None


def test_a_thread_claimed_for_but_not_yet_started_is_not_swept(clock):
    """claim() comes before start() -- the alternative is beginning work the
    lock might refuse -- and isRunning() is False in between.

    Takes the clock fixture. Without it this read the real monotonic clock and
    passed only because SWEEP_GRACE had not elapsed in the microseconds since
    the claim: a true statement about the machine, not about the code, and one
    that would have gone green with the grace deleted."""
    lock = oplock.OperationLock()
    lock.claim("3.3 Test", "Install", alive=lambda: False)
    assert lock.sweep() is None and lock.held is not None
    clock(oplock.OperationLock.SWEEP_GRACE - 1)
    assert lock.sweep() is None, "swept before the grace was up"
    clock(2)
    assert lock.sweep() is not None, "the grace never expires"


# -- what the pages are told ------------------------------------------------

def test_no_caution_when_nothing_is_running():
    assert oplock.OperationLock().caution_for("Working") is None


def test_no_caution_on_the_page_that_owns_the_operation():
    lock = oplock.OperationLock()
    lock.claim("Working", "Clean")
    assert lock.caution_for("Working") is None


def test_the_caution_names_the_other_prefix_and_its_operation():
    lock = oplock.OperationLock()
    lock.claim("3.3 Test", "Install Affinity")
    text = lock.caution_for("Working")
    assert "3.3 Test" in text and "Install Affinity" in text
    assert "unavailable" in text


def test_a_long_operation_offers_the_escape_hatch(clock):
    lock = oplock.OperationLock()
    lock.claim("3.3 Test", "Install Affinity")
    assert "release it" not in lock.caution_for("Working")
    clock(oplock.OperationLock.LONG_SECONDS)
    assert "release it" in lock.caution_for("Working")


def test_status_is_for_the_owning_page_only():
    lock = oplock.OperationLock()
    lock.claim("Working", "Clean")
    assert lock.status_for("Working").startswith("Clean")
    assert lock.status_for("3.3 Test") is None


# -- elapsed ----------------------------------------------------------------

def test_elapsed_crosses_the_minute(clock):
    lock = oplock.OperationLock()
    op = lock.claim("Working", "Clean")
    assert op.elapsed == "0s"
    clock(59)
    assert op.elapsed == "59s"
    clock(1)
    assert op.elapsed == "1m 00s"
    clock(125)
    assert op.elapsed == "3m 05s"


# -- reentrancy and threads -------------------------------------------------

def test_hold_keeps_a_claim_the_same_prefix_already_has():
    """The installer's operations nest: _one_click_setup_thread claims, then
    calls setup_wine, whose first statement claims again. claim() refused that
    and killed the worker thread."""
    lock = oplock.OperationLock()
    first = lock.hold("3.3 Test", "One-Click Full Setup")
    again = lock.hold("3.3 Test", "Setting up Wine environment")
    assert again is first
    assert lock.held.label == "Setting up Wine environment"


def test_hold_still_refuses_another_prefix():
    lock = oplock.OperationLock()
    lock.hold("3.3 Test", "Install")
    with pytest.raises(oplock.InUse):
        lock.hold("Working", "Clean")


def test_hold_updates_the_oracle_when_one_is_given():
    lock = oplock.OperationLock()
    lock.hold("3.3 Test", "One-Click", alive=lambda: True)
    lock.hold("3.3 Test", "Setup Wine", alive=lambda: False)
    assert lock.held.finished() is True


def test_only_one_of_many_threads_gets_the_lock():
    """The hosted installer claims from its own worker threads. An
    unsynchronised "if free then take" is a race with exactly the outcome this
    class exists to prevent."""
    import threading

    lock = oplock.OperationLock()
    winners, barrier = [], threading.Barrier(8)

    def contend(n):
        barrier.wait()
        try:
            lock.claim("prefix-%d" % n, "Install")
            winners.append(n)
        except oplock.InUse:
            pass

    threads = [threading.Thread(target=contend, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(winners) == 1
