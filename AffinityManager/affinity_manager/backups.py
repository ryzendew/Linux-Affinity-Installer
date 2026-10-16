"""Backups: a frozen copy of a whole prefix, and of the desktop files around it.

There are three kinds of copy in this application, and they are for different
jobs. The UI says so at every entry point, because picking the wrong one is how
somebody discovers, after an upgrade, that what they kept cannot bring back
what they lost.

  Snapshot  Just the settings -- preferences, workspaces, shortcuts, recent
            files. A few megabytes, kept by the manager. For undoing a
            settings change.

  Clone     A second prefix, registered and launchable. For experimenting
            without touching the original. It is a live prefix, not a copy to
            fall back to: using it changes it.

  Backup    This module. An exact copy of the whole prefix PLUS the shared
            desktop files an install rewrites -- the menu entry, the document
            associations, Wine's file-type definitions, the launchers that name
            the prefix -- written wherever the user chooses and never launched.
            Restoring it puts the prefix and those files back as they were.
            For undoing an install or an upgrade.

A backup is a directory:

    <location>/<prefix-slug>-<YYYYmmdd-HHMMSS>[-<label>]/
        .affinity-manager-backup   marker, written first
        prefix/                    the prefix, copied exactly
        host/                      the desktop files, at their paths under $HOME
        backup.json                the manifest, written last

The manifest is written last and the directory is built under a .partial name
and renamed at the end, so a backup that was interrupted can never be mistaken
for one that finished. The marker is written first so that even a partial one
can be recognised -- and deleted -- as ours, and nothing else can.

Where it goes matters as much as that it exists, so every location is
described by free space and by whether it sits on the same physical disk as the
prefix. On the machine this was written on, /home and /mnt/work are two
partitions of one NVMe drive: a backup in /mnt/work guards against mistakes and
not against that drive failing.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, desktopentry, hoststate, maintenance, probe, registry, settings

MANIFEST = "backup.json"
MARKER = ".affinity-manager-backup"
PARTIAL = ".partial"
FORMAT = 1
STAMP = "%Y%m%d-%H%M%S"

SETTING_DEFAULT_LOCATION = "backup_location"
SETTING_RECENT_LOCATIONS = "backup_recent_locations"
RECENT_KEEP = 5


class BackupError(RuntimeError):
    pass


class NotABackup(BackupError):
    pass


class InUse(BackupError):
    """Wine is running in the prefix."""


# ── which processes are using a prefix ───────────────────────────────────────


def activity(prefix):
    """What is running in a prefix. One place, so tests can stand in for /proc."""
    from . import liveness

    return liveness.scan(prefix)


def _require_quiet(prefix, *, replacing=False) -> None:
    """Refuse while Affinity runs; when REPLACING the prefix, refuse leftovers too.

    Copying a prefix that has only leftovers in it is safe: with Affinity gone
    nothing is writing its settings, and the registry on disk is whole. Putting
    a different prefix in its place is not -- those processes have it open --
    so a restore asks for them to be ended first.

    This used to refuse on ANY Wine process, which counted two-week-old
    leftovers with no wineserver as "Wine is running" for ever."""
    from . import liveness

    now = activity(prefix)
    if now.state == liveness.RUNNING:
        raise InUse(f"{now.summary()} Close it first: a copy taken or replaced "
                    "under a running Affinity can capture its settings "
                    "half-written.")
    if replacing and now.state == liveness.LEFTOVERS:
        raise InUse(f"{now.summary()} End them first -- they have this prefix "
                    "open, and it is about to be replaced.")


# ── locations ────────────────────────────────────────────────────────────────


def physical_disk(path) -> str | None:
    """The block device a path's filesystem lives on, as a disk -- "nvme0n1",
    "sda" -- not a partition. None when it cannot be told: network mounts,
    LVM, anything without a /sys/dev/block entry of the usual shape.

    Partitions are the trap this exists for. /home and /mnt/work can be two
    filesystems on one drive, and a backup that is "somewhere else" by
    filesystem is not somewhere else when the drive fails."""
    p = Path(path).expanduser()
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        dev = os.stat(p).st_dev
    except OSError:
        return None
    node = Path(f"/sys/dev/block/{os.major(dev)}:{os.minor(dev)}")
    try:
        real = node.resolve(strict=True)
    except OSError:
        return None
    if (real / "partition").exists():
        return real.parent.name
    return real.name


# Filesystems that cannot hold a Wine prefix. A prefix is full of symlinks --
# every drive letter is one -- and these store none, so rsync fails on the
# first and leaves a partial copy behind. Refused outright.
NO_SYMLINKS = frozenset({"vfat", "msdos", "exfat", "fat", "umsdos"})
# These can, through the Linux drivers, but not reliably: ntfs-3g and ntfs3
# store symlinks as reparse points and permissions not at all. Allowed, with
# the reason said.
SHAKY = frozenset({"ntfs", "ntfs3", "fuseblk"})
# Held in memory. A backup here reports success and is gone at the next reboot,
# which for a backup is worse than failing -- /tmp is one of these on most
# systems, and it shows plenty of free space.
IN_MEMORY = frozenset({"tmpfs", "ramfs"})


def filesystem_type(path) -> str | None:
    """The type of the filesystem a path is on, from /proc/self/mounts.

    Mount points are octal-escaped there -- "Work Backup" is written
    "Work\\040Backup" -- and not decoding that makes every removable drive with
    a space in its label look like part of the filesystem above it."""
    p = Path(path).expanduser()
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        real = os.path.realpath(p)
        lines = Path("/proc/self/mounts").read_text().splitlines()
    except OSError:
        return None
    best, kind = "", None
    for line in lines:
        fields = line.split()
        if len(fields) < 3:
            continue
        point = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), fields[1])
        if (real == point or real.startswith(point.rstrip("/") + "/")) \
                and len(point) > len(best):
            best, kind = point, fields[2]
    return kind


@dataclass
class Location:
    path: Path
    free: int
    exists: bool
    writable: bool
    same_disk: bool | None      # None: could not tell
    disk: str | None
    why: str = ""               # a default, a recent one, one chosen now
    fstype: str | None = None
    blocker: Path | None = None  # the existing folder that refuses the write

    @property
    def holds_prefix(self) -> bool:
        return self.fstype not in NO_SYMLINKS

    @property
    def survives_reboot(self) -> bool:
        return self.fstype not in IN_MEMORY

    @property
    def usable(self) -> bool:
        return self.writable and self.holds_prefix and self.survives_reboot

    def describe(self, needed: int) -> str:
        bits = []
        if not self.exists:
            bits.append("will be created")
        bits.append(f"{probe.human_size(self.free)} free")
        if self.free < needed * 1.05:
            bits.append(f"NOT ENOUGH -- needs {probe.human_size(needed)}")
        if self.same_disk is True:
            bits.append("same physical disk as the prefix: protects against "
                        "mistakes, not against the disk failing")
        elif self.same_disk is False:
            bits.append(f"a different disk ({self.disk})")
        if not self.survives_reboot:
            bits.append(f"IN MEMORY ({self.fstype}) -- gone at the next reboot")
        if not self.holds_prefix:
            bits.append(f"CANNOT HOLD A PREFIX -- {self.fstype} stores no symlinks, "
                        "and every drive letter in a prefix is one")
        elif self.fstype in SHAKY:
            bits.append(f"{self.fstype}: symlinks and permissions may not survive "
                        "the round trip")
        if not self.writable:
            owner = ""
            try:
                import pwd
                owner = pwd.getpwuid(self.blocker.stat().st_uid).pw_name
            except (KeyError, OSError, AttributeError):
                pass
            bits.append(f"not writable: {self.blocker} belongs to "
                        f"{owner or 'another user'} -- choose a folder of yours "
                        "inside it")
        return "; ".join(bits)


def describe_location(path, prefix, why="") -> Location:
    p = Path(path).expanduser()
    probe_at = p
    while not probe_at.exists() and probe_at != probe_at.parent:
        probe_at = probe_at.parent
    try:
        free = shutil.disk_usage(probe_at).free
    except OSError:
        free = 0
    mine, theirs = physical_disk(prefix), physical_disk(p)
    same = None if (mine is None or theirs is None) else (mine == theirs)
    return Location(p, free, p.is_dir(), os.access(probe_at, os.W_OK),
                    same, theirs, why, filesystem_type(p), probe_at)


def default_location() -> Path:
    saved = settings.get(SETTING_DEFAULT_LOCATION)
    if saved:
        return Path(saved).expanduser()
    return registry.base_dir() / "Backups"


def set_default_location(path) -> None:
    settings.set(SETTING_DEFAULT_LOCATION, str(Path(path).expanduser()))


def recent_locations() -> list[Path]:
    return [Path(p) for p in (settings.get(SETTING_RECENT_LOCATIONS) or [])]


def _remember_location(path) -> None:
    path = str(Path(path).expanduser())
    recent = [p for p in (settings.get(SETTING_RECENT_LOCATIONS) or []) if p != path]
    settings.set(SETTING_RECENT_LOCATIONS, ([path] + recent)[:RECENT_KEEP])


def candidate_locations(prefix) -> list[Location]:
    """The default, then recently used ones, each described once."""
    out, seen = [], set()
    for path, why in [(default_location(), "default")] + \
                     [(p, "used before") for p in recent_locations()]:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(describe_location(path, prefix, why))
    return out


# ── the desktop files around a prefix ────────────────────────────────────────
#
# What an install rewrites outside its own prefix, and therefore what a restore
# has to put back for the revert to be complete. Chosen narrowly: restoring is
# a global act -- these files are shared by every prefix -- so it must not
# reach anything unrelated to Affinity.


def _home() -> Path:
    return Path.home()


def _rel(path: Path) -> str:
    return str(path.relative_to(_home()))


def _under_home(path: Path) -> bool:
    try:
        path.relative_to(_home())
        return True
    except ValueError:
        return False


def _file_globs() -> list[Path]:
    """Whole files captured and restored as they were, relative to $HOME."""
    apps = hoststate.applications_dir()
    mime = hoststate.mime_packages_dir()
    return [
        apps / "Affinity.desktop",                 # the installer's fixed name
        apps / "wine-extension-*.desktop",         # Wine's file-type handlers
        apps / "wine" / "Programs" / "Affinity.desktop",
        mime / "x-wine-extension-*.xml",           # old installer naming
        mime / "affinity-*.xml",                   # new installer + manager
    ]


def _launcher_files(prefix) -> list[Path]:
    """The user's launchers that name this prefix. Captured, restored if they
    were changed, never moved aside when new -- a launcher somebody writes
    after the backup is theirs, not the install's."""
    out = []
    for f in maintenance.launchers_naming(prefix):
        if f.suffix == ".desktop":
            continue            # desktop entries are handled by _file_globs
        try:
            f.relative_to(_home())
        except ValueError:
            continue
        out.append(f)
    return out


def _glob(pattern: Path) -> list[Path]:
    return sorted(p for p in pattern.parent.glob(pattern.name)
                  if p.is_file() or p.is_symlink())


# Keys in mimeapps.list that decide what opens Affinity's documents. Only these
# are captured and restored: the file also holds the user's choice of PDF
# viewer, image editor and everything else, and a restore that put back the
# whole file would silently undo every one of those made since the backup.
def _is_affinity_key(key: str) -> bool:
    key = key.strip()
    return key in hoststate.DOCUMENT_TYPES or key.startswith("application/x-wine-extension-")


def _read_mimeapps(path: Path) -> dict:
    """{section: {key: value}} for the Affinity keys only."""
    out: dict = {}
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return out
    section = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        if _is_affinity_key(key):
            out.setdefault(section, {})[key.strip()] = value.strip()
    return out


def _write_mimeapps(path: Path, wanted: dict) -> list[str]:
    """Make the Affinity keys in one mimeapps.list exactly `wanted`.

    Every other line is left byte for byte as it is. Affinity keys present now
    but not in `wanted` are removed; ones in `wanted` are set, in place if the
    line exists and at the end of their section if not."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        lines = []
    notes, out, section, done = [], [], "", set()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            # Before leaving a section, add what it should have and did not.
            for key, value in wanted.get(section, {}).items():
                if (section, key) not in done:
                    out.append(f"{key}={value}")
                    done.add((section, key))
                    notes.append(f"{path.name}: {key} set in {section}")
            section = stripped
            out.append(line)
            continue
        if "=" in line:
            key = line.partition("=")[0].strip()
            if _is_affinity_key(key):
                value = wanted.get(section, {}).get(key)
                if value is None:
                    notes.append(f"{path.name}: {key} removed from {section}")
                    continue
                out.append(f"{key}={value}")
                done.add((section, key))
                continue
        out.append(line)
    for key, value in wanted.get(section, {}).items():
        if (section, key) not in done:
            out.append(f"{key}={value}")
            done.add((section, key))
    for sec, keys in wanted.items():
        missing = [(k, v) for k, v in keys.items() if (sec, k) not in done]
        if missing:
            out.append(sec)
            for key, value in missing:
                out.append(f"{key}={value}")
                notes.append(f"{path.name}: {key} set in {sec}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n")
    return notes


# ── the backup itself ────────────────────────────────────────────────────────


@dataclass
class Backup:
    path: Path
    prefix_name: str = "unknown"
    prefix_path: str = ""
    label: str = ""
    taken: str = ""
    files: int = 0
    bytes: int = 0
    host_files: list = field(default_factory=list)
    mimeapps: dict = field(default_factory=dict)
    machine: str = ""
    status: str = "ok"          # ok | partial | unreachable | damaged
    notes: list = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def when(self) -> str:
        try:
            return time.strftime("%Y-%m-%d %H:%M", time.strptime(self.taken, STAMP))
        except (ValueError, TypeError):
            return self.taken or "?"

    @property
    def location(self) -> Path:
        return self.path.parent

    def __str__(self) -> str:
        return f"{self.prefix_name}, {self.when}" + (f" ({self.label})" if self.label else "")


def _slug(name: str) -> str:
    return registry.dir_name(name)


def _safe_label(label: str) -> str:
    cleaned = "".join(c if (c.isalnum() or c in " ._-") else "-"
                      for c in (label or "").strip())
    return "-".join(cleaned.split()).strip("-.")[:60]


def _measure(root: Path) -> tuple[int, int]:
    """Files and bytes, counting symlinks as themselves -- never followed, or
    dosdevices/z: would count the whole machine."""
    files = size = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames + [d for d in dirnames
                                 if os.path.islink(os.path.join(dirpath, d))]:
            try:
                st = os.lstat(os.path.join(dirpath, name))
            except OSError:
                continue
            files += 1
            size += st.st_size
    return files, size


@dataclass
class BackupPlan:
    prefix_name: str
    source: Path
    dest: Path
    size: int
    location: Location
    include_host: bool
    label: str
    stamp: str

    @property
    def partial(self) -> Path:
        return self.dest.with_name(self.dest.name + PARTIAL)


def plan_backup(prefix_name, prefix_path, location, *, label="",
                include_host=True, size=None) -> BackupPlan:
    """What a backup would do. Writes nothing, and refuses early.

    `size` lets a dialog that already measured the prefix skip the walk; an
    11 GB prefix takes seconds to measure, and the dialog re-plans every time
    the chosen location changes."""
    src = Path(prefix_path).expanduser()
    if not probe.is_prefix(src):
        raise NotABackup(f"{src} does not look like a Wine prefix.")
    loc_path = Path(location).expanduser()
    try:
        loc_path.resolve().relative_to(src.resolve())
        raise BackupError(f"{loc_path} is inside the prefix it would back up.")
    except ValueError:
        pass
    size = maintenance._du(src) if size is None else size
    loc = describe_location(loc_path, src)
    if not loc.survives_reboot:
        raise BackupError(
            f"{loc_path} is on {loc.fstype}, which is held in memory: the backup "
            "would report success and be gone at the next reboot.")
    if not loc.holds_prefix:
        raise BackupError(
            f"{loc_path} is on {loc.fstype}, which stores no symlinks. A Wine "
            "prefix is full of them -- every drive letter is one -- so the copy "
            "would fail on the first. Choose a Linux-formatted disk.")
    if not loc.writable:
        raise BackupError(f"{loc_path} is not writable: {loc.blocker} refuses it.")
    if loc.free < size * 1.05:
        raise maintenance.NotEnoughSpace(
            f"The backup needs about {probe.human_size(size)}; "
            f"{loc_path} has {probe.human_size(loc.free)} free.")
    safe = _safe_label(label)
    stamp = time.strftime(STAMP)
    name = f"{_slug(prefix_name)}-{stamp}" + (f"-{safe}" if safe else "")
    dest = loc_path / name
    if dest.exists() or dest.with_name(dest.name + PARTIAL).exists():
        raise BackupError(f"{dest} already exists.")
    return BackupPlan(prefix_name, src, dest, size, loc, include_host, safe, stamp)


def create(plan: BackupPlan, *, progress=None) -> Backup:
    """Take the backup. Refuses while Wine runs in the prefix.

    rsync -aH into a .partial directory, the desktop files beside it, the
    manifest last, then one rename. Symlinks are NOT repointed, unlike a
    clone: a backup is meant to go back exactly where it came from, and a
    repointed link would be wrong the moment it did."""
    _require_quiet(plan.source)
    partial = plan.partial
    partial.mkdir(parents=True)
    (partial / MARKER).write_text(f"affinity-manager {__version__}\n")
    # Recorded now, not on success. An interrupted backup of an 11 GB prefix
    # is 11 GB of partial copy; recorded only at the end, it would sit on the
    # disk where nothing would ever list it or offer to remove it.
    _index_add(partial)
    _remember_location(plan.dest.parent)

    maintenance.copy_tree(plan.source, partial / "prefix", progress=progress,
                          hard_links=True)

    host_files, mimeapps = [], {}
    if plan.include_host:
        host_files, mimeapps = _capture_host(plan.source, partial / "host")

    files, size = _measure(partial / "prefix")
    manifest = {
        "format": FORMAT,
        "prefix_name": plan.prefix_name,
        "prefix_path": str(plan.source),
        "label": plan.label,
        "taken": plan.stamp,
        "files": files,
        "bytes": size,
        "host_files": host_files,
        "mimeapps": mimeapps,
        "machine": socket.gethostname(),
        "manager_version": __version__,
    }
    (partial / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    partial.rename(plan.dest)
    _index_drop(partial)
    _index_add(plan.dest)
    return read(plan.dest)


def _capture_host(prefix: Path, into: Path) -> tuple[list, dict]:
    captured = []
    seen = set()
    for pattern in _file_globs():
        for f in _glob(pattern):
            if f in seen or not _under_home(f):
                continue
            seen.add(f)
            _copy_home_file(f, into)
            captured.append({"path": _rel(f), "kind": "file"})
    for f in _launcher_files(prefix):
        if f in seen:
            continue
        seen.add(f)
        _copy_home_file(f, into)
        captured.append({"path": _rel(f), "kind": "launcher"})
    mimeapps = {}
    for f in hoststate.mimeapps_files():
        try:
            rel = _rel(f)
        except ValueError:
            continue
        mimeapps[rel] = _read_mimeapps(f) if f.exists() else None
    return captured, mimeapps


def _copy_home_file(f: Path, into: Path) -> None:
    target = into / _rel(f)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(f, target, follow_symlinks=False)


# ── reading and listing ──────────────────────────────────────────────────────


def read(path) -> Backup:
    """A backup directory, as whatever it turns out to be.

    Never raises for a directory that is ours: a partial one, a damaged
    manifest, a manifest that is not an object -- each comes back as a Backup
    with a status that says so, because the list must still show it and offer
    to remove it."""
    p = Path(path)
    if not p.is_dir():
        return Backup(p, status="unreachable",
                      notes=["not reachable -- is the disk it is on mounted?"])
    if not (p / MARKER).exists() and not (p / MANIFEST).exists():
        raise NotABackup(f"{p} is not a backup made by this application.")
    if p.name.endswith(PARTIAL) or not (p / MANIFEST).exists():
        return Backup(p, prefix_name=_guess_name(p), status="partial",
                      notes=["did not finish -- safe to delete"])
    try:
        data = json.loads((p / MANIFEST).read_text())
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        return Backup(p, prefix_name=_guess_name(p), status="damaged",
                      notes=["the manifest cannot be read"])

    def text(key, fallback=""):
        v = data.get(key)
        return v if isinstance(v, str) else fallback

    def number(key):
        v = data.get(key)
        return v if isinstance(v, int) and v >= 0 else 0

    host = data.get("host_files")
    mimeapps = data.get("mimeapps")
    return Backup(
        p, text("prefix_name", _guess_name(p)), text("prefix_path"),
        text("label"), text("taken"), number("files"), number("bytes"),
        host if isinstance(host, list) else [],
        mimeapps if isinstance(mimeapps, dict) else {},
        text("machine"))


def _guess_name(p: Path) -> str:
    return re.sub(r"-\d{8}-\d{6}.*$", "", p.name.removesuffix(PARTIAL)) or p.name


def _index_path() -> Path:
    return registry.manager_dir() / "backups.json"


def _index() -> list[str]:
    try:
        data = json.loads(_index_path().read_text())
    except (OSError, ValueError):
        return []
    paths = data.get("backups") if isinstance(data, dict) else None
    return [p for p in (paths or []) if isinstance(p, str)]


def _index_write(paths) -> None:
    target = _index_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"version": 1, "backups": sorted(set(paths))},
                              indent=2) + "\n")
    tmp.replace(target)


def _index_add(path) -> None:
    _index_write(_index() + [str(Path(path))])


def _index_drop(path) -> None:
    _index_write([p for p in _index() if p != str(Path(path))])


def listing(prefix_name=None) -> list[Backup]:
    """Every backup this manager knows of, newest first.

    Known from the index, and ALSO found by looking in the locations it knows,
    so a backup made before the index was lost -- or on another machine, on a
    disk that is plugged in now -- still shows up. Unreachable ones are listed
    rather than dropped: a backup on an unplugged disk still exists."""
    paths = set(_index())
    for loc in [default_location()] + recent_locations():
        try:
            for child in loc.iterdir():
                if child.is_dir() and ((child / MARKER).exists()
                                       or (child / MANIFEST).exists()):
                    paths.add(str(child))
        except OSError:
            continue
    out = []
    for path in paths:
        try:
            b = read(path)
        except NotABackup:
            continue
        if prefix_name and b.prefix_name != prefix_name:
            continue
        out.append(b)
    out.sort(key=lambda b: (b.taken or "", b.name), reverse=True)
    return out


def verify(backup: Backup) -> list[str]:
    """Is the copy still what the manifest says it is? Empty means yes.

    File count and total size, not checksums: checksumming eleven gigabytes
    to answer "did the disk get unplugged half way through" would take long
    enough that nobody would press the button."""
    if backup.status != "ok":
        return backup.notes or [f"backup is {backup.status}"]
    problems = []
    prefix = backup.path / "prefix"
    if not probe.is_prefix(prefix):
        return ["the copy of the prefix is missing or incomplete"]
    files, size = _measure(prefix)
    if files != backup.files:
        problems.append(f"{files} files, but {backup.files} were backed up")
    if size != backup.bytes:
        problems.append(f"{probe.human_size(size)}, but "
                        f"{probe.human_size(backup.bytes)} were backed up")
    for item in backup.host_files:
        rel = item.get("path") if isinstance(item, dict) else None
        if rel and not (backup.path / "host" / rel).exists() \
                and not (backup.path / "host" / rel).is_symlink():
            problems.append(f"desktop file missing from the backup: {rel}")
    return problems


def remove(backup: Backup) -> Path:
    """Delete one backup -- only ever a directory this application made."""
    p = Path(backup.path)
    if not ((p / MARKER).exists() or (p / MANIFEST).exists()):
        raise NotABackup(f"{p} was not made by this application; not deleting it.")
    shutil.rmtree(p)
    _index_drop(p)
    return p


# ── restoring ────────────────────────────────────────────────────────────────


@dataclass
class RestorePlan:
    backup: Backup
    target: Path
    restore_prefix: bool
    restore_host: bool
    size: int
    moved_aside_to: Path | None
    host_put_back: list
    host_moved_aside: list
    mimeapps_changes: list

    def describe(self) -> list[str]:
        lines = []
        if self.restore_prefix:
            if self.moved_aside_to:
                lines.append(f"The prefix now at {self.target} is renamed to "
                             f"{self.moved_aside_to.name} -- not deleted -- and "
                             "added to the list so you can launch it or remove it.")
            lines.append(f"The backup ({probe.human_size(self.size)}) is copied "
                         f"to {self.target}.")
        if self.restore_host:
            lines.append(f"{len(self.host_put_back)} desktop file(s) put back as "
                         "they were.")
            if self.host_moved_aside:
                lines.append(f"{len(self.host_moved_aside)} file(s) that appeared "
                             "since the backup are moved aside: "
                             + ", ".join(Path(p).name for p in self.host_moved_aside[:6])
                             + ("…" if len(self.host_moved_aside) > 6 else ""))
            if self.mimeapps_changes:
                lines.append("Document associations: "
                             + "; ".join(self.mimeapps_changes[:6]))
            lines.append("Anything replaced is kept in the manager's restores "
                         "folder, so this can be undone the same way.")
        return lines


def aside_name(prefix_name: str, when=None) -> str:
    """A list name for the prefix a restore replaced.

    Always a valid name: letters, digits, space and ._- only, 64 at most. The
    first version put the date in parentheses, which the registry refuses, so
    the replaced prefix was mentioned by path and never appeared in the list
    where it could be launched or removed."""
    suffix = " before restore " + time.strftime("%Y-%m-%d %H%M", when or time.localtime())
    cleaned = re.sub(r"[^A-Za-z0-9 ._-]", "-", prefix_name).strip(" .-_") or "Prefix"
    return cleaned[:64 - len(suffix)].rstrip(" .-_") + suffix


def _current_host_files() -> set[str]:
    return {_rel(f) for pattern in _file_globs() for f in _glob(pattern)
            if _under_home(f)}


def plan_restore(backup: Backup, *, restore_prefix=True, restore_host=True,
                 target=None) -> RestorePlan:
    if backup.status != "ok":
        raise NotABackup(f"This backup is {backup.status} and cannot be restored.")
    target = Path(target or backup.prefix_path).expanduser()
    if not str(target) or target == Path("."):
        raise BackupError("The backup does not say where its prefix lived.")
    moved = None
    if restore_prefix and target.exists():
        moved = target.with_name(f"{target.name}.before-restore-{time.strftime(STAMP)}")
    if restore_prefix:
        where = target.parent
        while not where.exists() and where != where.parent:
            where = where.parent
        free = shutil.disk_usage(where).free
        if free < backup.bytes * 1.05:
            raise maintenance.NotEnoughSpace(
                f"Restoring needs about {probe.human_size(backup.bytes)} on "
                f"{target.parent}; {probe.human_size(free)} is free.")

    put_back = [i["path"] for i in backup.host_files
                if isinstance(i, dict) and i.get("path")] if restore_host else []
    captured_files = {i["path"] for i in backup.host_files
                      if isinstance(i, dict) and i.get("kind") == "file"}
    moved_aside = sorted(_current_host_files() - captured_files) if restore_host else []

    changes = []
    if restore_host:
        for rel, wanted in (backup.mimeapps or {}).items():
            now = _read_mimeapps(_home() / rel)
            if (wanted or {}) != now:
                changes.append(f"the Affinity entries in {Path(rel).name} go back "
                               "to how they were; every other association in it "
                               "is left as you have it now")
    return RestorePlan(backup, target, restore_prefix, restore_host,
                       backup.bytes, moved, put_back, moved_aside, changes)


def restore(plan: RestorePlan, *, progress=None) -> list[str]:
    """Put a backup back. Nothing is deleted; everything replaced is kept.

    The prefix is copied into a staging directory beside its destination and
    swapped in with two renames, so an interrupted restore leaves the current
    prefix exactly where it was. The desktop files that are replaced go into a
    dated folder under the manager's own directory, so a restore can itself be
    reversed."""
    notes = []
    if plan.restore_prefix:
        _require_quiet(plan.target, replacing=True)
        staging = plan.target.with_name(plan.target.name + ".restoring")
        if staging.exists():
            shutil.rmtree(staging)
        try:
            maintenance.copy_tree(plan.backup.path / "prefix", staging,
                                  progress=progress, hard_links=True)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        if plan.target.exists():
            plan.target.rename(plan.moved_aside_to)
            notes.append(f"The prefix that was there is now {plan.moved_aside_to}")
        staging.rename(plan.target)
        notes.append(f"Restored {plan.target} from {plan.backup}")

    if plan.restore_host:
        notes += _restore_host(plan)
    return notes


def _restore_host(plan: RestorePlan) -> list[str]:
    aside = registry.manager_dir() / "restores" / time.strftime(STAMP)
    notes = []

    def keep(rel: str):
        current = _home() / rel
        if current.exists() or current.is_symlink():
            target = aside / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(current), str(target))

    for rel in plan.host_moved_aside:
        keep(rel)
        notes.append(f"moved aside: {rel}")
    for rel in plan.host_put_back:
        source = plan.backup.path / "host" / rel
        if not (source.exists() or source.is_symlink()):
            notes.append(f"missing from the backup, left as it is: {rel}")
            continue
        keep(rel)
        target = _home() / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=False)
        notes.append(f"put back: {rel}")

    for rel, wanted in (plan.backup.mimeapps or {}).items():
        path = _home() / rel
        if (wanted or {}) == _read_mimeapps(path):
            continue
        if path.exists():
            target = aside / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        notes += _write_mimeapps(path, wanted or {})

    _refresh_databases()
    if aside.exists():
        notes.append(f"Everything replaced is kept in {aside}")
    return notes


def _refresh_databases() -> None:
    desktopentry.refresh_menu()
    mime = hoststate.mime_packages_dir().parent
    if shutil.which("update-mime-database") and mime.is_dir():
        try:
            subprocess.run(["update-mime-database", str(mime)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=120, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
