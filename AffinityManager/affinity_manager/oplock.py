"""One operation at a time, across every prefix.

Not a preference. Provisioning a prefix runs the distro package manager --
pacman, apt, dnf, zypper -- and those take a system-wide lock, so two prefixes
installing at once collide there whatever this application thinks. winetricks
and `wineserver -k` are no better behaved, and two wineservers started a second
apart will fight over the same ~/.cache entries. A warning that two things are
happening would be describing a problem rather than preventing it.

So there is one lock, held by name, and every mutating action passes through
it. Entering another prefix's Setup page while it is held is still allowed --
looking is not doing -- but the page carries a line saying who is working and
its action buttons are disabled.

The lock lives in memory and that is deliberate. singleinstance has already
established that exactly one manager process is running, so an in-process lock
is sufficient, and a lock file would be a second source of truth free to
disagree with the first. What survives a crash is not this: it is the registry
row written before the work starts, which answers a different question. This
one answers "is anything running now"; that one answers "what was running when
the lights went out".

In memory, but not in one thread. The hosted installer calls into this from its
own worker threads -- _one_click_setup_thread's first statement is a claim --
so every method that reads or writes the held operation takes a mutex. An
unsynchronised "if free then take" is a race with exactly the outcome this
class exists to prevent.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional


def _now() -> float:
    """One place decides what "now" means.

    A dataclass field's default_factory captures the function object when the
    class is created, so it has to be called through a lambda below or the
    field would hold whatever this name meant at import and never look again.
    Going through a module-level function keeps the indirection in one spot,
    and keeps a substitute clock local to this module rather than patching the
    time module out from under everything else in the process."""
    return time.monotonic()


class InUse(Exception):
    """Refused: something else holds the lock.

    Named InUse rather than Busy because maintenance.Busy already means
    something quite different -- that a prefix has live Wine processes in it --
    and the two would sit next to each other in the same except clauses.

    An ordinary Exception, deliberately, and the cost of that is real: the
    installer's `_handle_button_click` wraps every command in
    `except Exception` and turns it into a log line, so a refusal raised
    beneath one IS absorbed there. The alternative is worse. PyQt6 calls
    qFatal() on an exception that escapes a slot, so a BaseException would
    abort the process mid-install rather than decline a click.

    What stops the absorption mattering is that the hosted page shows the
    refusal itself -- SetupPage.operation_started calls show_message before
    re-raising -- so the user is told even when the log line is all that
    survives. An earlier version of this docstring claimed the swallowing could
    not happen at all, which was simply untrue."""

    def __init__(self, operation: "Operation"):
        super().__init__(str(operation))
        self.operation = operation


@dataclass
class Operation:
    """What is running, where, and since when."""

    prefix: str
    label: str
    source: str = "manager"          # manager | setup
    started: float = field(default_factory=lambda: _now())

    # Optional liveness oracle -- typically a QThread's isRunning. The lock
    # never calls it on its own; sweep() does, on the timer that drives the
    # caution line. None means "no opinion", which is read as still running:
    # a lock that releases itself because nobody vouched for it would be no
    # lock at all.
    alive: Optional[Callable[[], bool]] = None

    @property
    def seconds(self) -> int:
        return int(_now() - self.started)

    @property
    def elapsed(self) -> str:
        s = self.seconds
        if s < 60:
            return "%ds" % s
        return "%dm %02ds" % (s // 60, s % 60)

    def finished(self) -> bool:
        """Has the work behind this operation stopped?

        Only ever True when something vouched for it. An operation with no
        oracle is presumed to be running for as long as it is held."""
        if self.alive is None:
            return False
        try:
            return not self.alive()
        except Exception:
            # A dead QThread can raise RuntimeError on isRunning once Qt has
            # deleted the C++ side. That is itself an answer: it is finished.
            return True

    def __str__(self) -> str:
        return "%s on %s (%s)" % (self.label, self.prefix, self.elapsed)


class OperationLock:
    """The single claim, and the things the UI needs to say about it."""

    # How long an operation may run before the caution line stops implying
    # patience and starts offering the escape hatch. Not a timeout: nothing is
    # cancelled at this mark, it only changes what the user is told. A first
    # install genuinely takes this long on a slow link, which is why the number
    # is generous and why nothing automatic happens when it passes.
    LONG_SECONDS = 20 * 60

    # How long an operation is left alone before the watchdog will believe an
    # oracle that says it has finished. A QThread is claimed for before it is
    # started -- the alternative is starting work the lock might refuse -- and
    # isRunning() is False in the gap between the two, so without this a sweep
    # landing in that gap would release a lock whose work is about to begin.
    # Seconds, because the gap is microseconds and nothing is waiting on this.
    SWEEP_GRACE = 5

    def __init__(self):
        self._held: Operation | None = None
        # Reentrant, because hold() calls claim() while already inside it.
        self._mutex = threading.RLock()

    @property
    def held(self) -> Operation | None:
        with self._mutex:
            return self._held

    def claim(self, prefix: str, label: str, source: str = "manager",
              alive: Optional[Callable[[], bool]] = None) -> Operation:
        """Take the lock, or raise InUse naming what already has it.

        Re-claiming for the prefix that already holds it is still a refusal.
        Two operations on one prefix is the collision this prevents in its
        purest form -- a clone reading a tree that a clean is deleting from --
        so there is no same-prefix exemption."""
        with self._mutex:
            if self._held is not None:
                raise InUse(self._held)
            self._held = Operation(prefix, label, source, alive=alive)
            return self._held

    def hold(self, prefix: str, label: str, source: str = "setup",
             alive: Optional[Callable[[], bool]] = None) -> Operation:
        """Claim, or keep a claim this prefix already has.

        The reentrant door, and it exists because the installer's operations
        nest. _one_click_setup_thread calls start_operation and then calls
        setup_wine, whose own first statement is another start_operation. With
        claim() that second call raised InUse naming the prefix's own
        operation, killing the worker thread: One-Click Full Setup could never
        install Wine inside the manager.

        Counting the nesting instead was the obvious alternative and does not
        work -- the installer's starts and ends are not balanced; one method
        has one start and eleven ends. So this asks a question that needs no
        bookkeeping: is the lock already ours? If it is, relabel it and carry
        on. Another prefix still gets InUse, which is the case the lock is
        for."""
        with self._mutex:
            current = self._held
            if current is not None and current.prefix == prefix:
                current.label = label
                if alive is not None:
                    current.alive = alive
                return current
            return self.claim(prefix, label, source, alive=alive)

    def release(self, prefix: str | None = None) -> Operation | None:
        """Give it up, and say what was given up.

        Naming the prefix is optional but checked when given. Releasing a lock
        somebody else holds would let two operations run each believing it had
        it, which is exactly the failure this class exists to prevent, so a
        mismatch releases nothing and returns None rather than raising: the
        common caller is a `finally` on a path that may or may not have
        claimed, and it should not have to remember which."""
        with self._mutex:
            current = self._held
            if current is None:
                return None
            if prefix is not None and current.prefix != prefix:
                return None
            self._held = None
            return current

    def sweep(self) -> Operation | None:
        """Release a claim whose work has demonstrably stopped.

        The watchdog. Every release ought to be explicit, and in the manager's
        own code it is -- _busy_done releases what _busy_start claimed. The
        hosted installer is the reason this exists: its commands start daemon
        threads and return at once, so the release has to wait on the thread
        rather than on the click, and a thread that dies on an unhandled
        exception never reaches the code that would release.

        Only an operation that vouched for itself can be swept, and only once
        it is past SWEEP_GRACE; see Operation.finished. Returns what was released, so the caller can say so
        rather than having the lock silently open."""
        with self._mutex:
            current = self._held
            if current is None or current.seconds < self.SWEEP_GRACE:
                return None
            if not current.finished():
                return None
            self._held = None
            return current

    def caution_for(self, prefix: str) -> str | None:
        """What to say on another prefix's page while this is held.

        None when there is nothing to say -- either nothing is running, or what
        is running belongs to the prefix being looked at, in which case it is
        not a caution about somebody else but that page's own status line."""
        current = self.held
        if current is None or current.prefix == prefix:
            return None
        tail = ("Only one prefix can be worked on at a time, so actions here "
                "are unavailable until it finishes.")
        if current.seconds >= self.LONG_SECONDS:
            tail += (" If you are certain it has stopped, release it from the "
                     "prefix list.")
        return "%s is running on %s (%s). %s" % (
            current.label, current.prefix, current.elapsed, tail)

    def status_for(self, prefix: str) -> str | None:
        """The same fact, phrased for the page that owns the operation.

        The Setup page and the prefix list share one status bar, so both need a
        line; they need different ones. 'Installing (4m 12s)' belongs to the
        prefix doing it, and caution_for's 'actions are unavailable' does
        not."""
        current = self.held
        if current is None or current.prefix != prefix:
            return None
        return "%s (%s)" % (current.label, current.elapsed)
