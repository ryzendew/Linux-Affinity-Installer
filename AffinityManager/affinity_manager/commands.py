"""Every way a given prefix can be run, as a command you can copy or execute.

A prefix is not one configuration. It usually holds several Wine builds, and
Affinity can be started through the plugin hook, directly, or through the
file-manager handler -- each of which behaves differently and is the right
answer to a different question. Working out the incantation by hand, correctly,
every time is how people end up running the wrong Wine and drawing conclusions
from it.

Each entry carries both an argv/env pair for running and a ready-to-paste shell
line, built from the same data so the thing you copy is the thing that runs.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from . import probe

# Affinity deadlocks at startup when OpenCL initialises on a real GPU, on Wine
# 11.11 to 11.18. The Affinity patch set fixes it from 11.19 (its OpenCL event
# callback patch), so launches on those builds leave opencl alone and Affinity's
# own preference decides. A build whose version cannot be read -- system wine --
# keeps it off.
AFFINITY_ENV = {"WINEDLLOVERRIDES": "opencl=d"}
OPENCL_DEADLOCK = ((11, 11), (11, 19))


def wine_build_version(build: str):
    """(major, minor) from a build name such as "ElementalWarrior-wine-11.19", or None."""
    m = re.search(r"wine-(\d+)\.(\d+)", str(build))
    return (int(m.group(1)), int(m.group(2))) if m else None


def affinity_env(build: str) -> dict:
    """Environment Affinity is launched with on this Wine build."""
    version = wine_build_version(build)
    low, high = OPENCL_DEADLOCK
    if version is None or low <= version < high:
        return dict(AFFINITY_ENV)
    return {}


class Command:
    __slots__ = ("group", "label", "detail", "argv", "env", "risky")

    def __init__(self, group, label, detail, argv, env=None, risky=False):
        self.group = group
        self.label = label
        self.detail = detail
        self.argv = [str(a) for a in argv]
        self.env = dict(env or {})
        # Risky ones are not run on a double-click, because "shut the prefix
        # down" next to "launch" in a list is an accident waiting to happen.
        self.risky = risky

    @property
    def shell(self) -> str:
        env = " ".join(f"{k}={shlex.quote(v)}" for k, v in sorted(self.env.items()))
        cmd = " ".join(shlex.quote(a) for a in self.argv)
        return f"{env} {cmd}".strip()

    def run(self) -> subprocess.Popen:
        env = dict(os.environ)
        env.update(self.env)
        return subprocess.Popen(
            self.argv,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def _wine_binaries(prefix: Path) -> list[tuple[str, Path]]:
    """(label, wine binary) for every Wine this prefix can use.

    The prefix's own builds first, because those are the ones AffinityOnLinux
    installed and the ones Affinity is meant to run on. System wine is offered
    last and only if present -- it will not load Affinity's vkd3d-proton, so
    anything measured on it is measuring Wine's own wined3d fallback instead."""
    out = []
    for name in probe.wine_builds(prefix):
        binary = prefix / name / "bin" / "wine"
        if binary.is_file():
            out.append((name, binary))
    system = shutil.which("wine")
    if system:
        out.append(("system wine (wined3d fallback -- not comparable)", Path(system)))
    return out


def for_prefix(prefix) -> list[Command]:
    prefix = Path(prefix).expanduser()
    app = prefix / probe.AFFINITY_SUBDIR
    base_env = {"WINEPREFIX": str(prefix)}
    commands: list[Command] = []

    launchers = [
        (
            "AffinityHook.exe",
            "Affinity, with plugins",
            "Starts Affinity through the plugin hook, so AffinityPluginLoader "
            "and WineFix load. This is what the desktop entry uses.",
        ),
        (
            "Affinity.exe",
            "Affinity, no plugins",
            "Starts Affinity directly. Use this to find out whether a problem "
            "belongs to Affinity or to the plugins.",
        ),
        (
            "affinity-on-linux.exe",
            "Affinity, as the file manager starts it",
            "The handler a double-clicked document goes through: converts the "
            "path, serialises launches, and hands warm documents to a running "
            "instance.",
        ),
    ]
    for exe_name, label, detail in launchers:
        exe = app / exe_name
        if not exe.is_file():
            continue
        for wine_label, wine in _wine_binaries(prefix):
            commands.append(
                Command(
                    group=f"Affinity ({wine_label})",
                    label=label,
                    detail=detail,
                    argv=[wine, exe],
                    env={**base_env, **affinity_env(wine_label)},
                )
            )

    tools = [
        ("winecfg", "Wine configuration", "Drives, graphics, DLL overrides and Windows version.", False),
        ("regedit", "Registry editor", "Where the DLL overrides and the DPI setting actually live.", False),
        ("winefile", "Wine file manager", "Browse the prefix as Windows sees it.", False),
        ("wineboot", "Restart the prefix", "Re-runs prefix initialisation. Closes anything running in it.", True),
        ("winedbg", "Wine debugger", "Attach to a hung Affinity: 'attach 0x<pid>', 'bt all', 'detach'.", False),
    ]
    for wine_label, wine in _wine_binaries(prefix):
        wine_dir = wine.parent
        for tool, label, detail, risky in tools:
            binary = wine_dir / tool
            if not binary.is_file():
                continue
            commands.append(
                Command(
                    group=f"Wine tools ({wine_label})",
                    label=label,
                    detail=detail,
                    argv=[binary],
                    env=base_env,
                    risky=risky,
                )
            )
        server = wine_dir / "wineserver"
        if server.is_file():
            commands.append(
                Command(
                    group=f"Wine tools ({wine_label})",
                    label="Shut the prefix down",
                    detail="wineserver -k. Ends every process in this prefix, "
                    "including anything unsaved. The orderly way to stop it -- "
                    "kill -9 on wineserver orphans the prefix's services.",
                    argv=[server, "-k"],
                    env=base_env,
                    risky=True,
                )
            )

    winetricks = shutil.which("winetricks")
    if winetricks:
        commands.append(
            Command(
                group="Other",
                label="Winetricks",
                detail="Install redistributables and fonts into this prefix.",
                argv=[winetricks],
                env=base_env,
            )
        )

    commands.append(
        Command(
            group="Other",
            label="Open the prefix directory",
            detail="The prefix itself, in your file manager.",
            argv=[shutil.which("xdg-open") or "xdg-open", str(prefix)],
            env={},
        )
    )
    return commands


def grouped(prefix) -> dict[str, list[Command]]:
    out: dict[str, list[Command]] = {}
    for command in for_prefix(prefix):
        out.setdefault(command.group, []).append(command)
    return out
