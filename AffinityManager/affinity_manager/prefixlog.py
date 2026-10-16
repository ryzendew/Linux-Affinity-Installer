"""One log per prefix.

AffinityOnLinux writes everything to a single ~/AffinitySetup.log, opened in
append mode. That is fine for one installer working on one prefix and wrong for
everything this manager does: with two prefixes the lines interleave, and there
is no way afterwards to say which prefix a line belonged to.

It is not a hypothetical. Two installer instances sharing that file produced a
log that read as one run addressing the wrong prefix, and an hour went into
diagnosing a targeting bug that did not exist. The evidence that settled it was
not in the log at all -- it was /proc/<pid>/environ.

So every operation this manager runs writes to <manager>/logs/<slug>.log, and
the registry records the offset that log had reached when the operation began.
Together those are what let a recovery message quote the part of a log where
something stopped.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from . import registry

# Big enough to hold a full setup with winetricks being verbose, small enough
# that nobody has to open a 28MB file to find out what happened. One previous
# log is kept; two would be an archive, and this is not one.
MAX_BYTES = 4 * 1024 * 1024


def logs_dir() -> Path:
    return registry.manager_dir() / "logs"


def path_for(prefix_name: str) -> Path:
    return logs_dir() / f"{registry.dir_name(prefix_name)}.log"


def offset(prefix_name: str) -> int:
    """Where the log has reached. Recorded before an operation starts, so the
    message about an interrupted one can begin in the right place."""
    try:
        return path_for(prefix_name).stat().st_size
    except OSError:
        return 0


def _rotate_if_large(path: Path) -> None:
    try:
        if path.stat().st_size < MAX_BYTES:
            return
    except OSError:
        return
    try:
        path.replace(path.with_suffix(".log.1"))
    except OSError:
        pass


def write(prefix_name: str, text: str, *, stamp: bool = True) -> None:
    """Append a line. Never raises: losing a log line must not take down the
    operation it was describing."""
    path = path_for(prefix_name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_large(path)
        prefix = datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ") if stamp else ""
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{prefix}{text.rstrip()}\n")
    except OSError:
        pass


def begin(prefix_name: str, operation: str) -> int:
    """Mark the start of an operation and return the offset it began at."""
    where = offset(prefix_name)
    write(prefix_name, f"=== {operation} ===")
    return where


def read_from(prefix_name: str, start: int, limit: int = 4096) -> str:
    try:
        with open(path_for(prefix_name), "r", encoding="utf-8", errors="replace") as f:
            f.seek(start)
            return f.read(limit)
    except OSError:
        return ""


def tail(prefix_name: str, lines: int = 200) -> str:
    try:
        text = path_for(prefix_name).read_text(errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-lines:])
