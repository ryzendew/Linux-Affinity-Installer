"""Host-side artifacts, and which prefix each one belongs to.

Installing Affinity writes things outside the prefix: a menu entry, MIME type
definitions, icons, and the desktop's choice of which application opens a
document. All of those have fixed names, so a second install rewrites the first
one's -- which is how a test prefix ends up owning the file associations of the
prefix somebody works in.

This module answers, for every one of those artifacts, "whose is it?". Three
answers, and the distinction is the whole point:

    OURS     written by this application and tagged with the prefix it serves
    FOREIGN  somebody else's -- AffinityOnLinux's Affinity.desktop,
             winemenubuilder's x-wine-extension-*.xml, a hand-made launcher
    SHARED   one global setting with one value, so it cannot belong to a
             prefix at all: the default handler for a document type

Reading, editing and removing are here too, because an asset browser needs all
three and the attribution rules are what make them safe: an edit or a delete of
a FOREIGN artifact is allowed but never silent, and every write moves the
previous copy aside first rather than overwriting it.
FOREIGN artifacts exist in the output so a removal plan can say "left alone,
not ours" rather than silently skipping them -- a list that omits what it will
not touch is not a list you can check.

See docs/prefix-separation.md for the rules this implements.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import desktopentry, registry

OURS, FOREIGN, SHARED = "ours", "foreign", "shared"

# The document types Affinity claims. Global identities: application/afphoto
# means the same thing whichever prefix opens it, so these are never duplicated
# per prefix. What varies per prefix is the handler, which is SHARED.
DOCUMENT_TYPES = (
    "application/af",
    "application/afdesign",
    "application/afphoto",
    "application/afpub",
)

# Marker written into the MIME packages and read back to attribute them. XML
# comment rather than an element, so the file stays a valid MIME package that
# update-mime-database will accept unchanged.
MIME_MARKER = "X-AffinityManager-Prefix"


@dataclass
class Artifact:
    kind: str           # menu | mime | icon | default-handler | registry
    path: Path | None   # None for things that are not files
    owner: str          # OURS | FOREIGN | SHARED
    prefix: str | None  # the prefix name, when we can attribute it
    detail: str
    size: int = 0
    value: str | None = None    # for a default-handler: the .desktop it names


def _data_home() -> Path:
    value = os.environ.get("XDG_DATA_HOME", "").strip()
    return Path(value).expanduser() if value else Path.home() / ".local" / "share"


def _config_home() -> Path:
    value = os.environ.get("XDG_CONFIG_HOME", "").strip()
    return Path(value).expanduser() if value else Path.home() / ".config"


def mimeapps_files() -> list[Path]:
    """Where a default handler is actually recorded.

    The current location and the one that still works. xdg-mime writes the
    first; plenty of systems have the second from older tools, and a stale
    entry there wins on some desktops, so both are read and both are cleaned."""
    return [_config_home() / "mimeapps.list",
            _data_home() / "applications" / "mimeapps.list"]


def applications_dir() -> Path:
    return desktopentry.applications_dir()


def mime_packages_dir() -> Path:
    return _data_home() / "mime" / "packages"


def icons_dir() -> Path:
    return _data_home() / "icons"


def mime_path(prefix_name: str) -> Path:
    """Where this prefix's MIME package goes.

    Deliberately not winemenubuilder's x-wine-extension-<ext>.xml scheme: it
    generates those for every association a prefix registers, and sharing the
    naming means one of us silently overwrites the other's file."""
    return mime_packages_dir() / f"affinity-{registry.dir_name(prefix_name)}-documents.xml"


def icon_path(prefix_name: str) -> Path:
    return icons_dir() / f"affinity-{registry.dir_name(prefix_name)}.svg"


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def mime_owner(path: Path) -> tuple[str, str | None]:
    """(owner, prefix name) for a MIME package."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return FOREIGN, None
    match = re.search(rf"{MIME_MARKER}:\s*(.+?)\s*(?:--)?>", text)
    if match:
        return OURS, match.group(1).strip()
    return FOREIGN, None


def default_handlers() -> list[Artifact]:
    """What the desktop currently opens Affinity documents with.

    One value per type, system-wide. Reported as SHARED because no prefix owns
    it -- and because changing it is the one action here that takes something
    away from another prefix, so it must be asked for rather than assumed."""
    out = []
    for mime in DOCUMENT_TYPES:
        try:
            result = subprocess.run(["xdg-mime", "query", "default", mime],
                                    capture_output=True, text=True, timeout=15)
            value = result.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            value = None
        out.append(Artifact(
            kind="default-handler", path=None, owner=SHARED, prefix=None,
            detail=f"{mime} opens with {value or 'nothing'}", value=value,
        ))
    return out


def handler_prefix(handlers=None) -> str | None:
    """The prefix that currently owns the document types, if we can tell.

    Only answerable when the handler is one of our own entries: the name is in
    the file. When it is AffinityOnLinux's fixed-name Affinity.desktop the
    answer is genuinely unknown -- the entry says which prefix its Exec drives,
    but that prefix may not be one we know about, and the file is rewritten by
    every install."""
    for artifact in (handlers if handlers is not None else default_handlers()):
        if not artifact.value:
            continue
        candidate = applications_dir() / artifact.value
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(errors="replace")
        except OSError:
            continue
        match = re.search(rf"{desktopentry.MARKER}=(.+)", text)
        if match:
            return match.group(1).strip()
    return None


def artifacts_for(prefix_name: str) -> list[Artifact]:
    """Everything on the host that belongs to this prefix."""
    out: list[Artifact] = []

    for path in desktopentry.entries_for(prefix_name):
        out.append(Artifact("menu", path, OURS, prefix_name,
                            f"Menu entry: {path.name}", _size(path)))

    mime = mime_path(prefix_name)
    if mime.exists():
        owner, named = mime_owner(mime)
        out.append(Artifact("mime", mime, owner, named or prefix_name,
                            f"Document type definitions for {prefix_name}", _size(mime)))

    icon = icon_path(prefix_name)
    if icon.exists():
        out.append(Artifact("icon", icon, OURS, prefix_name,
                            f"Icon: {icon.name}", _size(icon)))

    return out


def foreign_artifacts() -> list[Artifact]:
    """Affinity-related things on the host that are not ours.

    Listed so a plan can say what it is leaving alone. AffinityOnLinux's
    Affinity.desktop lands here by design: it has a fixed name, every install
    rewrites it, and it is not the manager's to manage."""
    out: list[Artifact] = []

    apps = applications_dir()
    if apps.is_dir():
        for path in sorted(apps.glob("*.desktop")):
            if "affinity" not in path.name.lower():
                continue
            if desktopentry.is_ours(path):
                continue
            out.append(Artifact("menu", path, FOREIGN, None,
                                f"Not ours: {path.name}", _size(path)))

    packages = mime_packages_dir()
    if packages.is_dir():
        for path in sorted(packages.glob("*.xml")):
            text_owner, _ = mime_owner(path)
            if text_owner == OURS:
                continue
            try:
                body = path.read_text(errors="replace")
            except OSError:
                continue
            if not any(t in body for t in DOCUMENT_TYPES):
                continue
            out.append(Artifact("mime", path, FOREIGN, None,
                                f"Not ours: {path.name}", _size(path)))

    return out


# ─────────────────────────────────────────────────────────── viewing and editing


class NotOurs(PermissionError):
    """Refused because the artifact belongs to somebody else.

    Overridable with force=True -- the user is allowed to edit AffinityOnLinux's
    Affinity.desktop if that is what they meant -- but never by default, and
    never without the previous copy being kept."""


def all_artifacts(prefix_names=()) -> list[Artifact]:
    """Every Affinity-related artifact on the host, ours and not.

    The one list an asset browser shows. Ours come first, grouped by prefix,
    then the foreign ones, then the shared handlers -- which have no file and so
    can be inspected but not edited here."""
    out: list[Artifact] = []
    for name in prefix_names:
        out.extend(artifacts_for(name))
    out.extend(foreign_artifacts())
    out.extend(default_handlers())
    return out


def read(artifact: Artifact) -> str:
    """The artifact's text, for viewing or editing."""
    if artifact.path is None:
        raise ValueError(f"{artifact.kind} has no file to read")
    return artifact.path.read_text(errors="replace")


def write(artifact: Artifact, text: str, *, force: bool = False) -> Path:
    """Replace an artifact's text, keeping the previous copy.

    Returns where the previous copy went, so a caller can say so. The old copy
    is a rename rather than a backup written afterwards: if the write fails
    half way, what is on disk is still one whole file, not a blend of two."""
    if artifact.path is None:
        raise ValueError(f"{artifact.kind} has no file to write")
    if artifact.owner != OURS and not force:
        raise NotOurs(
            f"{artifact.path.name} was not written by this application. "
            "Editing it is allowed, but has to be asked for."
        )
    kept = None
    if artifact.path.exists():
        kept = registry.aside_path(artifact.path)
        artifact.path.rename(kept)
    try:
        artifact.path.write_text(text)
    except OSError:
        # Put it back. A failed edit must not leave the artifact missing.
        if kept is not None and kept.exists() and not artifact.path.exists():
            kept.rename(artifact.path)
        raise
    return kept


def delete(artifact: Artifact, *, force: bool = False) -> Path | None:
    """Remove an artifact, keeping a copy aside.

    Returns where the copy went. Nothing here is large -- a desktop entry is a
    kilobyte -- so there is no reason to make this unrecoverable."""
    if artifact.path is None:
        raise ValueError(f"{artifact.kind} is not a file and cannot be deleted here")
    if artifact.owner != OURS and not force:
        raise NotOurs(
            f"{artifact.path.name} was not written by this application. "
            "Removing it is allowed, but has to be asked for."
        )
    if not artifact.path.exists():
        return None
    kept = registry.aside_path(artifact.path)
    artifact.path.rename(kept)
    return kept


def clear_handlers(entry_name: str, types=DOCUMENT_TYPES) -> list[str]:
    """Stop these document types being opened by one .desktop entry.

    There is no `xdg-mime unset`. Setting a default is a command; removing one
    is editing the file the command writes, so that is what this does -- the
    [Default Applications] section of mimeapps.list, dropping this entry from
    each type's list and dropping the line when nothing is left.

    This matters at removal time. Deleting a prefix whose entry holds the
    association leaves mimeapps.list naming a .desktop that no longer exists,
    and the symptom is that double-clicking a document does nothing at all,
    with nothing to indicate why.

    Only lines naming this entry are touched, so a type somebody else's
    application holds is left exactly as it was."""
    changed: list[str] = []
    wanted = set(types)

    for path in mimeapps_files():
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue

        out, section, edited = [], "", False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                section = stripped
                out.append(line)
                continue
            if section != "[Default Applications]" or "=" not in line:
                out.append(line)
                continue
            mime, _, value = line.partition("=")
            if mime.strip() not in wanted:
                out.append(line)
                continue
            kept = [e for e in value.split(";") if e.strip() and e.strip() != entry_name]
            if len(kept) == len([e for e in value.split(";") if e.strip()]):
                out.append(line)                    # this entry was not named
                continue
            edited = True
            if kept:
                out.append("%s=%s;" % (mime.strip(), ";".join(kept)))
                changed.append("%s no longer opens with %s" % (mime.strip(), entry_name))
            else:
                changed.append("%s has no default handler now" % mime.strip())

        if edited:
            try:
                path.write_text("\n".join(out) + "\n")
            except OSError as exc:
                changed.append("could not rewrite %s: %s" % (path, exc))
    return changed


# ───────────────────────────────────────────── who opens Affinity documents


@dataclass
class HandoverPlan:
    """What changing the document association would do.

    Shown before anything is called, because this is the one action here that
    takes something away from another prefix: there is exactly one default
    handler per MIME type, system-wide."""
    to_prefix: str
    entry: str                          # the .desktop that would become default
    from_prefix: str | None             # the prefix losing it, if we can tell
    from_entry: str | None              # what is default now
    types: tuple = DOCUMENT_TYPES
    foreign_current: bool = False       # current handler is not one of ours

    @property
    def summary(self) -> str:
        if self.from_entry is None:
            return f"Affinity documents will open in {self.to_prefix}."
        if self.from_prefix:
            return (f"Affinity documents open in {self.from_prefix} now. "
                    f"They would open in {self.to_prefix} instead.")
        return (f"Affinity documents are handled by {self.from_entry}, which this "
                f"application did not create. They would open in {self.to_prefix} "
                f"instead.")


def plan_handover(prefix_name: str, command_label: str, handlers=None) -> HandoverPlan:
    """Work out what pointing the document types at this prefix would change.

    Nothing is called. The caller shows plan.summary, and only then applies it."""
    entry = desktopentry.entry_path(prefix_name, command_label)
    current = handlers if handlers is not None else default_handlers()
    from_entry = next((a.value for a in current if a.value), None)
    from_prefix = handler_prefix(current)
    return HandoverPlan(
        to_prefix=prefix_name,
        entry=entry.name,
        from_prefix=from_prefix,
        from_entry=from_entry,
        foreign_current=bool(from_entry) and from_prefix is None,
    )


def apply_handover(plan: HandoverPlan) -> list[str]:
    """Make the prefix in the plan the handler for Affinity documents.

    One xdg-mime call per type, and the desktop database records the choice --
    so it survives without this application running, which a dispatcher process
    would not."""
    entry = applications_dir() / plan.entry
    if not entry.is_file():
        raise FileNotFoundError(
            f"{plan.entry} does not exist; write the menu entry for "
            f"{plan.to_prefix} before making it the default handler."
        )
    problems: list[str] = []
    for mime in plan.types:
        try:
            result = subprocess.run(["xdg-mime", "default", plan.entry, mime],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                problems.append(
                    f"{mime}: xdg-mime exited {result.returncode}"
                    + (f" ({result.stderr.strip().splitlines()[-1]})"
                       if result.stderr.strip() else "")
                )
        except (OSError, subprocess.SubprocessError) as exc:
            problems.append(f"{mime}: {exc}")
    desktopentry.refresh_menu()
    return problems
