#!/usr/bin/env python3
"""Run the Affinity on Linux Manager straight from the repository.

    curl -sSL https://github.com/jfacemyer/Linux-Affinity-Manager/raw/main/AffinityManager/run.py | python3

The installer can be piped into python3 because it is one file. The manager is
a package -- a dozen modules, and it loads the installer from beside itself --
so piping it cannot work. This file is the single-file part: it downloads the
branch as a tarball, unpacks it into a cache, and starts the manager from
there. Every run fetches the branch again, so like the piped installer it is
always the latest; nothing has to be kept up to date by hand.

Nothing is installed. No launcher, nothing on PATH, no package manager, no
sudo. What it leaves is the cache:

    ~/.cache/AffinityOnLinux/manager/<branch>/<commit>/

one directory per commit, the newest few kept. Deleting the whole folder is
always safe; the next run downloads again.

Offline, it starts the newest copy it already has and says so.

Lives in AffinityLinuxManager, which is carried inside AffinityOnLinux as
AffinityManager/ by git subtree, so the URL above serves this file from there.
REPO and BRANCH name where the public build lives. AFFINITY_MANAGER_REPO and
AFFINITY_MANAGER_BRANCH override them -- that is how the same commit is tried
from a staging branch, or from another server, before it is promoted:

    curl -sSL <repo>/raw/<branch>/AffinityManager/run.py | \
        AFFINITY_MANAGER_REPO=<repo> AFFINITY_MANAGER_BRANCH=<branch> python3

Whatever source this run used is passed on to the manager, and from there to
the installer, which fetches its own files from the same place.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

# The public home: a fork of the upstream installer that carries this work.
# Repoint at upstream if it is merged there (AffinityHandler/README.md,
# "Temporary download sources").
REPO = "https://github.com/jfacemyer/Linux-Affinity-Manager"
BRANCH = "main"

ENTRY = Path("AffinityManager") / "AffinityLinuxManager.py"
INSTALLER = Path("AffinityScripts") / "AffinityLinuxInstaller.py"
KEEP = 3                    # copies kept per branch, plus any still running
MIN_PYTHON = (3, 10)


class Refused(RuntimeError):
    """Something is wrong enough that starting anything would be a mistake."""


def say(message: str) -> None:
    print(f"[affinity-manager] {message}", file=sys.stderr, flush=True)


# ── where things go ──────────────────────────────────────────────────────────


def repo() -> str:
    return os.environ.get("AFFINITY_MANAGER_REPO", "").strip().rstrip("/") or REPO


def branch() -> str:
    return os.environ.get("AFFINITY_MANAGER_BRANCH", "").strip() or BRANCH


def raw_url(repo_url: str, for_branch: str, path: str) -> str:
    """A file on a branch, as the hosting service spells it.

    GitHub serves <repo>/raw/<branch>/<path> (a redirect to
    raw.githubusercontent.com); Forgejo and Gitea want
    <repo>/raw/branch/<branch>/<path>."""
    if repo_url.startswith("https://github.com/"):
        return f"{repo_url}/raw/{for_branch}/{path}"
    return f"{repo_url}/raw/branch/{for_branch}/{path}"


def cache_root(for_branch: str) -> Path:
    """~/.cache, because everything here can be downloaded again."""
    base = os.environ.get("XDG_CACHE_HOME", "").strip()
    root = Path(base).expanduser() if base else Path.home() / ".cache"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", for_branch).strip("-") or "branch"
    return root / "AffinityOnLinux" / "manager" / slug


def tarball_url(repo_url: str, for_branch: str) -> str:
    return f"{repo_url}/archive/{for_branch}.tar.gz"


# ── getting the branch ───────────────────────────────────────────────────────


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def commit_of(data: bytes) -> str:
    """The commit the tarball was made from.

    Forgejo writes it into the archive's pax header, the way git archive does.
    Falls back to a hash of the contents, which still names one exact tree --
    it just cannot be looked up in the repository."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            comment = tf.pax_headers.get("comment", "")
    except tarfile.TarError as exc:
        raise Refused(f"what was downloaded is not a tarball: {exc}") from exc
    if re.fullmatch(r"[0-9a-f]{40}", comment or ""):
        return comment
    return "sha256-" + hashlib.sha256(data).hexdigest()


def _strip_top(member: tarfile.TarInfo) -> str | None:
    parts = Path(member.name).parts
    return str(Path(*parts[1:])) if len(parts) > 1 else None


def extract(data: bytes, dest: Path) -> None:
    """Unpack into dest, which must not exist, atomically.

    Built under a temporary name and renamed into place, so a copy that was
    interrupted -- a dropped connection, a full disk -- can never be the one
    the next run decides to start.

    Members are checked rather than trusted: nothing absolute, nothing with
    "..", no links or devices. The repository holds none of those, so any one
    of them means the tarball is not what it claims to be."""
    staging = dest.with_name(f"{dest.name}.partial-{os.getpid()}")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            for member in tf.getmembers():
                # Checked on the RAW name. Stripping the top directory first
                # turns "/etc/passwd" into a harmless-looking "etc/passwd",
                # which would land inside the cache -- safe, but it would also
                # accept a tarball that is plainly not the repository.
                raw = member.name
                if (raw.startswith("/") or ".." in Path(raw).parts
                        or not (member.isfile() or member.isdir())):
                    raise Refused(f"refusing a suspicious entry in the tarball: "
                                  f"{member.name}")
                inner = _strip_top(member)
                if inner is None:
                    continue
                if Path(inner).is_absolute():
                    raise Refused(f"refusing a suspicious entry in the tarball: "
                                  f"{member.name}")
                member.name = inner
                if hasattr(tarfile, "data_filter"):
                    tf.extract(member, staging, filter="data")
                else:                                   # Python < 3.10.12
                    tf.extract(member, staging)
        for required in (ENTRY, INSTALLER):
            if not (staging / required).is_file():
                raise Refused(f"the branch has no {required}; is "
                              f"{branch()!r} the right branch?")
        staging.rename(dest)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


# ── the cache ────────────────────────────────────────────────────────────────


def copies(root: Path) -> list[Path]:
    """Finished copies, newest first. Partial ones are never offered."""
    try:
        found = [p for p in root.iterdir()
                 if p.is_dir() and ".partial-" not in p.name
                 and (p / ENTRY).is_file()]
    except OSError:
        return []
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def in_use(path: Path) -> bool:
    """Is a manager running out of this copy right now?

    A copy is never pruned from under a running manager: it loads the
    installer's icons and its hosted Setup page from its own directory as it
    goes, long after it started."""
    needle = str(path).encode()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if needle in (entry / "cmdline").read_bytes():
                return True
        except OSError:
            continue
    return False


def prune(root: Path, keep: int = KEEP, current: Path | None = None) -> list[Path]:
    removed = []
    for path in copies(root)[keep:]:
        if path == current or in_use(path):
            continue
        shutil.rmtree(path, ignore_errors=True)
        removed.append(path)
    # And partial ones left by a run that was killed -- but only old ones,
    # since another run may be unpacking right now.
    try:
        for path in root.iterdir():
            if ".partial-" in path.name and time.time() - path.stat().st_mtime > 3600:
                shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass
    return removed


# ── before starting anything ─────────────────────────────────────────────────


PYQT_HINT = """\
The manager needs PyQt6, and it is not installed. Install it with your
distribution's package manager, then run this again:

  Arch, Manjaro, CachyOS, EndeavourOS:   sudo pacman -S python-pyqt6
  Fedora, Nobara:                        sudo dnf install python3-pyqt6
  Debian, Ubuntu, Mint, Pop!_OS:         sudo apt install python3-pyqt6
  openSUSE:                              sudo zypper install python3-PyQt6

(The installer offers to do this for you; this does not, because it should
not be running a package manager on your behalf.)"""


def check_environment() -> None:
    if sys.version_info < MIN_PYTHON:
        raise Refused(f"Python {'.'.join(map(str, MIN_PYTHON))} or newer is "
                      f"needed; this is {sys.version.split()[0]}.")
    try:
        import PyQt6.QtWidgets  # noqa: F401
    except ImportError:
        raise Refused(PYQT_HINT) from None


def obtain(root: Path, url: str) -> Path:
    """The copy to run: freshly downloaded, or the newest one already here."""
    try:
        data = download(url)
    except OSError as exc:
        existing = copies(root)
        if not existing:
            raise Refused(f"could not download {url}: {exc}\n"
                          "There is no earlier copy to fall back to.") from exc
        say(f"could not download the branch ({exc}); starting the copy from "
            f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(existing[0].stat().st_mtime))}")
        return existing[0]

    commit = commit_of(data)
    dest = root / commit[:12]
    if (dest / ENTRY).is_file():
        os.utime(dest)              # newest again, for the next offline run
        say(f"up to date at {commit[:12]}")
        return dest
    root.mkdir(parents=True, exist_ok=True)
    extract(data, dest)
    say(f"fetched {branch()} at {commit[:12]}")
    return dest


def main(argv=None, run=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        check_environment()
        root = cache_root(branch())
        copy = obtain(root, tarball_url(repo(), branch()))
        prune(root, current=copy)
    except Refused as exc:
        say(str(exc))
        return 1
    entry = copy / ENTRY
    command = [sys.executable, str(entry), *argv]
    # A tarball is not a git checkout, so the manager cannot ask git which
    # build it is. Tell it, so the status line can say what is running.
    os.environ["AFFINITY_MANAGER_SOURCE"] = f"{branch()} @ {copy.name}"
    # And where it came from, so the installer fetches anything it needs from
    # the same repository and branch rather than from the public default --
    # a staging run must not quietly mix in files from main.
    os.environ["AFFINITY_MANAGER_REPO"] = repo()
    os.environ["AFFINITY_MANAGER_BRANCH"] = branch()
    # exec, not a child process: the manager then IS this process, so closing
    # it ends everything and its single-instance check sees one manager.
    (run or os.execv)(sys.executable, command)
    return 0


if __name__ == "__main__":
    sys.exit(main())
