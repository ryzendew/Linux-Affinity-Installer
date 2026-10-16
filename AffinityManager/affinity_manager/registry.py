"""The record of which prefixes this manager knows about.

Everything sits under one base directory that the user picks:

    <base>/Manager/prefixes.json    the registry
    <base>/AffinityLinux_2026-09-15_01/   a managed prefix
    <base>/My_Test_Build/                 another

The base directory is the one thing that cannot live inside itself, so it is
remembered in ~/.config/AffinityLinuxManager/base_dir -- the same problem, and
the same answer, as AffinityOnLinux's own install_location file.

The registry is deliberately not the source of truth about a prefix's contents.
What Affinity is installed, which Wine it has, whether it is running: all of
that is read off the filesystem when asked (see probe.py). The registry records
only what cannot be discovered -- that a directory is managed at all, what it
is called, and what it was created from.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

# Kept as a function rather than a constant so tests can point it elsewhere
# through the environment without reaching into module state.
ENV_BASE_DIR = "AFFINITY_MANAGER_HOME"


DEFAULT_BASE = Path.home() / ".AffinityLinuxManager"
MANAGER_SUBDIR = "Manager"


def config_path() -> Path:
    """Where the base directory is remembered.

    Outside the base directory, necessarily: it is the thing being remembered."""
    return Path.home() / ".config" / "AffinityLinuxManager" / "base_dir"


def base_dir() -> Path:
    override = os.environ.get(ENV_BASE_DIR, "").strip()
    if override:
        return Path(override).expanduser()
    try:
        saved = config_path().read_text().strip()
        if saved:
            return Path(saved).expanduser()
    except OSError:
        pass
    return DEFAULT_BASE


def base_dir_is_configured() -> bool:
    """False on a first run, so the window can ask instead of assuming."""
    if os.environ.get(ENV_BASE_DIR, "").strip():
        return True
    try:
        return bool(config_path().read_text().strip())
    except OSError:
        return False


def set_base_dir(path) -> Path:
    resolved = Path(path).expanduser()
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text(str(resolved) + "\n")
    return resolved


def manager_dir() -> Path:
    """Metadata lives in its own subdirectory so the base directory contains
    prefixes and exactly one non-prefix, rather than loose files among them."""
    return base_dir() / MANAGER_SUBDIR


def registry_path() -> Path:
    return manager_dir() / "prefixes.json"


class InvalidName(ValueError):
    pass


class DuplicateName(ValueError):
    pass


class PathInUse(ValueError):
    pass


_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")


def validate_name(name: str) -> str:
    """Names end up as directory names and in desktop entries, so they are kept
    to something that survives both without quoting games."""
    name = (name or "").strip()
    if not _NAME_RE.match(name):
        raise InvalidName(
            "Use 1-64 characters: letters, digits, space, dot, underscore or "
            "hyphen, starting with a letter or digit."
        )
    return name


def dir_name(name: str) -> str:
    """Directory form of a name: spaces become underscores.

    Substituted rather than stripped, so 'Affinity 33' and 'Affinity33' cannot
    collapse onto the same directory and silently share a prefix."""
    cleaned = re.sub(r"[^A-Za-z0-9 ._-]+", "", name.strip())
    return re.sub(r"\s+", "_", cleaned).strip("_") or "prefix"


# Kept as an alias: dir_name says what it is for, slug is what callers reach for.
slug = dir_name


def path_for(name: str, base: Path | None = None) -> Path:
    """Where a managed prefix goes. Always directly under the base directory --
    a flat list of prefixes beside one Manager directory."""
    return (Path(base) if base else base_dir()) / dir_name(name)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Registry:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else registry_path()
        self.entries: list[dict] = []
        self.recovered_from_backup = False
        self.load()

    # ── persistence ──────────────────────────────────────────────────────────

    def load(self) -> None:
        if not self.path.is_file():
            self.entries = []
            return
        data = self._read(self.path)
        if data is None:
            # Try the copy kept by the previous save before giving up. A corrupt
            # registry must not take the application down with it, but it must
            # not silently empty the prefix list either.
            data = self._read(self.path.with_suffix(".json.bak"))
            self.recovered_from_backup = data is not None
        if data is None:
            self.entries = []
            return
        entries = data.get("prefixes", []) if isinstance(data, dict) else []
        self.entries = [e for e in entries if isinstance(e, dict) and e.get("path")]

    @staticmethod
    def _read(path: Path):
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": SCHEMA_VERSION, "prefixes": self.entries}

        # Keep the last good copy before replacing it. This file is the only
        # record that a prefix is managed at all, and load() used to answer a
        # corrupt one with an empty list -- every prefix silently forgotten,
        # with a comment calling that acceptable because they "can be
        # re-adopted". They can, by hand, if you still know where they were.
        if self.path.is_file():
            try:
                self.path.replace(self.path.with_suffix(".json.bak"))
            except OSError:
                pass

        # Write, flush to the platter, then rename. Without the fsync the
        # rename can land before the bytes do, and a power cut leaves a
        # correctly-named empty file -- which is the one failure this
        # write-and-rename was supposed to rule out.
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self.path)

    # ── queries ──────────────────────────────────────────────────────────────

    def by_name(self, name: str) -> dict | None:
        lowered = name.strip().lower()
        return next((e for e in self.entries if e["name"].lower() == lowered), None)

    def by_path(self, path) -> dict | None:
        target = str(Path(path).expanduser().resolve())
        for e in self.entries:
            try:
                if str(Path(e["path"]).expanduser().resolve()) == target:
                    return e
            except OSError:
                continue
        return None

    # ── mutation ─────────────────────────────────────────────────────────────

    def _check_slug(self, name: str, *, allow=None) -> None:
        """Two names must not reduce to one directory name.

        dir_name() substitutes rather than strips, so "Affinity 33" and
        "Affinity_33" are different names that produce the SAME slug -- and the
        slug is what names this prefix's snapshots directory, its log file, its
        MIME package and its icon. Removing one of the two would delete the
        other's, which is the collision every other check here exists to
        prevent, reached by the one route nothing was checking."""
        slug = dir_name(name).lower()
        for entry in self.entries:
            if allow is not None and entry["name"] == allow:
                continue
            if dir_name(entry["name"]).lower() == slug:
                raise DuplicateName(
                    f"{name!r} and {entry['name']!r} both become {dir_name(name)!r}, "
                    "which is the directory name used for snapshots, logs and "
                    "menu entries. Pick a name that differs by more than "
                    "punctuation.")

    def add(self, name: str, path, *, installer_file=None, notes="") -> dict:
        name = validate_name(name)
        if self.by_name(name):
            raise DuplicateName(f"A prefix named {name!r} is already managed.")
        self._check_slug(name)
        resolved = Path(path).expanduser()
        if self.by_path(resolved):
            raise PathInUse(f"{resolved} is already managed.")
        entry = {
            "name": name,
            "path": str(resolved),
            "created": _now(),
            "installer_file": str(installer_file) if installer_file else None,
            "notes": notes,
            "protected": False,
        }
        self.entries.append(entry)
        # Not set up yet, so the list says that rather than "missing from disk",
        # which is true of an empty directory and tells the user nothing.
        entry["state"] = "new"
        self.save()
        return entry

    def repoint(self, name: str, path) -> dict:
        """Say that a managed prefix now lives somewhere else.

        Separate from rename because the two are independent: a prefix can move
        and keep its name, which is what relocating an adopted ~/.AffinityLinux
        does. The path is checked against the other entries for the same reason
        add() checks it -- two names for one directory is a way to delete a
        prefix while believing you are deleting a different one."""
        entry = self.by_name(name)
        if entry is None:
            raise KeyError(name)
        resolved = str(Path(path).expanduser())
        clash = self.by_path(resolved)
        if clash is not None and clash is not entry:
            raise PathInUse(f"{resolved} is already managed as {clash['name']!r}.")
        entry["path"] = resolved
        entry["moved"] = _now()
        self.save()
        return entry

    def rename(self, old: str, new: str) -> dict:
        entry = self.by_name(old)
        if not entry:
            raise KeyError(old)
        new = validate_name(new)
        clash = self.by_name(new)
        if clash and clash is not entry:
            raise DuplicateName(f"A prefix named {new!r} is already managed.")
        self._check_slug(new, allow=old)
        entry["name"] = new
        self.save()
        return entry

    def set_protected(self, name: str, value: bool) -> dict:
        """Mark a prefix as not deletable.

        Deliberately stored on the entry rather than as a filesystem permission:
        it is a statement about what this application may do, and making the
        directory read-only would also stop Affinity writing to it."""
        entry = self.by_name(name)
        if not entry:
            raise KeyError(name)
        entry["protected"] = bool(value)
        self.save()
        return entry

    def set_carry(self, name: str, source) -> dict:
        """Remember (or, with None, forget) the prefix whose settings to copy
        into this one once it is ready. On the entry, so it survives the
        manager being closed between creating a prefix and finishing Configure."""
        entry = self.by_name(name)
        if not entry:
            raise KeyError(name)
        if source:
            entry["carry_from"] = str(source)
        else:
            entry.pop("carry_from", None)
        self.save()
        return entry

    # ── operation state ──────────────────────────────────────────────────────
    #
    # Written BEFORE the work starts and cleared after, so that a manager which
    # dies mid-operation leaves a row saying so. That is the whole point: the
    # disk can look finished because the operation got most of the way through,
    # and the only thing that knows otherwise is a record written in advance.
    #
    # log_offset is where the prefix's log had reached when the operation
    # began. One integer, and it is what lets a recovery message quote the
    # right part of a log instead of its last page.

    def set_working(self, name: str, operation: str, *, log_offset: int | None = None) -> dict:
        entry = self.by_name(name)
        if entry is None:
            raise KeyError(name)
        entry["state"] = "working"
        entry["operation"] = operation
        entry["operation_started"] = _now()
        if log_offset is not None:
            entry["log_offset"] = log_offset
        self.save()
        return entry

    def clear_state(self, name: str, *, keep_operation: bool = False) -> dict:
        """The operation finished. Forget it happened."""
        entry = self.by_name(name)
        if entry is None:
            raise KeyError(name)
        for key in ("state", "operation_started", "log_offset"):
            entry.pop(key, None)
        if not keep_operation:
            entry.pop("operation", None)
        self.save()
        return entry

    def recover(self) -> list[dict]:
        """Turn every row still marked working into incomplete.

        Called once at startup, and only after single-instance checking has
        established that no other manager is running -- so a row still saying
        working was written by one that is gone, and the operation it tracked
        cannot still be going.

        The operation name and log offset are kept: they are what the message
        about it is made of. Returns the rows that changed so the caller can
        say so rather than repairing it quietly."""
        from . import prefixstate

        changed = prefixstate.recover_interrupted(self.entries)
        if changed:
            self.save()
        return changed

    def forget(self, name: str) -> dict:
        """Stop managing a prefix. Never touches the directory -- deleting
        several hundred gigabytes is not something a list view should do as a
        side effect of tidying."""
        entry = self.by_name(name)
        if not entry:
            raise KeyError(name)
        self.entries.remove(entry)
        self.save()
        return entry

    def suggest_path(self, name: str) -> Path:
        return path_for(name)

    def suggest_name(self, when=None, base: Path | None = None) -> str:
        """The name offered for a new prefix: AffinityLinux YYYY-MM-DD 0N.

        Numbered in creation order within the day, and the number skips past
        anything already taken -- whether by a registry entry or by a directory
        sitting in the base that was never registered. Offering a name whose
        directory already exists would walk every new prefix straight into the
        collision dialog."""
        day = (when or datetime.now()).strftime("%Y-%m-%d")
        root = Path(base) if base else base_dir()
        taken_names = {e["name"].lower() for e in self.entries}
        try:
            taken_dirs = {d.name.lower() for d in root.iterdir()}
        except OSError:
            taken_dirs = set()
        for n in range(1, 100):
            candidate = f"AffinityLinux {day} {n:02d}"
            if candidate.lower() in taken_names:
                continue
            if dir_name(candidate).lower() in taken_dirs:
                continue
            return candidate
        # Ninety-nine in one day means something is wrong; fall back to a name
        # that is certainly free rather than returning a colliding one.
        return f"AffinityLinux {day} {datetime.now().strftime('%H%M%S')}"


# ── directory collisions ─────────────────────────────────────────────────────
#
# A new prefix whose directory already exists is not rare: names repeat, an
# earlier attempt failed halfway, or the base directory was used before. The
# three ways out are offered rather than chosen, because only the user knows
# whether what is there matters.


def aside_path(path) -> Path:
    """An unused name to move an existing directory to."""
    path = Path(path)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.old-{stamp}")
    n = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.old-{stamp}-{n}")
        n += 1
    return candidate


def rename_aside(path) -> Path:
    """Move an existing directory out of the way and return where it went.

    A rename, never a delete. What is being moved is usually a Wine prefix of
    several gigabytes that took an hour to build, and the user asked to keep
    the name, not to destroy the contents."""
    path = Path(path)
    target = aside_path(path)
    path.rename(target)
    return target


def describe_collision(path) -> dict:
    """What is sitting at a path, in the terms the dialog needs to explain it."""
    from . import probe

    path = Path(path).expanduser()
    if not path.exists():
        return {"exists": False}
    try:
        entries = list(path.iterdir())
    except OSError:
        entries = []
    return {
        "exists": True,
        "empty": not entries,
        "is_prefix": probe.is_prefix(path),
        "has_affinity": probe.has_affinity(path),
        "affinity_version": probe.affinity_version(path),
        "managed": False,  # filled in by the caller, which has the registry
        "entry_count": len(entries),
    }


def is_protected(entry) -> bool:
    return bool(entry.get("protected"))
