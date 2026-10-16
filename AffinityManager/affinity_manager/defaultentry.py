"""The Default Affinity: the menu's "Affinity" entry, and what opens documents.

There is one fixed-name Affinity.desktop, one default handler for each Affinity
document type and one for affinity:// (the Canva sign-in callback), system-wide.
AffinityOnLinux used to rewrite all of them on every install, so setting up a
second prefix took them away from the prefix being worked in. Hosted by the
manager it no longer writes them; the manager does, here, for whichever managed
prefix the user makes the Default -- rule 3 of docs/prefix-separation.md: a
global choice is only ever changed by being asked for.

Every other managed prefix can still have a menu entry of its own, named after
it (desktopentry). Those never take the document types: click-to-open always
goes to the Default.

Entries written here carry both markers: DEFAULT_MARKER, so the Default can be
read back, and desktopentry.MARKER, so removing that prefix knows the entries
are its own. A copy written by somebody else -- AffinityOnLinux run on its own,
a hand-made launcher -- is moved aside into the manager's directory before it
is replaced, never deleted.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import commands, desktopentry, hoststate, probe, registry

DEFAULT_MARKER = "X-AffinityManager-Default"
MAIN = "Affinity.desktop"
URL_HANDLER = "affinity-url-handler.desktop"
URL_SCHEME = "x-scheme-handler/affinity"
DOCUMENT_TYPES = hoststate.DOCUMENT_TYPES
MENU_LABEL = "Affinity"     # the command label behind each prefix's named entry


def main_entry() -> Path:
    return desktopentry.applications_dir() / MAIN


def url_handler() -> Path:
    return desktopentry.applications_dir() / URL_HANDLER


def backup_dir() -> Path:
    return registry.manager_dir() / "host-backups"


def _marker(path: Path, key: str) -> str | None:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None
    match = re.search(rf"^{re.escape(key)}=(.+)$", text, re.M)
    return match.group(1).strip() if match else None


def current() -> str | None:
    """The managed prefix that is the Default, or None."""
    return _marker(main_entry(), DEFAULT_MARKER)


def launched_prefix(path: Path) -> str | None:
    """The WINEPREFIX a desktop entry runs, as written, or None."""
    exec_line = _marker(path, "Exec") or ""
    match = re.search(r"""WINEPREFIX=(?:"([^"]+)"|'([^']+)'|(\S+))""", exec_line)
    return next((g for g in match.groups() if g), None) if match else None


# ── what to run ──────────────────────────────────────────────────────────────

def launch_command(prefix) -> tuple[commands.Command, bool]:
    """How this prefix's Affinity is started from a menu, and whether that
    command takes documents.

    affinity-on-linux.exe first: it converts a document's path and hands it to a
    running instance, and still starts Affinity through AffinityHook.exe, so the
    plugins load either way. Then AffinityHook.exe, then Affinity.exe. Wine is
    the prefix's ElementalWarriorWine link, so switching the prefix's Wine build
    does not leave the entry on the old one."""
    prefix = Path(prefix).expanduser()
    app = prefix / probe.AFFINITY_SUBDIR
    link = prefix / "ElementalWarriorWine"
    wine = link / "bin" / "wine"
    build = link.resolve().name if link.exists() else ""
    if not wine.is_file():
        builds = probe.wine_builds(prefix)
        if not builds:
            raise FileNotFoundError(f"No Wine build in {prefix}")
        build = builds[0]
        wine = prefix / build / "bin" / "wine"
    for exe_name in ("affinity-on-linux.exe", "AffinityHook.exe", "Affinity.exe"):
        exe = app / exe_name
        if exe.is_file():
            break
    else:
        raise FileNotFoundError(f"Affinity is not installed in {prefix}")
    command = commands.Command(
        group="Menu",
        label=MENU_LABEL,
        detail=f"Affinity in {prefix.name}",
        argv=[wine, exe],
        env={"WINEPREFIX": str(prefix), **commands.affinity_env(build)},
    )
    return command, exe.name == "affinity-on-linux.exe"


def sign_in_supported(prefix) -> bool:
    """Can this prefix's Wine take the Canva sign-in callback?

    Wine 9 and 10 can; on 11.x only a build that resolves WinRT namespaces --
    the builds with the Affinity patches, and upstream from 11.19. Elsewhere the
    callback crashes the running Affinity, so no handler is better."""
    command, _ = launch_command(prefix)
    wine = Path(command.argv[0])
    wintypes = wine.parent.parent / "lib" / "wine" / "x86_64-windows" / "wintypes.dll"
    try:
        data = wintypes.read_bytes()
        if any(n.encode("utf-16-le") in data for n in ("WinMetadata", "WinMetaData")):
            return True
    except OSError:
        pass
    version = commands.wine_build_version(wine.parent.parent.name)
    return version is not None and version[0] in (9, 10)


# ── the change ───────────────────────────────────────────────────────────────

@dataclass
class DefaultPlan:
    """What making a prefix the Default would change. Shown before applying."""
    to_name: str
    to_path: Path
    from_name: str | None           # the managed prefix that is Default now
    from_launches: str | None       # the prefix the current entry runs, if not ours
    foreign: bool                   # there is an entry, and we did not write it
    sign_in: bool                   # the affinity:// handler follows too

    @property
    def summary(self) -> str:
        if self.from_name == self.to_name:
            text = f"{self.to_name} is already the Default; its entries will be rewritten."
        elif self.from_name:
            text = (f"The Default is {self.from_name} now. The menu's Affinity entry and "
                    f"double-clicked documents would open {self.to_name} instead.")
        elif self.foreign:
            where = f", which runs {self.from_launches}" if self.from_launches else ""
            text = (f"The menu's Affinity entry was not written by the manager{where}. "
                    f"It would be moved aside, and the entry and double-clicked "
                    f"documents would open {self.to_name}.")
        else:
            text = f"The menu's Affinity entry and double-clicked documents will open {self.to_name}."
        if not self.sign_in:
            text += (f"\n\nCanva sign-in stays where it is: {self.to_name}'s Wine "
                     "cannot take the sign-in callback.")
        return text


def plan(name: str, path) -> DefaultPlan:
    entry = main_entry()
    exists = entry.is_file()
    ours = exists and _marker(entry, DEFAULT_MARKER) is not None
    return DefaultPlan(
        to_name=name,
        to_path=Path(path).expanduser(),
        from_name=_marker(entry, DEFAULT_MARKER),
        from_launches=None if ours else launched_prefix(entry),
        foreign=exists and not ours,
        sign_in=sign_in_supported(path),
    )


def _set_aside(path: Path, notes: list[str]) -> None:
    """Move somebody else's copy into the manager's directory, dated."""
    if not path.is_file() or _marker(path, DEFAULT_MARKER) is not None:
        return
    dest = backup_dir() / f"{path.name}.{time.strftime('%Y%m%d-%H%M%S')}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    path.replace(dest)
    notes.append(f"{path.name} was not the manager's; moved to {dest}")


def _exec(command, field: str) -> str:
    return f"{desktopentry.exec_line(command)} {field}".rstrip()


def _write(path: Path, lines: list[str]) -> None:
    tmp = path.with_name(path.name + ".new")
    tmp.write_text("\n".join(lines) + "\n")
    tmp.replace(path)


def xdg_mime_default(entry_name: str, mime: str) -> str | None:
    """Set one default handler; an error message, or None."""
    try:
        result = subprocess.run(["xdg-mime", "default", entry_name, mime],
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"{mime}: {exc}"
    if result.returncode != 0:
        return f"{mime}: xdg-mime exited {result.returncode}"
    return None


def apply(p: DefaultPlan) -> list[str]:
    """Make the prefix in the plan the Default. Returns notes for the user."""
    command, takes_files = launch_command(p.to_path)
    notes: list[str] = []
    apps = desktopentry.applications_dir()
    apps.mkdir(parents=True, exist_ok=True)
    markers = [f"{DEFAULT_MARKER}={p.to_name}", f"{desktopentry.MARKER}={p.to_name}"]

    _set_aside(main_entry(), notes)
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=Affinity",
        f"Comment=Default Affinity: {p.to_name}",
        f"Exec={_exec(command, '%F' if takes_files else '')}",
        f"Path={p.to_path}",
        "Terminal=false",
        "Categories=Graphics;2DGraphics;RasterGraphics;VectorGraphics;",
        "StartupNotify=true",
        "StartupWMClass=affinity.exe",
    ]
    icon = desktopentry.find_icon()
    if icon:
        lines.insert(4, f"Icon={icon}")
    if takes_files:
        lines.append("MimeType=" + "".join(f"{t};" for t in DOCUMENT_TYPES))
    _write(main_entry(), lines + markers)

    if p.sign_in:
        _set_aside(url_handler(), notes)
        _write(url_handler(), [
            "[Desktop Entry]",
            "Type=Application",
            f"Name=Affinity sign-in handler ({p.to_name})",
            f"Exec={_exec(command, '%u')}",
            f"MimeType={URL_SCHEME};",
            "NoDisplay=true",
            "Terminal=false",
        ] + markers)

    problems = []
    if takes_files:
        problems += [e for t in DOCUMENT_TYPES if (e := xdg_mime_default(MAIN, t))]
    else:
        notes.append(f"{p.to_name} has no affinity-on-linux.exe, so double-clicked "
                     "documents are not handed to it; run Setup there to add it.")
    if p.sign_in:
        problem = xdg_mime_default(URL_HANDLER, URL_SCHEME)
        if problem:
            problems.append(problem)
    notes += [f"Could not set a default: {x}" for x in problems]
    desktopentry.refresh_menu()
    return notes


# ── a named entry per prefix ─────────────────────────────────────────────────

def menu_name(prefix_name: str) -> str:
    return f"Affinity — {prefix_name}"


def has_menu_entry(prefix_name: str) -> bool:
    return desktopentry.entry_path(prefix_name, MENU_LABEL).is_file()


def add_menu_entry(prefix_name: str, path) -> Path:
    """A launcher named after the prefix. It does not take document types."""
    command, _ = launch_command(path)
    return desktopentry.write(prefix_name, command, name=menu_name(prefix_name),
                              comment=f"Affinity in the {prefix_name} prefix")


def remove_menu_entry(prefix_name: str) -> bool:
    command = commands.Command("Menu", MENU_LABEL, "", ["true"])
    return desktopentry.remove(prefix_name, command)

