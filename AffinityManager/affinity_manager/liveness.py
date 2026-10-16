"""What is actually running in a prefix -- and what is only left behind.

"Is anything running?" was answered by asking whether any process had this
prefix as its WINEPREFIX, and whether any command line mentioned Affinity.exe or
AffinityHook. Both say yes about leftovers. On the working prefix this was
written against, Affinity had been closed for two weeks, and the manager still
called it running, because of:

  - two AffinityHook.exe launchers from earlier sessions, each with its own
    crash handler and full set of Wine background services;
  - a third set of Wine services from another session;
  - a diagnostic program left running;
  - and no wineserver at all. Their server had gone, so they were stuck --
    doing nothing, and never going to exit by themselves.

So every process in a prefix is put in one of four groups, and only the first
means Affinity is running:

  AFFINITY   Affinity.exe -- and an AffinityHook.exe young enough to be in the
             middle of starting it, since for the first few seconds of a launch
             the hook is all there is, and a second launch then would kill the
             first.
  HOOK       an AffinityHook.exe with no Affinity.exe to look after, older than
             that. Left behind by a session that is over.
  SERVICE    Wine's own background programs: services, explorer, svchost,
             plugplay, rpcss, winedevice, conhost, crashpad. They exist for a
             program and go when it does -- unless the program went badly.
  OTHER      any other Windows program: winecfg, an installer, a tool.

Read from /proc and nothing else, so it is cheap enough to ask every second.
"""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path

AFFINITY = "affinity"
HOOK = "hook"
SERVICE = "service"
OTHER = "other"
SERVER = "server"

RUNNING = "running"        # Affinity is running
LEFTOVERS = "leftovers"    # Affinity is not, but other Wine processes are
QUIET = "quiet"            # nothing at all

# How long a launcher may stand alone before it counts as left behind. A cold
# start of Affinity 3 takes up to a minute before Affinity.exe exists; the
# handler's own startup grace is 75 seconds.
HOOK_GRACE_SECONDS = 120

# /proc/<pid>/comm is cut at 15 characters, so these are as comm spells them.
SERVICE_NAMES = frozenset({
    "services.exe", "explorer.exe", "svchost.exe", "plugplay.exe", "rpcss.exe",
    "winedevice.exe", "conhost.exe", "crashpad_handle", "start.exe",
    "winemenubuilder", "wineboot.exe", "tabtip.exe", "rundll32.exe",
})
FRIENDLY = {
    "crashpad_handle": "crashpad_handler",
    "AffinityHook.ex": "AffinityHook.exe",
    "winemenubuilder": "winemenubuilder.exe",
}


@dataclass
class Proc:
    pid: int
    comm: str
    started: float          # epoch seconds
    group: str

    @property
    def name(self) -> str:
        return FRIENDLY.get(self.comm, self.comm)

    @property
    def age(self) -> float:
        return max(0.0, time.time() - self.started)

    def when(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.started))


@dataclass
class Activity:
    prefix: str
    procs: list = field(default_factory=list)

    def of(self, group) -> list:
        return [p for p in self.procs if p.group == group]

    @property
    def state(self) -> str:
        if self.of(AFFINITY):
            return RUNNING
        return LEFTOVERS if self.procs else QUIET

    @property
    def leftovers(self) -> list:
        return [p for p in self.procs if p.group != AFFINITY]

    @property
    def orphaned(self) -> bool:
        """Wine programs with no wineserver: stuck, and never exiting alone."""
        return bool(self.procs) and not self.of(SERVER)

    @property
    def running_pids(self) -> list:
        return sorted(p.pid for p in self.of(AFFINITY))

    def summary(self) -> str:
        """One sentence for a banner: what is there, and since when."""
        if self.state == QUIET:
            return "Nothing is running in this prefix."
        if self.state == RUNNING:
            first = min(self.of(AFFINITY), key=lambda p: p.started)
            return f"Affinity is running (pid {first.pid}, started {first.when()})."
        parts = []
        hooks, services, others = self.of(HOOK), self.of(SERVICE), self.of(OTHER)
        def count(n, one, many):
            return f"{n} {one if n == 1 else many}"
        if hooks:
            parts.append(count(len(hooks), "Affinity launcher", "Affinity launchers"))
        if services:
            parts.append(count(len(services), "Wine background process",
                               "Wine background processes"))
        if others:
            parts.append(", ".join(sorted({p.name for p in others})))
        oldest = min(self.leftovers, key=lambda p: p.started)
        text = ("Affinity is not running, but processes from earlier sessions "
                f"are still here: {'; '.join(parts)}. The oldest has been there "
                f"since {oldest.when()}.")
        if self.orphaned:
            text += (" Their wineserver has gone, so they are stuck and will "
                     "not exit by themselves.")
        return text


def _realpath(path) -> str:
    try:
        return os.path.realpath(os.path.expanduser(str(path)))
    except (OSError, ValueError):
        return ""


def _boot_time(proc: Path) -> float:
    try:
        for line in (proc / "stat").read_text().splitlines():
            if line.startswith("btime "):
                return float(line.split()[1])
    except (OSError, ValueError):
        pass
    return 0.0


def _start_time(entry: Path, boot: float, ticks: int) -> float:
    """Epoch seconds a process started, from field 22 of /proc/<pid>/stat."""
    try:
        raw = (entry / "stat").read_text()
        # comm is in parentheses and may contain spaces; fields follow the last ")".
        fields = raw[raw.rindex(")") + 2:].split()
        return boot + int(fields[19]) / ticks
    except (OSError, ValueError, IndexError):
        return time.time()


def _group(comm: str) -> str:
    if comm == "Affinity.exe":
        return AFFINITY
    if comm.startswith("AffinityHook"):
        return HOOK
    if comm == "wineserver":
        return SERVER
    if comm in SERVICE_NAMES:
        return SERVICE
    return OTHER


def scan(prefix, proc_root="/proc") -> Activity:
    """Every process whose own WINEPREFIX is this prefix, grouped.

    Matched on each process's environment rather than its command line: a
    command-line match also finds the shell that is doing the searching, and a
    substring match on the path finds a prefix whose name contains another's."""
    target = _realpath(prefix)
    proc = Path(proc_root)
    boot = _boot_time(proc)
    try:
        ticks = os.sysconf("SC_CLK_TCK")
    except (ValueError, OSError):
        ticks = 100
    activity = Activity(str(prefix))
    if not target:
        return activity
    try:
        entries = [e for e in proc.iterdir() if e.name.isdigit()]
    except OSError:
        return activity
    for entry in entries:
        try:
            environ = (entry / "environ").read_bytes()
        except OSError:
            continue
        value = None
        for item in environ.split(b"\0"):
            if item.startswith(b"WINEPREFIX="):
                value = item[len(b"WINEPREFIX="):].decode("utf-8", "replace")
                break
        if value is None or _realpath(value) != target:
            continue
        try:
            comm = (entry / "comm").read_text().strip()
        except OSError:
            continue
        activity.procs.append(Proc(int(entry.name), comm,
                                   _start_time(entry, boot, ticks), _group(comm)))

    # A launcher is part of a live start for its first couple of minutes,
    # whether or not Affinity.exe has appeared yet.
    for p in activity.procs:
        if p.group == HOOK and p.age < HOOK_GRACE_SECONDS:
            p.group = AFFINITY
    activity.procs.sort(key=lambda p: p.started)
    return activity


class StillRunning(RuntimeError):
    pass


def end_leftovers(prefix, *, include_affinity=False, grace=3.0,
                  proc_root="/proc", kill=os.kill, sleep=time.sleep) -> list[str]:
    """End the Wine processes left behind in one prefix. Returns what happened.

    Scanned again at the moment of ending, not trusted from whatever the
    caller showed the user: Affinity may have been started in between, and
    ending it would lose whatever is open in it. Unless include_affinity is
    given -- the user's explicit choice, for a shutdown that has hung -- an
    Affinity process found now stops everything.

    SIGTERM first, then SIGKILL for whatever is still there after `grace`
    seconds. Nothing outside this prefix is touched: every pid comes from a
    scan matched on that process's own WINEPREFIX."""
    activity = scan(prefix, proc_root)
    if activity.state == RUNNING and not include_affinity:
        raise StillRunning(activity.summary())
    targets = activity.procs if include_affinity else activity.leftovers
    notes = []
    for p in targets:
        try:
            kill(p.pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except PermissionError as exc:
            notes.append(f"could not end {p.name} (pid {p.pid}): {exc}")
    if targets:
        sleep(grace)
    remaining = {p.pid for p in scan(prefix, proc_root).procs}
    for p in targets:
        if p.pid not in remaining:
            notes.append(f"ended {p.name} (pid {p.pid}, from {p.when()})")
            continue
        try:
            kill(p.pid, signal.SIGKILL)
            notes.append(f"ended {p.name} (pid {p.pid}, from {p.when()}) "
                         "-- it had to be forced")
        except ProcessLookupError:
            notes.append(f"ended {p.name} (pid {p.pid}, from {p.when()})")
        except PermissionError as exc:
            notes.append(f"could not end {p.name} (pid {p.pid}): {exc}")
    return notes
