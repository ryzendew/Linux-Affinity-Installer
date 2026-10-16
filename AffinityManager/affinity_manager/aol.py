"""Load AffinityOnLinux's installer as a module, instead of copying it.

The manager needs three things from the installer: its look, its widgets, and
eventually the installer window itself. Until now it had the first two as
`aol_ui.py` -- 1,410 lines extracted verbatim with `ast.get_source_segment` --
which worked and could go stale silently the moment upstream touched a
stylesheet.

Importing it is possible because of an asymmetry worth stating plainly. The
installer must stay a single file: its documented install is
`curl ... | python3`, so it can never import a sibling. The manager has no such
constraint, and is never piped. So the dependency can only point one way, and
that way happens to be the useful one.

Importing is safe, and that was measured rather than assumed: every column-zero
statement in those 19,000 lines is an import, a def, a class, the PyQt6
try/except, or the `if __name__ == "__main__"` guard. Loading it starts no GUI,
no threads and no probing, and takes about 0.05s. `SystemExit` is caught anyway
-- the file calls `sys.exit(1)` at module level when PyQt6 is missing, and the
manager should report that rather than vanish with it.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import sys
from pathlib import Path

from . import installer

MODULE_NAME = "_affinity_on_linux_installer"

# What the manager reaches for. verify() checks they are all there, so an
# upstream rename is a clear message at startup rather than an AttributeError
# somewhere later.
REQUIRED_CLASS_ATTRS = (
    "_apply_mattscreative_theme",
    "_apply_dark_theme",
    "_apply_light_theme",
    "_mattscreative_dialog_stylesheet",
    "_dark_dialog_stylesheet",
)
REQUIRED_MODULE_ATTRS = (
    "AffinityInstallerGUI",
    "ZoomableTextEdit",
    "ProgressSpinner",
    "ENV_INSTALL_DIR",
    "ENV_INSTALLER_FILE",
)

_module = None
_source: Path | None = None


class NotAvailable(RuntimeError):
    """The installer could not be loaded, and the manager should say why."""


class NeedsRestart(NotAvailable):
    """A different installer was chosen after one had already been loaded.

    Not a failure so much as a limit. The module is cached because loading it
    twice would build a second set of Qt classes with the same names, and
    nothing good comes of two AffinityInstallerGUI types in one process --
    isinstance checks stop agreeing, stylesheets attach to the wrong class,
    and the second import re-runs 19,000 lines of module-level code.

    So a change of installer path is honoured at the next start, and said out
    loud. Before this, Settings reported the new path everywhere while the
    manager went on running the old one -- the one thing the installer
    reporting exists to prevent."""


def module(script: Path | None = None):
    """The installer, imported. Cached: loading twice would build a second set
    of Qt classes with the same names, and no good comes of that.

    If the resolved path has changed since the cached one was loaded -- the
    user picked a different installer in Settings, or fetched the managed
    checkout -- this raises NeedsRestart rather than quietly continuing to run
    the old one."""
    global _module, _source

    try:
        path = installer.check_installer(script)
    except Exception as exc:                      # InstallerNotFound/TooOld
        if _module is not None:
            return _module            # a loaded installer beats a broken path
        raise NotAvailable(str(exc)) from exc

    if _module is not None:
        if _source is not None and path.resolve() != _source.resolve():
            raise NeedsRestart(
                f"{path} was chosen, but {_source} is already loaded and cannot "
                "be swapped out while the application is running. Restart the "
                "manager to use the new one.")
        return _module

    spec = importlib.util.spec_from_file_location(MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise NotAvailable(f"{path} could not be loaded as a module.")
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = loaded
    try:
        spec.loader.exec_module(loaded)
    except SystemExit as exc:
        sys.modules.pop(MODULE_NAME, None)
        raise NotAvailable(
            f"{path} exited while being loaded (code {exc.code}). It does that "
            "when PyQt6 is missing, which cannot be the case here, so something "
            "else is wrong with that copy."
        ) from exc
    except BaseException as exc:
        sys.modules.pop(MODULE_NAME, None)
        raise NotAvailable(f"{path} failed to load: {exc}") from exc

    _module, _source = loaded, path
    return _module


def source() -> Path | None:
    """Which file was loaded. For the about box and for error messages."""
    return _source


def cls():
    """The installer's window class."""
    return getattr(module(), "AffinityInstallerGUI")


def verify() -> list[str]:
    """Names the manager depends on that this copy does not have.

    Empty means it will work. The point is to fail at startup with a sentence
    naming what changed, rather than to discover it when somebody clicks a
    button an hour in."""
    try:
        mod = module()
    except NotAvailable as exc:
        return [str(exc)]

    missing = [f"module attribute {name}" for name in REQUIRED_MODULE_ATTRS
               if not hasattr(mod, name)]
    window = getattr(mod, "AffinityInstallerGUI", None)
    if window is not None:
        missing += [f"AffinityInstallerGUI.{name}" for name in REQUIRED_CLASS_ATTRS
                    if not hasattr(window, name)]
    return missing


@contextlib.contextmanager
def target_env(prefix, installer_file=None):
    """Point the installer at one prefix for the duration of a block.

    The installer reads AFFINITY_INSTALL_DIR once, at construction. Launched as
    a child process that was a child's environment; hosted in this process it is
    ours, so it is set and put back. Leaving it set would leak the last-entered
    prefix into every subprocess the manager ever spawns afterwards."""
    mod = module()
    keys = {mod.ENV_INSTALL_DIR: str(Path(prefix).expanduser())}
    if installer_file:
        keys[mod.ENV_INSTALLER_FILE] = str(Path(installer_file).expanduser())
    else:
        keys[mod.ENV_INSTALLER_FILE] = None       # explicitly absent

    previous = {k: os.environ.get(k) for k in keys}
    try:
        for key, value in keys.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
