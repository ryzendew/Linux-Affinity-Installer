"""Removing a prefix: everything it put on the host, itemised.

Removal used to be `shutil.rmtree(path)` and dropping the registry row. The
menu entry, the MIME package, the icon and the document defaults were all left
behind -- so deleting a prefix left a menu entry that launched nothing and, if
that prefix held the document association, double-clicking an .afphoto did
nothing at all with no indication why.

Same shape as maintenance.Plan: computed, shown, and only then executed. Every
row says what it is, where it is, how big it is, and why it is proposed. **The
confirmation is the list, not a yes/no on a summary** -- a summary is where
"and 4 other items" hides the one you would have objected to.

Two defaults are deliberate and are not symmetrical with the rest:

  settings-backup   unticked. Losing the backups of a thing along with the
                    thing is the wrong default, and they are kilobytes.
  foreign           not offered at all. Anything without our marker belongs to
                    somebody else -- AffinityOnLinux's own Affinity.desktop
                    lands here by design -- and is listed as left alone so the
                    plan can say what it did not do.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import desktopentry, hoststate, prefixlog, probe, registry, snapshots

# Ticked unless said otherwise. The order is the order they are shown in, and
# it goes from the biggest and most obvious to the most easily overlooked.
KINDS = ("prefix", "menu", "mime", "icon", "default-handler", "registry",
         "log", "settings-backup")

UNTICKED = ("settings-backup",)


@dataclass
class Item:
    kind: str
    label: str              # what it is, for the row
    detail: str             # why it is proposed, or what it reverts to
    path: Path | None
    size: int = 0
    default: bool = True
    artifact: object = None     # a hoststate.Artifact, where there is one
    snapshot: object = None     # a snapshots.Snapshot, where there is one
    value: str = ""             # for a default-handler: the .desktop it names


@dataclass
class Plan:
    name: str
    path: Path
    items: list = field(default_factory=list)
    left_alone: list = field(default_factory=list)
    running: list = field(default_factory=list)

    @property
    def size(self) -> int:
        return sum(i.size for i in self.items if i.default)

    def chosen(self, kinds=None) -> list:
        if kinds is None:
            return [i for i in self.items if i.default]
        return [i for i in self.items if i.kind in kinds]


def plan(reg, name: str) -> Plan:
    """What removing this prefix would take with it. Touches nothing."""
    entry = reg.by_name(name)
    if entry is None:
        raise KeyError(name)
    path = Path(entry["path"]).expanduser()

    out = Plan(name, path, running=probe.running_pids(path) if path.exists() else [])

    if path.exists():
        out.items.append(Item(
            "prefix", str(path),
            "The prefix directory itself, and everything installed in it",
            path, probe.disk_usage(path)))
    else:
        out.items.append(Item(
            "prefix", str(path), "Not there any more; nothing to remove",
            None, 0, default=False))

    # The host-side artifacts we can attribute. artifacts_for reports the
    # owner, and anything not OURS is reported rather than offered -- even
    # under this prefix's own name, because the name is in a file anybody
    # could have written.
    for artifact in hoststate.artifacts_for(name):
        if artifact.owner != hoststate.OURS:
            out.left_alone.append(artifact)
            continue
        out.items.append(Item(artifact.kind, str(artifact.path),
                              artifact.detail, artifact.path, artifact.size,
                              artifact=artifact))

    # The document defaults, but only the ones that point here. There is one
    # default per MIME type system-wide, so removing a prefix that holds them
    # has to say what happens next: nothing else takes over by itself.
    ours = {p.name for p in desktopentry.entries_for(name)}
    for handler in hoststate.default_handlers():
        if handler.value not in ours:
            continue
        out.items.append(Item(
            "default-handler", handler.detail,
            "Removes the association from mimeapps.list. After this, nothing "
            "opens that type until you set a handler",
            None, 0, artifact=handler, value=handler.value))

    out.items.append(Item(
        "registry", "The row in prefixes.json",
        "Removes it from the list. On its own this leaves the directory alone",
        None, 0))

    log = prefixlog.path_for(name)
    if log.exists():
        out.items.append(Item(
            "log", str(log), "This prefix's operation log",
            log, log.stat().st_size))

    kept = snapshots.listing(name)
    if kept:
        total = sum(s.bytes for s in kept)
        root = snapshots.dir_for(name)
        out.items.append(Item(
            "settings-backup", f"{len(kept)} settings snapshot(s) in {root}",
            "Unticked on purpose: losing the backups with the thing they back "
            "up is the wrong default, and they are kilobytes",
            root, total, default=False))

    out.left_alone += hoststate.foreign_artifacts()
    return out


def apply(reg, plan_: Plan, chosen) -> list[str]:
    """Remove the chosen items, and say what happened to each.

    Order matters. The directory goes first, because that is the slow part and
    the one worth knowing failed before anything else has been dropped; the
    registry row goes last, because until it is gone the prefix is still
    findable and a partial removal can be finished by running this again.

    Nothing raises. A removal that stops half way because one desktop file was
    read-only would be worse than one that reports it."""
    kinds = {i.kind for i in chosen}
    done: list[str] = []

    # Asked again, now. plan_.running was read when the dialog was built, and
    # the dialog can sit open for as long as somebody reads it -- long enough
    # to double-click a document and have the desktop start Affinity in the
    # very prefix being removed, which is not far-fetched when the plan's own
    # default-handler rows say this prefix is what opens them.
    from . import liveness

    now = liveness.scan(plan_.path) if plan_.path.exists() else None
    if now is not None and now.state != liveness.QUIET and \
            any(i.kind == "prefix" for i in chosen):
        # Leftovers too, when the directory itself is going: they have it open.
        return [f"{now.summary()} Nothing was removed."]
    live = now.running_pids if now is not None else []
    if live or plan_.running:
        pid = (live or plan_.running)[0]
        return [f"Affinity is running in {plan_.name} (pid {pid}). "
                "Nothing was removed."]

    for item in chosen:
        if item.kind != "prefix" or item.path is None:
            continue
        try:
            shutil.rmtree(item.path)
            done.append(f"Removed {item.path}")
        except OSError as exc:
            done.append(f"Could not remove {item.path}: {exc}")

    # The document defaults, which are not files and cannot be deleted like
    # one. hoststate.delete raises ValueError for a path-less artifact, and
    # that ValueError used to escape this function entirely -- after the
    # prefix directory had already been removed, so the registry row survived
    # and the manager still listed a prefix that was no longer there.
    for item in chosen:
        if item.kind != "default-handler":
            continue
        try:
            notes = hoststate.clear_handlers(item.value) if item.value else []
            done += notes or [f"{item.label} was not recorded anywhere"]
        except Exception as exc:                 # apply() does not raise
            done.append(f"Could not clear {item.label}: {exc}")

    for item in chosen:
        if item.kind in ("prefix", "registry", "settings-backup",
                         "default-handler"):
            continue
        if item.artifact is not None:
            try:
                removed = hoststate.delete(item.artifact)
                done.append(f"Kept a copy and removed {item.label}" if removed
                            else f"{item.label} was already gone")
            except Exception as exc:             # apply() does not raise
                done.append(f"Left {item.label}: {exc}")
            continue
        if item.path is not None:
            try:
                item.path.unlink()
                done.append(f"Removed {item.path}")
            except OSError as exc:
                done.append(f"Could not remove {item.path}: {exc}")

    for item in chosen:
        if item.kind != "settings-backup" or item.path is None:
            continue
        try:
            shutil.rmtree(item.path)
            done.append(f"Removed the snapshots in {item.path}")
        except OSError as exc:
            done.append(f"Could not remove {item.path}: {exc}")

    if kinds & {"menu", "mime", "default-handler"}:
        try:
            desktopentry.refresh_menu()
            done.append("Rebuilt the desktop and MIME databases")
        except Exception as exc:                 # apply() does not raise
            done.append(f"Could not rebuild the desktop databases: {exc}")

    if "registry" in kinds:
        try:
            reg.forget(plan_.name)
            done.append(f"Removed {plan_.name} from the list")
        except KeyError:
            done.append(f"{plan_.name} was no longer in the list")
        except Exception as exc:                 # apply() does not raise
            done.append(f"Could not update the list: {exc}")

    for artifact in plan_.left_alone:
        done.append(f"Left alone, not ours: {artifact.path or artifact.detail}")
    return done
