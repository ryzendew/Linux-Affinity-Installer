"""Named, dated copies of a prefix's configuration.

A snapshot is the prefix's own settings, not the prefix: the `Settings`
directory, the loose `.dat` files beside it, and `sess.db`. Tens of kilobytes
against several gigabytes, which is what makes it something you take before
every risky change rather than once a year.

    <base>/Manager/snapshots/<slug>/<stamp>[-<label>]/

Stored as a directory copy rather than an archive, so it can be read, diffed
and partially restored by hand. An archive would be smaller and would make the
one thing you want at 2am -- "just give me back RecentFiles.xml" -- into a job.

Restoring across prefixes is allowed and useful: it is how the live prefix's
settings get into a test one. So a snapshot records which prefix it came from,
and a restore that crosses prefixes says so, because restoring into the wrong
one is the expensive mistake.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import maintenance, prefsseed, registry

MANIFEST = "snapshot.json"
STAMP = "%Y%m%d-%H%M%S"

# Directories a take() or a restore() is halfway through. Named so they sort
# beside the thing they will become, and skipped by listing() so a snapshot
# that never finished is never offered as one that did.
STAGING_SUFFIXES = (".taking", ".restoring")


class NoSettings(RuntimeError):
    """The prefix has no Affinity settings to snapshot yet."""


class NotASnapshot(ValueError):
    pass


@dataclass
class Snapshot:
    path: Path
    prefix: str             # the prefix it was taken from
    label: str
    taken: str              # the stamp, as written
    version: str            # the Affinity version folder, e.g. 3.0
    files: int = 0
    bytes: int = 0
    notes: list = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def when(self) -> str:
        """The stamp as a date a person can read.

        Directory names want YYYYmmdd-HHMMSS, which sorts correctly and is
        unambiguous; a column of "20260917 180041" is neither of those things
        to read. Falls back to the raw stamp for a directory this did not
        write."""
        try:
            return time.strftime("%Y-%m-%d %H:%M",
                                 time.strptime(self.taken, STAMP))
        except (ValueError, TypeError):
            return self.taken

    def __str__(self) -> str:
        return f"{self.when} {self.label}".strip() + f" — from {self.prefix}"


def snapshots_dir() -> Path:
    return registry.manager_dir() / "snapshots"


def dir_for(prefix_name: str) -> Path:
    """One directory per prefix, named by the same slug the prefix uses.

    registry.dir_name already validates and normalises, and substitutes rather
    than strips, so "Affinity 33" and "Affinity33" cannot collapse together
    here any more than they can among the prefixes themselves."""
    return snapshots_dir() / registry.dir_name(prefix_name)


def _source(prefix) -> prefsseed.Settings:
    found = prefsseed.settings_in(prefix)
    if not found:
        raise NoSettings(
            f"{prefix} has no Affinity settings yet. There is nothing to "
            "snapshot until Affinity has been started in it once.")
    return found[0]


def _siblings(version_dir: Path) -> list[Path]:
    """What beside Settings belongs in a snapshot: everything not volatile.

    The history matters here. This first admitted only sess.db and *.dat, and
    missed the workspaces and shortcuts the dialog promises. Then it took
    everything, on the claim that the version folder is configuration and
    nothing else -- and the working prefix's folder turned out to hold 205 MB of
    crash-recovery autosaves, a WebView2 profile, temp directories and a pid
    file that exists only while Affinity runs. Every snapshot was 224 MB, most
    of it other people's problems.

    So it follows prefsseed.kind_of: configuration and anything unrecognised
    are kept, volatile state is not. A snapshot keeps the unrecognised because
    it is a backup and losing a new kind of setting is the worse mistake; a
    carry into a new prefix leaves them behind for the opposite reason."""
    out = []
    if not version_dir.is_dir():
        return out
    for entry in sorted(version_dir.iterdir()):
        if entry.name == "Settings":
            continue
        if prefsseed.kind_of(entry.name) == prefsseed.VOLATILE:
            continue
        out.append(entry)
    return out


def _stamp() -> str:
    return time.strftime(STAMP)


def _safe_label(label: str) -> str:
    """A label that is still a directory name.

    Kept permissive -- people label these "before 3.3" and "known good" -- but
    a label cannot introduce a path separator or hide the snapshot with a dot."""
    cleaned = "".join(c if (c.isalnum() or c in " ._-") else "-"
                      for c in (label or "").strip())
    cleaned = "-".join(cleaned.split())
    return cleaned.strip("-.")[:60]


def take(prefix_name, prefix_path, label="", settings=None) -> Snapshot:
    """Copy a prefix's settings aside, under a dated name.

    `settings` names which Settings directory to take, for a prefix carried
    across Affinity versions and holding more than one. Without it the newest
    is used -- which is right when the user asks for a snapshot, and wrong for
    restore()'s safety net, where what must be preserved is the folder about to
    be overwritten and not whichever was touched most recently.

    Does not require the prefix to be idle. Reading settings from a running
    Affinity can catch a half-written preferences file, which is a reason to
    prefer taking these when it is closed -- but refusing outright would make
    the snapshot unavailable at exactly the moment somebody wants one, just
    before doing something they are unsure about.

    Built in a staging directory and renamed into place. An interrupted take --
    the disk filling, the manager being killed -- used to leave a half-copied
    directory that listing() presented as a finished snapshot, which is the
    worst possible thing for a backup to be."""
    source = settings or _source(prefix_path)
    stamp = _stamp()
    safe = _safe_label(label)
    dest = dir_for(prefix_name) / (f"{stamp}-{safe}" if safe else stamp)
    if dest.exists():
        raise NotASnapshot(f"{dest} already exists.")

    staging = dest.with_name(dest.name + ".taking")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        shutil.copytree(source.path, staging / "Settings", symlinks=True)
        siblings = _siblings(source.path.parent)
        for entry in siblings:
            target = staging / entry.name
            if entry.is_dir() and not entry.is_symlink():
                shutil.copytree(entry, target, symlinks=True)
            else:
                shutil.copy2(entry, target, follow_symlinks=False)

        (staging / MANIFEST).write_text(json.dumps({
            "prefix": prefix_name,
            "source": str(source.path),
            "version": source.version,
            "label": safe,
            "taken": stamp,
            "siblings": [e.name for e in siblings],
        }, indent=2) + "\n")
        staging.rename(dest)
    except BaseException:
        with contextlib.suppress(OSError):
            shutil.rmtree(staging)
        raise

    files, size, _ = prefsseed._measure(dest)
    return Snapshot(dest, prefix_name, safe, stamp, source.version, files, size)


def read_manifest(path: Path) -> Snapshot:
    path = Path(path)
    if not (path / "Settings").is_dir():
        raise NotASnapshot(f"{path} has no Settings directory in it.")
    data = {}
    try:
        data = json.loads((path / MANIFEST).read_text())
    except (OSError, ValueError):
        pass                    # an unreadable manifest is not a lost snapshot
    # A file on disk, so it says whatever somebody last wrote in it. Valid JSON
    # that is not an object -- a list, a number, "null" -- passed the except
    # above and then met .get(), and the AttributeError took the snapshots
    # dialog AND the removal plan with it, because both call listing().
    if not isinstance(data, dict):
        data = {}

    files, size, _ = prefsseed._measure(path)
    notes = []
    if not data:
        notes.append("no usable manifest; which prefix this came from is unknown")

    def text(key, fallback):
        value = data.get(key)
        return value if isinstance(value, str) and value else fallback

    return Snapshot(path, text("prefix", "unknown"), text("label", ""),
                    text("taken", path.name.split("-")[0]),
                    text("version", "unknown"), files, size, notes)


def listing(prefix_name=None) -> list[Snapshot]:
    """Snapshots, newest first. One prefix's, or every prefix's."""
    roots = ([dir_for(prefix_name)] if prefix_name
             else sorted(p for p in _existing(snapshots_dir()) if p.is_dir()))
    out = []
    for root in roots:
        for path in sorted(_existing(root), reverse=True):
            if not path.is_dir():
                continue
            # A take() or a restore() that was interrupted. Never offered as a
            # finished snapshot; the next take of the same prefix clears it.
            if path.name.endswith(STAGING_SUFFIXES):
                continue
            try:
                out.append(read_manifest(path))
            except (NotASnapshot, OSError):
                continue
    out.sort(key=lambda s: s.taken, reverse=True)
    return out


def _existing(path: Path):
    try:
        return list(path.iterdir())
    except OSError:
        return []


@dataclass
class RestorePlan:
    snapshot: Snapshot
    into_prefix: str
    into_path: Path
    destination: Path
    crosses_prefixes: bool
    will_replace: int
    will_add: int

    def describe(self) -> list[str]:
        lines = [f"Restore {self.snapshot} into {self.into_prefix}.",
                 f"{self.will_replace} file(s) replaced, "
                 f"{self.will_add} added, in {self.destination}."]
        if self.crosses_prefixes:
            lines.append(
                f"This snapshot was taken from {self.snapshot.prefix}, not from "
                f"{self.into_prefix}. That is allowed and is how settings move "
                "between prefixes -- but check it is the one you meant.")
        if self.snapshot.version != "unknown":
            lines.append(f"Affinity version folder: {self.snapshot.version}.")
        lines += self.snapshot.notes
        return lines


def plan_restore(snapshot: Snapshot, into_prefix: str, into_path) -> RestorePlan:
    into_path = Path(into_path).expanduser()
    destination = prefsseed.destination_for(
        into_path, None if snapshot.version == "unknown" else snapshot.version)
    stand_in = prefsseed.Settings(snapshot.path, snapshot.path / "Settings",
                                  snapshot.version, snapshot.files,
                                  snapshot.bytes, 0.0)
    counts = prefsseed.plan(stand_in, destination)
    return RestorePlan(snapshot, into_prefix, into_path, destination,
                       snapshot.prefix != into_prefix,
                       len(counts.replaced), len(counts.added))


def restore(plan: RestorePlan, *, snapshot_first=True) -> list[str]:
    """Put a snapshot back, after putting the current settings somewhere safe.

    Refuses on a running prefix -- reading settings from one is a risk, writing
    them into one is a corruption. Takes a snapshot of what is there first and
    defaults to doing so, because the common way to lose a configuration is to
    restore the wrong snapshot over it. That safety net is pointed at the
    version folder about to be overwritten, not at whichever is newest: a
    prefix carried from 3.0 to 3.3 has two, and backing up the wrong one is the
    same as not backing up at all.

    The swap is of the WHOLE version folder, in two renames. An earlier version
    renamed only Settings into place and then copied the loose state beside it
    one file at a time, afterwards -- which is exactly the mixed configuration
    this docstring claimed was impossible, and it also left stale siblings from
    the old configuration sitting next to the restored one."""
    maintenance._require_idle(plan.into_path)
    notes: list[str] = []

    destination = plan.destination          # <version>/Settings
    version_dir = destination.parent

    if snapshot_first:
        try:
            current = None
            if destination.is_dir():
                files, size, modified = prefsseed._measure(destination)
                current = prefsseed.Settings(plan.into_path, destination,
                                             version_dir.name, files, size,
                                             modified)
            kept = take(plan.into_prefix, plan.into_path,
                        label="before-restore", settings=current)
            notes.append(f"Current settings snapshotted as {kept.name}")
        except NoSettings:
            notes.append("Nothing was there to snapshot first")

    # Built complete, beside the folder it will replace, and then swapped in.
    staging = version_dir.with_name(version_dir.name + ".restoring")
    if staging.exists():
        shutil.rmtree(staging)
    try:
        # Whatever is there now, minus the parts the snapshot supplies. Copied
        # rather than started empty so anything the snapshot does not know
        # about survives the restore.
        if version_dir.is_dir():
            shutil.copytree(version_dir, staging, symlinks=True)
        else:
            staging.mkdir(parents=True)
        if (staging / "Settings").exists():
            shutil.rmtree(staging / "Settings")
        shutil.copytree(plan.snapshot.path / "Settings", staging / "Settings",
                        symlinks=True)

        restored = []
        for entry in sorted(plan.snapshot.path.iterdir()):
            if entry.name in (MANIFEST, "Settings"):
                continue
            target = staging / entry.name
            if target.exists() or target.is_symlink():
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            if entry.is_dir() and not entry.is_symlink():
                shutil.copytree(entry, target, symlinks=True)
            else:
                shutil.copy2(entry, target, follow_symlinks=False)
            restored.append(entry.name)

        previous = version_dir.with_name(version_dir.name + ".replaced-" + _stamp())
        version_dir.parent.mkdir(parents=True, exist_ok=True)
        if version_dir.exists():
            version_dir.rename(previous)
            notes.append(f"Replaced settings kept at {previous.name}")
        staging.rename(version_dir)
    except BaseException:
        with contextlib.suppress(OSError):
            shutil.rmtree(staging)
        raise

    notes.append(f"Restored into {destination}")
    if restored:
        notes.append("Also restored: " + ", ".join(restored))
    return notes


def remove(snapshot: Snapshot) -> Path:
    """Delete one snapshot. Checked, because this takes a path from a manifest.

    A snapshot outside the snapshots directory is not a snapshot, whatever its
    manifest says -- and the manifest is a file on disk that nothing stops
    somebody editing."""
    path = Path(snapshot.path).resolve()
    root = snapshots_dir().resolve()
    if not maintenance._is_inside(path, root):
        raise NotASnapshot(f"{path} is not inside {root}.")
    shutil.rmtree(path)
    return path
