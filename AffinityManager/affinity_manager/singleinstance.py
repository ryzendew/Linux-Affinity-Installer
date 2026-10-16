"""One manager at a time, and know what else is already running.

Two copies of the manager means two writers to prefixes.json and two hosted
installers racing for the same package manager. Worse, the old standalone
installer can be started straight from a checkout or a curl pipe, entirely
outside the manager, and it will happily provision a prefix the manager thinks
it owns.

So startup asks three questions and gives three different answers:

    same version already running     REFUSE. It is us; there is nothing to
                                     discuss, and a second copy can only do harm.
    different version running        WARN and let the user decide. Refusing here
                                     would make a half-upgraded machine unusable,
                                     and the user may genuinely be comparing two.
    standalone installer running     WARN, naming the prefix it is working on.
                                     It is not ours to refuse.

The lock is a file holding pid, version and start time. A file rather than an
abstract socket because it survives inspection: when something goes wrong the
user can look at it, and `cat` is a better debugger than a lock nobody can see.
A stale lock -- the pid is gone, or is now some unrelated program -- is taken
over rather than treated as a conflict, because the alternative is an
application that will not start until somebody deletes a file they do not know
about.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from . import registry

REFUSE, WARN, CLEAR = "refuse", "warn", "clear"

INSTALLER_SCRIPT = "AffinityLinuxInstaller.py"


@dataclass
class Conflict:
    action: str              # REFUSE | WARN | CLEAR
    kind: str                # manager | installer | none
    pid: int | None
    version: str | None
    detail: str

    @property
    def may_start(self) -> bool:
        return self.action != REFUSE


def lock_path() -> Path:
    return registry.manager_dir() / "manager.lock"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # someone else's; alive, just not ours to signal
    return True


def _cmdline(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def _prefix_of(pid: int) -> str | None:
    """AFFINITY_INSTALL_DIR out of a process's own environment."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            for entry in f.read().split(b"\0"):
                if entry.startswith(b"AFFINITY_INSTALL_DIR="):
                    return entry.split(b"=", 1)[1].decode("utf-8", "replace")
    except OSError:
        pass
    return None


def read_lock() -> dict | None:
    try:
        data = json.loads(lock_path().read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and data.get("pid") else None


def find_standalone_installer(exclude_pid: int | None = None) -> list[tuple[int, str | None]]:
    """Any AffinityLinuxInstaller.py running as its own process.

    Matched on the command line, which is right here and not the trap it is for
    Affinity.exe: this is a script name that only appears in an argv that is
    actually running it. It cannot match a hosted installer, which has no
    process of its own -- that is the point of hosting it."""
    found = []
    try:
        pids = [int(e) for e in os.listdir("/proc") if e.isdigit()]
    except OSError:
        return found
    for pid in pids:
        if pid == os.getpid() or pid == exclude_pid:
            continue
        line = _cmdline(pid)
        if INSTALLER_SCRIPT in line and "python" in line:
            found.append((pid, _prefix_of(pid)))
    return found


def check(version: str) -> Conflict:
    """What, if anything, is already running. Nothing is written."""
    existing = read_lock()
    if existing:
        pid = int(existing["pid"])
        if _alive(pid) and "python" in _cmdline(pid).lower():
            other = existing.get("version")
            if other == version:
                return Conflict(
                    REFUSE, "manager", pid, other,
                    f"Affinity Linux Manager is already running (pid {pid}). "
                    "Two copies would both write the prefix list and both drive "
                    "the same package manager.",
                )
            return Conflict(
                WARN, "manager", pid, other,
                f"A different version of the manager is running (pid {pid}, "
                f"version {other or 'unknown'}; this is {version}). Starting a "
                "second one risks two writers to the prefix list.",
            )

    standalone = find_standalone_installer()
    if standalone:
        pid, prefix = standalone[0]
        where = f" on {prefix}" if prefix else ""
        return Conflict(
            WARN, "installer", pid, None,
            f"The standalone installer is running (pid {pid}){where}. It works "
            "outside the manager, so operations started here could collide with "
            "it -- both use the system package manager.",
        )

    return Conflict(CLEAR, "none", None, None, "Nothing else is running.")


def acquire(version: str) -> Path:
    """Record that we are running. Call only after check() allowed it."""
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"pid": os.getpid(), "version": version,
               "started": registry._now()}
    tmp = path.with_suffix(".lock.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(path)
    return path


def release() -> None:
    """Give up the lock, but only if it is still ours.

    Checked, because a crashed manager's lock may already have been taken over
    by a later one, and deleting that on the way out would leave the running
    copy unprotected."""
    existing = read_lock()
    if existing and int(existing.get("pid", -1)) == os.getpid():
        try:
            lock_path().unlink()
        except OSError:
            pass
