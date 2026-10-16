"""Wine's renderer setting: put back `renderer=vulkan` when a prefix has lost it.

The installer sets HKCU\\Software\\Wine\\Direct3D "renderer"="vulkan". Without
it wined3d draws with OpenGL, where Affinity's flyouts and tooltips have come
up as black boxes. The setting has been lost when the installer stopped Wine
before the wineserver had written the registry to disk (installs from the
morning of 2026-10-16), and such a prefix stays on OpenGL however it is
launched.

Only a missing setting is put back. A renderer that was chosen -- "gl" from the
installer's OpenGL option -- is left alone.

The value goes straight into user.reg, and only while nothing runs in the
prefix: the wineserver holds the registry in memory and writes it back when it
exits, so an edit under a live one is overwritten. Wine reads the file at the
next start.
"""

from __future__ import annotations

import os
import re
import tempfile
import time
from pathlib import Path

from . import liveness, probe

KEY = r"Software\\Wine\\Direct3D"
VALUE = "renderer"


def _section_header(line: str) -> str | None:
    if not line.startswith("["):
        return None
    end = line.find("]")
    return line[1:end].lower() if end != -1 else None


def renderer_setting(prefix) -> str | None:
    """The prefix's renderer setting, or None if it has none."""
    reg = Path(prefix).expanduser() / "user.reg"
    try:
        lines = reg.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    inside = False
    for line in lines:
        header = _section_header(line)
        if header is not None:
            inside = header == KEY.lower()
            continue
        if inside:
            m = re.match(r'^"([^"]*)"="([^"]*)"', line)
            if m and m.group(1).lower() == VALUE:
                return m.group(2)
    return None


def _with_vulkan(text: str) -> str:
    """user.reg with "renderer"="vulkan" in the Direct3D key, added to the key
    if it is there and as a new key at the end if not."""
    lines = text.split("\n")
    value = f'"{VALUE}"="vulkan"'
    for i, line in enumerate(lines):
        if _section_header(line) == KEY.lower():
            j = i + 1
            while j < len(lines) and lines[j].startswith("#"):
                j += 1
            lines.insert(j, value)
            return "\n".join(lines)
    tail = "" if text.endswith("\n") else "\n"
    return f"{text}{tail}\n[{KEY}] {int(time.time())}\n{value}\n"


def restore_vulkan(prefix) -> bool:
    """Set the renderer to Vulkan if the prefix has Affinity, nothing running in
    it, and no renderer setting. Returns True when it changed the prefix."""
    prefix = Path(prefix).expanduser()
    reg = prefix / "user.reg"
    if not reg.is_file() or not probe.has_affinity(prefix):
        return False
    if renderer_setting(prefix) is not None:
        return False
    if liveness.scan(prefix).state != liveness.QUIET:
        return False
    text = reg.read_text(encoding="utf-8", errors="surrogateescape")
    fd, tmp = tempfile.mkstemp(dir=prefix, prefix=".user.reg.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape") as f:
            f.write(_with_vulkan(text))
        os.chmod(tmp, reg.stat().st_mode & 0o7777)
        # Checked again just before the swap: a Wine started meanwhile writes
        # its own copy back when it exits, and that one would win anyway.
        if liveness.scan(prefix).state != liveness.QUIET:
            os.unlink(tmp)
            return False
        os.replace(tmp, reg)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return True
