"""Finding and driving AffinityOnLinux's installer.

The manager does not install anything itself. Installing Affinity under Wine is
a long, distro-specific job that AffinityOnLinux already does, and a second
implementation would drift from it. What the manager adds is which prefix, and
which build.

This needs an installer that understands AFFINITY_INSTALL_DIR. Older copies
ignore it and would install into ~/.AffinityLinux instead -- silently taking
over the user's working prefix -- so that is checked for before launching
rather than discovered afterwards.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ENV_SCRIPT = "AFFINITY_INSTALLER_SCRIPT"

# The branch carrying AFFINITY_INSTALL_DIR and AFFINITY_INSTALLER_FILE. Until
# that work is upstream, a checkout sitting on main has an installer that will
# ignore the prefix it is handed -- so which branch is in use is not a detail,
# and is reported rather than assumed.
PREFERRED_REMOTE = (os.environ.get("AFFINITY_MANAGER_REPO", "").strip().rstrip("/")
                    or "https://github.com/jfacemyer/Linux-Affinity-Manager") + ".git"
PREFERRED_BRANCH = os.environ.get("AFFINITY_MANAGER_BRANCH", "").strip() or "main"
ENV_INSTALL_DIR = "AFFINITY_INSTALL_DIR"
ENV_INSTALLER_FILE = "AFFINITY_INSTALLER_FILE"

SCRIPT_NAME = "AffinityLinuxInstaller.py"


class InstallerNotFound(RuntimeError):
    pass


class InstallerTooOld(RuntimeError):
    pass


def managed_checkout() -> Path:
    """A checkout the manager owns, under its own metadata directory.

    Pinned to the branch that supports being pointed at a prefix, so the manager
    keeps working whatever a development checkout elsewhere is doing."""
    from . import registry

    return registry.manager_dir() / "AffinityOnLinux"


def vendored_installer() -> Path:
    """The installer beside this manager, when the manager lives inside
    AffinityOnLinux as AffinityManager/.

    This is the case the whole directory layout exists for, and it outranks the
    managed checkout: a copy shipped inside AffinityOnLinux should drive the
    installer it shipped with, not one fetched from a branch. It is still
    checked for AFFINITY_INSTALL_DIR support like any other, so being adjacent
    buys it no trust it has not earned."""
    return Path(__file__).resolve().parent.parent.parent / "AffinityScripts" / SCRIPT_NAME


def candidate_paths() -> list[Path]:
    """Where to look, in order of how deliberate the choice is."""
    from . import settings

    here = Path(__file__).resolve().parent.parent
    out = []
    override = os.environ.get(ENV_SCRIPT, "").strip()
    if override:
        out.append(Path(override).expanduser())
    configured = (settings.get("installer_script") or "").strip()
    if configured:
        out.append(Path(configured).expanduser())
    out.append(vendored_installer())
    out.append(managed_checkout() / "AffinityScripts" / SCRIPT_NAME)
    out += [
        here / SCRIPT_NAME,
        here.parent / "AffinityOnLinux" / "AffinityScripts" / SCRIPT_NAME,
        Path.home() / ".AffinityLinuxManager" / SCRIPT_NAME,
        Path.home() / ".local" / "share" / "AffinityOnLinux" / SCRIPT_NAME,
    ]
    return out


def find_installer() -> Path:
    for path in candidate_paths():
        if path.is_file():
            return path
    raise InstallerNotFound(
        f"Could not find {SCRIPT_NAME}. Set ${ENV_SCRIPT} to its path, or put a "
        f"checkout of AffinityOnLinux beside this project."
    )


def supports_install_dir(script: Path) -> bool:
    """Whether this installer honours AFFINITY_INSTALL_DIR.

    Read from the source rather than probed by running it, because the failure
    mode of guessing wrong is an install into the user's working prefix."""
    try:
        return ENV_INSTALL_DIR in script.read_text(errors="replace")
    except OSError:
        return False


def check_installer(script: Path | None = None) -> Path:
    script = Path(script) if script else find_installer()
    if not supports_install_dir(script):
        raise InstallerTooOld(
            f"{script} does not understand {ENV_INSTALL_DIR}, so it would "
            f"install into ~/.AffinityLinux regardless of which prefix was "
            f"asked for. Update AffinityOnLinux before creating prefixes."
        )
    return script


def launch(
    install_dir,
    *,
    installer_file=None,
    script: Path | None = None,
    env: dict | None = None,
) -> subprocess.Popen:
    """Start the installer against one prefix.

    Not waited on: the installer is a GUI that runs for a long time, and the
    manager stays usable while it does."""
    script = check_installer(script)
    child = dict(os.environ if env is None else env)
    child[ENV_INSTALL_DIR] = str(Path(install_dir).expanduser())
    if installer_file:
        child[ENV_INSTALLER_FILE] = str(Path(installer_file).expanduser())
    else:
        child.pop(ENV_INSTALLER_FILE, None)
    return subprocess.Popen([sys.executable, str(script)], env=child)


def launch_affinity(prefix, *, wine_build: str | None = None) -> subprocess.Popen:
    """Start Affinity in a prefix.

    Goes through AffinityHook.exe when it is there so plugins load, and falls
    back to Affinity.exe when it is not. opencl is disabled on the builds where,
    on a real GPU, it deadlocks Affinity at startup (Wine 11.11 to 11.18)."""
    prefix = Path(prefix).expanduser()
    app = prefix / "drive_c" / "Program Files" / "Affinity" / "Affinity"
    exe = app / "AffinityHook.exe"
    if not exe.is_file():
        exe = app / "Affinity.exe"
    if not exe.is_file():
        raise FileNotFoundError(f"No Affinity found in {prefix}")

    build = wine_build
    if not build:
        from . import probe

        build = probe.active_wine(prefix)
    if not build:
        raise FileNotFoundError(f"No Wine build found in {prefix}")

    # active_wine labels a guess from the symlink "<build> (link)": a label for
    # people, not a directory. Used as one, the path did not exist and Affinity
    # was started under system Wine -- none of the patches, and a black UI.
    build = build.removesuffix(" (link)")
    wine = prefix / build / "bin" / "wine"
    if not wine.is_file():
        wine = prefix / "ElementalWarriorWine" / "bin" / "wine"
    if not wine.is_file():
        # Never system Wine: it is not the build this prefix was set up with.
        raise FileNotFoundError(f"No Wine build {build} in {prefix}")

    env = dict(os.environ)
    env["WINEPREFIX"] = str(prefix)
    from .commands import affinity_env

    env.update(affinity_env(build))
    return subprocess.Popen(
        [str(wine), str(exe)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


# ── which checkout, and on what ──────────────────────────────────────────────


def _git(repo: Path, *args) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def describe(script: Path | None = None) -> dict:
    """Which installer is in use, from where, and whether it is the right one."""
    try:
        script = Path(script) if script else find_installer()
    except InstallerNotFound as e:
        return {"found": False, "error": str(e)}

    repo = _git(script.parent, "rev-parse", "--show-toplevel")
    repo_path = Path(repo) if repo else None
    branch = _git(repo_path, "rev-parse", "--abbrev-ref", "HEAD") if repo_path else ""
    commit = _git(repo_path, "rev-parse", "--short", "HEAD") if repo_path else ""
    dirty = bool(_git(repo_path, "status", "--porcelain")) if repo_path else False
    try:
        vendored = script.resolve() == vendored_installer().resolve()
    except OSError:
        vendored = False
    return {
        "found": True,
        "script": str(script),
        "repo": str(repo_path) if repo_path else None,
        "branch": branch,
        "commit": commit,
        "dirty": dirty,
        "supports_install_dir": supports_install_dir(script),
        "on_preferred_branch": branch == PREFERRED_BRANCH,
        "managed": repo_path is not None and repo_path == managed_checkout(),
        "vendored": vendored,
    }


def summary(info: dict | None = None) -> str:
    """One line for the status bar, saying the thing that matters most."""
    info = info or describe()
    if not info.get("found"):
        return info.get("error", "No installer found.")
    where = info["script"]
    if not info["supports_install_dir"]:
        return (
            f"{where} cannot be pointed at a prefix"
            + (f" (branch {info['branch']})" if info["branch"] else "")
            + " — it would install into ~/.AffinityLinux."
        )
    bits = []
    if info["branch"]:
        bits.append(f"branch {info['branch']}")
    if info["commit"]:
        bits.append(info["commit"] + ("+changes" if info["dirty"] else ""))
    detail = ", ".join(bits)
    warning = ""
    # The branch warning exists because a checkout on main has an installer
    # that ignores the prefix it is handed. It does not apply to the copy
    # shipped alongside this manager: that one is the right one by
    # construction, and it has already been checked for the support that
    # matters. Warning about it would be noise on every start of a merged
    # install, and noise is how a real warning stops being read.
    if info["branch"] and not info["on_preferred_branch"] and not info.get("vendored"):
        warning = f"  (expected {PREFERRED_BRANCH})"
    if info.get("vendored"):
        # Started by run.py from a downloaded tarball there is no git to ask,
        # so run.py says which branch and commit it unpacked.
        source = os.environ.get("AFFINITY_MANAGER_SOURCE", "").strip()
        if source and not detail:
            detail = f"downloaded: {source}"
        detail = ("shipped with this manager" + (f", {detail}" if detail else ""))
    return f"Installer: {where}" + (f"  [{detail}]" if detail else "") + warning


def fetch_managed_checkout(remote: str = PREFERRED_REMOTE, branch: str = PREFERRED_BRANCH):
    """Clone or update the manager's own checkout of the installer.

    Yields progress lines. Kept a normal clone rather than a shallow one: it is
    small, and a full history means the thing can be inspected and switched
    without re-fetching."""
    target = managed_checkout()
    if (target / ".git").is_dir():
        yield f"Updating {target}"
        for args in (("fetch", "origin", branch), ("checkout", branch), ("reset", "--hard", f"origin/{branch}")):
            out = _git(target, *args)
            yield f"  git {' '.join(args)}" + (f": {out.splitlines()[0]}" if out else "")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        yield f"Cloning {remote} ({branch}) into {target}"
        try:
            result = subprocess.run(
                ["git", "clone", "--branch", branch, remote, str(target)],
                capture_output=True,
                text=True,
                timeout=600,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            yield f"  failed: {e}"
            return
        if result.returncode != 0:
            yield f"  failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'git clone failed'}"
            return
    script = target / "AffinityScripts" / SCRIPT_NAME
    if script.is_file() and supports_install_dir(script):
        from . import settings

        settings.set("installer_script", str(script))
        yield f"  ready: {script}"
    else:
        yield "  that checkout has no installer that can be pointed at a prefix"
