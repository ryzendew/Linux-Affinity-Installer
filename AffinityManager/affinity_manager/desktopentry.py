"""Menu entries for a prefix's commands.

Any of the configurations in commands.py can be worth reaching from the
application menu -- a second Affinity on a different Wine, a shortcut to the
registry editor for the prefix you keep poking at. Writing those .desktop files
by hand means getting Exec quoting and environment right every time, which is
exactly the sort of thing that silently produces a menu entry that does nothing.

Entries written here are marked with an X-AffinityManager-Prefix key, so this
can tell its own entries from the ones AffinityOnLinux installs and never edit
or remove somebody else's.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

MARKER = "X-AffinityManager-Prefix"
COMMAND_MARKER = "X-AffinityManager-Command"


def applications_dir() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return root / "applications"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "entry"


def entry_path(prefix_name: str, command_label: str) -> Path:
    return applications_dir() / f"affinity-manager-{_slug(prefix_name)}-{_slug(command_label)}.desktop"


def find_icon() -> str | None:
    """An icon name already present on this system, or None.

    Only ever a name, never a bundled file: the Affinity artwork is Serif's and
    is not ours to ship. If AffinityOnLinux has installed one, referring to it
    by name is free; if not, the entry goes without."""
    names = ("Affinity", "affinity", "AffinityPhoto", "affinity-photo")
    roots = [
        Path.home() / ".local" / "share" / "icons",
        Path("/usr/share/icons"),
        Path("/usr/share/pixmaps"),
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for name in names:
            for ext in (".png", ".svg", ".xpm"):
                if list(root.rglob(f"{name}{ext}")):
                    return name
    return None


def exec_line(command) -> str:
    """Exec= for a command that needs environment.

    Desktop entries have no syntax for VAR=value before the program, so this
    goes through env(1). Everything is quoted with shlex, because a prefix path
    with a space in it otherwise produces an entry that fails silently."""
    parts = []
    if command.env:
        parts.append("env")
        parts += [f"{k}={shlex.quote(v)}" for k, v in sorted(command.env.items())]
    parts += [shlex.quote(a) for a in command.argv]
    return " ".join(parts)


def build(prefix_name: str, command, *, name=None, comment=None, categories=None) -> str:
    icon = find_icon()
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={name or f'{command.label} ({prefix_name})'}",
        f"Comment={comment or command.detail}",
        f"Exec={exec_line(command)}",
        "Terminal=false",
        f"Categories={categories or 'Graphics;2DGraphics;RasterGraphics;VectorGraphics;'}",
        "StartupNotify=true",
        f"{MARKER}={prefix_name}",
        f"{COMMAND_MARKER}={command.label}",
    ]
    if icon:
        lines.insert(5, f"Icon={icon}")
    return "\n".join(lines) + "\n"


def is_ours(path: Path) -> bool:
    try:
        return MARKER in path.read_text(errors="replace")
    except OSError:
        return False


def write(prefix_name: str, command, **kwargs) -> Path:
    path = entry_path(prefix_name, command.label)
    if path.exists() and not is_ours(path):
        # Refuse rather than overwrite: a name clash with an entry somebody else
        # installed would silently replace their launcher.
        raise FileExistsError(
            f"{path} exists and was not written by this application; not touching it."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build(prefix_name, command, **kwargs))
    path.chmod(0o755)
    refresh_menu()
    return path


def read_name(prefix_name: str, command) -> str | None:
    path = entry_path(prefix_name, command.label)
    try:
        for line in path.read_text(errors="replace").splitlines():
            if line.startswith("Name="):
                return line[len("Name="):]
    except OSError:
        pass
    return None


def exists(prefix_name: str, command) -> bool:
    return entry_path(prefix_name, command.label).is_file()


def remove(prefix_name: str, command) -> bool:
    path = entry_path(prefix_name, command.label)
    if not path.is_file():
        return False
    if not is_ours(path):
        raise PermissionError(f"{path} was not written by this application.")
    path.unlink()
    refresh_menu()
    return True


def owner_of(path: Path) -> str | None:
    """The prefix a desktop entry names, exactly, or None."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == MARKER:
            return value.strip()
    return None


def entries_for(prefix_name: str) -> list[Path]:
    """Every entry this application wrote for ONE prefix.

    The whole line has to be read. Testing for the substring
    "X-AffinityManager-Prefix=Test" matched a file whose value is "Test 33",
    and prefix names may contain spaces -- so removing "Test" offered, and
    deleted, the menu entries belonging to "Test 33"."""
    out = []
    directory = applications_dir()
    if not directory.is_dir():
        return out
    # The Default's fixed-name entries too (defaultentry), when this prefix's
    # marker is in them: removing the prefix the menu's Affinity entry runs
    # would otherwise leave it starting a prefix that is gone.
    candidates = list(directory.glob("affinity-manager-*.desktop"))
    candidates += [directory / "Affinity.desktop", directory / "affinity-url-handler.desktop"]
    for path in candidates:
        if path.is_file() and owner_of(path) == prefix_name:
            out.append(path)
    return sorted(out)


def refresh_menu() -> None:
    """Make the menu notice.

    KDE caches desktop files in ksycoca and keeps using the old copy until
    kbuildsycoca runs, so a new entry appears only after a logout without this.
    Both commands are best-effort -- a missing one is not an error, it just
    means that desktop is not installed."""
    for command in (
        ["kbuildsycoca6"],
        ["kbuildsycoca5"],
        ["update-desktop-database", str(applications_dir())],
    ):
        if shutil.which(command[0]):
            try:
                subprocess.run(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=60,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
