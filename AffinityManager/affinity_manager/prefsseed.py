"""Carrying preferences and recent files from one prefix into another.

A new prefix starts with the stock settings AffinityOnLinux installs, which is
right for somebody installing Affinity for the first time and wrong for
somebody who has been using it for a year and is building a second prefix to
test 3.3 in. What they want is their own workspace, their shortcuts and their
recent files -- not a fresh start they then have to undo by hand.

There are two ways to copy, and they are not interchangeable:

  FILL      Only files the destination does not already have. This is the rule
            the installer uses when it lays down stock settings, and the reason
            it uses it: replacing that directory wipes the user's preferences
            AND RecentFiles.xml, which is exactly the bug that started this.

  REPLACE   What the user is actually asking for when they say "copy my
            settings over". The destination's Settings directory is renamed
            aside first, with the date in its name, so the answer to "that was
            not what I wanted" is a rename rather than a reinstall.

Nothing here decides which. The caller asks, and the default offered is REPLACE
only because the user reached for this deliberately; FILL is what happens
without being asked for.

Not everything beside Settings is a setting. The version folder also holds
Affinity's crash-recovery autosaves (205 MB of them in the working prefix this
was written against, the oldest from December), the WebView2 browser profile,
temp directories, crash reports, logs, and a pid file that exists only while
Affinity is running. An earlier version copied all of it on the claim that "the
version folder is configuration and nothing else" -- a claim made without ever
listing a real one. So every entry is now one of three kinds, and only one kind
is carried.

Drive letters travel too, because recent files are Windows paths. 89 of the 117
recents in that prefix were paths on W:, and a fresh prefix has only C: and Z:.
"""

from __future__ import annotations

import collections
import getpass
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

FILL = "fill"
REPLACE = "replace"

# <prefix>/drive_c/users/<user>/AppData/Roaming/Affinity/Affinity/<version>/Settings
APPDATA_TAIL = ("AppData", "Roaming", "Affinity", "Affinity")


# ── what is in the version folder ────────────────────────────────────────────

CONFIG = "config"         # carried into a new prefix, and kept in snapshots
VOLATILE = "volatile"     # never carried, never snapshotted
UNKNOWN = "unknown"       # kept in snapshots, left behind by a carry, and named

# Known to be the user's configuration. Everything a person set up by hand:
# workspace layouts, shortcuts, print presets, colour profiles, plugins, lens
# profiles, fonts Affinity downloaded, the home-screen state, and the MCP
# server config the Affinity scripting bridge reads.
CONFIG_NAMES = frozenset({
    "Workspaces", "user", "profiles", "printing", "Plugins", "LensProfiles",
    "AffinityFonts", "preferences.dat", "studios3.dat", "home_favourites3.dat",
    "home_newdocument.dat", "notificationoptions.dat", "mcp.json",
})

# Known to be state belonging to one prefix's running history, not to the user.
#   autosave      crash-recovery files from sessions that did not end cleanly.
#                 In a different prefix they are at best dead weight and at
#                 worst an offer to "recover" documents on first launch.
#   backup        Affinity's own document backups, likewise.
#   pid           exists only while Affinity runs. Copied mid-session it would
#                 start the new prefix with a pid from a process in another one.
#   EBWebView     the WebView2 browser profile -- shader cache, crash dumps,
#                 metrics, and the runtime version it was built against.
#   temp, temp-critical, CrashReports, and logs: what the names say.
VOLATILE_NAMES = frozenset({
    "autosave", "backup", "pid", "EBWebView", "temp", "temp-critical",
    "CrashReports", "Log.txt",
})
VOLATILE_SUFFIXES = (".log",)


# And the sibling Common/<version> folder, shared by everything Affinity 3
# runs as. Found 2026-10-01 when a carried prefix came up without its recent
# fonts, fill presets, object styles, new-document presets or user dictionary:
# the carry only ever looked at Affinity/<version>.
#   Settings      Fonts.xml -- recently used and favourite font families.
#   user          the user's own presets: fills, object styles, document
#                 presets, dictionary, preflight, adjustments, macros...
#   modelcache    the AI models (segmentation, and others as they are used).
#                 Downloadable, but large -- 554 MB in the prefix this was
#                 written against -- and Affinity 3.3's liblearning.dll uses
#                 every generation found there, so carrying them saves the
#                 download and the wait the first time a feature needs one.
COMMON_CONFIG_NAMES = frozenset({"Settings", "user", "modelcache"})
#   sp.db*        an analytics event queue (24 MB in the prefix this was
#                 written against), not settings.
#   cs.dat/json   the cached dynamic configuration Affinity fetches.
#   ipc.dat, locks  this prefix's running state.
#   clipboard     Affinity's clipboard cache.
COMMON_VOLATILE_NAMES = frozenset({
    "sp.db", "sp.db-wal", "sp.db-shm", "cs.dat", "cs.json", "ipc.dat",
    "locks", "clipboard",
})

# And two folders in the Windows user's own profile, outside Affinity's
# entirely: the Windows Favorites and Links folders, whose shortcuts are what
# a file chooser offers as places. In the working prefix they are symlinks to
# client folders; a carried prefix came up with neither (2026-10-01).
PROFILE_CONFIG_NAMES = ("Favorites", "Links")


def kind_of_common(name: str) -> str:
    """kind_of for an entry in Common/<version>."""
    if name in COMMON_CONFIG_NAMES:
        return CONFIG
    if name in COMMON_VOLATILE_NAMES or name.lower().endswith(VOLATILE_SUFFIXES):
        return VOLATILE
    return UNKNOWN


def kind_of(name: str) -> str:
    """CONFIG, VOLATILE or UNKNOWN for one entry in a version folder.

    UNKNOWN is deliberate rather than a gap. A carry that took unrecognised
    entries would drag the next cache Affinity invents into every new prefix; a
    snapshot that dropped them would lose the next setting it invents. So a
    snapshot keeps them, a carry leaves them where they are and says so by
    name, and nothing is lost either way -- the source is only ever read."""
    if name in CONFIG_NAMES:
        return CONFIG
    if name in VOLATILE_NAMES or name.lower().endswith(VOLATILE_SUFFIXES):
        return VOLATILE
    return UNKNOWN


@dataclass
class Settings:
    """One Settings directory found inside a prefix."""

    prefix: Path
    path: Path
    version: str
    files: int
    bytes: int
    modified: float

    @property
    def has_recents(self) -> bool:
        return (self.path / "RecentFiles.xml").is_file()

    def _beside(self) -> list:
        version = self.path.parent
        if not version.is_dir():
            return []
        return [e for e in sorted(version.iterdir()) if e.name != "Settings"]

    @property
    def extras(self) -> list:
        """The configuration beside Settings -- and only that.

        Affinity keeps workspace layouts and keyboard shortcuts here, not
        inside Settings, so they have to travel; copying only Settings produced
        the source's preferences next to the destination's workspaces. But the
        same folder holds autosaves, a WebView2 profile and a live pid file,
        and those must not. See kind_of."""
        return [e for e in self._beside() if kind_of(e.name) == CONFIG]

    @property
    def left_behind(self) -> list:
        """(entry, kind) for everything a carry does not take, so it can be
        named to the user rather than silently dropped."""
        return [(e, kind_of(e.name)) for e in self._beside()
                if kind_of(e.name) != CONFIG]

    @property
    def common_dir(self) -> Path:
        """<...>/Roaming/Affinity/Common/<version>, beside Affinity/<version>."""
        version = self.path.parent
        return version.parent.parent / "Common" / version.name

    def _common(self) -> list:
        common = self.common_dir
        if not common.is_dir():
            return []
        return sorted(common.iterdir())

    @property
    def common_extras(self) -> list:
        """The configuration in Common/<version> -- see COMMON_CONFIG_NAMES."""
        return [e for e in self._common() if kind_of_common(e.name) == CONFIG]

    @property
    def profile_dir(self) -> Path:
        """drive_c/users/<user>: Settings is <user>/AppData/Roaming/Affinity/
        Affinity/<version>/Settings."""
        return self.path.parents[5]

    @property
    def profile_extras(self) -> list:
        """Favorites and Links, where they exist and hold anything."""
        out = []
        for name in PROFILE_CONFIG_NAMES:
            p = self.profile_dir / name
            try:
                if p.is_dir() and not p.is_symlink() and any(p.iterdir()):
                    out.append(p)
            except OSError:
                pass
        return out

    @property
    def common_left_behind(self) -> list:
        return [(e, kind_of_common(e.name)) for e in self._common()
                if kind_of_common(e.name) != CONFIG]

    def recents_by_drive(self) -> collections.Counter:
        """How many recent files sit on each drive letter.

        This is what makes the drive-letter import worth having: a count next
        to W: says which mappings the recent-files list actually depends on."""
        counts = collections.Counter()
        try:
            text = (self.path / "RecentFiles.xml").read_text(errors="replace")
        except OSError:
            return counts
        for letter in re.findall(r"(?<![A-Za-z0-9])([A-Za-z]):\\", text):
            counts[letter.upper()] += 1
        return counts


def _measure(path: Path) -> tuple[int, int, float]:
    files = size = 0
    newest = 0.0
    for f in path.rglob("*"):
        if not f.is_file():
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        files += 1
        size += st.st_size
        newest = max(newest, st.st_mtime)
    return files, size, newest


def settings_in(prefix) -> list[Settings]:
    """Every Affinity Settings directory in a prefix, newest first.

    Globbed rather than built from the current username: a prefix created on
    another machine, or by an installer run as a different user, has the other
    user's name in that path, and refusing to see it would be refusing to see
    the settings the user is pointing at."""
    p = Path(prefix).expanduser()
    users = p / "drive_c" / "users"
    out: list[Settings] = []
    if not users.is_dir():
        return out
    for user in sorted(users.iterdir()):
        root = user.joinpath(*APPDATA_TAIL)
        if not root.is_dir():
            continue
        for version in sorted(root.iterdir()):
            found = version / "Settings"
            if not found.is_dir():
                continue
            files, size, modified = _measure(found)
            if not files:
                continue
            out.append(Settings(p, found, version.name, files, size, modified))
    out.sort(key=lambda s: s.modified, reverse=True)
    return out


def sources(prefixes, exclude=None) -> list[Settings]:
    """Settings worth offering as a source, across several prefixes.

    The destination is excluded: offering to copy a prefix's settings onto
    itself is an invitation to a mistake, not a feature."""
    skip = Path(exclude).expanduser().resolve() if exclude else None
    out: list[Settings] = []
    for prefix in prefixes:
        p = Path(prefix).expanduser()
        try:
            if skip and p.resolve() == skip:
                continue
        except OSError:
            continue
        out += settings_in(p)
    out.sort(key=lambda s: s.modified, reverse=True)
    return out


def resolve_source(path) -> Settings | None:
    """Make sense of a location the user typed or browsed to.

    They may point at a prefix, at the Settings directory itself, or at the
    version directory above it. All three mean the same thing and all three are
    accepted -- being told "that is not a prefix" when you have just selected
    the exact directory you meant is no help to anybody."""
    p = Path(path).expanduser()
    if not p.is_dir():
        return None
    if p.name == "Settings":
        files, size, modified = _measure(p)
        if files:
            return Settings(p, p, p.parent.name, files, size, modified)
        return None
    if (p / "Settings").is_dir():
        return resolve_source(p / "Settings")
    found = settings_in(p)
    return found[0] if found else None


# The accounts Wine creates that are never the person using it. The installer
# has its own copy of this list; both are here so the two agree about which
# user's AppData an Affinity install lives under.
NOT_A_PERSON = ("Public", "Default", "All Users", "Default User")


def destination_for(prefix, version=None) -> Path:
    """Where settings go in a prefix that may not have any yet.

    An existing Settings directory wins, because a prefix that has been started
    once has already decided its user name and version folder. Otherwise the
    current login name is preferred if Wine made a directory for it -- which it
    does -- and only then does this fall back to whatever else is there.

    The skip list matches the installer's. They used to differ: this one let
    "Default" and "Default User" through and then took the alphabetically
    first, so on a prefix holding both Default and joshua it chose Default,
    and settings were written where nothing would ever read them. The directory
    is not created here, so a caller that only wanted to look has changed
    nothing."""
    p = Path(prefix).expanduser()
    existing = settings_in(p)
    if existing:
        if version:
            for s in existing:
                if s.version == version:
                    return s.path
        return existing[0].path

    users = p / "drive_c" / "users"
    user = None
    if users.is_dir():
        names = [d for d in sorted(users.iterdir())
                 if d.is_dir() and d.name not in NOT_A_PERSON]
        me = getpass.getuser()
        user = next((d for d in names if d.name == me), names[0] if names else None)
    if user is None:
        user = users / getpass.getuser()
    return user.joinpath(*APPDATA_TAIL) / (version or "3.0") / "Settings"


@dataclass
class SeedResult:
    added: list
    replaced: list
    kept: list
    saved_aside: Path | None
    extras: list = None

    def __post_init__(self):
        if self.extras is None:
            self.extras = []


def plan(source: Settings, destination: Path) -> SeedResult:
    """What the user will end up with. Writes nothing.

    "replaced" means the destination has a file of that name today and will
    have the source's afterwards. It does NOT describe seed()'s mechanism: in
    REPLACE mode the whole destination folder is renamed aside first, so
    nothing is overwritten in place and nothing is lost. The old docstring
    called this "what seed() would do in REPLACE mode", which was wrong in a
    way that mattered -- it made the count look like a count of destroyed
    files."""
    added, replaced = [], []
    for src in sorted(source.path.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(source.path)
        (replaced if (destination / rel).exists() else added).append(rel)
    return SeedResult(added, replaced, [], None,
                      [e.name for e in source.extras]
                      + ["Common/" + e.name for e in source.common_extras]
                      + [e.name for e in source.profile_extras])


def aside_of(destination) -> Path | None:
    """The most recent .before-copy- directory beside this Settings folder.

    For the message shown when a copy fails. By then REPLACE has already
    renamed the old settings aside, so the prefix has no Settings folder and
    the only copy is under a name the user has never seen -- which is not
    something to leave them to work out."""
    dest = Path(destination).expanduser()
    try:
        found = [p for p in dest.parent.iterdir()
                 if p.name.startswith(dest.name + ".before-copy-")]
    except OSError:
        return None
    return max(found, key=lambda p: p.name) if found else None


def seed(source: Settings, destination, *, mode=REPLACE) -> SeedResult:
    """Copy one Settings directory into another prefix.

    In REPLACE mode the destination is renamed aside before anything is
    written, not deleted. Undoing a copy should be a rename, and the one thing
    nobody can get back by reinstalling is RecentFiles.xml."""
    dest = Path(destination).expanduser()
    saved_aside = None

    if mode == REPLACE and dest.is_dir() and any(dest.iterdir()):
        saved_aside = dest.with_name(
            "%s.before-copy-%s" % (dest.name, time.strftime("%Y-%m-%d-%H%M%S")))
        dest.rename(saved_aside)

    dest.mkdir(parents=True, exist_ok=True)
    added, replaced, kept = [], [], []
    for src in sorted(source.path.rglob("*")):
        rel = src.relative_to(source.path)
        target = dest / rel
        if src.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if target.exists():
            if mode == FILL:
                kept.append(rel)
                continue
            replaced.append(rel)
        else:
            added.append(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)

    # And the workspaces and shortcuts, which live beside Settings rather than
    # inside it. Copying only Settings left the new prefix with the source's
    # preferences and recents next to its own workspaces -- a configuration
    # that had never existed anywhere.
    extras = []
    version_dir = dest.parent
    # Common/<version>, the sibling of Affinity/<version>: the user's own
    # presets and font history. See COMMON_CONFIG_NAMES.
    common_dir = version_dir.parent.parent / "Common" / version_dir.name
    # ...and the Windows user's Favorites and Links: <user>/AppData/Roaming/
    # Affinity/Affinity/<version> -> <user>, four levels above <version>.
    profile_dir = version_dir.parents[4]
    stamp = time.strftime("%Y-%m-%d-%H%M%S")
    for entry, into, label in (
            [(e, version_dir, e.name) for e in source.extras]
            + [(e, common_dir, "Common/" + e.name) for e in source.common_extras]
            + [(e, profile_dir, e.name) for e in source.profile_extras]):
        target = into / entry.name
        if target.exists() or target.is_symlink():
            if mode == FILL:
                kept.append(Path("..") / label)
                continue
            # Renamed aside, like Settings. This used to rmtree what it
            # displaced, while the module docstring promised REPLACE deletes
            # nothing -- true for Settings only.
            target.rename(target.with_name("%s.before-copy-%s" % (entry.name, stamp)))
        into.mkdir(parents=True, exist_ok=True)
        if entry.is_dir() and not entry.is_symlink():
            shutil.copytree(entry, target, symlinks=True)
        else:
            shutil.copy2(entry, target, follow_symlinks=False)
        extras.append(label)

    return SeedResult(added, replaced, kept, saved_aside, extras)


# ── drive letters ────────────────────────────────────────────────────────────
#
# A Wine drive letter is a symlink in <prefix>/dosdevices: "w:" -> /mnt/work.
# Recent files, and paths stored inside documents, are Windows paths, so a new
# prefix without the old prefix's letters has recents that point nowhere.


class PrefixNotReady(RuntimeError):
    """The destination has not been initialised by Wine yet."""


@dataclass
class DriveLetter:
    letter: str           # lower case, no colon: "w"
    target: str           # where it points: "/mnt/work"

    @property
    def label(self) -> str:
        return self.letter.upper() + ":"

    @property
    def available(self) -> bool:
        """False for removable media that is not plugged in right now. The
        mapping is still worth carrying -- it is right again the moment the
        disk is mounted -- but the user should see which ones are absent."""
        return os.path.isdir(self.target)


# Wine's own. C: is the prefix's drive_c and Z: is the host's root; a
# different target for either is not a designation, it is a broken prefix.
_WINE_OWNS = ("c", "z")
_LETTER = re.compile(r"^([a-zA-Z]):$")


def drive_letters(prefix) -> list[DriveLetter]:
    """The user's drive designations in a prefix.

    Only symlinks named with ONE colon. Wine also keeps "d::"-style entries
    that point at raw block devices, for programs that open a drive directly;
    those name hardware on this machine and are not designations anybody
    made. Relative targets are skipped for a similar reason: they point inside
    the prefix they came from."""
    dosdevices = Path(prefix).expanduser() / "dosdevices"
    out = []
    try:
        entries = sorted(dosdevices.iterdir())
    except OSError:
        return out
    for entry in entries:
        match = _LETTER.match(entry.name)
        if not match or match.group(1).lower() in _WINE_OWNS:
            continue
        if not entry.is_symlink():
            continue
        try:
            target = os.readlink(entry)
        except OSError:
            continue
        if not os.path.isabs(target):
            continue
        out.append(DriveLetter(match.group(1).lower(), target))
    return out


def prefix_of(path) -> Path | None:
    """The prefix a Settings folder lives in, found by walking up to the
    directory that holds dosdevices. None for a Settings folder that has been
    copied out of any prefix -- a backup on another disk."""
    for parent in Path(path).expanduser().resolve().parents:
        if (parent / "dosdevices").is_dir() and (parent / "drive_c").is_dir():
            return parent
    return None


def is_initialised(prefix) -> bool:
    """Has Wine created this prefix's drives?

    The test is dosdevices/c:, and it is the only safe one. Wine creates C: and
    Z: ONLY when it creates dosdevices itself -- dlls/ntdll/unix/server.c:

        if (!mkdir( "dosdevices", 0777 ))
        {
            mkdir( "drive_c", 0777 );
            symlink( "../drive_c", "dosdevices/c:" );
            symlink( "/", "dosdevices/z:" );
        }

    so putting a drive letter into a prefix before Wine has run in it leaves a
    prefix with no C: drive at all."""
    return (Path(prefix).expanduser() / "dosdevices" / "c:").is_symlink()


def import_drive_letters(prefix, letters) -> list[str]:
    """Create these drive letters in an initialised prefix. Returns notes.

    Never overwrites. A letter the destination already maps to the same place
    is reported as already there; one it maps somewhere else is left exactly
    as it is and reported, because which of the two the user meant is not
    something this can know."""
    root = Path(prefix).expanduser()
    if not is_initialised(root):
        raise PrefixNotReady(
            f"{root} has not been set up by Wine yet, so it has no C: drive. "
            "Adding a drive letter now would stop Wine ever creating one. Run "
            "Setup first, then import the drive letters.")
    dosdevices = root / "dosdevices"
    notes = []
    for d in letters:
        if d.letter in _WINE_OWNS:
            notes.append(f"{d.label} belongs to Wine; left alone")
            continue
        link = dosdevices / f"{d.letter}:"
        if link.is_symlink() or link.exists():
            try:
                current = os.readlink(link)
            except OSError:
                current = None
            if current == d.target:
                notes.append(f"{d.label} is already {d.target}")
            else:
                notes.append(f"{d.label} is already {current or 'something else'}; "
                             f"left alone rather than pointed at {d.target}")
            continue
        try:
            link.symlink_to(d.target)
            notes.append(f"{d.label} -> {d.target}"
                         + ("" if d.available else "  (not mounted right now)"))
        except OSError as exc:
            notes.append(f"could not create {d.label}: {exc}")
    return notes
