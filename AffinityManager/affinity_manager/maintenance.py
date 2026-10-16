"""Copying a prefix, and clearing out what an install leaves behind.

Two operations that are easy to get dangerously wrong by hand:

* **Clone.** A prefix is mostly self-contained -- `dosdevices/c:` is relative,
  and the registry carries no absolute path to the prefix itself -- but it does
  hold symlinks, and a naive copy either dereferences them (turning a 700 MB
  symlinked Wine build into 700 MB of duplicate) or leaves them pointing back
  into the original, so the copy quietly writes into the prefix it was supposed
  to protect.

* **Clean.** AffinityOnLinux unpacks Wine into the prefix and does not remove
  the archive, and every rebuild leaves the previous build beside the new one.
  A prefix accumulates gigabytes of Wine builds it will never run again. The
  risk is deleting the build it *is* running, or the one a symlink names.

Everything here reports before it acts. `cleanable()` and `plan_clone()` return
what would happen; nothing is removed or written until `clean()` or `clone()` is
called with that plan.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import probe


class Busy(RuntimeError):
    """The prefix is running. Neither operation is safe against a live prefix."""


class NotAPrefix(ValueError):
    pass


class CloneFailed(RuntimeError):
    """The copy did not complete. Raised rather than reported, because a partial
    prefix that is announced as a clone gets registered and later launched, and
    a prefix missing a DLL or holding half a system.reg misbehaves in ways that
    look like an application bug."""


class NotEnoughSpace(RuntimeError):
    pass


class DestinationInUse(ValueError):
    pass


@dataclass
class Item:
    """Something clean() could remove."""
    path: Path
    kind: str           # wine-build | archive | backup | temp | crashdump
    size: int
    reason: str
    is_symlink: bool = False

    @property
    def label(self) -> str:
        return f"{self.path.name} ({probe.human_size(self.size)})"


@dataclass
class Plan:
    source: Path
    dest: Path
    keep_builds: list[str] = field(default_factory=list)
    drop_builds: list[str] = field(default_factory=list)
    est_size: int = 0


def _du(path: Path) -> int:
    """Size on disk, not following symlinks out of the prefix."""
    if path.is_symlink():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        for f in files:
            fp = Path(root) / f
            if fp.is_symlink():
                continue
            try:
                total += fp.stat().st_size
            except OSError:
                pass
    return total


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _require_idle(prefix: Path) -> None:
    pids = probe.running_pids(prefix)
    if pids:
        raise Busy(
            f"Affinity is running in {prefix} (pid {pids[0]}). "
            "Close it first: copying or pruning a live prefix gives an "
            "inconsistent result and can strand its Wine services."
        )


# A launcher is a script or a desktop entry, never a megabyte.
LAUNCHER_MAX_BYTES = 256 * 1024

LAUNCHER_DIRS = ("~/.local/share/applications", "~/.local/bin", "~/bin",
                 "~/.local/share/applications/../applications")


def builds_named_by_launchers(prefix, dirs=None) -> set[str]:
    """Wine builds that a desktop entry or launcher script names explicitly.

    This is the authority, and it was the missing one. The launchers hardcode
    their Wine path -- "<prefix>/<build>/bin/wine" -- so a prefix can run 11.16
    every day while its ElementalWarriorWine symlink still says 11.12, left over
    from an older install. Reading only the symlink is how a clone kept the
    wrong Wine and an install went onto a build without any of the prefix's
    patches."""
    p = str(Path(prefix).expanduser())
    found: set[str] = set()
    seen: set[Path] = set()

    for d in (dirs if dirs is not None else LAUNCHER_DIRS):
        base = Path(d).expanduser()
        if not base.is_dir():
            continue
        for f in base.iterdir():
            if not f.is_file() or f.resolve() in seen:
                continue
            seen.add(f.resolve())
            # Launchers are small scripts and desktop entries. Reading every
            # regular file in ~/bin whole took 3.98s here -- 107MB, most of it
            # binaries -- and clean() called this once per selected item, on the
            # GUI thread. Cap it and skip anything that is not text.
            try:
                if f.stat().st_size > LAUNCHER_MAX_BYTES:
                    continue
                text = f.read_text()
            except (OSError, UnicodeError, ValueError):
                continue
            if p not in text:
                continue
            for line in text.splitlines():
                at = 0
                while True:
                    at = line.find(p + "/", at)
                    if at < 0:
                        break
                    rest = line[at + len(p) + 1:]
                    name = rest.split("/", 1)[0]
                    if name and (Path(p) / name / "bin" / "wine").is_file():
                        found.add(name)
                    at += 1
    return found


def protected_builds(prefix) -> set[str]:
    """Wine builds that must never be removed.

    The one actually mapped into a running process, the one the
    ElementalWarriorWine symlink names, and the symlink itself. probe.active_wine
    marks a guess from the symlink with a "(link)" suffix; strip it, because for
    this purpose a guess is still a reason to keep the build."""
    p = Path(prefix).expanduser()
    keep = {"ElementalWarriorWine"}

    active = probe.active_wine(p)
    if active:
        keep.add(active.removesuffix(" (link)"))

    link = p / "ElementalWarriorWine"
    if link.is_symlink():
        try:
            keep.add(Path(os.readlink(link)).name)
        except OSError:
            pass

    # The launchers hardcode their Wine and outrank the symlink.
    keep |= builds_named_by_launchers(p)
    return keep


def cleanable(prefix) -> list[Item]:
    """Everything that could be removed from this prefix, largest first.

    Nothing here is required to run Affinity. Wine builds are offered only when
    they are neither running nor named by the ElementalWarriorWine symlink."""
    p = Path(prefix).expanduser()
    if not probe.is_prefix(p):
        raise NotAPrefix(f"{p} does not look like a Wine prefix.")

    keep = protected_builds(p)
    items: list[Item] = []

    for d in sorted(p.iterdir()):
        if not d.is_dir() or d.is_symlink():
            continue
        if not (d / "bin" / "wine").is_file():
            continue
        if d.name in keep:
            continue
        items.append(Item(d, "wine-build", _du(d),
                          "A Wine build this prefix is not using"))

    # A symlinked build costs nothing, but a dangling one is worth offering.
    for d in sorted(p.iterdir()):
        if d.is_symlink() and d.name not in keep and not d.exists():
            items.append(Item(d, "wine-build", 0,
                              "A symlink to a Wine build that is gone",
                              is_symlink=True))

    for f in sorted(p.glob("*")):
        if f.is_file() and f.name.endswith((".tar.xz", ".tar.gz", ".tgz", ".zip")):
            items.append(Item(f, "archive", _du(f),
                              "A downloaded archive, already unpacked beside it"))

    # Copies left by hand or by a previous run of this tool.
    for pattern in ("*.bak-*", "*.pre-*", "*.pre*-20*", "*.aside-*", "*.orig-backup", "*.tmp"):
        for f in sorted(p.rglob(pattern)):
            if f.is_file() and not f.is_symlink():
                items.append(Item(f, "backup", _du(f),
                                  "A saved-aside copy"))

    for sub in ("drive_c/windows/temp", "drive_c/users"):
        base = p / sub
        if not base.is_dir():
            continue
        for tmp in base.rglob("Temp"):
            if tmp.is_dir() and not tmp.is_symlink():
                size = _du(tmp)
                if size:
                    items.append(Item(tmp, "temp", size, "Wine's temporary files"))
        if sub.endswith("temp") and any(base.iterdir()):
            size = _du(base)
            if size:
                items.append(Item(base, "temp", size, "Wine's temporary files"))

    seen: set[Path] = set()
    unique = []
    for it in items:
        if it.path in seen:
            continue
        seen.add(it.path)
        unique.append(it)
    return sorted(unique, key=lambda i: i.size, reverse=True)


def clean(prefix, items, *, dry_run: bool = False) -> tuple[int, list[str]]:
    """Remove the given items. Returns (bytes freed, problems).

    Refuses outright if the prefix is running, and re-checks every item against
    protected_builds() rather than trusting the caller's list -- the plan may
    have been built before Affinity was started."""
    p = Path(prefix).expanduser()
    # A dry run reads and reports; only an actual removal needs an idle prefix.
    if not dry_run:
        _require_idle(p)

    keep = protected_builds(p)
    freed = 0
    problems: list[str] = []

    for item in items:
        target = Path(item.path)
        try:
            target.relative_to(p)
        except ValueError:
            problems.append(f"refused {target}: outside the prefix")
            continue
        if target == p:
            problems.append("refused the prefix itself")
            continue
        # Refuse anything INSIDE a protected build, not just a build itself.
        # Keying on item.kind let every other kind through: the saved-aside
        # copies of patched DLLs live inside the running build and are classed
        # "backup", so "remove selected" deleted the only way to back the
        # patches out, from under a Wine that was in use.
        protected = next((b for b in keep
                          if target == p / b or _is_inside(target, p / b)), None)
        if protected:
            problems.append(f"refused {target.name}: inside {protected}, which is in use")
            continue
        if not target.exists() and not target.is_symlink():
            continue
        if dry_run:
            freed += item.size
            continue
        try:
            if target.is_symlink() or target.is_file():
                target.unlink()
            elif item.kind == "temp":
                # Empty it, do not remove it. %TEMP% and C:\windows\temp are
                # expected to exist: Wine and the installer write into them
                # without creating them, and these rows are ticked by default,
                # so "reclaim space" quietly broke the prefix.
                for child in target.iterdir():
                    if child.is_symlink() or child.is_file():
                        child.unlink()
                    else:
                        shutil.rmtree(child)
            else:
                shutil.rmtree(target)
            freed += item.size
        except OSError as exc:
            problems.append(f"{target}: {exc}")
    return freed, problems


def plan_clone(source, dest, *, keep_builds=None) -> Plan:
    """What clone() would copy. Does not touch the filesystem.

    keep_builds names the Wine builds to carry over; None keeps them all.
    There is deliberately no "keep the one it uses" shortcut -- which build a
    stopped prefix uses cannot be known, only guessed, and the guess was
    wrong in practice."""
    src = Path(source).expanduser()
    dst = Path(dest).expanduser()
    if not probe.is_prefix(src):
        raise NotAPrefix(f"{src} does not look like a Wine prefix.")
    if dst.exists() and any(dst.iterdir()):
        raise DestinationInUse(f"{dst} exists and is not empty.")
    # Careful: DestinationInUse subclasses ValueError, so raising it inside the
    # try would be swallowed by the except that is there to catch relative_to.
    inside = True
    try:
        dst.resolve().relative_to(src.resolve())
    except ValueError:
        inside = False
    if inside:
        raise DestinationInUse(f"{dst} is inside {src}.")

    builds = [b for b in probe.wine_builds(src) if b != "ElementalWarriorWine"]

    if keep_builds is None:
        # No explicit choice: keep everything. Guessing from active_wine() was
        # tried and was wrong -- with nothing running it falls back to the
        # ElementalWarriorWine symlink, which its own docstring says
        # demonstrably lies, and a clone built on that keeps the wrong Wine.
        drop = []
    else:
        wanted = set(keep_builds)
        drop = [b for b in builds if b not in wanted]

    est = _du(src) - sum(_du(src / b) for b in drop)
    return Plan(src, dst, [b for b in builds if b not in drop], drop, est)


def describe_builds(prefix) -> list[dict]:
    """Each Wine build in the prefix, with size and why it might matter.

    The note is the point. A stopped prefix cannot say which Wine it runs --
    active_wine() falls back to the ElementalWarriorWine symlink, and that
    symlink has been observed naming 11.12 while the prefix ran 11.16. So the
    running case is reported as fact and the symlink as a claim."""
    p = Path(prefix).expanduser()
    running = probe.wine_of_running(p)
    linked = None
    link = p / "ElementalWarriorWine"
    if link.is_symlink():
        try:
            linked = Path(os.readlink(link)).name
        except OSError:
            pass

    launched = builds_named_by_launchers(p)

    out = []
    for name in probe.wine_builds(p):
        if name == "ElementalWarriorWine":
            continue
        if name == running:
            note, suggest = "running now", True
        elif name in launched:
            note, suggest = "named by a launcher or desktop entry", True
        elif name == linked:
            note, suggest = "named by the ElementalWarriorWine symlink (which can be stale)", True
        else:
            note, suggest = "not referenced", False
        out.append({
            "name": name,
            "size": _du(p / name),
            "note": note,
            "suggested": suggest,
        })
    return out

def clone(plan: Plan, *, progress=None) -> list[str]:
    """Copy the prefix described by the plan, then repoint its own symlinks.

    Symlinks are preserved as symlinks -- dereferencing a symlinked Wine build
    would duplicate hundreds of megabytes, and dereferencing dosdevices would
    turn drive letters into copies of whole filesystems. Any absolute symlink
    that pointed inside the source is rewritten to point inside the copy, so the
    clone cannot write back into the original."""
    src, dst = plan.source, plan.dest
    _require_idle(src)

    # Re-validate the destination. The plan may have been built minutes ago, in
    # a dialog, and a prefix is several gigabytes: by the time the user presses
    # the button the destination can have become something else.
    if not probe.is_prefix(src):
        raise NotAPrefix(f"{src} does not look like a Wine prefix.")
    if dst.exists() and not dst.is_dir():
        raise DestinationInUse(f"{dst} exists and is not a directory.")
    if dst.exists() and any(dst.iterdir()):
        raise DestinationInUse(f"{dst} exists and is not empty.")
    if _is_inside(dst.resolve(), src.resolve()):
        raise DestinationInUse(f"{dst} is inside {src}.")

    # Running out of disk half way through is the most likely way this fails,
    # and the result is a prefix that looks complete. plan_clone already
    # measured the source; ask before starting rather than discovering later.
    dst.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(dst).free
    if plan.est_size and free < plan.est_size * 1.05:
        raise NotEnoughSpace(
            f"{probe.human_size(plan.est_size)} to copy but only "
            f"{probe.human_size(free)} free on {dst}."
        )

    problems: list[str] = []
    copy_tree(src, dst, progress=progress, exclude_top=plan.drop_builds,
              delete=True)

    problems += repoint_symlinks(src, dst)

    # A dropped build can strand ElementalWarriorWine. Prefer whatever the
    # source's launchers named, since that is what the prefix actually runs.
    named = fix_wine_symlink(dst, prefer=sorted(builds_named_by_launchers(src)))
    if named:
        problems.append(f"ElementalWarriorWine -> {named}")
    elif plan.keep_builds:
        problems.append("ElementalWarriorWine could not be pointed at a build")
    return problems


def copy_tree(src, dst, *, progress=None, exclude_top=(), delete=False,
              hard_links=False) -> None:
    """Copy a directory tree exactly: symlinks as symlinks, modes and times kept.

    The one copier, shared by clone and backup, so the fixes below live in one
    place. Raises CloneFailed on any failure -- a copy that half-finished and
    said nothing is how a truncated prefix got registered as a usable one.

    `exclude_top` names entries directly inside `src` to leave out. Only at the
    top: the fallback used to pass them to shutil.ignore_patterns, which
    ignores a matching name at ANY depth, so a folder inside drive_c that
    happened to share a Wine build's name would have been skipped too."""
    src, dst = Path(src), Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    cmd = ["rsync", "-a", "--info=progress2"]
    if hard_links:
        cmd.append("-H")
    if delete:
        cmd.append("--delete")
    for name in exclude_top:
        cmd += ["--exclude", f"/{name}/", "--exclude", f"/{name}"]
    cmd += [f"{src}/", f"{dst}/"]

    if shutil.which("rsync"):
        # --info=progress2 writes a running percentage, but on one line
        # terminated by \r rather than \n, so readline() would block until the
        # copy finished and the bar would jump from 0 to 100. Read raw and split
        # on both.
        # stderr goes to a file, not a pipe. Only stdout is read below, and a
        # pipe nobody drains fills at 64K: a prefix with a few hundred
        # unreadable files filled it, rsync blocked writing, this loop blocked
        # waiting for stdout, and the whole manager hung with the progress bar
        # frozen and every button greyed out.
        with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as errf:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=errf, text=True, bufsize=1)
            tail = ""
            while True:
                chunk = proc.stdout.read(256) if proc.stdout else ""
                if not chunk:
                    break
                tail += chunk
                parts = re.split(r"[\r\n]", tail)
                tail = parts.pop()
                for line in parts:
                    m = re.search(r"(\d+)%", line)
                    if m and progress:
                        progress(int(m.group(1)))
            proc.wait()
            if proc.returncode != 0:
                errf.seek(0)
                err = errf.read().strip().splitlines()
                # Raise. Appending to problems let the caller announce "Cloned"
                # and register a truncated prefix as a usable one.
                raise CloneFailed(
                    f"rsync exited {proc.returncode}: "
                    f"{err[-1] if err else 'no output'}"
                )
    else:
        top = str(src)
        skip = set(exclude_top)

        def ignore(directory, names):
            return [n for n in names if directory == top and n in skip]

        try:
            shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True,
                            ignore=ignore)
        except (OSError, shutil.Error) as exc:
            raise CloneFailed(f"copy failed: {exc}") from exc
    if progress:
        progress(100)



def fix_wine_symlink(prefix, *, prefer=()) -> str | None:
    """Make ElementalWarriorWine name a build that is actually present.

    A clone that leaves out Wine builds can strand this symlink: drop 11.12 and
    keep 11.16, and the link still says 11.12. Nothing complains until the
    installer resolves Wine through it, finds nothing, and reports that Wine
    setup has not finished -- on a prefix that has a perfectly good Wine sitting
    beside the broken link.

    Returns the build it now names, or None if the prefix has no Wine at all
    (in which case the dangling link is removed rather than left lying)."""
    p = Path(prefix).expanduser()
    link = p / "ElementalWarriorWine"

    if link.is_symlink() and link.exists():
        return Path(os.readlink(link)).name

    # A real directory, not a link. The stock installer unpacks Wine straight
    # into ElementalWarriorWine/, and treating that as a stale link meant
    # unlink() on a directory: IsADirectoryError, out of a function whose whole
    # job is to leave the prefix runnable.
    if link.exists() and not link.is_symlink():
        if (link / "bin" / "wine").is_file():
            return link.name
        return None

    builds = [b for b in probe.wine_builds(p) if b != "ElementalWarriorWine"]
    if not builds:
        if link.is_symlink():
            link.unlink()
        return None

    choice = next((b for b in prefer if b in builds), None) or max(builds, key=_build_rank)
    try:
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(choice)
    except OSError:
        return None
    return choice


def _build_rank(name: str):
    """Order Wine builds by version, preferring a plain version-named one.

    sorted()[-1] is lexicographic, and on the real prefix that picks
    ElementalWarrior-wine-11.16.stock-2026-09-08 over
    ElementalWarrior-wine-11.16 -- the stock build, with none of the prefix's
    patches. A clone pointed at it misbehaves in ways that read as a new
    regression. Rank by the version number, then prefer the name with nothing
    after it: a suffix means a variant or a dated backup."""
    m = re.search(r"(\d+(?:\.\d+)+)", name)
    version = tuple(int(x) for x in m.group(1).split(".")) if m else ()
    suffix = name[m.end():] if m else name
    return (version, 1 if not suffix.strip("-. ") else 0, name)


def repoint_symlinks(source, dest) -> list[str]:
    """Rewrite absolute symlinks in dest that point inside source.

    A prefix copied with -a keeps relative links (dosdevices/c: -> ../drive_c)
    correct for free, and absolute links to elsewhere on the system (z: -> /,
    the /dev/* device nodes) are correct as they are. The ones that matter are
    absolute links into the source prefix: ElementalWarriorWine when the
    installer wrote it absolute, and any build symlinked from a build tree."""
    src = str(Path(source).expanduser().resolve())
    src_raw = str(Path(source).expanduser())
    dst = Path(dest).expanduser().resolve()
    fixed: list[str] = []

    for root, dirs, files in os.walk(dst, followlinks=False):
        for name in list(dirs) + list(files):
            link = Path(root) / name
            if not link.is_symlink():
                continue
            try:
                target = os.readlink(link)
            except OSError:
                continue
            # Compare RESOLVED paths, and the unresolved spelling too. Testing
            # only the raw readlink text against a resolved source missed any
            # link written through a symlinked component -- and this machine has
            # exactly that shape, with ~/work -> /mnt/work. The link then still
            # resolved into the source, so the clone could write back into the
            # original, which is the one thing this function exists to prevent.
            abstarget = os.path.realpath(os.path.join(root, target))
            if abstarget == src or abstarget.startswith(src + "/"):
                inside = abstarget[len(src):].lstrip("/")
            elif target == src_raw or target.startswith(src_raw + "/"):
                inside = target[len(src_raw):].lstrip("/")
            else:
                continue
            new = str(dst / inside) if inside else str(dst)
            try:
                link.unlink()
                link.symlink_to(new)
                fixed.append(f"{link.relative_to(dst)} -> {new}")
            except OSError as exc:
                fixed.append(f"could not repoint {link}: {exc}")
    return fixed


# ── moving a prefix, and the launchers that name it ──────────────────────────
#
# The cold-start case this exists for: somebody has ~/.AffinityLinux from an
# ordinary AffinityOnLinux install, and wants it managed. Managing it where it
# is is one option and always offered. Moving it under the manager's base
# directory is the other, and is only useful if the launchers that name the old
# path follow it -- otherwise the prefix moves and the menu entry the user
# clicks every day stops working, which is a worse state than before.


class LauncherRefused(RuntimeError):
    """A launcher names the prefix but could not be rewritten."""


@dataclass
class RelocatePlan:
    source: Path
    dest: Path
    same_filesystem: bool
    size: int
    launchers: list[Path]

    @property
    def instant(self) -> bool:
        """A rename on one filesystem moves no bytes and cannot half-finish."""
        return self.same_filesystem


def _device_of_nearest_existing(path: Path) -> int:
    """st_dev of path, or of the closest parent that exists.

    The destination usually does not exist yet, and its filesystem is the one
    that decides whether this is a rename or a copy."""
    p = path
    while True:
        try:
            return os.stat(p).st_dev
        except OSError:
            if p.parent == p:
                raise
            p = p.parent


def launchers_naming(prefix, dirs=None) -> list[Path]:
    """Files under the launcher directories that mention this prefix.

    Same reading rules as builds_named_by_launchers -- small text files only --
    because the same ~/bin full of binaries is being walked."""
    p = str(Path(prefix).expanduser())
    out: list[Path] = []
    seen: set[Path] = set()
    for d in (dirs if dirs is not None else LAUNCHER_DIRS):
        base = Path(d).expanduser()
        if not base.is_dir():
            continue
        for f in sorted(base.iterdir()):
            if not f.is_file():
                continue
            real = f.resolve()
            if real in seen:
                continue
            seen.add(real)
            try:
                if f.stat().st_size > LAUNCHER_MAX_BYTES:
                    continue
                text = f.read_text()
            except (OSError, UnicodeError, ValueError):
                continue
            if _names_path(text, p):
                out.append(f)
    return out


# What ends a path in a launcher or a desktop entry when it is not quoted.
# Everything except "/" and NUL is legal in a POSIX filename, so this is a list
# of what a shell or a .desktop file uses to separate things, not a list of
# what a filename may not contain.
_DELIMITERS = " \t\n\r\f\v\"';:=,|&<>()"


def _token_at(text: str, at: int) -> str:
    """The whole path token containing the match that starts at `at`.

    This is the part a lookahead cannot do. ~/.AffinityLinux is a prefix of
    ~/.AffinityLinuxManager, of ~/.AffinityLinux-winetest, AND of
    "~/.AffinityLinux 3.3" -- and the last one defeats any rule about the next
    character, because a space is both a perfectly legal filename character and
    the usual separator. The only way to tell them apart is to read the token
    whole and compare it.

    A match sitting immediately after a quote runs to the closing quote, which
    is how a path with a space in it is written. Otherwise it runs to the first
    delimiter."""
    quote = text[at - 1] if at > 0 else ""
    if quote in ("'", '"'):
        end = text.find(quote, at)
        return text[at:end if end >= 0 else len(text)]
    end = at
    while end < len(text) and text[end] not in _DELIMITERS:
        end += 1
    return text[at:end]


def _references(text: str, path: str):
    """Every place `text` really names `path` or something inside it.

    Yields (start, token). A token that merely begins with the path -- a
    sibling directory, a longer name -- is not a reference and is skipped."""
    at = 0
    while True:
        at = text.find(path, at)
        if at < 0:
            return
        token = _token_at(text, at)
        if token == path or token.startswith(path + "/"):
            yield at, token
        at += 1


def _names_path(text: str, path: str) -> bool:
    return any(True for _ in _references(text, path))


def plan_relocate(source, dest, *, size=None) -> RelocatePlan:
    """What relocate() would do. Touches nothing.

    `size` lets a caller that already measured the prefix skip the walk. A
    prefix is several gigabytes and du is not free, which matters when the
    caller is a dialog rebuilding its text as somebody types."""
    src = Path(source).expanduser()
    dst = Path(dest).expanduser()
    if not probe.is_prefix(src):
        raise NotAPrefix(f"{src} does not look like a Wine prefix.")
    # A symlinked source is refused, not followed. os.rename on a symlink
    # renames the LINK: the prefix would not move at all, the old location
    # would keep working, and the manager would report a move that did not
    # happen. Everything else here follows links -- probe.is_prefix through
    # is_dir(), the device check through os.stat -- so nothing else notices.
    if src.is_symlink():
        raise NotAPrefix(
            f"{src} is a symlink to {os.path.realpath(src)}. Moving it would "
            f"move the link and leave the prefix where it is. Move "
            f"{os.path.realpath(src)} instead, or manage this one in place.")
    if dst.is_symlink():
        raise DestinationInUse(
            f"{dst} is a symlink. Remove it, or choose another name: moving "
            "onto it would write through it to somewhere unexpected.")
    if dst.exists() and not dst.is_dir():
        raise DestinationInUse(f"{dst} exists and is not a directory.")
    if dst.exists() and any(dst.iterdir()):
        raise DestinationInUse(f"{dst} exists and is not empty.")
    if _is_inside(dst.resolve() if dst.exists() else dst, src.resolve()):
        raise DestinationInUse(f"{dst} is inside {src}.")

    same = _device_of_nearest_existing(src) == _device_of_nearest_existing(dst)
    size = _du(src) if size is None else size
    if not same:
        free = shutil.disk_usage(
            dst if dst.exists() else dst.parent if dst.parent.exists()
            else Path.home()).free
        if size and free < size * 1.05:
            raise NotEnoughSpace(
                f"{probe.human_size(size)} to move but only "
                f"{probe.human_size(free)} free at {dst}."
            )
    return RelocatePlan(src, dst, same, size, launchers_naming(src))


def relocate(plan: RelocatePlan, *, progress=None, remove_source=False) -> list[str]:
    """Move a prefix to a new path, and fix what pointed at the old one.

    Two quite different operations wearing one name. On the same filesystem it
    is os.rename: instant, atomic, and with no window in which two copies
    exist. Across filesystems it is a copy, and then the source is left alone
    unless the caller explicitly asks for it to go -- an interrupted
    copy-then-delete is how a prefix is lost, and nobody should discover that
    "move" meant "delete the original" after the fact.

    Absolute symlinks inside the tree are repointed either way. A rename does
    not rewrite them, and the installer has been seen writing
    ElementalWarriorWine absolute, which would leave the moved prefix running
    Wine out of the old location -- or out of nothing, once it is gone."""
    src, dst = plan.source, plan.dest
    _require_idle(src)
    if not probe.is_prefix(src):
        raise NotAPrefix(f"{src} does not look like a Wine prefix.")
    # Re-checked, because the plan may be minutes old: a dialog was open.
    if src.is_symlink():
        raise NotAPrefix(f"{src} is a symlink; moving it would move the link.")
    if dst.is_symlink():
        raise DestinationInUse(f"{dst} is a symlink.")
    if dst.exists() and any(dst.iterdir()):
        raise DestinationInUse(f"{dst} exists and is not empty.")

    notes: list[str] = []
    if plan.same_filesystem:
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            if dst.exists():
                dst.rmdir()          # empty, checked above; rename needs it gone
            os.rename(src, dst)
        except OSError as exc:
            # Including the rmdir. It used to sit outside this try, so a
            # destination that was not the directory it looked like raised a
            # bare NotADirectoryError all the way out through the Qt slot that
            # called it -- which aborts the process.
            raise CloneFailed(f"could not move {src} to {dst}: {exc}") from exc
        if progress:
            progress(100)
        notes.append(f"Moved {src} to {dst}")
    else:
        copy = Plan(src, dst, [], [], plan.size)
        notes += clone(copy, progress=progress)
        notes.append(f"Copied {src} to {dst} (different filesystem)")
        if remove_source:
            try:
                shutil.rmtree(src)
                notes.append(f"Removed {src}")
            except OSError as exc:
                notes.append(f"Copied, but could not remove {src}: {exc}")
        else:
            notes.append(f"{src} is still there, and still {probe.human_size(plan.size)}")

    notes += repoint_symlinks(src, dst)
    return notes


def repoint_launchers(old, new, *, dirs=None, dry_run=False) -> list[str]:
    """Rewrite launchers and desktop entries that name the old path.

    The point of moving a prefix is that everything keeps working afterwards.
    A desktop entry with a stale Exec= is not a cosmetic problem: it is the
    button the user actually presses.

    Every file is backed up beside itself before it is changed. These are the
    user's own scripts, some of them hand-edited, and a bad substitution in one
    of them is not something this application should make unrecoverable."""
    old_s = str(Path(old).expanduser())
    new_s = str(Path(new).expanduser())
    changed: list[str] = []

    for f in launchers_naming(old_s, dirs):
        try:
            text = f.read_text()
        except (OSError, UnicodeError) as exc:
            changed.append(f"could not read {f}: {exc}")
            continue

        # Sliced, not substituted. re.sub treats the replacement as a TEMPLATE,
        # so a base directory containing a backslash -- which the user types
        # freely into the settings field, and which is created verbatim -- had
        # its escapes interpreted: \\P became a bad-escape error and \\1 became
        # a group reference. Nothing here is a pattern.
        spots = list(_references(text, old_s))
        if not spots:
            continue
        pieces, cursor = [], 0
        for at, _token in spots:
            pieces.append(text[cursor:at])
            pieces.append(new_s)
            cursor = at + len(old_s)
        pieces.append(text[cursor:])
        updated, count = "".join(pieces), len(spots)

        if dry_run:
            changed.append(f"{f}: {count} reference(s) would be updated")
            continue
        try:
            # A stamped name, like registry.aside_path. A fixed
            # ".before-move" was truncated by the second move of the same
            # prefix, so the copy of the launcher as the user originally wrote
            # it was destroyed by the very mechanism meant to preserve it.
            backup = _unused_backup(f)
            backup.write_text(text)
            shutil.copymode(f, backup)
            f.write_text(updated)
        except OSError as exc:
            changed.append(f"could not rewrite {f}: {exc}")
            continue
        changed.append(f"{f}: {count} reference(s) updated (kept {backup.name})")
    return changed


def _unused_backup(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.before-move-{stamp}")
    n = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.before-move-{stamp}-{n}")
        n += 1
    return candidate
