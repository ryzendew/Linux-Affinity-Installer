"""Renaming a managed prefix, and moving its folder to match.

A prefix's name is more than the label in the list. Four other things are
keyed by it, and a rename that changed only the registry would orphan them:

  - its log, logs/<dir name>.log (and the rotated .1);
  - its snapshots, snapshots/<dir name>/;
  - the menu entries this application wrote for it: their file names carry
    the name, and the X-AffinityManager-Prefix line is how removing the prefix
    later finds them (desktopentry.entries_for);
  - the Default's fixed-name entries, when this prefix is the Default, whose
    X-AffinityManager-Default line is what the manager reads back.

Renaming never moves the folder. move() does that as a second, separate step:
only within one filesystem (a rename(2), instant and atomic), only with
nothing running in the prefix, and followed by every launcher and desktop
entry that names the old path (maintenance.repoint_launchers, a copy of each
kept beside it).

When the prefix is the Default, both re-apply the Default rather than editing
its entries: that rewrites the menu entry's Exec, Path, comment and markers,
the sign-in handler, and the document associations, from the same code that
made it the Default.
"""

from __future__ import annotations

from pathlib import Path

from affinity_manager import (defaultentry, desktopentry, maintenance, prefixlog,
                              registry, snapshots)


class CannotMove(RuntimeError):
    """The folder cannot be moved from here; the message says why."""


def rename(reg: registry.Registry, old: str, new: str) -> list[str]:
    """Rename `old` to `new` everywhere it is a key. Returns notes on anything
    left as it was. Raises what Registry.rename raises, before touching
    anything, when the new name is invalid or taken."""
    entry = reg.by_name(old)
    if entry is None:
        raise KeyError(old)
    menu_files = desktopentry.entries_for(old)
    was_default = defaultentry.current() == old
    old_log = prefixlog.path_for(old)
    old_snaps = snapshots.dir_for(old)

    reg.rename(old, new)                     # validates; nothing changed if it raises
    notes: list[str] = []

    new_log = prefixlog.path_for(new)
    if old_log != new_log:
        for suffix in ("", ".1"):
            src = Path(f"{old_log}{suffix}")
            dst = Path(f"{new_log}{suffix}")
            if not src.exists():
                continue
            if dst.exists():
                notes.append(f"{dst.name} already exists, so the old log stays as {src.name}.")
                continue
            src.rename(dst)
        if entry.get("log") == str(old_log):
            entry["log"] = str(new_log)
            reg.save()

    new_snaps = snapshots.dir_for(new)
    if old_snaps != new_snaps and old_snaps.is_dir():
        if new_snaps.exists():
            notes.append(f"Snapshots for {new!r} already exist, so the old ones stay in {old_snaps}.")
        else:
            old_snaps.rename(new_snaps)

    if was_default:
        fixed = (defaultentry.main_entry(), defaultentry.url_handler())
        refreshed = _refresh_default(new, entry["path"], notes)
        if refreshed:
            menu_files = [f for f in menu_files if f not in fixed]
    for path in menu_files:
        notes += _rename_entry(path, old, new)
    if menu_files:
        desktopentry.refresh_menu()
    return notes


def move(reg: registry.Registry, name: str, dest) -> list[str]:
    """Move a managed prefix's folder to `dest` and make everything follow.

    Ordered so that a failure leaves the truth on disk: the folder moves first,
    then the launchers, and only then the registry entry."""
    entry = reg.by_name(name)
    if entry is None:
        raise KeyError(name)
    src = Path(entry["path"]).expanduser()
    dst = Path(dest).expanduser()
    if src == dst:
        return []
    try:
        plan = maintenance.plan_relocate(src, dst)
    except (maintenance.NotAPrefix, maintenance.DestinationInUse,
            maintenance.NotEnoughSpace) as exc:
        raise CannotMove(str(exc)) from exc
    if not plan.same_filesystem:
        raise CannotMove(
            f"{dst.parent} is on a different filesystem from {src}, so this would "
            "be a copy of several gigabytes, not a rename. Use Clone for that.")
    was_default = defaultentry.current() == name
    try:
        notes = maintenance.relocate(plan)
    except (maintenance.Busy, maintenance.CloneFailed, maintenance.NotAPrefix,
            maintenance.DestinationInUse) as exc:
        raise CannotMove(str(exc)) from exc
    # The manager's own entries are in desktopentry.applications_dir(), which
    # follows XDG_DATA_HOME; LAUNCHER_DIRS spells ~/.local/share. Both, so a set
    # XDG_DATA_HOME cannot leave the menu entries naming the old folder.
    # Wine's own Start-menu entries live in subfolders (applications/wine/
    # Programs/...), with WINEPREFIX=<path> in their Exec; the scan is flat.
    apps = desktopentry.applications_dir()
    dirs = list(maintenance.LAUNCHER_DIRS) + [str(apps)]
    for base in (apps / "wine", Path("~/.local/share/applications/wine").expanduser()):
        if base.is_dir():
            dirs += [str(d) for d in sorted(base.rglob("*")) if d.is_dir()]
    notes += maintenance.repoint_launchers(src, dst, dirs=dirs)
    reg.repoint(name, dst)
    if was_default:
        _refresh_default(name, dst, notes)
    return notes


def _refresh_default(name: str, path, notes: list[str]) -> bool:
    try:
        notes += defaultentry.apply(defaultentry.plan(name, path))
    except (OSError, ValueError, FileNotFoundError) as exc:
        notes.append(f"The Default's menu entry could not be rewritten ({exc}); "
                     "use Make Default on it again.")
        return False
    return True


def _rename_entry(path: Path, old: str, new: str) -> list[str]:
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        return [f"Could not read {path.name}: {exc}"]
    out = []
    for line in lines:
        key, sep, value = line.partition("=")
        key = key.strip()
        if sep and key in (desktopentry.MARKER, defaultentry.DEFAULT_MARKER) and value.strip() == old:
            line = f"{key}={new}"
        elif sep and key == "Name":
            if value == defaultentry.menu_name(old):
                line = f"Name={defaultentry.menu_name(new)}"
            elif value.endswith(f" ({old})"):
                line = f"Name={value[:-len(old) - 3]} ({new})"
        elif sep and key == "Comment" and value == f"Affinity in the {old} prefix":
            line = f"Comment=Affinity in the {new} prefix"
        out.append(line)
    text = "\n".join(out) + "\n"

    target = path
    prefix = f"affinity-manager-{desktopentry._slug(old)}-"
    if path.name.startswith(prefix):
        target = path.with_name(f"affinity-manager-{desktopentry._slug(new)}-"
                                + path.name[len(prefix):])
        if target.exists() and target != path:
            path.write_text(text)
            return [f"{target.name} already exists, so {path.name} keeps its file name."]
    target.write_text(text)
    if target != path:
        path.unlink()
    return []
