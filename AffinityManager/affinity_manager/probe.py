"""What is actually in a prefix, read from the filesystem.

None of this is stored in the registry. A prefix's Affinity version changes
when it is updated, its Wine changes when it is switched, and whether it is
running changes constantly -- a cached answer would be wrong more often than
right, and wrong in the direction that gets a second instance launched.
"""

from __future__ import annotations

import os
import re
import struct
from pathlib import Path

AFFINITY_SUBDIR = Path("drive_c/Program Files/Affinity/Affinity")


def affinity_dir(prefix) -> Path:
    return Path(prefix).expanduser() / AFFINITY_SUBDIR


def is_prefix(prefix) -> bool:
    """A Wine prefix, whether or not Affinity is in it yet."""
    p = Path(prefix).expanduser()
    return (p / "drive_c").is_dir() and (p / "dosdevices").is_dir()


def has_affinity(prefix) -> bool:
    return (affinity_dir(prefix) / "Affinity.exe").is_file()


def _pe_product_version(exe: Path) -> str | None:
    """Read the version out of a PE's VS_VERSIONINFO.

    Scanning for the UTF-16 'ProductVersion' key and taking the string after it
    is cruder than parsing the resource directory, and is enough here: these are
    Serif's own binaries and the key is present exactly once. Returns None
    rather than raising, because an unreadable version is a display detail and
    must not stop a prefix being listed."""
    try:
        blob = exe.read_bytes()
    except OSError:
        return None
    key = "ProductVersion".encode("utf-16-le")
    at = blob.find(key)
    if at < 0:
        return None
    tail = blob[at + len(key): at + len(key) + 128]
    text = tail.decode("utf-16-le", "ignore")
    match = re.search(r"\d+\.\d+\.\d+(\.\d+)?", text)
    return match.group(0) if match else None


def affinity_version(prefix) -> str | None:
    exe = affinity_dir(prefix) / "Affinity.exe"
    return _pe_product_version(exe) if exe.is_file() else None


def wine_builds(prefix) -> list[str]:
    """Wine builds installed inside the prefix, newest-looking last.

    AffinityOnLinux unpacks Wine into the prefix itself, so this is a property
    of the prefix rather than of the system."""
    p = Path(prefix).expanduser()
    if not p.is_dir():
        return []
    names = [
        d.name
        for d in p.iterdir()
        if d.is_dir() and (d / "bin" / "wine").is_file()
    ]
    return sorted(names)


def wine_of_running(prefix) -> str | None:
    """The Wine a running Affinity is actually mapped against.

    Read out of /proc/<pid>/maps. This is the only answer that cannot be wrong:
    the launchers hardcode their Wine paths, so what is running need not be what
    any symlink or configuration says."""
    root = str(Path(prefix).expanduser())
    for pid in running_pids(prefix):
        try:
            maps = Path(f"/proc/{pid}/maps").read_text(errors="replace")
        except OSError:
            continue
        for line in maps.splitlines():
            at = line.find(root + "/")
            if at < 0 or "/lib/wine/" not in line:
                continue
            rest = line[at + len(root) + 1:]
            build = rest.split("/", 1)[0]
            if build:
                return build
    return None


def active_wine(prefix) -> str | None:
    """Which Wine this prefix is using.

    Asks the running process first. The ElementalWarriorWine symlink looks like
    the answer and demonstrably lies -- on the prefix this was written against
    it pointed at 11.12 while Affinity was running 11.16 -- so it is used only
    when nothing is running, and the newest-sorting build only when there is no
    symlink either."""
    p = Path(prefix).expanduser()
    running = wine_of_running(p)
    if running:
        return running
    link = p / "ElementalWarriorWine"
    if link.is_symlink():
        try:
            target = os.readlink(link)
            # A symlink is a guess about a prefix that is not running, so say so
            # rather than presenting it as fact.
            return f"{Path(target).name} (link)"
        except OSError:
            pass
    builds = [b for b in wine_builds(prefix) if b != "ElementalWarriorWine"]
    return builds[-1] if builds else None


def running_pids(prefix) -> list[int]:
    """PIDs of the Affinity processes really running in this prefix.

    Asked of liveness, which tells Affinity apart from what a finished session
    left behind. This used to count any process whose command line mentioned
    AffinityHook -- so a launcher stranded by a session two weeks earlier, with
    no Affinity.exe and no wineserver, made the prefix "running" for ever,
    refusing every operation and telling the user to close an Affinity that was
    not open."""
    from . import liveness

    return liveness.scan(prefix).running_pids


def disk_usage(prefix) -> int:
    """Bytes on disk. Walked rather than shelled out to du, so it cannot be
    derailed by a prefix name that needs quoting."""
    total = 0
    for root, _dirs, files in os.walk(Path(prefix).expanduser(), onerror=lambda e: None):
        for name in files:
            try:
                st = os.lstat(os.path.join(root, name))
            except OSError:
                continue
            total += st.st_size
    return total


def human_size(num: int) -> str:
    step = 1024.0
    for unit in ("B", "K", "M", "G", "T"):
        if abs(num) < step or unit == "T":
            return f"{num:.0f}{unit}" if unit == "B" else f"{num:.1f}{unit}"
        num /= step
    return f"{num:.1f}T"


def describe(prefix) -> dict:
    """Everything the list view shows about one prefix, in one pass."""
    path = Path(prefix).expanduser()
    exists = path.is_dir()
    pids = running_pids(path) if exists else []
    return {
        "path": str(path),
        "exists": exists,
        "is_prefix": is_prefix(path) if exists else False,
        "has_affinity": has_affinity(path) if exists else False,
        "affinity_version": affinity_version(path) if exists else None,
        "wine": active_wine(path) if exists else None,
        "wine_builds": wine_builds(path) if exists else [],
        "running": bool(pids),
        "pids": pids,
    }
