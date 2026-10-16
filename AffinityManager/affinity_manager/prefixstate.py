"""What condition is a prefix in, and what would fix it?

The manager's list shows one badge per prefix and the setup state offers
different actions depending on it, so "unfinished" has to mean something
specific or the badge is decoration.

Every state below is decided from evidence on disk -- probe.py's questions --
except the two the manager records itself: WORKING, while an operation of ours
is running, and INCOMPLETE, which is what WORKING becomes if we are not running
any more. That second one is the whole reason the state is written down rather
than held in memory: a manager that is killed during an install has to be able
to say, next time it starts, that the install did not finish.

Ordering matters. The states are checked most-broken first, so a prefix missing
its drive_c is NOT_A_PREFIX rather than NO_AFFINITY -- the first true statement
is the most useful one, and "install Affinity into it" is bad advice for a
directory that is not a prefix at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import probe

NEW = "new"
MISSING = "missing"
NOT_A_PREFIX = "not-a-prefix"
NO_WINE = "no-wine"
NO_AFFINITY = "no-affinity"
INCOMPLETE = "incomplete"
WORKING = "working"
RUNNING = "running"
READY = "ready"

# Worst first, and this must be the order classify() checks in -- it is the
# display order and the precedence, and the two disagreeing is how a badge ends
# up not matching the reason underneath it. It shipped disagreeing: this listed
# NO_WINE and NO_AFFINITY above INCOMPLETE and WORKING while the function has
# always put the unfinished-operation states first, on purpose. test_prefixstate
# now reads the order out of the function and pins them together.
ORDER = (NEW, MISSING, NOT_A_PREFIX, INCOMPLETE, WORKING, NO_WINE, NO_AFFINITY,
         RUNNING, READY)

LABELS = {
    NEW: "Not set up yet",
    MISSING: "Missing",
    NOT_A_PREFIX: "Not a Wine prefix",
    NO_WINE: "No Wine build",
    NO_AFFINITY: "Affinity not installed",
    INCOMPLETE: "Unfinished",
    WORKING: "Working",
    RUNNING: "Running",
    READY: "Ready",
}

# Whether an operation may be started against a prefix in this state at all.
BLOCKS_OPERATIONS = {MISSING, RUNNING, WORKING}

# Wanting attention is not the same as being broken: a new prefix needs setting
# up, which is the next thing to do rather than something that went wrong.
NEEDS_SETUP = {NEW, NO_WINE, NO_AFFINITY}


@dataclass
class State:
    name: str
    label: str
    detail: str
    suggestion: str | None = None      # what would fix it, when anything would
    last_operation: str | None = None  # the operation that did not finish

    @property
    def blocks_operations(self) -> bool:
        return self.name in BLOCKS_OPERATIONS

    @property
    def needs_attention(self) -> bool:
        return self.name in (MISSING, NOT_A_PREFIX, NO_WINE, NO_AFFINITY, INCOMPLETE)

    @property
    def needs_setup(self) -> bool:
        return self.name in NEEDS_SETUP


def classify(prefix, *, entry: dict | None = None, facts: dict | None = None) -> State:
    """The condition of one prefix.

    `entry` is its registry row, which is where WORKING and INCOMPLETE come
    from; `facts` is a probe.describe() result, accepted so a caller refreshing
    a whole list pays for one pass per prefix rather than two."""
    path = Path(prefix).expanduser()
    facts = facts if facts is not None else probe.describe(path)
    entry = entry or {}
    operation = entry.get("operation")

    # Before MISSING, because "you added this and have not set it up" is more
    # useful than "there is nothing there" -- both true, one worth reading.
    if entry.get("state") == NEW and not facts.get("is_prefix"):
        return State(NEW, LABELS[NEW],
                     "Added to the list, but nothing has been installed into it yet.",
                     "Run setup to create the prefix and install Affinity.")

    if not facts.get("exists"):
        return State(MISSING, LABELS[MISSING],
                     f"Nothing at {path}.",
                     "Remove it from the list, or point the entry at where it moved to.")

    if not facts.get("is_prefix"):
        return State(NOT_A_PREFIX, LABELS[NOT_A_PREFIX],
                     f"{path} has no drive_c and dosdevices.",
                     "Set it up as a new prefix, or remove it from the list. "
                     "Nothing here will install into a directory that is not a prefix.")

    # An unfinished operation outranks what is on disk: the disk may look
    # complete because the operation got most of the way through, and saying
    # "Ready" about a prefix whose install was interrupted is the lie this
    # state exists to prevent.
    if entry.get("state") == INCOMPLETE:
        return State(INCOMPLETE, LABELS[INCOMPLETE],
                     _interrupted_detail(operation),
                     _interrupted_suggestion(operation, facts),
                     last_operation=operation)

    if entry.get("state") == WORKING:
        return State(WORKING, LABELS[WORKING],
                     f"{operation or 'An operation'} is running.",
                     None, last_operation=operation)

    if not facts.get("wine_builds"):
        return State(NO_WINE, LABELS[NO_WINE],
                     "The prefix has no Wine build in it.",
                     "Run setup: it installs a Wine build into the prefix.")

    if not facts.get("has_affinity"):
        return State(NO_AFFINITY, LABELS[NO_AFFINITY],
                     "Wine is here but Affinity is not installed.",
                     "Run setup and give it the Affinity installer.")

    if facts.get("running"):
        pids = facts.get("pids") or []
        return State(RUNNING, LABELS[RUNNING],
                     f"Affinity is running (pid {pids[0]})." if pids
                     else "Affinity is running.",
                     "Close Affinity before changing anything in this prefix.")

    version = facts.get("affinity_version")
    wine = facts.get("wine")
    return State(READY, LABELS[READY],
                 " · ".join(p for p in (
                     f"Affinity {version}" if version else "Affinity installed",
                     f"Wine {wine}" if wine else None) if p))


def _interrupted_detail(operation: str | None) -> str:
    what = operation or "An operation"
    return f"{what} was interrupted and did not finish."


def _interrupted_suggestion(operation: str | None, facts: dict) -> str:
    """Say something useful, and only when there is something useful to say.

    A wrong suggestion is worse than none: "run setup again" is right for an
    interrupted install and wrong for an interrupted clone, where the half-copy
    is the thing to deal with first."""
    op = (operation or "").lower()
    if "clone" in op or "copy" in op:
        return ("The copy is probably partial. Remove the destination and clone "
                "again rather than using it.")
    if "clean" in op or "remove" in op:
        return ("Some of what was selected may still be there. Open Clean again "
                "to see what is left.")
    if not facts.get("wine_builds"):
        return "No Wine build arrived. Run setup again; it will start over."
    if not facts.get("has_affinity"):
        return "Wine is installed but Affinity is not. Run setup again to finish."
    return ("Everything expected is present, so it may have finished after all. "
            "Run setup to check, or launch it and see.")


def recover_interrupted(entries) -> list[dict]:
    """Turn every WORKING row into INCOMPLETE. Call once, at startup.

    If a row still says WORKING when the manager starts, the manager that wrote
    it is gone -- single-instance startup has already established that no other
    copy is running -- so the operation it was tracking cannot still be going.
    Returns the rows that changed, so the caller can tell the user rather than
    fixing it silently."""
    changed = []
    for entry in entries:
        if entry.get("state") == WORKING:
            entry["state"] = INCOMPLETE
            changed.append(entry)
    return changed
