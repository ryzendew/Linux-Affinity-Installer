#!/usr/bin/env python3
"""
Affinity Linux Installer - PyQt6 GUI Version
A modern, professional GUI application for installing Affinity software on Linux
"""

import os
import sys
import subprocess
import webbrowser
import shutil
import tarfile
import zipfile
import threading
import platform
import urllib.request
import urllib.error
import urllib.parse
import re
import json
import hashlib
import tempfile
import queue
from pathlib import Path
import time
import signal
import shlex

# Single source of truth for the winetricks components this installer sets up.
# Order matters: .NET first (the runtimes and Affinity itself check against it),
# then fonts and runtimes, then the rest. Keep in sync with
# _check_winetricks_component().
# No .NET 3.5: Affinity 3 runs on 4.8. Installing 3.5 first took ~3.5 min and
# nearly doubled the 4.8 install after it (4:05 -> 7:30), and its 32-bit setup
# was the first to crash under Wine 11's new WoW64.
WINETRICKS_COMPONENTS = [
    ("dotnet48", ".NET Framework 4.8"),
    ("corefonts", "Windows Core Fonts"),
    ("vcrun2022", "Visual C++ Redistributables 2022"),
    ("msxml3", "MSXML 3.0"),
    ("msxml6", "MSXML 6.0"),
    # NOTE: no "crypt32" entry on purpose. winetricks' crypt32 verb installs
    # Microsoft's native crypt32.dll + a native override, but native crypt32
    # cannot validate chains against Wine's registry certificate stores, so
    # every TLS handshake fails at cert verification (12157 /
    # ERROR_INTERNET_SECURITY_CHANNEL_ERROR). Wine's builtin crypt32 reads
    # the prefix ROOT store correctly. Existing prefixes are migrated by
    # repair_crypt32_override().
    ("tahoma", "Tahoma Font"),
    ("renderer=vulkan", "Vulkan Renderer"),
]

# Side column (Quick Start / Troubleshooting) sizing. The floor keeps a column
# wide enough for its icon plus a few words of label; MIN_WINDOW_WIDTH is the
# budget the floors are trimmed to so the log column and the gaps still fit and
# the window never has to grow past it to avoid clipping (see _size_side_columns).
SIDE_PANEL_MIN_WIDTH = 190
SIDE_PANEL_MIN_FLOOR = 150
MIN_WINDOW_WIDTH = 620


def detect_distro_for_install():
    """Detect distribution for package installation"""
    try:
        with open("/etc/os-release", "r") as f:
            content = f.read()
        for line in content.split("\n"):
            if line.startswith("ID="):
                distro = line.split("=", 1)[1].strip().strip('"').lower()
                if distro == "pika":
                    distro = "pikaos"
                return distro
    except (IOError, FileNotFoundError):
        pass
    return None


def install_package(package_name, import_name=None):
    """Install a Python package if not available"""
    if import_name is None:
        import_name = package_name

    try:
        __import__(import_name)
        return True
    except ImportError:
        print(f"Installing {package_name}...")

        distro = detect_distro_for_install()
        pip_flags = ["--user"]
        if distro in ["arch", "artix", "cachyos", "manjaro", "endeavouros", "xerolinux"]:
            pip_flags.append("--break-system-packages")
        if not sys.stdout.isatty():
            pip_flags.insert(0, "--quiet")

        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", package_name] + pip_flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                __import__(import_name)
                print(f"✓ {package_name} installed successfully")
                return True
            except ImportError:
                print(f"✗ Failed to import {package_name} after installation")
                return False
        except subprocess.CalledProcessError:
            print(f"✗ Failed to install {package_name} via pip")
            return False
        except Exception as e:
            print(f"✗ Error installing {package_name}: {e}")
            return False


PYQT6_AVAILABLE = False
try:
    from PyQt6.QtWidgets import (
        QApplication,
        QMainWindow,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QPushButton,
        QLabel,
        QFileDialog,
        QMessageBox,
        QTextEdit,
        QFrame,
        QProgressBar,
        QGroupBox,
        QScrollArea,
        QDialog,
        QDialogButtonBox,
        QButtonGroup,
        QRadioButton,
        QInputDialog,
        QSlider,
        QLineEdit,
        QSizePolicy,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QEvent
    from PyQt6.QtGui import (
        QFont,
        QFontMetrics,
        QColor,
        QPalette,
        QIcon,
        QPixmap,
        QShortcut,
        QKeySequence,
        QWheelEvent,
        QPainter,
        QPen,
    )

    # Try to import SVG widget (may not be available on all distributions)
    try:
        from PyQt6.QtSvgWidgets import QSvgWidget

        SVG_WIDGET_AVAILABLE = True
    except ImportError:
        print("⚠️  QSvgWidget not available - some icons may not display correctly")
        SVG_WIDGET_AVAILABLE = False

        # Create a dummy QSvgWidget class to prevent import errors
        class QSvgWidget(QWidget):
            def load(self, content):
                pass

            def setFixedSize(self, size):
                super().setFixedSize(size)

    PYQT6_AVAILABLE = True
except ImportError:
    print("PyQt6 not found. Attempting to install...")
    if install_package("PyQt6", "PyQt6"):
        try:
            from PyQt6.QtWidgets import (
                QApplication,
                QMainWindow,
                QWidget,
                QVBoxLayout,
                QHBoxLayout,
                QPushButton,
                QLabel,
                QFileDialog,
                QMessageBox,
                QTextEdit,
                QFrame,
                QProgressBar,
                QGroupBox,
                QScrollArea,
                QDialog,
                QDialogButtonBox,
                QButtonGroup,
                QRadioButton,
                QInputDialog,
                QSlider,
                QLineEdit,
                QSizePolicy,
            )
            from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QEvent
            from PyQt6.QtGui import (
                QFont,
                QFontMetrics,
                QColor,
                QPalette,
                QIcon,
                QPixmap,
                QShortcut,
                QKeySequence,
                QWheelEvent,
                QPainter,
                QPen,
            )

            # Try to import SVG widget after installation
            try:
                from PyQt6.QtSvgWidgets import QSvgWidget

                SVG_WIDGET_AVAILABLE = True
            except ImportError:
                print(
                    "⚠️  QSvgWidget not available after installation - some icons may not display correctly"
                )
                SVG_WIDGET_AVAILABLE = False

                # Create a dummy QSvgWidget class to prevent import errors
                class QSvgWidget(QWidget):
                    def load(self, content):
                        pass

                    def setFixedSize(self, size):
                        super().setFixedSize(size)

            PYQT6_AVAILABLE = True
            print("✓ PyQt6 installed and imported successfully")
        except ImportError as e:
            print(f"✗ Failed to import PyQt6 after installation: {e}")
            PYQT6_AVAILABLE = False
    else:
        print("✗ Failed to install PyQt6 via pip")
        PYQT6_AVAILABLE = False

if not PYQT6_AVAILABLE:
    print("\nERROR: PyQt6 is required but could not be installed.")
    print("Please install PyQt6 manually using one of these methods:\n")
    print("Using pip:")
    print("  pip install --user PyQt6")
    print("\nOr using your distribution's package manager:")
    print("  Arch/Artix/CachyOS/EndeavourOS/XeroLinux: sudo pacman -S python-pyqt6")
    print("  Fedora/Nobara: sudo dnf install python3-pyqt6")
    print("  Debian/Ubuntu/Mint/Pop/Zorin/PikaOS: sudo apt install python3-pyqt6")
    print("  openSUSE: sudo zypper install python313-PyQt6")
    sys.exit(1)


# Overrides that let something else drive this installer.
#
# The installer is otherwise a single-prefix tool: it installs into
# ~/.AffinityLinux, or into the one path remembered in
# ~/.config/AffinityOnLinux/install_location, chosen through a dialog. Anything
# wanting a second prefix -- a manager handling several, a test run that must
# not touch the working install -- has no way to say so.
#
# Environment rather than only argv, because the caller is usually a subprocess
# launcher and because it then survives however the script is invoked (piped
# into python3, run from a checkout, re-execed).
ENV_INSTALL_DIR = "AFFINITY_INSTALL_DIR"
ENV_INSTALLER_FILE = "AFFINITY_INSTALLER_FILE"


# Every other Wine build is several hundred MB, and switching versions
# downloads the one asked for when it is not cached. So a setup caches only the
# build it installs; AFFINITY_CACHE_ALL_WINE=1 also caches all the others in
# <prefix>/Wine-Switch, for switching later without a connection.
ENV_CACHE_ALL_WINE = "AFFINITY_CACHE_ALL_WINE"


def cache_all_wine_versions():
    return os.environ.get(ENV_CACHE_ALL_WINE, "").strip() == "1"


# Affinity installers kept after a successful install, named by the version
# they installed, so a later install -- in any prefix -- can use one instead of
# downloading 650 MB again, or install an older Affinity on purpose.
def kept_installers_dir():
    base = os.environ.get("XDG_CACHE_HOME", "").strip() or os.path.join(Path.home(), ".cache")
    return Path(base) / "AffinityOnLinux" / "installers"


def pe_file_version(path):
    """The FileVersion string in a PE's version resource, or None."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    key = "FileVersion".encode("utf-16-le") + b"\0\0"
    i = data.rfind(key)
    if i < 0:
        return None
    i += len(key)
    i += (-i) % 4                     # values are 32-bit aligned
    end = data.find(b"\0\0", i)
    while end > 0 and (end - i) % 2:
        end = data.find(b"\0\0", end + 1)
    text = data[i:end].decode("utf-16-le", errors="replace").strip() if end > i else ""
    match = re.match(r"\d+(?:\.\d+){1,3}", text)
    return match.group(0) if match else None


def kept_installers():
    """[(version, path, downloaded)] newest version first; downloaded is the
    file's date, which is kept from the download."""
    out = []
    d = kept_installers_dir()
    try:
        for f in d.glob("Affinity-x64-*.exe"):
            version = f.stem[len("Affinity-x64-"):]
            if re.fullmatch(r"\d+(?:\.\d+){1,3}", version):
                out.append((version, f, f.stat().st_mtime))
    except OSError:
        return []
    out.sort(key=lambda x: tuple(int(n) for n in x[0].split(".")), reverse=True)
    return out


# The system wine package is not what runs Affinity -- each prefix has its own
# Wine build -- but that build links against system libraries (GnuTLS,
# FreeType, fontconfig, the Vulkan loader, X11/Wayland, audio, CUPS), and the
# distro's wine package is what pulls them all in.
DEP_LABELS = {
    "wine": "wine (system package: supplies the libraries the prefix's own Wine needs; "
            "system Wine itself is not used to run Affinity)",
}


# OpenCL needs a driver on the host -- Wine's opencl.dll is only a bridge to
# the system's OpenCL loader, which finds drivers through /etc/OpenCL/vendors.
# Without one Affinity logs "[OpenCL] Not available" and renders without it.
# The package that provides the driver, per GPU vendor and distro family.
GPU_VENDORS = {"0x8086": "intel", "0x1002": "amd", "0x10de": "nvidia"}
OPENCL_PACKAGES = {
    "arch":   {"intel": "intel-compute-runtime", "amd": "rocm-opencl-runtime (or opencl-mesa)",
               "nvidia": "opencl-nvidia"},
    "debian": {"intel": "intel-opencl-icd", "amd": "mesa-opencl-icd (or ROCm's OpenCL)",
               "nvidia": "the nvidia-opencl-icd package matching your NVIDIA driver"},
    "fedora": {"intel": "intel-compute-runtime", "amd": "mesa-libOpenCL (or rocm-opencl)",
               "nvidia": "xorg-x11-drv-nvidia-cuda (RPM Fusion)"},
    "suse":   {"intel": "intel-opencl", "amd": "Mesa-libOpenCL",
               "nvidia": "nvidia-compute-G06"},
}


def gpu_vendors(drm="/sys/class/drm"):
    """GPU vendors present ("intel", "amd", "nvidia"), from the DRM devices."""
    found = []
    try:
        for card in sorted(os.listdir(drm)):
            if not re.fullmatch(r"card\d+", card):
                continue
            try:
                vendor = open(os.path.join(drm, card, "device", "vendor")).read().strip().lower()
            except OSError:
                continue
            name = GPU_VENDORS.get(vendor)
            if name and name not in found:
                found.append(name)
    except OSError:
        pass
    return found


def opencl_drivers(vendors_dir="/etc/OpenCL/vendors"):
    """OpenCL drivers the loader can find: .icd files whose library exists
    (an absolute path that is there, or a bare name left to the linker)."""
    drivers = []
    try:
        for icd in sorted(Path(vendors_dir).glob("*.icd")):
            lib = icd.read_text(errors="replace").strip()
            if lib and (not lib.startswith("/") or Path(lib).exists()):
                drivers.append(icd.stem)
    except OSError:
        pass
    return drivers


# Serialises ensure_patcher_files across the installers in one process.
_PATCHER_FILES_LOCK = threading.Lock()


def _sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 256), b""):
            digest.update(block)
    return digest.hexdigest()


# Where this installer's own files are fetched from when there is no checkout
# beside it (the piped install). The public home by default; the manager's
# run.py passes on whichever repository and branch it was started from, so a
# staging run fetches from staging and never mixes in files from main.
# POC SOURCE -- repoint at upstream if this work is merged there.
SOURCE_REPO = "https://github.com/jfacemyer/Linux-Affinity-Manager"
SOURCE_BRANCH = "main"


# The fork's release downloads -- the Wine builds and the plugin loader above --
# come from GitHub. AFFINITY_RELEASES_FROM=https://<host>/<owner> fetches the
# same files from a Forgejo or Gitea copy of those repositories instead, so a
# release can be tested end to end before it is published on GitHub. The pins
# do not change: only byte-identical builds install from either host.
ENV_RELEASES_FROM = "AFFINITY_RELEASES_FROM"
RELEASES_HOME = "https://github.com/jfacemyer"


def releases_from():
    return os.environ.get(ENV_RELEASES_FROM, "").strip().rstrip("/")


def release_download_url(url):
    """A fork release download, from the host AFFINITY_RELEASES_FROM names if set."""
    alt = releases_from()
    if alt and url.startswith(RELEASES_HOME + "/"):
        return alt + url[len(RELEASES_HOME):]
    return url


def apl_release_api_url():
    """The plugin loader release's metadata: GitHub's API, or the Forgejo/Gitea
    one on the host AFFINITY_RELEASES_FROM names."""
    alt = releases_from()
    name = APL_RELEASE_REPO.split("/", 1)[1]
    if alt:
        host, owner = alt.rsplit("/", 1)
        return f"{host}/api/v1/repos/{owner}/{name}/releases/tags/{APL_RELEASE_TAG}"
    return f"https://api.github.com/repos/{APL_RELEASE_REPO}/releases/tags/{APL_RELEASE_TAG}"


def source_repo():
    return os.environ.get("AFFINITY_MANAGER_REPO", "").strip().rstrip("/") or SOURCE_REPO


def source_branch():
    return os.environ.get("AFFINITY_MANAGER_BRANCH", "").strip() or SOURCE_BRANCH


def source_raw_url(path):
    """A file on the source branch, spelled the way the host wants: GitHub
    serves <repo>/raw/<branch>/<path>, Forgejo and Gitea
    <repo>/raw/branch/<branch>/<path>."""
    repo, branch = source_repo(), source_branch()
    if repo.startswith("https://github.com/"):
        return f"{repo}/raw/{branch}/{path}"
    return f"{repo}/raw/branch/{branch}/{path}"


# The handler this installer is meant to install, by content. The piped install
# fetches it over the network from a branch that can be older than this file,
# and "it starts with MZ and is over 4KB" does not tell those apart.
HANDLER_SHA256 = "5bd31facbe433a884afab9dd6861d5094726055f3c1706a4d001a800e30ed97a"

# The same patch set on Wine 11.18, pinned for the same reason. Released on the
# fork that carries the patches' upstream pull request.
WINE_11_18_SHA256 = "c325bf804407abcf8070d02066b5be00680b0339e796a6583b4a1d2dae934853"

# Wine 11.19 with the full Affinity patch set, the default, pinned by content:
# the 11.16 release once went three weeks without eight fixes the local builds
# had, and nothing noticed. A tarball that is not this one is refused rather
# than installed. Rebuild, republish under a new tag, and update the URL and
# this hash together.
WINE_11_19_SHA256 = "637a0ec5ed8f225dd96c30796f9227f6f5a68ccc8e394a549391be7a6e9a626e"

# The plugin loader. Upstream's latest release (v0.3.0, April) predates Canva
# sign-in, the command-line open fix and the runtime Direct2D patches, all of
# which sit unreleased on its dev branch. This build is that dev branch plus
# fixes -- libplugins.dll kept loaded (random crashes), launch arguments quoted
# (paths with spaces), the color picker under Wine, the empty Leading dropdown in
# the text context toolbar (Affinity 3.3), the sub-tool panel's columns after
# a studio switch -- released on a fork until
# upstream publishes one. Each asset is pinned, like the Wine build.
# POC SOURCE -- repoint at an upstream release that carries these.
APL_RELEASE_REPO = "jfacemyer/AffinityPluginLoader"
APL_RELEASE_TAG = "wine-fixes-4"
APL_ASSET_SHA256 = {
    "affinitypluginloader-v0.3.0.zip": "5f254cda839a589ff8f17347c693bd4296e8e06079dc76a7d64f6a3b1ba1ca4a",
    "winefix-v0.3.0.zip": "40297d01f5b15f39dea9872563293989058285a8ac9aa6eca2e0f2a65f960d02",
}


def script_dir():
    """The checkout directory this file was run from, or None if there is none.

    The documented install is `curl ... | python3`, and there __file__ is not a
    path. Python sets it to the literal string "<stdin>", so both spellings
    used here before were wrong:

      Path(__file__).parent          ->  Path(".")  -- the CURRENT DIRECTORY
      Path(__file__).resolve().parent.parent  ->  the parent of it

    which means the fast paths looked for icons, MIME definitions and
    affinity-on-linux.exe in whatever directory the user happened to be
    standing in when they ran the pipe. An `icons/` folder there was picked up
    as if it were this project's; an `AffinityHandler/affinity-on-linux.exe`
    there was copied into the prefix and run. The `except NameError` guards
    written to cover the piped case never fired, because there is no NameError
    to catch.

    So the test is not "is __file__ defined" but "is it a file". And being a
    file is not enough either: the documented alternative to the pipe is
    `curl ... -o install.py && python3 install.py`, which people run from
    ~/Downloads -- and then checkout_root() would be the home directory, so
    ~/AffinityHandler/affinity-on-linux.exe and ~/mime would be treated as this
    project's. The directory therefore has to BE this project's AffinityScripts
    directory, by name. Anything else downloads, which is what the piped
    install has always actually been doing."""
    try:
        here = __file__
    except NameError:                       # older Pythons leave it unset
        return None
    if not here or here.startswith("<"):    # "<stdin>", "<string>"
        return None
    try:
        resolved = Path(here).resolve()
    except (OSError, ValueError):
        return None
    if not resolved.is_file():
        return None
    return resolved.parent if resolved.parent.name == "AffinityScripts" else None


def checkout_root():
    """The repository this file sits in, or None. This file lives in
    <root>/AffinityScripts, so the root is one level up."""
    where = script_dir()
    return where.parent if where else None


def override_install_dir():
    """Prefix directory to install into, or None.

    Used verbatim -- no .AffinityLinux suffix is appended, unlike the custom
    location dialog. The caller names the directory; that is the point."""
    value = os.environ.get(ENV_INSTALL_DIR, "").strip()
    return str(Path(value).expanduser()) if value else None


def override_installer_file():
    """An Affinity installer .exe to install from instead of downloading, or None.

    downloads.affinity.studio serves whatever the current release is, with no
    versioned URL, so pinning a version means keeping its installer and pointing
    at it. Returns None if the path does not exist, so a stale value degrades
    into the normal download rather than failing the install."""
    value = os.environ.get(ENV_INSTALLER_FILE, "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    return str(path) if path.is_file() else None


# ── Font registrations ─────────────────────────────────────────────────────────
#
# Found 2026-10-01, after a fresh prefix drew Affinity's bold UI text in Arial
# Narrow and Microsoft Yahei. The core fonts winetricks installs (Tahoma Bold,
# Arial, Verdana...) were on disk in windows\Fonts, but their registrations had
# gone from the 64-bit Fonts keys -- the ones a 64-bit Affinity reads. winetricks
# wrote them correctly; a later Wine startup's font re-sync dropped them, and the
# exact trigger was not reproduced. And Microsoft Yahei was registered from
# *another* Wine's font folder -- wine-tkg's, or the distro Wine's in
# /usr/share/wine -- because winetricks runs under wine-tkg, which looks for
# Wine's own fonts there.
#
# So rather than chase every way registrations can drift, the result is checked
# at the end of an install (and on request from the manager) and put right:
#   - every font file in the prefix's windows\Fonts is registered;
#   - registrations pointing into some other Wine's share/wine/fonts are removed.
# Host fonts (/usr/share/fonts, ~/.fonts) are Wine's normal integration and are
# left alone. Nothing points outside the prefix that did not already.

FONT_KEYS_64 = (
    r"HKLM\Software\Microsoft\Windows NT\CurrentVersion\Fonts",
    r"HKLM\Software\Microsoft\Windows\CurrentVersion\Fonts",
)
EXTERNAL_FONTS_KEY = r"HKCU\Software\Wine\Fonts\External Fonts"
FONT_FILE_SUFFIXES = (".ttf", ".otf")


def font_full_name(path):
    """The full name (name ID 4) from a TrueType/OpenType file, or None.

    That is the name Windows registers a font under -- "Tahoma Bold",
    "Arial Bold Italic" -- with " (TrueType)" after it."""
    import struct
    try:
        data = Path(path).read_bytes()
        count = struct.unpack_from(">H", data, 4)[0]
        table = None
        for i in range(count):
            tag, _, offset, _ = struct.unpack_from(">4sIII", data, 12 + 16 * i)
            if tag == b"name":
                table = offset
                break
        if table is None:
            return None
        _, n, strings = struct.unpack_from(">HHH", data, table)
        found = {}
        for i in range(n):
            platform_id, encoding, language, name_id, length, offset = \
                struct.unpack_from(">HHHHHH", data, table + 6 + 12 * i)
            if name_id != 4:
                continue
            raw = data[table + strings + offset: table + strings + offset + length]
            if platform_id == 3 and language == 0x409:
                found.setdefault(0, raw.decode("utf-16-be", "replace"))
            elif platform_id == 3:
                found.setdefault(1, raw.decode("utf-16-be", "replace"))
            elif platform_id == 1:
                found.setdefault(2, raw.decode("mac_roman", "replace"))
        name = found.get(0) or found.get(1) or found.get(2)
        return name.strip() if name else None
    except (OSError, struct.error, UnicodeError):
        return None


def parse_reg_query(text):
    """{value name: data} for the REG_SZ values in `wine reg query` output."""
    values = {}
    for line in text.splitlines():
        name, sep, data = line.strip("\r\n").partition("    REG_SZ    ")
        if sep:
            values[name.strip()] = data.strip()
    return values


def _foreign_wine_font(data, own_wine_dir):
    """Does this registration point into a Wine font folder other than the
    prefix's own Wine's? Those are left by running a different Wine on the
    prefix, and are not fonts anyone installed."""
    unix = data
    if len(unix) > 2 and unix[1] == ":" and unix[0] in "Zz":
        unix = unix[2:].replace("\\", "/")
    else:
        return False
    if "/share/wine/fonts/" not in unix:
        return False
    if own_wine_dir:
        own = str(Path(own_wine_dir).resolve()).rstrip("/") + "/"
        try:
            if str(Path(unix).resolve()).startswith(own):
                return False
        except OSError:
            pass
    return True


def plan_font_registry_repair(fonts_dir, registered, external, own_wine_dir):
    """What to add and remove. Touches nothing.

    `registered` is {key: {name: data}} for FONT_KEYS_64, `external` the
    External Fonts values. Returns (add {name: file}, remove {key: [names]}).
    A font file already registered under any name is left as it is: the name
    is only made up when there is no registration at all."""
    add = {}
    remove = {}
    nt_key = FONT_KEYS_64[0]
    by_file = {}
    for key in FONT_KEYS_64:
        for name, data in registered.get(key, {}).items():
            by_file.setdefault(data.rsplit("\\", 1)[-1].lower(), set()).add((key, name))
    try:
        files = sorted(p for p in Path(fonts_dir).iterdir()
                       if p.suffix.lower() in FONT_FILE_SUFFIXES and p.is_file())
    except OSError:
        files = []
    for f in files:
        keys_with_it = {k for k, _ in by_file.get(f.name.lower(), set())}
        if all(k in keys_with_it for k in FONT_KEYS_64):
            continue
        names = {n for _, n in by_file.get(f.name.lower(), set())}
        if names:
            name = sorted(names)[0]
        else:
            full = font_full_name(f)
            if not full:
                continue
            name = f"{full} (TrueType)"
        add[name] = f.name
    for key in FONT_KEYS_64:
        for name, data in registered.get(key, {}).items():
            if _foreign_wine_font(data, own_wine_dir):
                remove.setdefault(key, []).append(name)
    for name, data in external.items():
        if _foreign_wine_font(data, own_wine_dir):
            remove.setdefault(EXTERNAL_FONTS_KEY, []).append(name)
    return add, remove


def font_registry_patch(add, remove):
    """The .reg text that applies a plan: additions to both 64-bit keys,
    removals where they were found."""
    def esc(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')

    def full(key):
        return key.replace("HKLM\\", "HKEY_LOCAL_MACHINE\\").replace(
            "HKCU\\", "HKEY_CURRENT_USER\\")

    lines = ["Windows Registry Editor Version 5.00", ""]
    for key in FONT_KEYS_64 + (EXTERNAL_FONTS_KEY,):
        body = []
        if key in FONT_KEYS_64:
            body += [f'"{esc(n)}"="{esc(f)}"' for n, f in sorted(add.items())]
        body += [f'"{esc(n)}"=-' for n in sorted(remove.get(key, []))]
        if body:
            lines += [f"[{full(key)}]"] + body + [""]
    return "\r\n".join(lines) + "\r\n"


# The font verbs installed without winetricks: the same files, checksums and
# registrations as winetricks' corefonts and tahoma, in one pass. winetricks
# waits for Wine to shut down after each font family and starts it again for
# every registry value (two regedit runs per name), about 90 s for corefonts
# and 15 s for tahoma; here it is two regedit runs in all.
# {verb: (winetricks.log lines, [(cache subdir, file, url, sha256, glob,
#         [(file in Fonts, registered name)])])}
_COREFONTS_URL = "https://github.com/pushcx/corefonts/raw/master/"
DIRECT_FONT_VERBS = {
    "corefonts": (
        ["andale", "arial", "comicsans", "courier", "georgia", "impact", "times",
         "trebuchet", "verdana", "webdings", "corefonts"],
        [
            ("corefonts", "andale32.exe", _COREFONTS_URL + "andale32.exe",
             "0524fe42951adc3a7eb870e32f0920313c71f170c859b5f770d82b4ee111e970",
             "AndaleMo.TTF", [("andalemo.ttf", "Andale Mono")]),
            ("corefonts", "arial32.exe", _COREFONTS_URL + "arial32.exe",
             "85297a4d146e9c87ac6f74822734bdee5f4b2a722d7eaa584b7f2cbf76f478f6",
             "Arial*.TTF", [("arialbd.ttf", "Arial Bold"), ("arialbi.ttf", "Arial Bold Italic"),
                            ("ariali.ttf", "Arial Italic"), ("arial.ttf", "Arial")]),
            ("corefonts", "arialb32.exe", _COREFONTS_URL + "arialb32.exe",
             "a425f0ffb6a1a5ede5b979ed6177f4f4f4fdef6ae7c302a7b7720ef332fec0a8",
             "AriBlk.TTF", [("ariblk.ttf", "Arial Black")]),
            ("corefonts", "comic32.exe", _COREFONTS_URL + "comic32.exe",
             "9c6df3feefde26d4e41d4a4fe5db2a89f9123a772594d7f59afd062625cd204e",
             "Comic*.TTF", [("comicbd.ttf", "Comic Sans MS Bold"), ("comic.ttf", "Comic Sans MS")]),
            ("corefonts", "courie32.exe", _COREFONTS_URL + "courie32.exe",
             "bb511d861655dde879ae552eb86b134d6fae67cb58502e6ff73ec5d9151f3384",
             "cour*.ttf", [("courbd.ttf", "Courier New Bold"), ("courbi.ttf", "Courier New Bold Italic"),
                           ("couri.ttf", "Courier New Italic"), ("cour.ttf", "Courier New")]),
            ("corefonts", "georgi32.exe", _COREFONTS_URL + "georgi32.exe",
             "2c2c7dcda6606ea5cf08918fb7cd3f3359e9e84338dc690013f20cd42e930301",
             "Georgia*.TTF", [("georgiab.ttf", "Georgia Bold"), ("georgiai.ttf", "Georgia Italic"),
                              ("georgia.ttf", "Georgia"), ("georgiaz.ttf", "Georgia Bold Italic")]),
            ("corefonts", "impact32.exe", _COREFONTS_URL + "impact32.exe",
             "6061ef3b7401d9642f5dfdb5f2b376aa14663f6275e60a51207ad4facf2fccfb",
             "Impact.TTF", [("impact.ttf", "Impact")]),
            ("corefonts", "times32.exe", _COREFONTS_URL + "times32.exe",
             "db56595ec6ef5d3de5c24994f001f03b2a13e37cee27bc25c58f6f43e8f807ab",
             "Times*.TTF", [("timesbd.ttf", "Times New Roman Bold"),
                            ("timesbi.ttf", "Times New Roman Bold Italic"),
                            ("timesi.ttf", "Times New Roman Italic"), ("times.ttf", "Times New Roman")]),
            ("corefonts", "trebuc32.exe", _COREFONTS_URL + "trebuc32.exe",
             "5a690d9bb8510be1b8b4fe49f1f2319651fe51bbe54775ddddd8ef0bd07fdac9",
             "trebuc*.ttf", [("trebucbd.ttf", "Trebuchet MS Bold"), ("trebucbi.ttf", "Trebuchet MS Bold Italic"),
                             ("trebucit.ttf", "Trebuchet MS Italic"), ("trebuc.ttf", "Trebuchet MS")]),
            ("corefonts", "verdan32.exe", _COREFONTS_URL + "verdan32.exe",
             "c1cb61255e363166794e47664e2f21af8e3a26cb6346eb8d2ae2fa85dd5aad96",
             "Verdana*.TTF", [("verdanab.ttf", "Verdana Bold"), ("verdanai.ttf", "Verdana Italic"),
                              ("verdana.ttf", "Verdana"), ("verdanaz.ttf", "Verdana Bold Italic")]),
            ("corefonts", "webdin32.exe", _COREFONTS_URL + "webdin32.exe",
             "64595b5abc1080fba8610c5c34fab5863408e806aafe84653ca8575bed17d75a",
             "Webdings.TTF", [("webdings.ttf", "Webdings")]),
        ],
    ),
    "tahoma": (
        ["tahoma"],
        [
            ("tahoma", "IELPKTH.CAB", "https://downloads.sourceforge.net/corefonts/OldFiles/IELPKTH.CAB",
             "c1be3fb8f0042570be76ec6daa03a99142c88367c1bc810240b85827c715961a",
             "*.TTF", [("tahoma.ttf", "Tahoma"), ("tahomabd.ttf", "Tahoma Bold")]),
        ],
    ),
}


def winetricks_cache_dir():
    """Where winetricks keeps its downloads, so both share one copy."""
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "winetricks"


def prefix_temp_dir(prefix):
    """The prefix's C:\\windows\\temp as a host path, created if missing.

    Wine names the folder "temp". Host file names are case-sensitive and
    Wine's are not, so a second "Temp" beside it is what Wine opens for
    C:\\windows\\Temp, while winetricks writes its .reg files into "temp".
    The direct font install once created that "Temp", and every winetricks
    registry change after it failed with "file not found": vcrun2022's and
    msxml's DLL overrides and renderer=vulkan were never set, and Affinity
    crashed on Wine's own C++ runtime. A stray copy in another case is folded
    back into "temp" and removed."""
    windows = Path(prefix) / "drive_c" / "windows"
    temp = windows / "temp"
    temp.mkdir(parents=True, exist_ok=True)
    for other in list(windows.iterdir()):
        if other.name.lower() != "temp" or other.name == "temp" or not other.is_dir():
            continue
        for item in list(other.iterdir()):
            if not (temp / item.name).exists():
                shutil.move(str(item), str(temp / item.name))
        shutil.rmtree(other, ignore_errors=True)
    return temp


def install_font_verb(prefix, wine, verb, fetch, log=None, cabextract=None, env=None):
    """Install one of DIRECT_FONT_VERBS into the prefix without winetricks.

    `fetch(url, path)` downloads a missing file. Returns True when the fonts
    are copied, registered in both registry views and logged in
    winetricks.log; False (having changed nothing in the registry) otherwise,
    so the caller can fall back to winetricks. Never raises."""
    import fnmatch
    log = log or (lambda message, level="info": None)
    prefix, wine = Path(prefix), Path(wine)
    log_lines, packages = DIRECT_FONT_VERBS[verb]
    cabextract = cabextract or shutil.which("cabextract")
    if not cabextract:
        log("cabextract not found; installing the fonts through winetricks", "info")
        return False
    fonts_dir = prefix / "drive_c" / "windows" / "Fonts"
    try:
        fonts_dir.mkdir(parents=True, exist_ok=True)
        temp_root = prefix_temp_dir(prefix)
        registrations = {}
        with tempfile.TemporaryDirectory(dir=temp_root) as work:
            for subdir, name, url, sha256, pattern, fonts in packages:
                cached = winetricks_cache_dir() / subdir / name
                if not cached.is_file() or hashlib.sha256(cached.read_bytes()).hexdigest() != sha256:
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    if not fetch(url, str(cached)) or not cached.is_file():
                        log(f"Could not download {name}", "warning")
                        return False
                    if hashlib.sha256(cached.read_bytes()).hexdigest() != sha256:
                        log(f"{name} does not match its checksum", "warning")
                        cached.unlink(missing_ok=True)
                        return False
                out = Path(work) / name
                out.mkdir()
                result = subprocess.run([cabextract, "-q", "-d", str(out), str(cached)],
                                        capture_output=True, timeout=120)
                if result.returncode != 0:
                    log(f"cabextract failed on {name}", "warning")
                    return False
                for src in out.iterdir():
                    if not (src.is_file() and fnmatch.fnmatch(src.name.lower(), pattern.lower())):
                        continue
                    dest_name = src.name.lower()
                    for old in fonts_dir.iterdir():
                        if old.name.lower() == dest_name and old.name != dest_name:
                            old.unlink()
                    shutil.copyfile(src, fonts_dir / dest_name)
                for file_name, font_name in fonts:
                    if not (fonts_dir / file_name).is_file():
                        log(f"{file_name} was not in {name}", "warning")
                        return False
                    registrations[f"{font_name} (TrueType)"] = file_name

        # The keys winetricks fills by running regedit in both views: Wine
        # shares the Windows NT key between them and keeps a 32-bit copy of
        # the other under Wow6432Node. One 64-bit regedit run writes all three.
        def esc(text):
            return text.replace("\\", "\\\\").replace('"', '\\"')
        lines = ["Windows Registry Editor Version 5.00", ""]
        for key in FONT_KEYS_64 + (r"HKLM\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Fonts",):
            lines.append("[" + key.replace("HKLM\\", "HKEY_LOCAL_MACHINE\\") + "]")
            lines += [f'"{esc(n)}"="{esc(f)}"' for n, f in sorted(registrations.items())]
            lines.append("")
        patch = temp_root / f"font-{verb}.reg"
        patch.write_text("\r\n".join(lines) + "\r\n", encoding="utf-16")
        env = dict(env) if env else os.environ.copy()
        env["WINEPREFIX"] = str(prefix)
        env["WINEDEBUG"] = "-all"
        try:
            result = subprocess.run([str(wine), "regedit", "/S", f"C:\\windows\\temp\\{patch.name}"],
                                    env=env, capture_output=True, timeout=180)
            if result.returncode != 0:
                log(f"Could not register the fonts (regedit exit {result.returncode})", "warning")
                return False
        finally:
            patch.unlink(missing_ok=True)

        # So winetricks, and anything reading its log, sees them installed.
        with open(prefix / "winetricks.log", "a", encoding="utf-8") as handle:
            for line in log_lines:
                handle.write(line + "\n")
        if verb == "corefonts":
            (fonts_dir / "corefonts.installed").touch()
        log(f"Installed {len(registrations)} {verb} fonts directly", "success")
        return True
    except Exception as e:                    # noqa: BLE001 -- see docstring
        log(f"Could not install {verb} directly: {e}", "warning")
        return False


def repair_font_registrations(prefix, wine, log=None):
    """Check the prefix's font registrations and put them right, through the
    prefix's own Wine. Returns one line per change; empty when nothing was
    needed. Never raises: a font check must not fail an install."""
    log = log or (lambda message, level="info": None)
    prefix = Path(prefix)
    wine = Path(wine)
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    env["WINEDEBUG"] = "-all"
    try:
        def query(key):
            out = subprocess.run([str(wine), "reg", "query", key, "/reg:64"],
                                 env=env, capture_output=True, text=True,
                                 errors="replace", timeout=120)
            return parse_reg_query(out.stdout)

        registered = {key: query(key) for key in FONT_KEYS_64}
        external = query(EXTERNAL_FONTS_KEY)
        own = wine.resolve().parent.parent
        add, remove = plan_font_registry_repair(
            prefix / "drive_c" / "windows" / "Fonts", registered, external, own)
        if not add and not any(remove.values()):
            return []
        patch = prefix_temp_dir(prefix) / "font-registrations.reg"
        patch.write_text(font_registry_patch(add, remove), encoding="utf-16")
        result = subprocess.run(
            [str(wine), "regedit", "/S", r"C:\windows\temp\font-registrations.reg"],
            env=env, capture_output=True, timeout=120)
        try:
            patch.unlink()
        except OSError:
            pass
        if result.returncode != 0:
            log(f"Could not update font registrations (regedit exit {result.returncode})",
                "warning")
            return []
        notes = [f"registered {n} ({f})" for n, f in sorted(add.items())]
        notes += [f"removed {n} -- it pointed into another Wine's font folder"
                  for n in sorted({n for names in remove.values() for n in names})]
        return notes
    except Exception as e:                    # noqa: BLE001 -- see docstring
        log(f"Could not check font registrations: {e}", "warning")
        return []



class ElidedLabel(QLabel):
    """QLabel that shrinks with its panel instead of forcing its text width.

    The side columns sit next to the log pane, so on a narrow window there is
    less room than the labels ask for. A normal QLabel demands its full text
    width as a minimum, which pushes the column wider than its scroll area and
    gets the text clipped mid-word. Reporting a zero-width minimum lets the
    layout shrink us, and we show an ellipsis for whatever room is left.
    """

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self._full_hint = super().sizeHint()

    def text(self):
        """The complete label - layout code gets the elided one, callers don't."""
        return getattr(self, "_full_text", "")

    def setText(self, text):
        self._full_text = text
        super().setText(text)
        self._refresh_hint()
        self._apply_elision()

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        return QSize(0, hint.height())

    def sizeHint(self):
        # The preferred width still covers the whole label, so wide windows lay
        # out exactly as they did before; only the minimum collapses to zero.
        return getattr(self, "_full_hint", super().sizeHint())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elision()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._refresh_hint()
            self._apply_elision()

    def _refresh_hint(self):
        """Re-measure the whole label with the font/style currently in effect."""
        full = getattr(self, "_full_text", None)
        if full is None:
            return
        current = super().text()
        super().setText(full)
        try:
            self._full_hint = super().sizeHint()
        finally:
            super().setText(current)

    def _apply_elision(self):
        full = getattr(self, "_full_text", "")
        if not full or self.width() <= 0:
            return
        shown = QFontMetrics(self.font()).elidedText(
            full, Qt.TextElideMode.ElideRight, max(0, self.width() - 4)
        )
        if shown != super().text():
            super().setText(shown)


class ElidedActionButton(QPushButton):
    """QPushButton that shrinks with its panel and ellipsizes its label.

    Qt never elides button text on its own - it clips it - and the full text
    width becomes the panel's minimum, which is what used to cut these buttons
    off when the window was resized narrow. Same contract as ElidedLabel: the
    minimum collapses, the preferred width keeps describing the whole label,
    and text() keeps returning the unabbreviated label for callers that logic on.
    """

    # 12px + 24px of padding and a 1px border per side, from every #actionButton
    # rule in the stylesheets, plus a little slack for font/padding rounding.
    _TEXT_CHROME = 58

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._full_text = text
        self._full_hint = super().sizeHint()

    def text(self):
        """The complete label - layout code gets the elided one, callers don't."""
        return getattr(self, "_full_text", "")

    def setText(self, text):
        previous = getattr(self, "_full_text", None)
        self._full_text = text
        super().setText(text)
        self._refresh_hint()
        if previous is not None and self.toolTip() == previous:
            # The tooltip was mirroring the label (set because the label can be
            # abbreviated); keep it accurate when the label itself changes.
            self.setToolTip(text)
        self._apply_elision()

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        return QSize(0, hint.height())

    def sizeHint(self):
        return getattr(self, "_full_hint", super().sizeHint())

    def setIcon(self, icon):
        super().setIcon(icon)
        self._apply_elision()

    def setIconSize(self, size):
        super().setIconSize(size)
        self._apply_elision()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elision()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._refresh_hint()
            self._apply_elision()

    def _refresh_hint(self):
        """Re-measure the whole label with the font/style currently in effect."""
        full = getattr(self, "_full_text", None)
        if full is None:
            return
        current = super().text()
        super().setText(full)
        try:
            self._full_hint = super().sizeHint()
        finally:
            super().setText(current)

    def _apply_elision(self):
        full = getattr(self, "_full_text", "")
        if not full or self.width() <= 0:
            return
        icon_width = 0
        if not self.icon().isNull():
            icon_width = self.iconSize().width() + 8  # icon plus the gap to the text
        shown = QFontMetrics(self.font()).elidedText(
            full,
            Qt.TextElideMode.ElideRight,
            max(0, self.width() - icon_width - self._TEXT_CHROME),
        )
        if shown != super().text():
            super().setText(shown)


class ZoomableTextEdit(QTextEdit):
    """QTextEdit with Ctrl+Wheel zoom support"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zoom_in_callback = None
        self.zoom_out_callback = None

    def set_zoom_callbacks(self, zoom_in, zoom_out):
        """Set callbacks for zoom in/out"""
        self.zoom_in_callback = zoom_in
        self.zoom_out_callback = zoom_out

    def wheelEvent(self, event):
        """Handle mouse wheel events for zoom (Ctrl+Wheel) or scroll"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoomIn(1)
                if self.zoom_in_callback:
                    self.zoom_in_callback()
            elif delta < 0:
                self.zoomOut(1)
                if self.zoom_out_callback:
                    self.zoom_out_callback()
        else:
            super().wheelEvent(event)


class ProgressSpinner(QWidget):
    """A simple rotating spinner widget (indeterminate progress)."""

    def __init__(self, size=22, line_width=3, color=QColor("#8ff361"), parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._on_timeout)
        self._size = size
        self._line_width = line_width
        self._color = color
        self.setFixedSize(self._size, self._size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def start(self):
        self._timer.start()
        self.update()

    def stop(self):
        self._timer.stop()
        self.update()

    def _on_timeout(self):
        self._angle = (self._angle - 30) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(
            self._line_width, self._line_width, -self._line_width, -self._line_width
        )
        pen = QPen(self._color)
        pen.setWidth(self._line_width)
        painter.setPen(pen)
        start_angle = int(self._angle * 16)
        span_angle = int(270 * 16)
        painter.drawArc(rect, start_angle, span_angle)
        painter.end()


class AffinityInstallerGUI(QMainWindow):
    AFFINITY_URL_HANDLER = "affinity-url-handler.desktop"
    # .NET Framework WinRT facades copied from the .NET 4.8 offline installer (SHA-256).
    WINRT_FACADES = {
        "System.Runtime.WindowsRuntime": "1e1e6b4ac4e758fe1066e315f7928c393e1216dbe55c318803dd107123e1a8e3",
        "System.Runtime.WindowsRuntime.UI.Xaml": "8e035a8667213e5a87b69757251a00c7c5f72c5b1b8f7578ec20688629b189e1",
    }

    log_signal = pyqtSignal(str, str)
    progress_signal = pyqtSignal(float)
    progress_text_signal = pyqtSignal(str)
    operation_clock_signal = pyqtSignal(bool)
    show_message_signal = pyqtSignal(str, str, str)
    sudo_password_dialog_signal = pyqtSignal()
    interactive_prompt_signal = pyqtSignal(str, str)
    question_dialog_signal = pyqtSignal(str, str, list)
    nvidia_dxvk_vkd3d_choice_signal = pyqtSignal()
    prompt_affinity_install_signal = pyqtSignal()
    install_application_signal = pyqtSignal(str)
    show_spinner_signal = pyqtSignal(object)
    hide_spinner_signal = pyqtSignal(object)
    gpu_selection_signal = pyqtSignal()
    icons_updated_signal = pyqtSignal()
    refresh_status_signal = pyqtSignal()
    show_main_menu_signal = pyqtSignal()
    window_icon_signal = pyqtSignal(str)
    apply_auto_dpi_signal = pyqtSignal()
    cancel_button_signal = pyqtSignal(bool)

    def __init__(self):
        startup_start = time.time()
        timing_log = []

        def log_timing(step_name, start_time):
            elapsed = time.time() - start_time
            timing_log.append((step_name, elapsed))
            return time.time()

        step_start = time.time()
        super().__init__()
        step_start = log_timing("QMainWindow.__init__", step_start)

        # Title set again at the end of __init__, once self.directory is known.
        self.setWindowTitle("Affinity Linux Installer")
        screen = self.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        min_width = max(640, int(screen_width * 0.5))
        min_height = max(480, int(screen_height * 0.5))
        self.setMinimumSize(min_width, min_height)

        default_width = min(1200, int(screen_width * 0.8))
        default_height = min(1050, int(screen_height * 0.9))
        self.resize(default_width, default_height)
        step_start = log_timing("Window setup", step_start)

        self.distro = None
        self.distro_version = None
        self.directory = str(Path.home() / ".AffinityLinux")
        self._load_persisted_install_location()
        # An explicit target wins over the remembered one: the caller asked for
        # this prefix, and must not be redirected to whatever was used last.
        self._forced_directory = override_install_dir()
        if self._forced_directory:
            self.directory = self._forced_directory
        self.setup_complete = False
        self.installer_file = override_installer_file()
        self.update_buttons = {}
        self.switch_backend_button = None
        self.log_font_size = 11
        self.operation_cancelled = False
        self.current_operation = None
        self.operation_in_progress = False
        self.sudo_password = None
        self.sudo_password_validated = False
        self.sudo_password_dialog_done = True
        self.interactive_response = None
        self.waiting_for_response = False
        self.question_dialog_response = None
        self.waiting_for_question_response = False
        self.nvidia_dxvk_vkd3d_choice_response = None
        self.waiting_for_nvidia_choice = False
        self.theme = "mattscreative"
        self.dark_mode = True
        self._themes = ("dark", "light", "mattscreative")
        self._theme_display_names = {
            "dark": "Dark",
            "light": "Light",
            "mattscreative": "Mattscreative",
        }
        self._section_title_labels = []
        self.icon_buttons = []
        self._all_action_buttons = []
        self.enable_opencl = False
        self.cancel_event = threading.Event()
        self._process_lock = threading.Lock()
        self._active_processes = set()
        # Winetricks verbs that already stalled once this session: a wedged
        # ngen.exe wedges again, so we must not blindly retry them.
        self._stalled_components = set()
        # Log lines waiting to be painted (see _flush_log_queue).
        self._log_queue = []
        self._log_queue_lock = threading.Lock()
        self._button_spinner_map = {}
        self._last_clicked_button = None
        self._operation_button = None

        self.log_file_path = Path.home() / "AffinitySetup.log"
        self.log_file = None
        self._init_log_file()
        step_start = log_timing("Log file init", step_start)

        self.log_signal.connect(self._log_safe)
        self.progress_signal.connect(self._update_progress_safe)
        self.progress_text_signal.connect(self._update_progress_text_safe)
        self.operation_clock_signal.connect(self._operation_clock_safe)
        self.show_message_signal.connect(self._show_message_safe)
        self.sudo_password_dialog_signal.connect(self._request_sudo_password_safe)
        self.interactive_prompt_signal.connect(self._request_interactive_response_safe)
        self.question_dialog_signal.connect(self._show_question_dialog_safe)
        self.nvidia_dxvk_vkd3d_choice_signal.connect(
            self._show_nvidia_dxvk_vkd3d_choice_safe
        )
        self.prompt_affinity_install_signal.connect(self._prompt_affinity_install)
        self.install_application_signal.connect(self.install_application)
        self.show_spinner_signal.connect(self._show_spinner_safe)
        self.hide_spinner_signal.connect(self._hide_spinner_safe)
        self.waiting_for_gpu_selection = False
        self.gpu_selection_signal.connect(self._configure_gpu_selection_safe)
        self.icons_updated_signal.connect(self._update_button_icons)
        self.refresh_status_signal.connect(self.check_installation_status)
        self.show_main_menu_signal.connect(self.show_main_menu)
        self.window_icon_signal.connect(self._set_window_icon_safe)
        self.apply_auto_dpi_signal.connect(self._apply_auto_dpi_on_main_thread)
        self.cancel_button_signal.connect(self._set_cancel_button_visible_safe)
        step_start = log_timing("Signal connections", step_start)

        self.create_ui()
        step_start = log_timing("Create UI", step_start)

        self.apply_theme()
        step_start = log_timing("Apply theme", step_start)

        self.center_window()
        step_start = log_timing("Center window", step_start)

        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Affinity Linux Installer - Ready", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Which prefix this window drives, in the title bar and in the log.
        #
        # Two installer windows can be open at once -- one on the working prefix
        # and one on a copy -- and they share this log file. With a fixed title
        # and unmarked log lines there was no way to tell them apart, on screen
        # or afterwards: an interleaved log reads as one process doing
        # contradictory things to two directories. The pid is here so a log can
        # be untangled after the fact.
        self.announce_target()

        step_start = log_timing("Defer slow operations", step_start)

        total_time = time.time() - startup_start
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "info",
        )
        self.log("Startup Performance:", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "info",
        )
        for step_name, elapsed in timing_log:
            percentage = (elapsed / total_time * 100) if total_time > 0 else 0
            self.log(
                f"  {step_name:.<30} {elapsed:>6.3f}s ({percentage:>5.1f}%)", "info"
            )
        self.log(f"  {'TOTAL STARTUP TIME':.<30} {total_time:>6.3f}s", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "info",
        )

        self.log("Welcome! Please use the buttons on the right to get started.", "info")

        system_specs = self._get_system_specs()
        if system_specs:
            self.log("", "info")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "info",
            )
            self.log("System Specifications:", "info")
            for spec in system_specs:
                self.log(f"  {spec}", "info")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "info",
            )

            if self.log_file:
                try:
                    self.log_file.write(f"\nSystem Specifications:\n")
                    for spec in system_specs:
                        self.log_file.write(f"  {spec}\n")
                    self.log_file.write(f"{'=' * 80}\n")
                    self.log_file.flush()
                except Exception:
                    pass

        from PyQt6.QtCore import QTimer

        QTimer.singleShot(50, self._deferred_startup_tasks)
        QTimer.singleShot(500, self._check_and_update_dxvk_vkd3d)
        QTimer.singleShot(700, self.show_donation_dialog)

    def system_wine_matches_prefix(self):
        """Is the Wine on PATH the same build as the prefix's own Wine?

        A prefix belongs to the Wine that created it. Driving it with a
        different build risks a wineserver protocol refusal -- "version mismatch
        961/931", instant and quiet enough to be mistaken for the installer
        having started -- and, when no server happens to be running, something
        worse: a wineboot from an older Wine writing over a prefix built by a
        newer one.

        Compare the versions rather than probing. An earlier version of this
        asked `wine --version` under the prefix and looked for the mismatch
        text, which never appears: --version prints and exits without ever
        contacting wineserver, so the check passed in exactly the case it was
        written to catch.
        """
        def version_of(binary):
            try:
                result = subprocess.run(
                    [str(binary), "--version"],
                    capture_output=True, text=True, timeout=30,
                )
                return (result.stdout or result.stderr or "").strip().splitlines()[0].strip()
            except Exception:
                return None

        own = self.get_wine_path("wine")
        if not own or not Path(str(own)).exists():
            return True                      # no Wine in the prefix; system is all there is

        system_version, own_version = version_of("wine"), version_of(own)
        if not system_version or not own_version:
            return False                     # cannot tell: the prefix's own Wine is always right
        return system_version == own_version

    def announce_target(self):
        """Put the prefix this window operates on in the title and the log."""
        target = Path(self.directory)
        forced = " (given by the caller)" if getattr(self, "_forced_directory", None) else ""
        self.setWindowTitle(f"Affinity Linux Installer - {target.name}")
        self.setToolTip(str(target))
        self.log(f"Install directory: {target}{forced}   [pid {os.getpid()}]", "info")

    def _deferred_startup_tasks(self):
        """Run slow startup tasks in background after window is shown"""
        self._normalize_action_buttons()

        self.load_affinity_icon()

        self.setup_zoom()

        def run_background_tasks():
            import time as time_module

            bg_start = time_module.time()

            icons_start = time_module.time()
            self._ensure_icons_directory()
            icons_time = time_module.time() - icons_start
            if icons_time > 0.1:
                self.icons_updated_signal.emit()

            patcher_start = time_module.time()
            self.ensure_patcher_files(silent=True)
            patcher_time = time_module.time() - patcher_start

            status_start = time_module.time()
            self.refresh_status_signal.emit()
            status_time = time_module.time() - status_start

            total_bg_time = time_module.time() - bg_start

            if icons_time > 0.1 or patcher_time > 0.1 or status_time > 0.1:
                self.log(
                    f"Background tasks completed: icons={icons_time:.3f}s, patcher={patcher_time:.3f}s, status={status_time:.3f}s, total={total_bg_time:.3f}s",
                    "info",
                )

            wine_path = self.get_wine_path("wine")
            if not wine_path.exists():
                self.log(
                    "Click 'Setup Wine Environment' or 'One-Click Full Setup' to begin.",
                    "info",
                )
            else:
                self.log(
                    "Wine is set up. Use 'Update Affinity Applications' to install or update apps.",
                    "info",
                )

        threading.Thread(target=run_background_tasks, daemon=True).start()

    def check_installation_status(self):
        self.update_switch_backend_button()
        """Check if Wine and Affinity applications are installed, and update button states"""
        wine = self.get_wine_path("wine")
        wine_staging = self.get_wine_path("wine-staging")

        # Check if either wine or wine-staging exists
        wine_exists = wine.exists() or wine_staging.exists()

        wine_version_display = "Wine"
        if wine_exists:
            # Try both wine and wine-staging binaries
            for wine_bin in [wine, wine_staging]:
                if wine_bin.exists():
                    try:
                        success, stdout, _ = self.run_command(
                            [str(wine_bin), "--version"], check=False, capture=True
                        )
                        if success and stdout:
                            version_match = re.search(r"wine-(\d+\.\d+)", stdout)
                            if version_match:
                                wine_version_display = f"Wine {version_match.group(1)}"
                                break  # Found a working wine binary, no need to check further
                            else:
                                wine_dir = Path(self.directory) / "ElementalWarriorWine"
                                if (wine_dir / "bin" / "wine").exists():
                                    wine_version_display = "Wine (patched)"
                                    break
                    except Exception:
                        continue

            # If we still haven't found a version, mark as patched
            if wine_version_display == "Wine":
                wine_version_display = "Wine (patched)"

        if hasattr(self, "system_status_label"):
            if wine_exists:
                self.system_status_label.setStyleSheet(
                    "font-size: 12px; color: #4ec9b0; background-color: transparent; border: none; padding: 0px;"
                )
                self.system_status_label.setToolTip(
                    f"System Status: Ready - {wine_version_display} is installed"
                )
                if hasattr(self, "status_text_label"):
                    self.status_text_label.setText("Ready")
            else:
                self.system_status_label.setStyleSheet(
                    "font-size: 12px; color: #f48771; background-color: transparent; border: none; padding: 0px;"
                )
                self.system_status_label.setToolTip(
                    "System Status: Not Ready - Wine needs to be installed"
                )
                if hasattr(self, "status_text_label"):
                    self.status_text_label.setText("Not Ready")

        if wine_exists:
            self.log(f"Wine: ✓ Installed ({wine_version_display})", "success")
        else:
            self.log("Wine: ✗ Not installed", "error")

        app_status = {}
        app_names_display = {
            "Add": "Affinity (Unified)",
            "Photo": "Affinity Photo",
            "Designer": "Affinity Designer",
            "Publisher": "Affinity Publisher",
        }
        app_dirs = {
            "Add": ("Affinity", "Affinity.exe"),
            "Photo": ("Photo 2", "Photo.exe"),
            "Designer": ("Designer 2", "Designer.exe"),
            "Publisher": ("Publisher 2", "Publisher.exe"),
        }

        self.log("Affinity Applications:", "info")
        for app_name, (dir_name, exe_name) in app_dirs.items():
            app_path = (
                Path(self.directory)
                / "drive_c"
                / "Program Files"
                / "Affinity"
                / dir_name
                / exe_name
            )
            is_installed = app_path.exists()
            app_status[app_name] = is_installed

            display_name = app_names_display.get(app_name, app_name)
            if is_installed:
                self.log(f"  {display_name}: ✓ Installed", "success")
            else:
                self.log(f"  {display_name}: ✗ Not installed", "error")

            if app_name in self.update_buttons:
                btn = self.update_buttons[app_name]
                if is_installed:
                    current_text = btn.text()
                    if "✓" not in current_text:
                        btn.setText(current_text.split("✓")[0].strip() + " ✓")
                    btn.setEnabled(True)

        self.log("System Dependencies:", "info")
        deps = ["wine", "winetricks", "wget", "curl", "7z", "tar", "jq"]
        deps_installed = True
        for dep in deps:
            label = DEP_LABELS.get(dep, dep)
            if self.check_command(dep):
                self.log(f"  {label}: ✓ Installed", "success")
            else:
                self.log(f"  {label}: ✗ Not installed", "error")
                deps_installed = False

        if opencl_drivers():
            self.log(f"  OpenCL driver: ✓ {', '.join(opencl_drivers())}", "success")
        elif gpu_vendors():
            self.log("  OpenCL driver: ✗ none (Affinity runs without OpenCL) — "
                     + (self.opencl_advice() or ""), "warning")

        if self.check_command("unzstd") or self.check_command("zstd"):
            self.log(f"  zstd: ✓ Installed", "success")
        else:
            self.log(f"  zstd: ✗ Not installed (optional)", "warning")

        if self.check_command("xz") or self.check_command("unxz"):
            self.log(f"  xz: ✓ Installed", "success")
        else:
            self.log(
                f"  xz: ✗ Not installed (optional - Python lzma will be used)",
                "warning",
            )

        if self.check_dotnet_sdk():
            self.log(f"  .NET SDK: ✓ Installed", "success")
        else:
            self.log(f"  .NET SDK: ✗ Not installed", "error")

        if wine_exists:
            self.log("Winetricks Dependencies:", "info")
            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory
            wine = self.get_wine_path("wine")

            # renderer=vulkan has its own dedicated check below.
            winetricks_components = [
                (component, description)
                for component, description in WINETRICKS_COMPONENTS
                if component != "renderer=vulkan"
            ]

            for component, description in winetricks_components:
                if self._check_winetricks_component(component, wine, env):
                    self.log(f"  {description}: ✓ Installed", "success")
                else:
                    self.log(f"  {description}: ✗ Not installed", "error")

            try:
                if self._wine_reg_key_exists("HKCU", r"Software\Wine\Direct3D"):
                    renderer = self._read_wine_reg_value(
                        "HKCU", r"Software\Wine\Direct3D", "renderer"
                    )
                    vulkan_set = isinstance(renderer, str) and "vulkan" in renderer.lower()

                    if vulkan_set:
                        self.log(f"  Vulkan Renderer: ✓ Configured", "success")
                    else:
                        self.log(f"  Vulkan Renderer: ⚠ Not configured", "warning")
                else:
                    self.log(f"  Vulkan Renderer: ✗ Not configured", "error")
            except Exception:
                self.log(f"  Vulkan Renderer: ✗ Not configured", "error")

            self.log("WebView2 Runtime:", "info")
            if self.check_webview2_installed():
                self.log(f"  Microsoft Edge WebView2 Runtime: ✓ Installed", "success")
            else:
                self.log(f"  Microsoft Edge WebView2 Runtime: ✗ Not installed", "error")

        self.log("", "info")

        for app_name, button in self.update_buttons.items():
            if button is None:
                continue

            is_installed = app_status.get(app_name, False)
            enabled = wine_exists and is_installed

            button.setEnabled(enabled)
            if enabled:
                button.setStyleSheet("")

    def center_window(self):
        """Center window on screen"""
        frame = self.frameGeometry()
        screen = self.screen().availableGeometry().center()
        frame.moveCenter(screen)
        self.move(frame.topLeft())

    def setup_zoom(self):
        """Setup zoom in/out functionality for log area"""
        zoom_in_shortcut = QShortcut(QKeySequence("Ctrl+Plus"), self)
        zoom_in_shortcut.activated.connect(self.zoom_in)
        zoom_in_shortcut_alt = QShortcut(QKeySequence("Ctrl+="), self)
        zoom_in_shortcut_alt.activated.connect(self.zoom_in)

        zoom_out_shortcut = QShortcut(QKeySequence("Ctrl+Minus"), self)
        zoom_out_shortcut.activated.connect(self.zoom_out)
        zoom_out_shortcut_alt = QShortcut(QKeySequence("Ctrl+-"), self)
        zoom_out_shortcut_alt.activated.connect(self.zoom_out)

        zoom_reset_shortcut = QShortcut(QKeySequence("Ctrl+0"), self)
        zoom_reset_shortcut.activated.connect(self.zoom_reset)

    def zoom_in(self):
        """Zoom in (increase font size)"""
        if not hasattr(self, "log_text") or not self.log_text:
            return

        new_size = min(self.log_font_size + 1, 48)
        if new_size != self.log_font_size:
            self.log_font_size = new_size
            font = QFont("Consolas", self.log_font_size)
            self.log_text.setFont(font)
            self.log_text.document().setDefaultFont(font)
            self.update_zoom_buttons()

    def zoom_out(self):
        """Zoom out (decrease font size)"""
        if not hasattr(self, "log_text") or not self.log_text:
            return

        new_size = max(self.log_font_size - 1, 6)
        if new_size != self.log_font_size:
            self.log_font_size = new_size
            font = QFont("Consolas", self.log_font_size)
            self.log_text.setFont(font)
            self.log_text.document().setDefaultFont(font)
            self.update_zoom_buttons()

    def zoom_reset(self):
        """Reset zoom to default size"""
        if not hasattr(self, "log_text") or not self.log_text:
            return

        self.log_font_size = 11
        font = QFont("Consolas", 11)
        self.log_text.setFont(font)
        self.log_text.document().setDefaultFont(font)
        self.update_zoom_buttons()

    def update_zoom_buttons(self):
        """Update zoom button states"""
        try:
            if hasattr(self, "log_text") and self.log_text:
                current_font = self.log_text.currentFont()
                current_size = (
                    current_font.pointSize() if current_font else self.log_font_size
                )

                if hasattr(self, "zoom_in_btn"):
                    self.zoom_in_btn.setEnabled(current_size < 48)
                if hasattr(self, "zoom_out_btn"):
                    self.zoom_out_btn.setEnabled(current_size > 6)
        except Exception:
            pass

    def get_icon_path(self, icon_name):
        """Get the path to a light or dark icon based on theme"""
        if not icon_name:
            return None

        theme_suffix = "light" if self.dark_mode else "dark"

        icons_dir = (
            Path.home() / ".config" / "AffinityOnLinux" / "AffinityScripts" / "icons"
        )

        themed_icon_path = icons_dir / f"{icon_name}-{theme_suffix}.svg"
        if themed_icon_path.exists():
            return themed_icon_path

        base_icon_path = icons_dir / f"{icon_name}.svg"
        if base_icon_path.exists():
            return base_icon_path

        here = script_dir()
        local_icons_dir = (here / "icons") if here else None
        if local_icons_dir and local_icons_dir.exists():
            local_themed_icon = local_icons_dir / f"{icon_name}-{theme_suffix}.svg"
            if local_themed_icon.exists():
                return local_themed_icon

            local_base_icon = local_icons_dir / f"{icon_name}.svg"
            if local_base_icon.exists():
                return local_base_icon

        return None

    def _update_button_icons(self):
        """Update all button icons to match the current theme"""
        for btn, icon_name in self.icon_buttons:
            icon_path = self.get_icon_path(icon_name)
            if icon_path:
                icon = QIcon(str(icon_path))
                btn.setIcon(icon)
                if btn.objectName() == "zoomButton":
                    btn.setText("")
        self._normalize_action_buttons()

    def toggle_theme(self):
        """Cycle through dark, light, and mattscreative themes"""
        current_index = self._themes.index(self.theme)
        self.theme = self._themes[(current_index + 1) % len(self._themes)]
        self.apply_theme()

        next_theme = self._themes[
            (self._themes.index(self.theme) + 1) % len(self._themes)
        ]
        self.theme_toggle_btn.setText(self._theme_display_names[self.theme])
        self.theme_toggle_btn.setToolTip(
            "Switch to {} Theme".format(self._theme_display_names[next_theme])
        )

        self._update_button_icons()

        self._update_top_bar_style()

        self._update_theme_button_style()

        self._update_right_scroll_style()

        self._update_progress_label_style()

    def _dark_dialog_stylesheet(self):
        """Dark dialog stylesheet (base for the Mattscreative theme too)"""
        return """
            QDialog {
                background-color: #252526;
                color: #dcdcdc;
            }
                QLabel {
                    color: #dcdcdc;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4ec9b0;
                    padding: 10px 0px;
                    background-color: transparent;
                    border: none;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #cccccc;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                    background-color: transparent;
                    border: none;
                }
                QLineEdit {
                    background-color: #3c3c3c;
                    color: #dcdcdc;
                    border: 1px solid #555555;
                    border-radius: 6px;
                    padding: 8px 12px;
                    font-size: 13px;
                }
                QLineEdit:focus {
                    border: 1px solid #4ec9b0;
                    background-color: #3d3d3d;
                }
                QFrame#optionFrame {
                    background-color: #2d2d2d;
                    border: 1px solid #3c3c3c;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #4a4a4a;
                    background-color: #323232;
                }
                QRadioButton {
                    font-size: 16px;
                    color: #dcdcdc;
                    padding: 8px 0px;
                    spacing: 10px;
                    font-weight: 500;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #555555;
                    background-color: #3c3c3c;
                }
                QRadioButton::indicator:hover {
                    border-color: #6a6a6a;
                }
                QRadioButton::indicator:checked {
                    background-color: #4ec9b0;
                    border-color: #4ec9b0;
                }
                QPushButton {
                    background-color: #3c3c3c;
                    color: #f0f0f0;
                    border: 1px solid #555555;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                    border-color: #6a6a6a;
                }
                QPushButton:pressed {
                    background-color: #2d2d2d;
                }
                QPushButton#okButton, QPushButton#primaryButton {
                    background-color: #4ec9b0;
                    color: #1e1e1e;
                    border: 1px solid #4ec9b0;
                    font-weight: bold;
                }
                QPushButton#okButton:hover, QPushButton#primaryButton:hover {
                    background-color: #5dd9c0;
                    border-color: #5dd9c0;
                }
                QPushButton#okButton:pressed, QPushButton#primaryButton:pressed {
                    background-color: #3db9a0;
                }
                QPushButton#koFiButton {
                    background-color: #ff5e5b;
                    color: #ffffff;
                    border: 1px solid #ff5e5b;
                    font-weight: bold;
                }
                QPushButton#koFiButton:hover {
                    background-color: #ff7673;
                    border-color: #ff7673;
                }
                QPushButton#payPalButton {
                    background-color: #0070ba;
                    color: #ffffff;
                    border: 1px solid #0070ba;
                    font-weight: bold;
                }
                QPushButton#payPalButton:hover {
                    background-color: #0b7fc9;
                    border-color: #0b7fc9;
                }
                QDialogButtonBox QPushButton {
                    background-color: #3c3c3c;
                    color: #f0f0f0;
                    border: 1px solid #555555;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QDialogButtonBox QPushButton:hover {
                    background-color: #4a4a4a;
                    border-color: #6a6a6a;
                }
                QDialogButtonBox QPushButton:pressed {
                    background-color: #2d2d2d;
                }
                QSlider::groove:horizontal {
                    background-color: #3c3c3c;
                    height: 6px;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background-color: #4ec9b0;
                    width: 18px;
                    height: 18px;
                    margin: -6px 0;
                    border-radius: 9px;
                }
                QSlider::handle:horizontal:hover {
                    background-color: #5dd9c0;
                }
                QSlider::sub-page:horizontal {
                    background-color: #4ec9b0;
                    border-radius: 3px;
                }
                QSlider::add-page:horizontal {
                    background-color: #3c3c3c;
                    border-radius: 3px;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background-color: #2d2d2d;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #555555;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #666666;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
    """

    def _mattscreative_palette_style(self, dark_stylesheet):
        """Recolor a dark stylesheet with the Mattscreative palette"""
        return (
            dark_stylesheet
            .replace("#252526", "#161022")
            .replace("#3c3c3c", "#1A0A2E")
            .replace("#3d3d3d", "#241238")
            .replace("#323232", "#241238")
            .replace("#2d2d2d", "#1A0A2E")
            .replace("#4a4a4a", "#241238")
            .replace("#555555", "#3a2a5e")
            .replace("#6a6a6a", "#4a3a6e")
            .replace("#666666", "#4a3a6e")
            .replace("#b0b0b0", "#B8A9C9")
            .replace("#4ec9b0", "#04BEEF")
            .replace("#5dd9c0", "#2ac8f5")
            .replace("#3db9a0", "#04A8CC")
            .replace("#2da990", "#0795B8")
            .replace("#cccccc", "#B8A9C9")
            .replace("#dcdcdc", "#e6e0ee")
            .replace("#f0f0f0", "#FFFFFF")
            .replace("#1e1e1e", "#0F0818")
        )

    def _mattscreative_dialog_stylesheet(self):
        """Mattscreative dialog stylesheet - deep purple base with gold and cyan accents"""
        return self._mattscreative_palette_style(self._dark_dialog_stylesheet())

    def get_dialog_stylesheet(self):
        """Get the appropriate stylesheet for dialogs based on current theme - clean modern style"""
        if self.theme == "mattscreative":
            return self._mattscreative_dialog_stylesheet()
        if self.dark_mode:
            return self._dark_dialog_stylesheet()
        return self._light_dialog_stylesheet()

    def _light_dialog_stylesheet(self):
        """Light dialog stylesheet - clean modern style"""
        return """
                QDialog {
                    background-color: #ffffff;
                    color: #2d2d2d;
                }
                QLabel {
                    color: #2d2d2d;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4caf50;
                    padding: 10px 0px;
                    background-color: transparent;
                    border: none;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #555555;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                    background-color: transparent;
                    border: none;
                }
                QLineEdit {
                    background-color: #ffffff;
                    color: #2d2d2d;
                    border: 1px solid #c0c0c0;
                    border-radius: 6px;
                    padding: 8px 12px;
                    font-size: 13px;
                }
                QLineEdit:focus {
                    border: 1px solid #4caf50;
                    background-color: #fafafa;
                }
                QFrame#optionFrame {
                    background-color: #f5f5f5;
                    border: 1px solid #e0e0e0;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #c0c0c0;
                    background-color: #fafafa;
                }
                QRadioButton {
                    font-size: 14px;
                    color: #2d2d2d;
                    padding: 8px 0px;
                    spacing: 10px;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #c0c0c0;
                    background-color: #ffffff;
                }
                QRadioButton::indicator:hover {
                    border-color: #a0a0a0;
                }
                QRadioButton::indicator:checked {
                    background-color: #4caf50;
                    border-color: #4caf50;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    color: #2d2d2d;
                    border: 1px solid #c0c0c0;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #d0d0d0;
                    border-color: #a0a0a0;
                }
                QPushButton:pressed {
                    background-color: #c0c0c0;
                }
                QPushButton#okButton, QPushButton#primaryButton {
                    background-color: #4caf50;
                    color: #ffffff;
                    border: 1px solid #4caf50;
                    font-weight: bold;
                }
                QPushButton#okButton:hover, QPushButton#primaryButton:hover {
                    background-color: #45a049;
                    border-color: #45a049;
                }
                QPushButton#okButton:pressed, QPushButton#primaryButton:pressed {
                    background-color: #3d8b40;
                }
                QPushButton#koFiButton {
                    background-color: #ff5e5b;
                    color: #ffffff;
                    border: 1px solid #ff5e5b;
                    font-weight: bold;
                }
                QPushButton#koFiButton:hover {
                    background-color: #ff7673;
                    border-color: #ff7673;
                }
                QPushButton#payPalButton {
                    background-color: #0070ba;
                    color: #ffffff;
                    border: 1px solid #0070ba;
                    font-weight: bold;
                }
                QPushButton#payPalButton:hover {
                    background-color: #0b7fc9;
                    border-color: #0b7fc9;
                }
                QDialogButtonBox QPushButton {
                    background-color: #e0e0e0;
                    color: #2d2d2d;
                    border: 1px solid #c0c0c0;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QDialogButtonBox QPushButton:hover {
                    background-color: #d0d0d0;
                    border-color: #a0a0a0;
                }
                QDialogButtonBox QPushButton:pressed {
                    background-color: #c0c0c0;
                }
                QSlider::groove:horizontal {
                    background-color: #e0e0e0;
                    height: 6px;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background-color: #4caf50;
                    width: 18px;
                    height: 18px;
                    margin: -6px 0;
                    border-radius: 9px;
                }
                QSlider::handle:horizontal:hover {
                    background-color: #45a049;
                }
                QSlider::sub-page:horizontal {
                    background-color: #4caf50;
                    border-radius: 3px;
                }
                QSlider::add-page:horizontal {
                    background-color: #e0e0e0;
                    border-radius: 3px;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background-color: #f5f5f5;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #c0c0c0;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #a0a0a0;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
        """

    def get_messagebox_stylesheet(self):
        """Get the appropriate stylesheet for message boxes based on current theme - clean modern style"""
        if self.theme == "mattscreative":
            return self._mattscreative_palette_style(self._dark_messagebox_stylesheet())
        if self.dark_mode:
            return self._dark_messagebox_stylesheet()
        return self._light_messagebox_stylesheet()

    def _dark_messagebox_stylesheet(self):
        """Dark message box stylesheet (base for the Mattscreative theme too)"""
        return """
            QMessageBox {
                background-color: #252526;
                color: #dcdcdc;
            }
                QMessageBox QLabel {
                    color: #dcdcdc;
                    background-color: transparent;
                    font-size: 13px;
                    line-height: 1.4;
                }
                QMessageBox QPushButton {
                    background-color: #3c3c3c;
                    color: #f0f0f0;
                    border: 1px solid #555555;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QMessageBox QPushButton:hover {
                    background-color: #4a4a4a;
                    border-color: #6a6a6a;
                }
                QMessageBox QPushButton:pressed {
                    background-color: #2d2d2d;
                }
                QMessageBox QPushButton[default="true"] {
                    background-color: #4ec9b0;
                    color: #1e1e1e;
                    border: 1px solid #4ec9b0;
                    font-weight: bold;
                }
                QMessageBox QPushButton[default="true"]:hover {
                    background-color: #5dd9c0;
                    border-color: #5dd9c0;
                }
                QMessageBox QPushButton[default="true"]:pressed {
                    background-color: #3db9a0;
                }
        """

    def _light_messagebox_stylesheet(self):
        """Light message box stylesheet"""
        return """
                QMessageBox {
                    background-color: #ffffff;
                    color: #2d2d2d;
                }
                QMessageBox QLabel {
                    color: #2d2d2d;
                    background-color: transparent;
                    font-size: 13px;
                    line-height: 1.4;
                }
                QMessageBox QPushButton {
                    background-color: #e0e0e0;
                    color: #2d2d2d;
                    border: 1px solid #c0c0c0;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QMessageBox QPushButton:hover {
                    background-color: #d0d0d0;
                    border-color: #a0a0a0;
                }
                QMessageBox QPushButton:pressed {
                    background-color: #c0c0c0;
                }
                QMessageBox QPushButton[default="true"] {
                    background-color: #4caf50;
                    color: #ffffff;
                    border: 1px solid #4caf50;
                    font-weight: bold;
                }
                QMessageBox QPushButton[default="true"]:hover {
                    background-color: #45a049;
                    border-color: #45a049;
                }
                QMessageBox QPushButton[default="true"]:pressed {
                    background-color: #3d8b40;
                }
        """

    def show_donation_dialog(self):
        """Show a donation dialog with PayPal and Ko-fi links"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Support This Project")
        dialog.setModal(True)
        dialog.setMinimumWidth(420)
        dialog.setStyleSheet(self.get_dialog_stylesheet())

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Support This Project")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(title)

        message = QLabel(
            "If you want to support this project, donating helps keep this project "
            "alive. Here are the links:"
        )
        message.setObjectName("descriptionLabel")
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(message)

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(12)

        ko_fi_btn = QPushButton("Ko-fi")
        ko_fi_btn.setObjectName("koFiButton")
        ko_fi_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ko_fi_btn.setToolTip("https://ko-fi.com/tlv")
        ko_fi_btn.clicked.connect(
            lambda: self._open_donation_url("https://ko-fi.com/tlv")
        )
        buttons_layout.addWidget(ko_fi_btn)

        paypal_btn = QPushButton("PayPal")
        paypal_btn.setObjectName("payPalButton")
        paypal_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        paypal_btn.setToolTip("https://paypal.me/gamedev1909")
        paypal_btn.clicked.connect(
            lambda: self._open_donation_url("https://paypal.me/gamedev1909")
        )
        buttons_layout.addWidget(paypal_btn)

        layout.addLayout(buttons_layout)

        button_box = QDialogButtonBox()
        close_btn = button_box.addButton(QDialogButtonBox.StandardButton.Close)
        close_btn.clicked.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.layout().activate()
        message.adjustSize()
        dialog.adjustSize()
        dialog.exec()

    def _open_donation_url(self, url):
        """Open a donation URL in the system web browser"""
        try:
            webbrowser.open(url)
        except Exception:
            self._show_message_safe(
                "Donate",
                f"Could not open your browser. Please visit:\n{url}",
                "info",
            )

    def apply_theme(self):
        """Apply current theme (dark, light, or mattscreative)"""
        self.dark_mode = self.theme != "light"
        if self.theme == "dark":
            self._apply_dark_theme()
        elif self.theme == "light":
            self._apply_light_theme()
        else:
            self._apply_mattscreative_theme()
        self._update_section_titles()
        # Fonts/padding just changed (and the titles were re-cased), so the
        # columns' real minimum width is known now - re-assert it.
        self._refresh_window_minimum_width()

    def _apply_dark_theme(self):
        """Apply modern dark theme with card-based design"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a1a;
            }
            QWidget {
                background-color: #1a1a1a;
                color: #e0e0e0;
                font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
                font-size: 13px;
            }
            /* Top Bar */
            QFrame#topBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a2a, stop:1 #1f1f1f);
                border-bottom: 2px solid #333333;
            }
            QLabel#titleLabel {
                font-size: 20px;
                font-weight: 600;
                color: #ffffff;
                letter-spacing: -0.5px;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QLabel#statusIndicator {
                font-size: 12px;
                color: #666666;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QLabel#statusText {
                font-size: 12px;
                color: #999999;
                font-weight: 500;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QPushButton#themeToggle {
                background-color: #333333;
                color: #e0e0e0;
                border: 1px solid #444444;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton#themeToggle:hover {
                background-color: #3d3d3d;
                border-color: #555555;
            }
            QPushButton#donateButton {
                background-color: #e0a63d;
                color: #1e1e1e;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#donateButton:hover {
                background-color: #eeb24f;
            }
            /* Content Area */
            QWidget#contentArea {
                background-color: #1a1a1a;
            }
            /* Status Card */
            QFrame#statusCard {
                background-color: #252525;
                border: 1px solid #333333;
                border-radius: 12px;
            }
            QLabel#sectionTitle {
                font-size: 16px;
                font-weight: 600;
                color: #ffffff;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QLabel#statusTitle {
                font-size: 18px;
                font-weight: 600;
                color: #ffffff;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            /* Progress Section */
            QFrame#progressSection {
                background-color: #1e1e1e;
                border: 1px solid #2d2d2d;
                border-radius: 8px;
                padding: 12px;
            }
            QLabel#progressTimerLabel {
                font-size: 11px;
                color: #b0b0b0;
                padding: 0px 12px;
                background-color: transparent;
                border: none;
            }
            QLabel#progressLabel {
                font-size: 12px;
                font-weight: 500;
                color: #b0b0b0;
                padding: 8px 12px;
                background-color: transparent;
                border: none;
                border-radius: 0px;
            }
            QProgressBar#progressBar {
                border: none;
                background-color: #1a1a1a;
                height: 8px;
                border-radius: 4px;
            }
            QProgressBar#progressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4ec9b0, stop:1 #5dd9c0);
                border-radius: 4px;
            }
            QPushButton#cancelButton {
                background-color: #d32f2f;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#cancelButton:hover {
                background-color: #e53935;
            }
            QPushButton#cancelButton:pressed {
                background-color: #b71c1c;
            }
            /* Log Section */
            QFrame#logSection {
                background-color: #1e1e1e;
                border: 1px solid #2d2d2d;
                border-radius: 8px;
                padding: 12px;
            }
            QFrame#zoomToolbar {
                background-color: transparent;
                border: none;
            }
            QPushButton#zoomButton {
                background-color: #2d2d2d;
                color: #b0b0b0;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
            }
            QPushButton#zoomButton:hover {
                background-color: #3a3a3a;
                border-color: #4a4a4a;
                color: #ffffff;
            }
            QPushButton#zoomButton:disabled {
                background-color: #252525;
                color: #555555;
                border-color: #2d2d2d;
            }
            QTextEdit#logText {
                background-color: #0d0d0d;
                color: #d4d4d4;
                border: 1px solid #2d2d2d;
                border-radius: 8px;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 11px;
                padding: 12px;
                selection-background-color: #007acc;
            }
            /* Button Cards */
            QFrame#buttonCard {
                background-color: #252525;
                border: 1px solid #333333;
                border-radius: 12px;
            }
            QPushButton#actionButton {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #3d3d3d;
                padding: 12px 24px;
                border-radius: 100px;
                font-size: 14px;
                font-weight: 500;
                text-align: left;
            }
            QPushButton#actionButton:hover {
                background-color: #353535;
                border-color: #4d4d4d;
                color: #ffffff;
            }
            QPushButton#actionButton:pressed {
                background-color: #252525;
                border-color: #3d3d3d;
            }
            QPushButton#actionButton:disabled {
                background-color: #1f1f1f;
                color: #555555;
                border-color: #2d2d2d;
            }
            QPushButton#actionButton[class="primary"] {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4ec9b0, stop:1 #3db9a0);
                color: #000000;
                font-weight: 600;
                font-size: 14px;
                border: none;
            }
            QPushButton#actionButton[class="primary"]:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5dd9c0, stop:1 #4ec9b0);
            }
            QPushButton#actionButton[class="primary"]:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3db9a0, stop:1 #2da990);
            }
            /* Scroll Area */
            QScrollArea#rightScroll {
                background-color: #1a1a1a;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #1a1a1a;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #3d3d3d;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #4d4d4d;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QToolTip {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444444;
                padding: 6px;
                border-radius: 6px;
                font-size: 11px;
            }
            QDialog {
                background-color: #252525;
                border-radius: 12px;
            }
            QDialog QLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QDialog QLabel#titleLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QDialog QLabel#descriptionLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QMessageBox {
                background-color: #252525;
                border-radius: 12px;
            }
            QMessageBox QLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
        """)

    def _apply_light_theme(self):
        """Apply modern light theme with card-based design"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f7;
            }
            QWidget {
                background-color: #f5f5f7;
                color: #1d1d1f;
                font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
                font-size: 13px;
            }
            /* Top Bar */
            QFrame#topBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #f5f5f7);
                border-bottom: 2px solid #e0e0e0;
            }
            QLabel#titleLabel {
                font-size: 20px;
                font-weight: 600;
                color: #1d1d1f;
                letter-spacing: -0.5px;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QLabel#statusIndicator {
                font-size: 12px;
                color: #86868b;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QLabel#statusText {
                font-size: 12px;
                color: #515154;
                font-weight: 500;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QPushButton#themeToggle {
                background-color: #e5e5e7;
                color: #1d1d1f;
                border: 1px solid #d0d0d0;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton#themeToggle:hover {
                background-color: #d5d5d7;
                border-color: #c0c0c0;
            }
            QPushButton#donateButton {
                background-color: #f5a623;
                color: #1e1e1e;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#donateButton:hover {
                background-color: #f7b448;
            }
            /* Content Area */
            QWidget#contentArea {
                background-color: #f5f5f7;
            }
            /* Status Card */
            QFrame#statusCard {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
            }
            QLabel#sectionTitle {
                font-size: 16px;
                font-weight: 600;
                color: #1d1d1f;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QLabel#statusTitle {
                font-size: 18px;
                font-weight: 600;
                color: #1d1d1f;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            /* Progress Section */
            QFrame#progressSection {
                background-color: #fafafa;
                border: 1px solid #e5e5e7;
                border-radius: 8px;
                padding: 12px;
            }
            QLabel#progressTimerLabel {
                font-size: 11px;
                color: #515154;
                padding: 0px 12px;
                background-color: transparent;
                border: none;
            }
            QLabel#progressLabel {
                font-size: 12px;
                font-weight: 500;
                color: #515154;
                padding: 8px 12px;
                background-color: transparent;
                border: none;
                border-radius: 0px;
            }
            QProgressBar#progressBar {
                border: none;
                background-color: #e5e5e7;
                height: 8px;
                border-radius: 4px;
            }
            QProgressBar#progressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #34c759, stop:1 #30d158);
                border-radius: 4px;
            }
            QPushButton#cancelButton {
                background-color: #ff3b30;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#cancelButton:hover {
                background-color: #ff453a;
            }
            QPushButton#cancelButton:pressed {
                background-color: #d70015;
            }
            /* Log Section */
            QFrame#logSection {
                background-color: #fafafa;
                border: 1px solid #e5e5e7;
                border-radius: 8px;
                padding: 12px;
            }
            QFrame#zoomToolbar {
                background-color: transparent;
                border: none;
            }
            QPushButton#zoomButton {
                background-color: #ffffff;
                color: #515154;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
            }
            QPushButton#zoomButton:hover {
                background-color: #f5f5f7;
                border-color: #c0c0c0;
                color: #1d1d1f;
            }
            QPushButton#zoomButton:disabled {
                background-color: #f5f5f7;
                color: #86868b;
                border-color: #e0e0e0;
            }
            QTextEdit#logText {
                background-color: #ffffff;
                color: #1d1d1f;
                border: 1px solid #e5e5e7;
                border-radius: 8px;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 11px;
                padding: 12px;
                selection-background-color: #007aff;
            }
            /* Button Cards */
            QFrame#buttonCard {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
            }
            QPushButton#actionButton {
                background-color: #f5f5f7;
                color: #1d1d1f;
                border: 1px solid #e5e5e7;
                padding: 12px 24px;
                border-radius: 100px;
                font-size: 14px;
                font-weight: 500;
                text-align: left;
            }
            QPushButton#actionButton:hover {
                background-color: #ffffff;
                border-color: #d0d0d0;
                color: #000000;
            }
            QPushButton#actionButton:pressed {
                background-color: #e5e5e7;
                border-color: #c0c0c0;
            }
            QPushButton#actionButton:disabled {
                background-color: #f5f5f7;
                color: #86868b;
                border-color: #e5e5e7;
            }
            QPushButton#actionButton[class="primary"] {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #34c759, stop:1 #30d158);
                color: #ffffff;
                font-weight: 600;
                font-size: 14px;
                border: none;
            }
            QPushButton#actionButton[class="primary"]:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #30d158, stop:1 #2dd45f);
            }
            QPushButton#actionButton[class="primary"]:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #28cd55, stop:1 #24c04f);
            }
            /* Scroll Area */
            QScrollArea#rightScroll {
                background-color: #f5f5f7;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #f5f5f7;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #d0d0d0;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #c0c0c0;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QToolTip {
                background-color: #1d1d1f;
                color: #ffffff;
                border: 1px solid #2d2d2f;
                padding: 6px;
                border-radius: 6px;
                font-size: 11px;
            }
            QDialog {
                background-color: #ffffff;
                border-radius: 12px;
            }
            QDialog QLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QDialog QLabel#titleLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QDialog QLabel#descriptionLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QMessageBox {
                background-color: #ffffff;
                border-radius: 12px;
            }
            QMessageBox QLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
        """)

    def _apply_mattscreative_theme(self):
        """Apply the Mattscreative theme - deep purple base with gold and cyan accents"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #120B1F;
            }
            QWidget {
                background-color: #120B1F;
                color: #e6e0ee;
                font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
                font-size: 13px;
            }
            /* Top Bar */
            QFrame#topBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1A0A2E, stop:1 #120B1F);
                border-bottom: 2px solid #3a2a5e;
            }
            QLabel#titleLabel {
                font-size: 20px;
                font-weight: 600;
                color: #ffffff;
                letter-spacing: -0.5px;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QLabel#statusIndicator {
                font-size: 12px;
                color: #B8A9C9;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QLabel#statusText {
                font-size: 12px;
                color: #B8A9C9;
                font-weight: 500;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QPushButton#themeToggle {
                background-color: #1A0A2E;
                color: #ffffff;
                border: 1px solid #3a2a5e;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton#themeToggle:hover {
                background-color: #241238;
                border-color: #04BEEF;
            }
            QPushButton#donateButton {
                background-color: transparent;
                color: #FDB513;
                border: 1px solid #FDB513;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#donateButton:hover {
                background-color: #FDB513;
                color: #120B1F;
            }
            /* Content Area */
            QWidget#contentArea {
                background-color: #120B1F;
            }
            /* Status Card */
            QFrame#statusCard {
                background-color: #161022;
                border: 1px solid #2a1c3f;
                border-radius: 12px;
            }
            QLabel#sectionTitle {
                font-size: 15px;
                font-weight: 600;
                color: #ffffff;
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QLabel#statusTitle {
                font-size: 18px;
                font-weight: 600;
                color: #ffffff;
                background-color: transparent;
                border-top: none;
                border-left: none;
                border-right: none;
                border-bottom: 2px solid #FDB513;
                padding: 0px 0px 6px 0px;
            }
            /* Progress Section */
            QFrame#progressSection {
                background-color: #161022;
                border: 1px solid #2a1c3f;
                border-radius: 8px;
                padding: 12px;
            }
            QLabel#progressTimerLabel {
                font-size: 11px;
                color: #B8A9C9;
                padding: 0px 12px;
                background-color: transparent;
                border: none;
            }
            QLabel#progressLabel {
                font-size: 12px;
                font-weight: 500;
                color: #B8A9C9;
                padding: 8px 12px;
                background-color: transparent;
                border: none;
                border-radius: 0px;
            }
            QProgressBar#progressBar {
                border: none;
                background-color: #1A0A2E;
                height: 8px;
                border-radius: 4px;
            }
            QProgressBar#progressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #04BEEF, stop:1 #08A9D2);
                border-radius: 4px;
            }
            QPushButton#cancelButton {
                background-color: #FF6B6B;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#cancelButton:hover {
                background-color: #FF8080;
            }
            QPushButton#cancelButton:pressed {
                background-color: #E05555;
            }
            /* Log Section */
            QFrame#logSection {
                background-color: #161022;
                border: 1px solid #2a1c3f;
                border-radius: 8px;
                padding: 12px;
            }
            QFrame#zoomToolbar {
                background-color: transparent;
                border: none;
            }
            QPushButton#zoomButton {
                background-color: #1A0A2E;
                color: #B8A9C9;
                border: 1px solid #3a2a5e;
                border-radius: 6px;
            }
            QPushButton#zoomButton:hover {
                background-color: #241238;
                border-color: #04BEEF;
                color: #ffffff;
            }
            QPushButton#zoomButton:disabled {
                background-color: #161022;
                color: #6a5b80;
                border-color: #2a1c3f;
            }
            QTextEdit#logText {
                background-color: #0F0818;
                color: #d9d2e3;
                border: 1px solid #2a1c3f;
                border-radius: 8px;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 11px;
                padding: 12px;
                selection-background-color: #04BEEF;
            }
            /* Button Cards */
            QFrame#buttonCard {
                background-color: #161022;
                border: 1px solid #2a1c3f;
                border-radius: 12px;
            }
            QPushButton#actionButton {
                background-color: #1A0A2E;
                color: #ffffff;
                border: 1px solid #3a2a5e;
                padding: 12px 24px;
                border-radius: 100px;
                font-size: 14px;
                font-weight: 500;
                text-align: left;
            }
            QPushButton#actionButton:hover {
                background-color: #241238;
                border-color: #04BEEF;
                color: #ffffff;
            }
            QPushButton#actionButton:pressed {
                background-color: #161022;
                border-color: #3a2a5e;
            }
            QPushButton#actionButton:disabled {
                background-color: #161022;
                color: #6a5b80;
                border-color: #2a1c3f;
            }
            QPushButton#actionButton[class="primary"] {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #04BEEF, stop:1 #08A9D2);
                color: #0F0818;
                font-weight: 600;
                font-size: 14px;
                border: none;
            }
            QPushButton#actionButton[class="primary"]:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2ac8f5, stop:1 #04BEEF);
            }
            QPushButton#actionButton[class="primary"]:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #04A8CC, stop:1 #0795B8);
            }
            /* Scroll Area */
            QScrollArea#rightScroll {
                background-color: #120B1F;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #120B1F;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #3a2a5e;
                border-radius: 5px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #4a3a6e;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QToolTip {
                background-color: #1A0A2E;
                color: #ffffff;
                border: 1px solid #3a2a5e;
                padding: 6px;
                border-radius: 6px;
                font-size: 11px;
            }
            QDialog {
                background-color: #161022;
                border-radius: 12px;
            }
            QDialog QLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QDialog QLabel#titleLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QDialog QLabel#descriptionLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
            QMessageBox {
                background-color: #161022;
                border-radius: 12px;
            }
            QMessageBox QLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
            }
        """)

    def _update_theme_button_style(self):
        """Update theme toggle button styling based on current theme"""
        pass

    def _update_top_bar_style(self):
        """Update top bar styling based on current theme"""
        pass

    def _update_right_scroll_style(self):
        """Update side scroll area styling based on current theme"""
        scrolls = []
        if hasattr(self, "left_scroll"):
            scrolls.append(self.left_scroll)
        if hasattr(self, "right_scroll"):
            scrolls.append(self.right_scroll)

        if self.theme == "mattscreative":
            stylesheet = """
                QScrollArea {
                    background-color: #120B1F;
                    border: none;
                }
                QScrollBar:vertical {
                    background-color: #120B1F;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #3a2a5e;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #4a3a6e;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                    background: none;
                }
            """
        elif self.dark_mode:
            stylesheet = """
                QScrollArea {
                    background-color: #1c1c1c;
                    border: none;
                }
                QScrollBar:vertical {
                    background-color: #1c1c1c;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #555555;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #6a6a6a;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                    background: none;
                }
            """
        else:
            stylesheet = """
                QScrollArea {
                    background-color: #f5f5f5;
                    border: none;
                }
                QScrollBar:vertical {
                    background-color: #f5f5f5;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #c0c0c0;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #a0a0a0;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                    background: none;
                }
            """
        for scroll in scrolls:
            scroll.setStyleSheet(stylesheet)

    def _update_progress_label_style(self):
        """Update progress label styling based on current theme"""
        if hasattr(self, "progress_label"):
            if self.theme == "mattscreative":
                self.progress_label.setStyleSheet(
                    "font-size: 11px; font-weight: 500; color: #B8A9C9; "
                    "padding: 5px 10px; background-color: transparent; border: none; border-radius: 0px;"
                )
            elif self.dark_mode:
                self.progress_label.setStyleSheet(
                    "font-size: 11px; font-weight: 500; color: #dcdcdc; "
                    "padding: 5px 10px; background-color: transparent; border: none; border-radius: 0px;"
                )
            else:
                self.progress_label.setStyleSheet(
                    "font-size: 11px; font-weight: 500; color: #2d2d2d; "
                    "padding: 5px 10px; background-color: transparent; border: none; border-radius: 0px;"
                )

    def _update_section_titles(self):
        """Uppercase section titles with letter spacing for the Mattscreative theme"""
        for label, original_title in getattr(self, "_section_title_labels", []):
            font = label.font()
            if self.theme == "mattscreative":
                label.setText(original_title.upper())
                font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 110)
            else:
                label.setText(original_title)
                font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100)
            label.setFont(font)

    def _size_side_columns(self, content_layout, status_panel, side_panels):
        """Give the side button columns a minimum width inside a fixed budget.

        Each column needs room for its icon plus a few words of label; the rest
        of MIN_WINDOW_WIDTH is left for the log column and the gaps. The floors
        matter because Qt clips layout items it cannot fit rather than scrolling
        them, so a column that asks for its full text width (or a log column
        whose minimum grew with a long status line) would otherwise push the
        window wider than it is allowed to be.
        """
        try:
            margins = content_layout.contentsMargins()
            gaps = margins.left() + margins.right()
            # one gap per side column: 2 side columns -> 3 columns -> 2 gaps
            gaps += content_layout.spacing() * len(side_panels)
            status_layout = status_panel.layout() if status_panel is not None else None
            status_min = status_layout.minimumSize().width() if status_layout else 0
            budget = MIN_WINDOW_WIDTH - gaps - status_min
            floor = max(
                SIDE_PANEL_MIN_FLOOR,
                min(SIDE_PANEL_MIN_WIDTH, budget // max(1, len(side_panels))),
            )
        except Exception:
            floor = SIDE_PANEL_MIN_WIDTH
        for scroll in side_panels:
            scroll.setMinimumWidth(floor)

    def _refresh_window_minimum_width(self):
        """Keep the window from being squeezed narrower than its columns need.

        Qt honours a top-level minimum on resize but does not raise it when the
        content grows, so without this the layout ends up asking for more room
        than the window has and the buttons clip instead of scrolling/eliding.
        """
        try:
            central = self.centralWidget()
            layout = central.layout() if central is not None else None
            if layout is None:
                return
            minimum = layout.minimumSize().width()
            if minimum > 0:
                self.setMinimumWidth(minimum)
        except Exception:
            pass

    def create_ui(self):
        """Create the modern user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        screen = self.screen().availableGeometry()
        screen_width = screen.width()

        if screen_width < 1024:
            top_bar_height = 56
            top_bar_margin = 12
            top_bar_spacing = 12
            icon_size = 32
        else:
            top_bar_height = 64
            top_bar_margin = 24
            top_bar_spacing = 16
            icon_size = 40

        self.top_bar = QFrame()
        self.top_bar.setFixedHeight(top_bar_height)
        self.top_bar.setObjectName("topBar")
        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(top_bar_margin, 12, top_bar_margin, 12)
        top_bar_layout.setSpacing(top_bar_spacing)

        if hasattr(self, "affinity_icon_path") and self.affinity_icon_path:
            try:
                icon = QIcon(self.affinity_icon_path)
                self.setWindowIcon(icon)

                try:
                    svg_widget = QSvgWidget(self.affinity_icon_path)
                    svg_widget.setFixedSize(icon_size, icon_size)
                    svg_widget.setStyleSheet("background: transparent;")
                    top_bar_layout.addWidget(svg_widget)
                except Exception:
                    icon_label = QLabel()
                    pixmap = icon.pixmap(icon_size, icon_size)
                    if not pixmap.isNull():
                        icon_label.setPixmap(
                            pixmap.scaled(
                                icon_size,
                                icon_size,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                        )
                        icon_label.setFixedSize(icon_size, icon_size)
                        top_bar_layout.addWidget(icon_label)
            except Exception:
                pass

        self.title_label = QLabel("Affinity on Linux")
        self.title_label.setObjectName("titleLabel")
        if screen_width < 1024:
            self.title_label.setStyleSheet(
                "font-size: 18px; font-weight: 600; background-color: transparent; border: none; padding: 0px;"
            )
        else:
            self.title_label.setStyleSheet(
                "background-color: transparent; border: none; padding: 0px;"
            )
        top_bar_layout.addWidget(self.title_label)

        top_bar_layout.addStretch()

        status_container = QWidget()
        status_container.setStyleSheet("background-color: transparent; border: none;")
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)

        self.system_status_label = QLabel("●")
        self.system_status_label.setObjectName("statusIndicator")
        self.system_status_label.setToolTip("System Status: Initializing...")
        status_layout.addWidget(self.system_status_label)

        status_text = QLabel("Initializing...")
        status_text.setObjectName("statusText")
        if screen_width < 800:
            status_text.setVisible(False)
        status_layout.addWidget(status_text)
        self.status_text_label = status_text

        top_bar_layout.addWidget(status_container)

        self.donate_btn = QPushButton("Donate")
        self.donate_btn.setObjectName("donateButton")
        self.donate_btn.setToolTip("Support this project - Donate")
        self.donate_btn.setFixedSize(90, icon_size)
        self.donate_btn.clicked.connect(self.show_donation_dialog)
        top_bar_layout.addWidget(self.donate_btn)

        self.theme_toggle_btn = QPushButton(self._theme_display_names[self.theme])
        self.theme_toggle_btn.setObjectName("themeToggle")
        next_theme = self._themes[(self._themes.index(self.theme) + 1) % len(self._themes)]
        self.theme_toggle_btn.setToolTip(
            "Switch to {} Theme".format(self._theme_display_names[next_theme])
        )
        self.theme_toggle_btn.setFixedSize(max(icon_size * 3, 118), icon_size)
        self.theme_toggle_btn.clicked.connect(self.toggle_theme)
        top_bar_layout.addWidget(self.theme_toggle_btn)

        main_layout.addWidget(self.top_bar)

        content_widget = QWidget()
        content_widget.setObjectName("contentArea")
        content_layout = QHBoxLayout(content_widget)

        if screen_width < 1024:
            content_spacing = 12
            content_margin = 12
            right_panel_max = 360
        elif screen_width < 1280:
            content_spacing = 16
            content_margin = 16
            right_panel_max = 400
        else:
            content_spacing = 20
            content_margin = 20
            right_panel_max = 440

        content_layout.setSpacing(content_spacing)
        content_layout.setContentsMargins(
            content_margin, content_margin, content_margin, content_margin
        )

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setObjectName("leftScroll")
        self.left_scroll = left_scroll
        self._update_right_scroll_style()

        left_panel = self.create_button_sections()
        left_scroll.setWidget(left_panel)
        left_scroll.setMaximumWidth(right_panel_max)

        content_layout.addWidget(left_scroll, stretch=2)

        status_panel = self.create_status_section()
        content_layout.addWidget(status_panel, stretch=3)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setObjectName("rightScroll")
        self.right_scroll = right_scroll
        self._update_right_scroll_style()

        right_panel = self.create_troubleshooting_sections()
        right_scroll.setWidget(right_panel)
        right_scroll.setMaximumWidth(right_panel_max)

        content_layout.addWidget(right_scroll, stretch=2)

        main_layout.addWidget(content_widget, stretch=1)

        self._size_side_columns(content_layout, status_panel, (left_scroll, right_scroll))
        self._refresh_window_minimum_width()

    def create_status_section(self):
        """Create the modern status/log output section (responsive)"""
        screen = self.screen().availableGeometry()
        screen_width = screen.width()

        if screen_width < 1024:
            card_spacing = 12
            card_margin = 12
        elif screen_width < 1280:
            card_spacing = 14
            card_margin = 16
        else:
            card_spacing = 16
            card_margin = 20

        card = QFrame()
        card.setObjectName("statusCard")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(card_spacing)
        card_layout.setContentsMargins(
            card_margin, card_margin, card_margin, card_margin
        )

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Status & Log")
        title.setObjectName("statusTitle")
        header.addWidget(title)
        header.addStretch()
        card_layout.addLayout(header)
        self._section_title_labels.append((title, "Status & Log"))

        progress_section = QFrame()
        progress_section.setObjectName("progressSection")
        progress_layout = QVBoxLayout(progress_section)
        progress_layout.setSpacing(8)
        progress_layout.setContentsMargins(0, 0, 0, 0)

        self.progress_label = QLabel("Ready")
        self.progress_label.setObjectName("progressLabel")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Status lines are long ("Wine environment ready. Configure your
        # distribution below."). A single-line label would demand its full text
        # width as a minimum and drag the whole window's minimum width up with
        # it; wrapping keeps the log column's footprint stable.
        self.progress_label.setWordWrap(True)
        progress_layout.addWidget(self.progress_label)

        # When the current operation started and how long it has taken; the
        # last finished one stays shown until the next starts.
        self.timer_label = QLabel("")
        self.timer_label.setObjectName("progressTimerLabel")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label.hide()
        progress_layout.addWidget(self.timer_label)
        self._clock_started = None      # (wall-clock time, monotonic) of the start
        self._clock_tick = QTimer(self)
        self._clock_tick.setInterval(1000)
        self._clock_tick.timeout.connect(self._show_clock)
        self._clock_settle = QTimer(self)
        self._clock_settle.setSingleShot(True)
        self._clock_settle.setInterval(3000)
        self._clock_settle.timeout.connect(self._stop_clock)

        progress_container = QHBoxLayout()
        progress_container.setSpacing(12)
        progress_container.setContentsMargins(0, 0, 0, 0)

        self.progress = QProgressBar()
        self.progress.setObjectName("progressBar")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        progress_container.addWidget(self.progress, stretch=1)

        self.cancel_btn = QPushButton("✕")
        self.cancel_btn.setObjectName("cancelButton")
        self.cancel_btn.setToolTip("Cancel current operation")
        self.cancel_btn.setFixedSize(32, 32)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_operation)
        progress_container.addWidget(self.cancel_btn)

        progress_layout.addLayout(progress_container)
        card_layout.addWidget(progress_section)

        log_section = QFrame()
        log_section.setObjectName("logSection")
        log_layout = QVBoxLayout(log_section)
        log_layout.setSpacing(12)
        log_layout.setContentsMargins(0, 0, 0, 0)

        zoom_toolbar = QFrame()
        zoom_toolbar.setObjectName("zoomToolbar")
        zoom_layout = QHBoxLayout(zoom_toolbar)
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        zoom_layout.setSpacing(8)
        zoom_layout.addStretch()

        icon_name_zoom_out = "zoom-out"
        icon_path_zoom_out = self.get_icon_path(icon_name_zoom_out)
        self.zoom_out_btn = QPushButton()
        self.zoom_out_btn.setObjectName("zoomButton")
        self.zoom_out_btn.setToolTip("Zoom Out (Ctrl+-)")
        self.zoom_out_btn.setFixedSize(32, 32)
        if icon_path_zoom_out:
            self.zoom_out_btn.setIcon(QIcon(str(icon_path_zoom_out)))
        else:
            self.zoom_out_btn.setText("−")
        self.zoom_out_btn.setIconSize(QSize(18, 18))
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        zoom_layout.addWidget(self.zoom_out_btn)
        self.icon_buttons.append((self.zoom_out_btn, icon_name_zoom_out))

        icon_name_zoom_reset = "zoom-original"
        icon_path_zoom_reset = self.get_icon_path(icon_name_zoom_reset)
        self.zoom_reset_btn = QPushButton()
        self.zoom_reset_btn.setObjectName("zoomButton")
        self.zoom_reset_btn.setToolTip("Reset Zoom (Ctrl+0)")
        self.zoom_reset_btn.setFixedSize(32, 32)
        if icon_path_zoom_reset:
            self.zoom_reset_btn.setIcon(QIcon(str(icon_path_zoom_reset)))
        else:
            self.zoom_reset_btn.setText("⟲")
        self.zoom_reset_btn.setIconSize(QSize(18, 18))
        self.zoom_reset_btn.clicked.connect(self.zoom_reset)
        zoom_layout.addWidget(self.zoom_reset_btn)
        self.icon_buttons.append((self.zoom_reset_btn, icon_name_zoom_reset))

        icon_name_zoom_in = "zoom-in"
        icon_path_zoom_in = self.get_icon_path(icon_name_zoom_in)
        self.zoom_in_btn = QPushButton()
        self.zoom_in_btn.setObjectName("zoomButton")
        self.zoom_in_btn.setToolTip("Zoom In (Ctrl++)")
        self.zoom_in_btn.setFixedSize(32, 32)
        if icon_path_zoom_in:
            self.zoom_in_btn.setIcon(QIcon(str(icon_path_zoom_in)))
        else:
            self.zoom_in_btn.setText("+")
        self.zoom_in_btn.setIconSize(QSize(18, 18))
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_layout.addWidget(self.zoom_in_btn)
        self.icon_buttons.append((self.zoom_in_btn, icon_name_zoom_in))

        log_layout.addWidget(zoom_toolbar)

        self.log_text = ZoomableTextEdit(self)
        self.log_text.setObjectName("logText")
        self.log_text.setReadOnly(True)
        min_font_size = max(9, self.log_font_size)
        self.log_text.setFont(QFont("Consolas", min_font_size))
        self.log_text.set_zoom_callbacks(self.zoom_in, self.zoom_out)
        screen = self.screen().availableGeometry()
        if screen.height() < 768:
            self.log_text.setMinimumHeight(150)
        else:
            self.log_text.setMinimumHeight(200)
        log_layout.addWidget(self.log_text)

        # The log pane used to grow without bound: a --verbose winetricks run
        # pushes thousands of lines, and painting one HTML block per message was
        # what made the GUI crawl. Cap what we keep on screen and paint in
        # batches every 100 ms (see _log_safe / _flush_log_queue).
        self.log_text.document().setMaximumBlockCount(5000)
        self._log_flush_timer = QTimer(self)
        self._log_flush_timer.setInterval(100)
        self._log_flush_timer.timeout.connect(self._flush_log_queue)
        self._log_flush_timer.start()

        card_layout.addWidget(log_section)

        self.update_zoom_buttons()

        return card

    def create_button_sections(self):
        """Create modern organized button sections (responsive)"""
        screen = self.screen().availableGeometry()
        screen_width = screen.width()

        if screen_width < 1024:
            container_spacing = 12
        elif screen_width < 1280:
            container_spacing = 14
        else:
            container_spacing = 16

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(container_spacing)
        container_layout.setContentsMargins(0, 0, 0, 0)

        quick_group = self.create_button_group(
            "Quick Start",
            [
                (
                    "One-Click Full Setup",
                    self.one_click_setup,
                    "Setup Wine, dependencies, and prepare for Affinity installation",
                    "rocket",
                ),
                (
                    "Setup Wine Environment",
                    self.setup_wine_environment,
                    "Download and configure Wine environment only",
                    "wine",
                ),
                (
                    "Install System Dependencies",
                    self.install_system_dependencies,
                    "Install required Linux packages",
                    "dependencies",
                ),
                (
                    "Install Winetricks Dependencies",
                    self.install_winetricks_deps,
                    "Install Windows components (.NET, fonts, etc.)",
                    "wand",
                ),
            ],
        )
        container_layout.addWidget(quick_group)

        sys_group = self.create_button_group(
            "System Setup",
            [
                (
                    "Download Affinity Installer",
                    self.download_affinity_installer,
                    "Download the latest Affinity installer from official source",
                    "download",
                ),
                (
                    "Install from File Manager",
                    self.install_from_file,
                    "Install Affinity or any Windows app from a local .exe file",
                    "folderopen",
                ),
                (
                    "GPU rendering",
                    self.enable_opencl_support,
                    "Set up vkd3d-proton (DXVK on AMD) so Affinity draws on your "
                    "graphics card; OpenCL too, on Wine older than 11.11",
                    "lightning",
                ),
            ],
        )
        container_layout.addWidget(sys_group)

        app_buttons = [
            (
                "Affinity (Unified)",
                "Add",
                "Update or install Affinity V3 unified application",
                "affinity-unified",
            ),
            (
                "Affinity Photo",
                "Photo",
                "Update or install Affinity Photo for image editing",
                "camera",
            ),
            (
                "Affinity Designer",
                "Designer",
                "Update or install Affinity Designer for vector graphics",
                "pen",
            ),
            (
                "Affinity Publisher",
                "Publisher",
                "Update or install Affinity Publisher for page layout",
                "book",
            ),
        ]
        app_group = self.create_button_group(
            "Update Affinity Applications",
            [
                (
                    text,
                    lambda name=app_name: self.update_application(name),
                    tooltip,
                    icon,
                )
                for text, app_name, tooltip, icon in app_buttons
            ],
            button_refs=self.update_buttons,
            button_keys=[app_name for _, app_name, _, _ in app_buttons],
        )
        container_layout.addWidget(app_group)

        launch_group = self.create_button_group(
            "Launch",
            [
                (
                    "Launch Affinity v3",
                    self.launch_affinity_v3,
                    "Start Affinity V3 unified application",
                    "play",
                ),
                (
                    "Launch Affinity v3 (Ubuntu Snapshot)",
                    self.launch_affinity_v3_ubuntu_snapshot,
                    "Start Affinity V3 using the preserved Ubuntu/KDE/Wayland/NVIDIA runtime path",
                    "play",
                ),
            ],
        )
        container_layout.addWidget(launch_group)

        other_group = self.create_button_group(
            "Other",
            [
                ("Exit", self.close, "Close the installer", "exit"),
            ],
        )
        container_layout.addWidget(other_group)

        container_layout.addStretch()

        return container

    def create_troubleshooting_sections(self):
        """Create the Troubleshooting and Patches button sections"""
        screen = self.screen().availableGeometry()
        screen_width = screen.width()

        if screen_width < 1024:
            container_spacing = 12
        elif screen_width < 1280:
            container_spacing = 14
        else:
            container_spacing = 16

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(container_spacing)
        container_layout.setContentsMargins(0, 0, 0, 0)

        troubleshoot_group = self.create_button_group(
            "Troubleshooting",
            [
                (
                    "Switch Wine Version",
                    self.switch_wine_version,
                    "Remove current Wine and install a different version (keeps your apps and settings)",
                    "wine",
                ),
                (
                    "Update Wine Version",
                    self.update_wine_version,
                    "Install a Wine version with the fixes a new install applies for it: "
                    "OpenCL setting, Windows Metadata, document handler, fonts (keeps your apps and settings)",
                    "wine",
                ),
                (
                    "Wine Configuration",
                    self.open_winecfg,
                    "Open Wine settings to configure Windows version and libraries",
                    "wine",
                ),
                (
                    "Winetricks",
                    self.open_winetricks,
                    "Install additional Windows components and dependencies",
                    "wand",
                ),
                (
                    "Set Windows 11 + Renderer",
                    self.set_windows11_renderer,
                    "Configure Windows version and graphics renderer (Vulkan/OpenGL)",
                    "windows",
                ),
                (
                    "GPU Selection",
                    self.configure_gpu_selection,
                    "Select which GPU to use for dual GPU setups",
                    "display",
                ),
                (
                    self.get_switch_backend_button_text(),
                    self.switch_graphics_backend,
                    self.get_switch_backend_tooltip(),
                    "lightning",
                ),
                (
                    "Reinstall WinMetadata",
                    self.reinstall_winmetadata,
                    "Fix corrupted Windows metadata files",
                    "loop",
                ),
                (
                    "File Manager Integration",
                    self.setup_file_manager_integration,
                    "Set up (or repair) opening documents by double-clicking them",
                    "loop",
                ),
                (
                    "Fix Canva Sign-in (v3)",
                    self.fix_canva_sign_in,
                    "Install the .NET WinRT facades and the affinity:// handler the Canva sign-in needs",
                    "wrench",
                ),
                (
                    "Paste Sign-in URL (v3)",
                    self.inject_canva_sign_in_callback,
                    "Manually hand the browser sign-in callback to Affinity when the automatic handoff does not complete",
                    "wrench",
                ),
                (
                    "WebView2 Runtime (v3)",
                    self.install_webview2_runtime,
                    "Install WebView2 for Affinity V3 Help system",
                    "chrome",
                ),
                (
                    "Fix Settings (v3)",
                    self.fix_affinity_settings,
                    "Patch Affinity v3 DLL to enable settings saving",
                    "cog",
                ),
                (
                    "Set DPI Scaling",
                    self.set_dpi_scaling,
                    "Adjust interface size for better readability",
                    "scale",
                ),
                (
                    "Uninstall",
                    self.uninstall_affinity_linux,
                    "Completely remove Affinity Linux installation",
                    "trash",
                ),
            ],
        )
        container_layout.addWidget(troubleshoot_group)

        patches_group = self.create_button_group(
            "Patches",
            [
                (
                    "Return Colors (v3)",
                    self.apply_return_colors,
                    "Restore colored icons in Affinity v3 (replaces monochrome icons with v2 colored icons). Requires .NET SDK 10.0+",
                    "wand",
                ),
                (
                    "Install AffinityPluginLoader",
                    self.install_affinity_plugin_loader,
                    "Download and install the latest AffinityPluginLoader + WineFix from GitHub. Also updates Affinity.desktop to launch via AffinityHook.exe",
                    "wand",
                ),
            ],
        )
        container_layout.addWidget(patches_group)

        container_layout.addStretch()

        return container

    def create_button_group(self, title, buttons, button_refs=None, button_keys=None):
        """Create a modern grouped button section (responsive)"""
        screen = self.screen().availableGeometry()
        screen_width = screen.width()

        if screen_width < 1024:
            card_spacing = 8
            card_margin = 12
            button_height = 40
            icon_size = 18
        elif screen_width < 1280:
            card_spacing = 10
            card_margin = 14
            button_height = 42
            icon_size = 20
        else:
            card_spacing = 12
            card_margin = 16
            button_height = 44
            icon_size = 22

        card = QFrame()
        card.setObjectName("buttonCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(card_spacing)
        card_layout.setContentsMargins(card_margin, 16, card_margin, card_margin)

        title_label = ElidedLabel(title)
        title_label.setObjectName("sectionTitle")
        self._section_title_labels.append((title_label, title))
        if screen_width < 1024:
            title_label.setStyleSheet(
                "font-size: 14px; font-weight: 600; background-color: transparent; border: none; padding: 0px;"
            )
        else:
            title_label.setStyleSheet(
                "background-color: transparent; border: none; padding: 0px;"
            )
        card_layout.addWidget(title_label)

        buttons_layout = QVBoxLayout()
        if screen_width < 1024:
            buttons_layout.setSpacing(6)
        else:
            buttons_layout.setSpacing(8)
        buttons_layout.setContentsMargins(0, 0, 0, 0)

        for idx, button_data in enumerate(buttons):
            tooltip = None
            icon_name = None
            if len(button_data) == 2:
                text, command = button_data
            elif len(button_data) == 3:
                text, command, tooltip = button_data
            elif len(button_data) == 4:
                text, command, tooltip, icon_name = button_data
            else:
                text, command = button_data[0], button_data[1]

            btn = ElidedActionButton(text)
            btn.setObjectName("actionButton")

            if text == "One-Click Full Setup":
                btn.setProperty("class", "primary")

            btn.clicked.connect(
                lambda checked=False, b=btn, cmd=command: self._handle_button_click(
                    b, cmd
                )
            )

            if icon_name:
                icon_path = self.get_icon_path(icon_name)
                if icon_path:
                    icon = QIcon(str(icon_path))
                    btn.setIcon(icon)
                    btn.setIconSize(QSize(icon_size, icon_size))
                    self.icon_buttons.append((btn, icon_name))

            if tooltip:
                btn.setToolTip(tooltip)
            else:
                # The label can be abbreviated when the window is narrow
                # (see ElidedActionButton); keep the full text reachable.
                btn.setToolTip(text)

            btn.setMinimumHeight(button_height)
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            buttons_layout.addWidget(btn)
            self._all_action_buttons.append(btn)

            if (
                button_refs is not None
                and button_keys is not None
                and idx < len(button_keys)
            ):
                button_refs[button_keys[idx]] = btn

            if text.startswith("Switch to"):
                self.switch_backend_button = btn

        card_layout.addLayout(buttons_layout)

        return card

    def _normalize_action_buttons(self):
        """Give all action buttons a uniform height and let them stretch to fill
        their panel so they grow/shrink with the window and are never clipped."""
        buttons = [b for b in self._all_action_buttons if b is not None]
        if not buttons:
            return
        try:
            max_h = max(b.sizeHint().height() for b in buttons)
            for b in buttons:
                b.setMinimumHeight(max_h)
                b.setMaximumHeight(max_h)
                b.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
                )
        except Exception:
            pass

    def _handle_button_click(self, button, command):
        """Record last clicked button and invoke the original command."""
        # Every action changes the prefix. A second click while one ran
        # started One-Click Full Setup twice, and the two runs unpacked Wine
        # over each other and deleted each other's download (2026-10-16).
        # Actions run in threads they start: one is running while it is marked
        # as an operation and a thread the click started is alive. Either alone
        # could stick (a path that skips end_operation(), a helper thread that
        # outlives the action) and lock every button.
        busy = self.operation_in_progress and any(
            t.is_alive() for t in getattr(self, "_action_threads", []))
        if busy:
            QMessageBox.information(
                self.dialog_parent(),
                "Still working",
                f"'{self.current_operation or 'The current action'}' is still running.\n\n"
                "Wait for it to finish, or cancel it first.",
            )
            return
        before = set(threading.enumerate())
        try:
            self._last_clicked_button = button
            command()
            self._action_threads = [t for t in threading.enumerate()
                                    if t not in before and t.is_alive()]
        except Exception as e:
            self._last_clicked_button = None
            self.log(f"Error executing command: {e}", "error")

    def _show_spinner_safe(self, button):
        """Replace the given button's icon with a rotating spinner (UI thread)."""
        try:
            if button is None or not isinstance(button, QPushButton):
                return
            if button in self._button_spinner_map:
                return
            current_size = button.iconSize()
            size = (
                max(16, max(current_size.width(), current_size.height()))
                if current_size.isValid()
                else max(20, button.sizeHint().height() - 6)
            )
            if self.theme == "mattscreative":
                color = QColor("#04BEEF")
            else:
                color = QColor("#8ff361") if self.dark_mode else QColor("#4caf50")
            state = {
                "angle": 0,
                "timer": QTimer(self),
                "orig_icon": button.icon(),
                "orig_size": current_size
                if current_size.isValid()
                else QSize(size, size),
                "size": size,
                "color": color,
            }

            def tick():
                state["angle"] = (state["angle"] - 30) % 360
                pm = QPixmap(state["size"], state["size"])
                pm.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pm)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                lw = max(2, int(state["size"] * 0.12))
                rect = pm.rect().adjusted(lw, lw, -lw, -lw)
                pen = QPen(state["color"])
                pen.setWidth(lw)
                painter.setPen(pen)
                start_angle = int(state["angle"] * 16)
                span_angle = int(270 * 16)
                painter.drawArc(rect, start_angle, span_angle)
                painter.end()
                button.setIcon(QIcon(pm))
                button.setIconSize(QSize(state["size"], state["size"]))

            t = state["timer"]
            t.setInterval(50)
            t.timeout.connect(tick)
            t.start()
            tick()
            self._button_spinner_map[button] = state
        except Exception:
            pass

    def _hide_spinner_safe(self, button):
        """Restore the button's original icon (UI thread)."""
        try:
            state = self._button_spinner_map.pop(button, None)
            if state is None:
                return
            timer = state.get("timer")
            if timer:
                try:
                    timer.stop()
                except Exception:
                    pass
            orig_icon = state.get("orig_icon")
            orig_size = state.get("orig_size")
            if isinstance(button, QPushButton):
                if orig_icon is not None:
                    button.setIcon(orig_icon)
                if orig_size is not None and orig_size.isValid():
                    button.setIconSize(orig_size)
        except Exception:
            pass

    def load_affinity_icon(self):
        """Load Affinity V3 icon (non-blocking - downloads in background if needed)"""
        self.affinity_icon_path = None

        def check_and_load_icon():
            try:
                icon_dir = Path.home() / ".local" / "share" / "icons"
                icon_dir.mkdir(parents=True, exist_ok=True)
                icon_path = icon_dir / "Affinity.svg"

                if icon_path.exists():
                    try:
                        with open(icon_path, "rb") as f:
                            first_bytes = f.read(100).decode("utf-8", errors="ignore")
                            if first_bytes.strip().startswith(
                                "<?xml"
                            ) or first_bytes.strip().startswith("<svg"):
                                self.affinity_icon_path = str(icon_path)
                                self.window_icon_signal.emit(str(icon_path))
                                return
                            else:
                                icon_path.unlink()
                    except Exception:
                        self.affinity_icon_path = str(icon_path)
                        self.window_icon_signal.emit(str(icon_path))
                        return

                try:
                    icon_url = "https://raw.githubusercontent.com/seapear/AffinityOnLinux/main/Assets/Icons/Affinity-Canva.svg"
                    urllib.request.urlretrieve(icon_url, str(icon_path))
                    self.affinity_icon_path = str(icon_path)
                    self.window_icon_signal.emit(str(icon_path))
                except Exception:
                    pass
            except Exception:
                pass

        threading.Thread(target=check_and_load_icon, daemon=True).start()

    def closeEvent(self, event):
        """Handle window close event - stop children, flush log, close file"""
        if self.operation_in_progress:
            reply = QMessageBox.question(
                self,
                "Operation In Progress",
                f"'{self.current_operation or 'Unknown'}' is still running.\n\n"
                "Quit anyway and stop the running process(es)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

            # Worker threads are daemons and every child gets its own session,
            # so without this a quit orphans winetricks/wine — exactly what
            # wedges the next run.
            self.operation_cancelled = True
            self.cancel_event.set()
            try:
                self.terminate_active_processes()
            except Exception:
                pass
            try:
                self.stop_prefix_wine_processes(
                    reason="installer is closing", wait_seconds=5, force=True
                )
            except Exception:
                pass

        try:
            self._flush_log_queue()
        except Exception:
            pass
        if self.log_file:
            try:
                log_footer = f"{'=' * 80}\n"
                log_footer += f"Session Ended: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                log_footer += f"{'=' * 80}\n\n"
                self.log_file.write(log_footer)
                self.log_file.close()
            except Exception:
                pass
        event.accept()

    def sanitize_filename(self, filename):
        """Sanitize filename by replacing spaces and other problematic characters"""
        sanitized = filename.replace(" ", "-")
        sanitized = sanitized.replace("(", "-").replace(")", "-")
        sanitized = sanitized.replace("[", "-").replace("]", "-")
        while "--" in sanitized:
            sanitized = sanitized.replace("--", "-")
        return sanitized

    def log(self, message, level="info"):
        """Add message to log (thread-safe via signal)"""
        self.log_signal.emit(message, level)

    def _get_system_specs(self):
        """Gather system specifications"""
        specs = []

        try:
            uname = platform.uname()
            specs.append(f"OS: {uname.system} {uname.release}")
            specs.append(f"Architecture: {uname.machine}")
        except Exception:
            pass

        try:
            distro_info = {}
            if Path("/etc/os-release").exists():
                with open("/etc/os-release", "r") as f:
                    for line in f:
                        if "=" in line:
                            key, value = line.strip().split("=", 1)
                            distro_info[key] = value.strip('"')
            if "PRETTY_NAME" in distro_info:
                specs.append(f"Distribution: {distro_info['PRETTY_NAME']}")
            elif "NAME" in distro_info:
                version = distro_info.get("VERSION_ID", "")
                specs.append(f"Distribution: {distro_info['NAME']} {version}".strip())
        except Exception:
            pass

        try:
            cpu_info = ""
            if Path("/proc/cpuinfo").exists():
                with open("/proc/cpuinfo", "r") as f:
                    cpu_info = f.read()

            if cpu_info:
                for line in cpu_info.split("\n"):
                    if "model name" in line.lower():
                        cpu_model = line.split(":", 1)[1].strip()
                        specs.append(f"CPU: {cpu_model}")
                        break

                cpu_count = cpu_info.count("processor")
                if cpu_count > 0:
                    specs.append(f"CPU Cores: {cpu_count}")
        except Exception:
            pass

        try:
            mem_info = ""
            if Path("/proc/meminfo").exists():
                with open("/proc/meminfo", "r") as f:
                    mem_info = f.read()

            if mem_info:
                for line in mem_info.split("\n"):
                    if line.startswith("MemTotal:"):
                        mem_kb = int(line.split()[1])
                        mem_gb = mem_kb / (1024 * 1024)
                        specs.append(f"RAM: {mem_gb:.1f} GB")
                        break
        except Exception:
            pass

        try:
            gpu_info = []
            if Path("/proc/driver/nvidia/version").exists():
                try:
                    with open("/proc/driver/nvidia/version", "r") as f:
                        nvidia_version = f.read().strip()
                        gpu_info.append(
                            f"NVIDIA Driver: {nvidia_version.split()[7] if len(nvidia_version.split()) > 7 else 'Detected'}"
                        )
                except Exception:
                    pass

            try:
                result = subprocess.run(
                    ["lspci"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout:
                    for line in result.stdout.split("\n"):
                        if (
                            "vga" in line.lower()
                            or "3d" in line.lower()
                            or "display" in line.lower()
                        ):
                            gpu_line = line.split(":", 2)[-1].strip()
                            if gpu_line:
                                gpu_info.append(f"GPU: {gpu_line}")
                                break
            except Exception:
                pass

            if gpu_info:
                specs.extend(gpu_info)
        except Exception:
            pass

        return specs

    def _init_log_file(self):
        """Initialize log file"""
        try:
            self.log_file = open(self.log_file_path, "a", encoding="utf-8")
            log_header = f"\n{'=' * 80}\n"
            log_header += f"Affinity Linux Installer - Session Started\n"
            log_header += f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            log_header += f"{'=' * 80}\n"
            self.log_file.write(log_header)
            self.log_file.flush()
        except Exception as e:
            self.log_file = None

    def _log_safe(self, message, level="info"):
        """Thread-safe log handler (called from main thread)"""
        timestamp = time.strftime("%H:%M:%S")

        if level == "error":
            icon = "❌"
            color = "#ff7b72"
            bg_color = "rgba(255, 123, 114, 0.1)"
            icon_color = "#ff7b72"
        elif level == "success":
            icon = "✔"
            color = "#6a9955"
            bg_color = "rgba(106, 153, 85, 0.1)"
            icon_color = "#6a9955"
        elif level == "warning":
            icon = "⚠️"
            color = "#cd9731"
            bg_color = "rgba(205, 151, 49, 0.1)"
            icon_color = "#cd9731"
        else:
            icon = "•"
            color = "#9cdcfe"
            bg_color = "transparent"
            icon_color = "#569cd6"

        message = message.replace("<", "&lt;").replace(">", "&gt;")

        timestamp_html = (
            f'<span style="color: #6c7886; font-weight: 500;">[{timestamp}]</span>'
        )
        icon_html = f'<span style="color: {icon_color}; font-weight: bold; font-size: 12px;">{icon}</span>'

        if level in ["error", "success", "warning"]:
            full_message = f'<div style="background-color: {bg_color}; padding: 4px 8px; margin: 2px 0; border-radius: 4px; border-left: 3px solid {icon_color};">{timestamp_html} {icon_html} <span style="color: {color};">{message}</span></div>'
        else:
            full_message = f'<div style="padding: 2px 4px; margin: 1px 0;">{timestamp_html} {icon_html} <span style="color: {color};">{message}</span></div>'

        # Queue instead of painting: one QTextEdit append + relayout per message
        # is what made verbose winetricks runs crawl. _flush_log_queue paints
        # them in batches; the file still receives every line immediately.
        with self._log_queue_lock:
            self._log_queue.append(full_message)

        if self.log_file:
            try:
                plain_message = f"[{timestamp}] [{level.upper()}] {message}"
                self.log_file.write(plain_message + "\n")
                self.log_file.flush()
            except Exception:
                pass

    def _flush_log_queue(self):
        """Paint every queued log line in one batch (GUI thread, 10 Hz)."""
        try:
            with self._log_queue_lock:
                if not self._log_queue:
                    return
                batch = "\n".join(self._log_queue)
                self._log_queue.clear()
        except Exception:
            return
        try:
            self.log_text.append(batch)
            self.log_text.verticalScrollBar().setValue(
                self.log_text.verticalScrollBar().maximum()
            )
        except Exception:
            pass

    def update_progress(self, value):
        """Update progress bar (thread-safe via signal)"""
        self.progress_signal.emit(value)

    def _update_progress_safe(self, value):
        """Thread-safe progress update handler (called from main thread)"""
        self.progress.setValue(int(value * 100))

    def _update_progress_text_safe(self, text):
        """Thread-safe progress text update handler (called from main thread)"""
        self.progress_label.setText(text)

    def update_progress_text(self, text):
        """Update progress label text (thread-safe via signal)"""
        self.progress_text_signal.emit(text)

    def cancel_operation(self):
        """Cancel the current operation with confirmation"""
        reply = QMessageBox.question(
            self,
            "Cancel Operation",
            f"Are you sure you want to cancel the current operation?\n\n"
            f"Operation: {self.current_operation or 'Unknown'}\n\n"
            f"Note: This may leave the installation in an incomplete state.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.operation_cancelled = True
            self.cancel_event.set()
            self.update_progress_text("Cancelling...")
            try:
                self.terminate_active_processes()
            except Exception:
                pass
            # Killing the winetricks process group still leaves wineserver and
            # its children behind; sweep them up off the GUI thread.
            threading.Thread(
                target=self.stop_prefix_wine_processes,
                kwargs={
                    "reason": "operation cancelled",
                    "wait_seconds": 10,
                    "force": True,
                },
                daemon=True,
            ).start()
            self.log(
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "warning",
            )
            self.log("⚠ Operation cancelled by user", "warning")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
                "warning",
            )
            self.update_progress_text("Operation cancelled")
            self.update_progress(0.0)
            self.cancel_btn.setVisible(False)
            self.operation_in_progress = False
            try:
                if self._operation_button is not None:
                    self.hide_spinner_signal.emit(self._operation_button)
            except Exception:
                pass

    def _set_cancel_button_visible_safe(self, visible):
        """Show/hide the cancel button (called from main thread via signal)"""
        if hasattr(self, "cancel_btn"):
            self.cancel_btn.setVisible(visible)

    def start_operation(self, operation_name):
        """Mark the start of an operation and show cancel button"""
        self.operation_cancelled = False
        self.cancel_event.clear()
        self.current_operation = operation_name
        self.operation_in_progress = True
        self.operation_clock_signal.emit(True)
        if self._last_clicked_button is not None:
            self._operation_button = self._last_clicked_button
            self.show_spinner_signal.emit(self._operation_button)
        self.cancel_button_signal.emit(True)

    def end_operation(self):
        """Mark the end of an operation: restore UI, reset progress, toggle cancel."""
        self.operation_in_progress = False
        self.current_operation = None
        self.operation_clock_signal.emit(False)
        self.cancel_button_signal.emit(False)
        if self._operation_button is not None:
            self.hide_spinner_signal.emit(self._operation_button)
            self._operation_button = None
            self._last_clicked_button = None
        self.update_progress(0.0)
        self.update_progress_text("Ready")

    @staticmethod
    def format_elapsed(seconds):
        """1:05, 12:34, 1:02:03"""
        seconds = int(seconds)
        h, rest = divmod(seconds, 3600)
        m, s = divmod(rest, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    def _operation_clock_safe(self, running):
        """Start the clock with an operation, stop it a moment after the last
        one ends. The installer's ends do not pair with its starts: One-Click
        Full Setup ends the Wine setup's own operation and goes on, so an end
        followed by a start within the settle is one run, timed as one."""
        if getattr(self, "timer_label", None) is None:
            return
        if running:
            self._clock_settle.stop()
            if self._clock_started is None:
                self._clock_started = (time.strftime("%H:%M:%S"), time.monotonic())
                self.timer_label.show()
                self._clock_tick.start()
            self._show_clock()
        elif self._clock_started is not None:
            self._clock_settle.start()

    def _show_clock(self):
        if self._clock_started is None:
            return
        started, t0 = self._clock_started
        self.timer_label.setText(
            f"Started {started} · Elapsed {self.format_elapsed(time.monotonic() - t0)}")

    def _stop_clock(self):
        if self._clock_started is None:
            return
        started, t0 = self._clock_started
        # Ended when the last operation ended, not when the settle ran out.
        took = self.format_elapsed(max(0, time.monotonic() - t0 - self._clock_settle.interval() / 1000))
        self._clock_tick.stop()
        self._clock_started = None
        self.timer_label.setText(f"Started {started} · Finished in {took}")
        self.log(f"Finished in {took} (started {started})", "info")

    def check_cancelled(self):
        """Check if operation was cancelled"""
        if self.operation_cancelled:
            self.end_operation()
            return True
        return False

    def dialog_parent(self):
        """The window this installer's dialogs belong to: its own, or the
        manager's when it is hosted there. A dialog without a parent is a
        window of its own, and on Wayland it can end up behind the main
        window while it still blocks it (a finished install sat there with an
        "Installation Complete" box nobody could see)."""
        return self.window()

    def show_message(self, title, message, msg_type="info"):
        """Show message box (thread-safe via signal)"""
        self.show_message_signal.emit(title, message, msg_type)

    def _set_window_icon_safe(self, icon_path):
        """Set window icon (called from main thread via signal)"""
        self.setWindowIcon(QIcon(icon_path))

    def _show_message_safe(self, title, message, msg_type="info"):
        """Thread-safe message box handler (called from main thread)"""
        msg_box = QMessageBox(self.dialog_parent())
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStyleSheet(self.get_messagebox_stylesheet())

        if msg_type == "error":
            msg_box.setIcon(QMessageBox.Icon.Critical)
        elif msg_type == "warning":
            msg_box.setIcon(QMessageBox.Icon.Warning)
        else:
            msg_box.setIcon(QMessageBox.Icon.Information)

        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.adjustSize()
        msg_box.exec()

    def _request_sudo_password_safe(self):
        """Request sudo password from user (called from main thread)"""
        dialog = QDialog(self.dialog_parent())
        dialog.setWindowTitle("Administrator Authentication Required")
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Responsive sizing - improved for all screen sizes
        screen = dialog.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        if screen_width < 800 or screen_height < 600:
            min_width = min(350, int(screen_width * 0.9))
            min_height = min(200, int(screen_height * 0.7))
            default_width = min(450, int(screen_width * 0.85))
            default_height = min(220, int(screen_height * 0.65))
            max_width = int(screen_width * 0.95)
            max_height = int(screen_height * 0.85)
        elif screen_width < 1280 or screen_height < 720:
            min_width = 400
            min_height = 200
            default_width = 500
            default_height = 240
            max_width = int(screen_width * 0.9)
            max_height = int(screen_height * 0.85)
        else:
            min_width = 400
            min_height = 200
            default_width = 500
            default_height = 240
            max_width = 700
            max_height = 500

        dialog.setMinimumWidth(min_width)
        dialog.setMinimumHeight(min_height)
        dialog.setMaximumWidth(max_width)
        dialog.setMaximumHeight(max_height)
        dialog.resize(default_width, default_height)
        dialog.setSizeGripEnabled(True)

        # Apply theme stylesheet
        dialog.setStyleSheet(self.get_dialog_stylesheet())

        # Main layout with responsive margins
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(12)
        margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
        main_layout.setContentsMargins(margin, margin, margin, margin)

        title_label = QLabel("Administrator Authentication Required")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(title_label)

        desc_label = QLabel(
            "This operation requires administrator privileges.\n\nPlease enter your password to continue:"
        )
        desc_label.setObjectName("descriptionLabel")
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(desc_label)

        password_input = QLineEdit()
        password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_input.setPlaceholderText("Enter your password")
        password_input.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(password_input)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Continue")
        ok_btn.setObjectName("okButton")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)

        main_layout.addLayout(button_layout)

        password_input.returnPressed.connect(dialog.accept)

        dialog.layout().activate()
        dialog.adjustSize()

        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        password_input.setFocus()

        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.sudo_password = password_input.text()
        else:
            self.sudo_password = None
        self.sudo_password_dialog_done = True

    def get_sudo_password(self):
        """Get sudo password from user (thread-safe)"""
        if self.sudo_password_validated and self.sudo_password:
            return self.sudo_password
        if not self.account_can_sudo():
            self.log("This account cannot use sudo, so no administrator password is "
                     "asked for; that step is skipped.", "warning")
            return None

        self.sudo_password = None
        self.sudo_password_dialog_done = False
        self.sudo_password_dialog_signal.emit()

        # Wait for the dialog to actually finish instead of giving up after a
        # fixed timeout. Aborting here while the dialog is still on screen
        # would report a correctly entered password as "authentication
        # cancelled" and could leave a second dialog open on retry.
        max_wait = 6000
        waited = 0
        while not self.sudo_password_dialog_done and waited < max_wait:
            time.sleep(0.1)
            waited += 1
            if self.cancel_event.is_set():
                break

        return self.sudo_password

    def validate_sudo_password(self, password):
        """Validate sudo password by running a test command"""
        try:
            env = os.environ.copy()
            env.pop("SUDO_ASKPASS", None)
            env["LANG"] = "C"
            env["LC_ALL"] = "C"

            process = subprocess.Popen(
                ["sudo", "-S", "true"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                preexec_fn=os.setsid,
            )

            try:
                stdout, stderr = process.communicate(input=f"{password}\n", timeout=15)
            except subprocess.TimeoutExpired:
                try:
                    if process.pid:
                        try:
                            pgid = os.getpgid(process.pid)
                            os.killpg(pgid, signal.SIGTERM)
                            time.sleep(0.5)
                            if process.poll() is None:
                                os.killpg(pgid, signal.SIGKILL)
                        except (ProcessLookupError, OSError, AttributeError):
                            process.kill()
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
                try:
                    process.communicate()
                except Exception:
                    pass
                self.log(
                    "Password validation timed out - sudo may be waiting for input",
                    "error",
                )
                self.sudo_password_validated = False
                return False
            except Exception as e:
                try:
                    if process.poll() is None:
                        process.wait(timeout=1)
                except Exception:
                    pass
                if process.returncode == 0:
                    self.sudo_password_validated = True
                    return True
                self.log(f"Error validating sudo password: {e}", "error")
                self.sudo_password_validated = False
                return False

            if process.returncode == 0:
                self.sudo_password_validated = True
                return True
            else:
                # Check stderr for more details
                if stderr:
                    error_msg = stderr.strip()
                    error_lower = error_msg.lower()
                    if "incorrect password" in error_lower or "sorry, try again" in error_lower:
                        self.log("Incorrect password", "error")
                    elif "tty" in error_lower or "terminal" in error_lower:
                        self.log(
                            "Password rejected by sudo because a terminal is "
                            f"required on this system: {error_msg}",
                            "error",
                        )
                    elif "no askpass" in error_lower or "no password" in error_lower:
                        self.log(
                            "Sudo could not authenticate without a password prompt "
                            f"helper: {error_msg}",
                            "error",
                        )
                    else:
                        self.log(f"Password validation failed: {error_msg}", "error")
                else:
                    self.log("Password validation failed", "error")
                self.sudo_password_validated = False
                return False
        except Exception as e:
            self.log(f"Error validating sudo password: {e}", "error")
            self.sudo_password_validated = False
            return False

    def _request_interactive_response_safe(self, prompt_text, default_response):
        """Request user response to interactive prompt (called from main thread)"""
        # Parse the prompt to determine type
        prompt_lower = prompt_text.lower()

        # Detect yes/no questions
        if any(
            pattern in prompt_lower
            for pattern in ["(y/n)", "[y/n]", "yes/no", "overwrite?"]
        ):
            # Extract default from prompt
            default_yes = "y" in default_response.lower() if default_response else False

            reply = QMessageBox.question(
                self,
                "User Input Required",
                prompt_text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
                if default_yes
                else QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.interactive_response = "y\n"
            else:
                self.interactive_response = "n\n"
        else:
            # For other prompts, use input dialog
            response, ok = QInputDialog.getText(
                self,
                "User Input Required",
                prompt_text,
                QLineEdit.EchoMode.Normal,
                default_response or "",
            )

            if ok:
                self.interactive_response = response + "\n"
            else:
                self.interactive_response = "\n"  # Empty response (just Enter)

        self.waiting_for_response = False

    def get_interactive_response(self, prompt_text, default_response=""):
        """Get user response to interactive prompt (thread-safe)"""
        self.interactive_response = None
        self.waiting_for_response = True
        self.interactive_prompt_signal.emit(prompt_text, default_response)

        # Wait for response with timeout
        max_wait = 300  # 30 seconds
        waited = 0
        while self.waiting_for_response and waited < max_wait:
            time.sleep(0.1)
            waited += 1

        return self.interactive_response or "\n"

    def _show_wine_version_dialog_safe(self):
        """Show professional Wine version selection dialog (called from main thread)"""
        dialog = QDialog(self.dialog_parent())
        dialog.setWindowTitle("Choose Wine Version")
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Responsive sizing - adapt to screen size and content
        # Get screen size to adjust sizes
        screen = dialog.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        # Calculate optimal sizes based on screen size
        # Account for 2 Wine version options now
        if screen_width < 800 or screen_height < 600:
            # Small screen - use smaller sizes
            min_width = min(400, int(screen_width * 0.9))
            min_height = min(350, int(screen_height * 0.7))
            default_width = min(500, int(screen_width * 0.85))
            default_height = min(450, int(screen_height * 0.65))
            max_width = int(screen_width * 0.95)
            max_height = int(screen_height * 0.85)
        elif screen_width < 1280 or screen_height < 720:
            # Medium screen
            min_width = 500
            min_height = 400
            default_width = 650
            default_height = 550
            max_width = int(screen_width * 0.9)
            max_height = int(screen_height * 0.85)
        else:
            # Large screen
            min_width = 550
            min_height = 450
            default_width = 700
            default_height = 600
            max_width = 900
            max_height = 800

        dialog.setMinimumWidth(min_width)
        dialog.setMinimumHeight(min_height)
        dialog.setMaximumWidth(max_width)
        dialog.setMaximumHeight(max_height)
        dialog.resize(default_width, default_height)

        # Make dialog resizable
        dialog.setSizeGripEnabled(True)

        # Apply theme stylesheet
        dark_style = """
                QDialog {
                    background-color: #252526;
                    color: #dcdcdc;
                }
                QLabel {
                    color: #dcdcdc;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4ec9b0;
                    padding: 10px 0px;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #cccccc;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                }
                QLabel#optionDescription {
                    font-size: 13px;
                    color: #b0b0b0;
                    padding: 4px 0px 0px 0px;
                    line-height: 1.5;
                }
                QFrame#optionFrame {
                    background-color: #2d2d2d;
                    border: 1px solid #3c3c3c;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #4a4a4a;
                    background-color: #323232;
                }
                QRadioButton {
                    font-size: 16px;
                    color: #dcdcdc;
                    padding: 8px 0px;
                    spacing: 10px;
                    font-weight: 500;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #555555;
                    background-color: #3c3c3c;
                }
                QRadioButton::indicator:hover {
                    border-color: #6a6a6a;
                }
                QRadioButton::indicator:checked {
                    background-color: #4ec9b0;
                    border-color: #4ec9b0;
                }
                QPushButton {
                    background-color: #3c3c3c;
                    color: #f0f0f0;
                    border: 1px solid #555555;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                    border-color: #6a6a6a;
                }
                QPushButton:pressed {
                    background-color: #2d2d2d;
                }
                QPushButton#okButton, QPushButton#installButton {
                    background-color: #4ec9b0;
                    color: #1e1e1e;
                    border: 1px solid #4ec9b0;
                    font-weight: bold;
                }
                QPushButton#okButton:hover, QPushButton#installButton:hover {
                    background-color: #5dd9c0;
                    border-color: #5dd9c0;
                }
                QPushButton#okButton:pressed, QPushButton#installButton:pressed {
                    background-color: #3db9a0;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background-color: #2d2d2d;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #555555;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #666666;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
        """
        if self.theme == "mattscreative":
            dialog_style = self._mattscreative_palette_style(dark_style)
        elif self.dark_mode:
            dialog_style = dark_style
        else:
            dialog_style = """
                QDialog {
                    background-color: #ffffff;
                    color: #2d2d2d;
                }
                QLabel {
                    color: #2d2d2d;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4caf50;
                    padding: 10px 0px;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #555555;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                }
                QLabel#optionDescription {
                    font-size: 12px;
                    color: #666666;
                    padding: 4px 0px 0px 0px;
                    line-height: 1.4;
                }
                QFrame#optionFrame {
                    background-color: #f5f5f5;
                    border: 1px solid #e0e0e0;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #c0c0c0;
                    background-color: #fafafa;
                }
                QRadioButton {
                    font-size: 16px;
                    color: #2d2d2d;
                    padding: 8px 0px;
                    spacing: 10px;
                    font-weight: 500;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #c0c0c0;
                    background-color: #ffffff;
                }
                QRadioButton::indicator:hover {
                    border-color: #a0a0a0;
                }
                QRadioButton::indicator:checked {
                    background-color: #4caf50;
                    border-color: #4caf50;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    color: #2d2d2d;
                    border: 1px solid #c0c0c0;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #d0d0d0;
                    border-color: #a0a0a0;
                }
                QPushButton:pressed {
                    background-color: #c0c0c0;
                }
                QPushButton#installButton {
                    background-color: #4caf50;
                    color: #ffffff;
                    border: 1px solid #4caf50;
                    font-weight: bold;
                }
                QPushButton#installButton:hover {
                    background-color: #45a049;
                    border-color: #45a049;
                }
                QPushButton#installButton:pressed {
                    background-color: #3d8b40;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background-color: #f5f5f5;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #c0c0c0;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #a0a0a0;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """

        dialog.setStyleSheet(dialog_style)

        # Main layout with responsive margins
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(12)
        # Responsive margins - smaller on small screens
        margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
        main_layout.setContentsMargins(margin, margin, margin, margin)

        # Title
        title_label = QLabel("Choose Wine Version")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(title_label)

        # Description
        desc_label = QLabel(
            "Select which Wine version you would like to install. "
            "You can switch versions later by running 'Setup Wine Environment' again."
        )
        desc_label.setObjectName("descriptionLabel")
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(desc_label)

        # Options container with scroll area for better scaling
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        options_container = QFrame()
        options_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        options_layout = QVBoxLayout(options_container)
        options_layout.setSpacing(8)
        options_margin = 8 if (screen_width >= 800 and screen_height >= 600) else 6
        options_layout.setContentsMargins(
            options_margin, options_margin, options_margin, options_margin
        )

        scroll_area.setWidget(options_container)

        # Create button group to ensure only one radio button is selected at a time
        button_group = QButtonGroup(dialog)

        # Wine 11.19 option - clean frame with radio button and description (Recommended)
        wine_1119_frame = QFrame()
        wine_1119_frame.setObjectName("optionFrame")
        wine_1119_layout = QVBoxLayout(wine_1119_frame)
        wine_1119_layout.setContentsMargins(12, 10, 12, 10)
        wine_1119_layout.setSpacing(6)
        wine_1119_radio = QRadioButton("Wine 11.19 (Recommended)")
        wine_1119_radio.setChecked(True)
        wine_1119_radio.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        wine_1119_layout.addWidget(wine_1119_radio)
        wine_1119_desc = QLabel(
            "Latest build with the full Affinity patch set: Direct2D throughput and brush-latency fixes, wined3d Vulkan presentation fixes, OpenCL event dispatcher, pen pressure, plus color, printing and login fixes."
        )
        wine_1119_desc.setObjectName("optionDescription")
        wine_1119_desc.setWordWrap(True)
        wine_1119_desc.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        wine_1119_layout.addWidget(wine_1119_desc)
        options_layout.addWidget(wine_1119_frame)
        button_group.addButton(wine_1119_radio, 0)

        # Wine 11.18 option - clean frame with radio button and description
        wine_1118_frame = QFrame()
        wine_1118_frame.setObjectName("optionFrame")
        wine_1118_layout = QVBoxLayout(wine_1118_frame)
        wine_1118_layout.setContentsMargins(12, 10, 12, 10)
        wine_1118_layout.setSpacing(6)
        wine_1118_radio = QRadioButton("Wine 11.18")
        wine_1118_radio.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        wine_1118_layout.addWidget(wine_1118_radio)
        wine_1118_desc = QLabel(
            "Previous build with the Affinity login fix and performance patches (D2D geometry cache, OpenCL cache, SDR white-level and printer mapping). Use if 11.19 has issues."
        )
        wine_1118_desc.setObjectName("optionDescription")
        wine_1118_desc.setWordWrap(True)
        wine_1118_desc.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        wine_1118_layout.addWidget(wine_1118_desc)
        options_layout.addWidget(wine_1118_frame)
        button_group.addButton(wine_1118_radio, 1)

        # Add scroll area to main layout with stretch factor
        main_layout.addWidget(scroll_area, 1)

        # Buttons - fixed at bottom, responsive sizing
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Continue")
        ok_btn.setObjectName("okButton")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)

        main_layout.addLayout(button_layout)

        # Ensure the dialog is large enough to show all content; clamp inside min/max.
        hint = dialog.sizeHint()
        target_w = min(max(default_width, hint.width()), max_width)
        target_h = min(max(default_height, hint.height()), max_height)
        target_w = max(target_w, min_width)
        target_h = max(target_h, min_height)
        dialog.resize(target_w, target_h)

        # Show dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        # Get result
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            if wine_1119_radio.isChecked():
                self.question_dialog_response = "Wine 11.19 (Recommended)"
            elif wine_1118_radio.isChecked():
                self.question_dialog_response = "Wine 11.18"
        else:
            # User cancelled - return "Cancel" to match expected format
            self.question_dialog_response = "Cancel"

        self.waiting_for_question_response = False

    def _show_question_dialog_safe(self, title, message, buttons):
        """Show question dialog (called from main thread)"""
        # Check if this is a Wine version selection dialog
        is_wine_version_dialog = (
            "Wine Version" in title
            or "Wine version" in title
            or any("Wine 11.18" in btn or "Wine 11.19" in btn for btn in buttons)
        )
        if is_wine_version_dialog:
            self._show_wine_version_dialog_safe()
            return

        # Convert button list to QMessageBox buttons
        qbuttons = QMessageBox.StandardButton.NoButton
        for btn in buttons:
            if btn == "Yes":
                qbuttons |= QMessageBox.StandardButton.Yes
            elif btn == "No":
                qbuttons |= QMessageBox.StandardButton.No
            elif btn == "Retry":
                qbuttons |= QMessageBox.StandardButton.Retry
            elif btn == "Cancel":
                qbuttons |= QMessageBox.StandardButton.Cancel

        # Create message box and apply theme
        msg_box = QMessageBox(self.dialog_parent())
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(qbuttons)
        default_button = {
            "Yes": QMessageBox.StandardButton.Yes,
            "No": QMessageBox.StandardButton.No,
            "Retry": QMessageBox.StandardButton.Retry,
            "Cancel": QMessageBox.StandardButton.Cancel,
        }.get(getattr(self, "question_dialog_default", None))
        if default_button is not None:
            msg_box.setDefaultButton(default_button)
        msg_box.setStyleSheet(self.get_messagebox_stylesheet())
        msg_box.adjustSize()
        reply = msg_box.exec()

        # Store response
        if reply == QMessageBox.StandardButton.Yes:
            self.question_dialog_response = "Yes"
        elif reply == QMessageBox.StandardButton.No:
            self.question_dialog_response = "No"
        elif reply == QMessageBox.StandardButton.Retry:
            self.question_dialog_response = "Retry"
        elif reply == QMessageBox.StandardButton.Cancel:
            self.question_dialog_response = "Cancel"
        else:
            self.question_dialog_response = "Cancel"

        self.waiting_for_question_response = False

    def show_question_dialog(self, title, message, buttons=["Yes", "No"], default_button=None):
        """Show question dialog (thread-safe). default_button names the button Enter selects."""
        self.question_dialog_response = None
        self.question_dialog_default = default_button
        self.waiting_for_question_response = True
        self.question_dialog_signal.emit(title, message, buttons)

        # Wait for response indefinitely - let user take all the time they need
        # Only exit if operation is actually cancelled by user (via cancel button)
        while self.waiting_for_question_response:
            # Check if operation was cancelled by user (not timeout)
            if self.operation_cancelled:
                self.waiting_for_question_response = False
                return "Cancel"
            time.sleep(0.1)

        return self.question_dialog_response or "Cancel"

    def detect_cpu_generation(self):
        """Detect CPU generation using the V1-V5 method based on CPU model name.

        Returns:
            str: CPU generation ("V1", "V2", "V3", "V4", "V5", or "Unknown")
            bool: True if CPU is older (V1, V2, V3)
        """
        try:
            # Read CPU info from /proc/cpuinfo
            cpu_info = ""
            if Path("/proc/cpuinfo").exists():
                with open("/proc/cpuinfo", "r") as f:
                    cpu_info = f.read()

            # Try lscpu as fallback
            if not cpu_info or "model name" not in cpu_info.lower():
                try:
                    success, stdout, _ = self.run_command(
                        ["lscpu"], check=False, capture=True
                    )
                    if success:
                        cpu_info = stdout
                except Exception:
                    pass

            if not cpu_info:
                return "Unknown", False

            cpu_info_lower = cpu_info.lower()

            # AMD Detection (Zen architecture) - check in order from newest to oldest to avoid false matches
            # V5: Zen 4 (2022-2023) - Ryzen 7000 (desktop), Ryzen 7040 (mobile)
            if any(
                x in cpu_info_lower for x in ["ryzen 7", "ryzen 7000", "ryzen 7040"]
            ):
                return "V5", False

            # V4: Zen 3 (2020-2021) and Zen 5 (2024-2025) - Ryzen 5000, Ryzen 9000, Ryzen AI 300
            if any(
                x in cpu_info_lower
                for x in [
                    "ryzen 5",
                    "ryzen 5000",
                    "ryzen 9",
                    "ryzen 9000",
                    "ryzen ai 300",
                ]
            ):
                return "V4", False

            # V3: Zen 2 (2019-2020) - Ryzen 3000 (desktop), Ryzen 4000U/H (mobile)
            # Check for 4000 series first (mobile), then 3000 desktop (but not 3000U)
            if any(x in cpu_info_lower for x in ["ryzen 4", "ryzen 4000"]):
                return "V3", True
            if "ryzen 3" in cpu_info_lower or "ryzen 3000" in cpu_info_lower:
                # Check if it's not V2 (3000U is V2)
                if "3000u" not in cpu_info_lower and "pro 3700u" not in cpu_info_lower:
                    return "V3", True

            # V2: Zen+ (2018-2019) - Ryzen 2000 (desktop), Ryzen 3000U (mobile)
            if any(x in cpu_info_lower for x in ["ryzen 3000u", "ryzen 7 pro 3700u"]):
                return "V2", True
            if "ryzen 2" in cpu_info_lower or "ryzen 2000" in cpu_info_lower:
                # Check if it's not V1 (2000U is V1, 2000 desktop is V2)
                if "2000u" not in cpu_info_lower:
                    return "V2", True

            # V1: Zen (2017) - Ryzen 1000 (desktop), Ryzen 2000U (mobile)
            if any(
                x in cpu_info_lower for x in ["ryzen 1", "ryzen 1000", "ryzen 2000u"]
            ):
                return "V1", True

            # Intel Detection
            # V1: Broadwell (5th Gen, 2014-2015) - i7-5600U, i5-5300U
            if any(x in cpu_info_lower for x in ["i7-5600", "i5-5300", "broadwell"]):
                return "V1", True

            # V2: Skylake (6th Gen, 2015-2016) - i7-6600U, i5-6200U
            if any(x in cpu_info_lower for x in ["i7-6600", "i5-6200", "skylake"]):
                return "V2", True

            # V3: Kaby Lake (7th Gen, 2016-2017), Coffee Lake (8th Gen, 2017-2018)
            # i7-7600U, i7-8650U
            if any(
                x in cpu_info_lower
                for x in ["i7-7600", "i7-8650", "kaby lake", "coffee lake"]
            ):
                return "V3", True

            # V4: Ice Lake (10th Gen, 2019), Tiger Lake (11th Gen, 2020), Meteor Lake / Arrow Lake (14th Gen, 2024-2025)
            # i7-1065G7, i7-1165G7, i7-14700K
            if any(
                x in cpu_info_lower
                for x in [
                    "i7-1065",
                    "i7-1165",
                    "i7-14700",
                    "ice lake",
                    "tiger lake",
                    "meteor lake",
                    "arrow lake",
                ]
            ):
                return "V4", False

            # V5: Alder Lake (12th Gen, 2021), Raptor Lake (13th Gen, 2022-2023)
            # i7-12700K, i7-13700K
            if any(
                x in cpu_info_lower
                for x in ["i7-12700", "i7-13700", "alder lake", "raptor lake"]
            ):
                return "V5", False

            # Try to detect by generation number in model name
            # Intel: Look for patterns like "Core i7-5xxx", "Core i5-6xxx", etc.
            intel_gen_match = re.search(
                r"core\s+i[357]-([0-9])([0-9]{3})", cpu_info_lower
            )
            if intel_gen_match:
                gen_digit = int(intel_gen_match.group(1))
                if gen_digit == 5:
                    return "V1", True
                elif gen_digit == 6:
                    return "V2", True
                elif gen_digit == 7:
                    return "V3", True
                elif gen_digit in [10, 11, 14]:
                    return "V4", False
                elif gen_digit in [12, 13]:
                    return "V5", False

            # AMD: Look for Ryzen model numbers
            amd_match = re.search(r"ryzen\s+([0-9])([0-9]{3})", cpu_info_lower)
            if amd_match:
                first_digit = int(amd_match.group(1))
                if first_digit == 1:
                    return "V1", True
                elif first_digit == 2:
                    # Could be V1 (2000U) or V2 (2000 desktop) - default to V2
                    return "V2", True
                elif first_digit == 3:
                    # Could be V2 (3000U) or V3 (3000 desktop) - check for U suffix
                    if "u" in cpu_info_lower or "pro 3700u" in cpu_info_lower:
                        return "V2", True
                    return "V3", True
                elif first_digit == 4:
                    return "V3", True
                elif first_digit == 5:
                    return "V4", False
                elif first_digit == 7:
                    return "V5", False
                elif first_digit == 9:
                    return "V4", False

            return "Unknown", False
        except Exception as e:
            self.log(f"Error detecting CPU generation: {e}", "warning")
            return "Unknown", False

    def get_wine_dir(self):
        """Get the Wine directory path"""
        return Path(self.directory) / "ElementalWarriorWine"

    def get_wine_path(self, binary="wine"):
        """Get the path to a Wine binary"""
        return self.get_wine_dir() / "bin" / binary

    def get_current_wine_version(self):
        """Get the current ElementalWarrior Wine version (11.18 or 11.19)"""
        # Try regular wine first
        wine = self.get_wine_path("wine")
        wine_staging = self.get_wine_path("wine-staging")

        # Check both wine and wine-staging binaries
        for wine_bin in [wine, wine_staging]:
            if wine_bin.exists():
                try:
                    success, stdout, _ = self.run_command(
                        [str(wine_bin), "--version"], check=False, capture=True
                    )
                    if success and stdout:
                        version_match = re.search(r"wine-(\d+\.\d+)", stdout)
                        if version_match:
                            version = version_match.group(1)
                            # Map actual Wine version to ElementalWarrior version
                            if version.startswith("9."):
                                return "9.14"
                            elif version.startswith("10."):
                                return "10.10"
                            elif version in ("11.16", "11.18", "11.19"):
                                return version
                            elif version.startswith("11."):
                                return version
                except Exception:
                    continue
        return None

    def get_wine_tkg_for_installer(self, binary="wine"):
        """Get wine-tkg binary path for running installers, fallback to regular wine or wine-staging if not available"""
        wine_tkg_bin = self.get_wine_tkg_path(binary)
        if (
            wine_tkg_bin
            and wine_tkg_bin.exists()
            and self._wine_binary_is_functional(wine_tkg_bin)
        ):
            return str(wine_tkg_bin)

        # Fallback to regular wine
        wine_bin = self.get_wine_path(binary)
        if wine_bin.exists():
            return str(wine_bin)

        # Final fallback to wine-staging
        wine_staging_bin = self.get_wine_path(f"{binary}-staging")
        if wine_staging_bin.exists():
            return str(wine_staging_bin)

        # Ultimate fallback: distro/system-installed wine, if present on PATH
        system_wine = shutil.which(binary)
        if system_wine:
            return system_wine

        return str(wine_bin)

    def _wine_binary_is_functional(self, wine_bin):
        """Run a quick smoke test (`wine --version`) to verify a Wine binary
        actually runs, rather than just checking that the file exists on disk.
        A wine-tkg download can be present but still fail at runtime — e.g. a
        corrupted archive, an incompatible glibc, or missing shared libraries —
        and an exists() check alone won't catch that."""
        try:
            result = subprocess.run(
                [str(wine_bin), "--version"],
                capture_output=True,
                timeout=15,
            )
            return result.returncode == 0
        except Exception as e:
            self.log(f"wine-tkg smoke test failed for {wine_bin}: {e}", "warning")
            return False

    def _pin_system_wine_in_env(self, env):
        """Explicitly locate the distro-installed system wine and put it at the
        front of PATH, rather than silently hoping whatever wine happens to be
        inherited in the environment is a working one. Used as the fallback
        when wine-tkg is missing or fails its functional check."""
        system_wine = shutil.which("wine", path=env.get("PATH"))
        if not system_wine:
            for candidate in ("/usr/bin/wine", "/usr/local/bin/wine", "/bin/wine"):
                if Path(candidate).exists():
                    system_wine = candidate
                    break

        if system_wine:
            self.log(f"Using system wine: {system_wine}", "info")
            system_wine_dir = str(Path(system_wine).parent)
            current_path = env.get("PATH", "")
            env["PATH"] = f"{system_wine_dir}:{current_path}"
        else:
            self.log(
                "✗ No working wine-tkg and no system wine found either — "
                "winetricks will likely fail. Please install your distro's "
                "'wine' package.",
                "error",
            )
        return env

    def get_wine_tkg_dir(self):
        """Get the wine-tkg directory path"""
        return Path(self.directory) / "wine-tkg"

    def get_wine_tkg_path(self, binary="wine"):
        """Get the path to a wine-tkg binary"""
        self.log(f"DEBUG: get_wine_tkg_path() called for binary: {binary}", "info")
        wine_tkg_dir = self.get_wine_tkg_dir()
        self.log(f"DEBUG: wine-tkg directory: {wine_tkg_dir}", "info")

        if not wine_tkg_dir.exists():
            self.log(
                f"DEBUG: wine-tkg directory does not exist: {wine_tkg_dir}", "info"
            )
            return None

        self.log(f"DEBUG: Checking for binary: {binary}", "info")

        # Check if binary exists directly in wine_tkg_dir/bin/ (direct extraction)
        direct_path = wine_tkg_dir / "bin" / binary
        self.log(f"DEBUG: Checking direct path: {direct_path}", "info")
        if direct_path.exists():
            self.log(f"DEBUG: ✓ Found binary at direct path: {direct_path}", "info")
            return direct_path
        else:
            self.log(f"DEBUG: ✗ Direct path does not exist", "info")

        # Check if it's in a subdirectory (like wine-10.19-staging-amd64/bin/wine)
        self.log(f"DEBUG: Checking subdirectories...", "info")
        try:
            subdirs = list(wine_tkg_dir.iterdir())
            self.log(f"DEBUG: Found {len(subdirs)} items in wine-tkg directory", "info")

            for subdir in subdirs:
                if subdir.is_dir():
                    self.log(f"DEBUG:   Checking subdirectory: {subdir.name}", "info")

                    # Check subdir/bin/binary
                    subdir_bin = subdir / "bin" / binary
                    self.log(f"DEBUG:     Checking: {subdir_bin}", "info")
                    if subdir_bin.exists():
                        self.log(f"DEBUG: ✓ Found binary at: {subdir_bin}", "info")
                        return subdir_bin

                    # Also check if bin is directly in subdir (some archives might have different structure)
                    subdir_direct = subdir / binary
                    self.log(f"DEBUG:     Checking direct: {subdir_direct}", "info")
                    if subdir_direct.exists():
                        self.log(f"DEBUG: ✓ Found binary at: {subdir_direct}", "info")
                        return subdir_direct
        except Exception as e:
            self.log(f"DEBUG: Error iterating subdirectories: {e}", "warning")

        # Last resort: recursive search for the binary (but limit depth to avoid performance issues)
        self.log(f"DEBUG: Performing recursive search for '{binary}'...", "info")
        try:
            found_paths = []
            for path in wine_tkg_dir.rglob(binary):
                if path.is_file() and path.name == binary:
                    found_paths.append(path)
                    # Make sure it's executable or at least looks like a binary
                    try:
                        is_executable = path.stat().st_mode & 0o111
                        has_no_suffix = path.suffix == ""
                        if is_executable or has_no_suffix:
                            self.log(
                                f"DEBUG: ✓ Found binary via recursive search: {path}",
                                "info",
                            )
                            return path
                        else:
                            self.log(
                                f"DEBUG:   Found '{binary}' but not executable: {path}",
                                "info",
                            )
                    except Exception as e:
                        self.log(f"DEBUG:   Error checking file {path}: {e}", "warning")

            if found_paths:
                self.log(
                    f"DEBUG: Found {len(found_paths)} files named '{binary}' but none are valid binaries",
                    "info",
                )
                for p in found_paths[:5]:
                    self.log(f"DEBUG:   - {p}", "info")
        except Exception as e:
            self.log(f"DEBUG: Error during recursive search: {e}", "warning")

        self.log(f"DEBUG: ✗ Binary '{binary}' not found in wine-tkg directory", "info")
        return None

    def _debug_log(self, message, level="info"):
        """Debug logging helper - prints to stderr (unbuffered) AND logs to UI/file AND debug file"""
        # Use stderr which is unbuffered and more reliable for GUI apps
        sys.stderr.write(f"[DEBUG] {message}\n")
        sys.stderr.flush()  # Force immediate output

        # Also write to a debug log file
        debug_log_path = Path.home() / "wine-tkg-debug.log"
        try:
            with open(debug_log_path, "a", encoding="utf-8") as f:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] {message}\n")
                f.flush()
        except Exception:
            pass  # Don't fail if we can't write to debug file

        self.log(f"DEBUG: {message}", level)

    def ensure_wine_tkg(self):
        """Download and extract wine-tkg if not already present"""
        # Print to stderr as backup (visible in terminal, unbuffered)
        sys.stderr.write("\n" + "=" * 80 + "\n")
        sys.stderr.write("DEBUG: Starting wine-tkg setup process\n")
        sys.stderr.write("=" * 80 + "\n")
        sys.stderr.flush()

        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "info",
        )
        self.log("DEBUG: Starting wine-tkg setup process", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "info",
        )

        # Step 1: Get directory paths
        self._debug_log("Step 1 - Getting directory paths")
        wine_tkg_dir = self.get_wine_tkg_dir()
        self._debug_log(f"wine-tkg directory: {wine_tkg_dir}")
        self._debug_log(f"wine-tkg directory exists: {wine_tkg_dir.exists()}")

        # Step 2: Check if already extracted
        self._debug_log("Step 2 - Checking if wine-tkg is already available")
        wine_tkg_bin = self.get_wine_tkg_path("wine")
        self._debug_log(f"wine-tkg binary path: {wine_tkg_bin}")

        if wine_tkg_bin:
            exists = wine_tkg_bin.exists()
            self._debug_log(f"wine-tkg binary exists check: {exists}")
            if exists:
                self._debug_log(
                    f"✓ wine-tkg is already available at: {wine_tkg_bin}", "success"
                )
                return True
            else:
                self._debug_log(
                    f"✗ wine-tkg path exists but file not found: {wine_tkg_bin}",
                    "warning",
                )
        else:
            self._debug_log("wine-tkg binary not found, will download and extract")

        # Step 3: Setup download parameters — fetch latest release from GitHub
        self.log("DEBUG: Step 3 - Setting up download parameters", "info")
        self.log("Fetching latest wine-tkg version from GitHub...", "info")
        wine_tkg_version = None
        try:
            api_url = "https://api.github.com/repos/Kron4ek/Wine-Builds/releases/latest"
            req = urllib.request.Request(api_url)
            req.add_header("User-Agent", "AffinityLinuxInstaller")
            with urllib.request.urlopen(req, timeout=15) as resp:
                release_data = json.loads(resp.read().decode())
            wine_tkg_version = release_data.get("tag_name", "").lstrip("v")
            if wine_tkg_version:
                self.log(f"Latest wine-tkg version: {wine_tkg_version}", "info")
            else:
                self.log(
                    "Could not parse version from GitHub API, falling back to 11.0",
                    "warning",
                )
                wine_tkg_version = "11.0"
        except Exception as e:
            self.log(
                f"Failed to fetch latest wine-tkg version: {e} — falling back to 11.0",
                "warning",
            )
            wine_tkg_version = "11.0"

        wine_tkg_filename = f"wine-{wine_tkg_version}-staging-tkg-amd64-wow64.tar.xz"
        wine_tkg_url = f"https://github.com/Kron4ek/Wine-Builds/releases/download/{wine_tkg_version}/{wine_tkg_filename}"
        wine_tkg_file = wine_tkg_dir / wine_tkg_filename
        self.log(f"DEBUG: Download URL: {wine_tkg_url}", "info")
        self.log(f"DEBUG: Target file: {wine_tkg_file}", "info")

        # Step 4: Create directory
        self.log("DEBUG: Step 4 - Creating wine-tkg directory", "info")
        try:
            wine_tkg_dir.mkdir(parents=True, exist_ok=True)
            self.log(f"DEBUG: ✓ Directory created/verified: {wine_tkg_dir}", "info")
            self.log(
                f"DEBUG: Directory exists after creation: {wine_tkg_dir.exists()}",
                "info",
            )
        except Exception as e:
            error_msg = f"Failed to create wine-tkg directory: {e}"
            sys.stderr.write(f"ERROR: {error_msg}\n")
            sys.stderr.write(f"Error type: {type(e).__name__}\n")
            import traceback

            sys.stderr.write(f"Traceback:\n{traceback.format_exc()}\n")
            sys.stderr.flush()
            self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
            self.log(f"DEBUG: Error type: {type(e).__name__}", "error")
            self.log(f"DEBUG: Traceback:\n{traceback.format_exc()}", "error")
            return False

        # Step 5: Check if file already exists
        self.log("DEBUG: Step 5 - Checking if archive file already exists", "info")
        if wine_tkg_file.exists():
            file_size = wine_tkg_file.stat().st_size
            self.log(
                f"DEBUG: Archive file already exists, size: {file_size} bytes", "info"
            )
            if file_size == 0:
                self.log("DEBUG: Archive file is empty, will re-download", "warning")
                try:
                    wine_tkg_file.unlink()
                    self.log("DEBUG: ✓ Empty file removed", "info")
                except Exception as e:
                    self.log(f"DEBUG: ✗ Failed to remove empty file: {e}", "error")
            else:
                self.log(
                    "DEBUG: Archive file exists and has content, will use it", "info"
                )
        else:
            self.log("DEBUG: Archive file does not exist, will download", "info")

        # Step 6: Download wine-tkg
        self.log("DEBUG: Step 6 - Downloading wine-tkg archive", "info")
        self.log("Downloading wine-tkg...", "info")
        sys.stderr.write(f"\n[WINE-TKG] Starting download from: {wine_tkg_url}\n")
        sys.stderr.write(f"[WINE-TKG] Saving to: {wine_tkg_file}\n")
        sys.stderr.flush()
        try:
            download_result = self.download_file(
                wine_tkg_url, str(wine_tkg_file), "wine-tkg"
            )
            sys.stderr.write(f"[WINE-TKG] Download result: {download_result}\n")
            sys.stderr.flush()
            self.log(f"DEBUG: Download result: {download_result}", "info")
        except Exception as e:
            error_msg = f"Exception during download: {e}"
            sys.stderr.write(f"[WINE-TKG] ERROR: {error_msg}\n")
            import traceback

            sys.stderr.write(f"[WINE-TKG] Traceback:\n{traceback.format_exc()}\n")
            sys.stderr.flush()
            self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
            download_result = False

        if not download_result:
            error_msg = "Failed to download wine-tkg archive"
            sys.stderr.write(f"\nERROR: {error_msg}\n")
            sys.stderr.write("Possible causes:\n")
            sys.stderr.write(f"  - Network connectivity issues\n")
            sys.stderr.write(f"  - URL may be invalid or changed: {wine_tkg_url}\n")
            sys.stderr.write(f"  - Insufficient disk space\n")
            sys.stderr.write(
                f"  - Permission denied writing to: {wine_tkg_file.parent}\n"
            )
            if wine_tkg_file.exists():
                file_size = wine_tkg_file.stat().st_size
                sys.stderr.write(
                    f"  - Partial file exists with size: {file_size} bytes\n"
                )
            sys.stderr.flush()
            self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
            self.log(f"DEBUG: Possible causes:", "error")
            self.log(f"DEBUG:   - Network connectivity issues", "error")
            self.log(
                f"DEBUG:   - URL may be invalid or changed: {wine_tkg_url}", "error"
            )
            self.log(f"DEBUG:   - Insufficient disk space", "error")
            self.log(
                f"DEBUG:   - Permission denied writing to: {wine_tkg_file.parent}",
                "error",
            )
            if wine_tkg_file.exists():
                file_size = wine_tkg_file.stat().st_size
                self.log(
                    f"DEBUG:   - Partial file exists with size: {file_size} bytes",
                    "error",
                )
            return False

        # Verify download
        if wine_tkg_file.exists():
            file_size = wine_tkg_file.stat().st_size
            self.log(
                f"DEBUG: ✓ Download completed, file size: {file_size} bytes", "info"
            )
            if file_size == 0:
                error_msg = "Downloaded file is empty"
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(
                    f"DEBUG: Cause: Download completed but file has 0 bytes", "error"
                )
                return False
        else:
            error_msg = "Download reported success but file not found"
            self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
            self.log(f"DEBUG: Cause: File should exist at: {wine_tkg_file}", "error")
            return False

        if self.check_cancelled():
            self.log("DEBUG: Operation cancelled by user", "warning")
            return False

        # Step 7: Extract wine-tkg
        self.log("DEBUG: Step 7 - Extracting wine-tkg archive", "info")
        self.update_progress_text("Extracting wine-tkg...")
        self.log("Extracting wine-tkg...", "info")

        extraction_success = False
        extraction_method = None

        # Try Python lzma module first
        self.log(
            "DEBUG: Step 7a - Attempting extraction with Python lzma module", "info"
        )
        try:
            import lzma

            self.log("DEBUG: ✓ lzma module available", "info")

            try:
                self.log("DEBUG: Opening xz file with lzma...", "info")
                with lzma.open(wine_tkg_file, "rb") as xz_file:
                    self.log("DEBUG: ✓ xz file opened successfully", "info")

                    self.log("DEBUG: Opening tar archive...", "info")
                    with tarfile.open(fileobj=xz_file, mode="r") as tar:
                        self.log("DEBUG: ✓ tar archive opened successfully", "info")

                        # Check archive structure
                        self.log("DEBUG: Analyzing archive structure...", "info")
                        members = tar.getmembers()
                        self.log(
                            f"DEBUG: Archive contains {len(members)} entries", "info"
                        )
                        if members:
                            first_member = members[0].name
                            self.log(f"DEBUG: First entry: '{first_member}'", "info")
                            # Show first few entries
                            for i, member in enumerate(members[:5]):
                                self.log(
                                    f"DEBUG:   Entry {i + 1}: {member.name} ({member.size} bytes)",
                                    "info",
                                )

                        # Try with filter='data' first (Python 3.12+)
                        self.log(
                            "DEBUG: Attempting extraction with filter='data' (Python 3.12+)...",
                            "info",
                        )
                        try:
                            tar.extractall(wine_tkg_dir, filter="data")
                            extraction_success = True
                            extraction_method = "Python lzma with filter='data'"
                            self.log(
                                "DEBUG: ✓ Extraction successful with filter='data'",
                                "info",
                            )
                        except TypeError as e:
                            self.log(f"DEBUG: filter='data' not supported: {e}", "info")
                            self.log(
                                "DEBUG: Attempting extraction without filter (older Python)...",
                                "info",
                            )
                            tar.extractall(wine_tkg_dir)
                            extraction_success = True
                            extraction_method = "Python lzma without filter"
                            self.log(
                                "DEBUG: ✓ Extraction successful without filter", "info"
                            )
            except Exception as e:
                error_msg = f"Error during extraction with lzma: {e}"
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(f"DEBUG: Error type: {type(e).__name__}", "error")
                import traceback

                self.log(f"DEBUG: Traceback:\n{traceback.format_exc()}", "error")

        except ImportError:
            self.log("DEBUG: ✗ lzma module not available, will use xz command", "info")
            extraction_method = None

        # Fallback to xz command if lzma module not available or extraction failed
        if not extraction_success:
            self.log("DEBUG: Step 7b - Attempting extraction with xz command", "info")

            # Check for xz command
            xz_available = self.check_command("xz")
            unxz_available = self.check_command("unxz")
            self.log(f"DEBUG: xz command available: {xz_available}", "info")
            self.log(f"DEBUG: unxz command available: {unxz_available}", "info")

            if not xz_available and not unxz_available:
                error_msg = "Neither xz nor unxz command is available"
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(
                    f"DEBUG: Cause: Required for extracting .tar.xz files when Python lzma module is unavailable",
                    "error",
                )
                self.log(
                    f"DEBUG: Solution: Install xz package (e.g., 'sudo pacman -S xz' or 'sudo apt install xz-utils')",
                    "error",
                )
                return False

            xz_cmd = "xz" if xz_available else "unxz"
            self.log(f"DEBUG: Using command: {xz_cmd}", "info")

            # Decompress with xz
            tar_file = wine_tkg_file.with_suffix(".tar")
            self.log(f"DEBUG: Decompressing to: {tar_file}", "info")

            success, stdout, stderr = self.run_command(
                [xz_cmd, "-d", "-k", str(wine_tkg_file)], check=True
            )
            self.log(f"DEBUG: Decompression result: success={success}", "info")
            if stdout:
                self.log(f"DEBUG: Decompression stdout: {stdout[:200]}", "info")
            if stderr:
                self.log(f"DEBUG: Decompression stderr: {stderr[:200]}", "info")

            if not success:
                error_msg = "Failed to decompress wine-tkg archive with xz"
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(
                    f"DEBUG: Cause: xz command failed to decompress the archive",
                    "error",
                )
                if stderr:
                    self.log(f"DEBUG: Error output: {stderr}", "error")
                return False

            if not tar_file.exists():
                error_msg = "Decompression reported success but tar file not found"
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(f"DEBUG: Cause: Expected tar file at: {tar_file}", "error")
                return False

            tar_size = tar_file.stat().st_size
            self.log(
                f"DEBUG: ✓ Decompression successful, tar file size: {tar_size} bytes",
                "info",
            )

            # Extract tar file
            self.log("DEBUG: Extracting tar archive...", "info")
            try:
                with tarfile.open(tar_file, "r") as tar:
                    self.log("DEBUG: ✓ tar file opened successfully", "info")

                    members = tar.getmembers()
                    self.log(f"DEBUG: Archive contains {len(members)} entries", "info")

                    try:
                        tar.extractall(wine_tkg_dir, filter="data")
                        extraction_success = True
                        extraction_method = "xz command + tar with filter='data'"
                        self.log(
                            "DEBUG: ✓ Extraction successful with filter='data'", "info"
                        )
                    except TypeError:
                        tar.extractall(wine_tkg_dir)
                        extraction_success = True
                        extraction_method = "xz command + tar without filter"
                        self.log(
                            "DEBUG: ✓ Extraction successful without filter", "info"
                        )
            except Exception as e:
                error_msg = f"Error extracting tar file: {e}"
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(f"DEBUG: Error type: {type(e).__name__}", "error")
                import traceback

                self.log(f"DEBUG: Traceback:\n{traceback.format_exc()}", "error")
                return False

            # Clean up intermediate tar file
            if tar_file.exists():
                try:
                    tar_file.unlink()
                    self.log("DEBUG: ✓ Intermediate tar file cleaned up", "info")
                except Exception as e:
                    self.log(
                        f"DEBUG: Warning: Failed to clean up tar file: {e}", "warning"
                    )

        if not extraction_success:
            error_msg = "Extraction did not complete successfully"
            sys.stderr.write(f"\nERROR: {error_msg}\n")
            sys.stderr.write("Cause: All extraction methods failed\n")
            sys.stderr.flush()
            self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
            self.log(f"DEBUG: Cause: All extraction methods failed", "error")
            return False

        self.log(
            f"DEBUG: ✓ Extraction completed using method: {extraction_method}", "info"
        )

        # Step 8: Clean up archive file
        self.log("DEBUG: Step 8 - Cleaning up archive file", "info")
        if wine_tkg_file.exists():
            try:
                wine_tkg_file.unlink()
                self.log("DEBUG: ✓ Archive file cleaned up", "info")
            except Exception as e:
                self.log(
                    f"DEBUG: Warning: Failed to clean up archive file: {e}", "warning"
                )

        # Step 9: Verify extraction
        self.log("DEBUG: Step 9 - Verifying extraction", "info")
        self.log(f"DEBUG: Checking extraction directory: {wine_tkg_dir}", "info")

        if not wine_tkg_dir.exists():
            error_msg = "Extraction directory does not exist after extraction"
            self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
            self.log(
                f"DEBUG: Cause: Directory was removed or never created: {wine_tkg_dir}",
                "error",
            )
            return False

        # List extracted contents
        try:
            contents = list(wine_tkg_dir.iterdir())
            self.log(
                f"DEBUG: Extracted directory contains {len(contents)} items", "info"
            )
            for i, item in enumerate(contents[:10]):  # Show first 10 items
                item_type = "directory" if item.is_dir() else "file"
                size = f" ({item.stat().st_size} bytes)" if item.is_file() else ""
                self.log(
                    f"DEBUG:   Item {i + 1}: {item.name} ({item_type}){size}", "info"
                )
            if len(contents) > 10:
                self.log(f"DEBUG:   ... and {len(contents) - 10} more items", "info")
        except Exception as e:
            self.log(
                f"DEBUG: Warning: Failed to list directory contents: {e}", "warning"
            )

        # Step 10: Find wine binary
        self.log("DEBUG: Step 10 - Searching for wine binary", "info")
        wine_tkg_bin = self.get_wine_tkg_path("wine")
        self.log(f"DEBUG: get_wine_tkg_path() returned: {wine_tkg_bin}", "info")

        if wine_tkg_bin:
            if wine_tkg_bin.exists():
                self.log(f"DEBUG: ✓ wine binary found at: {wine_tkg_bin}", "success")
                # Verify it's executable
                try:
                    is_executable = wine_tkg_bin.stat().st_mode & 0o111
                    self.log(
                        f"DEBUG: Binary is executable: {bool(is_executable)}", "info"
                    )
                    if not is_executable:
                        self.log(
                            "DEBUG: Warning: Binary is not executable, attempting to make it executable...",
                            "warning",
                        )
                        try:
                            wine_tkg_bin.chmod(0o755)
                            self.log("DEBUG: ✓ Made binary executable", "info")
                        except Exception as e:
                            self.log(
                                f"DEBUG: Warning: Failed to make executable: {e}",
                                "warning",
                            )
                except Exception as e:
                    self.log(
                        f"DEBUG: Warning: Could not check executable bit: {e}",
                        "warning",
                    )

                self.log(
                    f"wine-tkg extracted successfully at: {wine_tkg_bin}", "success"
                )
                return True
            else:
                error_msg = (
                    f"wine binary path exists but file not found: {wine_tkg_bin}"
                )
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(
                    f"DEBUG: Cause: Path was returned but file does not exist", "error"
                )
        else:
            error_msg = "wine binary not found after extraction"
            sys.stderr.write(f"\nERROR: {error_msg}\n")
            sys.stderr.write("Cause: get_wine_tkg_path() returned None\n")
            sys.stderr.flush()
            self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
            self.log(f"DEBUG: Cause: get_wine_tkg_path() returned None", "error")

        # Detailed search for debugging
        sys.stderr.write("\nPerforming detailed search for wine binary...\n")
        sys.stderr.write(f"Expected locations:\n")
        sys.stderr.write(f"  1. {wine_tkg_dir / 'bin' / 'wine'}\n")
        sys.stderr.write(f"  2. {wine_tkg_dir}/*/bin/wine (subdirectory)\n")
        sys.stderr.flush()
        self.log("DEBUG: Performing detailed search for wine binary...", "info")
        self.log(f"DEBUG: Expected locations:", "info")
        self.log(f"DEBUG:   1. {wine_tkg_dir / 'bin' / 'wine'}", "info")
        self.log(f"DEBUG:   2. {wine_tkg_dir}/*/bin/wine (subdirectory)", "info")

        # Search for any wine-related files
        wine_files_found = []
        try:
            for item in wine_tkg_dir.rglob("*"):
                if item.is_file() and "wine" in item.name.lower():
                    wine_files_found.append(item)
                    if len(wine_files_found) <= 10:
                        sys.stderr.write(
                            f"  Found wine-related file: {item.relative_to(wine_tkg_dir)}\n"
                        )
                        self.log(
                            f"DEBUG:   Found wine-related file: {item.relative_to(wine_tkg_dir)}",
                            "info",
                        )
        except Exception as e:
            sys.stderr.write(f"Warning: Error during recursive search: {e}\n")
            sys.stderr.flush()
            self.log(f"DEBUG: Warning: Error during recursive search: {e}", "warning")

        if wine_files_found:
            sys.stderr.write(
                f"Found {len(wine_files_found)} wine-related files total\n"
            )
            sys.stderr.write("Most likely candidates:\n")
            self.log(
                f"DEBUG: Found {len(wine_files_found)} wine-related files total", "info"
            )
            self.log(f"DEBUG: Most likely candidates:", "info")
            for candidate in wine_files_found[:5]:
                if candidate.name == "wine" or candidate.name.startswith("wine"):
                    sys.stderr.write(f"  - {candidate}\n")
                    self.log(f"DEBUG:   - {candidate}", "info")
        else:
            sys.stderr.write("No wine-related files found in extraction directory\n")
            self.log(
                "DEBUG: No wine-related files found in extraction directory", "error"
            )

        sys.stderr.write(
            "\nERROR: wine-tkg extraction completed but binary not found\n"
        )
        sys.stderr.flush()
        self.log("DEBUG: ✗ wine-tkg extraction completed but binary not found", "error")
        return False

    def get_winetricks_env_with_tkg(self, base_env=None):
        """Get environment for winetricks with wine-tkg in PATH"""
        self.log("DEBUG: get_winetricks_env_with_tkg() called", "info")

        if base_env is None:
            env = os.environ.copy()
            self.log("DEBUG: Created new environment from os.environ", "info")
        else:
            env = base_env.copy()
            self.log("DEBUG: Created environment copy from base_env", "info")

        self.log("DEBUG: Searching for wine-tkg binary...", "info")
        wine_tkg_bin = self.get_wine_tkg_path("wine")
        self.log(f"DEBUG: get_wine_tkg_path() returned: {wine_tkg_bin}", "info")

        wine_tkg_usable = False
        if wine_tkg_bin:
            self.log(f"DEBUG: wine-tkg binary path: {wine_tkg_bin}", "info")
            self.log(f"DEBUG: wine-tkg binary exists: {wine_tkg_bin.exists()}", "info")

            if wine_tkg_bin.exists():
                # Don't just trust that the file existing means it works — a
                # corrupted download or a build incompatible with this host
                # can still pass an exists() check but fail to actually run.
                if self._wine_binary_is_functional(wine_tkg_bin):
                    wine_tkg_bin_dir = wine_tkg_bin.parent
                    current_path = env.get("PATH", "")
                    env["PATH"] = f"{wine_tkg_bin_dir}:{current_path}"
                    wine_tkg_usable = True
                    self.log(f"DEBUG: ✓ Using wine-tkg from: {wine_tkg_bin_dir}", "info")
                    self.log(
                        f"DEBUG: Updated PATH (first 200 chars): {env['PATH'][:200]}",
                        "info",
                    )
                    self.log(f"Using wine-tkg from: {wine_tkg_bin_dir}", "info")
                else:
                    self.log(
                        "wine-tkg is present but failed to run — falling back to system wine",
                        "warning",
                    )
            else:
                error_msg = "wine-tkg binary path returned but file does not exist"
                self.log(f"DEBUG: ✗ ERROR: {error_msg}", "error")
                self.log(f"DEBUG: Path was: {wine_tkg_bin}", "error")
                self.log("wine-tkg not found, using system wine", "warning")
        else:
            self.log("DEBUG: ✗ wine-tkg binary not found", "info")
            self.log("wine-tkg not found, using system wine", "warning")

        if not wine_tkg_usable:
            env = self._pin_system_wine_in_env(env)

        # ── Speed optimisations ───────────────────────────────────────────────
        # Suppress Wine debug output - major speedup per wineserver invocation
        env.setdefault("WINEDEBUG", "-all,fixme-all")

        # Use aria2c for multi-connection downloads if available, else curl, else wget
        if self.check_command("aria2c"):
            env["WINETRICKS_DOWNLOADER"] = "aria2c"
            self.log("winetricks: using aria2c for fast downloads", "info")
        elif self.check_command("curl"):
            env["WINETRICKS_DOWNLOADER"] = "curl"
        else:
            env["WINETRICKS_DOWNLOADER"] = "wget"

        # Disable winetricks GUI (ensures non-interactive even if DISPLAY is set)
        env["WINETRICKS_GUI"] = "none"

        # Keep wineserver alive between winetricks calls to avoid repeated cold starts
        env["WINESERVER_TIMEOUT"] = "60"
        return env

    def get_winetricks_env(self, base_env=None):
        """Build the environment used for winetricks runs"""
        env = os.environ.copy() if base_env is None else base_env.copy()
        env["WINEPREFIX"] = self.directory
        env["WINETRICKS_GUI"] = "0"
        env["DISPLAY"] = env.get("DISPLAY", ":0")

        # Prevent Wine from blocking headless setup with Mono/Gecko download prompts.
        dll_overrides = [entry for entry in env.get("WINEDLLOVERRIDES", "").split(";") if entry]
        for required_override in ("mscoree=", "mshtml="):
            if required_override not in dll_overrides:
                dll_overrides.append(required_override)
        env["WINEDLLOVERRIDES"] = ";".join(dll_overrides)

        # Always prefer the Wine build that owns the prefix, on every distro.
        # Running winetricks under a *second* Wine build lets two wineservers
        # alternate on one prefix — which is where the .NET installers wedge.
        local_wine = self.get_wine_path("wine")
        if local_wine.exists():
            env = self._use_wine_in_env(env, local_wine)
            self.log(f"winetricks: using the prefix's Wine ({local_wine})", "info")
            self._warn_new_wow64_wine(local_wine)
            return env

        if self.is_ubuntu_family_distro():
            self.log("Local installer Wine not found; winetricks will fall back to system Wine.", "warning")
            return env

        # No prefix Wine at all: fall back, preferring a pre-11 Wine when we get
        # to choose. AffinityLinuxInstaller.sh refuses Wine >= 11 for winetricks
        # because of hangs in Wine's new WoW64 mode.
        self.log("Setting up wine-tkg for winetricks...", "info")
        if self.ensure_wine_tkg():
            wine_tkg_bin = self.get_wine_tkg_path("wine")
            if (
                wine_tkg_bin
                and wine_tkg_bin.exists()
                and self._wine_binary_is_functional(wine_tkg_bin)
            ):
                system_wine = shutil.which("wine")
                tkg_major = self._wine_major_version(wine_tkg_bin)
                system_major = (
                    self._wine_major_version(system_wine) if system_wine else None
                )
                if (
                    tkg_major is not None
                    and tkg_major >= 11
                    and system_major is not None
                    and system_major < 11
                ):
                    self.log(
                        f"Preferring system Wine {system_major}.x over wine-tkg "
                        f"{tkg_major}.x for winetricks (Wine 11+ new WoW64 hangs winetricks).",
                        "warning",
                    )
                    return self._pin_system_wine_in_env(env)
                return self.get_winetricks_env_with_tkg(env)
        self.log("Failed to setup wine-tkg, continuing with system wine", "warning")
        return self._pin_system_wine_in_env(env)

    def _use_wine_in_env(self, env, wine_bin):
        """Point WINE/WINELOADER/WINESERVER/PATH at one specific Wine build."""
        wine_bin = Path(wine_bin)
        env["WINE"] = str(wine_bin)
        env["WINELOADER"] = str(wine_bin)
        env["PATH"] = f"{wine_bin.parent}:{env.get('PATH', '')}"
        wineserver = wine_bin.parent / "wineserver"
        if wineserver.exists():
            env["WINESERVER"] = str(wineserver)
        return env

    def _wine_major_version(self, wine_bin):
        """Major version of a Wine binary (11 for "wine-11.18"), or None."""
        if not wine_bin:
            return None
        wine_bin = str(wine_bin)
        if not Path(wine_bin).exists() and not shutil.which(wine_bin):
            return None
        try:
            result = subprocess.run(
                [wine_bin, "--version"],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=15,
            )
            match = re.search(
                r"wine-(\d+)\.", f"{result.stdout or ''}{result.stderr or ''}"
            )
            if match:
                return int(match.group(1))
        except Exception:
            pass
        return None

    def _warn_new_wow64_wine(self, wine_bin):
        """Say out loud when winetricks is about to run on a Wine 11+ build.

        AffinityLinuxInstaller.sh refuses Wine >= 11 for winetricks (hangs in
        the new WoW64 mode). We cannot always avoid that build, so at least
        tell the user what to try when a component stalls."""
        major = self._wine_major_version(wine_bin)
        if major is not None and major >= 11:
            self.log(
                f"winetricks is running on Wine {major}.x. Wine 11+ new WoW64 mode is "
                "known to hang the .NET installers — if a component stalls, switch "
                "to the other Wine version (11.18 / 11.19) and try again.",
                "warning",
            )
        return major

    def build_winetricks_command(self, component, extra_flags=(), verbose=True):
        """Build a winetricks command line for a single verb.

        `--force` means "don't check whether packages were already installed",
        so without it winetricks skips a verb it can already see is installed.
        That matters for the .NET verbs: forcing them re-runs the whole
        multi-minute .NET chain on every attempt, and that chain is exactly
        where Wine wedges (the 64-bit ngen.exe never returns).
        """
        skip_force = {
            "dotnet20",
            "dotnet20sp1",
            "dotnet30",
            "dotnet30sp1",
            "dotnet35",
            "dotnet35sp1",
            "dotnet40",
            "dotnet45",
            "dotnet471",
            "dotnet472",
            "dotnet48",
        }
        verb = str(component).split("=", 1)[0]
        command = ["winetricks", "--unattended"]
        if verbose:
            command.append("--verbose")
        command.extend(["--no-isolate", "--optout"])
        if verb not in skip_force:
            command.append("--force")
        command.extend(str(flag) for flag in extra_flags)
        command.append(component)
        return command

    # What counts as work for _prefix_activity: CPU seconds used per minute by
    # the prefix's Wine processes (its idle services use a fraction of one),
    # and the newest file under the folders .NET and Windows Installer write.
    ACTIVITY_CPU_SECONDS = 2.0
    ACTIVITY_PROBE_INTERVAL = 60
    ACTIVITY_DIRS = ("drive_c/windows/Microsoft.NET", "drive_c/windows/assembly",
                     "drive_c/windows/Installer", "drive_c/windows/temp",
                     "drive_c/windows/syswow64", "drive_c/windows/system32")

    def _prefix_activity(self):
        """A snapshot that changes while the prefix's Wine is doing work:
        (CPU in ACTIVITY_CPU_SECONDS steps, newest file date, Installer/ngen
        running). Read from /proc and file dates only -- nothing is attached."""
        hz = os.sysconf("SC_CLK_TCK")
        cpu = 0.0
        busy = False
        for pid in self._prefix_wine_pids():
            try:
                fields = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()
                cpu += (int(fields[11]) + int(fields[12])) / hz
                cmd = open(f"/proc/{pid}/cmdline", "rb").read().lower()
                busy = busy or any(n in cmd for n in (b"msiexec", b"ngen.exe", b"mscorsvw"))
            except (OSError, IndexError, ValueError):
                continue
        newest = 0.0
        for rel in self.ACTIVITY_DIRS:
            top = Path(self.directory) / rel
            try:
                newest = max(newest, top.stat().st_mtime,
                             *(e.stat().st_mtime for e in os.scandir(top)))
            except (OSError, ValueError):
                continue
        return (int(cpu // self.ACTIVITY_CPU_SECONDS), int(newest), busy)

    def _log_prefix_snapshot(self):
        """What was still running when a step was stopped, and what each
        program's threads were waiting on -- so a stopped step says why."""
        lines = []
        for pid in self._prefix_wine_pids():
            try:
                cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace").strip()
                waits = {}
                for tid in os.listdir(f"/proc/{pid}/task"):
                    state = open(f"/proc/{pid}/task/{tid}/stat").read().rsplit(")", 1)[1].split()[0]
                    chan = open(f"/proc/{pid}/task/{tid}/wchan").read().strip() or "-"
                    waits[f"{state}:{chan}"] = waits.get(f"{state}:{chan}", 0) + 1
                lines.append(f"    {cmd[:90]}  [{', '.join(f'{k} x{v}' for k, v in sorted(waits.items()))}]")
            except OSError:
                continue
        if lines:
            self.log("  Still running when it was stopped:\n" + "\n".join(lines[:15]), "info")

    def _prefix_wine_pids(self):
        """PIDs of processes whose environment points at our WINEPREFIX.

        Never returns our own process or anything in our process group."""
        # Compare against every spelling of the prefix path we may have handed
        # out (raw string, normalised, trailing slash).
        prefixes = {
            str(self.directory),
            str(Path(self.directory)),
            str(Path(self.directory)) + os.sep,
        }
        pids = []
        try:
            own_pgid = os.getpgrp()
        except Exception:
            own_pgid = None
        try:
            entries = os.listdir("/proc")
        except Exception:
            return pids

        for entry in entries:
            if not entry.isdigit():
                continue
            pid = int(entry)
            if pid == os.getpid():
                continue
            try:
                with open(f"/proc/{pid}/environ", "rb") as handle:
                    data = handle.read()
            except Exception:
                continue
            matched = False
            for item in data.split(b"\0"):
                if item.startswith(b"WINEPREFIX="):
                    value = item.split(b"=", 1)[1].decode("utf-8", "replace")
                    matched = value in prefixes
                    break
            if not matched:
                continue
            if own_pgid is not None:
                try:
                    if os.getpgid(pid) == own_pgid:
                        continue
                except Exception:
                    pass
            pids.append(pid)
        return pids

    def stop_prefix_wine_processes(
        self, env=None, reason="", wait_seconds=20, force=False
    ):
        """Stop every process still running against our WINEPREFIX.

        Left-over Wine work — a wedged .NET installer, an abandoned winetricks
        run, a wineserver started by a different Wine build — keeps Windows
        Installer busy, so the next winetricks run blocks forever waiting for a
        lock nobody will release. Returns True when the prefix is quiet.

        `force=True` runs even after the user cancelled (the cancel/close paths
        must clean up on their way out); `wait_seconds` keeps short-lived calls
        off the GUI thread for long."""
        if not force and self.cancel_event.is_set():
            return False

        pids = self._prefix_wine_pids()
        if not pids:
            return True

        what = "leftover Wine process(es)"
        if reason:
            self.log(f"Stopping {len(pids)} {what} in {self.directory} — {reason}", "info")
        else:
            self.log(f"Stopping {len(pids)} {what} in {self.directory}", "info")

        # 1. Ask politely first
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass

        # 2. Let the prefix's wineserver release its locks as well
        run_env = dict(env) if env else os.environ.copy()
        run_env.setdefault("WINEPREFIX", self.directory)
        wineserver = None
        for candidate in (
            run_env.get("WINESERVER"),
            str(self.get_wine_path("wineserver")),
            shutil.which("wineserver"),
        ):
            if candidate and Path(candidate).exists():
                wineserver = candidate
                break
        server_killed = False
        if wineserver:
            try:
                subprocess.run(
                    [wineserver, "-k"],
                    env=run_env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=min(30, max(3, wait_seconds)),
                    check=False,
                )
                server_killed = True
            except Exception:
                pass

        # 3. Wait for them to leave, then force whatever is left. Once
        # `wineserver -k` has returned, everything connected to the prefix is
        # gone; what remains is a straggler that never leaves by itself (a
        # winedevice.exe after each winetricks verb), and the full wait cost
        # 20 s per verb for nothing.
        # The wineserver itself is the exception: SIGTERM makes it write the
        # registry to disk (system.reg alone is ~11 MB), and killing it
        # mid-write loses what the last verb set (renderer=vulkan was lost
        # this way). It always gets the full wait.
        def is_wineserver(pid):
            try:
                comm = Path(f"/proc/{pid}/comm").read_text().strip()
            except Exception:
                return False
            return comm.startswith("wineserver")

        def is_alive(pid):
            # A zombie has exited; only its parent's wait is missing.
            try:
                stat = Path(f"/proc/{pid}/stat").read_text()
            except Exception:
                return False
            return stat.rsplit(")", 1)[-1].split()[0] != "Z"

        remaining = list(pids)
        servers = {pid for pid in remaining if is_wineserver(pid)}
        grace = min(wait_seconds, 2) if server_killed else wait_seconds
        start = time.monotonic()
        while remaining:
            elapsed = time.monotonic() - start
            if elapsed >= max(1, wait_seconds):
                break
            if elapsed >= max(1, grace) and not servers.intersection(remaining):
                break
            if not force and self.cancel_event.is_set():
                return False
            time.sleep(0.1)
            remaining = [pid for pid in remaining if is_alive(pid)]
        for pid in remaining:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
        if remaining:
            self.log(f"Force-killed {len(remaining)} stuck Wine process(es)", "warning")
        else:
            self.log("Prefix is clean", "success")
        return True

    def prefix_has_installed_affinity(self):
        """Return True when the prefix already contains an installed Affinity executable"""
        exe_paths = [
            Path(self.directory) / "drive_c" / "Program Files" / "Affinity" / "Photo 2" / "Photo.exe",
            Path(self.directory) / "drive_c" / "Program Files" / "Affinity" / "Designer 2" / "Designer.exe",
            Path(self.directory) / "drive_c" / "Program Files" / "Affinity" / "Publisher 2" / "Publisher.exe",
            Path(self.directory) / "drive_c" / "Program Files" / "Affinity" / "Affinity" / "Affinity.exe",
        ]
        return any(path.exists() for path in exe_paths)

    def backup_incomplete_ubuntu_prefix(self):
        """Back up incomplete Ubuntu-family prefixes before recreating them"""
        prefix_dir = Path(self.directory)
        if not self.is_ubuntu_family_distro():
            return True
        if not (prefix_dir / "system.reg").exists():
            return True
        if self.prefix_has_installed_affinity():
            return True

        backup_dir = prefix_dir.parent / f"{prefix_dir.name}.backup-{time.strftime('%Y%m%d-%H%M%S')}"
        try:
            self.log(
                "Detected an existing Ubuntu-family Wine prefix without installed Affinity applications.",
                "warning"
            )
            self.log(f"Backing it up to {backup_dir} so setup can continue from a clean prefix.", "info")
            # Nothing may still be running inside the prefix we are about to move:
            # a live wineserver keeps writing files under it mid-copy.
            self.stop_prefix_wine_processes(
                reason="backing up an incomplete prefix", wait_seconds=8
            )
            shutil.move(str(prefix_dir), str(backup_dir))
            prefix_dir.mkdir(parents=True, exist_ok=True)
            self.log("Incomplete Wine prefix backed up", "success")
            return True
        except Exception as e:
            self.log(f"Failed to back up incomplete Wine prefix: {e}", "error")
            return False

    def has_dotnet48_runtime(self):
        """Return True when .NET Framework 4.8 is registered in the prefix"""
        reg_file = Path(self.directory) / "system.reg"
        if not reg_file.exists():
            return False

        try:
            content = reg_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return False

        keys = [
            r"\[Software\\\\Microsoft\\\\NET Framework Setup\\\\NDP\\\\v4\\\\Full\](.*?)(?=\n\[|\Z)",
            r"\[Software\\\\Wow6432Node\\\\Microsoft\\\\NET Framework Setup\\\\NDP\\\\v4\\\\Full\](.*?)(?=\n\[|\Z)",
        ]
        for pattern in keys:
            match = re.search(pattern, content, re.DOTALL)
            if not match:
                continue
            block = match.group(1)
            if '"Install"=dword:00000001' not in block:
                continue

            release_match = re.search(r'"Release"=dword:([0-9a-fA-F]+)', block)
            if release_match and int(release_match.group(1), 16) >= 0x80e18:
                return True

            version_match = re.search(r'"Version"="([^"]+)"', block)
            if version_match and version_match.group(1).startswith("4.8"):
                return True
        return False

    def verify_required_wine_runtimes(self):
        """Ensure the prefix contains the minimum runtimes required by Affinity installers"""
        if self.has_dotnet48_runtime():
            return True

        self.log(".NET Framework 4.8 is not installed in the Wine prefix.", "error")
        self.log("Affinity's SetupUI.exe crashes without it, which matches the JIT/debugger failures seen on Ubuntu.", "info")
        if self.is_ubuntu_family_distro():
            self.log("Ubuntu-family systems use Wine 11.19 by default; if winetricks stalls on the Wine 11 new WoW64 path, switch to Wine 11.18 and try again.", "info")
        self.log("Aborting before launching the Affinity installer.", "info")
        return False

    def _register_process(self, proc):
        """Track a running subprocess for potential cancellation."""
        try:
            with self._process_lock:
                self._active_processes.add(proc)
        except Exception:
            pass

    def _unregister_process(self, proc):
        """Stop tracking a subprocess."""
        try:
            with self._process_lock:
                self._active_processes.discard(proc)
        except Exception:
            pass

    def _terminate_process(self, proc):
        """Terminate a subprocess and its process group safely."""
        try:
            # Try to terminate the whole process group first
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                proc.terminate()
            # Wait briefly, then force kill if still alive
            try:
                proc.wait(timeout=2)
            except Exception:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        finally:
            self._unregister_process(proc)

    def terminate_active_processes(self):
        """Terminate all active subprocesses started by this installer."""
        try:
            with self._process_lock:
                procs = list(self._active_processes)
            for p in procs:
                self._terminate_process(p)
        except Exception:
            pass

    def run_command(
        self, command, check=True, shell=False, capture=True, env=None, timeout=None
    ):
        """Execute shell command with GUI sudo password support and cancellation.

        `timeout` is a hard deadline (seconds): the polling loops below check it
        along with cancel_event, so a wedged command can no longer freeze the GUI
        forever. Defaults to AFFINITY_STALL_TIMEOUT (30 min), or 1 h for sudo —
        package installs are allowed to run long."""
        proc = None
        try:
            # Convert command to list if it's a string
            if isinstance(command, str) and not shell:
                command = command.split()
            # Ensure command is a list
            if not isinstance(command, list):
                command = list(command)

            # Set up environment for non-interactive operation
            if env is None:
                env = os.environ.copy()

            # Force non-interactive mode for various tools
            env["DEBIAN_FRONTEND"] = "noninteractive"
            env["NEEDRESTART_MODE"] = "a"  # Auto-restart services without asking
            env["DEBIAN_PRIORITY"] = "critical"
            env["APT_LISTCHANGES_FRONTEND"] = "none"
            env["LANG"] = "C"  # Use C locale to avoid encoding issues
            env["LC_ALL"] = "C"

            # Check if this is a sudo command
            is_sudo = (
                isinstance(command, list) and len(command) > 0 and command[0] == "sudo"
            )

            # Unset SUDO_ASKPASS to force sudo to read password from stdin via -S flag
            # This prevents errors when askpass programs (like ksshaskpass) don't exist
            if is_sudo:
                env.pop("SUDO_ASKPASS", None)  # Remove SUDO_ASKPASS if it exists

            # Hard deadline for this command (see docstring).
            if timeout is None:
                timeout = 3600 if is_sudo else self.get_stall_timeout()
            deadline = (time.monotonic() + timeout) if timeout else None
            cmd_display = (
                " ".join(str(c) for c in command[:6])
                if isinstance(command, list)
                else str(command)[:80]
            )

            if is_sudo:
                # Get password if needed
                max_attempts = 3
                for attempt in range(max_attempts):
                    if self.cancel_event.is_set():
                        return False, "", "Cancelled"
                    password = self.get_sudo_password()
                    if password is None:
                        self.log("Authentication cancelled by user", "warning")
                        return False, "", "Authentication cancelled"
                    # Validate password first
                    if not self.sudo_password_validated:
                        if self.validate_sudo_password(password):
                            self.log("Authentication successful", "success")
                            break
                        else:
                            self.log(
                                "Authentication failed. Please try again.", "error"
                            )
                            self.sudo_password = None
                            self.sudo_password_validated = False
                            if attempt == max_attempts - 1:
                                return (
                                    False,
                                    "",
                                    "Authentication failed after multiple attempts",
                                )
                    else:
                        break

                # Run command with password via stdin
                # Add -S flag to read password from stdin if not present
                # Make sure -S is right after "sudo"
                # Create a copy to avoid modifying the original
                command = list(command)
                if len(command) > 1:
                    # Only add -S if it's not already in position 1 (right after sudo)
                    # Don't remove -S that's part of the actual command (like pacman -S)
                    if command[1] != "-S":
                        # Insert -S right after "sudo"
                        command.insert(1, "-S")
                else:
                    # Only "sudo" in command, add -S
                    command.append("-S")

                proc = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE if capture else None,
                    stderr=subprocess.PIPE if capture else None,
                    text=True,
                    errors="replace",  # never die on undecodable output
                    env=env,  # Use the modified env that has SUDO_ASKPASS removed
                    preexec_fn=os.setsid,
                )
                self._register_process(proc)
                try:
                    # Hand the password over and close stdin right away, so the
                    # loop below stays free to poll for cancellation and the
                    # deadline (one blocking communicate() made Cancel a no-op).
                    password_input = f"{self.sudo_password}\n"
                    try:
                        proc.stdin.write(password_input)
                        proc.stdin.close()
                    except Exception:
                        pass

                    stdout_acc = ""
                    stderr_acc = ""
                    while True:
                        if self.cancel_event.is_set():
                            self._terminate_process(proc)
                            return False, stdout_acc, "Cancelled"
                        if deadline is not None and time.monotonic() >= deadline:
                            display = (
                                " ".join(str(c) for c in command[:6])
                                if isinstance(command, list)
                                else str(command)[:80]
                            )
                            self.log(
                                f"Command timed out after {timeout}s: {display}",
                                "error",
                            )
                            self._terminate_process(proc)
                            return False, stdout_acc, f"Timed out after {timeout}s"
                        try:
                            out, err = proc.communicate(timeout=0.2)
                        except subprocess.TimeoutExpired:
                            continue
                        except Exception as e:
                            # Decode/closed-pipe race: the command itself may
                            # still have succeeded, so trust its exit status.
                            error_msg = str(e)
                            if proc.poll() is None:
                                self._terminate_process(proc)
                            if proc.returncode == 0:
                                return True, stdout_acc, stderr_acc
                            self.log(
                                f"Error during command execution ({type(e).__name__}): {error_msg}",
                                "error",
                            )
                            return False, stdout_acc, error_msg
                        if capture:
                            stdout_acc += out or ""
                            stderr_acc += err or ""
                        return proc.returncode == 0, stdout_acc, stderr_acc
                finally:
                    self._unregister_process(proc)
            else:
                # Non-sudo command, run normally with cancellation support
                proc = subprocess.Popen(
                    command
                    if not shell
                    else (command if isinstance(command, str) else " ".join(command)),
                    shell=shell,
                    stdout=subprocess.PIPE if capture else None,
                    stderr=subprocess.PIPE if capture else None,
                    text=capture,
                    errors="replace" if capture else None,  # never die on undecodable output
                    env=env if env else os.environ.copy(),
                    preexec_fn=os.setsid,
                )
                self._register_process(proc)
                try:
                    if capture:
                        stdout_acc = ""
                        stderr_acc = ""
                        while True:
                            if deadline is not None and time.monotonic() >= deadline:
                                self._terminate_process(proc)
                                self.log(
                                    f"Command timed out after {timeout}s: {cmd_display}",
                                    "error",
                                )
                                return (
                                    False,
                                    stdout_acc,
                                    f"Timed out after {timeout}s",
                                )
                            try:
                                out, err = proc.communicate(timeout=0.2)
                            except subprocess.TimeoutExpired:
                                if self.cancel_event.is_set():
                                    self._terminate_process(proc)
                                    return False, stdout_acc, "Cancelled"
                                continue
                            except Exception as e:
                                # Decode/closed-pipe race: trust the exit status.
                                error_msg = str(e)
                                if proc.poll() is None:
                                    self._terminate_process(proc)
                                if proc.returncode == 0:
                                    return True, stdout_acc, stderr_acc
                                self.log(
                                    f"Error during command execution ({type(e).__name__}): {error_msg}",
                                    "error",
                                )
                                return False, stdout_acc, error_msg
                            stdout_acc += out or ""
                            stderr_acc += err or ""
                            break
                        success = proc.returncode == 0
                        return success, stdout_acc, stderr_acc
                    else:
                        while True:
                            if self.cancel_event.is_set():
                                self._terminate_process(proc)
                                return False, "", "Cancelled"
                            if deadline is not None and time.monotonic() >= deadline:
                                self._terminate_process(proc)
                                self.log(
                                    f"Command timed out after {timeout}s: {cmd_display}",
                                    "error",
                                )
                                return False, "", f"Timed out after {timeout}s"
                            if proc.poll() is not None:
                                break
                            time.sleep(0.1)
                        return proc.returncode == 0, "", ""
                finally:
                    self._unregister_process(proc)
        except Exception as e:
            # Never leave the child behind: an orphaned wine/winecfg process is
            # what makes the *next* run queue up and hang.
            try:
                if proc is not None:
                    self._terminate_process(proc)
            except Exception:
                pass
            return False, "", str(e)

    @staticmethod
    def _pump_child_output(stream, out_queue):
        """Read a child's stdout line by line and push lines onto `out_queue`.

        Runs in its own thread so the caller can keep polling for cancellation
        and stalls while the child is silent. A `None` sentinel marks EOF.
        """
        try:
            for line in iter(stream.readline, ""):
                out_queue.put(line)
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass
            out_queue.put(None)

    def get_stall_timeout(self, default=1800):
        """Seconds a streamed command may run without printing anything.

        Override with the AFFINITY_STALL_TIMEOUT environment variable.
        """
        try:
            value = int(os.environ.get("AFFINITY_STALL_TIMEOUT", ""))
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
        return default

    def run_command_streaming(
        self, command, env=None, progress_callback=None, stall_timeout=None,
        activity_probe=None, hard_limit=None,
    ):
        """Execute command and stream output to log in real-time, cancellable.

        A reader thread decodes the child's output (leniently, so a stray
        non-UTF-8 byte from Wine can never abort the run) while this loop:
          * honours cancel_event even while the child prints nothing,
          * kills the child once it has been silent for `stall_timeout`
            seconds — winetricks wedged inside a .NET installer otherwise
            blocks forever with the progress bar frozen at "Installing".

        Also stores the full streamed text in self._last_stream_output_text
        for post-run heuristics.

        With `activity_probe` (a callable returning a comparable snapshot of
        the work, see _prefix_activity), silence alone is not a stall: the
        snapshot is taken every 60 s, and a change counts as activity. The
        .NET installers print nothing for minutes while they work. Then
        `hard_limit` seconds is the backstop for anything that keeps busy
        without ever finishing.
        """
        self._last_stream_output_text = ""
        self._last_command_stalled = False
        if stall_timeout is None:
            stall_timeout = self.get_stall_timeout()
        if isinstance(command, str):
            command = command.split()
        display_cmd = " ".join(str(part) for part in command[:8])

        process = None
        try:
            # Set up environment for non-interactive operation
            if env is None:
                env = os.environ.copy()

            # Force non-interactive mode for various tools
            env["DEBIAN_FRONTEND"] = "noninteractive"
            env["NEEDRESTART_MODE"] = "a"  # Auto-restart services without asking
            env["DEBIAN_PRIORITY"] = "critical"
            env["APT_LISTCHANGES_FRONTEND"] = "none"
            env["LANG"] = "C"  # Use C locale to avoid encoding issues
            env["LC_ALL"] = "C"

            # Unset SUDO_ASKPASS if this is a sudo command
            is_sudo = (
                isinstance(command, list) and len(command) > 0 and command[0] == "sudo"
            )
            if is_sudo:
                env.pop("SUDO_ASKPASS", None)

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",  # never die on undecodable Wine output
                bufsize=1,
                universal_newlines=True,
                env=env,
                preexec_fn=os.setsid,
            )
            self._register_process(process)

            # Stream output line by line without ever blocking indefinitely
            lines = queue.Queue()
            threading.Thread(
                target=self._pump_child_output,
                args=(process.stdout, lines),
                daemon=True,
            ).start()

            buffer = []
            last_output = time.monotonic()
            started = last_output
            warned_stall = False
            probe_every = getattr(self, "ACTIVITY_PROBE_INTERVAL", 60)
            next_probe = started + probe_every
            last_activity = activity_probe() if activity_probe else None
            quiet_noted = False

            while True:
                if self.cancel_event.is_set():
                    self._terminate_process(process)
                    self._last_stream_output_text = "".join(buffer)
                    return False

                try:
                    line = lines.get(timeout=0.5)
                except queue.Empty:
                    now = time.monotonic()
                    if activity_probe and now >= next_probe:
                        next_probe = now + probe_every
                        try:
                            activity = activity_probe()
                        except Exception:
                            activity = last_activity
                        if activity != last_activity:
                            last_activity = activity
                            last_output = now
                            warned_stall = False
                            if not quiet_noted and now - started >= 2 * probe_every:
                                quiet_noted = True
                                self.log(f"  '{display_cmd}' is quiet but still working "
                                         "(using CPU or writing files)...", "info")
                    if hard_limit and now - started >= hard_limit:
                        self._last_command_stalled = True
                        self.log(f"  ✗ '{display_cmd}' has run for {int(now - started)}s, "
                                 f"past the {hard_limit}s limit — stopping it.", "error")
                        self._log_prefix_snapshot()
                        self._terminate_process(process)
                        self._last_stream_output_text = "".join(buffer)
                        return False
                    idle = now - last_output
                    if idle >= stall_timeout:
                        self._last_command_stalled = True
                        self.log(
                            f"  ✗ No output from '{display_cmd}' for {int(idle)}s — "
                            "assuming it is stuck and stopping it.",
                            "error",
                        )
                        self.log(
                            "  (Set AFFINITY_STALL_TIMEOUT to raise the limit, or "
                            "check the last log lines above for the step it died on.)",
                            "info",
                        )
                        if activity_probe:
                            self._log_prefix_snapshot()
                        self._terminate_process(process)
                        self._last_stream_output_text = "".join(buffer)
                        return False
                    if not warned_stall and idle >= stall_timeout / 2:
                        warned_stall = True
                        self.log(
                            f"  Waiting on '{display_cmd}' — no output for "
                            f"{int(idle)}s (stall limit {stall_timeout}s)...",
                            "warning",
                        )
                    continue

                if line is None:  # EOF sentinel from the reader thread
                    break

                last_output = time.monotonic()
                if line:
                    # Clean up the line and log it
                    line = line.rstrip()
                    if line:
                        buffer.append(line + "\n")
                        warned_stall = False
                        # Show important progress messages
                        line_lower = line.lower()
                        # Always show progress-related messages
                        if any(
                            keyword in line_lower
                            for keyword in [
                                "progress",
                                "downloading",
                                "installing",
                                "extracting",
                                "configuring",
                                "executing",
                                "running",
                                "done",
                                "complete",
                                "success",
                                "error",
                                "failed",
                                "warning",
                                "%",
                                "mb",
                                "kb",
                            ]
                        ):
                            self.log(f"  {line}", "info")

                            # Try to extract progress percentage if callback provided
                            if progress_callback:
                                percent_match = re.search(
                                    r"(\d+)\s*%", line, re.IGNORECASE
                                )
                                if percent_match:
                                    try:
                                        percent = int(percent_match.group(1))
                                        progress_callback(percent / 100.0)
                                    except (ValueError, TypeError):
                                        pass
                        # Filter out very verbose Wine debug messages but keep important ones
                        elif not any(
                            skip in line_lower
                            for skip in ["fixme:", "trace:", "debug:"]
                        ):
                            # Show other non-debug messages
                            self.log(f"  {line}", "info")

            # Reader hit EOF: give the child a moment to exit on its own, but do
            # not block forever if it hung up after closing its output.
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.log(
                    f"  '{display_cmd}' closed its output but is still running — "
                    "stopping it.",
                    "warning",
                )
                self._terminate_process(process)
            self._last_stream_output_text = "".join(buffer)
            return process.returncode == 0
        except Exception as e:
            self.log(f"Error running command: {e}", "error")
            if process is not None:
                # Never leave the child running on its own — orphaned winetricks
                # runs are what wedge the next attempt.
                try:
                    self._terminate_process(process)
                except Exception:
                    pass
            return False
        finally:
            if process is not None:
                try:
                    self._unregister_process(process)
                except Exception:
                    pass

    def _to_windows_path(self, unix_path, env=None):
        """Convert a UNIX path to a Windows path for Wine 'start' using winepath.
        Falls back to Z: drive mapping if winepath is unavailable."""
        try:
            winepath_bin = self.get_wine_path("winepath")
            if winepath_bin.exists():
                success, stdout, _ = self.run_command(
                    [str(winepath_bin), "-w", str(unix_path)],
                    check=False,
                    env=env,
                    capture=True,
                )
                if success and stdout:
                    return stdout.strip().splitlines()[-1]
        except Exception:
            pass
        # Fallback: Z: mapping
        p = str(unix_path)
        if p.startswith("/"):
            win = "Z:" + p
        else:
            win = p
        return win.replace("/", "\\")

    # Wine's own background processes, which never count as an installer.
    WINE_SERVICE_EXES = {"services.exe", "winedevice.exe", "svchost.exe", "plugplay.exe",
                         "rpcss.exe", "lsass.exe", "explorer.exe", "start.exe",
                         "conhost.exe", "wineboot.exe"}

    def _release_webview2_wait(self, stop, settle_seconds=10, interval=2):
        """End the wait on the WebView2 setup once the runtime is installed.

        The setup leaves MicrosoftEdgeUpdate.exe /c behind, which never exits,
        so `wine start /wait` waited out the whole 1-hour stall timeout. Once
        msedgewebview2.exe is in place and Edge's updater is all that is left
        (Wine's services aside) for `settle_seconds`, stop the updater; Edge
        Update is disabled right after anyway."""
        app_dir = (Path(self.directory) / "drive_c" / "Program Files (x86)" / "Microsoft"
                   / "EdgeWebView" / "Application")
        quiet_since = None
        while not stop.wait(interval):
            try:
                installed = any(app_dir.glob("*/msedgewebview2.exe"))
            except OSError:
                installed = False
            updaters, others = [], []
            for pid in self._prefix_wine_pids():
                try:
                    exe = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[0]
                except OSError:
                    continue
                name = exe.decode("utf-8", "replace").replace("\\", "/").rsplit("/", 1)[-1].lower()
                if name.startswith("microsoftedgeupdate"):
                    updaters.append(pid)
                elif name not in self.WINE_SERVICE_EXES and name not in ("wine", "wine64", "wineserver", "wine-preloader", "wine64-preloader"):
                    others.append(pid)
            if not (installed and updaters and not others):
                quiet_since = None
                continue
            quiet_since = quiet_since or time.monotonic()
            if time.monotonic() - quiet_since < settle_seconds:
                continue
            self.log("WebView2 Runtime installed; stopping Edge Update, which the setup leaves running", "info")
            for pid in updaters:
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
            return

    def _has_installer_activity(self, installer_file: Path) -> bool:
        """Heuristics to detect installer activity:
        - Check for Wine processes referencing installer/common names
        - If wmctrl is available, check for visible windows with class/name containing wine/setup/installer
        """
        try:
            # Process-based heuristic
            patterns = [
                installer_file.name.lower(),
                "setup",
                "msiexec",
                "install",
                ".msi",
                ".exe",
            ]
            success, stdout, _ = self.run_command(
                ["ps", "-eo", "pid,command"], check=False, capture=True
            )
            if success and stdout:
                text = stdout.lower()
                if ("wine" in text or "wineserver" in text) and any(
                    pat in text for pat in patterns
                ):
                    return True
            # Window-based heuristic (wmctrl)
            wmctrl = shutil.which("wmctrl")
            if wmctrl:
                ok, wout, _ = self.run_command(
                    [wmctrl, "-lx"], check=False, capture=True
                )
                if ok and wout:
                    w = wout.lower()
                    # Examples: 'wine.wine explorer.exe', 'setup.exe', 'affinity'
                    if "wine" in w and any(pat in w for pat in patterns):
                        return True
        except Exception:
            pass
        return False

    def _run_installer_and_capture(
        self, installer_file: Path, env: dict, label: str = "installer"
    ):
        """Run a Windows installer under Wine, stream logs, and wait robustly until it exits.
        Strategy:
        1) Try 'wine start /wait /unix <file>'
        2) If it exits too quickly or returns non-zero with no activity, try 'wine <file>'
        3) After launch, wait on 'wineserver -w' to ensure child processes finish (cancellable)

        Affinity installers still use system Wine, but WebView2 must stay on the
        same Wine runtime as the prefix to avoid wineserver/runtime mismatches.
        """
        # Check if this is Affinity v3 or WebView2 installer
        installer_name = installer_file.name.lower()
        is_affinity_v3 = "affinity" in installer_name and (
            "x64" in installer_name or "affinity-x64" in installer_name
        )
        is_affinity_v2 = (
            any(app in installer_name for app in ["photo", "designer", "publisher"])
            and ".exe" in installer_name
        )
        is_webview2 = "webview" in installer_name or "edge" in installer_name

        # Set Windows 11 before installing Affinity
        # (clear leftovers first: a wedged process would make winecfg queue)
        self.stop_prefix_wine_processes(env, reason="launching an installer")
        if not self.manages_host_entries():
            env = dict(env)
            overrides = env.get("WINEDLLOVERRIDES", "")
            env["WINEDLLOVERRIDES"] = ";".join(
                x for x in (overrides, "winemenubuilder.exe=d") if x)
        if is_affinity_v3 or is_affinity_v2:
            self.log(
                "Setting Windows version to 11 before Affinity installation...", "info"
            )
            # The prefix's own winecfg. System winecfg is another Wine, and
            # starting it in this prefix took 13 s and can update the prefix.
            prefix_winecfg = self.get_wine_path("winecfg")
            winecfg = str(prefix_winecfg) if prefix_winecfg.exists() else "winecfg"
            self.run_command([winecfg, "-v", "win11"], check=False, env=env)
            self.log("✓ Windows version set to 11", "success")
        elif is_webview2:
            webview2_tools = self.get_webview2_wine_tools()
            self.log("Setting Windows version to 11 before WebView2 installation...", "info")
            self.run_command([webview2_tools["winecfg"], "-v", "win11"], check=False, env=env)
            self.log("✓ Windows version set to 11", "success")

        # Use system Wine for Affinity installations (custom Wine doesn't work
        # for installation) -- but ONLY when system Wine can actually talk to
        # this prefix.
        #
        # A prefix belongs to the Wine that made it. Point a different Wine at
        # it and wineserver refuses with "version mismatch 961/931", the
        # installer exits in under two seconds, and the heuristics below then
        # decided it was "running despite error" and carried on: every
        # post-install step ran, the update reported success, and the
        # application was never replaced. Observed on a prefix built by
        # ElementalWarrior 11.16 with wine 11.1 on PATH.
        if is_affinity_v3 or is_affinity_v2:
            wine = "wine"
            if not self.system_wine_matches_prefix():
                wine = str(self.get_wine_path("wine"))
                self.log(
                    "System Wine does not match this prefix -- using the "
                    f"prefix's own Wine for installation: {wine}",
                    "warning",
                )
            else:
                self.log("Using system Wine for Affinity installation", "info")
        elif is_webview2:
            webview2_tools = self.get_webview2_wine_tools()
            wine = webview2_tools["wine"]
            if webview2_tools["source"] == "bundled":
                self.log("Using bundled installer Wine for WebView2 installation", "info")
            else:
                self.log("Using system Wine for WebView2 installation", "info")
        else:
            # Use custom Wine for other installers
            wine = str(self.get_wine_path("wine"))

        # For Affinity installers, try direct execution first (more reliable)
        if is_affinity_v3 or is_affinity_v2:
            attempts = [
                [wine, str(installer_file)],
                [wine, "start", "/wait", "/unix", str(installer_file)],
            ]
        else:
            attempts = [
                [wine, "start", "/wait", "/unix", str(installer_file)],
                [wine, str(installer_file)],
            ]
        for idx, cmd in enumerate(attempts, start=1):
            try:
                cmd_str = " ".join(shlex.quote(c) for c in cmd)
                self.log(f"Running ({label}) attempt {idx}: {cmd_str}", "info")
                t0 = time.time()
                watcher_stop = threading.Event()
                if is_webview2:
                    threading.Thread(target=self._release_webview2_wait,
                                     args=(watcher_stop,), daemon=True).start()
                # Affinity/WebView2 installers print nothing while they work
                # (WINEDEBUG is silenced), so give them a long leash.
                try:
                    ok = self.run_command_streaming(cmd, env=env, stall_timeout=3600)
                finally:
                    watcher_stop.set()
                dt = time.time() - t0

                # For Affinity installers, check if installer is actually running despite exceptions
                if is_affinity_v3 or is_affinity_v2:
                    txt = (self._last_stream_output_text or "").lower()
                    # Check if we got a debugger exception but installer might still be running
                    if "unhandled exception" in txt or "winedbg" in txt:
                        self.log(
                            "Wine debugger exception detected, checking if installer is running...",
                            "warning",
                        )
                        # Give it a moment to start
                        time.sleep(3)
                        if self._has_installer_activity(installer_file):
                            self.log(
                                "Installer is running despite exception message, continuing...",
                                "info",
                            )
                            ok = True

                # If it "succeeded" unrealistically fast, poll briefly for activity or window
                if ok and dt < 5.0:
                    self.log(
                        f"{label.capitalize()} attempt {idx} returned quickly ({dt:.2f}s). Polling for activity...",
                        "warning",
                    )
                    for _ in range(30):  # ~3s
                        if self.check_cancelled():
                            return False
                        if self._has_installer_activity(installer_file):
                            break
                        time.sleep(0.1)
                    else:
                        ok = False
                # Also verify there was some wine activity (best-effort heuristic)
                if ok and not self._has_installer_activity(installer_file):
                    # As a last signal, check stream output for obvious errors
                    txt = (self._last_stream_output_text or "").lower()
                    error_markers = [
                        "err:",
                        "cannot find",
                        "bad exe",
                        "failed",
                        "error:",
                        "no such file",
                        "unable to load",
                    ]
                    # Not a marker to weigh up: the installer never ran at all.
                    if "version mismatch" in txt:
                        self.log(
                            "Wine client/server version mismatch -- the installer "
                            "could not attach to this prefix and did not run.",
                            "error",
                        )
                        return False
                    # For Affinity installers, ignore debugger messages if installer is running
                    if is_affinity_v3 or is_affinity_v2:
                        # Double-check if installer is actually running
                        time.sleep(1)
                        if self._has_installer_activity(installer_file):
                            ok = True  # Installer is running, ignore error markers
                    if any(m in txt for m in error_markers) and not (
                        is_affinity_v3
                        or is_affinity_v2
                        and self._has_installer_activity(installer_file)
                    ):
                        ok = False
                # For Affinity installers, even if ok is False, check if installer is actually running
                if (is_affinity_v3 or is_affinity_v2) and not ok:
                    if "version mismatch" in (self._last_stream_output_text or "").lower():
                        self.log(
                            "Wine client/server version mismatch -- not continuing; "
                            "the application would be left unchanged while the "
                            "update reported success.",
                            "error",
                        )
                        return False
                    # Check one more time if installer is running
                    time.sleep(2)
                    if self._has_installer_activity(installer_file):
                        self.log(
                            "Installer is running despite error, continuing...", "info"
                        )
                        ok = True

                if ok:
                    # For WebView2, use polling with timeout instead of indefinite wineserver wait
                    if is_webview2:
                        self.log(
                            "Waiting for WebView2 installer to complete (polling with timeout)...",
                            "info",
                        )
                        max_wait_time = 600  # 10 minutes max
                        poll_interval = 2  # Check every 2 seconds
                        start_time = time.time()

                        while time.time() - start_time < max_wait_time:
                            if self.check_cancelled():
                                return False

                            # Check if installer process/window is still active
                            if not self._has_installer_activity(installer_file):
                                # No installer activity - wait a bit more to ensure it's really done
                                time.sleep(3)
                                # Double-check it's still inactive
                                if not self._has_installer_activity(installer_file):
                                    # Also verify WebView2 was actually installed
                                    webview2_paths = [
                                        Path(self.directory)
                                        / "drive_c"
                                        / "Program Files (x86)"
                                        / "Microsoft"
                                        / "EdgeWebView"
                                        / "Application",
                                        Path(self.directory)
                                        / "drive_c"
                                        / "Program Files"
                                        / "Microsoft"
                                        / "EdgeWebView"
                                        / "Application",
                                    ]
                                    installed = any(
                                        (path / "msedgewebview2.exe").exists()
                                        for path in webview2_paths
                                    )
                                    if installed:
                                        self.log(
                                            "WebView2 installer completed and files detected",
                                            "success",
                                        )
                                    else:
                                        self.log(
                                            "WebView2 installer appears to have completed (files not yet detected)",
                                            "info",
                                        )
                                    break

                            time.sleep(poll_interval)
                        else:
                            self.log(
                                "WebView2 installer timeout reached - proceeding anyway",
                                "warning",
                            )

                        # Final wineserver wait with short timeout
                        env_wait = env.copy() if env else os.environ.copy()
                        env_wait["WINEPREFIX"] = self.directory
                        try:
                            # Use timeout for wineserver wait (30 seconds max)
                            process = subprocess.Popen(
                                [self.get_webview2_wine_tools()["wineserver"], "-w"],
                                env=env_wait,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                            )
                            process.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            self.log(
                                "Wineserver wait timed out - installer may have finished",
                                "warning",
                            )
                            process.kill()
                        except Exception as e:
                            self.log(
                                f"Wineserver wait error (non-critical): {e}", "warning"
                            )
                    else:
                        self.log(
                            "Waiting for Wine processes to finish (wineserver -w)...",
                            "info",
                        )
                        # Extended wait; cancellable via run_command loop
                        env_wait = env.copy() if env else os.environ.copy()
                        env_wait["WINEPREFIX"] = self.directory
                        # Use system wineserver (always use system wineserver, not patched one)
                        self.run_command(
                            ["wineserver", "-w"],
                            check=False,
                            capture=False,
                            env=env_wait,
                        )
                    return True
                if self.check_cancelled():
                    return False
                self.log(
                    f"{label.capitalize()} attempt {idx} did not run (ok={ok}, dt={dt:.2f}s). Trying fallback...",
                    "warning",
                )
            except Exception as e:
                self.log(f"Error launching {label} attempt {idx}: {e}", "error")
        return False

    def run_command_interactive(self, command, env=None):
        """Execute command and handle interactive prompts via GUI, cancellable."""
        try:
            if isinstance(command, str):
                command = command.split()

            # Set up environment for non-interactive operation
            if env is None:
                env = os.environ.copy()

            # Force non-interactive mode for various tools
            env["DEBIAN_FRONTEND"] = "noninteractive"
            env["NEEDRESTART_MODE"] = "a"
            env["DEBIAN_PRIORITY"] = "critical"
            env["APT_LISTCHANGES_FRONTEND"] = "none"
            env["LANG"] = "C"
            env["LC_ALL"] = "C"

            # Check if this is a sudo command
            is_sudo = (
                isinstance(command, list) and len(command) > 0 and command[0] == "sudo"
            )

            # Unset SUDO_ASKPASS to force sudo to read password from stdin via -S flag
            # This prevents errors when askpass programs (like ksshaskpass) don't exist
            if is_sudo:
                env.pop("SUDO_ASKPASS", None)

            if is_sudo:
                # Get password if needed
                password = self.get_sudo_password()
                if password is None:
                    self.log("Authentication cancelled by user", "warning")
                    return False, "", "Authentication cancelled"

                # Validate password if not already validated
                if not self.sudo_password_validated:
                    if not self.validate_sudo_password(password):
                        self.log("Authentication failed", "error")
                        return False, "", "Authentication failed"

                # Add -S flag if not present
                # Create a copy to avoid modifying the original
                command = list(command)
                if len(command) > 1:
                    # Only add -S if it's not already in position 1 (right after
                    # sudo). Don't remove -S flags that belong to the actual
                    # command (like pacman -S).
                    if command[1] != "-S":
                        command.insert(1, "-S")
                else:
                    # Only "sudo" in command, add -S
                    command.append("-S")

            # Start process
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                preexec_fn=os.setsid,
            )
            self._register_process(process)

            # If sudo, send password first
            if is_sudo and self.sudo_password:
                try:
                    process.stdin.write(f"{self.sudo_password}\n")
                    process.stdin.flush()
                except Exception:
                    pass

            # Read output and detect prompts
            output_lines = []
            error_lines = []

            import select

            while True:
                if self.cancel_event.is_set():
                    self._terminate_process(process)
                    return False, "", "Cancelled"
                # Check if process has finished
                if process.poll() is not None:
                    # Read any remaining output
                    remaining_out = process.stdout.read()
                    remaining_err = process.stderr.read()
                    if remaining_out:
                        output_lines.append(remaining_out)
                    if remaining_err:
                        error_lines.append(remaining_err)
                    break

                # Try to read from stdout with timeout
                try:
                    # Use select to check if data is available (Unix-like systems)
                    import sys

                    if hasattr(select, "select"):
                        readable, _, _ = select.select(
                            [process.stdout, process.stderr], [], [], 0.1
                        )

                        for stream in readable:
                            line = stream.readline()
                            if line:
                                if stream == process.stdout:
                                    output_lines.append(line)
                                    self.log(f"  {line.rstrip()}", "info")
                                else:
                                    error_lines.append(line)

                                # Detect interactive prompts
                                line_lower = line.lower()
                                if any(
                                    pattern in line_lower
                                    for pattern in [
                                        "overwrite?",
                                        "(y/n)",
                                        "[y/n]",
                                        "yes/no",
                                        "continue?",
                                        "proceed?",
                                        "replace?",
                                    ]
                                ):
                                    # Interactive prompt detected!
                                    self.log(
                                        f"Interactive prompt detected: {line.rstrip()}",
                                        "warning",
                                    )

                                    # Extract default response if present
                                    default = ""
                                    if "(y/n)" in line_lower:
                                        # Check which is capitalized
                                        if "(Y/n)" in line:
                                            default = "y"
                                        elif "(y/N)" in line:
                                            default = "n"

                                    # Get user response via GUI
                                    response = self.get_interactive_response(
                                        line.rstrip(), default
                                    )

                                    # Send response to process
                                    if process.stdin:
                                        process.stdin.write(response)
                                        process.stdin.flush()
                except Exception as e:
                    self.log(f"Error reading process output: {e}", "warning")
                    time.sleep(0.1)

            # Get return code
            return_code = process.wait()

            stdout_text = "".join(output_lines)
            stderr_text = "".join(error_lines)

            return return_code == 0, stdout_text, stderr_text

        except Exception as e:
            self.log(f"Error in interactive command: {e}", "error")
            return False, "", str(e)
        finally:
            try:
                self._unregister_process(process)
            except Exception:
                pass

    def check_command(self, cmd):
        """Check if command exists"""
        return shutil.which(cmd) is not None

    def detect_distro(self):
        """Detect Linux distribution"""
        try:
            with open("/etc/os-release", "r") as f:
                content = f.read()

            raw_distro = None
            distro_like = ""
            for line in content.split("\n"):
                if line.startswith("ID="):
                    raw_distro = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("VERSION_ID="):
                    self.distro_version = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("ID_LIKE="):
                    distro_like = line.split("=", 1)[1].strip().strip('"')

            self.raw_distro = raw_distro
            self.distro_like = distro_like
            self.distro = raw_distro.lower() if raw_distro else raw_distro

            # Normalize "pika" to "pikaos" if detected
            if self.distro == "pika":
                self.distro = "pikaos"

            # Normalize "pop" to "pop" if detected
            if self.distro == "pop":
                self.distro = "pop"

            distro_like_tokens = {token.strip().lower() for token in distro_like.replace(",", " ").split() if token.strip()}
            if (
                self.distro not in {"ubuntu", "linuxmint", "zorin", "pop"}
                and "ubuntu" in distro_like_tokens
            ):
                detected_name = self.format_distro_name(self.distro)
                self.log(
                    f"Detected Ubuntu-compatible derivative: {detected_name}. Using Ubuntu dependency path.",
                    "info"
                )
                self.distro = "ubuntu"


            return True
        except Exception as e:
            self.log(f"Error detecting distribution: {e}", "error")
            return False

    def _ensure_icons_directory(self):
        """Ensure icons directory exists, download from GitHub if missing (optimized)"""
        try:
            # Always use the standard location in user's config directory
            # This ensures icons are available even when script is piped from curl
            # Named cache_dir, not script_dir: there is a module-level
            # script_dir() and a local of that name shadows it for the WHOLE
            # function body, so the call below raised TypeError before this
            # method could download anything.
            cache_dir = Path.home() / ".config" / "AffinityOnLinux" / "AffinityScripts"
            cache_dir.mkdir(parents=True, exist_ok=True)

            icons_dir = cache_dir / "icons"

            # Ensure icons directory exists
            icons_dir.mkdir(parents=True, exist_ok=True)

            # Check if local icons directory exists and has icons (fast path).
            # Only a real checkout counts -- see script_dir().
            here = script_dir()
            local_icons_dir = (here / "icons") if here else None
            if local_icons_dir and local_icons_dir.exists():
                # If local icons exist, copy them quickly instead of downloading
                try:
                    local_icons = list(local_icons_dir.glob("*.svg"))
                    if local_icons:
                        # Copy missing icons from local directory
                        for local_icon in local_icons:
                            dest_icon = icons_dir / local_icon.name
                            if not dest_icon.exists():
                                shutil.copy2(local_icon, dest_icon)
                        return  # Fast path - use local icons
                except Exception:
                    pass  # Fall through to download if copy fails

            # List of UI theme icons to download from GitHub (only if local icons don't exist)
            # Note: Application icons (Affinity.png, etc.) are downloaded elsewhere
            # These are just the UI button icons needed for the installer interface
            icon_files = [
                # Zoom icons
                ("zoom-in-dark.svg", "AffinityScripts/icons/zoom-in-dark.svg"),
                ("zoom-in-light.svg", "AffinityScripts/icons/zoom-in-light.svg"),
                ("zoom-out-dark.svg", "AffinityScripts/icons/zoom-out-dark.svg"),
                ("zoom-out-light.svg", "AffinityScripts/icons/zoom-out-light.svg"),
                (
                    "zoom-original-dark.svg",
                    "AffinityScripts/icons/zoom-original-dark.svg",
                ),
                (
                    "zoom-original-light.svg",
                    "AffinityScripts/icons/zoom-original-light.svg",
                ),
                # Action icons
                ("rocket-dark.svg", "AffinityScripts/icons/rocket-dark.svg"),
                ("rocket-light.svg", "AffinityScripts/icons/rocket-light.svg"),
                ("wine-dark.svg", "AffinityScripts/icons/wine-dark.svg"),
                ("wine-light.svg", "AffinityScripts/icons/wine-light.svg"),
                (
                    "dependencies-dark.svg",
                    "AffinityScripts/icons/dependencies-dark.svg",
                ),
                (
                    "dependencies-light.svg",
                    "AffinityScripts/icons/dependencies-light.svg",
                ),
                ("wand-dark.svg", "AffinityScripts/icons/wand-dark.svg"),
                ("wand-light.svg", "AffinityScripts/icons/wand-light.svg"),
                ("download-dark.svg", "AffinityScripts/icons/download-dark.svg"),
                ("download-light.svg", "AffinityScripts/icons/download-light.svg"),
                ("folderopen-dark.svg", "AffinityScripts/icons/folderopen-dark.svg"),
                ("folderopen-light.svg", "AffinityScripts/icons/folderopen-light.svg"),
                ("camera-dark.svg", "AffinityScripts/icons/camera-dark.svg"),
                ("camera-light.svg", "AffinityScripts/icons/camera-light.svg"),
                ("pen-dark.svg", "AffinityScripts/icons/pen-dark.svg"),
                ("pen-light.svg", "AffinityScripts/icons/pen-light.svg"),
                ("book-dark.svg", "AffinityScripts/icons/book-dark.svg"),
                ("book-light.svg", "AffinityScripts/icons/book-light.svg"),
                ("windows-dark.svg", "AffinityScripts/icons/windows-dark.svg"),
                ("windows-light.svg", "AffinityScripts/icons/windows-light.svg"),
                ("display-dark.svg", "AffinityScripts/icons/display-dark.svg"),
                ("display-light.svg", "AffinityScripts/icons/display-light.svg"),
                ("lightning-dark.svg", "AffinityScripts/icons/lightning-dark.svg"),
                ("lightning-light.svg", "AffinityScripts/icons/lightning-light.svg"),
                ("loop-dark.svg", "AffinityScripts/icons/loop-dark.svg"),
                ("loop-light.svg", "AffinityScripts/icons/loop-light.svg"),
                ("chrome-dark.svg", "AffinityScripts/icons/chrome-dark.svg"),
                ("chrome-light.svg", "AffinityScripts/icons/chrome-light.svg"),
                ("cog-dark.svg", "AffinityScripts/icons/cog-dark.svg"),
                ("cog-light.svg", "AffinityScripts/icons/cog-light.svg"),
                ("scale-dark.svg", "AffinityScripts/icons/scale-dark.svg"),
                ("scale-light.svg", "AffinityScripts/icons/scale-light.svg"),
                ("trash-dark.svg", "AffinityScripts/icons/trash-dark.svg"),
                ("trash-light.svg", "AffinityScripts/icons/trash-light.svg"),
                ("play-dark.svg", "AffinityScripts/icons/play-dark.svg"),
                ("play-light.svg", "AffinityScripts/icons/play-light.svg"),
                ("exit-dark.svg", "AffinityScripts/icons/exit-dark.svg"),
                ("exit-light.svg", "AffinityScripts/icons/exit-light.svg"),
                (
                    "affinity-unified-dark.svg",
                    "AffinityScripts/icons/affinity-unified-dark.svg",
                ),
                (
                    "affinity-unified-light.svg",
                    "AffinityScripts/icons/affinity-unified-light.svg",
                ),
            ]

            # Check which icons are missing
            missing_icons = []
            for local_name, github_path in icon_files:
                icon_path = icons_dir / local_name
                if not icon_path.exists():
                    missing_icons.append((local_name, github_path))

            # Only download if there are missing icons
            if not missing_icons:
                return  # All icons already exist

            # Download icons in parallel for speed (no log messages)
            base_url = "https://raw.githubusercontent.com/ryzendew/AffinityOnLinux/main/"

            def download_icon(local_name, github_path):
                """Download a single icon"""
                icon_path = icons_dir / local_name
                try:
                    # Check if github_path is a full URL (for user-attachments) or relative path
                    if github_path.startswith("http://") or github_path.startswith(
                        "https://"
                    ):
                        icon_url = github_path
                    else:
                        icon_url = base_url + github_path

                    # Use urlretrieve with timeout
                    urllib.request.urlretrieve(icon_url, str(icon_path))
                except Exception:
                    # Silently fail - icons are not critical for functionality
                    pass

            # Download icons in parallel (limit to 5 concurrent downloads to avoid overwhelming)
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=5) as executor:
                executor.map(lambda args: download_icon(*args), missing_icons)
        except Exception:
            # Silently fail - icons are not critical for functionality
            pass

    def detect_gpus(self):
        """Detect available GPUs in the system"""
        gpus = []

        # Get lspci output once
        lspci_success, lspci_stdout, _ = self.run_command(
            ["lspci"], check=False, capture=True
        )
        if not lspci_success or not lspci_stdout:
            # If lspci fails, return auto option only
            gpus.append(
                {
                    "type": "auto",
                    "name": "Auto (System Default)",
                    "index": 0,
                    "id": "auto",
                }
            )
            return gpus

        # Parse lspci output to find actual GPU devices
        # Look for VGA, 3D, or Display controller entries
        gpu_lines = []
        for line in lspci_stdout.split("\n"):
            line_lower = line.lower()
            # Check if this is a graphics/display device
            # GREP defined more explicitly, avoids wrong lines
            if any(
                keyword in line_lower
                for keyword in [
                    "vga",
                    "3d controller",
                    "display controller",
                    "graphics",
                ]
            ):
                gpu_lines.append(line)

        # Process each GPU line to extract type and model
        for line in gpu_lines:
            line_lower = line.lower()

            # Extract model name (everything after the last colon)
            if ":" in line:
                model = (
                    line.split(":")[2].strip()
                    if len(line.split(":")) > 2
                    else "Unknown GPU"
                )
            else:
                model = "Unknown GPU"

            # Determine GPU type
            gpu_type = None
            gpu_id = None

            if "nvidia" in line_lower:
                gpu_type = "nvidia"
                # Count existing nvidia GPUs to get index
                nvidia_count = sum(1 for gpu in gpus if gpu["type"] == "nvidia")
                gpu_id = f"nvidia_{nvidia_count}"
            elif (
                "amd" in line_lower or "radeon" in line_lower or "amd/ati" in line_lower
            ):
                gpu_type = "amd"
                amd_count = sum(1 for gpu in gpus if gpu["type"] == "amd")
                gpu_id = f"amd_{amd_count}"
            elif "intel" in line_lower:
                gpu_type = "intel"
                intel_count = sum(1 for gpu in gpus if gpu["type"] == "intel")
                gpu_id = f"intel_{intel_count}"

            # Only add if we identified a GPU type
            if gpu_type:
                gpus.append(
                    {
                        "type": gpu_type,
                        "name": model,
                        "index": len([g for g in gpus if g["type"] == gpu_type]),
                        "id": gpu_id,
                    }
                )

        # Always add "Auto" option as the first choice
        gpus.insert(
            0,
            {"type": "auto", "name": "Auto (System Default)", "index": 0, "id": "auto"},
        )

        return gpus

    def has_amd_gpu(self):
        """Check if system has an AMD GPU"""
        gpus = self.detect_gpus()
        return any(gpu["type"] == "amd" for gpu in gpus)

    def has_nvidia_gpu(self):
        """Check if system has an NVIDIA GPU"""
        gpus = self.detect_gpus()
        return any(gpu["type"] == "nvidia" for gpu in gpus)

    def get_selected_gpu(self):
        """Get environment variables for GPU selection"""
        gpu_config_file = Path(self.directory) / ".gpu_config"
        gpu_id = "auto"
        if gpu_config_file.exists():
            try:
                with open(gpu_config_file, "r") as f:
                    gpu_id = f.read().strip()
            except Exception:
                gpu_id = "auto"
        return gpu_id

    def get_dxvk_vkd3d_preference(self):
        """Get DXVK/vkd3d preference for NVIDIA users"""
        pref_file = Path(self.directory) / ".dxvk_vkd3d_preference"
        if pref_file.exists():
            try:
                with open(pref_file, "r") as f:
                    return f.read().strip()
            except Exception:
                return None
        return None

    def set_dxvk_vkd3d_preference(self, preference):
        """Set DXVK/vkd3d preference for NVIDIA users (either 'dxvk' or 'vkd3d')"""
        pref_file = Path(self.directory) / ".dxvk_vkd3d_preference"
        try:
            with open(pref_file, "w") as f:
                f.write(preference)
            return True
        except Exception as e:
            self.log(f"Failed to save DXVK/vkd3d preference: {e}", "error")
            return False

    def _show_nvidia_dxvk_vkd3d_choice_safe(self):
        """Show NVIDIA DXVK/vkd3d choice dialog (called from main thread)"""
        # Check if preference already exists
        existing_pref = self.get_dxvk_vkd3d_preference()
        if existing_pref in ["dxvk", "vkd3d"]:
            self.nvidia_dxvk_vkd3d_choice_response = existing_pref
            self.waiting_for_nvidia_choice = False
            return

        # Create a custom dialog
        dialog = QDialog(self.dialog_parent())
        dialog.setWindowTitle("Choose Graphics Backend for NVIDIA GPU")
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Responsive sizing - improved for all screen sizes
        screen = dialog.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        if screen_width < 800 or screen_height < 600:
            min_width = min(400, int(screen_width * 0.9))
            min_height = min(360, int(screen_height * 0.7))
            default_width = min(500, int(screen_width * 0.85))
            default_height = min(480, int(screen_height * 0.8))
            max_width = int(screen_width * 0.95)
            max_height = int(screen_height * 0.85)
        elif screen_width < 1280 or screen_height < 720:
            min_width = 450
            min_height = 420
            default_width = 550
            default_height = 500
            max_width = int(screen_width * 0.9)
            max_height = int(screen_height * 0.85)
        else:
            min_width = 450
            min_height = 440
            default_width = 560
            default_height = 520
            max_width = 800
            max_height = 700

        dialog.setMinimumWidth(min_width)
        dialog.setMinimumHeight(min_height)
        dialog.setMaximumWidth(max_width)
        dialog.setMaximumHeight(max_height)
        dialog.resize(default_width, default_height)
        dialog.setSizeGripEnabled(True)

        # Apply theme stylesheet matching main UI
        dark_style = """
                QDialog {
                    background-color: #252526;
                    color: #dcdcdc;
                }
                QLabel {
                    color: #dcdcdc;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4ec9b0;
                    padding: 10px 0px;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #cccccc;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                }
                QFrame#optionFrame {
                    background-color: #2d2d2d;
                    border: 1px solid #3c3c3c;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #4a4a4a;
                    background-color: #323232;
                }
                QRadioButton {
                    font-size: 16px;
                    color: #dcdcdc;
                    padding: 8px 0px;
                    spacing: 10px;
                    font-weight: 500;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #555555;
                    background-color: #3c3c3c;
                }
                QRadioButton::indicator:hover {
                    border-color: #6a6a6a;
                }
                QRadioButton::indicator:checked {
                    background-color: #4ec9b0;
                    border-color: #4ec9b0;
                }
                QPushButton {
                    background-color: #3c3c3c;
                    color: #f0f0f0;
                    border: 1px solid #555555;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                    border-color: #6a6a6a;
                }
                QPushButton:pressed {
                    background-color: #2d2d2d;
                }
                QPushButton#okButton {
                    background-color: #4ec9b0;
                    color: #1e1e1e;
                    border: 1px solid #4ec9b0;
                    font-weight: bold;
                }
                QPushButton#okButton:hover {
                    background-color: #5dd9c0;
                    border-color: #5dd9c0;
                }
                QPushButton#okButton:pressed {
                    background-color: #3db9a0;
                }
        """
        if self.theme == "mattscreative":
            dialog_style = self._mattscreative_palette_style(dark_style)
        elif self.dark_mode:
            dialog_style = dark_style
        else:
            dialog_style = """
                QDialog {
                    background-color: #ffffff;
                    color: #2d2d2d;
                }
                QLabel {
                    color: #2d2d2d;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4caf50;
                    padding: 10px 0px;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #555555;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                }
                QLabel#optionDescription {
                    font-size: 12px;
                    color: #666666;
                    padding: 4px 0px 0px 0px;
                    line-height: 1.4;
                }
                QFrame#optionFrame {
                    background-color: #f5f5f5;
                    border: 1px solid #e0e0e0;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #c0c0c0;
                    background-color: #fafafa;
                }
                QRadioButton {
                    font-size: 14px;
                    color: #2d2d2d;
                    padding: 8px 0px;
                    spacing: 10px;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #c0c0c0;
                    background-color: #ffffff;
                }
                QRadioButton::indicator:hover {
                    border-color: #a0a0a0;
                }
                QRadioButton::indicator:checked {
                    background-color: #4caf50;
                    border-color: #4caf50;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    color: #2d2d2d;
                    border: 1px solid #c0c0c0;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #d0d0d0;
                    border-color: #a0a0a0;
                }
                QPushButton:pressed {
                    background-color: #c0c0c0;
                }
                QPushButton#okButton {
                    background-color: #4caf50;
                    color: #ffffff;
                    border: 1px solid #4caf50;
                    font-weight: bold;
                }
                QPushButton#okButton:hover {
                    background-color: #45a049;
                    border-color: #45a049;
                }
                QPushButton#okButton:pressed {
                    background-color: #3d8b40;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background-color: #f5f5f5;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #c0c0c0;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #a0a0a0;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """

        dialog.setStyleSheet(dialog_style)

        # Main layout with responsive margins
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(12)
        margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
        main_layout.setContentsMargins(margin, margin, margin, margin)

        # Title
        title_label = QLabel("NVIDIA GPU Detected")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(title_label)

        # Description
        desc_label = QLabel()
        desc_label.setTextFormat(Qt.TextFormat.RichText)
        desc_label.setText(
            "Please choose your preferred graphics backend:\n\n"
            "• <b>vkd3d</b> - vkd3d-proton: Direct3D 12 on your GPU. The usual choice. "
            "(OpenCL also works with it, but only on Wine older than 11.11.)\n"
            "• <b>DXVK</b> - Direct3D 11 on your GPU, never OpenCL\n\n"
            "Note: You can change this later if needed."
        )
        desc_label.setObjectName("descriptionLabel")
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(desc_label)

        # Options container with scroll area for better scaling
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        options_container = QFrame()
        options_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        options_layout = QVBoxLayout(options_container)
        options_layout.setSpacing(8)
        options_margin = 8 if (screen_width >= 800 and screen_height >= 600) else 6
        options_layout.setContentsMargins(
            options_margin, options_margin, options_margin, options_margin
        )

        scroll_area.setWidget(options_container)

        # Radio buttons in styled frames
        button_group = QButtonGroup()

        # vkd3d option
        vkd3d_frame = QFrame()
        vkd3d_frame.setObjectName("optionFrame")
        vkd3d_layout = QVBoxLayout(vkd3d_frame)
        vkd3d_layout.setContentsMargins(12, 10, 12, 10)
        vkd3d_radio = QRadioButton("vkd3d (with OpenCL support)")
        vkd3d_radio.setChecked(True)
        vkd3d_radio.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        vkd3d_layout.addWidget(vkd3d_radio)
        options_layout.addWidget(vkd3d_frame)

        # DXVK option
        dxvk_frame = QFrame()
        dxvk_frame.setObjectName("optionFrame")
        dxvk_layout = QVBoxLayout(dxvk_frame)
        dxvk_layout.setContentsMargins(12, 10, 12, 10)
        dxvk_radio = QRadioButton("DXVK (hardware accelerated, no OpenCL)")
        dxvk_radio.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        dxvk_layout.addWidget(dxvk_radio)
        options_layout.addWidget(dxvk_frame)

        button_group.addButton(vkd3d_radio, 0)
        button_group.addButton(dxvk_radio, 1)

        main_layout.addWidget(scroll_area, 1)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Continue")
        ok_btn.setObjectName("okButton")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)

        main_layout.addLayout(button_layout)

        # Ensure the dialog is large enough to show all content; clamp inside min/max.
        hint = dialog.sizeHint()
        target_w = min(max(default_width, hint.width()), max_width)
        target_h = min(max(default_height, hint.height()), max_height)
        target_w = max(target_w, min_width)
        target_h = max(target_h, min_height)
        dialog.resize(target_w, target_h)

        # Show dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        # Get result
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if vkd3d_radio.isChecked():
                preference = "vkd3d"
            else:
                preference = "dxvk"

            self.set_dxvk_vkd3d_preference(preference)
            self.nvidia_dxvk_vkd3d_choice_response = preference
        else:
            # User cancelled - default to vkd3d
            self.set_dxvk_vkd3d_preference("vkd3d")
            self.nvidia_dxvk_vkd3d_choice_response = "vkd3d"

        self.waiting_for_nvidia_choice = False

    def ask_nvidia_dxvk_vkd3d_choice(self):
        """Ask NVIDIA users to choose between DXVK and vkd3d (thread-safe)"""
        # Check if preference already exists
        existing_pref = self.get_dxvk_vkd3d_preference()
        if existing_pref in ["dxvk", "vkd3d"]:
            return existing_pref

        # Show dialog using signal (thread-safe)
        self.nvidia_dxvk_vkd3d_choice_response = None
        self.waiting_for_nvidia_choice = True
        self.nvidia_dxvk_vkd3d_choice_signal.emit()

        # Wait for response with timeout
        max_wait = 300  # 30 seconds
        waited = 0
        while self.waiting_for_nvidia_choice and waited < max_wait:
            time.sleep(0.1)
            waited += 1

        return self.nvidia_dxvk_vkd3d_choice_response or "vkd3d"

    def get_gpu_env_vars(self, gpu_id=None):
        """Get environment variables for GPU selection"""
        if gpu_id is None:
            # Load from saved preference
            gpu_config_file = Path(self.directory) / ".gpu_config"
            if gpu_config_file.exists():
                try:
                    with open(gpu_config_file, "r") as f:
                        gpu_id = f.read().strip()
                except Exception:
                    gpu_id = "auto"
            else:
                gpu_id = "auto"

        env_vars = []

        if gpu_id == "auto" or not gpu_id:
            # No specific GPU selection - use system default
            return ""

        if gpu_id.startswith("nvidia_"):
            # NVIDIA GPU selection
            env_vars.append("__NV_PRIME_RENDER_OFFLOAD=1")
            env_vars.append("__GLX_VENDOR_LIBRARY_NAME=nvidia")
            # Also set for Vulkan
            env_vars.append("__VK_LAYER_NV_optimus=NVIDIA_only")

        elif gpu_id.startswith("amd_"):
            # AMD discrete GPU (using DRI_PRIME)
            index = int(gpu_id.split("_")[1]) if "_" in gpu_id else 1
            env_vars.append(f"DRI_PRIME={index}")

        elif gpu_id.startswith("intel_"):
            # Intel GPU (usually integrated, use DRI_PRIME=0)
            env_vars.append("DRI_PRIME=0")

        if env_vars:
            return " ".join(env_vars) + " "
        return ""

    def get_vulkan_device_select_env(self, gpu_id=None):
        """Return Vulkan device-selection env vars for the selected GPU, when available."""
        if gpu_id is None:
            gpu_id = self.get_selected_gpu()

        if not gpu_id or gpu_id == "auto":
            return {}

        match = re.match(r"^(nvidia|amd|intel)_(\d+)$", gpu_id)
        if not match:
            return {}

        target_type = match.group(1)
        target_index = int(match.group(2))

        lspci_success, lspci_stdout, _ = self.run_command(
            ["lspci", "-nn"],
            check=False,
            capture=True
        )
        if not lspci_success or not lspci_stdout:
            return {}

        def line_matches_gpu_type(line):
            line_lower = line.lower()
            if target_type == "nvidia":
                return "nvidia" in line_lower
            if target_type == "amd":
                return any(keyword in line_lower for keyword in ("amd", "radeon", "amd/ati"))
            if target_type == "intel":
                return "intel" in line_lower
            return False

        gpu_lines = []
        for line in lspci_stdout.splitlines():
            line_lower = line.lower()
            if not any(keyword in line_lower for keyword in ("vga", "3d controller", "display controller", "graphics")):
                continue
            if line_matches_gpu_type(line):
                gpu_lines.append(line)

        if not gpu_lines:
            return {}

        if target_index >= len(gpu_lines):
            # Older saved GPU selections may use a stale index; fall back to the first match.
            target_index = 0

        pci_id_match = re.search(r"\[([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\]", gpu_lines[target_index])
        if not pci_id_match:
            return {}

        selector = f"{pci_id_match.group(1).lower()}:{pci_id_match.group(2).lower()}"
        return {
            "MESA_VK_DEVICE_SELECT": selector,
            "MESA_VK_DEVICE_SELECT_FORCE_DEFAULT_DEVICE": "1",
        }

    def get_gpu_launch_prefix(self, gpu_id=None):
        """Return an optional launch wrapper for the selected GPU."""
        if gpu_id is None:
            gpu_id = self.get_selected_gpu()

        if gpu_id.startswith("nvidia_"):
            switcherooctl = shutil.which("switcherooctl")
            if switcherooctl:
                return [switcherooctl, "launch", "env"]

        return []

    def get_current_backend(self):
        """Detect which graphics backend is currently being used (dxvk or vkd3d)"""
        # Check preference first (applies to all GPU types)
        preference = self.get_dxvk_vkd3d_preference()
        if preference == "dxvk":
            return "dxvk"
        elif preference == "vkd3d":
            return "vkd3d"

        # If no preference set, check if vkd3d DLLs exist
        wine_lib_dir = (
            self.get_wine_dir() / "lib" / "wine" / "vkd3d-proton" / "x86_64-windows"
        )
        if wine_lib_dir.exists() and (wine_lib_dir / "d3d12.dll").exists():
            return "vkd3d"

        # Default to DXVK (for AMD, NVIDIA, and other GPUs)
        return "dxvk"

    def get_dxvk_env_vars(self):
        """Get DXVK environment variables for AMD GPU or NVIDIA GPU with DXVK preference"""
        gpu_id = self.get_selected_gpu()
        if self.has_nvidia_gpu() and (
            gpu_id.startswith("nvidia_") or gpu_id.startswith("auto")
        ):
            preference = self.get_dxvk_vkd3d_preference()
            if preference == "dxvk":
                return 'DXVK_ASYNC=0 DXVK_CONFIG="d3d9.deferSurfaceCreation = True; d3d9.shaderModel = 1" '
        elif self.has_amd_gpu() and (
            gpu_id.startswith("amd_") or gpu_id.startswith("auto")
        ):
            return 'DXVK_ASYNC=0 DXVK_CONFIG="d3d9.deferSurfaceCreation = True; d3d9.shaderModel = 1" '
        return ""

    def get_vulkan_runtime_env_vars(self, gpu_id=None):
        """Return the Vulkan runtime environment shared by direct launches and desktop launchers."""
        session_type = (os.environ.get("XDG_SESSION_TYPE") or "").lower()
        if gpu_id is None:
            gpu_id = self.get_selected_gpu()

        env_vars = {
            "DXVK_ASYNC": "0",
            "DXVK_CONFIG": "d3d9.deferSurfaceCreation = True; d3d9.shaderModel = 1",
            "DXVK_LOG_LEVEL": "none",
            "VKD3D_DEBUG": "none",
            "VKD3D_FEATURE_LEVEL": "12_1",
            "VKD3D_SHADER_DEBUG": "none",
            "VKD3D_SHADER_MODEL": "6_5",
        }

        if session_type == "wayland":
            env_vars["VKD3D_DISABLE_EXTENSIONS"] = "VK_KHR_present_id,VK_KHR_present_wait"
            if self.has_nvidia_gpu() and (gpu_id.startswith("nvidia_") or gpu_id == "auto"):
                env_vars["VKD3D_CONFIG"] = "swapchain_legacy"
        else:
            env_vars["VKD3D_DISABLE_EXTENSIONS"] = "VK_KHR_present_id"

        return env_vars

    def get_desktop_launch_env_parts(self):
        """Return desktop-launch env assignments for the currently selected GPU/backend."""
        env_parts = []

        gpu_env = self.get_gpu_env_vars()
        if gpu_env:
            env_parts.extend(gpu_env.strip().split())

        if self.get_renderer_setting() == "vulkan":
            for key, value in self.get_vulkan_runtime_env_vars().items():
                if any(char.isspace() for char in value):
                    env_parts.append(f'{key}="{value}"')
                else:
                    env_parts.append(f"{key}={value}")

            vulkan_device_env = self.get_vulkan_device_select_env(self.get_selected_gpu())
            for key, value in vulkan_device_env.items():
                env_parts.append(f"{key}={value}")

        return env_parts

    def _configure_gpu_selection_safe(self):
        """Configure GPU selection for dual GPU setups (safe UI slot)"""
        gpus = self.detect_gpus()

        if len(gpus) <= 1:
            self.show_message(
                "GPU Selection",
                "Only one GPU detected or no GPUs found.\n\n"
                "GPU selection is only needed for dual GPU setups.\n"
                "Your system will use the default GPU automatically.",
                "info",
            )
            # Ensure waiting flag is cleared for background callers
            try:
                self.waiting_for_gpu_selection = False
            except Exception:
                pass
            return

        # Load current selection
        gpu_config_file = Path(self.directory) / ".gpu_config"
        current_gpu = "auto"
        if gpu_config_file.exists():
            try:
                with open(gpu_config_file, "r") as f:
                    current_gpu = f.read().strip()
            except Exception:
                pass

        # Create dialog for GPU selection (without parent to avoid threading issues)
        dialog = QDialog(self.dialog_parent())
        dialog.setWindowTitle("GPU Selection for Affinity Applications")
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Responsive sizing
        screen = dialog.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        if screen_width < 800 or screen_height < 600:
            min_width = min(400, int(screen_width * 0.9))
            min_height = min(300, int(screen_height * 0.8))
            default_width = min(500, int(screen_width * 0.85))
            default_height = min(350, int(screen_height * 0.7))
            max_width = int(screen_width * 0.95)
            max_height = int(screen_height * 0.85)
        else:
            min_width = 450
            min_height = 320
            default_width = 550
            default_height = 380
            max_width = 800
            max_height = 700

        dialog.setMinimumWidth(min_width)
        dialog.setMinimumHeight(min_height)
        dialog.setMaximumWidth(max_width)
        dialog.setMaximumHeight(max_height)
        dialog.resize(default_width, default_height)
        dialog.setSizeGripEnabled(True)

        # Apply theme stylesheet
        dialog.setStyleSheet(self.get_dialog_stylesheet())

        # Main layout with responsive margins
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(12)
        margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
        main_layout.setContentsMargins(margin, margin, margin, margin)

        # Title
        title_label = QLabel("GPU Selection for Affinity Applications")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(title_label)

        # Description
        desc_label = QLabel(
            "Select which GPU to use for Affinity applications:\n\n"
            "This is useful for dual GPU setups (e.g., Intel + NVIDIA, AMD + NVIDIA).\n"
            "If you want to enable OpenCL and have a NVIDIA GPU, it's recommended to select it for better compatibility.\n"
        )
        desc_label.setObjectName("descriptionLabel")
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(desc_label)

        # Options container with scroll area for better scaling
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        options_container = QFrame()
        options_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        options_layout = QVBoxLayout(options_container)
        options_layout.setSpacing(8)
        options_margin = 8 if (screen_width >= 800 and screen_height >= 600) else 6
        options_layout.setContentsMargins(
            options_margin, options_margin, options_margin, options_margin
        )

        scroll_area.setWidget(options_container)

        # Create radio buttons for each GPU
        button_group = QButtonGroup(dialog)
        radio_buttons = []

        # Add "Auto" option first
        auto_frame = QFrame()
        auto_frame.setObjectName("optionFrame")
        auto_layout = QVBoxLayout(auto_frame)
        auto_layout.setContentsMargins(12, 10, 12, 10)
        auto_radio = QRadioButton("Auto (System Default)")
        auto_radio.setChecked(current_gpu == "auto")
        auto_radio.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        auto_layout.addWidget(auto_radio)
        options_layout.addWidget(auto_frame)
        button_group.addButton(auto_radio, -1)
        radio_buttons.append(("auto", auto_radio))

        # Add detected GPUs
        for gpu in gpus:
            if gpu["id"] != "auto":  # Skip if it's the auto placeholder
                gpu_frame = QFrame()
                gpu_frame.setObjectName("optionFrame")
                gpu_layout = QVBoxLayout(gpu_frame)
                gpu_layout.setContentsMargins(12, 10, 12, 10)
                gpu_label = f"{gpu['name']} ({gpu['type'].upper()})"
                radio = QRadioButton(gpu_label)
                radio.setChecked(current_gpu == gpu["id"])
                radio.setSizePolicy(
                    QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
                )
                gpu_layout.addWidget(radio)
                options_layout.addWidget(gpu_frame)
                button_group.addButton(radio, gpus.index(gpu))
                radio_buttons.append((gpu["id"], radio))

        main_layout.addWidget(scroll_area, 1)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Continue")
        ok_btn.setObjectName("okButton")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)

        main_layout.addLayout(button_layout)

        # Ensure the dialog is large enough to show all content; clamp inside min/max.
        hint = dialog.sizeHint()
        target_w = min(max(default_width, hint.width()), max_width)
        target_h = min(max(default_height, hint.height()), max_height)
        target_w = max(target_w, min_width)
        target_h = max(target_h, min_height)
        dialog.resize(target_w, target_h)

        # Show dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_id = None
            for gpu_id, radio in radio_buttons:
                if radio.isChecked():
                    selected_id = gpu_id
                    break

            if selected_id:
                self.question_dialog_response = selected_id
                # Save selection
                try:
                    with open(gpu_config_file, "w") as f:
                        f.write(selected_id)

                    gpu_name = next(
                        (gpu["name"] for gpu in gpus if gpu["id"] == selected_id),
                        "Auto",
                    )
                    self.log(f"GPU selection saved: {gpu_name}", "success")

                    # Update existing desktop entries
                    self.update_existing_desktop_entries()

                    self.show_message(
                        "GPU Selection Saved",
                        f"Selected GPU: {gpu_name}\n\n"
                        "All existing desktop entries have been updated with the new GPU configuration.",
                        "info",
                    )
                except Exception as e:
                    self.log(f"Failed to save GPU selection: {e}", "error")
        else:
            # User cancelled - return "Cancel" to match expected format
            self.question_dialog_response = "Cancel"

        self.waiting_for_question_response = False
        self.waiting_for_gpu_selection = False

    def configure_gpu_selection(self):
        """Ask user to select GPU for dual-GPU setups (thread-safe)"""
        self.waiting_for_gpu_selection = True
        self.gpu_selection_signal.emit()

        # Block the calling thread until the main thread finishes the dialog
        max_wait = 3000  # 5 minutes max wait
        waited = 0
        while self.waiting_for_gpu_selection and waited < max_wait:
            import time

            time.sleep(0.1)
            waited += 1

    def get_switch_backend_button_text(self):
        """Get the text for the switch backend button based on current backend"""
        current = self.get_current_backend()
        if current == "dxvk":
            return "Switch to VKD3D"
        else:
            return "Switch to DXVK"

    def get_switch_backend_tooltip(self):
        """Get the tooltip for the switch backend button based on current backend"""
        current = self.get_current_backend()
        if current == "dxvk":
            return "Switch from DXVK to VKD3D (includes OpenCL support)"
        else:
            return "Switch from VKD3D to DXVK for graphics acceleration"

    def update_switch_backend_button(self):
        """Update the switch backend button text and tooltip"""
        if self.switch_backend_button:
            self.switch_backend_button.setText(self.get_switch_backend_button_text())
            self.switch_backend_button.setToolTip(self.get_switch_backend_tooltip())

    def switch_graphics_backend(self):
        """Switch between DXVK and VKD3D based on current backend"""
        current = self.get_current_backend()
        if current == "dxvk":
            self.switch_to_vkd3d()
        else:
            self.switch_to_dxvk()

    def switch_to_vkd3d(self):
        """Switch from DXVK to VKD3D, installing vkd3d-proton"""
        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Switch to VKD3D",
            "This will:\n\n"
            "• Install vkd3d-proton (Direct3D 12 on your GPU)\n"
            "• Install d3d12.dll and d3d12core.dll\n"
            "• Set preference to use VKD3D\n"
            "• Update all desktop entries to remove DXVK environment variables\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Switching to VKD3D", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        try:
            # 1. Install vkd3d-proton (full setup)
            self.log("Installing vkd3d-proton...", "info")
            self.setup_vkd3d()

            # 2. Set preference to VKD3D
            self.set_dxvk_vkd3d_preference("vkd3d")
            self.log("Set preference to VKD3D", "success")

            # 3. Remove DXVK DLL overrides and DLLs from system32 (if any)
            self.remove_dxvk_overrides()

            # 4. Set up DLL overrides for vkd3d
            self.log("Setting up DLL overrides for vkd3d...", "info")
            self.setup_d3d12_overrides()

            # 5. Copy DLLs to application directories
            self.log("Copying d3d12 DLLs to application directories...", "info")
            wine_lib_dir = (
                self.get_wine_dir() / "lib" / "wine" / "vkd3d-proton" / "x86_64-windows"
            )
            vkd3d_temp = Path(self.directory) / "vkd3d_dlls"

            app_dirs = {
                "Photo": "Photo 2",
                "Designer": "Designer 2",
                "Publisher": "Publisher 2",
                "Add": "Affinity",
            }

            for app_name, app_dir_name in app_dirs.items():
                app_dir = (
                    Path(self.directory)
                    / "drive_c"
                    / "Program Files"
                    / "Affinity"
                    / app_dir_name
                )
                if app_dir.exists():
                    for dll in ["d3d12.dll", "d3d12core.dll"]:
                        for source in [wine_lib_dir / dll, vkd3d_temp / dll]:
                            if source.exists():
                                shutil.copy2(source, app_dir / dll)
                                self.log(f"Copied {dll} to {app_dir_name}", "success")
                                break

            # 6. Update all desktop entries (remove DXVK env vars)
            self.log(
                "Updating desktop entries (removing DXVK environment variables)...",
                "info",
            )
            desktop_dir = Path.home() / ".local" / "share" / "applications"
            if not desktop_dir.exists():
                self.log("Desktop directory not found", "warning")
            else:
                affinity_desktop_files = [
                    desktop_dir / "AffinityPhoto.desktop",
                    desktop_dir / "AffinityDesigner.desktop",
                    desktop_dir / "AffinityPublisher.desktop",
                    desktop_dir / "Affinity.desktop",
                ]

                updated_count = 0
                for desktop_file in affinity_desktop_files:
                    if desktop_file.exists() and not (
                        self.manages_host_entries()
                        and self._entry_serves_this_prefix(desktop_file)
                    ):
                        continue
                    if not desktop_file.exists():
                        continue

                    try:
                        # Read the desktop file
                        with open(desktop_file, "r") as f:
                            lines = f.readlines()

                        # Find and update the Exec line
                        new_lines = []
                        exec_updated = False

                        for line in lines:
                            if line.startswith("Exec="):
                                # Parse the existing Exec line
                                exec_content = line[5:].strip()

                                # Extract app path
                                quoted_path_match = re.search(
                                    r'wine\s+"([^"]+)"', exec_content
                                )
                                if quoted_path_match:
                                    app_path = quoted_path_match.group(1)
                                else:
                                    # Path wasn't cleanly quoted — don't guess by
                                    # splitting on whitespace (a bare space inside
                                    # "Program Files" would truncate the path).
                                    # Recompute it deterministically instead.
                                    app_path = self._infer_app_path_for_desktop_file(
                                        desktop_file
                                    )

                                # Get wine path
                                wine = self.get_wine_path("wine")
                                wine_path = str(wine)

                                desktop_env_parts = self.get_desktop_launch_env_parts()
                                directory_str = str(self.directory).rstrip("/")

                                # Rebuild Exec line with the current launch environment
                                exec_line = f"Exec=env WINEPREFIX={directory_str}"
                                if desktop_env_parts:
                                    exec_line += f' {" ".join(desktop_env_parts)}'
                                exec_line += f" {wine_path}"
                                if app_path:
                                    if " " in app_path or not app_path.startswith("/"):
                                        exec_line += f' "{app_path}"'
                                    else:
                                        exec_line += f" {app_path}"

                                new_lines.append(exec_line + "\n")
                                exec_updated = True
                            else:
                                new_lines.append(line)

                        # Write back if Exec line was updated
                        if exec_updated:
                            with open(desktop_file, "w") as f:
                                f.writelines(new_lines)
                            updated_count += 1
                            self.log(
                                f"Updated desktop entry: {desktop_file.name}", "success"
                            )

                    except Exception as e:
                        self.log(
                            f"Failed to update {desktop_file.name}: {e}", "warning"
                        )

                if updated_count > 0:
                    self.log(
                        f"Updated {updated_count} desktop entry/entries", "success"
                    )

            # Update button text
            self.update_switch_backend_button()
            self.create_affinity_url_handler()

            self.show_message(
                "Switch to VKD3D Complete",
                f"Successfully switched to VKD3D!\n\n"
                f"• Installed vkd3d-proton (Direct3D 12 on your GPU)\n"
                f"• Installed d3d12.dll and d3d12core.dll\n"
                f"• Removed DXVK DLL overrides\n"
                f"• Set up DLL overrides for d3d12 and d3d12core in Wine registry\n"
                f"• Updated {updated_count} desktop entry/entries\n"
                f"• All Affinity applications will now use VKD3D",
                "info",
            )

        except Exception as e:
            self.log(f"Error switching to VKD3D: {e}", "error")
            self.show_message(
                "Error", f"An error occurred while switching to VKD3D:\n\n{e}", "error"
            )

    def switch_to_dxvk(self):
        """Remove vkd3d and switch to DXVK using winetricks, updating all desktop entries"""
        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Switch to DXVK",
            "This will:\n\n"
            "• Remove vkd3d-proton DLLs from Wine and application directories\n"
            "• Install DXVK via winetricks\n"
            "• Reinstall d3d12.dll and d3d12core.dll (required for compatibility)\n"
            "• Set preference to use DXVK instead\n"
            "• Update all desktop entries to use DXVK environment variables\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Switching to DXVK", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        try:
            # 0. Kill wineserver to avoid version mismatch issues
            self.log("Stopping wineserver to avoid version conflicts...", "info")
            wineserver = self.get_wine_path("wineserver")
            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory
            self.run_command(
                [str(wineserver), "-k"], check=False, env=env, capture=True
            )
            import time

            time.sleep(1)  # Brief pause to ensure wineserver has stopped
            self.log("Wineserver stopped", "success")

            # 1. Remove vkd3d DLLs from Wine library directory
            wine_lib_dir = (
                self.get_wine_dir() / "lib" / "wine" / "vkd3d-proton" / "x86_64-windows"
            )
            if wine_lib_dir.exists():
                self.log("Removing vkd3d DLLs from Wine library directory...", "info")
                for dll in ["d3d12.dll", "d3d12core.dll", "dxgi.dll"]:
                    dll_path = wine_lib_dir / dll
                    if dll_path.exists():
                        dll_path.unlink()
                        self.log(f"Removed {dll} from Wine library", "success")

                # Try to remove parent directories if empty
                try:
                    if wine_lib_dir.exists() and not any(wine_lib_dir.iterdir()):
                        wine_lib_dir.rmdir()
                    parent = wine_lib_dir.parent
                    if parent.exists() and not any(parent.iterdir()):
                        parent.rmdir()
                except Exception:
                    pass  # Ignore errors removing directories

            # 2. Remove vkd3d_dlls directory
            vkd3d_temp = Path(self.directory) / "vkd3d_dlls"
            if vkd3d_temp.exists():
                self.log("Removing vkd3d_dlls directory...", "info")
                try:
                    shutil.rmtree(vkd3d_temp)
                    self.log("Removed vkd3d_dlls directory", "success")
                except Exception as e:
                    self.log(
                        f"Warning: Could not remove vkd3d_dlls directory: {e}",
                        "warning",
                    )

            # 3. Remove vkd3d DLLs from application directories
            app_dirs = {
                "Photo": "Photo 2",
                "Designer": "Designer 2",
                "Publisher": "Publisher 2",
                "Add": "Affinity",
            }

            for app_name, app_dir_name in app_dirs.items():
                app_dir = (
                    Path(self.directory)
                    / "drive_c"
                    / "Program Files"
                    / "Affinity"
                    / app_dir_name
                )
                if app_dir.exists():
                    for dll in ["d3d12.dll", "d3d12core.dll"]:
                        dll_path = app_dir / dll
                        if dll_path.exists():
                            dll_path.unlink()
                            self.log(f"Removed {dll} from {app_dir_name}", "success")

            # 4. Set preference to DXVK
            self.set_dxvk_vkd3d_preference("dxvk")
            self.log("Set preference to DXVK", "success")

            # 5. Remove vkd3d DLL overrides (if any)
            self.remove_d3d12_overrides()

            # 6. Install DXVK via winetricks
            self.log("Installing DXVK via winetricks...", "info")
            self.install_dxvk_dlls()

            # 7. Reinstall d3d12 DLLs and overrides (needed even with DXVK)
            self.log("Reinstalling d3d12 DLLs and setting up DLL overrides...", "info")
            self.install_d3d12_dlls()

            # 8. Copy DLLs back to application directories
            self.log("Copying d3d12 DLLs to application directories...", "info")
            wine_lib_dir = (
                self.get_wine_dir() / "lib" / "wine" / "vkd3d-proton" / "x86_64-windows"
            )
            vkd3d_temp = Path(self.directory) / "vkd3d_dlls"

            for app_name, app_dir_name in app_dirs.items():
                app_dir = (
                    Path(self.directory)
                    / "drive_c"
                    / "Program Files"
                    / "Affinity"
                    / app_dir_name
                )
                if app_dir.exists():
                    for dll in ["d3d12.dll", "d3d12core.dll"]:
                        # Try wine library first, then temp directory
                        for source in [wine_lib_dir / dll, vkd3d_temp / dll]:
                            if source.exists():
                                shutil.copy2(source, app_dir / dll)
                                self.log(f"Copied {dll} to {app_dir_name}", "success")
                                break

            # 9. Update all desktop entries
            self.log(
                "Updating desktop entries with DXVK environment variables...", "info"
            )
            desktop_dir = Path.home() / ".local" / "share" / "applications"
            if not desktop_dir.exists():
                self.log("Desktop directory not found", "warning")
            else:
                affinity_desktop_files = [
                    desktop_dir / "AffinityPhoto.desktop",
                    desktop_dir / "AffinityDesigner.desktop",
                    desktop_dir / "AffinityPublisher.desktop",
                    desktop_dir / "Affinity.desktop",
                ]

                updated_count = 0
                for desktop_file in affinity_desktop_files:
                    if desktop_file.exists() and not (
                        self.manages_host_entries()
                        and self._entry_serves_this_prefix(desktop_file)
                    ):
                        continue
                    if not desktop_file.exists():
                        continue

                    try:
                        # Read the desktop file
                        with open(desktop_file, "r") as f:
                            lines = f.readlines()

                        # Find and update the Exec line
                        new_lines = []
                        exec_updated = False

                        for line in lines:
                            if line.startswith("Exec="):
                                # Parse the existing Exec line
                                exec_content = line[5:].strip()  # Remove "Exec=" prefix

                                # Extract app path
                                quoted_path_match = re.search(
                                    r'wine\s+"([^"]+)"', exec_content
                                )
                                if quoted_path_match:
                                    app_path = quoted_path_match.group(1)
                                else:
                                    # Path wasn't cleanly quoted — don't guess by
                                    # splitting on whitespace (a bare space inside
                                    # "Program Files" would truncate the path).
                                    # Recompute it deterministically instead.
                                    app_path = self._infer_app_path_for_desktop_file(
                                        desktop_file
                                    )

                                # Get wine path
                                wine = self.get_wine_path("wine")
                                wine_path = str(wine)

                                desktop_env_parts = self.get_desktop_launch_env_parts()
                                directory_str = str(self.directory).rstrip("/")

                                # Rebuild Exec line with the current launch environment
                                exec_line = f"Exec=env WINEPREFIX={directory_str}"
                                if desktop_env_parts:
                                    exec_line += f' {" ".join(desktop_env_parts)}'
                                exec_line += f" {wine_path}"
                                if app_path:
                                    if " " in app_path or not app_path.startswith("/"):
                                        exec_line += f' "{app_path}"'
                                    else:
                                        exec_line += f" {app_path}"

                                new_lines.append(exec_line + "\n")
                                exec_updated = True
                            else:
                                new_lines.append(line)

                        # Write back if Exec line was updated
                        if exec_updated:
                            with open(desktop_file, "w") as f:
                                f.writelines(new_lines)
                            updated_count += 1
                            self.log(
                                f"Updated desktop entry: {desktop_file.name}", "success"
                            )

                    except Exception as e:
                        self.log(
                            f"Failed to update {desktop_file.name}: {e}", "warning"
                        )

                if updated_count > 0:
                    self.log(
                        f"Updated {updated_count} desktop entry/entries with DXVK configuration",
                        "success",
                    )

            # Update button text
            self.update_switch_backend_button()
            self.create_affinity_url_handler()

            self.show_message(
                "Switch to DXVK Complete",
                f"Successfully switched to DXVK!\n\n"
                f"• Removed vkd3d-proton DLLs\n"
                f"• Removed vkd3d DLL overrides\n"
                f"• Installed DXVK via winetricks\n"
                f"• Reinstalled d3d12.dll and d3d12core.dll (required for compatibility)\n"
                f"• Updated {updated_count} desktop entry/entries\n"
                f"• All Affinity applications will now use DXVK for graphics acceleration",
                "info",
            )

        except Exception as e:
            self.log(f"Error switching to DXVK: {e}", "error")
            self.show_message(
                "Error", f"An error occurred while switching to DXVK:\n\n{e}", "error"
            )

    def update_existing_desktop_entries(self):
        """Update existing desktop entries with current GPU configuration"""
        if not self.manages_host_entries():
            return
        desktop_dir = Path.home() / ".local" / "share" / "applications"
        if not desktop_dir.exists():
            return

        # Get current launch environment variables
        desktop_env_parts = self.get_desktop_launch_env_parts()
        launch_prefix = self.get_gpu_launch_prefix()
        directory_str = str(self.directory).rstrip("/")

        # Find all Affinity desktop entries
        affinity_desktop_files = [
            desktop_dir / "AffinityPhoto.desktop",
            desktop_dir / "AffinityDesigner.desktop",
            desktop_dir / "AffinityPublisher.desktop",
            desktop_dir / "Affinity.desktop",
        ]

        updated_count = 0
        for desktop_file in affinity_desktop_files:
            if not desktop_file.exists():
                continue

            try:
                # Read the desktop file
                with open(desktop_file, "r") as f:
                    lines = f.readlines()

                # Find and update the Exec line
                new_lines = []
                exec_updated = False

                for line in lines:
                    if line.startswith("Exec="):
                        # Parse the existing Exec line
                        exec_content = line[5:].strip()  # Remove "Exec=" prefix

                        # Use regex to extract the app path (everything after wine, typically in quotes or ending with .exe)
                        # Pattern 1: Find app path in quotes after wine
                        quoted_path_match = re.search(r'wine\s+"([^"]+)"', exec_content)
                        if quoted_path_match:
                            app_path = quoted_path_match.group(1)
                        else:
                            # Path wasn't cleanly quoted — don't guess by
                            # splitting on whitespace (a bare space inside
                            # "Program Files" would truncate the path down to
                            # just "Files/Affinity/Affinity/AffinityHook.exe").
                            # Recompute it deterministically instead.
                            app_path = self._infer_app_path_for_desktop_file(
                                desktop_file
                            )

                        # Get wine path (standard location)
                        wine = self.get_wine_path("wine")
                        wine_path = str(wine)

                        # Rebuild Exec line with new GPU env vars
                        exec_parts = ["Exec="]
                        if launch_prefix:
                            exec_parts.append(" ".join(shlex.quote(part) for part in launch_prefix))
                        exec_parts.append(f"env WINEPREFIX={directory_str}")
                        exec_parts.extend(desktop_env_parts)
                        exec_parts.append(wine_path)
                        if app_path:
                            # Quote the app path if it contains spaces or special characters
                            if " " in app_path or not app_path.startswith("/"):
                                exec_parts.append(f'"{app_path}"')
                            else:
                                exec_parts.append(app_path)
                        else:
                            # If we couldn't parse app_path, log a warning but still update GPU env
                            self.log(f"Warning: Could not parse app path from {desktop_file.name}, updating GPU env only", "warning")

                        new_lines.append(" ".join(exec_parts) + "\n")
                        exec_updated = True
                    else:
                        new_lines.append(line)

                # Write back if Exec line was updated
                if exec_updated:
                    with open(desktop_file, "w") as f:
                        f.writelines(new_lines)
                    updated_count += 1
                    self.log(f"Updated desktop entry: {desktop_file.name}", "info")

            except Exception as e:
                self.log(f"Failed to update {desktop_file.name}: {e}", "warning")

        if updated_count > 0:
            self.log(
                f"Updated {updated_count} desktop entry/entries with new GPU configuration",
                "success",
            )
        else:
            self.log("No desktop entries found to update", "info")

        # The affinity:// handler reuses the Exec= line of Affinity.desktop.
        self.create_affinity_url_handler()

    def format_distro_name(self, distro=None):
        """Format distribution name for display with proper capitalization"""
        if distro is None:
            distro = self.distro

        # Map lowercase distro IDs to proper display names
        distro_names = {
            "arch": "Arch",
            "cachyos": "CachyOS",
            "endeavouros": "EndeavourOS",
            "xerolinux": "XeroLinux",
            "fedora": "Fedora",
            "nobara": "Nobara",
            "opensuse-tumbleweed": "openSUSE Tumbleweed",
            "opensuse-leap": "openSUSE Leap",
            "pikaos": "PikaOS",
            "pop": "Pop!_OS",
            "ubuntu": "Ubuntu",
            "linuxmint": "Linux Mint",
            "zorin": "Zorin OS",
            "debian": "Debian",
            "manjaro": "Manjaro",
        }

        return distro_names.get(
            distro.lower() if distro else "", distro.title() if distro else "Unknown"
        )

    def is_ubuntu_family_distro(self, distro=None):
        """Return True for distributions that should use the Ubuntu compatibility path"""
        if distro is None:
            distro = self.distro
        return (distro or "").lower() in {"ubuntu", "linuxmint", "zorin", "pop"}

    def get_recommended_wine_version(self):
        """Return the preferred bundled Wine version for the current distro"""
        return "11.19"

    def get_wine_version_dialog_options(self):
        """Return Wine version labels and descriptions for UI prompts"""
        return [
            (
                "Wine 11.19 (Recommended)",
                "Latest build with the full Affinity patch set: Direct2D throughput and brush-latency fixes, wined3d Vulkan presentation fixes, OpenCL event dispatcher, pen pressure, plus color, printing and login fixes."
            ),
            (
                "Wine 11.18",
                "Previous build with the Affinity login fix and performance patches (D2D geometry cache, OpenCL cache, SDR white-level and printer mapping). Fallback if 11.19 has issues."
            ),
        ]

    def get_wine_version_prompt_message(self):
        """Build the shared Wine version chooser prompt"""
        option_lines = []
        for label, description in self.get_wine_version_dialog_options():
            option_lines.append(f"• {label} - {description}")

        note = "Note: You can switch versions later by running this setup again."

        return "Which Wine version would you like to install?\n\n" + "\n".join(option_lines) + f"\n\n{note}"

    def map_wine_dialog_choice_to_version(self, wine_choice):
        """Map a dialog label back to an internal Wine version"""
        if not wine_choice:
            return None
        if wine_choice.startswith("Wine 11.19"):
            return "11.19"
        if wine_choice.startswith("Wine 11.18"):
            return "11.18"
        if wine_choice.startswith("Wine 11.0"):
            return "11.0"
        if wine_choice.startswith("Wine 10.10"):
            return "10.10"
        if wine_choice.startswith("Wine 9.14"):
            return "9.14"
        return None

    def download_file(self, url, output_path, description=""):
        """Download file with progress tracking"""
        try:
            # Check if cancelled before starting
            if self.check_cancelled():
                return False

            self.log(f"Downloading {description}...", "info")

            # Create request with proper headers
            req = urllib.request.Request(url)
            req.add_header(
                "User-Agent",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            )
            req.add_header("Accept", "*/*")

            # Use urlopen for better header support and manual progress tracking
            with urllib.request.urlopen(req) as response:
                total_size = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                block_size = 8192

                with open(output_path, "wb") as out_file:
                    while True:
                        # Check for cancellation during download
                        if self.check_cancelled():
                            self.log(f"Download of {description} cancelled", "warning")
                            return False

                        chunk = response.read(block_size)
                        if not chunk:
                            break
                        out_file.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            percent = min(100, (downloaded * 100) // total_size)
                            self.update_progress(percent / 100.0)

                self.update_progress(1.0)
                return True
        except urllib.error.HTTPError as e:
            self.log(f"Download failed: HTTP {e.code} {e.reason}", "error")
            if e.code == 404:
                self.log(f"  URL may be expired or invalid: {url[:80]}...", "warning")
            return False
        except Exception as e:
            self.log(f"Download failed: {e}", "error")
            return False

    def start_initialization(self):
        """Start initialization process"""
        threading.Thread(target=self.initialize, daemon=True).start()

    def initialize(self):
        """Initialize installer"""
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Affinity Linux Installer - Initialization", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Detect distribution
        self.update_progress(0.1)
        if not self.detect_distro():
            self.log("Failed to detect distribution. Exiting.", "error")
            return

        self.log(
            f"Detected distribution: {self.format_distro_name()} {self.distro_version or ''}",
            "success",
        )
        self.update_progress(0.2)

        # Check dependencies
        if not self.check_dependencies():
            return

        # Check if Wine is already set up
        wine = self.get_wine_path("wine")
        if wine.exists():
            self.log("Wine is already set up", "success")
        else:
            self.log(
                "Wine is not set up. Use 'Setup Wine Environment' to install it.",
                "info",
            )

        # Show main menu (Wine setup can be done manually if needed)
        self.update_progress(1.0)
        self.show_main_menu_signal.emit()

    def _install_location_config_file(self):
        """Path to the small file that remembers a custom install location
        across app restarts. Stored outside the wine prefix itself (it can't
        live inside self.directory — that's the very thing it needs to
        remember)."""
        return Path.home() / ".config" / "AffinityOnLinux" / "install_location"

    def _load_persisted_install_location(self):
        """Restore a previously-chosen custom install location, if any, so
        features like Uninstall, Launch, and Update keep working against the
        right folder across app restarts. Falls back silently to the default
        ~/.AffinityLinux if nothing was saved or the saved value looks bad."""
        try:
            config_file = self._install_location_config_file()
            if config_file.exists():
                saved = config_file.read_text().strip()
                if saved:
                    self.directory = saved
        except Exception:
            pass

    def _save_install_location(self, directory):
        """Persist the chosen install location so it survives app restarts."""
        try:
            config_file = self._install_location_config_file()
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.write_text(str(directory))
        except Exception as e:
            self.log(f"Warning: could not save install location preference: {e}", "warning")

    def _clear_persisted_install_location(self):
        """Forget a saved custom install location (called after uninstall so
        a later run doesn't keep pointing at a folder that no longer exists)."""
        try:
            config_file = self._install_location_config_file()
            if config_file.exists():
                config_file.unlink()
        except Exception:
            pass

    def one_click_setup(self):
        """One-click full setup: detects distro, installs deps, sets up Wine, installs Winetricks deps"""
        # Nothing to ask when the caller named the directory.
        if self._forced_directory:
            self.log(f"Installing into {self.directory} (set by the caller)", "info")
            location_reply = None
        else:
            # Ask up front whether the user wants to install somewhere other than
            # the default location, before anything else happens.
            location_reply = QMessageBox.question(
                self,
                "Custom Install Location",
                "Do you want to choose a custom install location?\n\n"
                f"Default location:\n{self.directory}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

        if location_reply == QMessageBox.StandardButton.Yes:
            chosen_dir = QFileDialog.getExistingDirectory(
                self,
                "Select Install Location",
                str(Path.home()),
                QFileDialog.Option.ShowDirsOnly,
            )
            if chosen_dir:
                # Install into a dedicated subfolder rather than dumping the
                # Wine prefix (drive_c, dosdevices, etc.) directly into
                # whatever folder the user picked.
                self.directory = str(Path(chosen_dir) / ".AffinityLinux")
                self._save_install_location(self.directory)
                self.log(f"Custom install location selected: {self.directory}", "info")
            else:
                self.log(
                    "No custom location selected — using default install location.",
                    "info",
                )

        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("One-Click Full Setup", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        self.log(f"Install location: {self.directory}", "info")
        self.log("This will automatically:", "info")
        self.log("  1. Detect your Linux distribution", "info")
        self.log("  2. Check and install system dependencies", "info")
        self.log("  3. Setup Wine environment (download and configure)", "info")
        self.log("  4. Install Winetricks dependencies (.NET, fonts, etc.)", "info")
        self.log("  5. Prompt you to install an Affinity application\n", "info")

        threading.Thread(target=self._one_click_setup_thread, daemon=True).start()

    def _one_click_setup_thread(self):
        """One-click setup in background thread"""
        self.start_operation("One-Click Full Setup")

        # Ensure patcher files are available
        self.ensure_patcher_files()

        # Ask which GPU to use (for multi GPUs systems)
        gpus = self.detect_gpus()
        gpu_config_file = Path(self.directory) / ".gpu_config"
        if not gpu_config_file.exists() and len(gpus) > 2:
            self.configure_gpu_selection()

        if self.check_cancelled():
            return

        # Ask about OpenCL support (only if not already configured)
        opencl_config_file = Path(self.directory) / ".opencl_enabled"
        if not opencl_config_file.exists():
            # This question was titled "Enable OpenCL Support?", and it was
            # answered as one -- "No" sounded like the safe choice, given that
            # OpenCL hangs Affinity on newer Wine. But what "Yes" actually
            # installs is the GPU renderer (vkd3d-proton, or DXVK on AMD), and
            # "No" left Affinity drawing in software with an "unsupported
            # graphics card" warning. OpenCL itself is handled separately by
            # disable_opencl_if_needed, whatever is answered here.
            opencl_reply = self.show_question_dialog(
                "Use your graphics card?",
                "Affinity draws its canvas with Direct3D 12. To do that on your "
                "graphics card under Wine it needs a translation layer: "
                "vkd3d-proton (DXVK on AMD cards), which this sets up. "
                "Without it, Affinity falls back to slow software rendering and "
                "reports an unsupported graphics card.\n\n"
                "Recommended: Yes.\n\n"
                "About OpenCL: with Yes, Affinity can also use OpenCL "
                "acceleration on the recommended Wine 11.19. On Wine 11.11 to "
                "11.18 OpenCL stays switched off whichever you choose, because "
                "there it made Affinity hang at startup; 11.19 carries the fix.\n\n"
                "You can change this later.",
                ["Yes", "No"],
            )

            if opencl_reply == "Yes":
                self.enable_opencl = True
                self.log("GPU rendering (vkd3d-proton) will be set up", "info")

                # Check if AMD GPU is detected and install additional dependencies based on distribution
                if self.has_amd_gpu():
                    self.log(
                        "AMD GPU detected - installing additional OpenCL dependencies...",
                        "info",
                    )

                    amd_deps = []
                    install_cmd = None

                    # Fedora
                    if self.distro == "fedora":
                        # Check if Fedora 43 - use different dependencies
                        if self.distro_version == "43":
                            amd_deps = [
                                "mesa-opencl-icd",
                                "ocl-icd",
                                "rocm-opencl",
                                "rocm-hip",
                                "wine-opencl",
                            ]
                            self.log(
                                "Fedora 43 detected - installing Fedora 43 specific AMD OpenCL dependencies...",
                                "info",
                            )
                        else:
                            # Use older dependencies for other Fedora versions
                            amd_deps = [
                                "rocm-opencl",
                                "apr",
                                "apr-util",
                                "zlib",
                                "libxcrypt-compat",
                                "libcurl",
                                "libcurl-devel",
                                "mesa-libGLU",
                            ]
                        install_cmd = ["sudo", "dnf", "install", "-y"] + amd_deps

                    # Arch-based distributions (Arch, Artix, CachyOS, EndeavourOS, XeroLinux)
                    elif self.distro in ["arch", "artix", "cachyos", "endeavouros", "xerolinux"]:
                        # Arch uses different package names than Fedora
                        amd_deps = [
                            "opencl-mesa",
                            "ocl-icd",
                            "rocm-opencl-runtime",
                            "rocm-hip",
                            "wine-opencl",
                        ]
                        self.log(
                            f"{self.format_distro_name()} detected - installing Arch-based AMD OpenCL dependencies...",
                            "info",
                        )
                        install_cmd = [
                            "sudo",
                            "pacman",
                            "-S",
                            "--needed",
                            "--noconfirm",
                        ] + amd_deps

                    # PikaOS (Ubuntu/Debian-based)
                    elif self.distro == "pikaos":
                        # PikaOS uses Debian/Ubuntu package names
                        amd_deps = [
                            "mesa-opencl-icd",
                            "ocl-icd-libopencl1",
                            "rocm-opencl-runtime",
                            "rocm-hip-runtime",
                        ]
                        self.log(
                            "PikaOS detected - installing Debian/Ubuntu-based AMD OpenCL dependencies...",
                            "info",
                        )
                        install_cmd = ["sudo", "apt", "install", "-y"] + amd_deps

                    # Install dependencies if we have a command
                    if install_cmd and amd_deps:
                        self.log(f"Installing: {', '.join(amd_deps)}", "info")
                        success, stdout, stderr = self.run_command(install_cmd)

                        if success:
                            self.log(
                                "AMD OpenCL dependencies installed successfully",
                                "success",
                            )
                        else:
                            self.log(
                                f"Warning: Failed to install some AMD OpenCL dependencies: {stderr}",
                                "warning",
                            )
                            self.log(
                                "OpenCL may still work, but some features might be limited",
                                "warning",
                            )
            else:
                self.enable_opencl = False
                self.log("GPU rendering not chosen: Affinity will render in software", "info")

            # Save OpenCL preference
            try:
                with open(opencl_config_file, "w") as f:
                    f.write("1" if self.enable_opencl else "0")
            except Exception as e:
                self.log(f"Failed to save OpenCL preference: {e}", "warning")
        else:
            # Load existing preference
            self.enable_opencl = self.is_opencl_enabled()
            if self.enable_opencl:
                self.log("GPU rendering is set up (from previous setup)", "info")
            else:
                self.log("GPU rendering is not set up (from previous setup)", "info")

        if self.check_cancelled():
            return

        # Step 1: Detect distribution
        self.update_progress_text("Step 1/4: Detecting Linux distribution...")
        self.update_progress(0.05)

        if self.check_cancelled():
            return

        if not self.detect_distro():
            self.log("Failed to detect distribution. Cannot continue.", "error")
            self.update_progress_text("Ready")
            self.end_operation()
            return

        self.log(
            f"Detected distribution: {self.format_distro_name()} {self.distro_version or ''}",
            "success",
        )

        if self.check_cancelled():
            return

        # Step 2: Check and install dependencies
        self.update_progress_text(
            "Step 2/4: Checking and installing system dependencies..."
        )
        self.update_progress(0.15)

        if self.check_cancelled():
            return

        if not self.check_dependencies():
            self.log(
                "Dependency check failed. Please resolve issues and try again.", "error"
            )
            self.update_progress_text("Ready")
            self.end_operation()

            # Show retry dialog
            reply = self.show_question_dialog(
                "Dependency Check Failed",
                "Dependency check failed. Please resolve issues and try again.\n\n"
                "Would you like to retry the dependency check?",
                ["Yes", "No"],
            )

            if reply == "Yes":
                # Retry dependency check
                return self._one_click_setup_thread()
            else:
                self.end_operation()
                return

        if self.check_cancelled():
            return

        # Step 3: Setup Wine environment (this includes winetricks dependencies via configure_wine)
        self.update_progress_text("Step 3/4: Setting up Wine environment...")
        self.update_progress(0.40)

        if self.check_cancelled():
            return

        # Ask user to choose Wine version
        wine_version = self.show_question_dialog(
            "Choose Wine Version",
            "Which Wine version would you like to install?\n\n"
            "• Wine 11.19 (Recommended) - Latest build with the full Affinity patch set: Direct2D throughput and brush-latency fixes, wined3d Vulkan presentation fixes, OpenCL event dispatcher, pen pressure, plus color, printing and login fixes.\n"
            "• Wine 11.18 - Previous build with the Affinity login fix and performance patches (D2D geometry cache, OpenCL cache, SDR white-level and printer mapping). Fallback if 11.19 has issues.\n\n"
            "Note: You can switch versions later by running 'Setup Wine Environment' again.",
            ["Wine 11.19 (Recommended)", "Wine 11.18"],
        )

        if wine_version == "Wine 11.19 (Recommended)":
            wine_version_choice = "11.19"
        elif wine_version == "Wine 11.18":
            wine_version_choice = "11.18"
        else:
            self.log("Wine setup cancelled", "warning")
            self.end_operation()
            return

        # setup_wine() returns False when it gives up -- most often because the
        # Wine download failed. Its return value used to be discarded, so a failed
        # download only appeared in the log while the flow carried on to DPI
        # configuration and beyond against a prefix that has no Wine in it.
        if not self.setup_wine(wine_version_choice):
            if not self.check_cancelled():
                self.log("Wine setup failed; stopping here", "error")
                self.show_message(
                    "Wine setup failed",
                    "Wine could not be set up, so the rest of the installation "
                    "was skipped.\n\nThe usual cause is a failed download. See "
                    "the log for the exact error, then try again -- or pick a "
                    "different Wine version.",
                    "error",
                )
                self.end_operation()
            return

        if self.check_cancelled():
            return

        # Auto-configure Affinity DPI scaling based on host display resolution.
        # Runs on the GUI thread via signal so it is safe under Wayland/Qt.
        self.update_progress_text("Step 3.5/5: Auto-configuring DPI scaling for your display...")
        self.apply_auto_dpi_signal.emit()

        if self.check_cancelled():
            return

        # Step 4: Install Affinity v3 settings to enable settings saving
        self.update_progress_text("Step 4/5: Installing Affinity v3 settings...")
        self.update_progress(0.80)

        if self.check_cancelled():
            return

        self.log("Installing Affinity v3 settings files...", "info")
        self._install_affinity_settings_thread()

        if self.check_cancelled():
            return

        # Step 5: Install AffinityPluginLoader + WineFix
        self.update_progress_text(
            "Step 5/5: Installing AffinityPluginLoader + WineFix..."
        )
        self.update_progress(0.90)

        if self.check_cancelled():
            return

        install_dir = (
            Path(self.directory) / "drive_c" / "Program Files" / "Affinity" / "Affinity"
        )
        if install_dir.exists():
            self.log("\nInstalling AffinityPluginLoader + WineFix...", "info")
            self._install_affinity_plugin_loader_thread(standalone=False)
        else:
            self.log(
                "\nSkipping AffinityPluginLoader install - Affinity not yet installed.",
                "info",
            )
            self.log(
                "Use the 'Install AffinityPluginLoader' button after installing Affinity.",
                "info",
            )

        if self.check_cancelled():
            return

        # Complete!
        self.update_progress(1.0)
        # "Setup Complete!" read as "Affinity is installed" -- after a button
        # labelled Create and install, most of all. It is not: this is the
        # environment, and Affinity itself is the next step.
        self.update_progress_text("Wine is ready — Affinity is not installed yet")
        self.log("\n✓ Wine and everything Affinity needs are set up.", "success")
        self.log(
            "Affinity itself is not installed yet: that is the next step, "
            "offered now, or use the install buttons above.", "info"
        )

        # End operation
        self.end_operation()

        # Refresh installation status to update button states
        self.refresh_status_signal.emit()

        # Ask if user wants to install an Affinity app
        self.prompt_affinity_install_signal.emit()

    def _prompt_affinity_install(self):
        """Prompt user to install an Affinity application"""
        reply = QMessageBox.question(
            self,
            "Install Affinity now?",
            "Wine and everything Affinity needs are ready.\n\n"
            "Affinity itself is not installed yet. Install it now? This "
            "downloads Affinity's installer and runs it in this prefix.\n\n"
            "(No leaves the prefix ready, without Affinity; the install "
            "buttons can do it later.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Show a dialog to select which app (without parent to avoid threading issues)
            dialog = QDialog(self.dialog_parent())
            dialog.setWindowTitle("Select Affinity Application")
            dialog.setModal(True)
            dialog.setWindowFlags(
                dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
            )

            # Responsive sizing
            screen = dialog.screen().availableGeometry()
            screen_width = screen.width()
            screen_height = screen.height()

            if screen_width < 800 or screen_height < 600:
                min_width = min(400, int(screen_width * 0.9))
                min_height = min(300, int(screen_height * 0.7))
                default_width = min(500, int(screen_width * 0.85))
                default_height = min(350, int(screen_height * 0.65))
                max_width = int(screen_width * 0.95)
                max_height = int(screen_height * 0.85)
            elif screen_width < 1280 or screen_height < 720:
                min_width = 450
                min_height = 320
                default_width = 550
                default_height = 380
                max_width = int(screen_width * 0.9)
                max_height = int(screen_height * 0.85)
            else:
                min_width = 450
                min_height = 320
                default_width = 550
                default_height = 380
                max_width = 800
                max_height = 700

            dialog.setMinimumWidth(min_width)
            dialog.setMinimumHeight(min_height)
            dialog.setMaximumWidth(max_width)
            dialog.setMaximumHeight(max_height)
            dialog.resize(default_width, default_height)
            dialog.setSizeGripEnabled(True)
            dialog.setStyleSheet(self.get_dialog_stylesheet())

            # Main layout
            main_layout = QVBoxLayout(dialog)
            main_layout.setSpacing(12)
            margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
            main_layout.setContentsMargins(margin, margin, margin, margin)

            # Title
            title_label = QLabel("Select Affinity Application")
            title_label.setObjectName("titleLabel")
            title_label.setWordWrap(True)
            title_label.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
            )
            main_layout.addWidget(title_label)

            # Description
            desc_label = QLabel("Which Affinity application would you like to install?")
            desc_label.setObjectName("descriptionLabel")
            desc_label.setWordWrap(True)
            desc_label.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
            )
            main_layout.addWidget(desc_label)

            # Options container with scroll area for better scaling
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll_area.setFrameShape(QFrame.Shape.NoFrame)
            scroll_area.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )

            options_container = QFrame()
            options_container.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
            )
            options_layout = QVBoxLayout(options_container)
            options_layout.setSpacing(8)
            options_margin = 8 if (screen_width >= 800 and screen_height >= 600) else 6
            options_layout.setContentsMargins(
                options_margin, options_margin, options_margin, options_margin
            )

            scroll_area.setWidget(options_container)

            button_group = QButtonGroup()
            apps = [
                ("Add", "Affinity (Unified)"),
                ("Photo", "Affinity Photo"),
                ("Designer", "Affinity Designer"),
                ("Publisher", "Affinity Publisher"),
            ]

            radio_buttons = {}
            for idx, (app_code, app_name) in enumerate(apps):
                app_frame = QFrame()
                app_frame.setObjectName("optionFrame")
                app_layout = QVBoxLayout(app_frame)
                app_layout.setContentsMargins(12, 10, 12, 10)
                radio = QRadioButton(app_name)
                if app_code == "Add":
                    radio.setChecked(True)
                radio.setSizePolicy(
                    QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
                )
                app_layout.addWidget(radio)
                options_layout.addWidget(app_frame)
                button_group.addButton(radio, idx)
                radio_buttons[idx] = app_code

            main_layout.addWidget(scroll_area, 1)

            # Buttons
            button_layout = QHBoxLayout()
            button_layout.setSpacing(10)
            button_layout.addStretch()

            cancel_btn = QPushButton("Cancel")
            cancel_btn.setSizePolicy(
                QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
            )
            cancel_btn.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_btn)

            ok_btn = QPushButton("Continue")
            ok_btn.setObjectName("okButton")
            ok_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
            ok_btn.setDefault(True)
            ok_btn.clicked.connect(dialog.accept)
            button_layout.addWidget(ok_btn)

            main_layout.addLayout(button_layout)

            # Ensure the dialog is large enough to show all content; clamp inside min/max.
            hint = dialog.sizeHint()
            target_w = min(max(default_width, hint.width()), max_width)
            target_h = min(max(default_height, hint.height()), max_height)
            target_w = max(target_w, min_width)
            target_h = max(target_h, min_height)
            dialog.resize(target_w, target_h)

            # Show dialog
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

            if dialog.exec() == QDialog.DialogCode.Accepted:
                checked_id = button_group.checkedId()
                if checked_id >= 0 and checked_id in radio_buttons:
                    app_code = radio_buttons[checked_id]
                    self.install_application_signal.emit(app_code)

    def install_application(self, app_code):
        """Install an Affinity application - asks user if they want to download or provide their own exe"""
        app_names = {
            "Add": "Affinity (Unified)",
            "Photo": "Affinity Photo",
            "Designer": "Affinity Designer",
            "Publisher": "Affinity Publisher",
        }
        display_name = app_names.get(app_code, "Affinity")

        # A pinned installer answers the download-or-provide question before it
        # is asked. Checked before Wine so the message order matches the normal
        # path; the Wine check below still gates the install itself.
        pinned = override_installer_file()

        # Check if Wine is set up
        wine = self.get_wine_path("wine")
        if not wine.exists():
            self.log(
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            self.show_message(
                "Wine Not Found",
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            return

        # A pinned installer skips the dialog: the caller has already decided
        # which build to install, and asking would let a click undo the pin.
        if pinned:
            self.log(
                f"\nInstalling {display_name} from a pinned installer: {pinned}",
                "info",
            )
            self.start_operation(f"Install {display_name}")
            threading.Thread(
                target=self._run_installation_entry,
                args=(app_code, pinned),
                daemon=True,
            ).start()
            return

        # Ask user if they want to download or provide their own exe (without parent to avoid threading issues)
        dialog = QDialog(self.dialog_parent())
        dialog.setWindowTitle(f"Install {display_name}")
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Responsive sizing
        screen = dialog.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        if screen_width < 800 or screen_height < 600:
            min_width = min(400, int(screen_width * 0.9))
            min_height = min(280, int(screen_height * 0.7))
            default_width = min(500, int(screen_width * 0.85))
            default_height = min(320, int(screen_height * 0.65))
            max_width = int(screen_width * 0.95)
            max_height = int(screen_height * 0.85)
        elif screen_width < 1280 or screen_height < 720:
            min_width = 450
            min_height = 300
            default_width = 550
            default_height = 350
            max_width = int(screen_width * 0.9)
            max_height = int(screen_height * 0.85)
        else:
            min_width = 450
            min_height = 300
            default_width = 550
            default_height = 350
            max_width = 800
            max_height = 600

        dialog.setMinimumWidth(min_width)
        dialog.setMinimumHeight(min_height)
        dialog.setMaximumWidth(max_width)
        dialog.setMaximumHeight(max_height)
        dialog.resize(default_width, default_height)
        dialog.setSizeGripEnabled(True)
        dialog.setStyleSheet(self.get_dialog_stylesheet())

        # Main layout
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(12)
        margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
        main_layout.setContentsMargins(margin, margin, margin, margin)

        # Title
        title_label = QLabel(f"Install {display_name}")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(title_label)

        # Description
        desc_label = QLabel(f"How would you like to get the {display_name} installer?")
        desc_label.setObjectName("descriptionLabel")
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(desc_label)

        # Options container with scroll area for better scaling
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        options_container = QFrame()
        options_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        options_layout = QVBoxLayout(options_container)
        options_layout.setSpacing(8)
        options_margin = 8 if (screen_width >= 800 and screen_height >= 600) else 6
        options_layout.setContentsMargins(
            options_margin, options_margin, options_margin, options_margin
        )

        scroll_area.setWidget(options_container)

        button_group = QButtonGroup()

        # Download option
        download_frame = QFrame()
        download_frame.setObjectName("optionFrame")
        download_layout = QVBoxLayout(download_frame)
        download_layout.setContentsMargins(12, 10, 12, 10)
        download_radio = QRadioButton("Download from Affinity Studio (automatic)")
        download_radio.setChecked(True)
        download_radio.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        download_layout.addWidget(download_radio)
        options_layout.addWidget(download_frame)
        button_group.addButton(download_radio, 0)

        # Custom option
        custom_frame = QFrame()
        custom_frame.setObjectName("optionFrame")
        custom_layout = QVBoxLayout(custom_frame)
        custom_layout.setContentsMargins(12, 10, 12, 10)
        custom_radio = QRadioButton("Provide my own installer file (.exe)")
        custom_radio.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        custom_layout.addWidget(custom_radio)
        options_layout.addWidget(custom_frame)
        button_group.addButton(custom_radio, 1)

        # Installers kept by earlier installs, newest version first.
        kept = kept_installers() if app_code == "Add" else []
        for n, (version, path, downloaded) in enumerate(kept):
            kept_frame = QFrame()
            kept_frame.setObjectName("optionFrame")
            kept_layout = QVBoxLayout(kept_frame)
            kept_layout.setContentsMargins(12, 10, 12, 10)
            kept_radio = QRadioButton(
                f"Use the Affinity {version} installer, downloaded "
                f"{time.strftime('%Y-%m-%d', time.localtime(downloaded))}")
            kept_radio.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
            if n == 0:
                # The newest kept installer is the default: no 650 MB download,
                # and the version is known. Download is one click away.
                kept_radio.setChecked(True)
            kept_layout.addWidget(kept_radio)
            options_layout.addWidget(kept_frame)
            button_group.addButton(kept_radio, 2 + n)

        main_layout.addWidget(scroll_area, 1)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Continue")
        ok_btn.setObjectName("okButton")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)

        main_layout.addLayout(button_layout)

        # Ensure the dialog is large enough to show all content; clamp inside min/max.
        hint = dialog.sizeHint()
        target_w = min(max(default_width, hint.width()), max_width)
        target_h = min(max(default_height, hint.height()), max_height)
        target_w = max(target_w, min_width)
        target_h = max(target_h, min_height)
        dialog.resize(target_w, target_h)

        # Show dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        if dialog.exec() == QDialog.DialogCode.Accepted:
            checked_id = button_group.checkedId()
            installer_path = None

            if checked_id == 0:  # Download
                # Download the installer in background, then install
                self.log(
                    f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                self.log(f"Downloading {display_name} Installer", "info")
                self.log(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                )

                download_url = "https://downloads.affinity.studio/Affinity%20x64.exe"
                # Download to .AffinityLinux/Installer/ directory
                download_dir = Path(self.directory) / "Installer"
                download_dir.mkdir(parents=True, exist_ok=True)
                installer_path = download_dir / "Affinity-x64.exe"
                self.log(f"Downloading to: {installer_path}", "info")

                self.start_operation(f"Install {display_name}")
                threading.Thread(
                    target=self._download_then_install,
                    args=(app_code, display_name, download_url, str(installer_path)),
                    daemon=True,
                ).start()
                return

            elif checked_id >= 2:  # an installer kept by an earlier install
                version, installer_path, _ = kept[checked_id - 2]
                self.log(f"Using the kept Affinity {version} installer: {installer_path}", "info")

            else:  # Provide own file
                # Open file dialog to select .exe
                self.log(
                    f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                self.log(f"Custom Installer for {display_name}", "info")
                self.log(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                )
                self.log("Please select the installer .exe file...", "info")

                installer_path, _ = QFileDialog.getOpenFileName(
                    self,
                    f"Select {display_name} Installer",
                    "",
                    "Executable files (*.exe);;All files (*.*)",
                )

                if not installer_path:
                    self.log("Installation cancelled.", "warning")
                    return
                # QFileDialog returns a string, but we'll normalize it
                installer_path = Path(installer_path)

            # Verify file exists and convert to string for run_installation
            installer_path_str = str(installer_path)
            if not Path(installer_path_str).exists():
                self.log(f"Installer file not found: {installer_path_str}", "error")
                return

            # Start operation and installation in background thread
            self.start_operation(f"Install {display_name}")
            threading.Thread(
                target=self._run_installation_entry,
                args=(app_code, installer_path_str),
                daemon=True,
            ).start()

    def _keep_installer(self, installer, installed_exe):
        """Name the installer by the version it installed, here and in the
        shared folder kept_installers_dir(), keeping its download date."""
        version = pe_file_version(installed_exe)
        if not version or not Path(installer).exists():
            return
        name = f"Affinity-x64-{version}.exe"
        try:
            kept = kept_installers_dir() / name
            if not kept.exists():
                kept.parent.mkdir(parents=True, exist_ok=True)
                tmp = kept.with_name(name + ".part")
                shutil.copy2(installer, tmp)          # copy2 keeps the date
                tmp.replace(kept)
                self.log(f"Installer kept for later installs: {kept}", "info")
            installer = Path(installer)
            if installer.parent == Path(self.directory) / "Installer" and installer.name != name:
                installer.replace(installer.with_name(name))
        except OSError as e:
            self.log(f"Could not keep the installer: {e}", "warning")

    def _download_then_install(
        self, app_code, display_name, download_url, installer_path_str
    ):
        """Download installer then run installation (runs in background)."""
        try:
            self.log(f"Downloading from: {download_url}", "info")
            if not self.download_file(
                download_url, installer_path_str, f"{display_name} installer"
            ):
                self.log(
                    "Download failed. Please try providing your own installer file.",
                    "error",
                )
                self.show_message(
                    "Download Failed",
                    "Failed to download the installer.\n\nYou can download it manually from:\nhttps://downloads.affinity.studio/Affinity%20x64.exe\n\nThen use 'Provide my own installer file' option.",
                    "error",
                )
                # End the operation because run_installation won't be called
                self.end_operation()
                return
            self.log(f"Download completed: {installer_path_str}", "success")
            # Proceed to install (will end operation in wrapper)
            self._run_installation_entry(app_code, installer_path_str)
        except Exception as e:
            self.log(f"Error during download+install: {e}", "error")
            self.end_operation()

    def check_dependencies(self):
        """Check and install dependencies"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Dependency Verification", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        self.update_progress_text("Checking dependencies...")
        self.update_progress(0.0)

        # Show unsupported warning
        if self.distro in ["bazzite"]:
            self.show_unsupported_warning()

        missing = []
        deps = ["wine", "winetricks", "wget", "curl", "tar", "jq"]
        total_checks = len(deps) + 3  # +3 for archive tools, zstd, and dotnet

        for idx, dep in enumerate(deps):
            progress = (idx + 1) / total_checks * 0.5  # Use first 50% for checking
            self.update_progress(progress)
            self.update_progress_text(f"Checking {dep}...")

            label = DEP_LABELS.get(dep, dep)
            if self.check_command(dep):
                self.log(f"{label} is installed", "success")
            else:
                self.log(f"{label} is not installed", "error")
                missing.append(dep)

        # Check for either 7z or unzip (both can extract archives)
        progress = (len(deps) + 1) / total_checks * 0.5
        self.update_progress(progress)
        self.update_progress_text("Checking archive tools...")

        if not self.check_command("7z") and not self.check_command("unzip"):
            self.log(
                "Neither 7z nor unzip is installed (at least one is required)", "error"
            )
            missing.append("7z or unzip")
        else:
            if self.check_command("7z"):
                self.log("7z is installed", "success")
            else:
                self.log("unzip is installed (will be used instead of 7z)", "success")

        # Check zstd
        progress = (len(deps) + 2) / total_checks * 0.5
        self.update_progress(progress)
        self.update_progress_text("Checking zstd...")

        if not (self.check_command("unzstd") or self.check_command("zstd")):
            self.log("zstd or unzstd is not installed", "error")
            missing.append("zstd")
        else:
            self.log("zstd support is available", "success")

        # Check .NET SDK (optional but recommended for Affinity v3 settings fix)
        progress = (len(deps) + 3) / total_checks * 0.5
        self.update_progress(progress)
        self.update_progress_text("Checking .NET SDK...")

        if not self.check_dotnet_sdk():
            self.log(
                ".NET SDK is not installed (optional - needed for Affinity v3 settings fix)",
                "warning",
            )
            missing.append("dotnet-sdk")
        else:
            self.log(".NET SDK is installed", "success")

        # Handle unsupported distributions - show warning and allow retry
        if self.distro in ["bazzite"]:
            if missing:
                self.log("\n" + "=" * 80, "error")
                self.log("⚠️  WARNING: UNSUPPORTED DISTRIBUTION", "error")
                self.log("=" * 80, "error")
                self.log("\nMissing dependencies detected.", "error")
                self.log(
                    "This script will NOT auto-install for unsupported distributions.",
                    "error",
                )
                self.log(
                    "Please install the required dependencies manually.", "warning"
                )
                self.log(f"Missing: {', '.join(missing)}", "warning")

                # Show dialog asking user to install and retry
                reply = self.show_question_dialog(
                    "Unsupported Distribution - Missing Dependencies",
                    f"⚠️  WARNING: UNSUPPORTED DISTRIBUTION\n\n"
                    f"Missing dependencies: {', '.join(missing)}\n\n"
                    f"This script will NOT auto-install for unsupported distributions.\n"
                    f"Please install the required dependencies manually.\n\n"
                    f"Click 'Retry' after installing dependencies, or 'Cancel' to exit.",
                    ["Retry", "Cancel"],
                )

                if reply == "Retry":
                    # Re-check dependencies
                    return self.check_dependencies()
                else:
                    return False
            else:
                self.log(
                    "\nAll dependencies installed, but you are on an unsupported distribution.",
                    "warning",
                )
                self.log("No support will be provided if issues arise.", "warning")

        # Install missing dependencies (only for supported distributions)
        # For Ubuntu/Mint/Zorin, always run WineHQ setup to ensure proper Wine version
        if missing and not self.account_can_sudo() and self.distro not in ["bazzite"]:
            self.explain_admin_needed(missing)
            return False
        if self.is_ubuntu_family_distro() and not missing and not self.account_can_sudo():
            self.log("All dependencies are installed; this account cannot use sudo, "
                     "so the WineHQ repository setup is skipped.", "info")
            return True
        if self.is_ubuntu_family_distro():
            # Always run WineHQ setup for Ubuntu-based distros
            self.log(f"\nSetting up WineHQ for {self.format_distro_name()}...", "info")
            self.update_progress_text(
                f"Setting up Wine for {self.format_distro_name()}..."
            )

            # Request password before attempting installation
            self.log(
                "Administrator privileges required for package installation.", "info"
            )
            self.update_progress_text("Requesting administrator password...")

            password = self.get_sudo_password()
            if password is None:
                self.log(
                    "Password entry cancelled. Cannot install dependencies.", "error"
                )
                return False

            if not self.sudo_password_validated:
                if not self.validate_sudo_password(password):
                    self.log(
                        "Password validation failed. Cannot install dependencies.",
                        "error",
                    )
                    return False

            return self.install_dependencies()
        elif missing and self.distro not in ["bazzite"]:
            self.log(f"\nInstalling missing dependencies: {', '.join(missing)}", "info")
            self.update_progress_text(f"Installing {len(missing)} missing packages...")
            self.update_progress(0.5)  # Start second half of progress

            # Request password before attempting installation
            self.log(
                "Administrator privileges required for package installation.", "info"
            )
            self.update_progress_text("Requesting administrator password...")

            # Try to get and validate password (with retries)
            max_password_attempts = 3
            password_valid = False

            for password_attempt in range(max_password_attempts):
                password = self.get_sudo_password()
                if password is None:
                    self.log(
                        "Password entry cancelled. Cannot install dependencies.",
                        "error",
                    )
                    self.update_progress_text("Dependency installation cancelled")
                    return False

                # Validate password before proceeding
                if not self.sudo_password_validated:
                    self.log(
                        f"Validating password... (attempt {password_attempt + 1}/{max_password_attempts})",
                        "info",
                    )
                    if self.validate_sudo_password(password):
                        self.log("Password validated successfully.", "success")
                        password_valid = True
                        break
                    else:
                        if password_attempt < max_password_attempts - 1:
                            self.log(
                                "Password validation failed. Please try again.", "error"
                            )
                            # Clear the password to force a new dialog on next get_sudo_password call
                            self.sudo_password = None
                            self.sudo_password_validated = False
                            # Wait a moment for user to see the error message
                            time.sleep(1)
                        else:
                            self.log(
                                "Password validation failed after multiple attempts.",
                                "error",
                            )
                            return False
                else:
                    # Password already validated
                    password_valid = True
                    break

            if not password_valid:
                self.log(
                    "Could not validate password. Cannot install dependencies.", "error"
                )
                self.update_progress_text("Dependency installation cancelled")
                return False

            if not self.install_dependencies():
                self.update_progress_text("Dependency installation failed")
                return False

        self.update_progress(1.0)
        self.update_progress_text("All dependencies installed")
        self.log("\n✓ All required dependencies are installed!", "success")
        self.check_opencl_driver()
        return True

    def opencl_family(self):
        """Distro family for OPENCL_PACKAGES, or None."""
        d = self.distro or ""
        if d in ("arch", "artix", "cachyos", "endeavouros", "xerolinux", "manjaro", "garuda"):
            return "arch"
        if d in ("fedora", "nobara") or "fedora" in d:
            return "fedora"
        if "opensuse" in d or "suse" in d:
            return "suse"
        if self.is_ubuntu_family_distro() or d in ("debian", "pop", "pikaos"):
            return "debian"
        return None

    def opencl_advice(self):
        """None when an OpenCL driver is installed (or no GPU is recognised);
        otherwise a sentence naming the package for this GPU and distro."""
        if opencl_drivers():
            return None
        vendors = gpu_vendors()
        if not vendors:
            return None
        packages = OPENCL_PACKAGES.get(self.opencl_family() or "", {})
        named = [f"{v.upper() if v == 'amd' else v.capitalize()}: {packages[v]}"
                 for v in vendors if v in packages]
        what = ("; ".join(named) if named else
                "your distribution's OpenCL driver for " + ", ".join(vendors))
        return ("No OpenCL driver is installed, so Affinity will run without OpenCL "
                f"(slower filters and effects). To enable it, install — {what}. "
                "Then `clinfo -l` should list your GPU.")

    def check_opencl_driver(self):
        """Advise, never block: Affinity runs without OpenCL."""
        advice = self.opencl_advice()
        if advice:
            self.log(advice, "warning")
        return advice

    def show_unsupported_warning(self):
        """Display unsupported distribution warning"""
        self.log("\n" + "=" * 80, "warning")
        self.log("⚠️  WARNING: UNSUPPORTED DISTRIBUTION", "error")
        self.log("=" * 80, "warning")
        self.log(f"\nYOU ARE ON YOUR OWN!", "error")
        self.log(
            f"\nThe distribution ({self.format_distro_name()}) is OUT OF DATE",
            "warning",
        )
        self.log("and the script will NOT be built around it.", "warning")
        self.log("\nFor a modern, stable Linux experience, please consider:", "info")
        self.log("  • PikaOS 4", "success")
        self.log("  • CachyOS", "success")
        self.log("  • Nobara", "success")
        self.log("=" * 80 + "\n", "warning")

    def _distro_install_commands(self):
        """The package-manager command that installs the dependencies, per distro."""
        return {
            "arch": [
                "sudo",
                "pacman",
                "-S",
                "--needed",
                "--noconfirm",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "artix": [
                "sudo",
                "pacman",
                "-S",
                "--needed",
                "--noconfirm",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "cachyos": [
                "sudo",
                "pacman",
                "-S",
                "--needed",
                "--noconfirm",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "endeavouros": [
                "sudo",
                "pacman",
                "-S",
                "--needed",
                "--noconfirm",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "xerolinux": [
                "sudo",
                "pacman",
                "-S",
                "--needed",
                "--noconfirm",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "manjaro": [
                "sudo",
                "pacman",
                "-S",
                "--needed",
                "--noconfirm",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "fedora": [
                "sudo",
                "dnf",
                "install",
                "-y",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "p7zip-plugins",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "nobara": [
                "sudo",
                "dnf",
                "install",
                "-y",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "p7zip",
                "p7zip-plugins",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ],
            "opensuse-tumbleweed": [
                "sudo",
                "zypper",
                "install",
                "-y",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "7zip",
                "tar",
                "jq",
                "zstd",
            ],
            "opensuse-leap": [
                "sudo",
                "zypper",
                "install",
                "-y",
                "wine",
                "winetricks",
                "wget",
                "curl",
                "7zip",
                "tar",
                "jq",
                "zstd",
            ],
        }

    def account_can_sudo(self):
        """Can this account use sudo at all? Asked before any password prompt:
        an account outside the sudoers was asked for a password it could not
        use, and the install churned and then failed without saying why."""
        cached = getattr(self, "_account_can_sudo", None)
        if cached is not None:
            return cached
        can = False
        if shutil.which("sudo"):
            try:
                import grp
                groups = {grp.getgrgid(g).gr_name for g in os.getgroups()}
            except Exception:
                groups = set()
            if groups & {"wheel", "sudo", "admin"}:
                can = True
            else:
                try:
                    can = subprocess.run(["sudo", "-n", "true"], capture_output=True,
                                         timeout=10).returncode == 0
                except Exception:
                    can = False
        self._account_can_sudo = can
        return can

    def admin_install_command(self):
        """The one command an administrator can run to install what this
        installer needs from the system, or None for an unknown distro."""
        commands = self._distro_install_commands()
        if self.distro in commands:
            return " ".join(shlex.quote(a) for a in commands[self.distro])
        if self.is_ubuntu_family_distro() or self.distro in ("pop", "pikaos"):
            return ("sudo apt install wine winetricks wget curl p7zip-full tar jq "
                    "zstd dotnet-sdk-8.0")
        return None

    def explain_admin_needed(self, missing):
        """Say plainly that this account cannot install packages, what is
        missing, and the exact command for an administrator."""
        command = self.admin_install_command()
        text = (
            "This account cannot install system packages (it is not allowed to use "
            "sudo), and these are missing:\n\n    " + ", ".join(missing) + "\n\n"
            "Everything else -- Wine, Affinity, the prefix -- installs into your home "
            "folder and needs no administrator. Ask an administrator to run this once"
            + (":\n\n    " + command if command else
               " -- the packages above, from your distribution's package manager.")
            + "\n\nThen run the installer again."
            + (f"\n\nAlso, optionally: {self.opencl_advice()}" if self.opencl_advice() else "")
        )
        self.log(text, "error")
        self.show_message("An administrator needs to install some packages", text, "error")

    def install_dependencies(self):
        """Install dependencies based on distribution"""
        self.log(
            f"DEBUG: install_dependencies called with distro={self.distro}", "info"
        )
        if self.distro == "pikaos":
            return self.install_pikaos_dependencies()
        if self.distro == "pop":
            return self.install_popos_dependencies()
        if self.is_ubuntu_family_distro():
            return self.install_ubuntu_based_dependencies()

        commands = self._distro_install_commands()

        if self.distro in commands:
            self.log(
                f"Installing dependencies for {self.format_distro_name()}...", "info"
            )
            self.update_progress_text(
                f"Installing packages for {self.format_distro_name()}..."
            )
            self.update_progress(0.6)

            success, stdout, stderr = self.run_command(commands[self.distro])

            if success:
                self.update_progress(1.0)
                self.update_progress_text("Dependencies installed")
                self.log("Dependencies installed successfully", "success")

                # .NET SDK packages are installed separately (best-effort) on
                # openSUSE: zypper resolves the whole transaction as one unit,
                # so if dotnet-sdk-8.0 becomes temporarily unsatisfiable in the
                # repos (this has happened on Tumbleweed), bundling it with
                # wine/winetricks/etc would fail the ENTIRE dependency install
                # and leave the user stuck. The dedicated .NET SDK check/install
                # logic elsewhere in this installer already handles detecting
                # and installing whichever SDK is actually available.
                if self.distro in ("opensuse-tumbleweed", "opensuse-leap"):
                    self.log("Installing .NET SDK packages...", "info")
                    for dotnet_pkg in ("dotnet-sdk-10.0", "dotnet-sdk-8.0"):
                        dotnet_success, _, dotnet_stderr = self.run_command(
                            ["sudo", "zypper", "install", "-y", dotnet_pkg],
                            check=False,
                        )
                        if dotnet_success:
                            self.log(f"  ✓ {dotnet_pkg} installed", "success")
                        else:
                            self.log(
                                f"  ⚠ {dotnet_pkg} could not be installed — "
                                "will be retried automatically later if needed: "
                                f"{dotnet_stderr}",
                                "warning",
                            )

                # Install msttcore-fonts to fix font rendering bug with Affinity
                if self.distro in ("fedora", "nobara"):
                    msttcore_rpm = "/tmp/msttcore-fonts-installer-2.6-1.noarch.rpm"
                    msttcore_url = "https://github.com/isboston/msttcore-fonts/releases/download/fonts/msttcore-fonts-installer-2.6-1.noarch.rpm"
                    self.log(
                        "Downloading msttcore-fonts to fix font rendering bug...",
                        "info",
                    )
                    if self.download_file(msttcore_url, msttcore_rpm, "msttcore-fonts"):
                        self.log("Installing msttcore-fonts...", "info")
                        rpm_success, _, rpm_stderr = self.run_command(
                            ["sudo", "dnf", "install", "-y", msttcore_rpm],
                            check=False,
                        )
                        if rpm_success:
                            self.log("  ✓ msttcore-fonts installed", "success")
                        else:
                            self.log(
                                f"  ⚠ msttcore-fonts could not be installed "
                                f"(may already be installed): {rpm_stderr}",
                                "warning",
                            )
                        try:
                            os.remove(msttcore_rpm)
                        except OSError:
                            pass
                    else:
                        self.log(
                            "  ⚠ Failed to download msttcore-fonts "
                            "(font rendering may have issues)",
                            "warning",
                        )

                return True
            else:
                self.log(f"Failed to install dependencies: {stderr}", "error")

                # Show retry dialog
                reply = self.show_question_dialog(
                    "Dependency Installation Failed",
                    f"Failed to install dependencies:\n{stderr}\n\n"
                    "Would you like to retry the installation?",
                    ["Yes", "No"],
                )

                if reply == "Yes":
                    # Retry installation
                    return self.install_dependencies()
                else:
                    return False

        self.log(f"Unsupported distribution: {self.format_distro_name()}", "error")
        return False

    def install_pikaos_dependencies(self):
        """Install PikaOS dependencies with WineHQ staging"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("PikaOS Special Configuration", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        self.log("PikaOS's built-in Wine has compatibility issues.", "warning")
        self.log("Setting up WineHQ staging from Debian...\n", "info")

        # Total steps: keyrings, gpg key, i386, repo, apt update, wine install, deps install, winetricks install = 8 steps
        total_steps = 8
        current_step = 0

        # Create keyrings directory
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Creating keyrings directory..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Creating APT keyrings directory...", "info")
        success, _, _ = self.run_command(
            ["sudo", "mkdir", "-pm755", "/etc/apt/keyrings"]
        )
        if not success:
            self.log("Failed to create keyrings directory", "error")
            return False

        # Add GPG key
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding WineHQ GPG key..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding WineHQ GPG key...", "info")

        # Get sudo password for GPG operation
        password = self.get_sudo_password()
        if password is None:
            self.log("Authentication cancelled by user", "error")
            return False

        # Validate password if not already validated
        if not self.sudo_password_validated:
            if not self.validate_sudo_password(password):
                self.log("Authentication failed", "error")
                return False

        # Download GPG key to temporary file first (handles binary data correctly)
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_key_path = tmp_file.name

        try:
            # Download the key in binary mode
            success, _, _ = self.run_command(
                [
                    "wget",
                    "-O",
                    tmp_key_path,
                    "https://dl.winehq.org/wine-builds/winehq.key",
                ]
            )
            if not success:
                self.log("Failed to download GPG key", "error")
                os.unlink(tmp_key_path)
                return False

            # Read the key file in binary mode
            with open(tmp_key_path, "rb") as key_file:
                key_data = key_file.read()

            # Clean up temp file
            os.unlink(tmp_key_path)

            # Run GPG command with sudo, passing binary key data
            gpg_proc = subprocess.Popen(
                [
                    "sudo",
                    "-S",
                    "gpg",
                    "--dearmor",
                    "-o",
                    "/etc/apt/keyrings/winehq-archive.key",
                    "-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Send password first (as bytes), then the key data (binary)
            gpg_input = f"{self.sudo_password}\n".encode() + key_data
            gpg_stdout, gpg_stderr = gpg_proc.communicate(input=gpg_input)

            if gpg_proc.returncode == 0:
                self.log("WineHQ GPG key added", "success")
            else:
                error_msg = (
                    gpg_stderr.decode("utf-8", errors="ignore")
                    if gpg_stderr
                    else "Unknown error"
                )
                self.log(f"Failed to add GPG key: {error_msg}", "error")
                return False
        except Exception as e:
            # Clean up temp file on error
            import os as _os

            if _os.path.exists(tmp_key_path):
                try:
                    _os.unlink(tmp_key_path)
                except:
                    pass
            self.log(f"Failed to add GPG key: {str(e)}", "error")
            return False

        # Add i386 architecture
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding i386 architecture..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding i386 architecture...", "info")
        success, _, _ = self.run_command(["sudo", "dpkg", "--add-architecture", "i386"])
        if not success:
            self.log("Failed to add i386 architecture", "error")
            return False

        # Add repository
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding WineHQ repository..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding WineHQ repository...", "info")

        # Always use Debian testing repository for the newest WineHQ packages
        # This ensures we get the latest WineHQ versions without needing to update
        # the script every Debian release. Debian testing codename is currently "forky"
        codename = "forky"  # Debian testing
        self.log(
            f"Using Debian testing (forky) repository for latest WineHQ packages",
            "info",
        )

        # Remove existing WineHQ repository files first to avoid conflicts
        repo_pattern = Path("/etc/apt/sources.list.d/")
        for repo_file in repo_pattern.glob("winehq-*.sources"):
            self.run_command(["sudo", "rm", "-f", str(repo_file)], check=False)

        # Add the repository using the detected codename
        # Use -NP flags: -N for timestamping, -P for directory
        success, _, _ = self.run_command(
            [
                "sudo",
                "wget",
                "-NP",
                "/etc/apt/sources.list.d/",
                f"https://dl.winehq.org/wine-builds/debian/dists/{codename}/winehq-{codename}.sources",
            ]
        )
        if not success:
            self.log(f"Failed to add repository for {codename}", "error")
            return False

        # Update package lists
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Updating package lists..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Updating package lists...", "info")
        success, _, _ = self.run_command(["sudo", "apt", "update"])
        if not success:
            self.log("Failed to update package lists", "error")
            return False

        # Install WineHQ staging
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing WineHQ staging..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Installing WineHQ staging...", "info")
        success, _, _ = self.run_command(
            ["sudo", "apt", "install", "--install-recommends", "-y", "winehq-staging"]
        )
        if not success:
            self.log("Failed to install WineHQ staging", "error")
            return False

        # Install remaining dependencies
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing remaining dependencies..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Installing remaining dependencies...", "info")
        success, _, _ = self.run_command(
            [
                "sudo",
                "apt",
                "install",
                "-y",
                "wget",
                "curl",
                "p7zip-full",
                "tar",
                "jq",
                "zstd",
            ]
        )
        if not success:
            self.log("Failed to install remaining dependencies", "error")
            return False

        # Install winetricks from source
        self.log("Installing winetricks from source...", "info")
        success, _, _ = self.run_command(
            ["git", "clone", "https://github.com/Winetricks/winetricks"]
        )
        if not success:
            self.log("Failed to clone winetricks repository", "error")
            return False

        # Change to winetricks directory and install.
        #
        # The chdir back sat after an early return, so a failed `make install`
        # left the whole process in ./winetricks -- for ever, since this is a
        # GUI that keeps running. Every later relative path in the run then
        # resolved somewhere the user never chose, including the rmtree below
        # on a subsequent attempt.
        was = os.getcwd()
        try:
            os.chdir("winetricks")
            success, _, _ = self.run_command(["sudo", "make", "install"])
        finally:
            os.chdir(was)
        if not success:
            self.log("Failed to install winetricks", "error")
            return False

        # Clean up
        shutil.rmtree("winetricks")

        self.update_progress(1.0)
        self.update_progress_text("PikaOS dependencies installed")
        self.log("All dependencies installed for PikaOS", "success")
        return True

    def install_popos_dependencies(self):
        """Install Pop!_OS dependencies with WineHQ staging"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Pop!_OS Special Configuration", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        self.log("Pop!_OS's built-in Wine has compatibility issues.", "warning")
        self.log("Setting up WineHQ staging from Ubuntu...\n", "info")

        # Total steps: keyrings, gpg key, i386, repo, apt update, wine install, deps install = 7 steps
        total_steps = 7
        current_step = 0

        # Create keyrings directory
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Creating keyrings directory..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Creating APT keyrings directory...", "info")
        success, _, _ = self.run_command(
            ["sudo", "mkdir", "-pm755", "/etc/apt/keyrings"]
        )
        if not success:
            self.log("Failed to create keyrings directory", "error")
            return False

        # Add GPG key
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding WineHQ GPG key..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding WineHQ GPG key...", "info")

        # Get sudo password for GPG operation
        password = self.get_sudo_password()
        if password is None:
            self.log("Authentication cancelled by user", "error")
            return False

        # Validate password if not already validated
        if not self.sudo_password_validated:
            if not self.validate_sudo_password(password):
                self.log("Authentication failed", "error")
                return False

        # Download GPG key to temporary file first (handles binary data correctly)
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_key_path = tmp_file.name

        try:
            # Download the key in binary mode
            success, _, _ = self.run_command(
                [
                    "wget",
                    "-O",
                    tmp_key_path,
                    "https://dl.winehq.org/wine-builds/winehq.key",
                ]
            )
            if not success:
                self.log("Failed to download GPG key", "error")
                os.unlink(tmp_key_path)
                return False

            # Read the key file in binary mode
            with open(tmp_key_path, "rb") as key_file:
                key_data = key_file.read()

            # Clean up temp file
            os.unlink(tmp_key_path)

            # Remove existing key file to avoid overwrite prompts
            self.run_command(
                ["sudo", "rm", "-f", "/etc/apt/keyrings/winehq-archive.key"],
                check=False,
            )

            # Run GPG command with sudo, passing binary key data
            gpg_proc = subprocess.Popen(
                [
                    "sudo",
                    "-S",
                    "gpg",
                    "--dearmor",
                    "-o",
                    "/etc/apt/keyrings/winehq-archive.key",
                    "-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Send password first (as bytes), then the key data (binary)
            gpg_input = f"{self.sudo_password}\n".encode() + key_data
            gpg_stdout, gpg_stderr = gpg_proc.communicate(input=gpg_input)

            if gpg_proc.returncode == 0:
                self.log("WineHQ GPG key added", "success")
            else:
                error_msg = (
                    gpg_stderr.decode("utf-8", errors="ignore")
                    if gpg_stderr
                    else "Unknown error"
                )
                self.log(f"Failed to add GPG key: {error_msg}", "error")
                return False
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(tmp_key_path):
                try:
                    os.unlink(tmp_key_path)
                except:
                    pass
            self.log(f"Failed to add GPG key: {str(e)}", "error")
            return False

        # Add i386 architecture
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding i386 architecture..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding i386 architecture...", "info")
        success, _, _ = self.run_command(["sudo", "dpkg", "--add-architecture", "i386"])
        if not success:
            self.log("Failed to add i386 architecture", "error")
            return False

        # Add repository
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding WineHQ repository..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding WineHQ repository...", "info")
        # Get Ubuntu version codename
        codename = "jammy"
        try:
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.startswith("VERSION_CODENAME="):
                        codename = line.split("=")[1].strip()
        except (IOError, FileNotFoundError):
            pass  # Default to jammy

        # Remove existing file first to avoid overwrite prompt
        repo_file = Path(f"/etc/apt/sources.list.d/winehq-{codename}.sources")
        if repo_file.exists():
            self.run_command(["sudo", "rm", "-f", str(repo_file)], check=False)

        success, _, _ = self.run_command(
            [
                "sudo",
                "wget",
                "-P",
                "/etc/apt/sources.list.d/",
                f"https://dl.winehq.org/wine-builds/ubuntu/dists/{codename}/winehq-{codename}.sources",
            ]
        )
        if not success:
            self.log("Failed to add repository", "error")
            return False

        # Update package lists
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Updating package lists..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Updating package lists...", "info")
        success, _, _ = self.run_command(["sudo", "apt", "update"])
        if not success:
            self.log("Failed to update package lists", "error")
            return False

        # Install WineHQ staging
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing WineHQ staging..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Installing WineHQ staging...", "info")
        success, _, _ = self.run_command(
            ["sudo", "apt", "install", "--install-recommends", "-y", "winehq-staging"]
        )
        if not success:
            self.log("Failed to install WineHQ staging", "error")
            return False

        # Install remaining dependencies
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing remaining dependencies..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Installing remaining dependencies...", "info")
        success, _, _ = self.run_command(
            [
                "sudo",
                "apt",
                "install",
                "-y",
                "winetricks",
                "wget",
                "curl",
                "p7zip-full",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk-8.0",
            ]
        )
        if not success:
            self.log("Failed to install remaining dependencies", "error")
            self.log(
                "Note: dotnet-sdk-8.0 may require Microsoft's repository. You can install it manually if needed.",
                "warning",
            )
            return False

        self.update_progress(1.0)
        self.update_progress_text("Pop!_OS dependencies installed")
        self.log("All dependencies installed for Pop!_OS", "success")
        return True

    def install_ubuntu_based_dependencies(self):
        """Install dependencies for Ubuntu, Linux Mint, and Zorin OS with WineHQ staging"""
        print("DEBUG: install_ubuntu_based_dependencies() CALLED!", flush=True)
        self.log("===========================================", "info")
        self.log("★ Starting Ubuntu-based dependency installation ★", "warning")
        self.log(f"★ Detected distro: {self.distro} ★", "warning")
        self.log("===========================================", "info")
        distro_name = self.format_distro_name()
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log(f"{distro_name} Configuration", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Detect Ubuntu version codename
        codename = "jammy"
        ubuntu_version_num = 22.04
        try:
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.startswith("VERSION_CODENAME="):
                        codename = line.split("=")[1].strip()
                    if line.startswith("VERSION_ID="):
                        version_str = line.split("=")[1].strip().strip('"')
                        ubuntu_version_num = float(version_str)
        except (IOError, FileNotFoundError):
            pass

        # Linux Mint and Zorin may report their own version, need to detect base
        # Linux Mint 22 = Ubuntu 24.04 (noble), Linux Mint 21.x = Ubuntu 22.04 (jammy)
        # Zorin 18 = Ubuntu 24.04 (noble), Zorin 17.x = Ubuntu 22.04 (jammy)
        if self.distro == "linuxmint":
            # Force noble for Mint 22 - Mint 22 is based on Ubuntu 24.04
            # Check both VERSION_ID and DEBIAN_CODENAME
            detected_mint_version = ""
            detected_debian_codename = ""

            try:
                with open("/etc/os-release", "r") as f:
                    for line in f:
                        if line.startswith("VERSION_ID="):
                            detected_mint_version = (
                                line.split("=")[1].strip().strip('"')
                            )
                        if line.startswith("DEBIAN_CODENAME="):
                            detected_debian_codename = line.split("=")[1].strip()
            except:
                pass

            # Mint 22+ uses Ubuntu 24.04 (noble), older uses 22.04 (jammy)
            print(
                f"DEBUG: Mint version='{detected_mint_version}', debian_codename='{detected_debian_codename}'",
                flush=True,
            )
            if (
                detected_mint_version.startswith("22")
                or detected_debian_codename == "noble"
            ):
                codename = "noble"
                ubuntu_version_num = 24.04
            else:
                codename = "jammy"
                ubuntu_version_num = 22.04

        elif self.distro == "zorin":
            # Force noble for Zorin 18 - Zorin 18 is based on Ubuntu 24.04
            detected_zorin_version = ""
            detected_debian_codename = ""

            try:
                with open("/etc/os-release", "r") as f:
                    for line in f:
                        if line.startswith("VERSION_ID="):
                            detected_zorin_version = (
                                line.split("=")[1].strip().strip('"')
                            )
                        if line.startswith("DEBIAN_CODENAME="):
                            detected_debian_codename = line.split("=")[1].strip()
            except:
                pass

            # Zorin 18+ uses Ubuntu 24.04 (noble), older uses 22.04 (jammy)
            if (
                detected_zorin_version.startswith("18")
                or detected_debian_codename == "noble"
            ):
                codename = "noble"
                ubuntu_version_num = 24.04
            else:
                codename = "jammy"
                ubuntu_version_num = 22.04

        self.log(
            f"Detected codename: {codename}, version: {ubuntu_version_num}", "info"
        )

        # Debug: log raw os-release values for Mint/Zorin
        if self.distro in ["linuxmint", "zorin"]:
            try:
                with open("/etc/os-release", "r") as f:
                    content = f.read()
                # Just log the codename lines
                for line in content.split("\n"):
                    if "CODENAME" in line or "VERSION_ID" in line:
                        self.log(f"DEBUG: {line}", "info")
            except:
                pass

        # Validate codename is valid for WineHQ
        if codename not in ["noble", "jammy", "focal"]:
            self.log(
                f"Warning: codename '{codename}' may not have WineHQ packages. Using 'jammy' as fallback.",
                "warning",
            )
            codename = "jammy"

        # Check if we should use official Wine (Ubuntu 24.04+) or WineHQ staging
        # Note: Linux Mint 22 still uses WineHQ staging (better compatibility)
        is_mint = distro_name.lower() in ["linux mint", "mint", "zorin"]
        use_official_wine = ubuntu_version_num >= 24.04 and not is_mint

        if use_official_wine:
            self.log(
                f"Using official Wine packages for Ubuntu {ubuntu_version_num}...\n",
                "info",
            )
            return self.install_ubuntu_official_wine(codename)
        else:
            if is_mint:
                self.log(
                    f"Using WineHQ staging for {distro_name} (better compatibility)...\n",
                    "info",
                )
            else:
                self.log(f"Setting up WineHQ staging for {distro_name}...\n", "info")
            return self.install_ubuntu_winehq_staging(codename)


    def install_ubuntu_official_wine(self, codename):
        """Install Wine using official Ubuntu repositories for 24.04+"""
        distro_name = self.format_distro_name()
        total_steps = 4
        current_step = 0

        # Add i386 architecture
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding i386 architecture..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding i386 architecture...", "info")
        success, _, _ = self.run_command(["sudo", "dpkg", "--add-architecture", "i386"])
        if not success:
            self.log("Failed to add i386 architecture", "error")
            return False

        # Update package lists
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Updating package lists..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Updating package lists...", "info")
        success, _, _ = self.run_command(["sudo", "apt", "update"])
        if not success:
            self.log("Failed to update package lists", "error")
            return False

        # Install Wine
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing Wine..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Installing Wine (official Ubuntu packages)...", "info")
        success, _, _ = self.run_command(
            [
                "sudo",
                "apt",
                "install",
                "-y",
                "wine",
                "wine64",
                "wine32",
                "libwine",
                "libwine:i386",
                "fonts-wine",
            ]
        )
        if not success:
            self.log("Failed to install Wine", "error")
            return False

        # Install remaining dependencies
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing remaining dependencies..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Installing remaining dependencies...", "info")
        # apt aborts the whole transaction if any requested package does not exist.
        # Ubuntu 26.04 no longer ships p7zip-full (7zip provides the 7z command)
        # or dotnet-sdk-8.0, so only request what this release actually has.
        remaining_packages = ["winetricks", "wget", "curl", "tar", "jq", "zstd"]
        remaining_packages.append(
            "p7zip-full" if self._apt_package_available("p7zip-full") else "7zip"
        )
        remaining_packages += [
            pkg
            for pkg in ("dotnet-sdk-8.0", "dotnet-sdk-10.0")
            if self._apt_package_available(pkg)
        ]
        success, _, _ = self.run_command(
            ["sudo", "apt", "install", "-y"] + remaining_packages
        )
        if not success:
            self.log("Failed to install remaining dependencies", "error")
            self.log(
                "Note: dotnet-sdk packages may require Microsoft's repository. You can install them manually if needed.",
                "warning",
            )
            return False

        self.update_progress(1.0)
        self.update_progress_text(f"{distro_name} dependencies installed")
        self.log(f"All dependencies installed for {distro_name}", "success")
        return True

    def _apt_package_available(self, package):
        """Return True if apt has an install candidate for the package."""
        success, stdout, _ = self.run_command(
            ["apt-cache", "policy", package], check=False, capture=True
        )
        if not success or not stdout:
            return False
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("Candidate:"):
                return line.split(":", 1)[1].strip() not in ("", "(none)")
        return False

    def get_preferred_ubuntu_winehq_version(self, codename):
        """Return the preferred WineHQ package version for Ubuntu-family systems"""
        return f"10.20~{codename}-1"

    def get_preferred_ubuntu_winehq_packages(self, codename):
        """Return the pinned WineHQ staging package set used on Ubuntu-family systems"""
        version = self.get_preferred_ubuntu_winehq_version(codename)
        return [
            f"winehq-staging={version}",
            f"wine-staging={version}",
            f"wine-staging-amd64={version}",
            f"wine-staging-i386:i386={version}",
        ]

    def install_ubuntu_winehq_staging(self, codename):
        """Install WineHQ staging for older Ubuntu versions (< 24.04)"""
        distro_name = self.format_distro_name()

        # Total steps: keyrings, gpg key, i386, repo, apt update, wine install, deps install = 7 steps
        total_steps = 7
        current_step = 0

        # Create keyrings directory
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Creating keyrings directory..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Creating APT keyrings directory...", "info")
        success, _, _ = self.run_command(
            ["sudo", "mkdir", "-pm755", "/etc/apt/keyrings"]
        )
        if not success:
            self.log("Failed to create keyrings directory", "error")
            return False

        # Add GPG key
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding WineHQ GPG key..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding WineHQ GPG key...", "info")

        # Get sudo password for GPG operation
        password = self.get_sudo_password()
        if password is None:
            self.log("Authentication cancelled by user", "error")
            return False

        # Validate password if not already validated
        if not self.sudo_password_validated:
            if not self.validate_sudo_password(password):
                self.log("Authentication failed", "error")
                return False

        # Download GPG key to temporary file first (handles binary data correctly)
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_key_path = tmp_file.name

        try:
            # Download the key in binary mode
            success, _, _ = self.run_command(
                [
                    "wget",
                    "-O",
                    tmp_key_path,
                    "https://dl.winehq.org/wine-builds/winehq.key",
                ]
            )
            if not success:
                self.log("Failed to download GPG key", "error")
                os.unlink(tmp_key_path)
                return False

            # Read the key file in binary mode
            with open(tmp_key_path, "rb") as key_file:
                key_data = key_file.read()

            # Clean up temp file
            os.unlink(tmp_key_path)

            # Remove existing key file to avoid overwrite prompts
            self.run_command(
                ["sudo", "rm", "-f", "/etc/apt/keyrings/winehq-archive.key"],
                check=False,
            )

            # Run GPG command with sudo, passing binary key data
            gpg_proc = subprocess.Popen(
                [
                    "sudo",
                    "-S",
                    "gpg",
                    "--dearmor",
                    "-o",
                    "/etc/apt/keyrings/winehq-archive.key",
                    "-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Send password first (as bytes), then the key data (binary)
            gpg_input = f"{self.sudo_password}\n".encode() + key_data
            gpg_stdout, gpg_stderr = gpg_proc.communicate(input=gpg_input)

            if gpg_proc.returncode == 0:
                self.log("WineHQ GPG key added", "success")
            else:
                error_msg = (
                    gpg_stderr.decode("utf-8", errors="ignore")
                    if gpg_stderr
                    else "Unknown error"
                )
                self.log(f"Failed to add GPG key: {error_msg}", "error")
                return False
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(tmp_key_path):
                try:
                    os.unlink(tmp_key_path)
                except:
                    pass
            self.log(f"Failed to add GPG key: {str(e)}", "error")
            return False

        # Add i386 architecture
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding i386 architecture..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding i386 architecture...", "info")
        success, stdout, stderr = self.run_command(
            ["sudo", "dpkg", "--add-architecture", "i386"]
        )
        if not success:
            self.log(f"Failed to add i386 architecture - STDOUT: {stdout}", "error")
            self.log(f"Failed to add i386 architecture - STDERR: {stderr}", "error")
            return False
        else:
            self.log(f"Added i386 architecture successfully", "success")

        # Add repository
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Adding WineHQ repository..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Adding WineHQ repository...", "info")
        self.log(f"DEBUG: Using codename '{codename}' for WineHQ repo", "info")

        # Remove existing file first to avoid overwrite prompt
        repo_file = Path(f"/etc/apt/sources.list.d/winehq-{codename}.sources")
        if repo_file.exists():
            self.run_command(["sudo", "rm", "-f", str(repo_file)], check=False)

        repo_url = f"https://dl.winehq.org/wine-builds/ubuntu/dists/{codename}/winehq-{codename}.sources"
        self.log(f"DEBUG: Downloading repo from: {repo_url}", "info")
        self.log(
            f"DEBUG: Running command: sudo wget -NP /etc/apt/sources.list.d/ {repo_url}",
            "info",
        )

        # Use curl to download (no sudo needed), then sudo to move
        max_retries = 3
        for attempt in range(max_retries):
            # First download without sudo to /tmp
            success, stdout, stderr = self.run_command(
                ["curl", "-fsSL", "-o", f"/tmp/winehq-{codename}.sources", repo_url]
            )
            self.log(f"DEBUG: curl download exit code: {success}", "info")
            if not success:
                if stdout:
                    self.log(f"DEBUG: curl STDOUT:\n{stdout}", "info")
                if stderr:
                    self.log(f"DEBUG: curl STDERR:\n{stderr}", "info")

            # Check if file was downloaded to /tmp
            tmp_file = Path(f"/tmp/winehq-{codename}.sources")
            if tmp_file.exists():
                self.log(f"Downloaded to /tmp successfully", "success")

                # Now move to /etc/apt with sudo
                success2, stdout2, stderr2 = self.run_command(
                    [
                        "sudo",
                        "mv",
                        f"/tmp/winehq-{codename}.sources",
                        f"/etc/apt/sources.list.d/winehq-{codename}.sources",
                    ]
                )
                if success2:
                    self.log(f"Moved file to sources.list.d", "success")
                else:
                    self.log(
                        f"Failed to move file - STDOUT: {stdout2}, STDERR: {stderr2}",
                        "error",
                    )

            # Check if repo file exists
            repo_file = Path(f"/etc/apt/sources.list.d/winehq-{codename}.sources")

            # Debug: list all files in sources.list.d
            sources_dir = Path("/etc/apt/sources.list.d")
            if sources_dir.exists():
                files = list(sources_dir.glob("*"))
                self.log(
                    f"DEBUG: Files in sources.list.d: {[f.name for f in files]}", "info"
                )

            if repo_file.exists():
                self.log(f"WineHQ repository file found: {repo_file}", "success")
                break

            if attempt < max_retries - 1:
                self.log(
                    f"Warning: Repository file not found at {repo_file}, retrying... (attempt {attempt + 1}/{max_retries})",
                    "warning",
                )
            else:
                self.log("Failed to add repository after multiple attempts", "error")
                if stdout:
                    self.log(f"STDOUT: {stdout}", "error")
                if stderr:
                    self.log(f"STDERR: {stderr}", "error")
                return False

        # Update package lists
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Updating package lists..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Updating package lists...", "info")
        success, _, _ = self.run_command(["sudo", "apt", "update"])
        if not success:
            self.log("Failed to update package lists", "error")
            return False

        # Install WineHQ staging
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing WineHQ staging..."
        )
        self.update_progress(current_step / total_steps)
        preferred_version = self.get_preferred_ubuntu_winehq_version(codename)
        self.log("Installing WineHQ staging...", "info")

        available, stdout, _ = self.run_command(["apt-cache", "madison", "winehq-staging"], check=False)
        pinned_packages = self.get_preferred_ubuntu_winehq_packages(codename)
        if available and stdout and preferred_version in stdout:
            self.log(
                f"Pinning WineHQ staging to {preferred_version} to avoid Wine 11 new WoW64 issues on Ubuntu-family systems.",
                "info"
            )
            wine_install_cmd = ["sudo", "apt", "install", "--install-recommends", "--allow-downgrades", "-y", *pinned_packages]
        else:
            self.log(
                f"Preferred WineHQ version {preferred_version} is unavailable for {codename}. Falling back to the latest WineHQ staging package.",
                "warning"
            )
            wine_install_cmd = ["sudo", "apt", "install", "--install-recommends", "-y", "winehq-staging"]

        success, stdout, stderr = self.run_command(wine_install_cmd)
        if not success:
            self.log("Failed to install WineHQ staging", "error")
            if stdout:
                self.log(f"STDOUT: {stdout}", "error")
            if stderr:
                self.log(f"STDERR: {stderr}", "error")
            return False

        # Install remaining dependencies
        current_step += 1
        self.update_progress_text(
            f"Step {current_step}/{total_steps}: Installing remaining dependencies..."
        )
        self.update_progress(current_step / total_steps)
        self.log("Installing remaining dependencies...", "info")
        success, _, _ = self.run_command(
            [
                "sudo",
                "apt",
                "install",
                "-y",
                "winetricks",
                "wget",
                "curl",
                "p7zip-full",
                "tar",
                "jq",
                "zstd",
                "dotnet-sdk-8.0",
                "dotnet-sdk-10.0",
            ]
        )
        if not success:
            self.log("Failed to install remaining dependencies", "error")
            self.log(
                "Note: dotnet-sdk packages may require Microsoft's repository. You can install them manually if needed.",
                "warning",
            )
            return False

        self.update_progress(1.0)
        self.update_progress_text(f"{distro_name} dependencies installed")
        self.log(f"All dependencies installed for {distro_name}", "success")
        return True

    def setup_wine(self, wine_version="11.19"):
        """Setup Wine environment - installs custom Wine 11.18 or 11.19 with Affinity patches

        Args:
            wine_version: "11.19" for Wine 11.19 (recommended, full patch set),
                          or "11.18" for Wine 11.18 (login fix + performance patches)
        """
        self.start_operation("Setting up Wine environment")

        try:
            # Check if cancelled at start
            if self.check_cancelled():
                return False

            # First check that system Wine is available (needed for installation)
            system_wine = shutil.which("wine")
            if not system_wine:
                self.log(
                    "System Wine not found. System Wine is required for installation:",
                    "error",
                )
                self.log("  Ubuntu/Debian: sudo apt install wine", "info")
                self.log("  Fedora: sudo dnf install wine", "info")
                self.log("  Arch: sudo pacman -S wine", "info")
                self.update_progress_text("Ready")
                return False

            self.log(
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            self.log("Wine Binary Setup", "info")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )

            # Get Wine version configuration
            config = self._get_wine_version_config(wine_version)
            wine_url = config["wine_url"]
            wine_file_name = config["wine_file_name"]
            wine_dir_name = config["wine_dir_name"]
            wine_dir_pattern = config["wine_dir_pattern"]
            archive_format = config["archive_format"]
            wine_display_name = config["wine_display_name"]

            self.log(f"Installing: {wine_display_name}", "info")

            # Stop Wine processes
            self.update_progress_text("Preparing Wine environment...")
            self.update_progress(0.0)
            self.log("Stopping Wine processes...", "info")
            # Scoped to this prefix: run_command defaults to os.environ.copy(),
            # so with no WINEPREFIX this killed whatever prefix the process had
            # inherited, taking every Wine process it served with it.
            _env = os.environ.copy()
            _env["WINEPREFIX"] = self.directory
            self.run_command(["wineserver", "-k"], check=False, env=_env)

            if self.check_cancelled():
                return False

            if not self.backup_incomplete_ubuntu_prefix():
                self.update_progress_text("Failed to prepare Wine prefix")
                return False

            # Create directory
            self.update_progress_text("Creating installation directory...")
            self.update_progress(0.05)
            Path(self.directory).mkdir(parents=True, exist_ok=True)
            self.log("Installation directory created", "success")

            if self.check_cancelled():
                return False

            # Download Wine binary
            wine_file = Path(self.directory) / wine_file_name

            self.update_progress_text(f"Downloading {wine_display_name}...")
            self.update_progress(0.10)
            self.log(f"Downloading {wine_display_name}...", "info")
            if not self.download_file(
                wine_url, str(wine_file), f"{wine_display_name} binaries"
            ):
                self.log(f"Failed to download {wine_display_name}", "error")
                self.update_progress_text("Ready")
                return False
            if not self._wine_download_matches(wine_file, config):
                self.update_progress_text("Ready")
                return False

            if self.check_cancelled():
                return False

            # Extract Wine
            self.update_progress_text("Extracting Wine binary...")
            self.update_progress(0.50)
            self.log("Extracting Wine binary...", "info")
            try:
                if archive_format == "gz":
                    with tarfile.open(wine_file, "r:gz") as tar:
                        tar.extractall(self.directory, filter="data")
                elif archive_format == "xz":
                    try:
                        import lzma

                        with lzma.open(wine_file, "rb") as xz_file:
                            with tarfile.open(fileobj=xz_file, mode="r") as tar:
                                tar.extractall(self.directory, filter="data")
                    except ImportError:
                        if not self.check_command("xz") and not self.check_command(
                            "unxz"
                        ):
                            self.log(
                                "xz or unxz is required to extract Wine archive. Please install xz.",
                                "error",
                            )
                            self.update_progress_text("Ready")
                            return False
                        tar_file = wine_file.with_suffix(".tar")
                        xz_cmd = "xz" if self.check_command("xz") else "unxz"
                        success, _, _ = self.run_command(
                            [xz_cmd, "-d", "-k", str(wine_file)], check=True
                        )
                        if not success:
                            self.log("Failed to decompress Wine archive", "error")
                            self.update_progress_text("Ready")
                            return False
                        with tarfile.open(tar_file, "r") as tar:
                            tar.extractall(self.directory, filter="data")
                        tar_file.unlink()

                wine_file.unlink()
                self.log("Wine binary extracted", "success")
            except Exception as e:
                self.log(f"Failed to extract Wine: {e}", "error")
                self.update_progress_text("Ready")
                return False

            if self.check_cancelled():
                return False

            # Find and link Wine directory
            self.update_progress(0.55)
            wine_dir = next(Path(self.directory).glob(wine_dir_pattern), None)
            if wine_dir and wine_dir != Path(self.directory) / wine_dir_name:
                target = Path(self.directory) / wine_dir_name
                if target.exists() or target.is_symlink():
                    if target.is_symlink():
                        target.unlink()
                    elif target.is_dir():
                        shutil.rmtree(target)
                target.symlink_to(wine_dir)
                self.log("Wine symlink created", "success")

            # Verify Wine binary
            self.update_progress(0.60)
            wine_binary = Path(self.directory) / wine_dir_name / "bin" / "wine"
            if not wine_binary.exists():
                self.log("Wine binary not found", "error")
                self.update_progress_text("Ready")
                return False

            self.log("Wine binary verified", "success")

            if self.check_cancelled():
                return False

            # Download icons
            self.update_progress_text("Downloading application icons...")
            self.update_progress(0.65)
            self.log("\nSetting up application icons...", "info")
            icons_dir = Path.home() / ".local" / "share" / "icons"
            icons_dir.mkdir(parents=True, exist_ok=True)

            icons = [
                (
                    "https://github.com/user-attachments/assets/c7b70ee5-58e3-46c6-b385-7c3d02749664",
                    icons_dir / "AffinityPhoto.svg",
                    "Photo icon",
                ),
                (
                    "https://github.com/user-attachments/assets/8ea7f748-c455-4ee8-9a94-775de40dbbf3",
                    icons_dir / "AffinityDesigner.svg",
                    "Designer icon",
                ),
                (
                    "https://github.com/user-attachments/assets/96ae06f8-470b-451f-ba29-835324b5b552",
                    icons_dir / "AffinityPublisher.svg",
                    "Publisher icon",
                ),
                (
                    "https://raw.githubusercontent.com/seapear/AffinityOnLinux/main/Assets/Icons/Affinity-Canva.svg",
                    icons_dir / "Affinity.svg",
                    "Affinity V3 icon",
                ),
            ]

            total_icons = len(icons)
            for idx, (url, path, desc) in enumerate(icons):
                if self.check_cancelled():
                    return False
                icon_progress = 0.65 + (idx / total_icons) * 0.05
                self.update_progress(icon_progress)
                if not self.download_file(url, str(path), desc):
                    self.log(
                        f"Warning: {desc} download failed, but continuing...", "warning"
                    )

            if self.check_cancelled():
                return False

            # Setup WinMetadata. 9.14 and 10.10 need it. 11.12 does not, because
            # its RoResolveNamespace is a stub and the metadata would never be
            # read. A build that implements RoResolveNamespace does need it --
            # that is what lets a double-clicked document open -- so ask the
            # build what it supports rather than keeping a version list.
            if wine_version in ["9.14", "10.10"]:
                self.update_progress_text("Setting up Windows Metadata...")
                self.update_progress(0.70)
                self.setup_winmetadata()
            elif self.wine_resolves_winrt_namespaces():
                self.update_progress_text("Setting up Windows Metadata...")
                self.update_progress(0.70)
                self.install_combined_winmetadata()
            else:
                self.log(
                    "Skipping WinMetadata setup: this Wine stubs RoResolveNamespace, "
                    "so the metadata would never be read",
                    "info",
                )

            if self.check_cancelled():
                return False

            # Before anything else uses this prefix: with OpenCL left on, Affinity
            # hangs during startup on these Wine versions and never finishes.
            self.disable_opencl_if_needed(wine_version)

            if cache_all_wine_versions():
                self.update_progress_text("Caching other Wine versions...")
                self.update_progress(0.72)
                self._download_all_wine_versions_to_cache(wine_version)
            else:
                self.log(
                    "Not caching the other Wine versions; switching downloads the one "
                    f"chosen. Set {ENV_CACHE_ALL_WINE}=1 to cache them all for offline "
                    "switching.",
                    "info",
                )

            if self.check_cancelled():
                return False

            if self.check_cancelled():
                return False

            # Setup vkd3d-proton (only if OpenCL is enabled and not AMD GPU)
            if self.is_opencl_enabled():
                gpu_id = self.get_selected_gpu()
                if self.has_nvidia_gpu() and (
                    gpu_id.startswith("nvidia_") or gpu_id.startswith("auto")
                ):
                    # Ask NVIDIA users to choose between DXVK and vkd3d
                    preference = self.ask_nvidia_dxvk_vkd3d_choice()
                    if preference == "dxvk":
                        self.update_progress_text(
                            "NVIDIA GPU with DXVK preference - installing d3d12 DLLs..."
                        )
                        self.update_progress(0.80)
                        self.log(
                            "NVIDIA GPU with DXVK preference - installing d3d12 DLLs and setting up DLL overrides",
                            "info",
                        )
                        self.install_d3d12_dlls()
                    else:
                        self.update_progress_text(
                            "Setting up vkd3d-proton (GPU rendering)..."
                        )
                        self.update_progress(0.80)
                        self.setup_vkd3d()
                elif self.has_amd_gpu() and (
                    gpu_id.startswith("amd_") or gpu_id.startswith("auto")
                ):
                    self.update_progress_text(
                        "AMD GPU detected - installing DXVK via winetricks..."
                    )
                    self.update_progress(0.80)
                    self.log(
                        "AMD GPU detected - installing DXVK via winetricks", "info"
                    )
                    self.install_dxvk_dlls()
                    self.log("Installing d3d12 DLLs for compatibility...", "info")
                    self.install_d3d12_dlls()
                else:
                    self.update_progress_text("Setting up vkd3d-proton (GPU rendering)...")
                    self.update_progress(0.80)
                    self.setup_vkd3d()
            else:
                self.update_progress_text("Installing d3d12 DLLs...")
                self.update_progress(0.80)
                self.log(
                    "GPU rendering was not chosen, but installing d3d12 DLLs into Wine for compatibility",
                    "info",
                )
                self.install_d3d12_dlls()

            if self.check_cancelled():
                return False

            # Configure Wine
            self.update_progress_text("Configuring Wine with winetricks...")
            self.update_progress(0.90)
            if not self.configure_wine():
                return False

            if self.check_cancelled():
                return False

            self.setup_complete = True
            self.update_progress(1.0)
            self.update_progress_text("Wine setup complete!")
            self.log("\n✓ Wine setup completed!", "success")

            # Refresh installation status to update button states
            self.refresh_status_signal.emit()
            return True

        except Exception as e:
            if not self.check_cancelled():
                self.log(f"Error setting up Wine environment: {e}", "error")
            return False

        finally:
            # Make sure to end the operation even if there was an error or cancellation
            if (
                hasattr(self, "current_operation")
                and self.current_operation == "Setting up Wine environment"
            ):
                self.end_operation()

    def _download_and_extract_winmetadata(self, extract_to_dir):
        """Download WinMetadata.tar.xz and extract it to the specified directory"""
        try:
            # Create temp directory for download
            temp_dir = Path(self.directory) / ".temp_winmetadata"
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            temp_dir.mkdir(exist_ok=True)

            winmetadata_url = "https://github.com/ryzendew/AffinityOnLinux/releases/download/10.4-Wine-Affinity/WinMetadata.tar.xz"
            winmetadata_file = temp_dir / "WinMetadata.tar.xz"

            self.log("Downloading WinMetadata...", "info")
            if not self.download_file(
                winmetadata_url, str(winmetadata_file), "WinMetadata"
            ):
                self.log("Failed to download WinMetadata", "error")
                return False

            self.log("Extracting WinMetadata...", "info")
            self.update_progress_text("Extracting Windows Metadata...")

            # Extract tar.xz file
            try:
                import lzma

                with lzma.open(winmetadata_file, "rb") as xz_file:
                    with tarfile.open(fileobj=xz_file, mode="r") as tar:
                        tar.extractall(extract_to_dir, filter="data")
            except ImportError:
                # Fallback to using xz command if lzma module is not available
                if not self.check_command("xz") and not self.check_command("unxz"):
                    self.log(
                        "xz or unxz is required to extract WinMetadata. Please install xz.",
                        "error",
                    )
                    return False
                tar_file = winmetadata_file.with_suffix(".tar")
                xz_cmd = "xz" if self.check_command("xz") else "unxz"
                success, _, _ = self.run_command(
                    [xz_cmd, "-d", "-k", str(winmetadata_file)], check=True
                )
                if not success:
                    self.log("Failed to decompress WinMetadata archive", "error")
                    return False
                with tarfile.open(tar_file, "r") as tar:
                    tar.extractall(extract_to_dir, filter="data")
                tar_file.unlink()

            # Clean up temp directory
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

            self.log("WinMetadata downloaded and extracted", "success")
            return True
        except Exception as e:
            self.log(f"Failed to download and extract WinMetadata: {e}", "error")
            return False

    def _download_wintypes_dll(self, output_path):
        """Download wintypes.dll to the specified path"""
        try:
            wintypes_url = "https://github.com/ElementalWarrior/wine-wintypes.dll-for-affinity/raw/refs/heads/master/wintypes_shim.dll.so"

            self.log("Downloading wintypes.dll...", "info")
            if not self.download_file(wintypes_url, str(output_path), "wintypes.dll"):
                self.log("Failed to download wintypes.dll", "error")
                return False

            self.log("wintypes.dll downloaded", "success")
            return True
        except Exception as e:
            self.log(f"Failed to download wintypes.dll: {e}", "error")
            return False

    def clear_shadowing_winmds(self, quiet=False):
        """Move Wine's per-namespace winmd files out of the way.

        They shadow the combined Windows.winmd rather than supplementing it:
        RoResolveNamespace walks a namespace up -- Windows.Storage.Streams,
        Windows.Storage, Windows -- and returns the FIRST file that exists. With
        windows.storage.winmd present it never reaches Windows.winmd, and Wine's
        own generated metadata is what it resolves against, which fails with
        TypeLoadException when Affinity is handed a document. So a prefix with
        both sets behaves exactly like a prefix with no combined metadata at all.

        THIS HAS TO RUN LAST. The ten files are not a leftover -- they are part
        of Wine, listed in wine.inf as

            [WinmdFiles]  ->  DestinationDirs: 11,winmetadata

        under [BaseInstall] and [BaseWow64Install], which wineboot re-runs
        through InstallHinfSection on every prefix update. Anything that boots
        the prefix -- a Wine version change, winetricks, installing .NET, the
        Affinity installer itself -- copies all ten straight back. Clearing them
        during Wine setup and stopping there leaves a finished install with the
        metadata shadowed again, which is exactly the state that makes
        double-clicking a document silently do nothing.

        Moved aside rather than deleted: they are Wine's, not ours, and a
        prefix that later stops using the combined metadata will want them.
        Returns how many were moved."""
        dest_dir = (
            Path(self.directory) / "drive_c" / "windows" / "system32" / "WinMetadata"
        )
        if not dest_dir.is_dir():
            return 0
        shadowed = [f for f in dest_dir.glob("*.winmd") if f.name != "Windows.winmd"]
        if not shadowed:
            return 0
        if not (dest_dir / "Windows.winmd").is_file():
            # Nothing to shadow. Removing them here would leave the prefix with
            # no WinRT metadata at all, which is worse than the wrong metadata.
            if not quiet:
                self.log(
                    "Per-namespace winmd files are present but Windows.winmd is not; "
                    "leaving them alone",
                    "warning",
                )
            return 0
        aside = dest_dir / ".wine-shadowed"
        try:
            aside.mkdir(exist_ok=True)
            moved = 0
            for f in shadowed:
                target = aside / f.name
                if target.exists():
                    target.unlink()
                shutil.move(str(f), str(target))
                moved += 1
        except OSError as e:
            self.log(f"Could not move shadowing winmd files aside: {e}", "warning")
            return 0
        if not quiet:
            self.log(
                f"Moved {moved} per-namespace winmd file(s) aside; they shadow the "
                "combined metadata that lets Affinity open a document it is handed",
                "info",
            )
        return moved

    def install_combined_winmetadata(self):
        """Install ONLY the combined Windows.winmd into the prefix.

        The same WinMetadata.tar.xz as setup_winmetadata(), but just one file out
        of it, and that difference decides whether a document opens.

        RoResolveNamespace resolves a namespace by walking up: Windows.Storage.
        Streams, then Windows.Storage, then Windows -- first file that exists
        wins. With the per-namespace files present it stops at, say,
        Windows.Foundation.winmd, and the CLR then fails on assembly identity,
        because those types reference each other as members of the single
        "Windows" assembly rather than of per-namespace ones. Measured: with all
        21 files the document silently never opens; with Windows.winmd alone,
        cold and warm both work.

        Left alone for 9.14 and 10.10, which have their own arrangement."""
        try:
            system32_dir = (
                Path(self.directory) / "drive_c" / "windows" / "system32"
            )
            dest_dir = system32_dir / "WinMetadata"
            dest = dest_dir / "Windows.winmd"

            # Clear any per-namespace winmds first, and do it even when
            # Windows.winmd is already present, so this can repair a prefix as
            # well as populate one. Doing it here is not enough on its own --
            # see clear_shadowing_winmds().
            self.clear_shadowing_winmds()

            if dest.exists():
                self.log("Windows.winmd already installed", "success")
                return True

            with tempfile.TemporaryDirectory() as tmp:
                if not self._download_and_extract_winmetadata(Path(tmp)):
                    self.log("Could not fetch WinMetadata", "warning")
                    return False
                src = Path(tmp) / "WinMetadata" / "Windows.winmd"
                if not src.is_file():
                    self.log("Windows.winmd missing from the archive", "warning")
                    return False
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

            self.log("Windows.winmd installed", "success")
            return True
        except Exception as e:
            self.log(f"Could not install Windows.winmd: {e}", "warning")
            return False

    # Affinity deadlocks at startup when OpenCL initialises on a real GPU, on
    # every Wine from 11.11 onward. It is not a crash and not a slow start: the
    # rasteriser waits on an event that is never signalled, so the splash never
    # clears, the UI never builds and the process sits at a couple of dozen
    # threads instead of the ~150 a finished startup reaches. The backtrace is
    #
    #     ntdll <- kernelbase(WaitForMultipleObjects) <- libkernel
    #           <- libraster <- libpersona
    #
    # Wine builds old enough to predate the regression are left alone, so
    # anyone who wants OpenCL can still have it by choosing one. So are the
    # builds from 11.19, whose Affinity patch set fixes the event callbacks
    # the rasteriser waits on.
    OPENCL_DEADLOCK_FROM = (11, 11)
    OPENCL_FIXED_FROM = (11, 19)

    def wine_deadlocks_on_opencl(self, wine_version=None):
        version = wine_version or self.get_current_wine_version() or ""
        parts = []
        for piece in str(version).split("."):
            digits = "".join(c for c in piece if c.isdigit())
            if not digits:
                break
            parts.append(int(digits))
        if len(parts) < 2:
            return False
        return self.OPENCL_DEADLOCK_FROM <= (parts[0], parts[1]) < self.OPENCL_FIXED_FROM

    def _wine_download_matches(self, wine_file, config):
        """Is this the Wine build the installer was made for?

        True when the config pins no hash. A mismatch is refused, not
        installed: it is either a stale or partial download, or a release
        rebuilt without this installer being updated -- and the second is
        exactly how new installs went three weeks without eight fixes."""
        want = config.get("wine_sha256")
        if not want:
            return True
        try:
            got = _sha256_of(wine_file)
        except OSError as e:
            self.log(f"Could not check the Wine download: {e}", "error")
            return False
        if got == want:
            # Name the pinned release, so a log says which build was installed.
            release = re.search(r"/releases/download/([^/]+)/", config.get("wine_url", ""))
            pinned = f" (release {release.group(1)})" if release else ""
            self.log(f"{config['wine_display_name']}{pinned}: checksum matches", "success")
            return True
        self.log(
            f"The downloaded {config['wine_display_name']} is not the build this "
            f"installer expects (got {got[:16]}..., wanted {want[:16]}...). "
            "Not installing it. If the release was rebuilt, the installer "
            "needs the new checksum.", "error")
        return False

    def install_font_verb_directly(self, verb, env=None):
        """Install a DIRECT_FONT_VERBS verb without winetricks; False means
        use winetricks instead."""
        if self.check_cancelled():
            return False
        return install_font_verb(
            self.directory, self.get_wine_path("wine"), verb,
            lambda url, path: self.download_file(url, path, Path(path).name),
            log=self.log, env=env)

    def repair_fonts(self):
        """Put the prefix's font registrations right; log what changed."""
        wine = self.get_wine_path("wine")
        if not wine.exists():
            return []
        notes = repair_font_registrations(self.directory, wine, self.log)
        if notes:
            self.log(f"Font registrations repaired ({len(notes)} change(s)):", "info")
            for note in notes[:40]:
                self.log(f"  {note}", "info")
        else:
            self.log("Font registrations checked: nothing to repair", "info")
        return notes

    def disable_opencl_if_needed(self, wine_version=None):
        """Turn opencl.dll off in the prefix where leaving it on hangs startup.

        Written to the prefix registry rather than into a launcher, so it holds
        however Affinity is started -- which matters, because the failure only
        showed up through the desktop entry. Every test that launched it by hand
        passed WINEDLLOVERRIDES on the command line and started cleanly, and the
        disagreement between those two took a long time to explain.

        Not conditional on the OpenCL preference: answering yes to that question
        installs OpenCL packages and vkd3d-proton, which is a different thing
        from letting Affinity load opencl.dll and hang."""
        if not self.wine_deadlocks_on_opencl(wine_version):
            # Remove it rather than just not adding it. The override is written
            # into the prefix registry, and the version-switch path swaps only
            # the Wine directory -- so moving to a build that predates the
            # regression left opencl disabled forever, with no way back short
            # of editing the registry by hand.
            try:
                wine = self.get_wine_path("wine")
                if wine.exists():
                    env = os.environ.copy()
                    env["WINEPREFIX"] = self.directory
                    subprocess.run(
                        [str(wine), "reg", "delete",
                         "HKCU\\Software\\Wine\\DllOverrides", "/v", "opencl", "/f"],
                        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=120, check=False,
                    )
            except Exception:
                pass
            return False
        try:
            wine = self.get_wine_path("wine")
            if not wine.exists():
                return False
            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory
            subprocess.run(
                [str(wine), "reg", "add", "HKCU\\Software\\Wine\\DllOverrides",
                 "/v", "opencl", "/d", "", "/f"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=120,
                check=False,
            )
            self.log(
                "Disabled opencl.dll in the prefix: on this Wine, Affinity hangs "
                "during startup when OpenCL initialises on a real GPU",
                "info",
            )
            return True
        except Exception as e:
            self.log(f"Could not disable opencl.dll: {e}", "warning")
            return False

    def wine_resolves_winrt_namespaces(self):
        """True when this Wine build implements RoResolveNamespace instead of
        stubbing it.

        This decides whether installing WinMetadata is worth anything. With a
        stub, nothing ever reads C:\\windows\\system32\\WinMetadata, so putting
        metadata there changes nothing -- which is why 11.12 skips it. With a
        real implementation, a single genuine Windows.winmd in that directory is
        what lets Affinity open a document handed to it on the command line.

        Detected rather than kept as a version list, so a newer build that
        implements it is picked up without editing this file. The implementation
        resolves against the WinMetadata directory by name, so the string is
        present in wintypes.dll only when it is."""
        try:
            wintypes = (
                Path(self.get_wine_path("wine")).parent.parent
                / "lib"
                / "wine"
                / "x86_64-windows"
                / "wintypes.dll"
            )
            if not wintypes.is_file():
                return False
            # Upstream Wine (11.19 and later) implements it too, and spells the
            # directory "WinMetaData"; the Affinity patch set spelled it
            # "WinMetadata". Matching one spelling only read 11.19 as a stub.
            data = wintypes.read_bytes()
            return any(name.encode("utf-16-le") in data
                       for name in ("WinMetadata", "WinMetaData"))
        except Exception:
            return False

    def setup_winmetadata(self):
        """Download and install WinMetadata to system32"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Windows Metadata Installation", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        system32_dir = Path(self.directory) / "drive_c" / "windows" / "system32"
        system32_dir.mkdir(parents=True, exist_ok=True)

        self.update_progress_text("Downloading Windows Metadata...")
        self.log("Downloading and installing Windows metadata...", "info")
        try:
            winmetadata_dest = system32_dir / "WinMetadata"

            # Remove existing WinMetadata if it exists
            if winmetadata_dest.exists():
                shutil.rmtree(winmetadata_dest)
                self.log("Removed existing WinMetadata folder", "info")

            # Download and extract WinMetadata
            if not self._download_and_extract_winmetadata(system32_dir):
                self.log("WinMetadata will not be installed", "warning")
                return

            # Verify WinMetadata was extracted
            if not winmetadata_dest.exists():
                self.log("WinMetadata extraction failed - folder not found", "error")
                return

            self.log("WinMetadata installed to system32", "success")
        except Exception as e:
            self.log(f"Failed to install WinMetadata: {e}", "error")

    def setup_file_manager_integration(self):
        """Install or repair everything needed to open a document by double-clicking it.

        Each step is also part of a normal install and skips itself when already
        done, so this is safe to run repeatedly. It exists because those steps can
        fail independently of the install -- a download that did not resolve, for
        instance -- and re-running the whole install to recover them means
        re-fetching Wine and Affinity for no reason."""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("File Manager Integration", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        wine_binary = self.get_wine_path("wine")
        if not wine_binary.exists():
            self.log("Wine is not set up yet.", "error")
            QMessageBox.warning(
                self,
                "Wine Not Ready",
                "Wine setup must complete first.",
            )
            return

        install_dir = (
            Path(self.directory) / "drive_c" / "Program Files" / "Affinity" / "Affinity"
        )
        if not install_dir.is_dir():
            self.log("Affinity is not installed yet.", "error")
            QMessageBox.warning(
                self,
                "Affinity Not Installed",
                "Install Affinity first, then run this.",
            )
            return

        self.start_operation("File Manager Integration")
        threading.Thread(
            target=self._setup_file_manager_integration_entry, daemon=True
        ).start()

    def _setup_file_manager_integration_entry(self):
        try:
            self.update_progress_text("Installing WinRT interop facade...")
            self.update_progress(0.2)
            self.install_winrt_interop_facade()

            if self.wine_resolves_winrt_namespaces():
                self.update_progress_text("Installing Windows metadata...")
                self.update_progress(0.4)
                self.install_combined_winmetadata()
            else:
                self.log(
                    "This Wine build stubs RoResolveNamespace, so documents cannot be "
                    "opened from the file manager. Switch to a build that implements "
                    "it (Wine 11.16).",
                    "warning",
                )

            self.update_progress_text("Installing the file-manager handler...")
            self.update_progress(0.6)
            self.install_file_manager_handler()

            self.update_progress_text("Updating the desktop entry...")
            self.update_progress(0.8)
            self.create_desktop_entry("Add")

            self.update_progress(1.0)
            handler = (
                Path(self.directory)
                / "drive_c"
                / "Program Files"
                / "Affinity"
                / "Affinity"
                / "affinity-on-linux.exe"
            )
            if handler.exists():
                self.log("Double-clicking a document should now open it", "success")
            else:
                self.log(
                    "The handler is still missing, so the desktop entry was left "
                    "alone. See the errors above.",
                    "warning",
                )
        except Exception as e:
            self.log(f"File manager integration failed: {e}", "error")
        finally:
            self.end_operation()

    def fix_canva_sign_in(self):
        """Install what the Canva sign-in callback needs in an existing Affinity v3 prefix"""
        if not self.affinity_v3_exe_path().exists():
            QMessageBox.warning(self, "Affinity Not Found", f"Affinity v3 is not installed:\n{self.affinity_v3_exe_path()}")
            return
        wine_support = self.canva_sign_in_wine_support()
        if wine_support == "unknown":
            QMessageBox.warning(self, "Wine Not Found", "Could not run the Wine of this prefix.")
            return
        if wine_support == "unsupported":
            self.remove_affinity_url_handler()
            QMessageBox.information(
                self,
                "Wine Version Not Supported",
                "The Canva sign-in fix supports Wine 11.18 and 11.19 with login metadata.\n\n"
                "With other Wine 11 builds the sign-in also needs Windows WinMetadata and the "
                "login Wine patches, which this prefix does not have.",
            )
            return
        self.start_operation("Fix Canva Sign-in")
        threading.Thread(target=self._fix_canva_sign_in_entry, daemon=True).start()

    def _fix_canva_sign_in_entry(self):
        """Wrapper: install the WinRT facades and the affinity:// handler, then end the operation."""
        try:
            facades_installed = self.install_windowsruntime_facades()
            self.repair_affinity_url_protocol_command()
            if self.create_affinity_url_handler() and facades_installed:
                self.log("\n✓ Canva sign-in fix installed", "success")
            else:
                self.log("\n✗ Canva sign-in fix not installed, see the messages above", "error")
        finally:
            self.end_operation()

    @staticmethod
    def _extract_affinity_callback_url(pasted):
        """Return the affinity:// URL from a pasted browser address or link, else None.

        Accepts the raw affinity:// link or the full page address carrying it in
        the url= parameter. The value is a short-lived credential: callers must
        never log it, only its length.
        """
        if not pasted:
            return None
        pasted = pasted.strip()
        if pasted.startswith("affinity://"):
            url = pasted
        else:
            try:
                values = urllib.parse.parse_qs(urllib.parse.urlparse(pasted).query).get("url")
            except Exception:
                return None
            if not values:
                return None
            url = values[0]
        if not url.startswith("affinity://"):
            return None
        if not (20 < len(url) < 8192):
            return None
        return url

    def inject_canva_sign_in_callback(self):
        """Ask for the sign-in callback URL and hand it to Affinity (manual fallback)."""
        if not self.affinity_v3_exe_path().exists():
            QMessageBox.warning(self, "Affinity Not Found", f"Affinity v3 is not installed:\n{self.affinity_v3_exe_path()}")
            return
        self.start_operation("Paste Sign-in URL")
        threading.Thread(target=self._inject_canva_callback_entry, daemon=True).start()

    def _inject_canva_callback_entry(self):
        """Wrapper: paste the callback URL, hand it to Affinity, end the operation."""
        try:
            pasted = (self.get_interactive_response(
                "Paste the sign-in callback URL from the browser, then press Enter.\n\n"
                "Either the full page address or the affinity:// link.\n"
                "Use this only when the browser handoff does not reach Affinity by itself.",
                "") or "").strip()
            url = self._extract_affinity_callback_url(pasted)
            if not url:
                self.log("That does not look like an affinity:// callback URL. Nothing was sent.", "warning")
                return
            exe = self.affinity_v3_exe_path()
            try:
                drive_c = Path(self.directory) / "drive_c"
                windows_exe = "C:\\" + str(exe.relative_to(drive_c)).replace("/", "\\")
            except (OSError, ValueError):
                self.log("Could not map the Affinity exe into the prefix.", "warning")
                return
            wine = self.get_wine_path("wine")
            env = self.get_winetricks_env()
            self.log(f"Handing a {len(url)}-character callback URL to Affinity...", "info")
            success, _, _ = self.run_command(
                [str(wine), str(windows_exe), url], check=False, env=env, capture=True, timeout=120)
            if self.cancel_event.is_set():
                return
            if success:
                self.log("Callback handed to Affinity. If it does not sign in within a few "
                         "seconds, the code expired: start the browser sign-in again and "
                         "paste the fresh URL.", "success")
            else:
                self.log("Affinity did not accept the callback. Make sure Affinity is running, "
                         "then try again with a fresh URL.", "warning")
        finally:
            self.end_operation()

    def reinstall_winmetadata(self):
        """Remove old WinMetadata folder and reinstall fresh"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Reinstall WinMetadata", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Check if Wine is set up
        wine_binary = self.get_wine_path("wine")
        if not wine_binary.exists():
            self.log(
                "Wine is not set up yet. Please setup Wine environment first.", "error"
            )
            QMessageBox.warning(
                self,
                "Wine Not Ready",
                "Wine setup must complete before reinstalling WinMetadata.\n"
                "Please setup Wine environment first.",
            )
            return

        self.start_operation("Reinstall WinMetadata")
        threading.Thread(target=self._reinstall_winmetadata_entry, daemon=True).start()

    def _reinstall_winmetadata_entry(self):
        """Wrapper: reinstall WinMetadata and end operation."""
        try:
            self._reinstall_winmetadata_thread()
        finally:
            self.end_operation()

    def refresh_winmetadata(self, *, context="update"):
        """Reinstall the WinRT metadata, by Wine version, without destroying
        what is already there.

        Two defects this replaces.

        The update path used to do this unconditionally and always via
        setup_winmetadata(), the per-namespace archive. That archive is right
        only for Wine 9.14 and 10.10; on a Wine that resolves namespaces for
        itself the per-namespace files SHADOW the combined Windows.winmd rather
        than supplement it, so every update quietly undid the thing that lets a
        document open from the file manager.

        And it deleted first. A prefix that has been curated -- 85 files against
        the 21 in the archive -- lost that curation to a routine update with no
        way back. So the old directory is moved aside, never removed, and the
        counts are reported: reinstalling should not silently take a prefix
        backwards.
        """
        system32_dir = Path(self.directory) / "drive_c" / "windows" / "system32"
        winmetadata_dir = system32_dir / "WinMetadata"

        self.log("Stopping Wine processes...", "info")
        # Scoped to this prefix: run_command defaults to os.environ.copy(),
        # so with no WINEPREFIX this killed whatever prefix the process had
        # inherited, taking every Wine process it served with it.
        _env = os.environ.copy()
        _env["WINEPREFIX"] = self.directory
        self.run_command(["wineserver", "-k"], check=False, env=_env)
        time.sleep(2)

        before = len(list(winmetadata_dir.glob("*.winmd"))) if winmetadata_dir.exists() else 0
        kept_at = None
        if winmetadata_dir.exists():
            # A second-resolution stamp collides when an install and an update
            # land in the same second, and rename() onto an existing directory
            # fails. Make it unique.
            stamp = time.strftime("%Y%m%d-%H%M%S")
            kept_at = system32_dir / f"WinMetadata.replaced-{stamp}"
            n = 1
            while kept_at.exists():
                kept_at = system32_dir / f"WinMetadata.replaced-{stamp}.{n}"
                n += 1
            try:
                winmetadata_dir.rename(kept_at)
                self.log(f"Existing WinMetadata ({before} files) kept at {kept_at.name}", "info")
            except Exception as e:
                # Do NOT carry on. The 9.14/10.10 branch below rmtree's this
                # directory, so falling through after a failed rename turns
                # "moved aside, never removed" into exactly removal.
                self.log(
                    f"Could not move the existing WinMetadata aside: {e}. "
                    "Stopping rather than risking the copy that is there.",
                    "error",
                )
                return

            # Prune. Nothing else ever removed these, and refresh_winmetadata
            # runs on every update and every reinstall, so they accumulated one
            # folder of winmds per run, forever.
            backups = sorted(system32_dir.glob("WinMetadata.replaced-*"))
            for stale in backups[:-3]:
                try:
                    shutil.rmtree(stale)
                    self.log(f"Pruned old backup {stale.name}", "info")
                except OSError:
                    pass

        system32_dir.mkdir(parents=True, exist_ok=True)

        wine_version = self.get_current_wine_version()
        if wine_version in ["9.14", "10.10"]:
            self.log("Installing fresh WinMetadata...", "info")
            self.setup_winmetadata()
        elif self.wine_resolves_winrt_namespaces():
            self.log("Installing fresh Windows.winmd...", "info")
            self.install_combined_winmetadata()
            self.log("Setting up wintypes.dll override...", "info")
            self.setup_wintypes_dll_override()
            self.log("Copying wintypes.dll for installed Affinity apps...", "info")
            self.copy_wintypes_dll_for_all_apps()
            # Last, and only here: the per-namespace files must go after
            # anything that can run a wineboot, because wine.inf puts them back.
            self.clear_shadowing_winmds(quiet=True)
        else:
            self.log(
                "Skipping WinMetadata and wintypes.dll setup for this Wine (not needed)",
                "info",
            )

        after = len(list(winmetadata_dir.glob("*.winmd"))) if winmetadata_dir.exists() else 0
        if kept_at and after < before:
            self.log(
                f"Note: this prefix had {before} metadata files and now has {after}. "
                f"The previous set is at {kept_at}; restore it if a document stops "
                f"opening from the file manager.",
                "warning",
            )

    def _reinstall_winmetadata_thread(self):
        """Reinstall WinMetadata in background thread"""
        self.refresh_winmetadata(context="reinstall")
        if self.affinity_v3_exe_path().exists():
            self.install_windowsruntime_facades()
            self.create_affinity_url_handler()

        self.log("\n✓ WinMetadata reinstallation completed!", "success")

    def get_latest_vkd3d_version(self):
        """Get the latest vkd3d-proton version from GitHub releases API

        Returns:
            str: Latest version tag (e.g., "3.0a") or None if check fails
        """
        try:
            api_url = "https://api.github.com/repos/HansKristian-Work/vkd3d-proton/releases/latest"
            self.log("Checking for latest vkd3d-proton version...", "info")

            request = urllib.request.Request(api_url)
            request.add_header("User-Agent", "AffinityLinuxInstaller")

            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode())
                latest_version = data.get("tag_name", "").lstrip(
                    "v"
                )  # Remove 'v' prefix if present

                if latest_version:
                    self.log(f"Latest vkd3d-proton version: {latest_version}", "info")
                    return latest_version
                else:
                    self.log("Could not determine latest version from API", "warning")
                    return None
        except urllib.error.URLError as e:
            self.log(f"Failed to check for latest vkd3d-proton version: {e}", "warning")
            return None
        except json.JSONDecodeError as e:
            self.log(f"Failed to parse GitHub API response: {e}", "warning")
            return None
        except Exception as e:
            self.log(f"Error checking for latest vkd3d-proton version: {e}", "warning")
            return None

    def get_installed_vkd3d_version(self):
        """Get the currently installed vkd3d-proton version from cache

        Returns:
            str: Installed version or None if not found
        """
        version_file = Path(self.directory) / "dxvk" / ".vkd3d_version"
        if version_file.exists():
            try:
                return version_file.read_text().strip()
            except Exception:
                return None
        return None

    def set_installed_vkd3d_version(self, version):
        """Store the installed vkd3d-proton version

        Args:
            version: Version string to store
        """
        cache_dir = Path(self.directory) / "dxvk"
        cache_dir.mkdir(parents=True, exist_ok=True)
        version_file = cache_dir / ".vkd3d_version"
        try:
            version_file.write_text(version)
        except Exception as e:
            self.log(f"Failed to save vkd3d version: {e}", "warning")

    def get_latest_dxvk_version(self):
        """Get the latest DXVK version from GitHub releases API (normal version, not steamrt-sniper)

        Returns:
            str: Latest version tag (e.g., "2.3") or None if check fails
        """
        try:
            api_url = "https://api.github.com/repos/doitsujin/dxvk/releases/latest"
            self.log("Checking for latest DXVK version...", "info")

            request = urllib.request.Request(api_url)
            request.add_header("User-Agent", "AffinityLinuxInstaller")

            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode())
                latest_version = data.get("tag_name", "").lstrip(
                    "v"
                )  # Remove 'v' prefix if present

                if latest_version:
                    self.log(f"Latest DXVK version: {latest_version}", "info")
                    return latest_version
                else:
                    self.log("Could not determine latest version from API", "warning")
                    return None
        except urllib.error.URLError as e:
            self.log(f"Failed to check for latest DXVK version: {e}", "warning")
            return None
        except json.JSONDecodeError as e:
            self.log(f"Failed to parse GitHub API response: {e}", "warning")
            return None
        except Exception as e:
            self.log(f"Error checking for latest DXVK version: {e}", "warning")
            return None

    def get_installed_dxvk_version(self):
        """Check if DXVK is installed via winetricks

        Returns:
            str: "winetricks" if installed, None if not found
        """
        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory
        wine = self.get_wine_path("wine")

        dxvk_dlls = ["d3d8", "d3d9", "d3d11", "dxgi"]
        for dll in dxvk_dlls:
            success, stdout, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "query",
                    "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                    "/v",
                    dll,
                ],
                check=False,
                env=env,
                capture=True,
            )
            if success and "native" in stdout:
                return "winetricks"
        return None

    def set_installed_dxvk_version(self, version):
        """Mark DXVK as installed (for compatibility)

        Args:
            version: Version string (typically "winetricks")
        """
        pass

    def install_dxvk_dlls(self):
        """Install DXVK using winetricks and ensure DLL overrides are set correctly

        DXVK is installed via winetricks which should handle DLL overrides, but we verify
        and set them up if needed to ensure proper functionality.
        """
        self.log("Installing DXVK via winetricks...", "info")

        env = os.environ.copy()
        env = self.get_winetricks_env(env)

        # A leftover winetricks/Wine process would make this run queue behind it.
        self.stop_prefix_wine_processes(env, reason="winetricks needs an idle prefix")

        success = self.run_command_streaming(
            self.build_winetricks_command("dxvk", verbose=False),
            env=env,
            progress_callback=None,
        )

        # Always check for 64-bit DLLs regardless of winetricks success
        # (winetricks may fail but still install 32-bit DLLs, or may fail completely)
        system32_dir = Path(self.directory) / "drive_c" / "windows" / "system32"
        dxvk_dll_names = [
            "d3d8.dll",
            "d3d9.dll",
            "d3d10.dll",
            "d3d10_1.dll",
            "d3d10core.dll",
            "d3d11.dll",
            "dxgi.dll",
        ]
        missing_64bit = [
            dll for dll in dxvk_dll_names if not (system32_dir / dll).exists()
        ]

        if missing_64bit:
            self.log(
                "64-bit DXVK DLLs missing in system32, downloading DXVK release...",
                "info",
            )
        latest_version = self.get_latest_dxvk_version()
        if not latest_version:
            latest_version = "2.3"

            dxvk_url = f"https://github.com/doitsujin/dxvk/releases/download/v{latest_version}/dxvk-{latest_version}.tar.gz"
            dxvk_file = Path(self.directory) / f"dxvk-{latest_version}.tar.gz"

            if self.download_file(dxvk_url, str(dxvk_file), "DXVK"):
                try:
                    import tarfile

                    with tarfile.open(dxvk_file, "r:gz") as tar:
                        extracted_count = 0
                        for member in tar.getmembers():
                            if member.name.startswith(
                                f"dxvk-{latest_version}/x64/"
                            ) and member.name.endswith(".dll"):
                                dll_name = Path(member.name).name
                                if dll_name in missing_64bit:
                                    member.name = dll_name
                                    tar.extract(member, system32_dir, filter="data")
                                    extracted_count += 1
                                    self.log(
                                        f"Extracted 64-bit {dll_name} to system32",
                                        "info",
                                    )

                        if extracted_count > 0:
                            self.log(
                                f"Extracted {extracted_count} 64-bit DXVK DLL(s) to system32",
                                "success",
                            )
                        else:
                            self.log("No 64-bit DLLs found in DXVK archive", "warning")
                except Exception as e:
                    self.log(f"Failed to extract DXVK: {e}", "warning")
                finally:
                    if dxvk_file.exists():
                        dxvk_file.unlink()
            else:
                self.log(
                    "Failed to download DXVK, DLLs may not work correctly", "warning"
                )
        else:
            self.log("64-bit DXVK DLLs verified in system32", "success")

        if success:
            self.log("DXVK installed via winetricks, verifying installation...", "info")
        else:
            self.log(
                "Winetricks installation failed, but continuing with manual DXVK setup...",
                "warning",
            )

        # Verify and set up DLL overrides (regardless of winetricks success)
        wine = self.get_wine_path("wine")
        dxvk_dlls = ["d3d8", "d3d9", "d3d10", "d3d10_1", "d3d10core", "d3d11", "dxgi"]
        override_count = 0

        for dll in dxvk_dlls:
            success_check, stdout, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "query",
                    "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                    "/v",
                    dll,
                ],
                check=False,
                env=env,
                capture=True,
            )
            if success_check and "native" in stdout:
                override_count += 1

        if override_count < len(dxvk_dlls):
            self.log("Setting up DLL overrides for DXVK...", "info")
            reg_file = Path(self.directory) / "dxvk_overrides.reg"
            with open(reg_file, "w") as f:
                f.write("REGEDIT4\n")
                f.write("[HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides]\n")
                for dll in dxvk_dlls:
                    f.write(f'"{dll}"="native,builtin"\n')

            regedit = self.get_wine_path("regedit")
            reg_success, _, stderr = self.run_command(
                [str(regedit), str(reg_file)], check=False, env=env, capture=True
            )
            reg_file.unlink()

            if reg_success:
                self.log("DXVK DLL overrides configured", "success")
            else:
                self.log(
                    f"Warning: Could not configure DLL overrides: {stderr}", "warning"
                )
        else:
            self.log(f"DXVK DLL overrides verified ({override_count} DLLs)", "success")

        self.set_installed_dxvk_version("winetricks")

    def install_d3d12_dlls(self):
        """Install d3d12.dll and d3d12core.dll from vkd3d-proton and set up DLL overrides"""
        self.log("Installing d3d12.dll and d3d12core.dll...", "info")

        # Get latest version or use default
        latest_version = self.get_latest_vkd3d_version()
        if not latest_version:
            # Fallback to current latest known version
            latest_version = "3.0a"
            self.log(f"Using fallback version: {latest_version}", "info")

        # Check if we need to update
        installed_version = self.get_installed_vkd3d_version()
        if installed_version and installed_version == latest_version:
            self.log(f"vkd3d-proton {latest_version} is already installed", "info")
        elif installed_version:
            self.log(
                f"Updating vkd3d-proton from {installed_version} to {latest_version}",
                "info",
            )
            # Clear old cache if version changed
            cache_dir = Path(self.directory) / "dxvk"
            old_cached_dir = cache_dir / f"vkd3d-proton-{installed_version}"
            if old_cached_dir.exists():
                try:
                    shutil.rmtree(old_cached_dir)
                    self.log(f"Removed old cached version {installed_version}", "info")
                except Exception as e:
                    self.log(f"Warning: Could not remove old cache: {e}", "warning")

        vkd3d_version = latest_version
        vkd3d_url = f"https://github.com/HansKristian-Work/vkd3d-proton/releases/download/v{vkd3d_version}/vkd3d-proton-{vkd3d_version}.tar.zst"
        vkd3d_file_name = f"vkd3d-proton-{vkd3d_version}.tar.zst"
        cache_dir = Path(self.directory) / "dxvk"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached_vkd3d_file = cache_dir / vkd3d_file_name
        cached_vkd3d_dir = cache_dir / f"vkd3d-proton-{vkd3d_version}"
        vkd3d_temp = Path(self.directory) / "vkd3d_dlls"
        vkd3d_temp.mkdir(exist_ok=True)

        # Check if DLLs already exist
        wine_lib_dir = (
            self.get_wine_dir() / "lib" / "wine" / "vkd3d-proton" / "x86_64-windows"
        )
        if (
            wine_lib_dir.exists()
            and (wine_lib_dir / "d3d12.dll").exists()
            and (wine_lib_dir / "d3d12core.dll").exists()
        ):
            self.log("d3d12 DLLs already installed", "info")
            self.setup_d3d12_overrides()
            return

        # Check cache first
        vkd3d_dir = None
        if cached_vkd3d_dir.exists():
            self.log("Using cached vkd3d-proton...", "info")
            vkd3d_dir = cached_vkd3d_dir
        else:
            # Download vkd3d-proton
            self.log("Downloading vkd3d-proton for d3d12 DLLs...", "info")
            vkd3d_file = Path(self.directory) / vkd3d_file_name
            if not self.download_file(vkd3d_url, str(vkd3d_file), "vkd3d-proton"):
                self.log("Failed to download vkd3d-proton", "error")
                return

            # Cache the downloaded file
            shutil.copy2(vkd3d_file, cached_vkd3d_file)
            self.log("Cached vkd3d-proton archive", "success")

            # Extract vkd3d-proton
            self.log("Extracting vkd3d-proton...", "info")
            if self.check_command("unzstd"):
                tar_file = Path(self.directory) / "vkd3d-proton.tar"
                success, _, _ = self.run_command(
                    ["unzstd", "-f", str(vkd3d_file), "-o", str(tar_file)]
                )
                if success:
                    with tarfile.open(tar_file, "r") as tar:
                        tar.extractall(self.directory, filter="data")
                    tar_file.unlink()
                    self.log("vkd3d-proton extracted", "success")

            vkd3d_file.unlink()

            # Find extracted directory and cache it
            vkd3d_dir = next(Path(self.directory).glob("vkd3d-proton-*"), None)
            if vkd3d_dir:
                # Cache the extracted directory
                shutil.copytree(vkd3d_dir, cached_vkd3d_dir)
                self.log("Cached vkd3d-proton directory", "success")
            else:
                self.log("Failed to find extracted vkd3d-proton directory", "error")
                return

        # Copy DLLs
        if vkd3d_dir:
            wine_lib_dir.mkdir(parents=True, exist_ok=True)

            for dll in ["d3d12.dll", "d3d12core.dll"]:
                for source_dir in [vkd3d_dir / "x64", vkd3d_dir]:
                    src = source_dir / dll
                    if src.exists():
                        shutil.copy2(src, vkd3d_temp / dll)
                        shutil.copy2(src, wine_lib_dir / dll)
                        self.log(f"Installed {dll}", "success")
                        break

            # Only remove if it's not the cached version
            if vkd3d_dir != cached_vkd3d_dir:
                shutil.rmtree(vkd3d_dir)

            # Store installed version
            self.set_installed_vkd3d_version(vkd3d_version)
            self.log(f"d3d12 DLLs installed (vkd3d-proton {vkd3d_version})", "success")

        # Set up DLL overrides
        self.setup_d3d12_overrides()

    def _user_reg_override(self, dll):
        """A DllOverrides value from the prefix's user.reg, or None.

        Read from the file rather than with `wine reg query`, which would start
        Wine to answer. Only as fresh as Wine's last save, so None means
        "set it", never "it is unset"."""
        try:
            text = (Path(self.directory) / "user.reg").read_text(errors="replace")
        except OSError:
            return None
        section = re.search(r"^\[Software\\\\Wine\\\\DllOverrides\][^\n]*\n(.*?)(?:^\[|\Z)",
                            text, re.M | re.S)
        if not section:
            return None
        value = re.search(rf'^"\*?{re.escape(dll)}"="([^"]*)"', section.group(1), re.M)
        return value.group(1) if value else None

    def setup_d3d12_overrides(self):
        """Set up DLL overrides for d3d12.dll and d3d12core.dll"""
        self.log("Setting up DLL overrides for d3d12...", "info")

        dlls = ("d3d12", "d3d12core")
        if all(self._user_reg_override(name) == "native,builtin" for name in dlls):
            self.log("DLL overrides for d3d12 already set", "info")
            return

        env = self.get_winetricks_env()
        wine = self.get_wine_path("wine")
        override_failures = []

        # One regedit for both: every Wine process started here costs seconds.
        reg_file = Path(self.directory) / "d3d12-overrides.reg"
        reg_file.write_text(
            "Windows Registry Editor Version 5.00\r\n\r\n"
            "[HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides]\r\n"
            + "".join(f'"{name}"="native,builtin"\r\n' for name in dlls),
            encoding="utf-16")
        success, _, stderr = self.run_command(
            [str(wine), "regedit", "/S", self.prefix_windows_path(self.directory, reg_file)],
            check=False,
            env=env,
            capture=True
        )
        try:
            reg_file.unlink()
        except OSError:
            pass
        for dll_name in dlls:
            if success:
                self.log(f"Configured DLL override for {dll_name}", "success")
            else:
                override_failures.append(f"{dll_name}: {stderr.strip() or 'unknown error'}")

        if override_failures:
            self.log(
                f"Warning: Could not configure all DLL overrides: {'; '.join(override_failures)}",
                "warning"
            )
        else:
            self.log("DLL overrides configured for d3d12", "success")


    def repair_crypt32_override(self):
        """Force Wine builtin crypt32 (migrates prefixes harmed by native crypt32)

        Older installer runs executed `winetricks crypt32`, which drops in
        Microsoft's native crypt32.dll and sets a native override. Native
        crypt32 cannot validate certificate chains against Wine's registry
        stores, so all HTTPS from the prefix fails at cert verification
        (ERROR_INTERNET_SECURITY_CHANNEL_ERROR 12157): Affinity update
        checks, CanvaAI/cloud features, asset downloads. Wine's builtin
        crypt32 handles the prefix ROOT store correctly. The leftover
        native file in system32 is inert once the override is builtin.
        Only affects new processes; running apps pick it up on restart.
        """
        self.log("Ensuring Wine builtin crypt32 for working TLS...", "info")

        env = self.get_winetricks_env()
        wine = self.get_wine_path("wine")
        override_key = "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides"

        success, _, stderr = self.run_command(
            [str(wine), "reg", "add", override_key, "/v", "*crypt32", "/t", "REG_SZ", "/d", "builtin", "/f"],
            check=False,
            env=env,
            capture=True
        )
        if success:
            self.log("DLL override '*crypt32' set to builtin (TLS chain validation fixed)", "success")
            return True

        self.log(f"Warning: Could not set crypt32 override: {stderr.strip() or 'unknown error'}", "warning")
        return False


    def setup_dxvk_overrides(self):
        """
        Set up DLL overrides for DXVK in Wine registry

        DXVK is installed via winetricks which automatically sets up DLL overrides.
        This function verifies the installation and ensures overrides are correct.
        """
        self.log("Verifying DXVK installation via winetricks...", "info")

        env = os.environ.copy()
        env = self.get_winetricks_env(env)

        wine = self.get_wine_path("wine")

        dxvk_dlls = ["d3d8", "d3d9", "d3d10", "d3d10_1", "d3d10core", "d3d11", "dxgi"]
        override_count = 0

        for dll in dxvk_dlls:
            success, stdout, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "query",
                    "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                    "/v",
                    dll,
                ],
                check=False,
                env=env,
                capture=True,
            )
            if success and "native" in stdout:
                override_count += 1

        if override_count > 0:
            self.log(f"DXVK DLL overrides verified ({override_count} DLLs)", "success")
        else:
            self.log(
                "DXVK DLL overrides not found - winetricks should have set them up",
                "warning",
            )
            self.log("Installing DXVK via winetricks to set up overrides...", "info")
            self.install_dxvk_dlls()

    def remove_dxvk_overrides(self):
        """Remove DXVK via winetricks and clean up DLL overrides"""
        self.log("Removing DXVK via winetricks...", "info")

        env = os.environ.copy()
        env = self.get_winetricks_env(env)

        wine = self.get_wine_path("wine")

        dxvk_dlls = ["d3d8", "d3d9", "d3d10", "d3d10_1", "d3d10core", "d3d11", "dxgi"]
        removed_count = 0

        for dll in dxvk_dlls:
            success, _, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "delete",
                    "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                    "/v",
                    dll,
                    "/f",
                ],
                check=False,
                env=env,
                capture=True,
            )
            if success:
                removed_count += 1

        if removed_count > 0:
            self.log(f"Removed {removed_count} DXVK DLL override(s)", "success")
        else:
            self.log("No DXVK DLL overrides found to remove", "info")

        self.remove_dxvk_dlls_from_system32()

        cache_dir = Path(self.directory) / "dxvk"
        if cache_dir.exists():
            try:
                shutil.rmtree(cache_dir)
                self.log("Removed DXVK cache directory", "success")
            except Exception as e:
                self.log(f"Warning: Could not remove DXVK cache: {e}", "warning")

    def remove_dxvk_dlls_from_system32(self):
        """Remove DXVK DLLs from system32 directory"""
        self.log("Removing DXVK DLLs from system32...", "info")

        system32_dir = Path(self.directory) / "drive_c" / "windows" / "system32"
        dxvk_dlls = ["d3d8.dll", "d3d9.dll", "d3d10core.dll", "d3d11.dll", "dxgi.dll"]
        removed_count = 0

        for dll in dxvk_dlls:
            dll_path = system32_dir / dll
            if dll_path.exists():
                try:
                    dll_path.unlink()
                    self.log(f"Removed {dll} from system32", "success")
                    removed_count += 1
                except Exception as e:
                    self.log(
                        f"Warning: Could not remove {dll} from system32: {e}", "warning"
                    )

        if removed_count > 0:
            self.log(f"Removed {removed_count} DXVK DLL(s) from system32", "success")
        else:
            self.log("No DXVK DLLs found in system32 to remove", "info")

    def remove_d3d12_overrides(self):
        """Remove DLL overrides for vkd3d (d3d12, d3d12core)"""
        self.log("Removing DLL overrides for vkd3d...", "info")

        wine = self.get_wine_path("wine")
        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory

        vkd3d_dlls = ["d3d12", "d3d12core"]
        removed_count = 0

        for dll in vkd3d_dlls:
            success, _, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "delete",
                    "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                    "/v",
                    dll,
                    "/f",
                ],
                check=False,
                env=env,
                capture=True,
            )
            if success:
                removed_count += 1

        if removed_count > 0:
            self.log(f"Removed {removed_count} vkd3d DLL override(s)", "success")
        else:
            self.log("No vkd3d DLL overrides found to remove", "info")

    def setup_vkd3d(self):
        """Setup vkd3d-proton for OpenCL"""
        # Check NVIDIA GPU preference
        if self.has_nvidia_gpu():
            preference = self.get_dxvk_vkd3d_preference()
            if preference == "dxvk":
                self.log(
                    "NVIDIA GPU with DXVK preference - skipping vkd3d-proton installation",
                    "info",
                )
                # Still install d3d12 DLLs and overrides
                self.install_d3d12_dlls()
                return

        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("GPU Rendering Setup (vkd3d-proton)", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Get latest version or use default
        latest_version = self.get_latest_vkd3d_version()
        if not latest_version:
            # Fallback to current latest known version
            latest_version = "3.0a"
            self.log(f"Using fallback version: {latest_version}", "info")

        # Check if we need to update
        installed_version = self.get_installed_vkd3d_version()
        if installed_version and installed_version == latest_version:
            self.log(f"vkd3d-proton {latest_version} is already installed", "info")
        elif installed_version:
            self.log(
                f"Updating vkd3d-proton from {installed_version} to {latest_version}",
                "info",
            )

        vkd3d_version = latest_version
        vkd3d_url = f"https://github.com/HansKristian-Work/vkd3d-proton/releases/download/v{vkd3d_version}/vkd3d-proton-{vkd3d_version}.tar.zst"
        vkd3d_file = Path(self.directory) / f"vkd3d-proton-{vkd3d_version}.tar.zst"
        vkd3d_temp = Path(self.directory) / "vkd3d_dlls"
        vkd3d_temp.mkdir(exist_ok=True)

        self.update_progress_text("Downloading vkd3d-proton...")
        self.log(f"Downloading vkd3d-proton {vkd3d_version}...", "info")
        if not self.download_file(vkd3d_url, str(vkd3d_file), "vkd3d-proton"):
            self.log("Failed to download vkd3d-proton", "error")
            return

        # Extract vkd3d-proton
        self.update_progress_text("Extracting vkd3d-proton...")
        self.log("Extracting vkd3d-proton...", "info")
        if self.check_command("unzstd"):
            tar_file = Path(self.directory) / "vkd3d-proton.tar"
            success, _, _ = self.run_command(
                ["unzstd", "-f", str(vkd3d_file), "-o", str(tar_file)]
            )
            if success:
                with tarfile.open(tar_file, "r") as tar:
                    tar.extractall(self.directory, filter="data")
                tar_file.unlink()
                self.log("vkd3d-proton extracted", "success")

        vkd3d_file.unlink()

        # Copy DLLs
        vkd3d_dir = next(Path(self.directory).glob("vkd3d-proton-*"), None)
        if vkd3d_dir:
            wine_lib_dir = (
                self.get_wine_dir() / "lib" / "wine" / "vkd3d-proton" / "x86_64-windows"
            )
            wine_lib_dir.mkdir(parents=True, exist_ok=True)

            for dll in ["d3d12.dll", "d3d12core.dll"]:
                for source_dir in [vkd3d_dir / "x64", vkd3d_dir]:
                    src = source_dir / dll
                    if src.exists():
                        shutil.copy2(src, vkd3d_temp / dll)
                        shutil.copy2(src, wine_lib_dir / dll)
                        self.log(f"Copied {dll}", "success")
                        break

            shutil.rmtree(vkd3d_dir)

            # Store installed version
            self.set_installed_vkd3d_version(vkd3d_version)
            self.log(
                f"vkd3d-proton setup completed (version {vkd3d_version})", "success"
            )

        # Set up DLL overrides
        self.setup_d3d12_overrides()

    def configure_wine(self):
        """Configure Wine with winetricks"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Wine Configuration", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        env = self.get_winetricks_env()


        wine_cfg = self.get_wine_path("winecfg")

        components = [component for component, _ in WINETRICKS_COMPONENTS]

        # Clear out anything still holding the prefix (a wedged installer from a
        # previous attempt, an abandoned winetricks, a wineserver from another
        # Wine build) — otherwise Windows Installer keeps the next run waiting.
        self.stop_prefix_wine_processes(
            env, reason="winetricks needs an idle prefix"
        )

        prefix_temp_dir(self.directory)
        self.log(
            "Installing Wine components (this may take several minutes)...", "info"
        )
        total_components = len(components)
        for idx, component in enumerate(components):
            if self.cancel_event.is_set():
                return False

            # Every verb starts from a quiet prefix: leftovers from the previous
            # verb are what make Windows Installer queue and the run hang.
            self.stop_prefix_wine_processes(
                env, reason=f"starting '{component}'"
            )

            # Calculate base progress for this component (0.0 to 1.0 across all components)
            base_progress = idx / total_components
            component_progress_range = 1.0 / total_components

            # Update progress label to show current component
            self.update_progress_text(
                f"Installing: {component} ({idx + 1}/{total_components})"
            )

            self.log(
                f"Installing {component}... [{idx + 1}/{total_components}]", "info"
            )
            self.log("  (Progress will be shown below)", "info")

            # Progress callback that updates based on component progress
            def update_component_progress(percent):
                # percent is 0.0-1.0 for this component
                # Map it to overall progress
                overall_progress = base_progress + (percent * component_progress_range)
                self.update_progress(overall_progress)

            # The fonts go in directly; winetricks only if that fails.
            component_ok = (component in DIRECT_FONT_VERBS
                            and self.install_font_verb_directly(component, env))
            # Use streaming to show progress
            if not component_ok:
                component_ok = self.run_command_streaming(
                    self.build_winetricks_command(component),
                    env=env,
                    progress_callback=update_component_progress,
                    stall_timeout=600,
                    activity_probe=self._prefix_activity,
                    hard_limit=2700,
                )
            # The .NET installers' 32-bit setups crash intermittently under
            # Wine 11's new WoW64 (an unhandled page fault high in the 32-bit
            # address space); clean runs of the same verb succeed. Once more,
            # from a stopped prefix, before giving up on one Affinity needs.
            # A stall gets the retry too: the .NET 4.0 self-extractor has been
            # seen to hang mid-unpack (and the stall watchdog to kill it) on one
            # machine while the same verb ran through on another.
            if (not component_ok and component.startswith("dotnet")
                    and not self.cancel_event.is_set()):
                how = "stalled" if self._last_command_stalled else "failed"
                self.log(f"'{component}' {how}; stopping the prefix's Wine and trying once more", "warning")
                self.stop_prefix_wine_processes(env, reason=f"retrying '{component}'")
                component_ok = self.run_command_streaming(
                    self.build_winetricks_command(component),
                    env=env,
                    progress_callback=update_component_progress,
                    stall_timeout=600,
                    activity_probe=self._prefix_activity,
                    hard_limit=2700,
                )
            # Go by what is in the prefix, not by winetricks' exit: .NET can be
            # complete while its installer is still being waited on.
            if (not component_ok and component == "dotnet48"
                    and not self.cancel_event.is_set() and self.has_dotnet48_runtime()):
                self.log("'dotnet48' reported a problem, but .NET Framework 4.8 is installed", "success")
                component_ok = True
                self._last_command_stalled = False
            if not component_ok and not self.cancel_event.is_set():
                if self._last_command_stalled:
                    self._stalled_components.add(component)
                    self.log(
                        f"'{component}' stalled — Wine stopped responding and was stopped.",
                        "error",
                    )
                    self.log(
                        "If this repeats, switch to the other Wine version (11.18 / 11.19) and try again (Wine 11+ new WoW64 hangs winetricks).",
                        "warning",
                    )
                else:
                    self.log(f"'{component}' failed — continuing with the rest", "warning")

            # Mark this component as complete
            self.update_progress(base_progress + component_progress_range)

        if not self.cancel_event.is_set():
            self.ensure_vulkan_renderer(env)

        # Set Windows version to 11
        self.log("Setting Windows version to 11...", "info")
        # A leftover process would make winecfg queue behind it (or talk to a
        # wineserver belonging to a different Wine build).
        self.stop_prefix_wine_processes(env, reason="setting Windows version")
        self.run_command([str(wine_cfg), "-v", "win11"], check=False, env=env)

        # Apply dark theme
        self.log("Applying Wine dark theme...", "info")
        theme_file = Path(self.directory) / "wine-dark-theme.reg"
        if self.download_file(
            "https://raw.githubusercontent.com/seapear/AffinityOnLinux/refs/heads/main/Auxiliary/Other/wine-dark-theme.reg",
            str(theme_file),
            "dark theme",
        ):
            regedit = self.get_wine_path("regedit")
            self.run_command([str(regedit), str(theme_file)], check=False, env=env)
            theme_file.unlink()

        # Migrate prefixes created when `crypt32` was still installed native.
        self.repair_crypt32_override()

        if not self.verify_required_wine_runtimes():
            self.update_progress_text("Missing required Wine runtimes")
            return False

        self.log("Wine configuration completed", "success")
        self.update_progress_text("Ready")
        return True


    def show_main_menu(self):
        """Display main application menu"""
        self.log("\n✓ Setup complete! Select an application to install:", "success")
        self.update_progress(1.0)

    def setup_wine_environment(self):
        """Setup Wine environment only"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Setup Wine Environment", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Ask user to choose Wine version
        wine_version = self.show_question_dialog(
            "Choose Wine Version",
            "Which Wine version would you like to install?\n\n"
            "• Wine 11.19 (Recommended) - Latest build with the full Affinity patch set: Direct2D throughput and brush-latency fixes, wined3d Vulkan presentation fixes, OpenCL event dispatcher, pen pressure, plus color, printing and login fixes.\n"
            "• Wine 11.18 - Previous build with the Affinity login fix and performance patches (D2D geometry cache, OpenCL cache, SDR white-level and printer mapping). Fallback if 11.19 has issues.\n\n"
            "Note: You can switch versions later by running this setup again.",
            ["Wine 11.19 (Recommended)", "Wine 11.18"],
        )

        if wine_version == "Wine 11.19 (Recommended)":
            wine_version_choice = "11.19"
        elif wine_version == "Wine 11.18":
            wine_version_choice = "11.18"
        else:
            self.log("Wine setup cancelled", "warning")
            return

        threading.Thread(
            target=self.setup_wine, args=(wine_version_choice,), daemon=True
        ).start()

    def _get_wine_version_config(self, wine_version):
        config = AffinityInstallerGUI._pinned_wine_version_config(self, wine_version)
        if config and "wine_url" in config:
            config = dict(config, wine_url=release_download_url(config["wine_url"]))
        return config

    def _pinned_wine_version_config(self, wine_version):
        """Get Wine version configuration (URL, filename, SHA-256, etc.)

        Args:
            wine_version: "11.18" or "11.19"

        Returns:
            dict with wine_url, wine_file_name, wine_sha256, wine_dir_name, wine_dir_pattern, archive_format, wine_display_name
        """
        if wine_version == "11.18":
            return {
                # POC SOURCE -- the fork's release of the 11.18 patch set.
                "wine_url": "https://github.com/jfacemyer/Affinity-Wine-Builder/releases/download/11.18-r1/ElementalWarrior-wine-11.18.tar.xz",
                "wine_file_name": "ElementalWarrior-wine-11.18.tar.xz",
                "wine_sha256": WINE_11_18_SHA256,
                "wine_dir_name": "ElementalWarriorWine",
                "wine_dir_pattern": "ElementalWarrior-wine-11.18*",
                "archive_format": "xz",
                "wine_display_name": "Wine 11.18 (Affinity login fix + performance patches)",
            }
        else:  # Default to 11.19
            return {
                # POC SOURCE -- the fork's release of the 11.19 patch set.
                "wine_url": "https://github.com/jfacemyer/Affinity-Wine-Builder/releases/download/11.19-r10/ElementalWarrior-wine-11.19.tar.xz",
                "wine_file_name": "ElementalWarrior-wine-11.19.tar.xz",
                "wine_sha256": WINE_11_19_SHA256,
                "wine_dir_name": "ElementalWarriorWine",
                "wine_dir_pattern": "ElementalWarrior-wine-11.19*",
                "archive_format": "xz",
                "wine_display_name": "Wine 11.19 (Latest - full Affinity patch set)",
            }

    def _download_wine_to_cache(self, wine_version, cache_dir):
        """Download a Wine version to cache directory

        Args:
            wine_version: "11.18" or "11.19"
            cache_dir: Path to cache directory

        Returns:
            True if successful, False otherwise
        """
        config = self._get_wine_version_config(wine_version)
        wine_file = cache_dir / config["wine_file_name"]
        wine_dir = cache_dir / wine_version

        # Check if already cached
        if wine_dir.exists() and (wine_dir / "bin" / "wine").exists():
            self.log(
                f"{config['wine_display_name']} already cached, skipping download",
                "info",
            )
            return True

        # Download Wine binary
        self.log(f"Caching {config['wine_display_name']}...", "info")
        if not self.download_file(
            config["wine_url"],
            str(wine_file),
            f"{config['wine_display_name']} binaries",
        ):
            self.log(f"Failed to cache {config['wine_display_name']}", "warning")
            return False
        if not self._wine_download_matches(wine_file, config):
            return False

        if self.check_cancelled():
            return False

        # Extract Wine
        self.log(f"Extracting {config['wine_display_name']}...", "info")
        try:
            if config["archive_format"] == "gz":
                with tarfile.open(wine_file, "r:gz") as tar:
                    tar.extractall(cache_dir, filter="data")
            elif config["archive_format"] == "xz":
                try:
                    import lzma

                    with lzma.open(wine_file, "rb") as xz_file:
                        with tarfile.open(fileobj=xz_file, mode="r") as tar:
                            tar.extractall(cache_dir, filter="data")
                except ImportError:
                    if not self.check_command("xz") and not self.check_command("unxz"):
                        self.log(
                            "xz or unxz is required to extract Wine archive. Please install xz.",
                            "warning",
                        )
                        wine_file.unlink()
                        return False
                    tar_file = wine_file.with_suffix(".tar")
                    xz_cmd = "xz" if self.check_command("xz") else "unxz"
                    success, _, _ = self.run_command(
                        [xz_cmd, "-d", "-k", str(wine_file)], check=True
                    )
                    if not success:
                        self.log("Failed to decompress Wine archive", "warning")
                        wine_file.unlink()
                        return False
                    with tarfile.open(tar_file, "r") as tar:
                        tar.extractall(cache_dir, filter="data")
                    tar_file.unlink()

            wine_file.unlink()

            # Find extracted directory and rename to version name
            extracted_dir = next(cache_dir.glob(config["wine_dir_pattern"]), None)
            if extracted_dir:
                if extracted_dir != wine_dir:
                    if wine_dir.exists():
                        shutil.rmtree(wine_dir)
                    extracted_dir.rename(wine_dir)
                self.log(f"Cached {config['wine_display_name']}", "success")
                return True
            else:
                self.log(
                    f"Could not find extracted Wine directory for {wine_version}",
                    "warning",
                )
                return False

        except Exception as e:
            self.log(f"Failed to extract cached Wine {wine_version}: {e}", "warning")
            if wine_file.exists():
                wine_file.unlink()
            return False

    def _download_all_wine_versions_to_cache(self, selected_version):
        """Download all Wine versions to cache directory (except the one already being installed)

        Args:
            selected_version: The version that's already being downloaded/installed
        """
        cache_dir = Path(self.directory) / "Wine-Switch"
        cache_dir.mkdir(parents=True, exist_ok=True)

        all_versions = ["11.18", "11.19"]

        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Caching All Wine Versions", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        self.log(
            "Downloading all Wine versions to cache for future switching...", "info"
        )
        self.log(
            "This helps users with capped internet by avoiding re-downloads.\n", "info"
        )

        for version in all_versions:
            if version == selected_version:
                # Already downloading this one, skip
                continue

            if self.check_cancelled():
                return

            self._download_wine_to_cache(version, cache_dir)

        self.log("\n✓ All Wine versions cached successfully!", "success")

    def _cache_dxvk(self):
        """DXVK is now handled by winetricks, which manages its own caching.

        This function is kept for compatibility but no longer performs manual caching.
        """
        self.log("DXVK caching is handled automatically by winetricks", "info")

    def _check_and_update_dxvk_vkd3d(self):
        """Check if DXVK or vkd3d-proton need updating and update them if needed
        Also download DXVK if missing.
        Runs in background thread to avoid blocking GUI.
        """
        threading.Thread(
            target=self._check_and_update_dxvk_vkd3d_thread, daemon=True
        ).start()

    def _check_and_update_dxvk_vkd3d_thread(self):
        """Background thread to check DXVK/vkd3d-proton status"""
        try:
            # Only check if Wine is already set up
            wine_dir = self.get_wine_dir()
            if not wine_dir.exists():
                return  # Wine not set up yet, skip check

            self.log("Checking DXVK and vkd3d-proton status...", "info")

            # Check if DXVK is installed via winetricks
            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory
            wine = self.get_wine_path("wine")

            dxvk_installed = False
            dxvk_dlls = ["d3d8", "d3d9", "d3d11", "dxgi"]
            for dll in dxvk_dlls:
                success, stdout, _ = self.run_command(
                    [
                        str(wine),
                        "reg",
                        "query",
                        "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                        "/v",
                        dll,
                    ],
                    check=False,
                    env=env,
                    capture=True,
                )
                if success and "native" in stdout:
                    dxvk_installed = True
                    break

            if dxvk_installed:
                self.log("DXVK is installed via winetricks", "info")
            else:
                if self.has_amd_gpu():
                    self.log(
                        "AMD GPU detected - DXVK should be installed via winetricks",
                        "info",
                    )
                else:
                    self.log(
                        "DXVK not installed (will be installed when switching to DXVK)",
                        "info",
                    )

            # Check vkd3d-proton
            latest_vkd3d = self.get_latest_vkd3d_version()
            if latest_vkd3d:
                installed_vkd3d = self.get_installed_vkd3d_version()
                cache_dir = Path(self.directory) / "dxvk"
                cached_vkd3d_dir = cache_dir / f"vkd3d-proton-{latest_vkd3d}"

                # Check if vkd3d-proton is missing or outdated
                if not installed_vkd3d or installed_vkd3d != latest_vkd3d:
                    if not cached_vkd3d_dir.exists():
                        self.log(
                            f"vkd3d-proton {latest_vkd3d} is missing or outdated, will download when needed",
                            "info",
                        )
                    elif installed_vkd3d != latest_vkd3d:
                        self.log(
                            f"vkd3d-proton update available: {installed_vkd3d} -> {latest_vkd3d}",
                            "info",
                        )
                        self.log(
                            "Update will be downloaded when switching to vkd3d", "info"
                        )

            self.log("DXVK and vkd3d-proton check completed", "success")

        except Exception as e:
            self.log(f"Error checking DXVK/vkd3d-proton updates: {e}", "warning")

    def _setup_wine_switch(self, wine_version="11.19"):
        """Setup Wine binary only - for switching versions without reconfiguration

        Args:
            wine_version: "11.18" or "11.19" (recommended)
        """
        try:
            # Get Wine version configuration
            config = self._get_wine_version_config(wine_version)
            wine_url = config["wine_url"]
            wine_file_name = config["wine_file_name"]
            wine_dir_name = config["wine_dir_name"]
            wine_dir_pattern = config["wine_dir_pattern"]
            archive_format = config["archive_format"]
            wine_display_name = config["wine_display_name"]

            # Check cache first
            cache_dir = Path(self.directory) / "Wine-Switch"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cached_wine_dir = cache_dir / wine_version

            if cached_wine_dir.exists() and (cached_wine_dir / "bin" / "wine").exists():
                # Use cached version
                self.log(f"Using cached {wine_display_name}...", "info")
                self.update_progress_text(f"Using cached {wine_display_name}...")
                self.update_progress(0.3)

                # Create directory
                Path(self.directory).mkdir(parents=True, exist_ok=True)

                if self.check_cancelled():
                    return False

                # Copy from cache
                self.update_progress_text("Copying Wine from cache...")
                self.update_progress(0.5)
                self.log("Copying Wine from cache...", "info")

                # Find and link Wine directory
                wine_dir = next(Path(self.directory).glob(wine_dir_pattern), None)
                if wine_dir and wine_dir != Path(self.directory) / wine_dir_name:
                    target = Path(self.directory) / wine_dir_name
                    if target.exists() or target.is_symlink():
                        if target.is_symlink():
                            target.unlink()
                        elif target.is_dir():
                            shutil.rmtree(target)
                    target.symlink_to(wine_dir)
                else:
                    # Copy from cache
                    target = Path(self.directory) / wine_dir_name
                    if target.exists() or target.is_symlink():
                        if target.is_symlink():
                            target.unlink()
                        elif target.is_dir():
                            shutil.rmtree(target)
                    shutil.copytree(cached_wine_dir, target)

                self.log("Wine copied from cache", "success")
            else:
                # Download and cache
                self.log(
                    f"Selected version: {wine_version} -> Downloading: {wine_display_name}",
                    "info",
                )
                self.log(f"Download URL: {wine_url}", "info")

                # Create directory
                Path(self.directory).mkdir(parents=True, exist_ok=True)

                if self.check_cancelled():
                    return False

                # Download Wine binary
                wine_file = Path(self.directory) / wine_file_name
                self.update_progress_text(f"Downloading {wine_display_name}...")
                self.update_progress(0.4)
                self.log(f"Downloading {wine_display_name}...", "info")
                if not self.download_file(
                    wine_url, str(wine_file), f"{wine_display_name} binaries"
                ):
                    self.log(f"Failed to download {wine_display_name}", "error")
                    return False
                if not self._wine_download_matches(wine_file, config):
                    return False

                if self.check_cancelled():
                    return False

                # Extract Wine
                self.update_progress_text("Extracting Wine binary...")
                self.update_progress(0.6)
                self.log("Extracting Wine binary...", "info")
                try:
                    if archive_format == "gz":
                        with tarfile.open(wine_file, "r:gz") as tar:
                            tar.extractall(self.directory, filter="data")
                    elif archive_format == "xz":
                        try:
                            import lzma

                            with lzma.open(wine_file, "rb") as xz_file:
                                with tarfile.open(fileobj=xz_file, mode="r") as tar:
                                    tar.extractall(self.directory, filter="data")
                        except ImportError:
                            if not self.check_command("xz") and not self.check_command(
                                "unxz"
                            ):
                                self.log(
                                    "xz or unxz is required to extract Wine archive. Please install xz.",
                                    "error",
                                )
                                return False
                            tar_file = wine_file.with_suffix(".tar")
                            xz_cmd = "xz" if self.check_command("xz") else "unxz"
                            success, _, _ = self.run_command(
                                [xz_cmd, "-d", "-k", str(wine_file)], check=True
                            )
                            if not success:
                                self.log("Failed to decompress Wine archive", "error")
                                return False
                            with tarfile.open(tar_file, "r") as tar:
                                tar.extractall(self.directory, filter="data")
                            tar_file.unlink()

                    wine_file.unlink()
                    self.log("Wine binary extracted", "success")
                except Exception as e:
                    self.log(f"Failed to extract Wine: {e}", "error")
                    return False

                # Cache this version for future use
                cache_dir.mkdir(parents=True, exist_ok=True)
                extracted_dir = next(Path(self.directory).glob(wine_dir_pattern), None)
                if extracted_dir:
                    cached_wine_dir = cache_dir / wine_version
                    if cached_wine_dir.exists():
                        shutil.rmtree(cached_wine_dir)
                    shutil.copytree(extracted_dir, cached_wine_dir)
                    self.log(f"Cached {wine_display_name} for future use", "success")

                if self.check_cancelled():
                    return False

                # Find and link Wine directory
                self.update_progress(0.8)
                wine_dir = next(Path(self.directory).glob(wine_dir_pattern), None)
                if wine_dir and wine_dir != Path(self.directory) / wine_dir_name:
                    target = Path(self.directory) / wine_dir_name
                    if target.exists() or target.is_symlink():
                        if target.is_symlink():
                            target.unlink()
                        elif target.is_dir():
                            shutil.rmtree(target)
                    target.symlink_to(wine_dir)
                    self.log("Wine symlink created", "success")

            # Verify Wine binary
            self.update_progress(0.9)
            wine_binary = Path(self.directory) / wine_dir_name / "bin" / "wine"
            if not wine_binary.exists():
                self.log("Wine binary not found", "error")
                return False

            self.log("Wine binary verified", "success")
            self.update_progress(1.0)
            return True

        except Exception as e:
            self.log(f"Error installing Wine: {e}", "error")
            return False

    def update_wine_version(self, *_):
        """Switch Wine Version, then the fixes a new install applies for the
        version chosen -- see _apply_wine_version_fixes."""
        return self.switch_wine_version(with_fixes=True)

    def _apply_wine_version_fixes(self, wine_version):
        """What a new install does for a Wine version after installing it, so
        a switched prefix ends up the same: WinMetadata where that Wine reads
        it, OpenCL on or off for it, the WinRT facades and the file-manager
        handler where Affinity is installed, and the font registrations.
        Each step is independent; one failing does not stop the rest."""
        self.log("Applying the fixes for this Wine version...", "info")
        steps = []
        if wine_version in ("9.14", "10.10"):
            steps.append(("Windows Metadata", self.setup_winmetadata))
        elif self.wine_resolves_winrt_namespaces():
            steps.append(("Windows Metadata", self.install_combined_winmetadata))
        steps.append(("OpenCL setting", lambda: self.disable_opencl_if_needed(wine_version)))
        if self.affinity_v3_exe_path().exists():
            steps.append(("WinRT facades", self.install_windowsruntime_facades))
            steps.append(("File-manager handler", self.install_file_manager_handler))
        steps.append(("Font registrations", self.repair_fonts))
        for label, step in steps:
            if self.check_cancelled():
                return
            self.update_progress_text(f"Applying fixes: {label}...")
            try:
                step()
            except Exception as e:
                self.log(f"{label}: {e}", "warning")
        self.log("Fixes for this Wine version applied", "success")

    def switch_wine_version(self, with_fixes=False):
        """Switch to a different Wine version - removes current and installs new one"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Switch Wine Version", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Check if Wine is installed
        wine_dir = self.get_wine_dir()
        if not wine_dir.exists():
            self.log(
                "No Wine installation found. Use 'Setup Wine Environment' to install Wine first.",
                "warning",
            )
            QMessageBox.warning(
                self,
                "No Wine Installation",
                "No Wine installation found.\n\n"
                "Please use 'Setup Wine Environment' to install Wine first.",
            )
            return

        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Switch Wine Version",
            "This will remove the current Wine installation and install a new version.\n\n"
            "Your Wine prefix and installed applications will NOT be affected.\n"
            "Only the Wine binary will be replaced.\n\n"
            "Do you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            self.log("Wine version switch cancelled", "warning")
            return

        # Ask user to choose Wine version
        wine_version = self.show_question_dialog(
            "Choose Wine Version",
            "Which Wine version would you like to install?\n\n"
            "• Wine 11.19 (Recommended) - Latest build with the full Affinity patch set: Direct2D throughput and brush-latency fixes, wined3d Vulkan presentation fixes, OpenCL event dispatcher, pen pressure, plus color, printing and login fixes.\n"
            "• Wine 11.18 - Previous build with the Affinity login fix and performance patches (D2D geometry cache, OpenCL cache, SDR white-level and printer mapping). Fallback if 11.19 has issues.\n\n"
            "Note: This will replace your current Wine installation.",
            ["Wine 11.19 (Recommended)", "Wine 11.18"],
        )

        if wine_version == "Wine 11.19 (Recommended)":
            wine_version_choice = "11.19"
        elif wine_version == "Wine 11.18":
            wine_version_choice = "11.18"
        else:
            self.log("Wine version switch cancelled", "warning")
            return

        # Run the switch in a thread
        threading.Thread(
            target=self._switch_wine_version_thread,
            args=(wine_version_choice, with_fixes is True),
            daemon=True,
        ).start()

    def _switch_wine_version_thread(self, wine_version, with_fixes=False):
        """Thread function to switch Wine version"""
        self.start_operation("Switching Wine Version")

        try:
            # Check if cancelled
            if self.check_cancelled():
                return False

            self.log(
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            self.log("Switching Wine Version", "info")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )

            # Step 1: Stop Wine processes
            self.update_progress_text("Stopping Wine processes...")
            self.update_progress(0.1)
            self.log("Stopping Wine processes...", "info")
            # Scoped to this prefix: run_command defaults to os.environ.copy(),
            # so with no WINEPREFIX this killed whatever prefix the process had
            # inherited, taking every Wine process it served with it.
            _env = os.environ.copy()
            _env["WINEPREFIX"] = self.directory
            self.run_command(["wineserver", "-k"], check=False, env=_env)
            time.sleep(1)  # Give processes time to terminate

            if self.check_cancelled():
                return False

            # Step 2: Remove current Wine installation (not applicable for system Wine)
            wine_dir = self.get_wine_dir()
            if wine_dir and wine_dir.exists():
                self.update_progress_text("Removing current Wine installation...")
                self.update_progress(0.2)
                self.log(f"Removing current Wine installation: {wine_dir}", "info")
                try:
                    if wine_dir.is_symlink():
                        wine_dir.unlink()
                        self.log("Wine symlink removed", "success")
                    else:
                        shutil.rmtree(wine_dir)
                        self.log("Wine directory removed", "success")
                except Exception as e:
                    self.log(f"Error removing Wine directory: {e}", "error")
                    # Try to continue anyway - setup_wine will handle it

            # Also remove any old wine archive files
            wine_archives = list(Path(self.directory).glob("ElementalWarrior*.tar.*"))
            for archive in wine_archives:
                try:
                    archive.unlink()
                    self.log(f"Removed old archive: {archive.name}", "info")
                except Exception:
                    pass

            if self.check_cancelled():
                return False

            # Step 3: Install new Wine version (skip configuration to preserve existing setup)
            self.update_progress_text(f"Installing Wine {wine_version}...")
            self.update_progress(0.3)
            self.log(
                f"\nInstalling Wine version: {wine_version} (preserving existing configuration)...",
                "info",
            )

            # Call _setup_wine_switch which only replaces the binary, no reconfiguration
            # Pass the wine_version parameter to ensure the correct version is downloaded
            success = self._setup_wine_switch(wine_version)

            if not success:
                self.log(f"Failed to install Wine version: {wine_version}", "error")
            elif with_fixes:
                self._apply_wine_version_fixes(wine_version)

            if success:
                self.log(
                    "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                self.log("Wine version switched successfully!", "success")
                self.log(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                )
                self.update_progress_text("Wine version switched")
                self.update_progress(1.0)

                # Refresh installation status
                self.refresh_status_signal.emit()
            else:
                self.log(
                    "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                self.log("Failed to switch Wine version", "error")
                self.log(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                )
                self.update_progress_text("Failed to switch Wine version")

            self.end_operation()
            return success

        except Exception as e:
            self.log(f"Error switching Wine version: {e}", "error")
            self.update_progress_text("Error switching Wine version")
            self.end_operation()
            return False

    def install_winetricks_deps(self):
        """Install winetricks dependencies - wrapper for button"""
        self.install_winetricks_dependencies()

    def install_system_dependencies(self):
        """Install system dependencies"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Installing System Dependencies", "info")

        # Start operation and check for cancellation
        self.start_operation("Installing System Dependencies")
        if self.check_cancelled():
            return
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        threading.Thread(target=self._install_system_deps, daemon=True).start()

    def _install_system_deps(self):
        """Install system dependencies in thread"""
        if self.distro == "pikaos":
            self.log("Using PikaOS dependency installation...", "info")
            success = self.install_pikaos_dependencies()
            if success:
                # Also install .NET SDK if not already installed
                if not self.check_dotnet_sdk():
                    self.log("Installing .NET SDK...", "info")
                    self.install_dotnet_sdk()
            self.log(
                "System dependencies installation completed"
                if success
                else "System dependencies installation failed",
                "success" if success else "error",
            )
            self.end_operation()
            return

        if not self.distro:
            self.detect_distro()

        # Check for distributions that should be directed to PikaOS instead
        if self.distro in ["bazzite"]:
            distro_name = self.format_distro_name()
            message = f"""{distro_name} is not officially supported for optimal Affinity compatibility.

For better support and compatibility, we recommend installing PikaOS - a Debian-based distribution specifically optimized for gaming and compatibility:

https://wiki.pika-os.com/en/home

PikaOS provides:
• Better Wine compatibility
• Gaming-focused optimizations
• Regular updates for Affinity applications
• Debian base with enhanced package management

Would you like to continue with {distro_name} anyway?"""

            reply = self.show_question_dialog(
                f"{distro_name} Not Recommended", message, ["Continue Anyway", "Cancel"]
            )

            if reply == "Cancel":
                self.log(
                    f"Installation cancelled by user due to {distro_name} recommendation",
                    "warning",
                )
                self.end_operation()
                return False

        self.log(f"Installing dependencies for {self.format_distro_name()}...", "info")
        success = self.install_dependencies()

        # After installing main dependencies, check and install .NET SDK if missing
        # (it should be included in install_dependencies, but check anyway)
        if success:
            if not self.check_dotnet_sdk():
                self.log(
                    ".NET SDK not found in installed packages. Installing separately...",
                    "info",
                )
                self.install_dotnet_sdk()
            else:
                self.log(".NET SDK is already installed", "success")

        self.log(
            "System dependencies installation completed"
            if success
            else "System dependencies installation failed",
            "success" if success else "error",
        )
        self.end_operation()
        return success

    def install_winetricks_dependencies(self):
        """Install winetricks dependencies"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Installing Winetricks Dependencies", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Start operation and check for cancellation
        self.start_operation("Installing Winetricks Dependencies")
        if self.check_cancelled():
            return

        # Check if Wine is set up
        wine_binary = self.get_wine_path("wine")
        if not wine_binary.exists():
            self.log(
                "Wine is not set up yet. Please wait for Wine setup to complete.",
                "error",
            )
            QMessageBox.warning(
                self,
                "Wine Not Ready",
                "Wine setup must complete before installing winetricks dependencies.",
            )
            self.end_operation()
            return

        threading.Thread(target=self._install_winetricks_deps, daemon=True).start()

    def _install_winetricks_deps(self):
        """Install winetricks dependencies in thread"""
        try:
            if self.check_cancelled():
                return False

            env = self.get_winetricks_env()
            wine_cfg = self.get_wine_path("winecfg")
            components = list(WINETRICKS_COMPONENTS)

            had_failures = False

            def make_progress_callback(base_progress, component_progress_range):
                def update_component_progress(percent):
                    overall_progress = base_progress + (percent * component_progress_range)
                    self.update_progress(overall_progress)
                return update_component_progress

            prefix_temp_dir(self.directory)
            self.log("Installing Wine components (this may take several minutes)...", "info")

            # Clear out anything still holding the prefix (a wedged installer
            # from a previous attempt, an abandoned winetricks, a wineserver
            # from another Wine build) before Windows Installer is touched.
            self.stop_prefix_wine_processes(
                env, reason="winetricks needs an idle prefix"
            )

            total_components = len(components)
            for idx, (component, description) in enumerate(components):
                if self.check_cancelled():
                    return False

                # Every verb starts from a quiet prefix: leftovers from the
                # previous verb are what make Windows Installer queue and hang.
                self.stop_prefix_wine_processes(
                    env, reason=f"starting '{component}'"
                )

                base_progress = idx / total_components
                component_progress_range = 1.0 / total_components
                progress_callback = make_progress_callback(base_progress, component_progress_range)

                self.update_progress_text(f"Installing: {description} ({idx + 1}/{total_components})")
                self.log(f"Installing {description} ({component})... [{idx + 1}/{total_components}]", "info")
                self.log("  (This may take several minutes - progress will be shown below)", "info")

                command = self.build_winetricks_command(component)
                # The fonts go in directly; winetricks only if that fails.
                success = (component in DIRECT_FONT_VERBS
                           and self.install_font_verb_directly(component, env))
                if not success:
                    success = self.run_command_streaming(
                        command,
                        env=env,
                        progress_callback=progress_callback,
                        stall_timeout=600,
                        activity_probe=self._prefix_activity,
                        hard_limit=2700,
                    )

                stalled = self._last_command_stalled
                if not success and not self.check_cancelled():
                    if stalled and component in self._stalled_components:
                        # Second stall of the same verb: another attempt would
                        # just burn another 20 minutes on the same deadlock.
                        self.log(
                            f"{description} stalled twice in a row — not retrying it.",
                            "error",
                        )
                        self.log(
                            "This is the known Wine 11+ new WoW64 hang: the 64-bit ngen.exe never returns.",
                            "info",
                        )
                        self.log(
                            "Close the installer, switch to the other Wine version (11.18 / 11.19), then try again.",
                            "warning",
                        )
                    else:
                        if stalled:
                            self._stalled_components.add(component)
                        self.log(f"{description} installation failed, retrying once...", "warning")
                        # A failed run can leave a half-finished installer behind;
                        # clear it out so the retry does not queue behind it.
                        self.stop_prefix_wine_processes(
                            env, reason="retrying after a failed/stalled run"
                        )
                        time.sleep(2)
                        success = self.run_command_streaming(
                            command,
                            env=env,
                            progress_callback=progress_callback,
                            stall_timeout=600,
                    activity_probe=self._prefix_activity,
                    hard_limit=2700,
                        )
                        if not success and self._last_command_stalled:
                            self._stalled_components.add(component)

                self.update_progress(base_progress + component_progress_range)

                component_key = component.split("=", 1)[0]
                if success:
                    self.log(f"✓ {description} installed", "success")
                    continue

                if self._check_winetricks_component(component_key, self.get_wine_path("wine"), env):
                    self.log(f"✓ {description} appears to already be installed", "success")
                    continue

                had_failures = True
                self.log(f"✗ {description} installation failed after retry. You may need to install it manually.", "error")

            if self.check_cancelled():
                return False

            self.ensure_vulkan_renderer(env)

            self.log("Setting Windows version to 11...", "info")
            self.stop_prefix_wine_processes(env, reason="setting Windows version")
            self.run_command([str(wine_cfg), "-v", "win11"], check=False, env=env)

            self.log("Applying Wine dark theme...", "info")
            theme_file = Path(self.directory) / "wine-dark-theme.reg"
            if self.download_file(
                "https://raw.githubusercontent.com/seapear/AffinityOnLinux/refs/heads/main/Auxiliary/Other/wine-dark-theme.reg",
                str(theme_file),
                "dark theme",
            ):
                regedit = self.get_wine_path("regedit")
                self.run_command([str(regedit), str(theme_file)], check=False, env=env)
                theme_file.unlink()
                self.log("Dark theme applied", "success")


            if not self.verify_required_wine_runtimes():
                self.update_progress_text("Missing required Wine runtimes")
                return False

            if had_failures:
                self.log("Winetricks dependencies completed with warnings. Check the log above for any manual follow-up.", "warning")
            else:
                self.log("\n✓ Winetricks dependencies installation completed!", "success")

            # Migrate prefixes created when `crypt32` was still installed native.
            self.repair_crypt32_override()

            self.update_progress(1.0)
            self.update_progress_text("Ready")
            return not had_failures
        except Exception as e:
            self.log(f"Error in winetricks dependencies installation: {str(e)}", "error")
            self.log("Please check the logs and try again.", "error")
            return False
        finally:
            if hasattr(self, "current_operation") and self.current_operation == "Installing Winetricks Dependencies":
                self.end_operation()


    def _seed_settings(self, settings_source, target_dir):
        """Copy the repository's stock Settings in without overwriting the user's.

        This step exists because a fresh prefix needs the seed files before
        Affinity v3 will save settings at all. But the same directory is where
        the user's own preferences live, and where RecentFiles.xml lives, so
        copying the whole stock tree over the top of it is data loss: every
        install or update resets the preferences and empties the recent
        documents list. It goes unnoticed for a while, because the list starts
        refilling as soon as documents are opened -- until someone looks for a
        file they had open last week.

        Filling in only what is missing serves both cases. A fresh prefix gets
        the complete set; a prefix that has been used is left exactly as it was.

        Returns (added, kept) as lists of paths relative to the source.
        """
        added, kept = [], []
        for src in sorted(settings_source.rglob("*")):
            rel = src.relative_to(settings_source)
            dest = target_dir / rel
            if src.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
                continue
            if dest.exists():
                kept.append(rel)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            added.append(rel)
        return added, kept

    def install_affinity_settings(self):
        """Install Affinity v3 (Unified) settings files to enable settings saving"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Fix Settings (Affinity v3 only)", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        self.log("Note: This fix applies only to Affinity v3 (Unified).", "info")

        # Check if Wine is set up
        wine_binary = self.get_wine_path("wine")
        if not wine_binary.exists():
            self.log(
                "Wine is not set up yet. Please setup Wine environment first.", "error"
            )
            QMessageBox.warning(
                self,
                "Wine Not Ready",
                "Wine setup must complete before installing Affinity v3 settings.\n"
                "Please setup Wine environment first.",
            )
            return

        # Start operation and wrapper thread
        self.start_operation("Install Affinity v3 Settings")
        threading.Thread(
            target=self._install_affinity_settings_entry, daemon=True
        ).start()


    def _wine_reg_key_exists(self, hive, key_path):
        """Check if a registry key exists by parsing the prefix's reg files (fast)."""
        reg_file = "system.reg" if hive == "HKLM" else "user.reg"
        reg_path = Path(self.directory) / reg_file
        if not reg_path.exists():
            return False
        target = "[" + key_path.replace("\\", "\\\\").lower() + "]"
        try:
            with open(reg_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("["):
                        end = line.find("]")
                        if end != -1 and line[: end + 1].lower() == target:
                            return True
        except Exception:
            pass
        return False

    def ensure_vulkan_renderer(self, env):
        """Set Wine's renderer to Vulkan again if the prefix has no renderer setting.

        Without the setting Wine draws with OpenGL, where Affinity's popups have
        come up black. The setting has been lost when Wine was stopped before
        writing the registry to disk. A renderer that was chosen (OpenGL) is
        kept. Returns True when the prefix has a renderer setting."""
        key = r"Software\Wine\Direct3D"
        # The registry files are read directly: stop Wine so they are current.
        self.stop_prefix_wine_processes(env, reason="checking the renderer setting")
        if self._read_wine_reg_value("HKCU", key, "renderer") is not None:
            return True
        self.log("Wine's renderer setting is missing; setting it to Vulkan again", "warning")
        self.run_command(
            [str(self.get_wine_path("wine")), "reg", "add", "HKCU\\" + key,
             "/v", "renderer", "/d", "vulkan", "/f"],
            check=False, env=env, timeout=120,
        )
        self.run_command([str(self.get_wine_path("wineserver")), "-w"],
                         check=False, env=env, timeout=60)
        if self._read_wine_reg_value("HKCU", key, "renderer") is None:
            self.log("Could not set Wine's renderer to Vulkan", "error")
            return False
        self.log("Wine's renderer is set to Vulkan", "success")
        return True

    def _read_wine_reg_value(self, hive, key_path, value_name):
        """Read a registry value from the prefix's reg files (system.reg/user.reg).

        Parsing the file is instant, unlike `wine reg query` which costs several
        seconds per call due to wineserver startup. Returns int for dword values,
        str for quoted strings, or None if not found.
        """
        reg_file = "system.reg" if hive == "HKLM" else "user.reg"
        reg_path = Path(self.directory) / reg_file
        if not reg_path.exists():
            return None
        try:
            target_section = key_path.replace("\\", "\\\\").lower()
            current_section = None
            with open(reg_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("["):
                        end = line.find("]")
                        current_section = (
                            line[1:end].lower() if end != -1 else None
                        )
                        continue
                    if current_section != target_section:
                        continue
                    m = re.match(r'^"([^"]*)"=(.*)$', line)
                    if not m or m.group(1).lower() != value_name.lower():
                        continue
                    raw = m.group(2).strip()
                    if raw.lower().startswith("dword:"):
                        try:
                            return int(raw[6:], 16)
                        except ValueError:
                            return None
                    if raw.startswith('"') and raw.endswith('"'):
                        return raw[1:-1]
                    return raw
        except Exception:
            return None
        return None

    def _check_winetricks_component(self, component, wine, env):
        """Check if a winetricks component is installed"""
        try:
            # Different checks for different components
            if component == "dotnet35sp1" or component == "dotnet35":
                # Check for .NET 3.5 in registry (dotnet35sp1 installs .NET 3.5 SP1)
                install = self._read_wine_reg_value(
                    "HKLM",
                    r"Software\Microsoft\NET Framework Setup\NDP\v3.5",
                    "Install",
                )
                if install == 1:
                    return True
            elif component == "dotnet48":
                return self.has_dotnet48_runtime()
            elif component == "corefonts":
                # Check if core fonts directory exists
                fonts_dir = Path(self.directory) / "drive_c" / "windows" / "Fonts"
                if fonts_dir.exists():
                    # Check for some common core fonts. Not tahoma.ttf: Tahoma is
                    # its own verb, and counting it here hid a missing corefonts.
                    core_fonts = ["arial.ttf", "times.ttf", "courier.ttf"]
                    for font in core_fonts:
                        if (fonts_dir / font).exists():
                            return True
            elif component == "tahoma":
                fonts_dir = Path(self.directory) / "drive_c" / "windows" / "Fonts"
                if (fonts_dir / "tahoma.ttf").exists():
                    return True
            elif component == "vcrun2022":
                # Check for Visual C++ 2022 redistributables
                vcrun_paths = [
                    Path(self.directory)
                    / "drive_c"
                    / "windows"
                    / "system32"
                    / "vcruntime140.dll",
                    Path(self.directory)
                    / "drive_c"
                    / "windows"
                    / "syswow64"
                    / "vcruntime140.dll",
                ]
                for vcrun_path in vcrun_paths:
                    if vcrun_path.exists():
                        return True
            elif component == "msxml3":
                # Check for MSXML3
                msxml3_path = (
                    Path(self.directory)
                    / "drive_c"
                    / "windows"
                    / "system32"
                    / "msxml3.dll"
                )
                if msxml3_path.exists():
                    return True
            elif component == "msxml6":
                # Check for MSXML6
                msxml6_path = (
                    Path(self.directory)
                    / "drive_c"
                    / "windows"
                    / "system32"
                    / "msxml6.dll"
                )
                if msxml6_path.exists():
                    return True
            # A component without a check of its own above -- Tahoma had none,
            # so it always read "Not installed" -- goes by the verbs winetricks
            # recorded in the prefix.
            else:
                return component in self._winetricks_logged_verbs()
        except Exception:
            pass

        return False

    def _winetricks_logged_verbs(self):
        """The verbs winetricks recorded as installed in this prefix."""
        try:
            text = (Path(self.directory) / "winetricks.log").read_text(errors="replace")
        except OSError:
            return set()
        return {line.strip() for line in text.splitlines() if line.strip()}

    def check_webview2_installed(self):
        """Check if WebView2 Runtime is already installed (fast check - file paths only)"""
        # Fast check: only check file paths, skip slow registry query
        webview2_paths = [
            Path(self.directory)
            / "drive_c"
            / "Program Files (x86)"
            / "Microsoft"
            / "EdgeWebView"
            / "Application",
            Path(self.directory)
            / "drive_c"
            / "Program Files"
            / "Microsoft"
            / "EdgeWebView"
            / "Application",
        ]

        for webview2_path in webview2_paths:
            if webview2_path.exists():
                # Check if msedgewebview2.exe exists
                msedgewebview2_exe = webview2_path / "msedgewebview2.exe"
                if msedgewebview2_exe.exists():
                    return True

        # If file check fails, do a registry check (only if file check failed)
        # Skip registry check to make it faster - file check is usually sufficient
        # Registry check can be slow and may hang, so we skip it for speed
        return False

        return False

    def get_webview2_install_env(self, base_env=None):
        """Build a consistent Wine environment for WebView2 installation and launch."""
        env = os.environ.copy() if base_env is None else base_env.copy()
        env["WINEPREFIX"] = self.directory

        local_wine = self.get_wine_path("wine")
        local_wineserver = self.get_wine_path("wineserver")
        if local_wine.exists():
            env["WINE"] = str(local_wine)
            env["WINELOADER"] = str(local_wine)
            env["PATH"] = f"{local_wine.parent}:{env.get('PATH', '')}"
            if local_wineserver.exists():
                env["WINESERVER"] = str(local_wineserver)
        return env

    def get_webview2_wine_tools(self):
        """Return Wine tools for WebView2, preferring the bundled installer Wine."""
        local_wine = self.get_wine_path("wine")
        local_winecfg = self.get_wine_path("winecfg")
        local_regedit = self.get_wine_path("regedit")
        local_wineserver = self.get_wine_path("wineserver")

        if local_wine.exists():
            return {
                "wine": str(local_wine),
                "winecfg": str(local_winecfg) if local_winecfg.exists() else "winecfg",
                "regedit": str(local_regedit) if local_regedit.exists() else "regedit",
                "wineserver": str(local_wineserver) if local_wineserver.exists() else "wineserver",
                "source": "bundled",
            }

        return {
            "wine": "wine",
            "winecfg": "winecfg",
            "regedit": "regedit",
            "wineserver": "wineserver",
            "source": "system",
        }

    def configure_webview2_runtime(self, env=None):
        """Apply the post-install WebView2 configuration used by Affinity v3."""
        env = self.get_webview2_install_env(env)
        tools = self.get_webview2_wine_tools()
        regedit = tools["regedit"]
        wine = tools["wine"]

        self.log("Ensuring Edge Update services are disabled...", "info")
        disable_edge_update_reg = Path(self.directory) / "disable-edge-update.reg"
        with open(disable_edge_update_reg, "w") as f:
            f.write("Windows Registry Editor Version 5.00\n\n")
            f.write("[HKEY_LOCAL_MACHINE\\System\\CurrentControlSet\\Services\\edgeupdate]\n")
            f.write("\"Start\"=dword:00000004\n\n")
            f.write("[HKEY_LOCAL_MACHINE\\System\\CurrentControlSet\\Services\\edgeupdatem]\n")
            f.write("\"Start\"=dword:00000004\n")

        self.run_command([str(regedit), str(disable_edge_update_reg)], check=False, env=env)
        disable_edge_update_reg.unlink()

        # The runtime installs as Windows 11, but msedgewebview2.exe runs as
        # Windows 7: as Windows 11 the WebView2 GPU process fails at startup
        # and the Affinity v3 Help window stays empty (Wine 10.10; on 11.19
        # with runtime 142 the GPU processes still die as Windows 11 and all
        # stay up as Windows 7).
        self.log("Setting msedgewebview2.exe to Windows 7 compatibility...", "info")
        self.run_command(
            [
                str(wine), "reg", "add",
                "HKEY_CURRENT_USER\\Software\\Wine\\AppDefaults\\msedgewebview2.exe",
                "/v", "Version",
                "/d", "win7",
                "/f",
            ],
            check=False,
            env=env,
            capture=True,
        )

        return True

    def ensure_webview2_runtime(self):
        """Install the WebView2 Runtime with Affinity v3, unless it is already there.

        Affinity v3's Help is a WebView2 page: without the runtime Help stays
        blank and Affinity logs "Couldn't find a compatible Webview2 Runtime".
        It used to come only from its own button, so every install made by
        One-Click Full Setup or the manager had a blank Help. Failing here is
        not an install failure: the button can still add it later."""
        if self.check_webview2_installed():
            self.configure_webview2_runtime()
            return True
        self.update_progress_text("Installing WebView2 for Affinity's Help...")
        try:
            if self._install_webview2_runtime_thread():
                return True
        except Exception as e:
            self.log(f"WebView2 Runtime was not installed: {e}", "warning")
        self.log(
            "Affinity's Help needs the WebView2 Runtime; add it later with "
            "'WebView2 Runtime (v3)'.",
            "warning",
        )
        return False

    def install_webview2_runtime(self):
        """Install Microsoft Edge WebView2 Runtime for Affinity v3 (Unified)"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Installing Microsoft Edge WebView2 Runtime (Affinity v3)", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        tools = self.get_webview2_wine_tools()
        if tools["source"] == "system" and not shutil.which("wine"):
            self.log("No Wine runtime is available for WebView2 installation.", "error")
            QMessageBox.warning(
                self,
                "Wine Not Installed",
                "Wine is required for WebView2 Runtime installation.\n\n"
                "Please install Wine using your distribution's package manager:\n"
                "  • Arch/Artix/CachyOS/EndeavourOS/XeroLinux: sudo pacman -S wine\n"
                "  • Fedora/Nobara: sudo dnf install wine\n"
                "  • PikaOS: sudo apt install wine",
            )
            return

        # Start operation and wrapper thread
        self.start_operation("Install WebView2 Runtime")
        threading.Thread(
            target=self._install_webview2_runtime_entry, daemon=True
        ).start()

    def _install_webview2_runtime_entry(self):
        """Wrapper to install WebView2 and end the operation when invoked from the button."""
        try:
            self._install_webview2_runtime_thread()
        finally:
            self.end_operation()

    def _install_webview2_runtime_thread(self):
        """Install Microsoft Edge WebView2 Runtime in background thread"""
        tools = self.get_webview2_wine_tools()
        if tools["source"] == "system" and not shutil.which("wine"):
            self.log("No Wine runtime is available for WebView2 installation.", "error")
            self.log("You can install Wine using your distribution's package manager.", "info")
            return False

        env = self.get_webview2_install_env()
        wine_cfg = tools["winecfg"]
        wine = tools["wine"]

        if tools["source"] == "bundled":
            self.log(f"Using bundled installer Wine for WebView2 installation (WINEPREFIX={self.directory})", "info")
        else:
            self.log(f"Using system Wine for WebView2 installation (WINEPREFIX={self.directory})", "info")
        # Check if WebView2 Runtime is already installed
        self.log("Checking if WebView2 Runtime is already installed...", "info")
        webview2_installed = False

        # Check for WebView2 installation directory
        webview2_paths = [
            Path(self.directory)
            / "drive_c"
            / "Program Files (x86)"
            / "Microsoft"
            / "EdgeWebView"
            / "Application",
            Path(self.directory)
            / "drive_c"
            / "Program Files"
            / "Microsoft"
            / "EdgeWebView"
            / "Application",
        ]

        for webview2_path in webview2_paths:
            if webview2_path.exists():
                # Check if msedgewebview2.exe exists
                msedgewebview2_exe = webview2_path / "msedgewebview2.exe"
                if msedgewebview2_exe.exists():
                    webview2_installed = True
                    self.log(f"WebView2 Runtime found at: {webview2_path}", "success")
                    break

        # Also check registry for WebView2 installation
        if not webview2_installed:
            try:
                success, stdout, _ = self.run_command(
                    [
                        str(wine),
                        "reg",
                        "query",
                        "HKEY_LOCAL_MACHINE\\SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
                    ],
                    check=False,
                    env=env,
                    capture=True,
                )
                if success:
                    webview2_installed = True
                    self.log("WebView2 Runtime found in registry", "success")
            except Exception:
                pass

        if webview2_installed:
            self.log(
                "WebView2 Runtime is already installed. Skipping installation.", "info"
            )
            self.log("Verifying configuration...", "info")
            self.configure_webview2_runtime(env)
            self.log("\n✓ WebView2 Runtime configuration verified!", "success")
            self.log("WebView2 Runtime is installed and configured correctly.", "info")
            return True

        # WebView2 not found, proceed with installation
        self.log("WebView2 Runtime not found. Proceeding with installation...", "info")

        try:
            # Step 1: Set Windows 11 compatibility mode (WebView2 requires Win10/11)
            self.log("Setting Windows 11 compatibility mode...", "info")
            self.stop_prefix_wine_processes(env, reason="setting Windows version")
            self.run_command([str(wine_cfg), "-v", "win11"], check=False, env=env)
            self.log("Windows 11 compatibility mode set", "success")

            # Step 2: Download Microsoft Edge WebView2 Runtime
            self.log("Downloading Microsoft Edge WebView2 Runtime...", "info")
            webview2_url = "https://github.com/ryzendew/AffinityOnLinux/releases/download/10.4-Wine-Affinity/MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
            webview2_file = (
                Path(self.directory) / "MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
            )

            if not self.download_file(
                webview2_url, str(webview2_file), "WebView2 Runtime"
            ):
                self.log("Failed to download WebView2 Runtime", "error")
                return False

            self.log("WebView2 Runtime downloaded", "success")

            # Step 3: Install WebView2 Runtime using system wine (like Affinity v3)
            self.log("Installing Microsoft Edge WebView2 Runtime...", "info")
            self.log("This may take a few minutes...", "info")
            if tools["source"] == "bundled":
                self.log("Using bundled installer Wine for WebView2 installation", "info")
            else:
                self.log("Using system Wine for WebView2 installation", "info")
            env["WINEDEBUG"] = "-all"

            success = self._run_installer_and_capture(webview2_file, env, label="WebView2 installer")
            if not success:
                self.log(
                    "WebView2 installer may have completed despite non-zero exit code",
                    "warning",
                )

            # Wait a moment for files to be written
            time.sleep(3)
            self.log("WebView2 Runtime installation completed", "success")

            self.configure_webview2_runtime(env)
            self.log("WebView2 Runtime configuration applied", "success")
            # Clean up installer file
            if webview2_file.exists():
                webview2_file.unlink()
                self.log("WebView2 installer file removed", "success")

            self.log(
                "\n✓ Microsoft Edge WebView2 Runtime installation completed!", "success"
            )
            self.log("WebView2 Runtime has been installed for Affinity v3.", "info")
            self.log("Help > View Help should now work in Affinity v3.", "info")
            return True

        except Exception as e:
            if not self.check_cancelled():
                self.log(f"Error installing WebView2 Runtime: {e}", "error")
            # Try to restore Windows 11 compatibility even if something failed
            try:
                self.stop_prefix_wine_processes(
                    env, reason="restoring Windows version"
                )
                self.run_command([str(wine_cfg), "-v", "win11"], check=False, env=env)
            except:
                pass
            return False

    def _install_affinity_settings_entry(self):
        """Wrapper to install Affinity settings and end the operation when invoked from the button."""
        try:
            self._install_affinity_settings_thread()
        finally:
            self.end_operation()

    def _install_affinity_settings_thread(self):
        """Install Affinity v3 (Unified) settings in background thread - downloads repo and copies Settings"""
        try:
            # Determine Windows username
            # Wine typically uses "Public" as the default username, but check for existing users
            users_dir = Path(self.directory) / "drive_c" / "users"
            username = "Public"  # Default Wine username

            # Check if users directory exists and has other users
            if users_dir.exists():
                # Look for existing user directories (excluding Public, Default, etc.)
                existing_users = [
                    d.name
                    for d in users_dir.iterdir()
                    if d.is_dir()
                    and d.name not in ["Public", "Default", "All Users", "Default User"]
                ]
                if existing_users:
                    # Use the first existing user, or fall back to Public
                    username = existing_users[0]
                    self.log(f"Using existing Windows user: {username}", "info")
                else:
                    self.log(f"Using default Windows user: {username}", "info")
            else:
                self.log(f"Creating users directory structure for: {username}", "info")
                users_dir.mkdir(parents=True, exist_ok=True)

            # Create temp directory for cloning/downloading
            temp_dir = Path(self.directory) / ".temp_settings"
            if temp_dir.exists():
                self.log("Cleaning up existing temp directory...", "info")
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    self.log(
                        f"Warning: Could not remove existing temp dir: {e}", "warning"
                    )
            temp_dir.mkdir(exist_ok=True)

            # Download the repository as a zip file
            self.update_progress_text("Downloading Settings from repository...")
            self.update_progress(0.1)
            self.log("Downloading Settings from GitHub repository...", "info")
            repo_zip = temp_dir / "AffinityOnLinux.zip"
            repo_url = (
                "https://github.com/seapear/AffinityOnLinux/archive/refs/heads/main.zip"
            )

            if not self.download_file(repo_url, str(repo_zip), "Settings repository"):
                self.log("Failed to download Settings repository", "error")
                self.log(f"  URL: {repo_url}", "error")
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
                return

            # Verify the zip file was downloaded
            if not repo_zip.exists() or repo_zip.stat().st_size == 0:
                self.log("Downloaded zip file is missing or empty", "error")
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
                return

            self.log(
                f"Downloaded zip file size: {repo_zip.stat().st_size / 1024 / 1024:.2f} MB",
                "info",
            )

            # Extract the zip file
            self.update_progress_text("Extracting Settings repository...")
            self.update_progress(0.3)
            self.log("Extracting Settings repository...", "info")
            try:
                if self.check_command("7z"):
                    success, stdout, stderr = self.run_command(
                        ["7z", "x", str(repo_zip), f"-o{temp_dir}", "-y"]
                    )
                    if not success:
                        self.log(f"7z extraction failed: {stderr}", "error")
                        raise Exception("7z extraction failed")
                    self.log("Extraction completed with 7z", "success")
                elif self.check_command("unzip"):
                    with zipfile.ZipFile(repo_zip, "r") as zip_ref:
                        zip_ref.extractall(temp_dir)
                    self.log("Extraction completed with unzip", "success")
                else:
                    self.log("Neither 7z nor unzip available for extraction", "error")
                    self.log(
                        "Please install 7z or unzip to extract the repository", "error"
                    )
                    try:
                        shutil.rmtree(temp_dir)
                    except Exception:
                        pass
                    return

                # Find the extracted directory (usually AffinityOnLinux-main)
                extracted_dirs = list(temp_dir.glob("AffinityOnLinux-*"))
                self.log(
                    f"Found {len(extracted_dirs)} extracted director{'y' if len(extracted_dirs) == 1 else 'ies'}",
                    "info",
                )

                extracted_dir = extracted_dirs[0] if extracted_dirs else None
                if not extracted_dir:
                    self.log("Could not find extracted repository directory", "error")
                    self.log(
                        f"Contents of temp_dir: {[d.name for d in temp_dir.iterdir()]}",
                        "error",
                    )
                    try:
                        shutil.rmtree(temp_dir)
                    except Exception:
                        pass
                    return

                self.log(f"Using extracted directory: {extracted_dir.name}", "info")

                # Check if Auxiliary directory exists
                auxiliary_dir = extracted_dir / "Auxiliary"
                if not auxiliary_dir.exists():
                    self.log("Auxiliary directory not found in repository", "error")
                    self.log(
                        f"Contents of extracted directory: {[d.name for d in extracted_dir.iterdir()]}",
                        "error",
                    )
                    try:
                        shutil.rmtree(temp_dir)
                    except Exception:
                        pass
                    return

                settings_dir = auxiliary_dir / "Settings"
                if not settings_dir.exists():
                    self.log("Settings directory not found in Auxiliary", "error")
                    self.log(
                        f"Contents of Auxiliary: {[d.name for d in auxiliary_dir.iterdir()]}",
                        "error",
                    )
                    try:
                        shutil.rmtree(temp_dir)
                    except Exception:
                        pass
                    return

                # List what's in the Settings directory
                settings_contents = [
                    d.name for d in settings_dir.iterdir() if d.is_dir()
                ]
                self.log(f"Found Settings folders: {settings_contents}", "info")

                # Source Settings directory path - For Affinity v3 (Unified), use 3.0
                # $APP would be "Affinity" and version is 3.0
                # So the source should be: Auxiliary/Settings/Affinity/3.0/Settings
                self.update_progress_text("Locating Settings files...")
                self.update_progress(0.5)
                settings_source_dirs = [
                    settings_dir
                    / "Affinity"
                    / "3.0"
                    / "Settings",  # Affinity v3 uses 3.0
                    settings_dir / "Affinity" / "Settings",
                    settings_dir / "Unified" / "3.0" / "Settings",
                    settings_dir / "Unified" / "Settings",
                ]

                settings_source = None
                for source_dir in settings_source_dirs:
                    if source_dir.exists():
                        files = list(source_dir.iterdir())
                        if files:
                            settings_source = source_dir
                            self.log(
                                f"Found settings at: {source_dir.relative_to(extracted_dir)}",
                                "success",
                            )
                            self.log(
                                f"  Contains {len(files)} file(s)/folder(s)", "info"
                            )
                            break

                if not settings_source:
                    self.log("Settings directory not found in repository", "error")
                    self.log("Tried paths:", "error")
                    for path in settings_source_dirs:
                        self.log(
                            f"  - {path.relative_to(extracted_dir)}: {'exists' if path.exists() else 'not found'}",
                            "error",
                        )

                    # List what's actually in Settings/Affinity if it exists
                    affinity_settings = settings_dir / "Affinity"
                    if affinity_settings.exists():
                        self.log(
                            f"Contents of Settings/Affinity: {[d.name for d in affinity_settings.iterdir()]}",
                            "info",
                        )

                    try:
                        shutil.rmtree(temp_dir)
                    except Exception:
                        pass
                    return

                # Target directory in Wine prefix
                # Based on Settings.md: mv $APP/3.0/Settings drive_c/users/$USERNAME/AppData/Roaming/Affinity/
                # For Affinity v3, this means: Affinity/3.0/Settings -> AppData/Roaming/Affinity/Affinity/3.0/Settings
                affinity_appdata = (
                    users_dir / username / "AppData" / "Roaming" / "Affinity"
                )

                # Check what version folder Affinity v3 actually uses by looking at existing structure
                affinity_dir = affinity_appdata / "Affinity"
                version_folder = None
                if affinity_dir.exists():
                    existing_versions = [
                        d.name for d in affinity_dir.iterdir() if d.is_dir()
                    ]
                    if existing_versions:
                        # Prefer 3.0 for Affinity v3
                        if "3.0" in existing_versions:
                            version_folder = "3.0"
                        elif "2.0" in existing_versions:
                            version_folder = "2.0"
                        else:
                            # Use the first one found (sorted)
                            version_folder = sorted(existing_versions)[0]
                        self.log(
                            f"Found existing Affinity version folder: {version_folder}",
                            "info",
                        )

                # If no existing version folder, use 3.0 for Affinity v3
                if not version_folder:
                    # Try to detect from source path
                    source_parts = settings_source.parts
                    if "3.0" in source_parts:
                        version_folder = "3.0"
                    elif "2.0" in source_parts:
                        version_folder = "2.0"
                    else:
                        version_folder = "3.0"  # Default to 3.0 for Affinity v3
                    self.log(
                        f"Using version folder: {version_folder} (Affinity v3 uses 3.0)",
                        "info",
                    )

                # Target path: AppData/Roaming/Affinity/Affinity/3.0/Settings (for v3)
                target_dir = affinity_appdata / "Affinity" / version_folder / "Settings"

                # Fill in only the settings files that are missing.
                #
                # The stock set is a seed for a fresh prefix. On a prefix that has
                # been used this directory holds the user's own preferences and
                # RecentFiles.xml, and replacing it wipes both. See _seed_settings.
                self.update_progress_text("Installing Settings files...")
                self.update_progress(0.7)
                target_dir.mkdir(parents=True, exist_ok=True)
                self.log("Installing stock settings, keeping any you already have...", "info")
                self.log(f"  From: {settings_source}", "info")
                self.log(f"  To: {target_dir}", "info")

                added, kept = self._seed_settings(settings_source, target_dir)
                self.update_progress(0.9)

                if kept:
                    self.log(
                        f"Kept {len(kept)} existing settings file(s) untouched "
                        f"(your preferences and RecentFiles.xml are among them)",
                        "success",
                    )
                self.log(
                    f"Added {len(added)} missing settings file(s) to: {target_dir}",
                    "success",
                )
                for rel in added[:5]:
                    self.log(f"  + {rel}", "info")

                # Permissions on the files we added, and nothing else. Walking
                # target_dir chmod'd every settings file in the prefix --
                # including the ones _seed_settings had just deliberately left
                # alone, three lines after logging that they were untouched.
                try:
                    os.chmod(target_dir, 0o755)
                    for rel in added:
                        path = target_dir / rel
                        os.chmod(path, 0o755 if path.is_dir() else 0o644)
                    self.log(
                        f"Permissions set on the {len(added)} file(s) added", "success"
                    )
                except Exception as e:
                    self.log(f"Note: Could not set permissions: {e}", "warning")

                # Clean up temp files
                try:
                    shutil.rmtree(temp_dir)
                    self.log("Temp files cleaned up", "info")
                except Exception as e:
                    self.log(f"Note: Could not clean up temp files: {e}", "warning")

                self.update_progress(1.0)
                self.update_progress_text("Settings installation complete!")
                self.log("\n✓ Affinity v3 settings installation completed!", "success")
                self.log(
                    "Settings files have been installed for Affinity v3 (Unified).",
                    "info",
                )

            except Exception as e:
                import traceback

                self.log(f"Error installing settings: {e}", "error")
                self.log(f"Traceback: {traceback.format_exc()}", "error")
            try:
                shutil.rmtree(temp_dir)
                repo_zip.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception as e:
            import traceback

            self.log(f"Error installing settings: {e}", "error")
            self.log(f"Traceback: {traceback.format_exc()}", "error")
            # Clean up on error
            try:
                shutil.rmtree(temp_dir)
                repo_zip.unlink(missing_ok=True)
            except:
                pass

    def install_from_file(self):
        """Install from file manager - custom .exe file"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Custom Installer from File Manager", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Check if Wine is set up
        wine_binary = self.get_wine_path("wine")
        if not wine_binary.exists():
            self.log(
                "Wine is not set up yet. Please wait for Wine setup to complete.",
                "error",
            )
            QMessageBox.warning(
                self,
                "Wine Not Ready",
                "Wine setup must complete before installing applications.\n"
                "Please wait for the initialization to finish.",
            )
            return

        # Open file dialog to select .exe
        self.log("Please select the installer .exe file...", "info")
        installer_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Installer (.exe)",
            "",
            "Executable files (*.exe);;All files (*.*)",
        )

        if not installer_path:
            self.log("Installation cancelled.", "warning")
            return

        # Detect app name from filename - check multiple patterns
        filename_lower = Path(installer_path).name.lower()
        filename_no_spaces = (
            filename_lower.replace(" ", "").replace("-", "").replace("_", "")
        )
        app_name = None

        # Check various patterns that might be in Affinity installer filenames
        if "photo" in filename_lower or "photo" in filename_no_spaces:
            app_name = "Photo"
            self.log(
                f"Detected: Affinity Photo (from filename: {Path(installer_path).name})",
                "info",
            )
        elif "designer" in filename_lower or "designer" in filename_no_spaces:
            app_name = "Designer"
            self.log(
                f"Detected: Affinity Designer (from filename: {Path(installer_path).name})",
                "info",
            )
        elif "publisher" in filename_lower or "publisher" in filename_no_spaces:
            app_name = "Publisher"
            self.log(
                f"Detected: Affinity Publisher (from filename: {Path(installer_path).name})",
                "info",
            )
        elif (
            ("affinity" in filename_lower or "affinity" in filename_no_spaces)
            and ("x64" in filename_lower or "x64" in filename_no_spaces)
            and "photo" not in filename_lower
            and "designer" not in filename_lower
            and "publisher" not in filename_lower
        ):
            app_name = "Add"
            self.log(
                f"Detected: Affinity (Unified) v3 (from filename: {Path(installer_path).name})",
                "info",
            )
        else:
            self.log(
                f"Could not detect Affinity app from filename: {Path(installer_path).name}",
                "warning",
            )
            self.log(
                "Desktop entry will not be created automatically for non-Affinity apps.",
                "info",
            )

        if app_name:
            self.log(f"Will automatically create desktop entry for {app_name}", "info")

        # Start operation and installation
        self.start_operation("Custom Installation")
        threading.Thread(
            target=self._run_custom_installation_entry,
            args=(installer_path, app_name),
            daemon=True,
        ).start()

    def _run_custom_installation_entry(self, installer_path, app_name):
        """Wrapper: run custom installation and always end operation."""
        try:
            self.run_custom_installation(installer_path, app_name)
        finally:
            self.end_operation()

    def run_custom_installation(self, installer_path, app_name):
        """Run custom installation process"""
        try:
            self.log(f"Selected installer: {installer_path}", "success")

            if not self.verify_required_wine_runtimes():
                self.show_message(
                    "Wine Runtime Missing",
                    ".NET Framework 4.8 is missing in the Wine prefix. Run 'Setup Wine Environment' or 'Install Winetricks Dependencies' again before launching the installer.",
                    "error"
                )
                return
            # Copy installer with sanitized filename (remove spaces)
            original_filename = Path(installer_path).name
            sanitized_filename = self.sanitize_filename(original_filename)
            installer_file = Path(self.directory) / sanitized_filename
            shutil.copy2(installer_path, installer_file)
            self.log(
                f"Installer {original_filename} copied to Wine prefix: {installer_file} (WINEPREFIX={self.directory})",
                "success",
            )

            # Set Windows version
            # Use regular Wine for all installations (wine-tkg is only for winetricks)
            wine_cfg = self.get_wine_path("winecfg")
            wine = self.get_wine_path("wine")

            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory
            self.stop_prefix_wine_processes(
                env, reason="launching the Affinity installer"
            )
            self.run_command([str(wine_cfg), "-v", "win11"], check=False, env=env)

            # Run installer
            env["WINEDEBUG"] = "-all"
            self.log("Launching installer with custom Wine...", "info")
            self.log("Follow the installation wizard in the window that opens.", "info")
            self.log("Click 'No' if you encounter any errors.", "warning")

            # Run installer and wait until it finishes, capturing logs (with fallback)
            success = self._run_installer_and_capture(
                installer_file, env, label="installer"
            )
            if not success and not self.check_cancelled():
                self.log("Installer process exited with a non-zero status", "warning")
            else:
                self.log("Installer succes.")
            # Clean up installer
            # if installer_file.exists():
            #     installer_file.unlink()
            # self.log("Installer file removed", "success")

            if app_name == "Add" and not self.affinity_v3_exe_path().exists():
                if self.check_cancelled():
                    return
                self.log("The Affinity setup finished without installing Affinity", "warning")
                installed, reason = self.install_affinity_v3_from_msi(installer_file, env)
                if not installed:
                    if not self.cancel_event.is_set():
                        self.show_affinity_not_installed(reason, declined=reason == self.MSI_DECLINED)
                    return

            # Restore WinMetadata (only needed for legacy Wine 9.14 and 10.10, not 11.18/11.19)
            wine_version = self.get_current_wine_version()
            if wine_version in ["9.14", "10.10"]:
                self.restore_winmetadata()
            else:
                self.log(
                    "Skipping WinMetadata restore for Wine 11.18/11.19 (not needed)", "info"
                )

            if app_name == "Add" and self.affinity_v3_exe_path().exists():
                self.install_windowsruntime_facades()
                self.create_affinity_url_handler()
                self.precompile_affinity()
                self.ensure_webview2_runtime()

            # Set up wintypes.dll and Wine overrides for Affinity apps (v2 and v3) - only for legacy Wine (< 11.18)
            if app_name in ["Photo", "Designer", "Publisher", "Add"]:
                wine_version = self.get_current_wine_version()
                if wine_version in ["9.14", "10.10"]:
                    self.log("Setting up wintypes.dll and Wine overrides...", "info")
                    # Set up DLL override for wintypes.dll
                    self.setup_wintypes_dll_override()
                    # Copy wintypes.dll for the installed app
                    self.setup_wintypes_dll(app_name)
                else:
                    self.log(
                        "Skipping wintypes.dll setup for Wine 11.18/11.19 (not needed)",
                        "info",
                    )

            # If it's an Affinity app, automatically create desktop entry and configure OpenCL
            if app_name in ["Photo", "Designer", "Publisher"]:
                self.log(f"Detected Affinity app: {app_name}, configuring...", "info")

                # Wait a bit more to ensure installation is fully complete
                time.sleep(2)

                # Configure OpenCL for Affinity apps (if enabled)
                if self.is_opencl_enabled():
                    self.configure_opencl(app_name)

                # Verify app path exists before creating desktop entry
                app_names = {
                    "Photo": ("Photo", "Photo.exe", "Photo 2"),
                    "Designer": ("Designer", "Designer.exe", "Designer 2"),
                    "Publisher": ("Publisher", "Publisher.exe", "Publisher 2"),
                }
                name, exe, dir_name = app_names.get(app_name, ("", "", ""))
                app_path = (
                    Path(self.directory)
                    / "drive_c"
                    / "Program Files"
                    / "Affinity"
                    / dir_name
                    / exe
                )

                if app_path.exists():
                    self.log(f"Found application at: {app_path}", "success")
                    self.precompile_affinity(app_path)
                    # Automatically create desktop entry
                    # Call directly - create_desktop_entry uses signals so it's thread-safe
                    try:
                        self.create_desktop_entry(app_name)
                        self.log("Desktop entry created successfully", "success")
                    except Exception as e:
                        self.log(f"Error creating desktop entry: {e}", "error")
                else:
                    self.log(
                        f"Warning: Application not found at expected path: {app_path}",
                        "warning",
                    )
                    self.log(
                        "Desktop entry will not be created automatically.", "warning"
                    )

                display_name = {
                    "Add": "Affinity (Unified)",
                    "Photo": "Affinity Photo",
                    "Designer": "Affinity Designer",
                    "Publisher": "Affinity Publisher",
                }.get(app_name, app_name)

                self.log(f"\n✓ {display_name} installation completed!", "success")
                how = self.launch_instructions()
                self.log(how, "info")

                self.show_message(
                    "Installation Complete",
                    f"{display_name} has been successfully installed!\n\n{how}",
                    "info",
                )
                self.offer_after_install()
            else:
                # For non-Affinity apps, just complete without desktop entry
                display_name = app_name if app_name else "Application"
                self.log(f"\n✓ {display_name} installation completed!", "success")

                # Run AffinityPluginLoader + WineFix automatically after Affinity (Unified) installs
                if app_name == "Add":
                    install_dir = (
                        Path(self.directory)
                        / "drive_c"
                        / "Program Files"
                        / "Affinity"
                        / "Affinity"
                    )
                    if install_dir.exists():
                        self.log(
                            "\nRunning AffinityPluginLoader + WineFix install...",
                            "info",
                        )
                        self._install_affinity_plugin_loader_thread(standalone=False)
                    else:
                        self.log(
                            "\n⚠ Affinity directory not found — skipping AffinityPluginLoader install.",
                            "warning",
                        )

                self.show_message(
                    "Installation Complete",
                    f"{display_name} has been successfully installed!\n\n"
                    "You may need to create a desktop entry manually if needed.",
                    "info",
                )
        except Exception as e:
            self.log(f"Installation error: {e}", "error")
            self.show_message("Installation Error", f"An error occurred:\n{e}", "error")

    def create_custom_desktop_entry(self, installer_path, app_name):
        """Create desktop entry for custom installed app"""
        reply = QMessageBox.question(
            self,
            "Create Desktop Entry",
            f"Would you like to create a desktop entry for '{app_name}'?\n\n"
            "You'll need to provide the executable path.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Ask for executable path
        exe_path, ok = QInputDialog.getText(
            self,
            "Executable Path",
            f"Enter the full path to the {app_name} executable:\n\n"
            "Example: C:\\Program Files\\MyApp\\MyApp.exe",
        )

        if not ok or not exe_path:
            self.log("Desktop entry creation cancelled.", "warning")
            return

        # Ask for icon path (optional)
        icon_path, ok = QInputDialog.getText(
            self,
            "Icon Path (Optional)",
            "Enter the path to an icon file (optional):\n\n"
            "Leave blank to use default icon.",
        )

        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)

        desktop_file = desktop_dir / f"{app_name.replace(' ', '')}.desktop"

        wine = self.get_wine_path("wine")

        # Normalize all paths to strings to avoid double slashes
        wine_str = str(wine)
        directory_str = str(self.directory).rstrip(
            "/"
        )  # Remove trailing slash if present

        # Normalize path: convert Windows backslashes to forward slashes, remove double slashes
        exe_path_normalized = exe_path.replace("\\", "/").replace("//", "/")
        # If it's a Windows path starting with C:, convert to Linux path
        if exe_path_normalized.startswith("C:/"):
            exe_path_normalized = directory_str + "/drive_c" + exe_path_normalized[2:]

        desktop_env_parts = self.get_desktop_launch_env_parts()
        launch_prefix = self.get_gpu_launch_prefix()

        with open(desktop_file, "w") as f:
            f.write("[Desktop Entry]\n")
            f.write(f"Name={app_name}\n")
            f.write(f"Comment={app_name} installed via Affinity Linux Installer\n")
            if icon_path:
                icon_path_str = str(icon_path).rstrip("/")
                f.write(f"Icon={icon_path_str}\n")
            f.write(f"Path={directory_str}\n")
            # Use Linux path format with proper quoting for spaces
            # Include GPU environment variables if configured
            exec_parts = ["Exec="]
            if launch_prefix:
                exec_parts.append(" ".join(shlex.quote(part) for part in launch_prefix))
            exec_parts.append(f"env WINEPREFIX={directory_str}")
            exec_parts.extend(desktop_env_parts)
            exec_parts.append(wine_str)
            exec_parts.append(f'"{exe_path_normalized}"')
            f.write(" ".join(exec_parts) + "\n")
            f.write("Terminal=false\n")
            f.write("Type=Application\n")
            f.write("Categories=Application;\n")
            f.write("StartupNotify=true\n")

        self.log(f"Desktop entry created: {desktop_file}", "success")

    def update_application(self, app_name):
        """Update Affinity application - simple installer that assumes everything is set up"""
        app_names = {
            "Add": "Affinity (Unified)",
            "Photo": "Affinity Photo",
            "Designer": "Affinity Designer",
            "Publisher": "Affinity Publisher",
        }

        display_name = app_names.get(app_name, app_name)

        self.log(
            f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log(f"Update {display_name}", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Check if Wine is set up
        wine = self.get_wine_path("wine")
        if not wine.exists():
            self.log(
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            self.show_message(
                "Wine Not Found",
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            return

        # Ask for installer file
        self.log(f"Please select the {display_name} installer (.exe)...", "info")

        installer_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {display_name} Installer",
            "",
            "Executable files (*.exe);;All files (*.*)",
        )

        if not installer_path:
            self.log("Update cancelled.", "warning")
            return

        # Start operation and update in thread
        self.start_operation(f"Update {display_name}")
        threading.Thread(
            target=self._run_update_entry,
            args=(display_name, installer_path),
            daemon=True,
        ).start()

    def _run_update_entry(self, display_name, installer_path):
        """Wrapper: run update and always end operation."""
        try:
            self.run_update(display_name, installer_path)
        finally:
            self.end_operation()

    def run_update(self, display_name, installer_path):
        """Run the update process - simple installer without desktop entries or deps"""
        try:
            self.update_progress_text("Preparing update...")
            self.update_progress(0.0)
            self.log(f"Selected installer: {installer_path}", "success")

            if not self.verify_required_wine_runtimes():
                self.show_message(
                    "Wine Runtime Missing",
                    ".NET Framework 4.8 is missing in the Wine prefix. Run 'Setup Wine Environment' or 'Install Winetricks Dependencies' again before launching the updater.",
                    "error"
                )
                return
            # Copy installer to Wine prefix with sanitized filename (remove spaces)
            self.update_progress_text("Copying installer...")
            self.update_progress(0.2)
            original_filename = Path(installer_path).name
            sanitized_filename = self.sanitize_filename(original_filename)
            installer_file = Path(self.directory) / sanitized_filename
            shutil.copy2(installer_path, installer_file)
            self.log(
                f"Installer copied to Wine prefix: {installer_file} (WINEPREFIX={self.directory})",
                "success",
            )

            # Set up environment
            self.update_progress_text("Configuring Wine...")
            self.update_progress(0.3)
            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory

            # Use regular Wine for all installations (wine-tkg is only for winetricks)
            wine_cfg = self.get_wine_path("winecfg")
            self.stop_prefix_wine_processes(
                env, reason="running the updater"
            )
            self.run_command([str(wine_cfg), "-v", "win11"], check=False, env=env)

            env["WINEDEBUG"] = "-all"

            # Run installer with custom Wine
            self.update_progress_text("Running updater...")
            self.update_progress(0.4)
            # Wine will be determined by _run_installer_and_capture based on installer type
            self.log("Launching installer...", "info")
            self.log("Follow the installation wizard in the window that opens.", "info")
            self.log(
                "This will update the application without creating desktop entries.",
                "info",
            )

            # Run updater and wait, capturing logs (with fallback)
            success = self._run_installer_and_capture(
                installer_file, env, label="updater"
            )
            if not success and not self.check_cancelled():
                self.log("Updater process exited with a non-zero status", "warning")

            # Clean up installer
            if installer_file.exists():
                installer_file.unlink()
                self.log("Installer file removed", "success")

            # Remove Wine desktop entries created by the installer
            desktop_dir = Path.home() / ".local" / "share" / "applications"
            wine_desktop_dir = desktop_dir / "wine" / "Programs"

            # Ensure display_name is a string
            if not isinstance(display_name, str):
                display_name = str(display_name) if display_name is not None else ""

            # Map display names to possible Wine desktop entry names
            wine_entry_names = []
            if display_name and (
                "Suite" in display_name or display_name == "Affinity Suite"
            ):
                wine_entry_names = ["Affinity.desktop"]
            elif display_name and "Photo" in display_name:
                wine_entry_names = [
                    "Affinity Photo 2.desktop",
                    "Affinity Photo.desktop",
                ]
            elif display_name and "Designer" in display_name:
                wine_entry_names = [
                    "Affinity Designer 2.desktop",
                    "Affinity Designer.desktop",
                ]
            elif display_name and "Publisher" in display_name:
                wine_entry_names = [
                    "Affinity Publisher 2.desktop",
                    "Affinity Publisher.desktop",
                ]

            removed_count = 0
            for entry_name in wine_entry_names:
                wine_entry = wine_desktop_dir / entry_name
                if wine_entry.exists():
                    try:
                        wine_entry.unlink()
                        removed_count += 1
                        self.log(f"Removed Wine desktop entry: {entry_name}", "info")
                    except Exception as e:
                        self.log(f"Could not remove {entry_name}: {e}", "error")

            # Also check for generic Affinity.desktop if not already checked
            if display_name and "Unified" not in display_name:
                generic_entry = wine_desktop_dir / "Affinity.desktop"
                if generic_entry.exists():
                    try:
                        generic_entry.unlink()
                        self.log("Removed Wine desktop entry: Affinity.desktop", "info")
                    except Exception as e:
                        self.log(f"Could not remove Affinity.desktop: {e}", "error")

            if removed_count > 0:
                self.log(
                    f"Cleaned up {removed_count} Wine desktop entr{'y' if removed_count == 1 else 'ies'}",
                    "success",
                )

            # Reinstall WinMetadata to avoid corruption
            self.log(
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            self.log("Reinstalling WinMetadata to prevent corruption...", "info")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )

            self.refresh_winmetadata(context="update")

            # For Affinity v3 (Unified), reinstall settings files
            if display_name and (
                "Unified" in display_name or display_name == "Affinity (Unified)"
            ):
                # Reinstall settings files
                self.log(
                    "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                self.log("Reinstalling Affinity v3 settings files...", "info")
                self.log(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                )
                self._install_affinity_settings_thread()

                # Patch the DLL to fix settings saving (this is the last step)
                self.update_progress_text("Patching DLL for settings fix...")
                self.update_progress(0.95)
                patch_success = self.patch_affinity_dll(display_name)
                if patch_success:
                    self.log("Settings fix patch applied successfully", "success")
                else:
                    self.log(
                        "Settings fix patch was skipped or failed (check log for details)",
                        "warning",
                    )

                if self.affinity_v3_exe_path().exists():
                    self.install_windowsruntime_facades()
                    self.create_affinity_url_handler()
                    # the update replaced the assemblies the old native images were made from
                    self.precompile_affinity()

            self.update_progress(1.0)
            self.update_progress_text("Update complete!")
            self.log(f"\n✓ {display_name} update completed!", "success")
            self.log(
                "The application has been updated. Use your existing desktop entry to launch it.",
                "info",
            )

            # Refresh installation status to update button states
            self.refresh_status_signal.emit()

            message_text = f"{display_name} has been successfully updated!\n\n"
            message_text += "WinMetadata has been reinstalled to prevent corruption.\n"
            if display_name and (
                "Unified" in display_name or display_name == "Affinity (Unified)"
            ):
                message_text += "Affinity v3 settings have been reinstalled.\n"
                message_text += "Settings fix patch has been applied (settings should now save properly).\n"
            message_text += "Use your existing desktop entry to launch the application."

            self.show_message("Update Complete", message_text, "info")
        except Exception as e:
            self.log(f"Update error: {e}", "error")
            self.show_message("Update Error", f"An error occurred:\n{e}", "error")

    def _run_installation_entry(self, app_name, installer_path):
        """Wrapper: run installation and always end operation."""
        try:
            self.run_installation(app_name, installer_path)
        finally:
            self.end_operation()

    MSI_DECLINED = "You chose not to install Affinity from its MSI package."
    AFFINITY_KNOWN_ISSUES_URL = (
        "https://github.com/ryzendew/Linux-Affinity-Installer/blob/main/docs/Known-issues.md"
        "#affinity-installer-setupuiexe-crashes"
    )

    def install_affinity_v3_from_msi(self, installer_file, env):
        """Install Affinity v3 from the MSI package embedded in its setup executable.

        The WPF setup window in Affinity-x64.exe (SetupUI.exe) crashes on some Wine
        builds before it installs anything, such as the Wine 10.0 that Ubuntu 26.04
        packages. That window installs the same MSI package, so it is installed here with
        msiexec and the prefix's own Wine.

        Returns (installed, reason), where reason explains a failure to the user.
        """
        for stale in Path(self.directory).glob(".affinity-msi-*"):
            shutil.rmtree(stale, ignore_errors=True)
        if not self.check_command("7z"):
            self.log("7z not found, cannot extract the Affinity MSI package", "error")
            return False, (
                "Installing Affinity from its MSI package needs 7z. Install 7-Zip and run the "
                "installation again."
            )

        reply = self.show_question_dialog(
            "Install Affinity from its MSI package?",
            "The Affinity setup finished, but Affinity.exe is not in "
            "C:\\Program Files\\Affinity\\Affinity. The setup window crashes on some Wine "
            "builds, such as the Wine 10.0 in Ubuntu 26.04.\n\n"
            "The setup file contains the MSI package that the setup window installs. This "
            "installer can install it into the default folder. It needs about 700 MB of "
            "temporary space in the prefix.\n\n"
            "Install Affinity this way? If you closed the setup yourself or chose another "
            "folder, choose No.",
            ["Yes", "No"],
            default_button="No",
        )
        if reply != "Yes":
            if self.cancel_event.is_set():
                return False, "The installation was cancelled."
            self.log("MSI installation declined", "info")
            return False, self.MSI_DECLINED

        # The prefix is on disk; /tmp may be RAM-backed and the MSI is about 640 MB.
        with tempfile.TemporaryDirectory(prefix=".affinity-msi-", dir=self.directory) as temp_dir:
            self.update_progress_text("Extracting the Affinity MSI package...")
            # 7z exits with 1 on warnings, so the extracted files decide success.
            _, stdout, stderr = self.run_command(
                ["7z", "x", "-t#", "-y", f"-o{temp_dir}", str(installer_file)], check=False
            )
            if self.cancel_event.is_set():
                return False, "The installation was cancelled."
            msi_files = sorted(
                Path(temp_dir).glob("*.msi"), key=lambda path: path.stat().st_size, reverse=True
            )
            for msi in msi_files:
                self.log(f"  Found {msi.name} ({msi.stat().st_size // (1024 * 1024)} MB)", "info")
            if not msi_files:
                self.log(f"7z could not extract an MSI package from {installer_file.name}: {(stdout + stderr).strip()}", "error")
                return False, (
                    f"7z could not extract the MSI package from {installer_file.name}. "
                    "Check the free disk space. Details are in the log."
                )

            # The setup ran with the system Wine; wait for its wineserver to exit before
            # the prefix's own Wine uses the same prefix.
            try:
                subprocess.run(["wineserver", "-w"], env=env, timeout=60, check=False)
            except subprocess.TimeoutExpired:
                self.log("The system wineserver is still running after 60 seconds", "error")
                return False, (
                    "Wine processes from the setup are still running. Close them, or stop them "
                    f"with: WINEPREFIX={self.directory} wineserver -k\n"
                    "Then run the installation again."
                )
            except OSError:
                self.log("System wineserver not found, not waiting for the setup's Wine processes", "warning")
            if self.cancel_event.is_set():
                return False, "The installation was cancelled."

            wine = self.get_wine_path("wine")
            if not wine.exists():
                self.log(f"Wine not found at {wine}", "error")
                return False, f"The prefix's Wine was not found at {wine}."
            msi_log = Path(self.directory) / "affinity-msi.log"
            self.update_progress_text("Installing Affinity from its MSI package...")
            self.log(
                f"Installing {msi_files[0].name} with msiexec (log: {msi_log})...",
                "info",
            )
            # The setup window also passes REBOOT=ReallySuppress. Its desktop shortcut
            # checkbox sets INSTALL_DESKTOP_SHORTCUT_PROPERTY; this installer makes its own
            # shortcuts, so the MSI's is turned off.
            success, _, _ = self.run_command(
                [
                    str(wine), "msiexec", "/i",
                    self._to_windows_path(msi_files[0], env=env),
                    "REBOOT=ReallySuppress",
                    "INSTALL_DESKTOP_SHORTCUT_PROPERTY=#0",
                    "/l*v", self._to_windows_path(msi_log, env=env),
                ],
                check=False,
                env=env,
                timeout=3600,  # a big MSI install legitimately runs for a while
            )
            if not success:
                self.log(f"msiexec did not succeed, see {msi_log}", "warning")
            self.log("Waiting for Wine processes to finish...", "info")
            # Bounded: a leftover process would otherwise block here forever.
            self.run_command(
                [str(self.get_wine_path("wineserver")), "-w"],
                check=False,
                env=env,
                timeout=600,
            )

        if self.affinity_v3_exe_path().exists():
            self.log("Affinity installed from its MSI package", "success")
            return True, ""
        return False, f"msiexec did not install Affinity. See {msi_log}."

    def show_affinity_not_installed(self, reason, declined=False):
        """Report that Affinity v3 was not installed, with the reason and where to look next"""
        self.log(
            f"Affinity was not installed: {reason} See {self.AFFINITY_KNOWN_ISSUES_URL}",
            "warning" if declined else "error",
        )
        self.show_message(
            "Affinity Not Installed",
            f"Affinity was not installed.\n\n{reason}\n\n"
            f"See 'Affinity Installer (SetupUI.exe) Crashes':\n{self.AFFINITY_KNOWN_ISSUES_URL}",
            "warning" if declined else "error",
        )

    def run_installation(self, app_name, installer_path):
        """Run the installation process"""
        try:
            self.update_progress_text("Preparing installation...")
            self.update_progress(0.0)
            self.log(f"Selected installer: {installer_path}", "success")

            if not self.verify_required_wine_runtimes():
                self.show_message(
                    "Wine Runtime Missing",
                    ".NET Framework 4.8 is missing in the Wine prefix. Run 'Setup Wine Environment' or 'Install Winetricks Dependencies' again before launching the installer.",
                    "error"
                )
                return
            # Check if installer is already in .AffinityLinux/Installer/ (downloaded installer)
            installer_path_obj = Path(installer_path)
            installer_dir = Path(self.directory) / "Installer"

            # If installer is in .AffinityLinux/Installer/, use it directly
            if installer_path_obj.parent == installer_dir:
                self.log(
                    f"Using installer from .AffinityLinux/Installer/: {installer_path_obj.name}",
                    "info",
                )
                installer_file = installer_path_obj
            else:
                # For custom installers, copy to Wine prefix with sanitized filename (remove spaces)
                self.update_progress_text("Copying installer...")
                self.update_progress(0.1)
                original_filename = installer_path_obj.name
                sanitized_filename = self.sanitize_filename(original_filename)
                installer_file = Path(self.directory) / sanitized_filename
                shutil.copy2(installer_path, installer_file)
                self.log(
                    f"Installer copied to Wine prefix: {installer_file} (WINEPREFIX={self.directory})",
                    "success",
                )

            # Set Windows version
            self.update_progress_text("Configuring Wine...")
            self.update_progress(0.2)
            # Check if this is Affinity v3 or v2
            installer_name = installer_file.name.lower()
            is_affinity_v3 = (
                app_name == "Add" or app_name == "Affinity (Unified)"
            ) or (
                "affinity" in installer_name
                and ("x64" in installer_name or "affinity-x64" in installer_name)
            )
            is_affinity_v2 = (
                any(app in installer_name for app in ["photo", "designer", "publisher"])
                and ".exe" in installer_name
            )

            # Use regular Wine for all installations (wine-tkg is only for winetricks)
            wine_cfg = self.get_wine_path("winecfg")
            wine = self.get_wine_path("wine")

            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory
            self.stop_prefix_wine_processes(
                env, reason="launching the installer"
            )
            self.run_command([str(wine_cfg), "-v", "win11"], check=False, env=env)

            # Run installer
            self.update_progress_text("Running installer...")
            self.update_progress(0.3)

            env["WINEDEBUG"] = "-all"
            self.log("Launching installer...", "info")
            self.log("Follow the installation wizard in the window that opens.", "info")
            self.log("Click 'No' if you encounter any errors.", "warning")

            # Run installer and wait, capturing logs (with fallback)
            success = self._run_installer_and_capture(
                installer_file, env, label="installer"
            )
            if not success and not self.check_cancelled():
                self.log("Installer process exited with a non-zero status", "warning")

            installs_unified = app_name in ("Add", "Affinity (Unified)")
            affinity_v3_exe = self.affinity_v3_exe_path()
            msi_failure = "The Affinity setup finished without installing Affinity."
            if installs_unified and not affinity_v3_exe.exists() and not self.check_cancelled():
                self.log("The Affinity setup finished without installing Affinity", "warning")
                _, msi_failure = self.install_affinity_v3_from_msi(installer_file, env)

            # Clean up installer (only if it was copied to Wine prefix, not if it's in .AffinityLinux/Installer/)
            self.update_progress(0.5)
            if installer_file.parent != installer_dir:
                # Only remove if it was copied (not the original in Installer folder)
                if installer_file.exists():
                    installer_file.unlink()
                    self.log("Installer file removed", "success")
            else:
                self.log(
                    f"Installer kept in .AffinityLinux/Installer/: {installer_file.name}",
                    "info",
                )

            if installs_unified:
                if self.check_cancelled():
                    return
                if not affinity_v3_exe.exists():
                    self.show_affinity_not_installed(msi_failure, declined=msi_failure == self.MSI_DECLINED)
                    return
                self._keep_installer(installer_path_obj, affinity_v3_exe)

            # Restore WinMetadata (only needed for legacy Wine 9.14 and 10.10, not 11.18/11.19)
            wine_version = self.get_current_wine_version()
            if wine_version in ["9.14", "10.10"]:
                self.update_progress_text("Restoring Windows Metadata...")
                self.update_progress(0.6)
                self.restore_winmetadata()
            else:
                self.log(
                    "Skipping WinMetadata restore for Wine 11.18/11.19 (not needed)", "info"
                )

            if app_name == "Add" and self.affinity_v3_exe_path().exists():
                self.install_windowsruntime_facades()

            # Configure OpenCL (if enabled)
            if self.is_opencl_enabled():
                self.update_progress_text("Setting up GPU rendering for Affinity...")
                self.update_progress(0.7)
                self.configure_opencl(app_name)
            else:
                self.log("GPU rendering was not chosen; vkd3d-proton not placed beside Affinity", "info")

            # For Affinity v2 apps (Photo, Designer, Publisher), copy wintypes.dll and set override (only for legacy Wine < 11.18)
            if is_affinity_v2:
                wine_version = self.get_current_wine_version()
                if wine_version in ["9.14", "10.10"]:
                    self.update_progress_text("Configuring wintypes.dll for v2 app...")
                    self.update_progress(0.82)
                    self.setup_wintypes_dll(app_name)
                else:
                    self.log(
                        "Skipping wintypes.dll setup for Wine 11.18/11.19 (not needed)",
                        "info",
                    )

            # For Affinity v3 (Unified), copy wintypes.dll and set override, then patch the DLL (only for legacy Wine < 11.18)
            if app_name == "Add" or app_name == "Affinity (Unified)":
                wine_version = self.get_current_wine_version()
                if wine_version in ["9.14", "10.10"]:
                    # Copy wintypes.dll and set override
                    self.update_progress_text("Configuring wintypes.dll for v3 app...")
                    self.update_progress(0.82)
                    self.setup_wintypes_dll(app_name)
                else:
                    self.log(
                        "Skipping wintypes.dll setup for Wine 11.18/11.19 (not needed)",
                        "info",
                    )

                # Patch the DLL to fix settings saving
                self.update_progress_text("Patching DLL for settings fix...")
                self.update_progress(0.85)
                self.patch_affinity_dll(app_name)

                # Only now: the patch rewrites Serif.Affinity.dll and keeps its
                # identity, so images compiled before it are loaded anyway and
                # Affinity dies in clr.dll at every start.
                if self.affinity_v3_exe_path().exists():
                    self.precompile_affinity()
                    self.ensure_webview2_runtime()

            # Install the file-manager handler before the desktop entry, which
            # only claims the document types once the handler is in place.
            self.update_progress_text("Installing file-manager handler...")
            self.update_progress(0.88)
            self.install_winrt_interop_facade()
            self.install_file_manager_handler()

            # Create desktop entry
            self.update_progress_text("Creating desktop entry...")
            self.update_progress(0.9)
            self.create_desktop_entry(app_name)

            # Run AffinityPluginLoader + WineFix automatically after Affinity (Unified) installs
            if app_name in ["Add", "Affinity (Unified)"]:
                install_dir = (
                    Path(self.directory)
                    / "drive_c"
                    / "Program Files"
                    / "Affinity"
                    / "Affinity"
                )
                if install_dir.exists():
                    self.update_progress_text(
                        "Installing AffinityPluginLoader + WineFix..."
                    )
                    self.log(
                        "\nRunning AffinityPluginLoader + WineFix install...", "info"
                    )
                    self._install_affinity_plugin_loader_thread(standalone=False)
                else:
                    self.log(
                        "\n⚠ Affinity directory not found — skipping AffinityPluginLoader install.",
                        "warning",
                    )

            # Last, after everything that can boot the prefix. wineboot restores
            # Wine's per-namespace winmd files from wine.inf on every prefix
            # update, so clearing them any earlier than this is undone by the
            # next step -- see clear_shadowing_winmds(). Getting this wrong
            # produces an install that looks complete and in which
            # double-clicking a document silently does nothing.
            self.update_progress_text("Finalising WinRT metadata...")
            self.update_progress(0.97)
            self.clear_shadowing_winmds()
            # Again at the end: a prefix whose Wine changed during the install
            # must still come out with opencl off.
            self.disable_opencl_if_needed()
            # And the fonts, last of all: winetricks registers them under
            # wine-tkg, and a later Wine startup can drop them again -- see
            # repair_font_registrations().
            self.update_progress_text("Checking font registrations...")
            self.repair_fonts()

            self.update_progress(1.0)
            self.update_progress_text("Installation complete!")
            display_name = {
                "Add": "Affinity (Unified)",
                "Photo": "Affinity Photo",
                "Designer": "Affinity Designer",
                "Publisher": "Affinity Publisher",
            }.get(app_name, app_name)
            self.log(f"\n✓ {display_name} installation completed!", "success")
            how = self.launch_instructions()
            self.log(how, "info")

            self.show_message(
                "Installation Complete",
                f"{display_name} has been successfully installed!\n\n{how}",
                "info",
            )
            self.offer_after_install()
        except Exception as e:
            self.log(f"Installation error: {e}", "error")
            self.show_message("Installation Error", f"An error occurred:\n{e}", "error")

    def setup_wintypes_dll(self, app_name):
        """Download and copy wintypes.dll next to exe and set up DLL override for Affinity v2 and v3 apps"""
        try:
            # Get app directory and exe path
            app_dir = None
            exe_path = None

            # Handle v2 apps (Photo, Designer, Publisher)
            if app_name in ["Photo", "Designer", "Publisher"]:
                app_names = {
                    "Photo": ("Photo 2", "Photo.exe"),
                    "Designer": ("Designer 2", "Designer.exe"),
                    "Publisher": ("Publisher 2", "Publisher.exe"),
                }
                dir_name, exe = app_names.get(app_name, (None, None))
                if dir_name and exe:
                    app_dir = (
                        Path(self.directory)
                        / "drive_c"
                        / "Program Files"
                        / "Affinity"
                        / dir_name
                    )
                    exe_path = app_dir / exe

            # Handle v3 (Unified) app
            elif app_name == "Add" or app_name == "Affinity (Unified)":
                app_dir = (
                    Path(self.directory)
                    / "drive_c"
                    / "Program Files"
                    / "Affinity"
                    / "Affinity"
                )
                exe_path = app_dir / "Affinity.exe"

            if not app_dir or not exe_path or not exe_path.exists():
                self.log(
                    f"Exe not found for {app_name}, skipping wintypes.dll setup",
                    "warning",
                )
                return

            # Download wintypes.dll to temp location first
            temp_dir = Path(self.directory) / ".temp_wintypes"
            temp_dir.mkdir(exist_ok=True)
            wintypes_temp = temp_dir / "wintypes.dll"

            if not self._download_wintypes_dll(wintypes_temp):
                self.log(f"Failed to download wintypes.dll for {app_name}", "warning")
                return

            # Copy wintypes.dll next to exe
            wintypes_dest = app_dir / "wintypes.dll"
            shutil.copy2(wintypes_temp, wintypes_dest)
            self.log(f"Copied wintypes.dll to {wintypes_dest}", "success")

            # Clean up temp file
            try:
                wintypes_temp.unlink()
            except Exception:
                pass

            # Set up DLL override for wintypes.dll as Native (Windows)
            self.setup_wintypes_dll_override()
        except Exception as e:
            self.log(f"Error setting up wintypes.dll: {e}", "warning")

    def setup_wintypes_dll_override(self):
        """Set up DLL override for wintypes.dll as Native (Windows)"""
        try:
            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory

            # Check if override already exists
            wine = self.get_wine_path("wine")
            success_check, stdout, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "query",
                    "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                    "/v",
                    "wintypes",
                ],
                check=False,
                env=env,
                capture=True,
            )

            if success_check and "native" in stdout:
                self.log("wintypes.dll override already configured", "info")
            else:
                # Create registry file for wintypes override
                reg_file = Path(self.directory) / "wintypes_override.reg"
                with open(reg_file, "w") as f:
                    f.write("REGEDIT4\n")
                    f.write("[HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides]\n")
                    f.write('"wintypes"="native"\n')

                regedit = self.get_wine_path("regedit")
                reg_success, _, stderr = self.run_command(
                    [str(regedit), str(reg_file)], check=False, env=env, capture=True
                )
                reg_file.unlink()

                if reg_success:
                    self.log(
                        "wintypes.dll override configured as Native (Windows)",
                        "success",
                    )
                else:
                    self.log(
                        f"Warning: Could not configure wintypes.dll override: {stderr}",
                        "warning",
                    )
        except Exception as e:
            self.log(f"Error setting up wintypes.dll override: {e}", "warning")

    def copy_wintypes_dll_for_all_apps(self):
        """Download and copy wintypes.dll for all installed Affinity apps (v2 and v3)"""
        try:
            affinity_dir = (
                Path(self.directory) / "drive_c" / "Program Files" / "Affinity"
            )
            if not affinity_dir.exists():
                self.log("Affinity installation directory not found", "warning")
                return

            # Download wintypes.dll to temp location first
            temp_dir = Path(self.directory) / ".temp_wintypes"
            temp_dir.mkdir(exist_ok=True)
            wintypes_temp = temp_dir / "wintypes.dll"

            if not self._download_wintypes_dll(wintypes_temp):
                self.log("Failed to download wintypes.dll", "warning")
                return

            copied_count = 0

            # Check for v2 apps (Photo 2, Designer 2, Publisher 2)
            v2_apps = [
                ("Photo 2", "Photo.exe"),
                ("Designer 2", "Designer.exe"),
                ("Publisher 2", "Publisher.exe"),
            ]

            for dir_name, exe in v2_apps:
                app_dir = affinity_dir / dir_name
                exe_path = app_dir / exe

                if exe_path.exists():
                    wintypes_dest = app_dir / "wintypes.dll"
                    try:
                        shutil.copy2(wintypes_temp, wintypes_dest)
                        self.log(f"Copied wintypes.dll to {wintypes_dest}", "info")
                        copied_count += 1
                    except Exception as e:
                        self.log(
                            f"Warning: Could not copy wintypes.dll to {dir_name}: {e}",
                            "warning",
                        )

            # Check for v3 (Unified) app
            v3_app_dir = affinity_dir / "Affinity"
            v3_exe_path = v3_app_dir / "Affinity.exe"

            if v3_exe_path.exists():
                wintypes_dest = v3_app_dir / "wintypes.dll"
                try:
                    shutil.copy2(wintypes_temp, wintypes_dest)
                    self.log(f"Copied wintypes.dll to {wintypes_dest}", "info")
                    copied_count += 1
                except Exception as e:
                    self.log(
                        f"Warning: Could not copy wintypes.dll to Affinity v3: {e}",
                        "warning",
                    )

            # Clean up temp file
            try:
                wintypes_temp.unlink()
            except Exception:
                pass

            if copied_count > 0:
                self.log(f"Copied wintypes.dll for {copied_count} app(s)", "success")
            else:
                self.log("No Affinity apps found to copy wintypes.dll", "info")
        except Exception as e:
            self.log(f"Error copying wintypes.dll for all apps: {e}", "warning")

    def restore_winmetadata(self):
        """Restore WinMetadata after installation"""
        self.log("Restoring Windows metadata files...", "info")

        # Kill Wine processes
        # Scoped to this prefix: run_command defaults to os.environ.copy(),
        # so with no WINEPREFIX this killed whatever prefix the process had
        # inherited, taking every Wine process it served with it.
        _env = os.environ.copy()
        _env["WINEPREFIX"] = self.directory
        self.run_command(["wineserver", "-k"], check=False, env=_env)
        time.sleep(2)

        system32_dir = Path(self.directory) / "drive_c" / "windows" / "system32"
        system32_dir.mkdir(parents=True, exist_ok=True)

        try:
            winmetadata_dest = system32_dir / "WinMetadata"

            # Remove existing WinMetadata if it exists
            if winmetadata_dest.exists():
                shutil.rmtree(winmetadata_dest)
                self.log("Removed existing WinMetadata folder", "info")

            # Download and extract WinMetadata
            if not self._download_and_extract_winmetadata(system32_dir):
                self.log("Failed to restore WinMetadata", "warning")
                return

            # Verify WinMetadata was extracted
            if not winmetadata_dest.exists():
                self.log("WinMetadata restoration failed - folder not found", "warning")
                return

            self.log("WinMetadata restored", "success")
        except Exception as e:
            self.log(f"Failed to restore WinMetadata: {e}", "warning")

    def affinity_v3_exe_path(self):
        """Return the path of the Affinity v3 (Unified) executable in the prefix"""
        return Path(self.directory) / "drive_c" / "Program Files" / "Affinity" / "Affinity" / "Affinity.exe"

    def get_winetricks_cache_dir(self):
        """Return the winetricks download cache, resolved the same way winetricks does"""
        if os.environ.get("W_CACHE"):
            return Path(os.environ["W_CACHE"])
        if os.environ.get("WINETRICKS_DIR"):
            return Path(os.environ["WINETRICKS_DIR"]) / "cache"
        xdg_cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
        return Path(xdg_cache) / "winetricks"

    def _download_dotnet48_installer(self, installer, url, sha256):
        """Download the .NET 4.8 offline installer into the winetricks cache and verify it"""

        def matches(path):
            digest = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest() == sha256

        if installer.exists():
            if matches(installer):
                return True
            # Same recovery as winetricks: keep the bad file aside and download again.
            os.replace(installer, installer.with_name(installer.name + ".bak"))
            self.log(f"Checksum mismatch for {installer.name}, downloading it again", "warning")

        installer.parent.mkdir(parents=True, exist_ok=True)
        partial = installer.with_name(installer.name + ".part")
        try:
            if not self.download_file(url, str(partial), ".NET Framework 4.8 offline installer"):
                return False
            if not matches(partial):
                self.log(f"Checksum mismatch for the downloaded {installer.name}", "warning")
                return False
            os.replace(partial, installer)
            return True
        finally:
            if partial.exists():
                partial.unlink()

    def windowsruntime_facade_paths(self):
        """Return the GAC path of each WinRT facade in the prefix"""
        gac_dir = (
            Path(self.directory) / "drive_c" / "windows" / "Microsoft.NET" / "assembly" / "GAC_MSIL"
        )
        return {
            name: gac_dir / name / "v4.0_4.0.0.0__b77a5c561934e089" / f"{name}.dll"
            for name in self.WINRT_FACADES
        }

    def windowsruntime_facades_installed(self):
        """Return True when both WinRT facades are in the prefix GAC"""
        try:
            return all(path.exists() for path in self.windowsruntime_facade_paths().values())
        except OSError:
            return False

    def canva_sign_in_wine_support(self):
        """Return "supported", "unsupported" or "unknown" for the prefix's Wine.

        The Canva sign-in fix supports Wine 11.18 and 11.19 (when the build
        carries the login metadata: the applicationmodel.datatransfer,
        applicationmodel.datatransfer, foundation and storage.streams WinMetadata plus
        the SharedStorageAccessManager activation): the callback method needs those to
        JIT, and the stock Wine 11 line does not ship them.
        "unknown" means the prefix's Wine could not be run.
        """
        wine = self.get_wine_path("wine")
        if not wine.exists():
            return "unknown"
        # A build that resolves WinRT namespaces itself -- the 11.16 build with
        # the Affinity patches -- has what 11.12 lacks: with the WinMetadata and
        # the facades installed, the callback method compiles. Detected, not
        # listed by version, for the same reason as wine_resolves_winrt_namespaces.
        if self.wine_resolves_winrt_namespaces():
            return "supported"
        success, stdout, _ = self._run_uncancellable([str(wine), "--version"])
        match = re.search(r"wine-(\d+)\.", stdout) if success else None
        if not match:
            return "unknown"
        if match.group(1) in ("9", "10"):
            return "supported"
        if match.group(1) == "11" and self.canva_sign_in_winmetadata_installed():
            return "supported"
        return "unsupported"

    #: WinMetadata files the Canva sign-in callback needs on Wine 11+.
    CANVA_SIGN_IN_WINMD = (
        "windows.applicationmodel.datatransfer.winmd",
        "windows.foundation.winmd",
        "windows.storage.streams.winmd",
    )

    def canva_sign_in_winmetadata_dir(self):
        """Return the prefix's WinMetadata directory (Wine uses lowercase)."""
        return (
            Path(self.directory) / "drive_c" / "windows" / "system32" / "winmetadata"
        )

    def canva_sign_in_winmetadata_installed(self):
        """Return True when the prefix has the WinMetadata the sign-in needs."""
        try:
            winmetadata = self.canva_sign_in_winmetadata_dir()
            return all((winmetadata / name).exists() for name in self.CANVA_SIGN_IN_WINMD)
        except OSError:
            return False

    @staticmethod
    def prefix_windows_path(directory, path):
        """Return the Windows path of a file in a prefix: C:\\ for drive_c, Z:\\ otherwise."""
        drive_c = Path(directory) / "drive_c"
        path = Path(path)
        try:
            return "C:\\" + str(path.relative_to(drive_c)).replace("/", "\\")
        except ValueError:
            return "Z:" + str(path).replace("/", "\\")

    def precompile_affinity(self, exe_path=None):
        """Compile Affinity's .NET assemblies to native images with ngen, as Windows does.

        Windows' .NET Framework precompiles an installed application's assemblies
        in the background. Under Wine nothing does, so Affinity JIT-compiles its own
        code at every launch and the first time each part of it is used. The first
        studio switch in a session took 1.3-1.4 s, and 0.8-1.0 s with native images.
        The images are tied to the assemblies they were made from: after an Affinity
        update .NET ignores them and JIT-compiles again until this runs again.

        The 64-bit ngen.exe has hung under Wine 11's new WoW64 during the .NET
        winetricks verbs, so this has a deadline, and failing is not an error:
        Affinity runs the same without native images, only slower to warm up.
        """
        exe = Path(exe_path) if exe_path else self.affinity_v3_exe_path()
        if not exe.exists():
            return False
        if not self.has_dotnet48_runtime():
            self.log(".NET Framework 4.8 is not installed in the prefix, skipping native images", "warning")
            return False
        framework = Path(self.directory) / "drive_c" / "windows" / "Microsoft.NET" / "Framework64" / "v4.0.30319"
        if not (framework / "ngen.exe").exists():
            self.log("ngen.exe not found in the prefix, skipping native images", "warning")
            return False
        wine = self.get_wine_path("wine")
        if not wine.exists():
            return False

        env = os.environ.copy()
        env["WINEPREFIX"] = str(self.directory)
        env["WINEDEBUG"] = "-all"
        self.update_progress_text("Compiling Affinity to native code...")
        self.log("Compiling Affinity's .NET assemblies to native images (ngen), a minute or two...", "info")
        success, stdout, stderr = self.run_command(
            [
                str(wine),
                self.prefix_windows_path(self.directory, framework / "ngen.exe"),
                "install",
                self.prefix_windows_path(self.directory, exe),
            ],
            check=False,
            env=env,
            timeout=900,
        )
        if success:
            self.log("Affinity compiled to native images: it warms up faster", "success")
            return True
        if (stderr or "").startswith("Timed out"):
            self.log("ngen did not finish; Affinity will run without native images", "warning")
            for line in kill_stalled_wine_processes(self.directory) or []:
                self.log(line, "info")
        else:
            last = ((stdout or "") + (stderr or "")).strip().splitlines()[-1:] or [""]
            self.log(f"ngen failed ({last[0]}); Affinity will run without native images", "warning")
        return False

    def install_windowsruntime_facades(self):
        """Install the .NET Framework WinRT facades that `winetricks dotnet48` leaves out.

        Affinity handles the affinity:// callback of the Canva sign-in in
        Serif.Affinity.Application.ProcessCommandLineArguments. The CLR cannot JIT that
        method without System.Runtime.WindowsRuntime, and also needs WinMetadata. The
        .NET 4.8 offline installer only carries these facades inside its Windows 8+
        servicing packages, which are not installed under Wine, so they are copied into the GAC.
        """
        installer_name = "ndp48-x86-x64-allos-enu.exe"
        installer_url = (
            "https://download.visualstudio.microsoft.com/download/pr/"
            "7afca223-55d2-470a-8edc-6a1739ae3252/abd170b4b0ec15ad0222a809b761a036/"
            + installer_name
        )
        installer_sha256 = "95889d6de3f2070c07790ad6cf2000d33d9a1bdfc6a381725ab82ab1c314fd53"
        cab_name = "x64-Windows10.0-KB4486153-x64.cab"
        temp_prefix = ".winrt-facades-"

        for stale in Path(self.directory).glob(temp_prefix + "*"):
            shutil.rmtree(stale, ignore_errors=True)

        targets = self.windowsruntime_facade_paths()
        if self.windowsruntime_facades_installed():
            return True

        wine_support = self.canva_sign_in_wine_support()
        if wine_support == "unknown":
            self.log("Could not run the prefix's Wine, skipping the WinRT facades", "warning")
            return False
        if wine_support == "unsupported":
            self.log("Skipping the WinRT facades: the Canva sign-in fix supports Wine 11.18 and 11.19 with login metadata", "info")
            return False
        if not self.has_dotnet48_runtime():
            self.log(".NET Framework 4.8 is not installed in the prefix, skipping the WinRT facades", "warning")
            return False
        if not self.check_command("7z"):
            self.log("7z not found, skipping the WinRT facades needed for Canva sign-in", "warning")
            return False

        self.update_progress_text("Installing WinRT facades for .NET 4.8...")
        self.log("Installing WinRT facades for .NET 4.8 (Canva sign-in)...", "info")
        installer = self.get_winetricks_cache_dir() / "dotnet48" / installer_name
        try:
            if not self._download_dotnet48_installer(installer, installer_url, installer_sha256):
                self.log("Could not get the .NET Framework 4.8 offline installer", "warning")
                return False

            # The prefix is on disk; /tmp may be RAM-backed and the cab is about 350 MB.
            with tempfile.TemporaryDirectory(prefix=temp_prefix, dir=self.directory) as temp_dir:
                temp_path = Path(temp_dir)
                # 7z exits with 1 on warnings, so the extracted files decide success.
                _, stdout, stderr = self.run_command(
                    ["7z", "e", "-y", f"-o{temp_path}", str(installer), cab_name], check=False
                )
                cab_path = temp_path / cab_name
                if not cab_path.exists():
                    self.log(f"Could not extract {cab_name}: {(stdout + stderr).strip()}", "warning")
                    return False

                dll_dir = temp_path / "dll"
                patterns = [f"msil_{name.lower()}_b77a5c561934e089_*/*" for name in self.WINRT_FACADES]
                _, stdout, stderr = self.run_command(
                    ["7z", "e", "-y", f"-o{dll_dir}", str(cab_path)] + patterns, check=False
                )
                if self.cancel_event.is_set():
                    return False

                for name, target in targets.items():
                    source = dll_dir / f"{name.lower()}.dll"
                    if not source.exists():
                        self.log(f"{source.name} not found in {cab_name}: {(stdout + stderr).strip()}", "warning")
                        return False
                    with open(source, "rb") as f:
                        if hashlib.sha256(f.read()).hexdigest() != self.WINRT_FACADES[name]:
                            self.log(f"Unexpected checksum for {source.name}, skipping the WinRT facades", "warning")
                            return False
                    target.parent.mkdir(parents=True, exist_ok=True)
                    staged = target.with_name(target.name + ".tmp")
                    shutil.copy2(source, staged)
                    os.replace(staged, target)

            self.log("WinRT facades for .NET 4.8 installed", "success")
            return True
        except Exception as e:
            self.log(f"Failed to install the WinRT facades: {e}", "warning")
            return False

    def is_opencl_enabled(self):
        """Check if OpenCL is enabled"""
        # First check instance variable (set during one-click setup)
        if hasattr(self, "enable_opencl") and self.enable_opencl:
            return True

        # Check saved preference
        opencl_config_file = Path(self.directory) / ".opencl_enabled"
        if opencl_config_file.exists():
            try:
                with open(opencl_config_file, "r") as f:
                    content = f.read().strip()
                    return content == "1"
            except Exception:
                pass

        return False

    def get_renderer_setting(self):
        """Get the current renderer setting from registry (vulkan, gl, or gdi)."""
        try:
            wine = self.get_wine_path("wine")
            if not wine.exists():
                return "vulkan"  # Default to vulkan if Wine not set up

            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory

            success, stdout, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "query",
                    "HKEY_CURRENT_USER\\Software\\Wine\\Direct3D",
                    "/v",
                    "renderer",
                ],
                check=False,
                env=env,
                capture=True,
            )

            if success and stdout:
                stdout_lower = stdout.lower()
                if "gl" in stdout_lower or "opengl" in stdout_lower:
                    return "gl"
                elif "gdi" in stdout_lower:
                    return "gdi"
                elif "vulkan" in stdout_lower:
                    return "vulkan"

            # Default to vulkan if not found
            return "vulkan"
        except Exception:
            return "vulkan"  # Default to vulkan on error

    def force_wine_x11_driver_if_needed(self, env=None):
        """Force Wine to use X11 when the host session runs on Wayland."""
        session_type = (os.environ.get("XDG_SESSION_TYPE") or "").lower()
        if session_type != "wayland":
            return True

        env = os.environ.copy() if env is None else env.copy()
        env["WINEPREFIX"] = self.directory
        env.setdefault("DISPLAY", os.environ.get("DISPLAY", ":0"))

        xauthority = os.environ.get("XAUTHORITY")
        if xauthority:
            env["XAUTHORITY"] = xauthority

        wine = self.get_wine_path("wine")
        if not wine.exists():
            self.log("Wine binary not found while forcing the X11 graphics driver.", "warning")
            return False

        self.log("Wayland session detected; forcing Wine to use the X11 graphics driver.", "info")
        success, _, stderr = self.run_command(
            [
                str(wine), "reg", "add",
                "HKEY_CURRENT_USER\\Software\\Wine\\Drivers",
                "/v", "Graphics",
                "/t", "REG_SZ",
                "/d", "x11",
                "/f",
            ],
            check=False,
            env=env,
            capture=True,
        )
        if success:
            self.log("✓ Wine graphics driver forced to X11 for this prefix", "success")
        else:
            self.log(f"Warning: Could not force Wine graphics driver to X11: {stderr}", "warning")
        return success

    def get_affinity_v3_user_data_dir(self):
        """Return the per-user Affinity v3 roaming data directory inside the prefix."""
        username = os.environ.get("USER") or os.environ.get("LOGNAME") or "user"
        return (
            Path(self.directory)
            / "drive_c"
            / "users"
            / username
            / "AppData"
            / "Roaming"
            / "Affinity"
            / "Affinity"
            / "3.0"
        )

    def affinity_v3_user_data_has_startup_corruption_signature(self):
        """Detect the reproducible Affinity v3 profile corruption signature seen on Ubuntu."""
        log_file = self.get_affinity_v3_user_data_dir() / "Log.txt"
        if not log_file.exists():
            return False

        try:
            content = log_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return False

        signatures = [
            "JPEG XL: input does not have a valid signature",
        ]
        return any(signature in content for signature in signatures)

    def quarantine_affinity_v3_user_data(self, reason):
        """Back up the current Affinity v3 roaming profile and recreate an empty one."""
        user_data_dir = self.get_affinity_v3_user_data_dir()
        if not user_data_dir.exists():
            return True

        backup_dir = user_data_dir.parent / f"{user_data_dir.name}.backup-{time.strftime('%Y%m%d-%H%M%S')}"
        try:
            self.log(reason, "warning")
            self.log(f"Backing up Affinity v3 user data to {backup_dir}", "info")
            shutil.move(str(user_data_dir), str(backup_dir))
            user_data_dir.mkdir(parents=True, exist_ok=True)
            self.log("✓ Affinity v3 user data reset completed", "success")
            return True
        except Exception as e:
            self.log(f"Warning: Could not back up Affinity v3 user data: {e}", "warning")
            return False

    def configure_opencl(self, app_name):
        """Configure d3d12 DLLs for application (needed even when using DXVK)"""
        app_dirs = {
            "Photo": "Photo 2",
            "Designer": "Designer 2",
            "Publisher": "Publisher 2",
            "Add": "Affinity",
        }

        app_dir_name = app_dirs.get(app_name, "Affinity")
        app_dir = (
            Path(self.directory)
            / "drive_c"
            / "Program Files"
            / "Affinity"
            / app_dir_name
        )

        if not app_dir.exists():
            self.log(f"Application directory not found: {app_dir}", "warning")
            return

        wine_lib_dir = (
            self.get_wine_dir() / "lib" / "wine" / "vkd3d-proton" / "x86_64-windows"
        )
        vkd3d_temp = Path(self.directory) / "vkd3d_dlls"

        # Ensure DLLs are installed in Wine library first
        if not wine_lib_dir.exists() or not (wine_lib_dir / "d3d12.dll").exists():
            self.log("d3d12 DLLs not found in Wine library, installing...", "info")
            self.install_d3d12_dlls()

        dlls_copied = self.sync_vkd3d_runtime_into_app_dir(app_dir, app_dir_name)
        # Ensure DLL overrides are set up
        self.setup_d3d12_overrides()

        if dlls_copied > 0:
            self.log(f"d3d12 DLLs configured for {app_dir_name}", "success")

    def sync_vkd3d_runtime_into_app_dir(self, app_dir, app_label=None):
        """Copy the vkd3d-proton D3D12 runtime next to an Affinity EXE if needed."""
        wine_lib_dir = self.get_wine_dir() / "lib" / "wine" / "vkd3d-proton" / "x86_64-windows"
        vkd3d_temp = Path(self.directory) / "vkd3d_dlls"
        copied = 0
        label = app_label or app_dir.name

        for dll in ["d3d12.dll", "d3d12core.dll"]:
            target = app_dir / dll
            source = None

            for candidate in [vkd3d_temp / dll, wine_lib_dir / dll]:
                if candidate.exists():
                    source = candidate
                    break

            if not source:
                self.log(f"Warning: Could not find a vkd3d-proton copy of {dll} for {label}", "warning")
                continue

            needs_copy = (
                not target.exists()
                or target.stat().st_size != source.stat().st_size
            )
            if needs_copy:
                shutil.copy2(source, target)
                self.log(f"Copied {dll} to {label}", "success")
                copied += 1

        return copied

    def build_local_mscms_shim(self):
        """Build the local mscms compatibility shim if a compiler is available."""
        build_dir = Path(self.directory) / "wine_shims"
        source = Path(__file__).resolve().parent.parent / "mscms_shim.c"
        output = build_dir / "mscms.dll"

        if output.exists() and source.exists() and output.stat().st_mtime >= source.stat().st_mtime:
            return output

        if not source.exists():
            self.log(f"Warning: mscms shim source not found: {source}", "warning")
            return None

        compiler = shutil.which("x86_64-w64-mingw32-gcc")
        if not compiler:
            self.log("Warning: x86_64-w64-mingw32-gcc not found; mscms compatibility shim will be skipped", "warning")
            return None

        try:
            build_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.log(f"Warning: Could not create the mscms shim build directory: {e}", "warning")
            return None

        success, _, stderr = self.run_command(
            [
                compiler,
                "-shared",
                "-O2",
                "-Wl,--export-all-symbols",
                "-o",
                str(output),
                str(source),
            ],
            check=False,
        )
        if not success or not output.exists():
            err_text = stderr.strip() if stderr else "unknown compiler error"
            self.log(f"Warning: Failed to build the mscms compatibility shim: {err_text}", "warning")
            return None

        self.log("Built the local mscms compatibility shim", "success")
        return output

    def sync_mscms_shim_into_app_dir(self, app_dir, app_label=None):
        """Deploy the mscms compatibility shim next to an Affinity EXE if possible."""
        shim_source = self.build_local_mscms_shim()
        builtin_source = Path(self.directory) / "drive_c" / "windows" / "system32" / "mscms.dll"
        label = app_label or app_dir.name
        copied = 0

        if not shim_source or not shim_source.exists():
            return 0

        if not builtin_source.exists():
            self.log(f"Warning: Could not find Wine's builtin mscms.dll for {label}", "warning")
            return 0

        copies = [
            (shim_source, app_dir / "mscms.dll"),
            (builtin_source, app_dir / "mscms_builtin.dll"),
        ]

        for source, target in copies:
            needs_copy = (
                not target.exists()
                or target.stat().st_size != source.stat().st_size
            )
            if needs_copy:
                shutil.copy2(source, target)
                self.log(f"Copied {target.name} to {label}", "success")
                copied += 1

        return copied

    def enable_opencl_support(self):
        """Enable OpenCL support for Affinity applications"""
        # Check if Wine is set up
        wine = self.get_wine_path("wine")
        if not wine.exists():
            QMessageBox.warning(
                self,
                "Wine Not Installed",
                "Wine must be installed before setting up GPU rendering.\n\n"
                "Please run 'One-Click Setup' or 'Setup Wine Environment' first.",
            )
            return

        # Check if OpenCL is already enabled
        if self.is_opencl_enabled():
            reply = QMessageBox.question(
                self,
                "GPU rendering already set up",
                "GPU rendering is already set up for this prefix.\n\n"
                "Set it up again?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Use your graphics card",
            "This sets up GPU rendering for Affinity:\n\n"
            "• vkd3d-proton (or d3d12 DLLs / DXVK for AMD cards), which lets "
            "Affinity's Direct3D 12 canvas run on your graphics card\n"
            "• AMD OpenCL dependencies, if an AMD card is detected\n\n"
            "OpenCL acceleration itself stays switched off on Wine 11.11 and "
            "newer, because it has made Affinity hang at startup (seen on "
            "Intel Arc; other cards untested). On an older Wine build it is "
            "turned on too.\n\n"
            "Set this up now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Run in a thread to avoid blocking UI
        def enable_opencl_thread():
            try:
                self.update_progress(0.0)
                self.update_progress_text("Setting up GPU rendering...")
                self.log(
                    "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                self.log("Setting Up GPU Rendering", "info")
                self.log(
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                )

                # Set OpenCL preference
                self.enable_opencl = True
                self.update_progress(0.1)

                # Save OpenCL preference
                opencl_config_file = Path(self.directory) / ".opencl_enabled"
                try:
                    with open(opencl_config_file, "w") as f:
                        f.write("1")
                    self.log("OpenCL preference saved", "success")
                    # Verify it was saved correctly
                    if opencl_config_file.exists():
                        with open(opencl_config_file, "r") as f:
                            content = f.read().strip()
                            if content == "1":
                                self.log("OpenCL preference verified", "success")
                            else:
                                self.log(
                                    f"Warning: OpenCL preference file contains '{content}' instead of '1'",
                                    "warning",
                                )
                    else:
                        self.log(
                            "Error: OpenCL preference file was not created", "error"
                        )
                except Exception as e:
                    self.log(f"Error: Failed to save OpenCL preference: {e}", "error")
                    import traceback

                    self.log(f"Traceback: {traceback.format_exc()}", "error")

                self.update_progress(0.2)

                # Check GPU and set up accordingly
                gpu_id = self.get_selected_gpu()
                if self.has_nvidia_gpu() and (
                    gpu_id.startswith("nvidia_") or gpu_id.startswith("auto")
                ):
                    # Ask NVIDIA users to choose between DXVK and vkd3d
                    preference = self.ask_nvidia_dxvk_vkd3d_choice()
                    self.update_progress(0.4)

                    if preference == "dxvk":
                        self.update_progress_text(
                            "NVIDIA GPU with DXVK preference - installing d3d12 DLLs..."
                        )
                        self.log(
                            "NVIDIA GPU with DXVK preference - installing d3d12 DLLs and setting up DLL overrides",
                            "info",
                        )
                        self.install_d3d12_dlls()
                    else:
                        self.update_progress_text(
                            "Setting up vkd3d-proton (GPU rendering)..."
                        )
                        self.log("Setting up vkd3d-proton (GPU rendering)...", "info")
                        self.setup_vkd3d()

                elif self.has_amd_gpu() and (
                    gpu_id.startswith("amd_") or gpu_id.startswith("auto")
                ):
                    self.update_progress_text(
                        "AMD GPU detected - installing OpenCL dependencies..."
                    )
                    self.log(
                        "AMD GPU detected - installing additional OpenCL dependencies...",
                        "info",
                    )

                    amd_deps = []
                    install_cmd = None

                    # Fedora
                    if self.distro == "fedora":
                        if self.distro_version == "43":
                            amd_deps = [
                                "mesa-opencl-icd",
                                "ocl-icd",
                                "rocm-opencl",
                                "rocm-hip",
                                "wine-opencl",
                            ]
                            self.log(
                                "Fedora 43 detected - installing Fedora 43 specific AMD OpenCL dependencies...",
                                "info",
                            )
                        else:
                            amd_deps = [
                                "rocm-opencl",
                                "apr",
                                "apr-util",
                                "zlib",
                                "libxcrypt-compat",
                                "libcurl",
                                "libcurl-devel",
                                "mesa-libGLU",
                            ]
                        install_cmd = ["sudo", "dnf", "install", "-y"] + amd_deps

                    # Arch-based distributions
                    elif self.distro in ["arch", "cachyos", "endeavouros", "xerolinux"]:
                        amd_deps = [
                            "opencl-mesa",
                            "ocl-icd",
                            "rocm-opencl-runtime",
                            "rocm-hip",
                            "wine-opencl",
                        ]
                        self.log(
                            f"{self.format_distro_name()} detected - installing Arch-based AMD OpenCL dependencies...",
                            "info",
                        )
                        install_cmd = [
                            "sudo",
                            "pacman",
                            "-S",
                            "--needed",
                            "--noconfirm",
                        ] + amd_deps

                    # PikaOS (Ubuntu/Debian-based)
                    elif self.distro == "pikaos":
                        amd_deps = [
                            "mesa-opencl-icd",
                            "ocl-icd-libopencl1",
                            "rocm-opencl-runtime",
                            "rocm-hip-runtime",
                        ]
                        self.log(
                            "PikaOS detected - installing Debian/Ubuntu-based AMD OpenCL dependencies...",
                            "info",
                        )
                        install_cmd = ["sudo", "apt", "install", "-y"] + amd_deps

                    # Install dependencies if we have a command
                    if install_cmd and amd_deps:
                        self.log(f"Installing: {', '.join(amd_deps)}", "info")
                        success, stdout, stderr = self.run_command(install_cmd)

                        if success:
                            self.log(
                                "AMD OpenCL dependencies installed successfully",
                                "success",
                            )
                        else:
                            self.log(
                                f"Warning: Failed to install some AMD OpenCL dependencies: {stderr}",
                                "warning",
                            )
                            self.log(
                                "OpenCL may still work, but some features might be limited",
                                "warning",
                            )

                    self.update_progress(0.5)
                    self.update_progress_text("Installing d3d12 DLLs for AMD GPU...")
                    self.install_d3d12_dlls()

                else:
                    self.update_progress(0.4)
                    self.update_progress_text("Setting up vkd3d-proton (GPU rendering)...")
                    self.log("Setting up vkd3d-proton (GPU rendering)...", "info")
                    self.setup_vkd3d()

                self.update_progress(0.8)

                # Configure OpenCL for all installed Affinity applications
                self.update_progress_text(
                    "Setting up GPU rendering for Affinity applications..."
                )
                apps_to_configure = []

                # Check which apps are installed
                app_dirs = {
                    "Photo": "Photo 2",
                    "Designer": "Designer 2",
                    "Publisher": "Publisher 2",
                    "Add": "Affinity",
                }

                for app_name, app_dir_name in app_dirs.items():
                    app_dir = (
                        Path(self.directory)
                        / "drive_c"
                        / "Program Files"
                        / "Affinity"
                        / app_dir_name
                    )
                    if app_dir.exists():
                        apps_to_configure.append(app_name)

                if apps_to_configure:
                    self.log(
                        f"Setting up GPU rendering for: {', '.join(apps_to_configure)}",
                        "info",
                    )
                    for app_name in apps_to_configure:
                        self.configure_opencl(app_name)
                else:
                    self.log("No Affinity applications found to configure", "info")

                self.update_progress(1.0)
                self.update_progress_text("GPU rendering set up")

                # Verify OpenCL is enabled
                if self.is_opencl_enabled():
                    self.log(
                        "\n✓ GPU rendering has been set up.", "success"
                    )
                    self.log(
                        "vkd3d-proton is now in place for all installed Affinity applications.",
                        "info",
                    )
                    # Show success message on main thread
                    self.show_message(
                        "GPU rendering set up",
                        "GPU rendering has been set up for all installed Affinity "
                        "applications.\n\n"
                        "You may need to restart Affinity applications for the changes to take effect.",
                        "info",
                    )
                else:
                    self.log(
                        "\n⚠ Warning: the GPU rendering preference may not have been saved correctly",
                        "warning",
                    )
                    self.log(
                        "Please check the .opencl_enabled file in your Affinity directory",
                        "warning",
                    )
                    self.show_message(
                        "GPU rendering",
                        "GPU rendering was set up, but the preference may not have been saved correctly.\n\n"
                        "Please check the log for details.",
                        "warning",
                    )

                # Refresh installation status
                self.refresh_status_signal.emit()

            except Exception as e:
                import traceback

                error_msg = str(e)
                error_trace = traceback.format_exc()
                self.log(f"Error setting up GPU rendering: {error_msg}", "error")
                self.log(f"Traceback: {error_trace}", "error")
                self.update_progress_text("Error setting up GPU rendering")
                self.show_message(
                    "Error",
                    f"An error occurred while setting up GPU rendering:\n\n{error_msg}\n\nCheck the log for details.",
                    "error",
                )

        # Start the thread
        thread = threading.Thread(target=enable_opencl_thread, daemon=True)
        thread.start()

    def _parse_version(self, version_str):
        """Parse version string and return tuple of (major, minor, patch) for comparison"""
        try:
            # Remove any non-numeric suffixes (e.g., "8.0.100-preview" -> "8.0.100")
            version_str = version_str.strip().split("-")[0].split("+")[0]
            parts = version_str.split(".")
            major = int(parts[0]) if len(parts) > 0 else 0
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
            return (major, minor, patch)
        except (ValueError, IndexError):
            return (0, 0, 0)

    def _is_version_sufficient(self, version_str, min_major=8):
        """Check if version is 8.0 or newer"""
        major, minor, patch = self._parse_version(version_str)
        return major >= min_major

    def check_dotnet_sdk_10(self):
        """Check if .NET SDK version 10.0 or newer is installed"""
        # First, try to run dotnet --version
        success, stdout, _ = self.run_command(
            ["dotnet", "--version"], check=False, capture=True
        )
        if success and stdout:
            version = stdout.strip()
            major, minor, patch = self._parse_version(version)
            if major >= 10:
                self.log(f".NET SDK 10.0+ found (version {version})", "success")
                return True
            else:
                self.log(
                    f".NET SDK found but version {version} is too old (need 10.0+)",
                    "warning",
                )
                return False

        # If dotnet command not found, check if it's installed via package manager
        if self.distro in ["fedora", "nobara"]:
            success, stdout, _ = self.run_command(
                ["dnf", "list", "installed", "dotnet-sdk*"], check=False, capture=True
            )
            if success and stdout:
                for line in stdout.split("\n"):
                    if "dotnet-sdk" in line.lower() and "installed" in line.lower():
                        match = re.search(r"dotnet-sdk-(\d+)\.(\d+)", line)
                        if match:
                            major = int(match.group(1))
                            if major >= 10:
                                self.log(
                                    f".NET SDK 10.0+ package found via dnf: {line.split()[0]}",
                                    "success",
                                )
                                return True

        elif self.distro in ["arch", "cachyos", "endeavouros", "xerolinux"]:
            success, stdout, _ = self.run_command(
                ["pacman", "-Q"], check=False, capture=True
            )
            if success and stdout:
                for line in stdout.split("\n"):
                    if "dotnet-sdk" in line.lower():
                        match = re.search(r"dotnet-sdk-(\d+)\.(\d+)", line)
                        if match:
                            major = int(match.group(1))
                            if major >= 10:
                                self.log(
                                    f".NET SDK 10.0+ package found via pacman: {line.split()[0]}",
                                    "success",
                                )
                                return True

        elif self.distro in ["pikaos", "pop", "debian"]:
            success, stdout, _ = self.run_command(
                ["dpkg", "-l", "dotnet-sdk*"], check=False, capture=True
            )
            if success and stdout:
                for line in stdout.split("\n"):
                    if "dotnet-sdk" in line.lower() and line.startswith("ii"):
                        match = re.search(r"dotnet-sdk-(\d+)\.(\d+)", line)
                        if match:
                            major = int(match.group(1))
                            if major >= 10:
                                self.log(
                                    f".NET SDK 10.0+ package found via dpkg: {line.split()[1]}",
                                    "success",
                                )
                                return True

        return False

    def check_dotnet_sdk(self):
        """Check if .NET SDK version 8.0 or newer is installed"""
        # First, try to run dotnet --version
        success, stdout, _ = self.run_command(
            ["dotnet", "--version"], check=False, capture=True
        )
        if success and stdout:
            version = stdout.strip()
            if self._is_version_sufficient(version):
                self.log(
                    f".NET SDK found (version {version}) - using installed version",
                    "success",
                )
                return True
            else:
                self.log(
                    f".NET SDK found but version {version} is too old (need 8.0+)",
                    "warning",
                )

        common_paths = [
            "/usr/bin/dotnet",
            "/usr/local/bin/dotnet",
            "/opt/dotnet/dotnet",
            Path.home() / ".dotnet" / "dotnet",
            Path.home() / "bin" / "dotnet" / "dotnet",
            Path.home() / "bin" / "dotnet",
        ]
        # Also check DOTNET_ROOT environment variable if set
        dotnet_root = os.environ.get("DOTNET_ROOT")
        if dotnet_root:
            common_paths.insert(0, Path(dotnet_root) / "dotnet")
            common_paths.insert(1, Path(dotnet_root))

        for path in common_paths:
            path_obj = Path(path)
            if path_obj.exists() and path_obj.is_file():
                # Try running it
                success, stdout, _ = self.run_command(
                    [str(path), "--version"], check=False, capture=True
                )
                if success and stdout:
                    version = stdout.strip()
                    if self._is_version_sufficient(version):
                        self.log(
                            f".NET SDK found at {path}: {version} - using installed version",
                            "success",
                        )
                        return True

        # If dotnet command not found, check if it's installed via package manager
        # This is useful when dotnet is installed but not in PATH
        if self.distro in ["fedora", "nobara"]:
            # Check for any dotnet-sdk package (not just 8.0)
            success, stdout, _ = self.run_command(
                ["dnf", "list", "installed", "dotnet-sdk*"], check=False, capture=True
            )
            if success and stdout:
                # Look for any dotnet-sdk package
                for line in stdout.split("\n"):
                    if "dotnet-sdk" in line.lower() and "installed" in line.lower():
                        # Extract version from package name (e.g., dotnet-sdk-8.0, dotnet-sdk-9.0)
                        match = re.search(r"dotnet-sdk-(\d+)\.(\d+)", line)
                        if match:
                            major = int(match.group(1))
                            if major >= 8:
                                self.log(
                                    f".NET SDK package found via dnf: {line.split()[0]}",
                                    "success",
                                )
                                # Try to find dotnet in common locations
                                common_paths = [
                                    "/usr/bin/dotnet",
                                    "/usr/local/bin/dotnet",
                                    "/opt/dotnet/dotnet",
                                    Path.home() / ".dotnet" / "dotnet",
                                ]
                                for path in common_paths:
                                    if Path(path).exists():
                                        # Try running it
                                        success, stdout, _ = self.run_command(
                                            [str(path), "--version"],
                                            check=False,
                                            capture=True,
                                        )
                                        if success and stdout:
                                            version = stdout.strip()
                                            if self._is_version_sufficient(version):
                                                self.log(
                                                    f".NET SDK found at {path}: {version} - using installed version",
                                                    "success",
                                                )
                                                return True
                                # Package is installed but dotnet command not accessible
                                self.log(
                                    ".NET SDK package is installed but 'dotnet' command not found in PATH",
                                    "warning",
                                )
                                self.log(
                                    "You may need to add /usr/bin to your PATH or restart your terminal",
                                    "info",
                                )
                                return True  # Return True anyway since package is installed

        elif self.distro in ["arch", "cachyos", "endeavouros", "xerolinux"]:
            # Check for any dotnet-sdk package via pacman
            # Query all installed packages and filter for dotnet-sdk
            success, stdout, _ = self.run_command(
                ["pacman", "-Q"], check=False, capture=True
            )
            if success and stdout:
                # Check all installed packages for dotnet-sdk
                for line in stdout.split("\n"):
                    if "dotnet-sdk" in line.lower():
                        # Extract version from package name (e.g., dotnet-sdk-8.0, dotnet-sdk-9.0)
                        match = re.search(r"dotnet-sdk-(\d+)\.(\d+)", line)
                        if match:
                            major = int(match.group(1))
                            if major >= 8:
                                package_name = line.split()[0]
                                self.log(
                                    f".NET SDK package found via pacman: {package_name}",
                                    "success",
                                )
                                # Try common paths
                                common_paths = [
                                    "/usr/bin/dotnet",
                                    "/usr/local/bin/dotnet",
                                ]
                                for path in common_paths:
                                    if Path(path).exists():
                                        success, stdout, _ = self.run_command(
                                            [path, "--version"],
                                            check=False,
                                            capture=True,
                                        )
                                        if success and stdout:
                                            version = stdout.strip()
                                            if self._is_version_sufficient(version):
                                                self.log(
                                                    f".NET SDK found at {path}: {version} - using installed version",
                                                    "success",
                                                )
                                                return True
                                return True  # Package is installed

        elif self.distro in ["pikaos", "pop", "debian"]:
            # Check for any dotnet-sdk package via dpkg
            success, stdout, _ = self.run_command(
                ["dpkg", "-l", "dotnet-sdk*"], check=False, capture=True
            )
            if success and stdout:
                # Look for any dotnet-sdk package
                for line in stdout.split("\n"):
                    if "dotnet-sdk" in line.lower() and line.startswith("ii"):
                        # Extract version from package name (e.g., dotnet-sdk-8.0, dotnet-sdk-9.0)
                        match = re.search(r"dotnet-sdk-(\d+)\.(\d+)", line)
                        if match:
                            major = int(match.group(1))
                            if major >= 8:
                                self.log(
                                    f".NET SDK package found via dpkg: {line.split()[1]}",
                                    "success",
                                )
                                common_paths = [
                                    "/usr/bin/dotnet",
                                    "/usr/local/bin/dotnet",
                                ]
                                for path in common_paths:
                                    if Path(path).exists():
                                        success, stdout, _ = self.run_command(
                                            [path, "--version"],
                                            check=False,
                                            capture=True,
                                        )
                                        if success and stdout:
                                            version = stdout.strip()
                                            if self._is_version_sufficient(version):
                                                self.log(
                                                    f".NET SDK found at {path}: {version} - using installed version",
                                                    "success",
                                                )
                                                return True
                                return True  # Package is installed

        elif self.distro in ["opensuse-tumbleweed", "opensuse-leap"]:
            # Check for any dotnet-sdk package via zypper
            success, stdout, _ = self.run_command(
                ["zypper", "search", "-i", "dotnet-sdk*"], check=False, capture=True
            )
            if success and stdout:
                # Look for any installed dotnet-sdk package
                for line in stdout.split("\n"):
                    if "dotnet-sdk" in line.lower() and "|" in line:
                        # Extract version from package name (e.g., dotnet-sdk-8.0, dotnet-sdk-9.0)
                        match = re.search(r"dotnet-sdk-(\d+)\.(\d+)", line)
                        if match:
                            major = int(match.group(1))
                            if major >= 8:
                                # Extract package name (first field before |)
                                package_name = line.split("|")[0].strip()
                                self.log(
                                    f".NET SDK package found via zypper: {package_name}",
                                    "success",
                                )
                                # Try common paths
                                common_paths = [
                                    "/usr/bin/dotnet",
                                    "/usr/local/bin/dotnet",
                                    "/opt/dotnet/dotnet",
                                    Path.home() / ".dotnet" / "dotnet",
                                    Path.home() / "bin" / "dotnet" / "dotnet",
                                    Path.home() / "bin" / "dotnet",
                                ]
                                # Also check DOTNET_ROOT if set
                                dotnet_root = os.environ.get("DOTNET_ROOT")
                                if dotnet_root:
                                    common_paths.insert(0, Path(dotnet_root) / "dotnet")
                                    common_paths.insert(1, Path(dotnet_root))
                                for path in common_paths:
                                    path_obj = Path(path)
                                    if path_obj.exists() and path_obj.is_file():
                                        success, stdout, _ = self.run_command(
                                            [str(path), "--version"],
                                            check=False,
                                            capture=True,
                                        )
                                        if success and stdout:
                                            version = stdout.strip()
                                            if self._is_version_sufficient(version):
                                                self.log(
                                                    f".NET SDK found at {path}: {version} - using installed version",
                                                    "success",
                                                )
                                                return True
                                # Package is installed but dotnet command not accessible
                                self.log(
                                    ".NET SDK package is installed but 'dotnet' command not found in PATH",
                                    "warning",
                                )
                                self.log(
                                    "You may need to add the dotnet directory to your PATH or restart your terminal",
                                    "info",
                                )
                                return True  # Return True anyway since package is installed

        return False

    def ensure_patcher_files(self, silent=False):
        """Ensure AffinityPatcher and ReturnColors files are available in .AffinityLinux/Patch/

        One at a time: the startup background task and One-Click Setup both
        call this, and two concurrent git clones into one directory made the
        second fail ("could not lock config file") and fall back to the ZIP.
        The second caller now waits and finds the files already there."""
        with _PATCHER_FILES_LOCK:
            return self._ensure_patcher_files(silent)

    def _ensure_patcher_files(self, silent=False):
        try:
            # Destination: .AffinityLinux/Patch/AffinityPatcherSettings/
            dest_patch_dir = Path(self.directory) / "Patch" / "AffinityPatcherSettings"
            dest_patch_dir.mkdir(parents=True, exist_ok=True)

            # Files to copy/download
            files_to_get = {
                "AffinityPatcher.cs": "https://raw.githubusercontent.com/ryzendew/AffinityOnLinux/main/Patch/AffinityPatcherSettings/AffinityPatcher.cs",
                "AffinityPatcher.csproj": "https://raw.githubusercontent.com/ryzendew/AffinityOnLinux/main/Patch/AffinityPatcherSettings/AffinityPatcher.csproj",
            }

            # First, try to copy from local repository if available
            root = checkout_root()
            source_patch_dir = ((root / "Patch" / "AffinityPatcherSettings")
                                if root else None)

            files_copied = False
            files_downloaded = False
            all_exist = True

            for filename, github_url in files_to_get.items():
                dest_file = dest_patch_dir / filename

                # Check if file already exists and is valid
                if dest_file.exists():
                    # File already exists, skip
                    continue

                # Try to copy from local repository first. There is no local
                # repository at all for the piped install, which is the
                # documented one -- source_patch_dir is None there, and
                # None / filename raises into this method's own except Exception,
                # taking the download below with it.
                source_file = (source_patch_dir / filename) if source_patch_dir else None
                if source_file is not None and source_file.exists():
                    try:
                        shutil.copy2(source_file, dest_file)
                        files_copied = True
                        if not silent:
                            self.log(
                                f"Copied {filename} to .AffinityLinux/Patch/AffinityPatcherSettings/",
                                "info",
                            )
                        continue
                    except Exception as e:
                        if not silent:
                            self.log(
                                f"Failed to copy {filename} from local: {e}", "warning"
                            )

                # If local copy failed or doesn't exist, download from GitHub
                if not dest_file.exists():
                    if not silent:
                        self.log(f"Downloading {filename} from GitHub...", "info")
                    try:
                        if self.download_file(github_url, str(dest_file), filename):
                            files_downloaded = True
                            if not silent:
                                self.log(
                                    f"Downloaded {filename} to .AffinityLinux/Patch/AffinityPatcherSettings/",
                                    "success",
                                )
                        else:
                            all_exist = False
                            if not silent:
                                self.log(f"Failed to download {filename}", "error")
                    except Exception as e:
                        all_exist = False
                        if not silent:
                            self.log(f"Error downloading {filename}: {e}", "error")

            # Final check - verify all files exist
            for filename in files_to_get.keys():
                dest_file = dest_patch_dir / filename
                if not dest_file.exists():
                    all_exist = False

            # Download ReturnColors from GitHub (still in Patch/ directory, not in AffinityPatcherSettings/)
            returncolors_dest = (
                Path(self.directory) / "Patch" / "return-affinity-colors"
            )
            returncolors_repo = (
                "https://github.com/ShawnTheBeachy/return-affinity-colors.git"
            )

            # Check if ReturnColors project folder exists (it's inside return-affinity-colors/ReturnColors/)
            returncolors_project_exists = (
                returncolors_dest.exists()
                and (returncolors_dest / "ReturnColors").exists()
                and (
                    returncolors_dest / "ReturnColors" / "ReturnColors.csproj"
                ).exists()
            )

            if not returncolors_project_exists:
                if not silent:
                    self.log("Downloading ReturnColors from GitHub...", "info")

                # Try git clone first (preferred method)
                if self.check_command("git"):
                    try:
                        # Remove existing directory if it exists but is incomplete
                        if returncolors_dest.exists():
                            shutil.rmtree(returncolors_dest)

                        # Clone the repository
                        success, stdout, stderr = self.run_command(
                            [
                                "git",
                                "clone",
                                "--depth",
                                "1",
                                returncolors_repo,
                                str(returncolors_dest),
                            ],
                            check=False,
                            capture=True,
                        )

                        if success:
                            if not silent:
                                self.log(
                                    "ReturnColors downloaded from GitHub via git",
                                    "success",
                                )
                        else:
                            if not silent:
                                self.log(
                                    f"Git clone failed: {stderr[:200] if stderr else 'Unknown error'}",
                                    "warning",
                                )
                            # Fall through to zip download
                            if returncolors_dest.exists():
                                shutil.rmtree(returncolors_dest)
                    except Exception as e:
                        if not silent:
                            self.log(f"Error cloning ReturnColors: {e}", "warning")
                        if returncolors_dest.exists():
                            try:
                                shutil.rmtree(returncolors_dest)
                            except:
                                pass

                # Fallback: Download as zip and extract
                if not returncolors_project_exists:
                    try:
                        # Download zip from GitHub
                        zip_url = "https://github.com/ShawnTheBeachy/return-affinity-colors/archive/refs/heads/main.zip"
                        temp_zip = tempfile.NamedTemporaryFile(
                            delete=False, suffix=".zip"
                        )
                        temp_zip_path = Path(temp_zip.name)
                        temp_zip.close()

                        if not silent:
                            self.log(
                                "Downloading ReturnColors as ZIP from GitHub...", "info"
                            )

                        if self.download_file(
                            zip_url, str(temp_zip_path), "ReturnColors ZIP"
                        ):
                            # Extract zip
                            with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
                                # Extract to a temp directory first
                                temp_extract = dest_patch_dir / ".temp_returncolors"
                                if temp_extract.exists():
                                    shutil.rmtree(temp_extract)
                                temp_extract.mkdir(exist_ok=True)
                                zip_ref.extractall(temp_extract)

                                # Move the extracted folder to the correct location
                                extracted_folder = (
                                    temp_extract / "return-affinity-colors-main"
                                )
                                if extracted_folder.exists():
                                    if returncolors_dest.exists():
                                        shutil.rmtree(returncolors_dest)
                                    extracted_folder.rename(returncolors_dest)

                                # Clean up temp directory
                                if temp_extract.exists():
                                    try:
                                        shutil.rmtree(temp_extract)
                                    except:
                                        pass

                            # Clean up zip file
                            temp_zip_path.unlink()

                            # Verify the structure is correct
                            if (
                                returncolors_dest.exists()
                                and (returncolors_dest / "ReturnColors").exists()
                                and (
                                    returncolors_dest
                                    / "ReturnColors"
                                    / "ReturnColors.csproj"
                                ).exists()
                            ):
                                if not silent:
                                    self.log(
                                        "ReturnColors downloaded and extracted from GitHub",
                                        "success",
                                    )
                            else:
                                if not silent:
                                    self.log(
                                        "ReturnColors extraction failed - folder structure not found",
                                        "warning",
                                    )
                                # Try to find the correct structure
                                if returncolors_dest.exists():
                                    # Check if ReturnColors folder is at the root
                                    if (
                                        returncolors_dest / "ReturnColors.csproj"
                                    ).exists():
                                        # The zip might have extracted differently, move files
                                        pass  # Structure is already correct
                        else:
                            if not silent:
                                self.log(
                                    "Failed to download ReturnColors ZIP from GitHub",
                                    "warning",
                                )
                    except Exception as e:
                        if not silent:
                            self.log(f"Error downloading ReturnColors: {e}", "warning")
            elif not silent:
                self.log("ReturnColors already exists in .AffinityLinux/Patch/", "info")

            if files_copied and not silent:
                self.log("Patcher files are ready in .AffinityLinux/Patch/", "success")
            elif files_downloaded and not silent:
                self.log(
                    "Patcher files downloaded and ready in .AffinityLinux/Patch/",
                    "success",
                )
            elif not all_exist and not silent:
                self.log("Some patcher files are missing", "warning")

            return all_exist
        except Exception as e:
            if not silent:
                self.log(f"Error ensuring patcher files: {e}", "error")
            return False

    def build_affinity_patcher(self):
        """Build the AffinityPatcher .NET project"""
        # Use Patch/AffinityPatcherSettings directory from .AffinityLinux (ensured to be available)
        patch_dir = Path(self.directory) / "Patch" / "AffinityPatcherSettings"

        if not patch_dir.exists():
            self.log(
                f"AffinityPatcherSettings directory not found: {patch_dir}", "error"
            )
            return None

        csproj_file = patch_dir / "AffinityPatcher.csproj"
        if not csproj_file.exists():
            self.log(f"AffinityPatcher.csproj not found: {csproj_file}", "error")
            return None

        self.log(f"Building AffinityPatcher from: {patch_dir}", "info")

        # Build the project - use absolute path and prevent building project references
        # Output directory is within the AffinityPatcherSettings folder
        output_dir = patch_dir / "bin" / "Release"
        # Use --no-incremental for clean build and -p:BuildProjectReferences=false to prevent building other projects
        # Also use absolute path to ensure we're building the correct project
        # The issue is that MSBuild might be picking up files from return-affinity-colors subdirectory
        # So we explicitly build only the project file and disable project references
        csproj_absolute = csproj_file.resolve()
        success, stdout, stderr = self.run_command(
            [
                "dotnet",
                "build",
                str(csproj_absolute),
                "-c",
                "Release",
                "-o",
                str(output_dir.resolve()),
                "--no-incremental",
                "-p:BuildProjectReferences=false",
                "/p:DisableImplicitNuGetFallbackFolder=true",
            ],
            check=False,
            capture=True,
        )

        if not success:
            self.log(f"Failed to build AffinityPatcher: {stderr}", "error")
            if stdout:
                self.log(f"Build output: {stdout}", "warning")
            return None

        # Find the built executable - .NET can create different output formats
        # Try common output names
        possible_names = [
            "AffinityPatcher",  # Native executable (Linux)
            "AffinityPatcher.dll",  # DLL (runnable with dotnet)
            "AffinityPatcher.exe",  # Windows executable (unlikely on Linux)
        ]

        patcher_exe = None
        for name in possible_names:
            candidate = output_dir / name
            if candidate.exists():
                patcher_exe = candidate
                break

        if patcher_exe and patcher_exe.exists():
            self.log(f"AffinityPatcher built successfully: {patcher_exe}", "success")
            return patcher_exe
        else:
            # List what's actually in the output directory for debugging
            if output_dir.exists():
                files = list(output_dir.glob("*"))
                self.log(
                    f"Files in output directory: {[f.name for f in files]}", "warning"
                )
            self.log(
                f"Built patcher not found at expected location: {output_dir}", "error"
            )
            return None

    def run_affinity_patcher(self, dll_path):
        """Run the AffinityPatcher on the specified DLL"""
        if not Path(dll_path).exists():
            self.log(f"DLL not found: {dll_path}", "error")
            return False

        # Build the patcher if needed
        patcher_exe = self.build_affinity_patcher()
        if not patcher_exe:
            self.log("Failed to build AffinityPatcher", "error")
            return False

        self.log(f"Running AffinityPatcher on: {dll_path}", "info")

        # Run the patcher - use dotnet for DLLs, direct execution for native executables
        if patcher_exe.suffix == ".dll":
            cmd = ["dotnet", str(patcher_exe), dll_path]
        else:
            cmd = [str(patcher_exe), dll_path]

        success, stdout, stderr = self.run_command(cmd, check=False, capture=True)

        if success:
            self.log("AffinityPatcher completed successfully", "success")
            if stdout:
                # Log the patcher output
                for line in stdout.strip().split("\n"):
                    if line.strip():
                        if "SUCCESS" in line or "success" in line.lower():
                            self.log(line, "success")
                        elif "ERROR" in line or "error" in line.lower():
                            self.log(line, "error")
                        else:
                            self.log(line, "info")
            return True
        else:
            self.log(f"AffinityPatcher failed: {stderr}", "error")
            if stdout:
                self.log(f"Output: {stdout}", "warning")
            return False

    def build_return_colors(self):
        """Build the ReturnColors .NET project"""
        # Use Patch directory from .AffinityLinux
        patch_dir = Path(self.directory) / "Patch"
        # ReturnColors is downloaded from GitHub, so it's in return-affinity-colors/ReturnColors/
        returncolors_repo_dir = patch_dir / "return-affinity-colors"
        returncolors_dir = returncolors_repo_dir / "ReturnColors"

        # Also check the old location for backwards compatibility
        if not returncolors_dir.exists():
            old_returncolors_dir = patch_dir / "ReturnColors"
            if old_returncolors_dir.exists():
                returncolors_dir = old_returncolors_dir

        if not returncolors_dir.exists():
            self.log(f"ReturnColors directory not found: {returncolors_dir}", "warning")
            self.log("Attempting to download ReturnColors from GitHub...", "info")
            # Try to ensure it's downloaded
            self.ensure_patcher_files(silent=True)
            # Check again after download attempt
            returncolors_repo_dir = patch_dir / "return-affinity-colors"
            returncolors_dir = returncolors_repo_dir / "ReturnColors"
            if not returncolors_dir.exists():
                old_returncolors_dir = patch_dir / "ReturnColors"
                if old_returncolors_dir.exists():
                    returncolors_dir = old_returncolors_dir
            if not returncolors_dir.exists():
                self.log(
                    f"ReturnColors directory still not found after download attempt",
                    "error",
                )
                return None

        csproj_file = returncolors_dir / "ReturnColors.csproj"
        if not csproj_file.exists():
            self.log(f"ReturnColors.csproj not found: {csproj_file}", "warning")
            return None

        self.log(f"Building ReturnColors from: {returncolors_dir}", "info")

        # Build the project
        output_dir = returncolors_dir / "bin" / "Release"
        success, stdout, stderr = self.run_command(
            [
                "dotnet",
                "build",
                str(csproj_file),
                "-c",
                "Release",
                "-o",
                str(output_dir),
            ],
            check=False,
            capture=True,
        )

        if not success:
            self.log(f"Failed to build ReturnColors: {stderr}", "warning")
            if stdout:
                self.log(f"Build output: {stdout}", "warning")
            return None

        # Find the built executable
        possible_names = [
            "ReturnColors",  # Native executable (Linux)
            "ReturnColors.dll",  # DLL (runnable with dotnet)
            "ReturnColors.exe",  # Windows executable (unlikely on Linux)
        ]

        returncolors_exe = None
        for name in possible_names:
            candidate = output_dir / name
            if candidate.exists():
                returncolors_exe = candidate
                break

        if returncolors_exe and returncolors_exe.exists():
            self.log(f"ReturnColors built successfully: {returncolors_exe}", "success")
            return returncolors_exe
        else:
            if output_dir.exists():
                files = list(output_dir.glob("*"))
                self.log(
                    f"Files in output directory: {[f.name for f in files]}", "warning"
                )
            self.log(
                f"Built ReturnColors not found at expected location: {output_dir}",
                "warning",
            )
            return None

    def run_return_colors_colorize(self, affinity_dir):
        """Run ReturnColors colorize command to restore colored icons"""
        if not Path(affinity_dir).exists():
            self.log(f"Affinity directory not found: {affinity_dir}", "warning")
            return False

        # Build ReturnColors if needed
        returncolors_exe = self.build_return_colors()
        if not returncolors_exe:
            self.log("ReturnColors not available, skipping icon colorization", "info")
            return False

        self.log("Running ReturnColors to restore colored icons...", "info")

        # Run ReturnColors colorize command
        # The command expects: colorize <directory>
        if returncolors_exe.suffix == ".dll":
            cmd = ["dotnet", str(returncolors_exe), "colorize", str(affinity_dir)]
        else:
            cmd = [str(returncolors_exe), "colorize", str(affinity_dir)]

        success, stdout, stderr = self.run_command(cmd, check=False, capture=True)

        if success:
            self.log("ReturnColors colorize completed successfully", "success")
            if stdout:
                # Log the output
                for line in stdout.strip().split("\n"):
                    if line.strip():
                        if "success" in line.lower() or "completed" in line.lower():
                            self.log(line, "success")
                        elif "error" in line.lower() or "failed" in line.lower():
                            self.log(line, "error")
                        else:
                            self.log(line, "info")
            return True
        else:
            self.log(f"ReturnColors colorize failed: {stderr}", "warning")
            if stdout:
                self.log(f"Output: {stdout}", "warning")
            return False

    def patch_affinity_dll(self, app_name):
        """Patch the Serif.Affinity.dll for Affinity v3 (Unified)"""
        # Only patch Affinity v3 (Unified)
        if app_name != "Add" and app_name != "Affinity (Unified)":
            return True  # Not applicable, return success

        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Patching Affinity DLL for settings fix...", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Ensure patcher files (including ReturnColors) are available
        self.ensure_patcher_files(silent=True)

        # Check if .NET SDK is available, try to install if missing
        if not self.check_dotnet_sdk():
            self.log(".NET SDK not found. Attempting to install...", "info")
            if not self.install_dotnet_sdk():
                self.log("Failed to install .NET SDK automatically", "warning")
                self.log("Settings patching will be skipped.", "warning")
                self.log("You can install .NET SDK manually:", "info")
                if self.distro in ["arch", "cachyos"]:
                    self.log("  sudo pacman -S dotnet-sdk-8.0", "info")
                elif self.distro in ["endeavouros", "xerolinux"]:
                    self.log("  sudo pacman -S dotnet-sdk-8.0", "info")
                elif self.distro in ["fedora", "nobara"]:
                    self.log("  sudo dnf install dotnet-sdk-8.0", "info")
                elif self.distro in ["pikaos", "pop", "debian"]:
                    self.log("  sudo apt install dotnet-sdk-8.0", "info")
                    self.log("  (May require Microsoft's .NET repository)", "warning")
                elif self.distro in ["opensuse-tumbleweed", "opensuse-leap"]:
                    self.log("  sudo zypper install dotnet-sdk-8.0", "info")
                return False
            else:
                self.log(".NET SDK installed successfully", "success")

        # Find the DLL
        dll_path = (
            Path(self.directory)
            / "drive_c"
            / "Program Files"
            / "Affinity"
            / "Affinity"
            / "Serif.Affinity.dll"
        )

        if not dll_path.exists():
            self.log(f"Serif.Affinity.dll not found at: {dll_path}", "warning")
            self.log(
                "The DLL may not be installed yet. Patching will be skipped.", "warning"
            )
            return False

        # Run the settings patcher
        return self.run_affinity_patcher(str(dll_path))

    def _mimeapps_path(self):
        return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "mimeapps.list"

    def _run_uncancellable(self, command):
        """Run a short command (xdg-mime, update-desktop-database, wine --version).

        It does not use run_command, which returns early while an earlier operation's
        cancel flag is still set.
        """
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
            return result.returncode == 0, result.stdout, result.stderr
        except (OSError, subprocess.SubprocessError) as e:
            return False, "", str(e)

    @staticmethod
    def _mimeapps_key(line):
        """Return the key of a mimeapps.list entry line, or None"""
        key, sep, _ = line.partition("=")
        return key.strip() if sep else None

    def get_default_url_handler(self, scheme):
        """Return the desktop file set as default for a URL scheme, or None"""
        mime_type = f"x-scheme-handler/{scheme}"
        if self.check_command("xdg-mime"):
            success, stdout, _ = self._run_uncancellable(["xdg-mime", "query", "default", mime_type])
            if success:
                return stdout.strip() or None
        try:
            section = None
            for line in self._mimeapps_path().read_text(encoding="utf-8-sig").splitlines():
                stripped = line.strip()
                if stripped.startswith("["):
                    section = stripped
                elif section == "[Default Applications]" and self._mimeapps_key(stripped) == mime_type:
                    return stripped.partition("=")[2].split(";")[0].strip() or None
        except (OSError, UnicodeError):
            pass
        return None

    def _write_mimeapps_default(self, mime_type, desktop_name, remove=None):
        """Put desktop_name first in one [Default Applications] entry, or drop `remove` from it.

        Other desktop files listed in that entry and the rest of the file are kept.
        """
        mimeapps = self._mimeapps_path()
        try:
            if not mimeapps.exists():
                if not desktop_name:
                    return True
                raw = ""
            else:
                raw = mimeapps.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as e:
            self.log(f"Could not read {mimeapps}: {e}", "warning")
            return False
        bom = raw.startswith("﻿")
        lines = raw.lstrip("﻿").splitlines()

        # Desktop files already listed for mime_type in [Default Applications].
        section, listed = None, []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("["):
                section = stripped
            elif section == "[Default Applications]" and self._mimeapps_key(stripped) == mime_type:
                listed += [name.strip() for name in stripped.partition("=")[2].split(";") if name.strip()]
        dropped = {desktop_name, remove} - {None}
        values = ([desktop_name] if desktop_name else []) + [
            name for i, name in enumerate(listed) if name not in dropped and name not in listed[:i]
        ]
        entry = f"{mime_type}={';'.join(values)};" if values else None

        output, section, written, in_defaults_seen = [], None, False, False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("["):
                if section == "[Default Applications]" and entry and not written:
                    output.append(entry)
                    written = True
                section = stripped
                in_defaults_seen = in_defaults_seen or section == "[Default Applications]"
            elif section == "[Default Applications]" and self._mimeapps_key(stripped) == mime_type:
                if entry and not written:
                    output.append(entry)
                    written = True
                continue
            output.append(line)
        if entry and not written:
            if not in_defaults_seen or section != "[Default Applications]":
                output.append("[Default Applications]")
            output.append(entry)

        try:
            target = mimeapps.resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            staged = target.with_name(target.name + ".tmp")
            staged.write_text(("﻿" if bom else "") + "\n".join(output) + "\n", encoding="utf-8")
            if target.exists():
                shutil.copymode(target, staged)
            os.replace(staged, target)
            return True
        except (OSError, RuntimeError) as e:
            self.log(f"Could not update {mimeapps}: {e}", "warning")
            return False

    def _set_default_url_handler(self, scheme, desktop_name):
        """Set the default handler for a URL scheme"""
        mime_type = f"x-scheme-handler/{scheme}"
        if self.check_command("xdg-mime"):
            success, _, stderr = self._run_uncancellable(["xdg-mime", "default", desktop_name, mime_type])
            if success:
                return True
            self.log(f"xdg-mime failed ({stderr.strip()}), editing mimeapps.list directly", "warning")
        return self._write_mimeapps_default(mime_type, desktop_name)

    def _affinity_url_handler_exec(self):
        """Return the Exec= line for the affinity:// handler.

        It reuses the Exec= line of Affinity.desktop when that runs Wine directly, so a
        cold start through the handler matches the desktop entry. Otherwise, for example
        with the Ubuntu Snapshot launcher script, it builds the equivalent command.
        """
        desktop_file = Path.home() / ".local" / "share" / "applications" / "Affinity.desktop"
        try:
            for line in desktop_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("Exec=") and re.search(r'(Affinity|AffinityHook)\.exe"\s*$', line):
                    return line.rstrip()
        except (OSError, UnicodeError):
            pass
        exec_line, _ = self._build_affinity_exec_line(prefer_hook=True)
        return exec_line

    def winmetadata_installed(self):
        """Return True when the prefix has WinMetadata (.winmd files) in system32."""
        # Wine creates the directory lowercase; previously this checked "WinMetadata"
        # and never matched on a case-sensitive filesystem.
        for dirname in ("winmetadata", "WinMetadata"):
            winmetadata = Path(self.directory) / "drive_c" / "windows" / "system32" / dirname
            try:
                if any(winmetadata.glob("*.winmd")):
                    return True
            except OSError:
                continue
        return False

    def offer_after_install(self):
        """Called after the closing message of an Affinity install. Nothing to
        offer when the installer runs by itself: it writes the menu entry for
        the prefix it installed. The manager offers to make the new prefix its
        Default, the one the menu and double-clicked documents start."""

    def launch_instructions(self):
        """How to start what was just installed, for the closing message.

        Run on its own, this installer writes the menu entry. A caller that
        keeps its own entries (manages_host_entries) says where to start it
        instead."""
        return "You can now launch it from your application menu."

    def manages_host_entries(self):
        """Whether this installer writes the host's fixed-name entries.

        Affinity.desktop, the desktop icon and affinity-url-handler.desktop
        have one name each, so every install rewrites the last one's: setting
        up a second prefix took the menu entry, document double-click and the
        Canva sign-in away from the prefix being worked in. A caller that keeps
        its own entries -- the prefix manager -- overrides this to say so, and
        then none of them are written or removed here, and Wine's menu builder
        is kept from adding entries while Affinity's installer runs."""
        return True

    def _entry_serves_this_prefix(self, entry):
        """Does this .desktop file launch this prefix? False when unreadable."""
        try:
            text = Path(entry).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        prefix = str(Path(self.directory)).rstrip("/")
        return any(f"WINEPREFIX={q}{prefix}{tail}" in text
                   for q in ("", '"', "'") for tail in (" ", '"', "'", "/"))

    def create_affinity_url_handler(self):
        """Register the affinity:// handler that completes the Canva sign-in.

        The browser hands the sign-in callback to this handler. It launches Affinity with
        the URL, and a running Affinity receives it from that second instance over a named
        pipe. It is only registered on supported Wine (11.18 or 11.19 with login
        metadata) and once WinMetadata and the WinRT facades are installed: otherwise the running Affinity crashes when the URL
        arrives. Wine's generated handler is replaced because it runs `wine start`, which
        crashes on URLs longer than about 300 characters.
        """
        if not self.manages_host_entries():
            return False
        if not self.affinity_v3_exe_path().exists():
            return False
        desktop_dir = Path.home() / ".local" / "share" / "applications"
        handler_file = desktop_dir / self.AFFINITY_URL_HANDLER

        wine_support = self.canva_sign_in_wine_support()
        if wine_support != "supported":
            if wine_support == "unknown":
                self.log("Could not run the prefix's Wine, not changing the affinity:// handler", "warning")
                return False
            # A handler left from an earlier Wine version would crash the running Affinity.
            if handler_file.exists():
                self.remove_affinity_url_handler()
            self.log("Not registering the affinity:// handler: the Canva sign-in fix supports Wine 11.18 and 11.19 with login metadata", "info")
            return False
        if not self.windowsruntime_facades_installed() or not self.winmetadata_installed():
            self.log("WinRT facades or WinMetadata missing, not registering the affinity:// handler", "warning")
            return False

        # Ask before writing our desktop file, so it cannot be the query's fallback answer.
        current = self.get_default_url_handler("affinity")
        if current not in (None, handler_file.name, "wine-protocol-affinity.desktop"):
            self.log(
                f"affinity:// is handled by {current}; leaving it. For the Canva sign-in in this "
                "prefix, remove that default and use Troubleshooting > Fix Canva Sign-in (v3)",
                "warning",
            )
            return False

        try:
            desktop_dir.mkdir(parents=True, exist_ok=True)
            with open(handler_file, "w", encoding="utf-8") as f:
                f.write("[Desktop Entry]\n")
                f.write("Type=Application\n")
                f.write("Name=Affinity sign-in handler\n")
                f.write(f"{self._affinity_url_handler_exec()} %u\n")
                f.write("MimeType=x-scheme-handler/affinity;\n")
                f.write("NoDisplay=true\n")
                f.write("Terminal=false\n")
        except OSError as e:
            self.log(f"Could not write {handler_file}: {e}", "warning")
            return False

        if self.check_command("update-desktop-database"):
            self._run_uncancellable(["update-desktop-database", str(desktop_dir)])

        # Set it even when the query already names this handler: the query can fall back
        # to any installed handler when mimeapps.list has no valid entry.
        if not self._set_default_url_handler("affinity", handler_file.name):
            return False
        wine_protocol_entry = desktop_dir / "wine-protocol-affinity.desktop"
        try:
            if wine_protocol_entry.exists():
                wine_protocol_entry.unlink()
        except OSError:
            pass
        if current != handler_file.name:
            self.log("Registered the affinity:// handler used by the Canva sign-in", "success")
        return True

    def repair_affinity_url_protocol_command(self):
        """Point HKCR\\affinity at the real v3 exe (fallback handoff path).

        Affinity registers "C:\\Program Files\\Affinity\\Affinity.exe", but the v3
        install lives one level deeper (...\\Affinity\\Affinity\\Affinity.exe), so
        `wine start <affinity://-url>` fails and the browser handoff dies wherever
        no desktop handler catches it first. The installer's own desktop handler
        launches the exe directly and does not need this key.
        """
        exe = self.affinity_v3_exe_path()
        if not exe.exists():
            return False
        try:
            drive_c = Path(self.directory) / "drive_c"
            windows_path = "C:\\" + str(exe.relative_to(drive_c)).replace("/", "\\")
        except (OSError, ValueError):
            return False
        env = self.get_winetricks_env()
        wine = self.get_wine_path("wine")
        success, _, stderr = self.run_command(
            [str(wine), "reg", "add", "HKEY_CLASSES_ROOT\\affinity\\shell\\open\\command",
             "/ve", "/d", f'"{windows_path}" "%1"', "/f"],
            check=False, env=env, capture=True,
        )
        if success:
            self.log("affinity:// protocol handler points at the v3 exe", "success")
            return True
        self.log(f"Could not fix the affinity:// protocol command: {(stderr or '').strip() or 'unknown error'}", "warning")
        return False

    def remove_affinity_url_handler(self):
        """Remove the affinity:// handler and its default-handler entry -- but
        only one that launches this prefix. Another prefix's handler is that
        prefix's Canva sign-in, and this one has no business removing it."""
        if not self.manages_host_entries():
            return
        desktop_dir = Path.home() / ".local" / "share" / "applications"
        handler_file = desktop_dir / self.AFFINITY_URL_HANDLER
        if handler_file.exists() and not self._entry_serves_this_prefix(handler_file):
            self.log(f"Leaving {handler_file.name}: it serves another prefix", "info")
            return
        try:
            # Query before deleting: xdg-mime ignores defaults whose desktop file is gone.
            is_default = self.get_default_url_handler("affinity") == handler_file.name
            if handler_file.exists():
                handler_file.unlink()
                self.log(f"Removed {handler_file.name}", "info")
            if is_default:
                self._write_mimeapps_default("x-scheme-handler/affinity", None, remove=handler_file.name)
            if self.check_command("update-desktop-database"):
                self._run_uncancellable(["update-desktop-database", str(desktop_dir)])
        except Exception as e:
            self.log(f"Could not remove the affinity:// handler: {e}", "warning")

    def snapshot_launcher_applies(self):
        """The Ubuntu Snapshot launcher is one setup's workaround: an Ubuntu-family
        system with an NVIDIA driver, and the default prefix -- its script
        launches ~/.AffinityLinux whatever was installed. Elsewhere it made the
        menu entry start the wrong prefix, without the document it was asked to
        open, under NVIDIA-specific Vulkan settings."""
        if Path(self.directory).expanduser() != Path.home() / ".AffinityLinux":
            return False
        if not Path("/proc/driver/nvidia/version").exists():
            return False
        try:
            release = Path("/etc/os-release").read_text().lower()
        except OSError:
            return False
        ids = " ".join(line.split("=", 1)[1].strip('"') for line in release.splitlines()
                       if line.startswith(("id=", "id_like=")))
        return "ubuntu" in ids.split()

    def create_desktop_entry(self, app_name):
        """Create desktop entry for application"""
        if not self.manages_host_entries():
            self.log("Menu entries for this prefix are kept by the manager, not written here", "info")
            return
        if app_name == "Add" and self.snapshot_launcher_applies():
            snapshot_script = self.get_ubuntu_snapshot_launcher_script(require_exists=False)
            if snapshot_script.exists():
                if self.install_ubuntu_snapshot_launchers(show_dialog=False):
                    self.log("Unified Affinity desktop entry now uses the Ubuntu Snapshot launcher", "info")
                    self.create_affinity_url_handler()
                    return
                self.log("Ubuntu Snapshot launcher installation failed, falling back to the built-in desktop entry writer", "warning")

        app_names = {
            "Photo": ("Photo", "Photo.exe", "Photo 2", "AffinityPhoto.svg"),
            "Designer": (
                "Designer",
                "Designer.exe",
                "Designer 2",
                "AffinityDesigner.svg",
            ),
            "Publisher": (
                "Publisher",
                "Publisher.exe",
                "Publisher 2",
                "AffinityPublisher.svg",
            ),
            "Add": ("Affinity", "Affinity.exe", "Affinity", "Affinity.svg"),
        }

        name, exe, dir_name, icon = app_names.get(
            app_name, ("Affinity", "Affinity.exe", "Affinity", "Affinity.svg")
        )

        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)

        desktop_file = desktop_dir / f"Affinity{name}.desktop"
        if app_name == "Add":
            desktop_file = desktop_dir / "Affinity.desktop"

        wine = self.get_wine_path("wine")
        app_path = (
            Path(self.directory)
            / "drive_c"
            / "Program Files"
            / "Affinity"
            / dir_name
            / exe
        )
        icon_path = Path.home() / ".local" / "share" / "icons" / icon

        # Normalize all paths to strings to avoid double slashes
        wine_str = str(wine)
        directory_str = str(self.directory).rstrip(
            "/"
        )  # Remove trailing slash if present
        icon_path_str = str(icon_path)
        app_path_str = str(app_path).replace("\\", "/")  # Ensure forward slashes, no double slashes

        # Launch through affinity-on-linux.exe when it is installed, so documents
        # can be opened from the file manager. Wine converts argv[0] to a DOS path
        # but passes arguments through verbatim, so something inside the prefix has
        # to turn the Unix path a file manager hands over into one Affinity can
        # open; the handler also serialises concurrent double-clicks and picks the
        # warm or cold route. Without it the entry is unchanged.
        handler_path = app_path.parent / "affinity-on-linux.exe"
        # Both conditions matter: the handler has to be there, and the Wine build
        # has to be able to act on a document once the handler forwards it.
        # Checked here as well as at install time so that switching to a build
        # without the support gives the association up again.
        has_handler = handler_path.exists() and self.wine_resolves_winrt_namespaces()
        if has_handler:
            app_path_str = str(handler_path).replace("\\", "/")

        desktop_env_parts = self.get_desktop_launch_env_parts()
        launch_prefix = self.get_gpu_launch_prefix()

        with open(desktop_file, "w") as f:
            f.write("[Desktop Entry]\n")
            if app_name == "Add":
                f.write("Name=Affinity Suite\n")
                f.write("Comment=A powerful creative suite.\n")
            else:
                f.write(f"Name=Affinity {name}\n")
                f.write(f"Comment=A powerful {name.lower()} software.\n")
            f.write(f"Icon={icon_path_str}\n")
            f.write(f"Path={directory_str}\n")
            # Use Linux path format with proper quoting for spaces
            # Include GPU environment variables if configured
            exec_parts = ["Exec="]
            if launch_prefix:
                exec_parts.append(" ".join(shlex.quote(part) for part in launch_prefix))
            exec_parts.append(f"env WINEPREFIX={directory_str}")
            exec_parts.extend(desktop_env_parts)
            exec_parts.append(wine_str)
            exec_parts.append(f'"{app_path_str}"')
            # %F, not %f: the file manager then hands every selected document to
            # one invocation instead of racing one process per file.
            if has_handler:
                exec_parts.append("%F")
            f.write(" ".join(exec_parts) + "\n")
            f.write("Terminal=false\n")
            f.write("Type=Application\n")
            f.write("Categories=Graphics;\n")
            f.write("StartupNotify=true\n")
            if app_name == "Add":
                f.write("StartupWMClass=affinity.exe\n")
            else:
                f.write(f"StartupWMClass={name.lower()}.exe\n")
            # Only claim the document types when the handler is there to open
            # them. Without it a double-click would hand Affinity a Unix path it
            # cannot resolve, which looks like the association is broken.
            if has_handler:
                mime_types = {
                    "Photo": "application/afphoto;",
                    "Designer": "application/afdesign;",
                    "Publisher": "application/afpub;",
                }.get(
                    app_name,
                    "application/af;application/afphoto;"
                    "application/afdesign;application/afpub;",
                )
                f.write(f"MimeType={mime_types}\n")

        # Remove Wine's default entry
        wine_entry = desktop_dir / "wine" / "Programs" / f"Affinity {name} 2.desktop"
        if wine_entry.exists():
            wine_entry.unlink()

        if app_name == "Add":
            wine_entry = desktop_dir / "wine" / "Programs" / "Affinity.desktop"
            if wine_entry.exists():
                wine_entry.unlink()

        # Remove duplicate wine-protocol-affinity.desktop file
        wine_protocol_entry = desktop_dir / "wine-protocol-affinity.desktop"
        if wine_protocol_entry.exists():
            try:
                wine_protocol_entry.unlink()
                self.log("Removed duplicate wine-protocol-affinity.desktop", "info")
            except Exception as e:
                self.log(
                    f"Warning: Could not remove wine-protocol-affinity.desktop: {e}",
                    "warning",
                )

        if app_name == "Add":
            # After Affinity.desktop is written, so the handler reuses its Exec= line.
            self.create_affinity_url_handler()

        # Create desktop shortcut
        desktop_shortcut = Path.home() / "Desktop" / desktop_file.name
        if desktop_shortcut.parent.exists():
            try:
                shutil.copy2(desktop_file, desktop_shortcut)
                self.log("Desktop shortcut created", "success")
            except PermissionError:
                self.log(
                    f"Could not create desktop shortcut (permission denied): {desktop_shortcut}",
                    "warning",
                )
                self.log(
                    "Desktop entry is still available in the applications menu", "info"
                )
            except Exception as e:
                self.log(f"Could not create desktop shortcut: {e}", "warning")

        self.log(f"Desktop entry created: {desktop_file}", "success")

        if has_handler:
            self.register_document_types()

    def install_winrt_interop_facade(self):
        """Install System.Runtime.WindowsRuntime.dll into the prefix GAC.

        Without it Affinity starts normally but silently ignores a document
        handed to it -- no exception, nothing in the log, the file just never
        opens. It is the WinRT interop facade that supplies AsTask(), which
        Affinity awaits on SharedStorageAccessManager.RedeemTokenForFileAsync().

        It is missing by design, not by a broken install: the assembly ships
        inside the .NET Framework 4.8 redistributable, but only in the Windows
        8/10 payload cabs. On Windows 7 there is no WinRT, so the installer
        correctly skips it -- and winetricks' dotnet verbs set the prefix to
        win7, because on a real Windows 8+ the standalone installer refuses to
        run at all. Re-running it with the prefix reporting Windows 10 does not
        help either: it detects 4.8 and exits without doing anything. Extracting
        the file is the way.

        It must go in the GAC. Assemblies signed with the ECMA pseudo key carry
        no real signature and are trusted only because the GAC is trusted; from
        an application directory the CLR rejects the genuine file with
        "Strong name validation failed" (0x8013141A)."""
        gac_dir = (
            Path(self.directory)
            / "drive_c"
            / "windows"
            / "Microsoft.NET"
            / "assembly"
            / "GAC_MSIL"
            / "System.Runtime.WindowsRuntime"
            / "v4.0_4.0.0.0__b77a5c561934e089"
        )
        dest = gac_dir / "System.Runtime.WindowsRuntime.dll"
        if dest.exists():
            self.log("WinRT interop facade already installed", "success")
            return

        if not self.check_command("7z"):
            self.log(
                "7z is not installed, so the WinRT interop facade cannot be "
                "extracted; documents will not open from the file manager",
                "warning",
            )
            return

        ndp_url = (
            "https://download.visualstudio.microsoft.com/download/pr/"
            "7afca223-55d2-470a-8edc-6a1739ae3252/"
            "abd170b4b0ec15ad0222a809b761a036/ndp48-x86-x64-allos-enu.exe"
        )
        ndp_sha = "95889d6de3f2070c07790ad6cf2000d33d9a1bdfc6a381725ab82ab1c314fd53"
        # winetricks' dotnet48 verb caches the redistributable here, so an
        # install that already ran it does not download it twice.
        cache = Path.home() / ".cache" / "winetricks" / "dotnet48"
        ndp = cache / "ndp48-x86-x64-allos-enu.exe"

        try:
            if not ndp.exists():
                self.log("Downloading the .NET Framework 4.8 redistributable...", "info")
                cache.mkdir(parents=True, exist_ok=True)
                # 72MB, written into winetricks' own cache. Download beside it
                # and rename: urlretrieve straight onto the destination leaves a
                # partial file on a dropped connection, and every later run then
                # sees it exists, fails the same checksum, and refuses -- with no
                # way out but deleting it by hand.
                part = ndp.with_name(ndp.name + ".part")
                try:
                    with urllib.request.urlopen(ndp_url, timeout=300) as r, \
                         open(part, "wb") as f:
                        shutil.copyfileobj(r, f)
                    os.replace(str(part), str(ndp))
                finally:
                    if part.exists():
                        try:
                            part.unlink()
                        except OSError:
                            pass

            digest = hashlib.sha256(ndp.read_bytes()).hexdigest()
            if digest != ndp_sha:
                self.log(
                    "Checksum mismatch on the .NET redistributable; refusing to use it "
                    "and removing it, so the next run downloads it again rather than "
                    "failing the same way",
                    "error",
                )
                try:
                    ndp.unlink()
                except OSError:
                    pass
                return

            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                subprocess.run(
                    ["7z", "x", "-y", f"-o{tmp_path / 'ndp'}", str(ndp)],
                    check=True,
                    capture_output=True,
                )
                cabs = sorted((tmp_path / "ndp").glob("Windows10.0-KB*-x86.cab"))
                if not cabs:
                    self.log("No Windows 10 payload found in the redistributable", "error")
                    return

                listing = subprocess.run(
                    ["7z", "l", str(cabs[0])], check=True, capture_output=True, text=True
                ).stdout
                inner = None
                for line in listing.splitlines():
                    candidate = line.split()[-1] if line.split() else ""
                    if (
                        "msil_system.runtime.windowsruntime_b77a5c561934e089"
                        in candidate.lower()
                        and candidate.lower().endswith("system.runtime.windowsruntime.dll")
                    ):
                        inner = candidate
                        break
                if not inner:
                    self.log("Interop facade not found inside the payload", "error")
                    return

                subprocess.run(
                    ["7z", "e", "-y", f"-o{tmp_path / 'fac'}", str(cabs[0]), inner],
                    check=True,
                    capture_output=True,
                )
                extracted = tmp_path / "fac" / "system.runtime.windowsruntime.dll"
                if not extracted.is_file() or extracted.stat().st_size == 0:
                    self.log("Extracting the interop facade produced nothing", "error")
                    return

                gac_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(extracted, dest)

            self.log("WinRT interop facade installed", "success")
        except Exception as e:
            self.log(
                f"Could not install the WinRT interop facade: {e}. "
                "Documents will not open from the file manager.",
                "warning",
            )

    def install_file_manager_handler(self):
        """Put affinity-on-linux.exe in the prefix, beside Affinity.exe.

        This is what lets a document be opened from the file manager: Wine
        converts argv[0] to a DOS path but passes arguments through verbatim, so
        a file manager's /home/you/art.afphoto reaches Affinity unchanged and
        cannot be opened. See AffinityHandler/README.md."""
        install_dir = (
            Path(self.directory) / "drive_c" / "Program Files" / "Affinity" / "Affinity"
        )
        if not install_dir.is_dir():
            self.log(
                "Affinity install directory not found; skipping file-manager handler",
                "warning",
            )
            return

        # Pointless, and worse than pointless, on a build that stubs
        # RoResolveNamespace: the handler would install and the desktop entry
        # would claim the document types, but Affinity silently ignores a
        # document handed to it, so double-clicking would open an empty
        # application and look like the association is broken.
        if not self.wine_resolves_winrt_namespaces():
            self.log(
                "This Wine build cannot open documents handed to it, so the "
                "file-manager handler is not installed (use Wine 11.19 or 11.18)",
                "info",
            )
            return

        # The handler is useless against shadowed metadata, and this runs in the
        # repair path as well as the install path, so assert it here rather than
        # trusting whatever ran earlier.
        self.clear_shadowing_winmds(quiet=True)

        dest = install_dir / "affinity-on-linux.exe"
        # Fetched from the source branch (source_raw_url). It has to be
        # fetchable because the documented install pipes this script straight
        # into python3, where there is no checkout to copy from.
        #
        # The branch is the one this installer ships on, and that is not
        # cosmetic. It used to name an older PR branch that was
        # eight handler commits behind, whose binary still contained the
        # startup watchdog that kills sessions -- so a piped install fetched
        # and ran that one, silently, while a checkout install got the current
        # one. HANDLER_SHA256 below is what this installer expects, checked on
        # the download and on the checkout copy alike; anything else is refused
        # rather than installed.
        raw_url = source_raw_url("AffinityHandler/affinity-on-linux.exe")

        try:
            # Same fast path as the icons: use the checkout when there is one,
            # and download when this script was piped into python3.
            local_exe = None
            root = checkout_root()
            if root:
                candidate = root / "AffinityHandler" / "affinity-on-linux.exe"
                if candidate.exists():
                    local_exe = candidate

            if local_exe:
                got = _sha256_of(local_exe)
                if got != HANDLER_SHA256:
                    raise RuntimeError(
                        f"{local_exe} is not the handler this installer expects "
                        f"(got {got[:16]}..., wanted {HANDLER_SHA256[:16]}...). "
                        "The checkout and this script are out of step; rebuild "
                        "the handler or update the checkout."
                    )
                shutil.copy2(local_exe, dest)
            else:
                # Download beside the destination and rename into place, rather
                # than writing over it. urlretrieve leaves a partial file behind
                # on ContentTooShortError, and every later decision about the
                # handler keys off the file merely existing -- so a truncated
                # download became "File-manager handler installed" and a prefix
                # that cannot open documents.
                part = dest.with_name(dest.name + ".part")
                try:
                    with urllib.request.urlopen(raw_url, timeout=60) as r, open(part, "wb") as f:
                        shutil.copyfileobj(r, f)
                    head = part.open("rb").read(2)
                    size = part.stat().st_size
                    if head != b"MZ" or size < 4096:
                        raise RuntimeError(
                            f"downloaded handler is not a PE image ({size} bytes, "
                            f"starts {head!r})"
                        )
                    got = _sha256_of(part)
                    if got != HANDLER_SHA256:
                        raise RuntimeError(
                            "the handler that was downloaded is not the one this "
                            "installer expects.\n"
                            f"  expected {HANDLER_SHA256}\n"
                            f"  got      {got}\n"
                            "The branch it comes from is behind this installer. "
                            "Install from a checkout of this repository instead, "
                            "and file-manager integration will use the copy "
                            "beside it."
                        )
                    os.replace(str(part), str(dest))
                finally:
                    if part.exists():
                        try:
                            part.unlink()
                        except OSError:
                            pass

            dest.chmod(0o755)
            self.log("File-manager handler installed", "success")
        except Exception as e:
            self.log(
                f"Could not install the file-manager handler: {e}. "
                "Documents will not open from the file manager.",
                "warning",
            )

    def register_document_types(self):
        """Teach the desktop what .af/.afphoto/.afdesign/.afpub files are, and make
        Affinity the default for them.

        A MimeType= line in a .desktop file does nothing on its own: the file
        manager first has to recognise the extension, which needs shared-mime-info
        definitions, and the association is only picked up once the mime and
        desktop databases have been rebuilt. KDE additionally caches this in
        ksycoca, so without kbuildsycoca the old association keeps being used and
        it looks like nothing changed."""
        if not self.manages_host_entries():
            return
        mime_names = [
            "x-wine-extension-af.xml",
            "x-wine-extension-afphoto.xml",
            "x-wine-extension-afdesign.xml",
            "x-wine-extension-afpub.xml",
        ]
        # From the source branch -- see install_file_manager_handler().
        raw_base = source_raw_url("mime/")

        try:
            mime_dir = Path.home() / ".local" / "share" / "mime" / "packages"
            mime_dir.mkdir(parents=True, exist_ok=True)

            # Same fast path as the icons: use the checkout when the installer
            # was run from one, and download when it was piped into python3.
            local_mime_dir = None
            root = checkout_root()
            if root:
                candidate = root / "mime"
                if candidate.is_dir():
                    local_mime_dir = candidate

            # Install under a name winemenubuilder will never generate. It
            # writes x-wine-extension-<ext>.xml into this very directory for
            # every association a prefix registers -- this machine already has
            # x-wine-extension-crd.xml and x-wine-extension-application.xml --
            # so sharing the scheme means one of us silently overwrites the
            # other's file. The MIME type inside is what matters; the filename
            # only has to be ours.
            for name in mime_names:
                dest = mime_dir / f"affinity-{name}"
                part = dest.with_name(dest.name + ".part")
                if local_mime_dir and (local_mime_dir / name).exists():
                    shutil.copy2(local_mime_dir / name, part)
                else:
                    with urllib.request.urlopen(raw_base + name, timeout=60) as r, \
                         open(part, "wb") as f:
                        shutil.copyfileobj(r, f)
                if part.stat().st_size == 0:
                    part.unlink()
                    raise RuntimeError(f"{name} downloaded empty")
                os.replace(str(part), str(dest))
                # A copy this installer wrote under the old colliding name is
                # now a duplicate declaring the same type; drop it so the two
                # cannot disagree after an edit.
                old_style = mime_dir / name
                if old_style.exists() and old_style.read_bytes() == dest.read_bytes():
                    old_style.unlink()

            # Look at what these say. Every one of them ran with check=False and
            # capture_output=True and nothing read either, so the success line
            # below was printed whatever happened -- including when the MIME
            # database had not been rebuilt and nothing was actually associated.
            def tool(cmd):
                r = subprocess.run(cmd, check=False, capture_output=True)
                if r.returncode != 0:
                    err = (r.stderr or b"").decode("utf-8", "replace").strip()
                    self.log(
                        f"{cmd[0]} exited {r.returncode}"
                        + (f": {err.splitlines()[-1]}" if err else ""),
                        "warning",
                    )
                return r.returncode == 0

            mime_ok = tool(
                ["update-mime-database", str(Path.home() / ".local" / "share" / "mime")]
            )
            tool(
                [
                    "update-desktop-database",
                    str(Path.home() / ".local" / "share" / "applications"),
                ]
            )
            associated = 0
            for mime in (
                "application/af",
                "application/afphoto",
                "application/afdesign",
                "application/afpub",
            ):
                if tool(["xdg-mime", "default", "Affinity.desktop", mime]):
                    associated += 1
            for cache in ("kbuildsycoca6", "kbuildsycoca5"):
                if shutil.which(cache):
                    tool([cache])
                    break

            if mime_ok and associated:
                self.log(
                    "Affinity documents can now be opened from the file manager",
                    "success",
                )
            else:
                self.log(
                    "Document types may not be registered: "
                    f"mime database {'rebuilt' if mime_ok else 'NOT rebuilt'}, "
                    f"{associated} of 4 associations set. Opening a document from "
                    "the file manager may not work.",
                    "warning",
                )
        except Exception as e:
            self.log(f"Could not register Affinity document types: {e}", "warning")

    def get_ubuntu_snapshot_launcher_script(self, require_exists=True):
        """Return the preserved Ubuntu launcher script path."""
        script_path = Path(__file__).resolve().parent / "AffinityUbuntuLauncher.sh"
        if require_exists and not script_path.exists():
            raise FileNotFoundError(f"Ubuntu Snapshot launcher not found: {script_path}")
        return script_path

    def launch_affinity_v3_ubuntu_snapshot(self):
        """Launch Affinity using the preserved Ubuntu snapshot script."""
        self.log("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log("Launching Affinity v3 via Ubuntu Snapshot launcher", "info")
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        try:
            script_path = self.get_ubuntu_snapshot_launcher_script()
        except FileNotFoundError as e:
            self.log(str(e), "error")
            self.show_message("Launcher Not Found", str(e), "error")
            return

        try:
            subprocess.Popen(
                ["bash", str(script_path), "launch"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            self.log("✓ Ubuntu Snapshot launcher started", "success")
            self.log("Affinity should open in a moment...", "info")
        except Exception as e:
            self.log(f"✗ Failed to start Ubuntu Snapshot launcher: {e}", "error")
            self.show_message(
                "Launch Failed",
                f"Failed to start the Ubuntu Snapshot launcher:\n\n{str(e)}",
                "error"
            )

    def install_ubuntu_snapshot_launchers(self, show_dialog=True):
        """Install menu and desktop launchers that use the preserved Ubuntu snapshot script."""
        self.log("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log("Installing Ubuntu Snapshot launchers", "info")
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        try:
            script_path = self.get_ubuntu_snapshot_launcher_script()
        except FileNotFoundError as e:
            self.log(str(e), "error")
            if show_dialog:
                self.show_message("Launcher Not Found", str(e), "error")
            return False

        targets = [
            ("applications menu", Path.home() / ".local" / "share" / "applications" / "Affinity.desktop"),
        ]
        desktop_target = Path.home() / "Desktop" / "Affinity.desktop"
        if desktop_target.parent.exists():
            targets.append(("desktop", desktop_target))

        installed_targets = []
        failed_targets = []

        for target_label, target_path in targets:
            env = os.environ.copy()
            env["AFFINITY_DESKTOP_FILE"] = str(target_path)
            success, stdout, stderr = self.run_command(
                ["bash", str(script_path), "desktop"],
                check=False,
                capture=True,
                env=env
            )

            if success and target_path.exists():
                if target_path == desktop_target:
                    try:
                        target_path.chmod(target_path.stat().st_mode | 0o111)
                    except Exception as chmod_error:
                        self.log(f"Warning: Could not mark desktop launcher as executable: {chmod_error}", "warning")
                installed_targets.append(str(target_path))
                self.log(f"Ubuntu Snapshot launcher installed for {target_label}: {target_path}", "success")
            else:
                error_text = stderr.strip() or stdout.strip() or "unknown error"
                failed_targets.append(f"{target_path} ({error_text})")
                self.log(f"Failed to install Ubuntu Snapshot launcher for {target_label}: {error_text}", "error")

        if not installed_targets:
            if show_dialog:
                self.show_message(
                    "Launcher Installation Failed",
                    "The Ubuntu Snapshot launchers could not be written.\n\n"
                    + "\n".join(failed_targets),
                    "error"
                )
            return False

        if show_dialog:
            message = "Ubuntu Snapshot launchers installed successfully:\n\n" + "\n".join(installed_targets)
            if failed_targets:
                message += "\n\nSome targets failed:\n" + "\n".join(failed_targets)
            self.show_message(
                "Launchers Installed",
                message,
                "warning" if failed_targets else "info"
            )

        return True

    def _download_affinity_installer_thread(self, save_path_obj: Path):
        """Worker: Download Affinity installer and end operation."""
        download_url = "https://downloads.affinity.studio/Affinity%20x64.exe"
        self.log(f"Downloading from: {download_url}", "info")
        self.log(f"Saving to: {save_path_obj}", "info")
        try:
            if self.download_file(
                download_url, str(save_path_obj), "Affinity installer"
            ):
                self.log(f"\n✓ Download completed successfully!", "success")
                self.log(f"Installer saved to: {save_path_obj}", "success")
                self.show_message(
                    "Download Complete",
                    "Affinity installer has been downloaded successfully!\n\nYou can now run it with the installer buttons.",
                    "info",
                )
            else:
                self.log("✗ Download failed", "error")
        finally:
            self.end_operation()

    def open_winecfg(self):
        """Open Wine Configuration tool using custom Wine"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Opening Wine Configuration", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        wine_cfg = self.get_wine_path("winecfg")

        if not wine_cfg.exists():
            self.log(
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            self.show_message(
                "Wine Not Found",
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            return

        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory

        self.log(f"Opening winecfg using: {wine_cfg}", "info")
        self.log("The Wine Configuration window should open now.", "info")

        # Run winecfg in background (non-blocking)
        threading.Thread(
            target=lambda: self.run_command(
                [str(wine_cfg)], check=False, capture=False, env=env
            ),
            daemon=True,
        ).start()

        self.log("✓ Wine Configuration opened", "success")

    def open_winetricks(self):
        """Open Winetricks GUI using custom Wine"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Opening Winetricks", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        wine_cfg = self.get_wine_path("winecfg")

        if not wine_cfg.exists():
            self.log(
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            self.show_message(
                "Wine Not Found",
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            return

        # Check if winetricks is available
        winetricks_path = shutil.which("winetricks")
        if not winetricks_path:
            self.log(
                "Winetricks is not installed. Please install it using your package manager.",
                "error",
            )
            self.show_message(
                "Winetricks Not Found",
                "Winetricks is not installed. Please install it using:\n\n"
                "Arch/CachyOS/EndeavourOS/XeroLinux: sudo pacman -S winetricks\n"
                "Fedora/Nobara: sudo dnf install winetricks\n"
                "Debian/Ubuntu/Mint/Pop/Zorin/PikaOS: sudo apt install winetricks\n"
                "openSUSE: sudo zypper install winetricks",
                "error",
            )
            return

        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory

        self.log(f"Opening winetricks using: {winetricks_path}", "info")
        self.log("The Winetricks GUI should open now.", "info")

        # Run winetricks in background (non-blocking)
        # Winetricks will open its GUI when run without arguments
        threading.Thread(
            target=lambda: self.run_command(
                [winetricks_path], check=False, capture=False, env=env
            ),
            daemon=True,
        ).start()

        self.log("✓ Winetricks opened", "success")

    def set_windows11_renderer(self):
        """Set Windows 11 and configure renderer (OpenGL or Vulkan)"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Windows 11 + Renderer Configuration", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Start operation for renderer configuration
        self.start_operation("Configure Renderer")

        wine_cfg = self.get_wine_path("winecfg")

        if not wine_cfg.exists():
            self.log(
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            self.show_message(
                "Wine Not Found",
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            self.end_operation()
            return

        # Ask user to choose renderer (without parent to avoid threading issues)
        dialog = QDialog(self.dialog_parent())
        dialog.setWindowTitle("Select Renderer")
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Responsive sizing
        screen = dialog.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        if screen_width < 800 or screen_height < 600:
            min_width = min(350, int(screen_width * 0.9))
            min_height = min(280, int(screen_height * 0.7))
            default_width = min(450, int(screen_width * 0.85))
            default_height = min(320, int(screen_height * 0.65))
            max_width = int(screen_width * 0.95)
            max_height = int(screen_height * 0.85)
        elif screen_width < 1280 or screen_height < 720:
            min_width = 400
            min_height = 300
            default_width = 500
            default_height = 350
            max_width = int(screen_width * 0.9)
            max_height = int(screen_height * 0.85)
        else:
            min_width = 400
            min_height = 300
            default_width = 500
            default_height = 350
            max_width = 750
            max_height = 600

        dialog.setMinimumWidth(min_width)
        dialog.setMinimumHeight(min_height)
        dialog.setMaximumWidth(max_width)
        dialog.setMaximumHeight(max_height)
        dialog.resize(default_width, default_height)
        dialog.setSizeGripEnabled(True)

        # Apply theme stylesheet matching main UI
        dark_style = """
                QDialog {
                    background-color: #252526;
                    color: #dcdcdc;
                }
                QLabel {
                    color: #dcdcdc;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4ec9b0;
                    padding: 10px 0px;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #cccccc;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                }
                QFrame#optionFrame {
                    background-color: #2d2d2d;
                    border: 1px solid #3c3c3c;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #4a4a4a;
                    background-color: #323232;
                }
                QRadioButton {
                    font-size: 16px;
                    color: #dcdcdc;
                    padding: 8px 0px;
                    spacing: 10px;
                    font-weight: 500;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #555555;
                    background-color: #3c3c3c;
                }
                QRadioButton::indicator:hover {
                    border-color: #6a6a6a;
                }
                QRadioButton::indicator:checked {
                    background-color: #4ec9b0;
                    border-color: #4ec9b0;
                }
                QPushButton {
                    background-color: #3c3c3c;
                    color: #f0f0f0;
                    border: 1px solid #555555;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                    border-color: #6a6a6a;
                }
                QPushButton:pressed {
                    background-color: #2d2d2d;
                }
                QPushButton#okButton {
                    background-color: #4ec9b0;
                    color: #1e1e1e;
                    border: 1px solid #4ec9b0;
                    font-weight: bold;
                }
                QPushButton#okButton:hover {
                    background-color: #5dd9c0;
                    border-color: #5dd9c0;
                }
                QPushButton#okButton:pressed {
                    background-color: #3db9a0;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background-color: #2d2d2d;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #555555;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #666666;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
        """
        if self.theme == "mattscreative":
            dialog_style = self._mattscreative_palette_style(dark_style)
        elif self.dark_mode:
            dialog_style = dark_style
        else:
            dialog_style = """
                QDialog {
                    background-color: #ffffff;
                    color: #2d2d2d;
                }
                QLabel {
                    color: #2d2d2d;
                    background-color: transparent;
                }
                QLabel#titleLabel {
                    font-size: 18px;
                    font-weight: bold;
                    color: #4caf50;
                    padding: 10px 0px;
                }
                QLabel#descriptionLabel {
                    font-size: 13px;
                    color: #555555;
                    padding: 5px 0px 15px 0px;
                    line-height: 1.4;
                }
                QLabel#optionDescription {
                    font-size: 12px;
                    color: #666666;
                    padding: 4px 0px 0px 0px;
                    line-height: 1.4;
                }
                QFrame#optionFrame {
                    background-color: #f5f5f5;
                    border: 1px solid #e0e0e0;
                    border-radius: 6px;
                    padding: 8px;
                    margin: 4px 0px;
                }
                QFrame#optionFrame:hover {
                    border-color: #c0c0c0;
                    background-color: #fafafa;
                }
                QRadioButton {
                    font-size: 14px;
                    color: #2d2d2d;
                    padding: 8px 0px;
                    spacing: 10px;
                }
                QRadioButton::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 9px;
                    border: 2px solid #c0c0c0;
                    background-color: #ffffff;
                }
                QRadioButton::indicator:hover {
                    border-color: #a0a0a0;
                }
                QRadioButton::indicator:checked {
                    background-color: #4caf50;
                    border-color: #4caf50;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    color: #2d2d2d;
                    border: 1px solid #c0c0c0;
                    border-radius: 8px;
                    min-width: 100px;
                    padding: 10px 20px;
                    font-size: 13px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background-color: #d0d0d0;
                    border-color: #a0a0a0;
                }
                QPushButton:pressed {
                    background-color: #c0c0c0;
                }
                QPushButton#okButton {
                    background-color: #4caf50;
                    color: #ffffff;
                    border: 1px solid #4caf50;
                    font-weight: bold;
                }
                QPushButton#okButton:hover {
                    background-color: #45a049;
                    border-color: #45a049;
                }
                QPushButton#okButton:pressed {
                    background-color: #3d8b40;
                }
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background-color: #f5f5f5;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #c0c0c0;
                    border-radius: 6px;
                    min-height: 30px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #a0a0a0;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
            """

        dialog.setStyleSheet(dialog_style)

        # Main layout with responsive margins
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(12)
        margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
        main_layout.setContentsMargins(margin, margin, margin, margin)

        # Title
        title_label = QLabel("Select Renderer")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(title_label)

        # Description
        desc_label = QLabel("Choose a renderer for troubleshooting:")
        desc_label.setObjectName("descriptionLabel")
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(desc_label)

        # Options container with scroll area for better scaling
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        options_container = QFrame()
        options_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        options_layout = QVBoxLayout(options_container)
        options_layout.setSpacing(8)
        options_margin = 8 if (screen_width >= 800 and screen_height >= 600) else 6
        options_layout.setContentsMargins(
            options_margin, options_margin, options_margin, options_margin
        )

        scroll_area.setWidget(options_container)

        button_group = QButtonGroup()

        # Vulkan option
        vulkan_frame = QFrame()
        vulkan_frame.setObjectName("optionFrame")
        vulkan_layout = QVBoxLayout(vulkan_frame)
        vulkan_layout.setContentsMargins(12, 10, 12, 10)
        vulkan_radio = QRadioButton("Vulkan (Recommended - OpenCL support)")
        vulkan_radio.setChecked(True)
        vulkan_radio.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        vulkan_layout.addWidget(vulkan_radio)
        options_layout.addWidget(vulkan_frame)

        # OpenGL option
        opengl_frame = QFrame()
        opengl_frame.setObjectName("optionFrame")
        opengl_layout = QVBoxLayout(opengl_frame)
        opengl_layout.setContentsMargins(12, 10, 12, 10)
        opengl_radio = QRadioButton("OpenGL (Alternative)")
        opengl_radio.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        opengl_layout.addWidget(opengl_radio)
        options_layout.addWidget(opengl_frame)

        # GDI option
        gdi_frame = QFrame()
        gdi_frame.setObjectName("optionFrame")
        gdi_layout = QVBoxLayout(gdi_frame)
        gdi_layout.setContentsMargins(12, 10, 12, 10)
        gdi_radio = QRadioButton("GDI (Fallback)")
        gdi_radio.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        gdi_layout.addWidget(gdi_radio)
        options_layout.addWidget(gdi_frame)

        button_group.addButton(vulkan_radio, 0)
        button_group.addButton(opengl_radio, 1)
        button_group.addButton(gdi_radio, 2)

        main_layout.addWidget(scroll_area, 1)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Continue")
        ok_btn.setObjectName("okButton")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_btn)

        main_layout.addLayout(button_layout)

        # Ensure the dialog is large enough to show all content; clamp inside min/max.
        hint = dialog.sizeHint()
        target_w = min(max(default_width, hint.width()), max_width)
        target_h = min(max(default_height, hint.height()), max_height)
        target_w = max(target_w, min_width)
        target_h = max(target_h, min_height)
        dialog.resize(target_w, target_h)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.log("Renderer configuration cancelled", "warning")
            self.end_operation()
            return

        # Determine selected renderer
        renderer_map = {
            0: ("vulkan", "Vulkan", "vulkan"),
            1: ("gl", "OpenGL", "opengl"),
            2: ("gdi", "GDI", "gdi")
        }

        selected_id = button_group.checkedId()
        renderer_value, renderer_name, winetricks_value = renderer_map.get(
            selected_id, ("vulkan", "Vulkan", "vulkan")
        )

        env = os.environ.copy()
        env = self.get_winetricks_env(env)
        # Set Windows version to 11
        self.log("Setting Windows version to 11...", "info")
        self.stop_prefix_wine_processes(env, reason="setting Windows version")
        success, _, _ = self.run_command(
            [str(wine_cfg), "-v", "win11"], check=False, env=env
        )
        if success:
            self.log("✓ Windows version set to 11", "success")
        else:
            self.log("⚠ Warning: Failed to set Windows version", "warning")

        # Set renderer directly via registry (more reliable than winetricks)
        self.log(f"Configuring {renderer_name} renderer...", "info")
        wine = self.get_wine_path("wine")

        # Set renderer directly via registry - this is more reliable than winetricks
        self.log(f"Setting {renderer_name} renderer via registry...", "info")
        reg_add_success, reg_add_stdout, reg_add_stderr = self.run_command(
            [
                str(wine),
                "reg",
                "add",
                "HKEY_CURRENT_USER\\Software\\Wine\\Direct3D",
                "/v",
                "renderer",
                "/t",
                "REG_SZ",
                "/d",
                renderer_value,
                "/f",
            ],
            check=False,
            env=env,
            capture=True,
        )

        if reg_add_success:
            self.log(f"✓ {renderer_name} renderer set via registry", "success")
        else:
            # Fallback to winetricks if direct registry setting fails
            self.log(f"Registry method failed, trying winetricks...", "info")
            success, stdout, stderr = self.run_command(
                ["winetricks", "--unattended", "--force", "--no-isolate", "--optout", f"renderer={winetricks_value}"],
                check=False,
                env=env,
            )
            if success:
                self.log(f"✓ {renderer_name} renderer set via winetricks", "success")
            else:
                self.log(
                    f"⚠ Warning: Failed to set {renderer_name} renderer via both methods",
                    "warning",
                )

        # Verify renderer was actually set in registry
        self.log(f"Verifying {renderer_name} renderer configuration...", "info")
        renderer_verified = False

        try:
            # Check registry for renderer setting
            renderer_check_success, renderer_check_stdout, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "query",
                    "HKEY_CURRENT_USER\\Software\\Wine\\Direct3D",
                    "/v",
                    "renderer",
                ],
                check=False,
                env=env,
                capture=True,
            )

            if renderer_check_success and renderer_check_stdout:
                renderer_check_lower = renderer_check_stdout.lower()
                # Check for the renderer value we set
                if renderer_value == "vulkan" and "vulkan" in renderer_check_lower:
                    renderer_verified = True
                elif renderer_value == "gl" and ("gl" in renderer_check_lower or "opengl" in renderer_check_lower):
                    renderer_verified = True
                elif renderer_value == "gdi" and "gdi" in renderer_check_lower:
                    renderer_verified = True

                if renderer_verified:
                    self.log(
                        f"✓ {renderer_name} renderer verified in registry", "success"
                    )
                else:
                    # Show what was actually found
                    actual_renderer = None
                    if "renderer" in renderer_check_lower:
                        # Extract the actual value
                        match = re.search(
                            r"renderer\s+REG_SZ\s+(\w+)",
                            renderer_check_stdout,
                            re.IGNORECASE,
                        )
                        if match:
                            actual_renderer = match.group(1)
                            self.log(
                                f"⚠ Warning: Expected {renderer_name} but found {actual_renderer} in registry",
                                "warning",
                            )
                        else:
                            self.log(
                                f"⚠ Warning: {renderer_name} renderer may not be set correctly",
                                "warning",
                            )
                    else:
                        self.log(
                            f"⚠ Warning: Could not verify {renderer_name} renderer in registry",
                            "warning",
                        )

                    # Retry setting the renderer if verification failed
                    if (
                        not actual_renderer
                        or actual_renderer.lower() != renderer_value.lower()
                    ):
                        self.log(
                            f"Retrying to set {renderer_name} renderer via registry...",
                            "info",
                        )
                        retry_success, _, retry_stderr = self.run_command(
                            [
                                str(wine),
                                "reg",
                                "add",
                                "HKEY_CURRENT_USER\\Software\\Wine\\Direct3D",
                                "/v",
                                "renderer",
                                "/t",
                                "REG_SZ",
                                "/d",
                                renderer_value,
                                "/f",
                            ],
                            check=False,
                            env=env,
                            capture=True,
                        )

                        if retry_success:
                            # Verify again after retry
                            verify_success, verify_stdout, _ = self.run_command(
                                [
                                    str(wine),
                                    "reg",
                                    "query",
                                    "HKEY_CURRENT_USER\\Software\\Wine\\Direct3D",
                                    "/v",
                                    "renderer",
                                ],
                                check=False,
                                env=env,
                                capture=True,
                            )

                            if (
                                verify_success
                                and renderer_value.lower()
                                in (verify_stdout or "").lower()
                            ):
                                self.log(
                                    f"✓ {renderer_name} renderer set successfully via registry",
                                    "success",
                                )
                            else:
                                self.log(
                                    f"⚠ Warning: Failed to verify {renderer_name} renderer after retry",
                                    "warning",
                                )
                        else:
                            self.log(
                                f"⚠ Warning: Failed to set {renderer_name} renderer via registry: {retry_stderr[:100] if retry_stderr else 'Unknown error'}",
                                "warning",
                            )
            else:
                self.log(f"⚠ Warning: Could not read renderer from registry", "warning")
        except Exception as e:
            self.log(f"⚠ Warning: Error verifying renderer: {e}", "warning")

        self.log("\n✓ Windows 11 and renderer configuration completed", "success")
        self.end_operation()

    def install_dotnet_sdk(self, version="8.0"):
        """Install .NET SDK based on distribution"""
        try:
            self.log(f"Installing .NET SDK {version}...", "info")

            # Determine package name based on version
            if version == "10.0":
                package_name = "dotnet-sdk-10.0"
            else:
                package_name = "dotnet-sdk-8.0"

            if self.distro in [
                "pikaos",
                "pop",
                "debian",
                "ubuntu",
                "linuxmint",
                "zorin",
            ]:
                # Try installing dotnet-sdk (may need Microsoft repo)
                success, _, stderr = self.run_command(
                    ["sudo", "apt", "install", "-y", package_name], check=False
                )
                if not success:
                    self.log(
                        f"Failed to install {package_name} from default repos",
                        "warning",
                    )
                    self.log(
                        "You may need to add Microsoft's .NET repository. See: https://learn.microsoft.com/dotnet/core/install/linux",
                        "info",
                    )
                    return False
                return True

            commands = {
                "arch": [
                    "sudo",
                    "pacman",
                    "-S",
                    "--needed",
                    "--noconfirm",
                    package_name,
                ],
                "cachyos": [
                    "sudo",
                    "pacman",
                    "-S",
                    "--needed",
                    "--noconfirm",
                    package_name,
                ],
                "endeavouros": [
                    "sudo",
                    "pacman",
                    "-S",
                    "--needed",
                    "--noconfirm",
                    package_name,
                ],
                "xerolinux": [
                    "sudo",
                    "pacman",
                    "-S",
                    "--needed",
                    "--noconfirm",
                    package_name,
                ],
                "fedora": ["sudo", "dnf", "install", "-y", package_name],
                "nobara": ["sudo", "dnf", "install", "-y", package_name],
                "opensuse-tumbleweed": [
                    "sudo",
                    "zypper",
                    "install",
                    "-y",
                    package_name,
                ],
                "opensuse-leap": ["sudo", "zypper", "install", "-y", package_name],
            }

            if self.distro in commands:
                success, _, stderr = self.run_command(
                    commands[self.distro], check=False
                )
                if success:
                    self.log(".NET SDK installed successfully", "success")
                    return True
                else:
                    self.log(
                        f"Failed to install .NET SDK: {stderr[:200] if stderr else 'Unknown error'}",
                        "error",
                    )
                    return False

            self.log(
                f"Unsupported distribution for .NET SDK auto-install: {self.format_distro_name()}",
                "error",
            )
            return False
        except Exception as e:
            self.log(f"Error installing .NET SDK: {e}", "error")
            return False

    def apply_return_colors(self):
        """Apply ReturnColors patch to restore colored icons in Affinity v3"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Return Colors (Affinity v3)", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Check if Wine is set up
        wine_binary = self.get_wine_path("wine")
        if not wine_binary.exists():
            self.log(
                "Wine is not set up yet. Please setup Wine environment first.", "error"
            )
            QMessageBox.warning(
                self,
                "Wine Not Ready",
                "Wine setup must complete before applying patches.\n"
                "Please setup Wine environment first.",
            )
            return

        # Check if Affinity v3 is installed
        affinity_dir = (
            Path(self.directory) / "drive_c" / "Program Files" / "Affinity" / "Affinity"
        )
        dll_path = affinity_dir / "Serif.Affinity.dll"

        if not dll_path.exists():
            self.log("Affinity v3 (Unified) is not installed.", "error")
            self.log(f"Expected DLL at: {dll_path}", "info")
            self.show_message(
                "Affinity v3 Not Found",
                "Affinity v3 (Unified) is not installed.\n\n"
                "This patch only works for Affinity v3 (Unified).\n"
                "Please install Affinity v3 first using the 'Affinity (Unified)' button.",
                "error",
            )
            return

        self.start_operation("Return Colors")

        # Ensure patcher files are available
        self.ensure_patcher_files()

        # Check if .NET SDK 10.0+ is installed (required for ReturnColors)
        if not self.check_dotnet_sdk_10():
            self.log(".NET SDK 10.0+ is required for ReturnColors patch", "warning")
            self.log("Attempting to install .NET SDK 10.0 automatically...", "info")

            # Try to install dotnet-sdk-10.0 automatically
            install_success = False
            if self.distro in [
                "pikaos",
                "pop",
                "debian",
                "ubuntu",
                "linuxmint",
                "zorin",
            ]:
                success, _, _ = self.run_command(
                    ["sudo", "apt", "install", "-y", "dotnet-sdk-10.0"], check=False
                )
                if success:
                    install_success = True
                else:
                    self.log(
                        "Failed to install dotnet-sdk-10.0 from default repos",
                        "warning",
                    )
            elif self.distro in ["arch", "cachyos"]:
                success, _, _ = self.run_command(
                    [
                        "sudo",
                        "pacman",
                        "-S",
                        "--needed",
                        "--noconfirm",
                        "dotnet-sdk-10.0",
                    ],
                    check=False,
                )
                if success:
                    install_success = True
            elif self.distro in ["endeavouros", "xerolinux"]:
                success, _, _ = self.run_command(
                    [
                        "sudo",
                        "pacman",
                        "-S",
                        "--needed",
                        "--noconfirm",
                        "dotnet-sdk-10.0",
                    ],
                    check=False,
                )
                if success:
                    install_success = True
            elif self.distro in ["fedora", "nobara"]:
                success, _, _ = self.run_command(
                    ["sudo", "dnf", "install", "-y", "dotnet-sdk-10.0"], check=False
                )
                if success:
                    install_success = True
            elif self.distro in ["opensuse-tumbleweed", "opensuse-leap"]:
                success, _, _ = self.run_command(
                    ["sudo", "zypper", "install", "-y", "dotnet-sdk-10.0"], check=False
                )
                if success:
                    install_success = True

            # Check again if installation succeeded
            if install_success and self.check_dotnet_sdk_10():
                self.log(".NET SDK 10.0 installed successfully", "success")
            else:
                # Installation failed or still not detected, show manual instructions
                self.log(".NET SDK 10.0+ is required for ReturnColors patch", "error")
                self.log(
                    "ReturnColors requires .NET SDK 10.0 or newer to build.", "info"
                )
                self.log("Please install .NET SDK 10.0 manually:", "info")

                install_instructions = ""
                if self.distro in ["arch", "cachyos"]:
                    self.log("  sudo pacman -S dotnet-sdk-10.0", "info")
                    install_instructions = "sudo pacman -S dotnet-sdk-10.0"
                elif self.distro in ["endeavouros", "xerolinux"]:
                    self.log("  sudo pacman -S dotnet-sdk-10.0", "info")
                    install_instructions = "sudo pacman -S dotnet-sdk-10.0"
                elif self.distro in ["fedora", "nobara"]:
                    self.log("  sudo dnf install dotnet-sdk-10.0", "info")
                    install_instructions = "sudo dnf install dotnet-sdk-10.0"
                elif self.distro in [
                    "pikaos",
                    "pop",
                    "debian",
                    "ubuntu",
                    "linuxmint",
                    "zorin",
                ]:
                    self.log("  sudo apt install dotnet-sdk-10.0", "info")
                    self.log("  (May require Microsoft's .NET repository)", "warning")
                    install_instructions = "sudo apt install dotnet-sdk-10.0\n(May require Microsoft's .NET repository)"
                elif self.distro in ["opensuse-tumbleweed", "opensuse-leap"]:
                    self.log("  sudo zypper install dotnet-sdk-10.0", "info")
                    install_instructions = "sudo zypper install dotnet-sdk-10.0"
                else:
                    self.log(
                        "  Please install .NET SDK 10.0 from: https://dotnet.microsoft.com/download",
                        "info",
                    )
                    install_instructions = (
                        "Install from: https://dotnet.microsoft.com/download"
                    )

                # Ensure distro is detected before trying alternative method
                if not self.distro:
                    self.detect_distro()

                # Try to install using the install_dotnet_sdk method as fallback
                self.log(
                    "Attempting to install .NET SDK using alternative method...", "info"
                )
                if self.install_dotnet_sdk(version="10.0"):
                    # Check again if installation succeeded
                    if self.check_dotnet_sdk_10():
                        self.log(
                            ".NET SDK 10.0 installed successfully via alternative method",
                            "success",
                        )
                    else:
                        self.end_operation()
                        self.show_message(
                            ".NET SDK 10.0 Required",
                            "ReturnColors patch requires .NET SDK 10.0 or newer to build.\n\n"
                            f"Please install it manually:\n{install_instructions}\n\n"
                            "After installing, restart the installer and try again.",
                            "error",
                        )
                        return
                else:
                    self.end_operation()
                    self.show_message(
                        ".NET SDK 10.0 Required",
                        "ReturnColors patch requires .NET SDK 10.0 or newer to build.\n\n"
                        f"Please install it manually:\n{install_instructions}\n\n"
                        "After installing, restart the installer and try again.",
                        "error",
                    )
                    return

        # Run ReturnColors colorize
        success = self.run_return_colors_colorize(str(affinity_dir))

        if success:
            self.log("\n✓ ReturnColors patch applied successfully!", "success")
            self.log(
                "Affinity v3 icons have been restored to colored versions.", "info"
            )
            self.end_operation()
            self.show_message(
                "Patch Applied Successfully",
                "ReturnColors patch has been applied successfully!\n\n"
                "Affinity v3 icons have been restored to colored versions.\n"
                "You may need to restart Affinity v3 to see the changes.",
                "info",
            )
        else:
            self.log("\n✗ ReturnColors patch failed", "error")
            self.end_operation()
            self.show_message(
                "Patch Failed",
                "Failed to apply ReturnColors patch.\n\n"
                "Please check the log for details and ensure:\n"
                "• Affinity v3 is installed\n"
                "• .NET SDK is installed\n"
                "• ReturnColors files are available",
                "error",
            )

    def fix_affinity_settings(self):
        """Fix Affinity v3 settings by patching the DLL"""
        try:
            self.log(
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            self.log("Fix Affinity v3 Settings", "info")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )

            # Ensure patcher files are available
            self.ensure_patcher_files()

            # Check if Affinity v3 is installed
            dll_path = (
                Path(self.directory)
                / "drive_c"
                / "Program Files"
                / "Affinity"
                / "Affinity"
                / "Serif.Affinity.dll"
            )

            if not dll_path.exists():
                self.log("Affinity v3 (Unified) is not installed.", "error")
                self.log(f"Expected DLL at: {dll_path}", "info")
                self.show_message(
                    "Affinity v3 Not Found",
                    "Affinity v3 (Unified) is not installed.\n\n"
                    "This fix only works for Affinity v3 (Unified).\n"
                    "Please install Affinity v3 first using the 'Affinity (Unified)' button.",
                    "error",
                )
                return

            self.start_operation("Fix Affinity Settings")

            # Check if .NET SDK is installed, if not try to install it
            if not self.check_dotnet_sdk():
                self.log(".NET SDK not found. Attempting to install...", "info")
                try:
                    if not self.install_dotnet_sdk():
                        self.log("Failed to install .NET SDK automatically", "error")
                        self.log("Please install .NET SDK manually:", "info")
                        if self.distro in ["arch", "cachyos"]:
                            self.log("  sudo pacman -S dotnet-sdk-8.0", "info")
                        elif self.distro in ["endeavouros", "xerolinux"]:
                            self.log("  sudo pacman -S dotnet-sdk-8.0", "info")
                        elif self.distro in ["fedora", "nobara"]:
                            self.log("  sudo dnf install dotnet-sdk-8.0", "info")
                        elif self.distro in ["pikaos", "pop", "debian"]:
                            self.log("  sudo apt install dotnet-sdk-8.0", "info")
                            self.log(
                                "  (May require Microsoft's .NET repository)", "warning"
                            )
                        elif self.distro in ["opensuse-tumbleweed", "opensuse-leap"]:
                            self.log("  sudo zypper install dotnet-sdk-8.0", "info")
                        self.end_operation()
                        self.show_message(
                            ".NET SDK Required",
                            ".NET SDK is required to patch the Affinity DLL.\n\n"
                            "Please install it manually using the commands shown in the log, then try again.",
                            "error",
                        )
                        return
                except Exception as e:
                    self.log(f"Error during .NET SDK installation: {e}", "error")
                    self.end_operation()
                    self.show_message(
                        "Installation Error",
                        f"An error occurred while trying to install .NET SDK:\n{e}\n\n"
                        "Please install .NET SDK manually and try again.",
                        "error",
                    )
                    return

            # Patch the DLL
            success = self.patch_affinity_dll("Add")

            if success:
                self.log("\n✓ Settings fix completed successfully!", "success")
                self.log(
                    "Affinity v3 should now be able to save settings properly.", "info"
                )
                self.log(
                    "You may need to restart Affinity for the changes to take effect.",
                    "info",
                )
                self.show_message(
                    "Settings Fix Complete",
                    "The Affinity v3 DLL has been patched successfully!\n\n"
                    "Settings should now save properly.\n"
                    "You may need to restart Affinity for the changes to take effect.",
                    "info",
                )
            else:
                self.log("\n✗ Settings fix failed", "error")
                self.show_message(
                    "Settings Fix Failed",
                    "Failed to patch the Affinity v3 DLL.\n\n"
                    "Please check the log for details.\n"
                    "Make sure .NET SDK is installed if you see related errors.",
                    "error",
                )
        except Exception as e:
            self.log(f"Unexpected error during settings fix: {e}", "error")
            self.show_message(
                "Unexpected Error",
                f"An unexpected error occurred:\n{e}\n\n"
                "Please check the log for details.",
                "error",
            )
        finally:
            self.end_operation()

    def _apply_auto_dpi_on_main_thread(self):
        """Auto-configure Affinity DPI scaling based on the host display
        resolution and scale factor (used during one-click setup). Writes
        HKEY_CURRENT_USER\\Control Panel\\Desktop\\LogPixels via wine reg."""
        try:
            screen = QApplication.primaryScreen()
            if screen is None:
                self.log(
                    "Could not detect primary screen; skipping auto DPI", "warning"
                )
                return
            dpr = screen.devicePixelRatio() or 1.0
            geo = screen.geometry()
            phys_w = int(geo.width() * dpr)
            phys_h = int(geo.height() * dpr)

            # Resolution-based recommendation (mirrors the dialog's common values table)
            if phys_w >= 3840 or phys_h >= 2160:
                res_dpi = 192
            elif phys_w >= 2560 or phys_h >= 1440:
                res_dpi = 144
            elif phys_w >= 1920 or phys_h >= 1080:
                res_dpi = 96
            else:
                res_dpi = 96

            # OS-scale-based recommendation (96 per 100% host scale, snapped to slider steps)
            scale_dpi = max(96, min(480, int(round((96.0 * dpr) / 12.0)) * 12))

            recommended = max(res_dpi, scale_dpi)
            percentage = int(round((recommended / 96.0) * 100))
            self.log(
                f"Auto DPI detected: {phys_w}x{phys_h} at {dpr:.2f}x scale -> DPI {recommended} ({percentage}%)",
                "info",
            )

            wine = self.get_wine_path("wine")
            if not wine.exists():
                self.log("Wine not available; skipping auto DPI", "warning")
                return
            env = os.environ.copy()
            env["WINEPREFIX"] = self.directory
            env["WINEDEBUG"] = "-all"
            success, _, stderr = self.run_command(
                [
                    str(wine),
                    "reg",
                    "add",
                    "HKEY_CURRENT_USER\\Control Panel\\Desktop",
                    "/v",
                    "LogPixels",
                    "/t",
                    "REG_DWORD",
                    "/d",
                    str(recommended),
                    "/f",
                ],
                check=False,
                env=env,
                capture=True,
            )
            if success:
                self.log(
                    f"Auto DPI set to {recommended} ({percentage}%); restart Affinity apps to apply",
                    "success",
                )
            else:
                self.log(
                    f"Failed to write auto DPI: {stderr or 'unknown error'}",
                    "warning",
                )
        except Exception as e:
            self.log(f"Auto DPI error: {e}", "warning")

    def set_dpi_scaling(self):
        """Set DPI scaling for Affinity applications"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("DPI Scaling Configuration", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        wine = self.get_wine_path("wine")

        if not wine.exists():
            self.log(
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            self.show_message(
                "Wine Not Found",
                "Wine is not set up yet. Please run 'Setup Wine Environment' first.",
                "error",
            )
            return

        # Try to get current DPI value from registry
        env = os.environ.copy()
        env["WINEPREFIX"] = self.directory
        current_dpi = 96  # Default value

        # Try to read current DPI from registry
        try:
            success, stdout, _ = self.run_command(
                [
                    str(wine),
                    "reg",
                    "query",
                    "HKEY_CURRENT_USER\\Control Panel\\Desktop",
                    "/v",
                    "LogPixels",
                ],
                check=False,
                env=env,
                capture=True,
            )
            if success and stdout:
                # Parse the output to extract DPI value
                # Output format: "LogPixels    REG_DWORD    0x000000c0 (192)"
                match = re.search(r"0x[0-9a-fA-F]+|(\d+)", stdout)
                if match:
                    # Try to find hex value first
                    hex_match = re.search(r"0x([0-9a-fA-F]+)", stdout)
                    if hex_match:
                        current_dpi = int(hex_match.group(1), 16)
                    else:
                        # Try decimal
                        dec_match = re.search(r"\((\d+)\)", stdout)
                        if dec_match:
                            current_dpi = int(dec_match.group(1))
        except:
            pass  # Use default if reading fails

        # Create dialog (without parent to avoid threading issues)
        dialog = QDialog(self.dialog_parent())
        dialog.setWindowTitle("Set DPI Scaling")
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # Responsive sizing
        screen = dialog.screen().availableGeometry()
        screen_width = screen.width()
        screen_height = screen.height()

        if screen_width < 800 or screen_height < 600:
            min_width = min(420, int(screen_width * 0.9))
            min_height = min(440, int(screen_height * 0.7))
            default_width = min(540, int(screen_width * 0.85))
            default_height = min(500, int(screen_height * 0.7))
            max_width = int(screen_width * 0.95)
            max_height = int(screen_height * 0.9)
        elif screen_width < 1280 or screen_height < 720:
            min_width = 480
            min_height = 480
            default_width = 560
            default_height = 560
            max_width = int(screen_width * 0.9)
            max_height = int(screen_height * 0.9)
        else:
            min_width = 500
            min_height = 500
            default_width = 580
            default_height = 620
            max_width = 820
            max_height = 780

        dialog.setMinimumWidth(min_width)
        dialog.setMinimumHeight(min_height)
        dialog.setMaximumWidth(max_width)
        dialog.setMaximumHeight(max_height)
        dialog.resize(default_width, default_height)
        dialog.setSizeGripEnabled(True)
        dialog.setStyleSheet(self.get_dialog_stylesheet())

        # Main layout
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(12)
        margin = 20 if (screen_width >= 800 and screen_height >= 600) else 15
        main_layout.setContentsMargins(margin, margin, margin, margin)

        # Title
        title_label = QLabel("Set DPI Scaling")
        title_label.setObjectName("titleLabel")
        title_label.setWordWrap(True)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(title_label)

        # Info label
        info_label = QLabel(
            "Adjust DPI scaling for Affinity applications.\n"
            "Higher values make UI elements larger.\n\n"
            "Common values:\n"
            "• 96 = 100% (1080p, 24-27 inches)\n"
            "• 120 = 125% (1080p, 13-15 inch laptops)\n"
            "• 144 = 150% (1440p, 27-32 inches)\n"
            "• 192 = 200% (4K, 27-32 inches)"
        )
        info_label.setObjectName("descriptionLabel")
        info_label.setWordWrap(True)
        info_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(info_label)

        # Current value display
        value_label = QLabel()
        value_label.setObjectName("titleLabel")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        main_layout.addWidget(value_label)

        # Slider
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(96)
        slider.setMaximum(480)
        slider.setValue(current_dpi)
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider.setTickInterval(24)  # Show ticks every 24 DPI
        slider.setSingleStep(12)  # Step by 12 DPI for smoother adjustment
        slider.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        main_layout.addWidget(slider)

        # Min/Max labels
        minmax_layout = QHBoxLayout()
        min_label = QLabel("96 (100%)")
        min_label.setObjectName("descriptionLabel")
        minmax_layout.addWidget(min_label)
        minmax_layout.addStretch()
        max_label = QLabel("480 (500%)")
        max_label.setObjectName("descriptionLabel")
        minmax_layout.addWidget(max_label)
        main_layout.addLayout(minmax_layout)

        # Update label when slider changes
        def update_label(value):
            percentage = int((value / 96) * 100)
            value_label.setText(f"DPI: {value} ({percentage}%)")

        slider.valueChanged.connect(update_label)
        update_label(current_dpi)  # Set initial value

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("okButton")
        save_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        save_btn.setDefault(True)
        save_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(save_btn)

        main_layout.addLayout(button_layout)

        # Ensure the dialog is large enough to show all content; clamp inside min/max.
        hint = dialog.sizeHint()
        target_w = min(max(default_width, hint.width()), max_width)
        target_h = min(max(default_height, hint.height()), max_height)
        target_w = max(target_w, min_width)
        target_h = max(target_h, min_height)
        dialog.resize(target_w, target_h)

        # Show dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.log("DPI scaling configuration cancelled", "warning")
            return

        selected_dpi = slider.value()
        percentage = int((selected_dpi / 96) * 100)

        # Apply DPI setting via registry
        self.log(f"Setting DPI scaling to {selected_dpi} ({percentage}%)...", "info")

        # Use wine reg add command
        success, stdout, stderr = self.run_command(
            [
                str(wine),
                "reg",
                "add",
                "HKEY_CURRENT_USER\\Control Panel\\Desktop",
                "/v",
                "LogPixels",
                "/t",
                "REG_DWORD",
                "/d",
                str(selected_dpi),
                "/f",
            ],
            check=False,
            env=env,
        )

        if success:
            self.log(f"✓ DPI scaling set to {selected_dpi} ({percentage}%)", "success")
            self.log(
                "Note: You may need to restart Affinity applications for the change to take effect.",
                "info",
            )
            self.show_message(
                "DPI Scaling Updated",
                f"DPI scaling has been set to {selected_dpi} ({percentage}%).\n\n"
                "You may need to restart Affinity applications for the change to take effect.",
                "info",
            )
        else:
            self.log(
                f"✗ Failed to set DPI scaling: {stderr or 'Unknown error'}", "error"
            )
            self.show_message(
                "Error",
                f"Failed to set DPI scaling:\n{stderr or 'Unknown error'}",
                "error",
            )

    def get_wine_user_dir(self):
        """Return the current Wine user's home directory inside the prefix."""
        username = os.environ.get("USER") or os.environ.get("LOGNAME") or Path.home().name
        return Path(self.directory) / "drive_c" / "users" / username

    def configure_file_dialog_shortcuts(self):
        """Add quick-access shortcuts for Wine file dialogs."""
        self.log("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log("Configure Wine File Dialog Shortcuts", "info")
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        prefix_dir = Path(self.directory)
        user_dir = self.get_wine_user_dir()
        dosdevices_dir = prefix_dir / "dosdevices"
        favorites_dir = user_dir / "Favorites"
        links_dir = user_dir / "Links"
        home_dir = Path.home()

        if not prefix_dir.exists():
            self.log("Wine prefix not found. Please set up Wine first.", "error")
            self.show_message(
                "Wine Prefix Not Found",
                "The Wine prefix does not exist yet.\n\nPlease run 'Setup Wine Environment' first.",
                "error"
            )
            return

        created_items = []
        skipped_items = []

        def ensure_shortcut(link_path, target_path):
            target_path = Path(target_path)
            if not target_path.exists():
                return False, f"target missing: {target_path}"

            try:
                link_path.parent.mkdir(parents=True, exist_ok=True)
                if link_path.is_symlink():
                    current_target = Path(os.path.realpath(link_path))
                    if current_target == target_path.resolve():
                        return False, None
                    link_path.unlink()
                elif link_path.exists():
                    return False, f"kept existing entry: {link_path.name}"

                link_path.symlink_to(target_path)
                return True, None
            except Exception as e:
                return False, str(e)

        shortcut_targets = {
            "Home": home_dir,
            "Desktop": home_dir / "Desktop",
            "Documents": home_dir / "Documents",
            "Downloads": home_dir / "Downloads",
            "Pictures": home_dir / "Pictures",
        }

        for folder in (favorites_dir, links_dir):
            folder.mkdir(parents=True, exist_ok=True)
            for label, target in shortcut_targets.items():
                created, info = ensure_shortcut(folder / label, target)
                if created:
                    created_items.append(str(folder / label))
                    self.log(f"Created file dialog shortcut: {folder / label} -> {target}", "success")
                elif info:
                    skipped_items.append(f"{folder / label}: {info}")

        home_drive = dosdevices_dir / "h:"
        created, info = ensure_shortcut(home_drive, home_dir)
        if created:
            created_items.append(str(home_drive))
            self.log(f"Created Home drive mapping: {home_drive} -> {home_dir}", "success")
        elif info:
            skipped_items.append(f"{home_drive}: {info}")

        if created_items:
            self.log("Wine file dialog shortcuts updated", "success")
            message = (
                "Wine file dialog shortcuts were updated successfully.\n\n"
                "You should now see easier access to your Linux home folder:\n"
                "• H: drive mapped to your home directory\n"
                "• Home/Documents/Downloads/Pictures shortcuts under Favorites and Links\n\n"
                "Restart Affinity if its file dialog is already open."
            )
            if skipped_items:
                message += "\n\nSome existing entries were kept unchanged:\n" + "\n".join(skipped_items[:8])
            self.show_message("File Dialog Shortcuts Updated", message, "info")
            return

        self.log("No file dialog shortcuts were changed", "warning")
        message = (
            "No file dialog shortcuts were changed.\n\n"
            "The most likely reason is that the shortcuts already exist, or conflicting non-link entries were left untouched."
        )
        if skipped_items:
            message += "\n\nDetails:\n" + "\n".join(skipped_items[:8])
        self.show_message("No Changes Applied", message, "warning")

    def uninstall_affinity_linux(self):
        """Uninstall Affinity Linux by deleting the install directory (self.directory) — this may be the default ~/.AffinityLinux or a custom location"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Uninstall Affinity Linux", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Show warning dialog with Yes/No buttons
        reply = QMessageBox.warning(
            self,
            "Uninstall Affinity Linux",
            f"WARNING: This will permanently delete the following folder and all its contents:\n{self.directory}\n\n"
            "This includes:\n"
            "• All Wine configuration and settings\n"
            "• All installed Affinity applications (Photo, Designer, Publisher, Unified)\n"
            "• All application data and preferences\n"
            "• All downloaded installers and cached files\n"
            "• WebView2 Runtime and other dependencies\n"
            "• Desktop entries from .local/share/applications\n\n"
            "This action CANNOT be undone!\n\n"
            "Do you want to proceed with the uninstall?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            self.log("Uninstall cancelled by user", "warning")
            return

        # Stop Wine processes first. `wineserver -k` alone leaves msiexec and
        # setup.exe behind, and those hold files open while we delete them.
        self.log("Stopping Wine processes...", "info")
        try:
            if self.stop_prefix_wine_processes(reason="uninstalling", wait_seconds=8):
                self.log("Wine processes stopped", "success")
            else:
                self.log("Warning: some Wine processes may still be running", "warning")
        except Exception as e:
            self.log(f"Warning: Could not stop all Wine processes: {e}", "warning")

        # Remove desktop entries from .local/share/applications
        self.log("Removing desktop entries...", "info")
        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_files = [
            desktop_dir / "AffinityPhoto.desktop",
            desktop_dir / "AffinityDesigner.desktop",
            desktop_dir / "AffinityPublisher.desktop",
            desktop_dir / "Affinity.desktop",
        ]

        removed_count = 0
        for desktop_file in desktop_files:
            if desktop_file.exists():
                try:
                    desktop_file.unlink()
                    self.log(f"Removed desktop entry: {desktop_file.name}", "info")
                    removed_count += 1
                except Exception as e:
                    self.log(
                        f"Warning: Could not remove {desktop_file.name}: {e}", "warning"
                    )

        self.remove_affinity_url_handler()

        # Also remove Wine's default entries if they exist
        wine_desktop_dir = desktop_dir / "wine" / "Programs"
        wine_entries = [
            wine_desktop_dir / "Affinity Photo 2.desktop",
            wine_desktop_dir / "Affinity Photo.desktop",
            wine_desktop_dir / "Affinity Designer 2.desktop",
            wine_desktop_dir / "Affinity Designer.desktop",
            wine_desktop_dir / "Affinity Publisher 2.desktop",
            wine_desktop_dir / "Affinity Publisher.desktop",
            wine_desktop_dir / "Affinity.desktop",
        ]

        for wine_entry in wine_entries:
            if wine_entry.exists():
                try:
                    wine_entry.unlink()
                    self.log(f"Removed Wine desktop entry: {wine_entry.name}", "info")
                    removed_count += 1
                except Exception as e:
                    self.log(
                        f"Warning: Could not remove {wine_entry.name}: {e}", "warning"
                    )

        if removed_count > 0:
            self.log(f"Removed {removed_count} desktop entry/entries", "success")

        # Delete the install directory (default or custom location)
        affinity_dir = Path(self.directory)
        if not affinity_dir.exists():
            self.log(
                f"Affinity Linux directory not found at {affinity_dir}. Nothing to uninstall.",
                "warning",
            )
            self.show_message(
                "Nothing to Uninstall",
                f"The install folder does not exist:\n{affinity_dir}\n\nNothing to uninstall.",
                "info",
            )
            return

        self.log(f"Deleting directory: {affinity_dir}", "info")
        try:

            def _force_remove(func, path, exc_info):
                """Error handler: chmod and retry for read-only files"""
                try:
                    os.chmod(path, 0o777)
                    func(path)
                except Exception:
                    pass

            shutil.rmtree(str(affinity_dir), onerror=_force_remove)

            # If rmtree left anything behind, fall back to rm -rf
            if affinity_dir.exists():
                self.log(
                    "Standard removal incomplete, falling back to rm -rf...", "warning"
                )
                result = subprocess.run(
                    ["rm", "-rf", str(affinity_dir)],
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=600,
                )
                if result.returncode != 0:
                    raise Exception(f"rm -rf failed: {result.stderr.strip()}")

            self.log(f"\u2713 {affinity_dir} deleted successfully", "success")
            self.log("\n✓ Uninstall completed!", "success")
            self.log("All Affinity Linux files have been removed.", "info")

            deleted_path = str(affinity_dir)

            # Forget any custom install location — it no longer exists, so a
            # future launch should fall back to the default ~/.AffinityLinux.
            self._clear_persisted_install_location()
            self.directory = str(Path.home() / ".AffinityLinux")
            # And drop the pin. Leaving _forced_directory set meant the next
            # install in the same window skipped the custom-location prompt
            # entirely and landed on ~/.AffinityLinux -- the working prefix --
            # without asking.
            self._forced_directory = None

            self.show_message(
                "Uninstall Complete",
                f"{deleted_path} has been successfully deleted.\n\n"
                "All Affinity installations and configurations have been removed.\n\n"
                "You may close this installer now.",
                "info",
            )

            # Refresh installation status
            self.refresh_status_signal.emit()

        except PermissionError:
            self.log("✗ Permission denied. Some files may be in use.", "error")
            self.log("Please close all Affinity applications and try again.", "error")
            self.show_message(
                "Uninstall Failed",
                "Permission denied. Some files may be in use.\n\n"
                "Please close all Affinity applications and Wine processes, then try again.",
                "error",
            )
        except Exception as e:
            self.log(f"✗ Failed to delete directory: {e}", "error")
            self.show_message(
                "Uninstall Failed",
                f"Failed to delete {affinity_dir}:\n\n{str(e)}\n\n"
                "You may need to manually delete it.",
                "error",
            )

    def launch_affinity_v3(self):
        """Launch Affinity v3 with optimized environment variables"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Launch Affinity v3", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Check if Affinity is installed
        affinity_exe = (
            Path(self.directory)
            / "drive_c"
            / "Program Files"
            / "Affinity"
            / "Affinity"
            / "Affinity.exe"
        )
        if not affinity_exe.exists():
            self.log("✗ Affinity v3 is not installed", "error")
            self.log(
                "Please install Affinity v3 first using 'Update Affinity Applications' → 'Affinity (Unified)'",
                "info",
            )
            self.show_message(
                "Affinity Not Found",
                "Affinity v3 is not installed.\n\nPlease install it first using:\n'Update Affinity Applications' → 'Affinity (Unified)'",
                QMessageBox.Icon.Warning,
            )
            return

        # Check if Wine is set up
        wine_bin = self.get_wine_path("wine")
        if not wine_bin.exists():
            self.log("✗ Wine is not set up", "error")
            self.log("Please run 'Setup Wine Environment' first", "info")
            self.show_message(
                "Wine Not Found",
                "Wine is not set up.\n\nPlease run 'Setup Wine Environment' first.",
                QMessageBox.Icon.Warning,
            )
            return

        if self.affinity_v3_user_data_has_startup_corruption_signature():
            self.quarantine_affinity_v3_user_data(
                "Detected a previous Affinity v3 startup log with the JPEG XL corruption signature."
            )

        self.log("Setting up environment variables...", "info")

        synced_mscms_runtime = self.sync_mscms_shim_into_app_dir(affinity_exe.parent, "Affinity")
        # Prepare environment variables
        env = os.environ.copy()

        # Set PATH to include Wine binaries (only for custom Wine builds)
        wine_dir = self.get_wine_dir()
        if wine_dir:
            wine_dir_str = str(wine_dir)
            current_path = env.get("PATH", "")
            env["PATH"] = f"{wine_dir_str}/bin:{current_path}"
        # For system Wine, it's already in PATH

        # Set Wine-related environment variables
        env["WINE"] = str(wine_bin)
        env["WINEPREFIX"] = self.directory
        env["WINEDEBUG"] = "-all,fixme-all"
        dll_overrides = ["d3d12=n,b", "d3d12core=n,b"]
        if synced_mscms_runtime or (affinity_exe.parent / "mscms.dll").exists():
            dll_overrides.append("mscms=n,b")
            if synced_mscms_runtime:
                self.log("Enabled the local mscms compatibility shim for Affinity", "info")
        env["WINEDLLOVERRIDES"] = ";".join(dll_overrides)
        env.setdefault("DISPLAY", os.environ.get("DISPLAY", ":0"))
        xauthority = os.environ.get("XAUTHORITY")
        if xauthority:
            env["XAUTHORITY"] = xauthority

        wineserver_bin = self.get_wine_path("wineserver")
        if wineserver_bin.exists():
            env["WINESERVER"] = str(wineserver_bin)

        self.force_wine_x11_driver_if_needed(env)
        # Add GPU selection environment variables if configured
        selected_gpu = self.get_selected_gpu()
        gpu_env = self.get_gpu_env_vars(selected_gpu)
        if gpu_env:
            # Parse GPU env vars and add to environment
            for env_var in gpu_env.strip().split():
                if "=" in env_var:
                    key, value = env_var.split("=", 1)
                    env[key] = value

        session_type = (os.environ.get("XDG_SESSION_TYPE") or "").lower()

        # Check renderer setting - only set DXVK/VKD3D if Vulkan is selected
        renderer = self.get_renderer_setting()

        if renderer == "vulkan":
            synced_runtime = self.sync_vkd3d_runtime_into_app_dir(affinity_exe.parent, "Affinity")
            if synced_runtime:
                self.log("Updated the local vkd3d-proton runtime for Affinity", "info")

            env.update(self.get_vulkan_runtime_env_vars(selected_gpu))
            if session_type == "wayland":
                self.log(
                    "Wayland session detected; disabling VK_KHR_present_id and VK_KHR_present_wait for KWin/XWayland stability.",
                    "info",
                )

            vulkan_device_env = self.get_vulkan_device_select_env(selected_gpu)
            if vulkan_device_env:
                env.update(vulkan_device_env)
                selector = vulkan_device_env.get("MESA_VK_DEVICE_SELECT")
                if selector:
                    self.log(f"Forcing Vulkan device selection to {selector}", "info")
        else:
            # For OpenGL or GDI, disable DXVK/VKD3D to prevent Vulkan initialization errors
            # Also disable DLL overrides that might force Vulkan
            env["DXVK_STATE_CACHE"] = "0"
            env["DXVK_HUD"] = "0"
            # Don't set VKD3D variables for OpenGL/GDI
            self.log(
                f"Renderer is set to {renderer.upper()}, DXVK/VKD3D disabled", "info"
            )

            # If OpenGL/GDI is selected and OpenCL is disabled, remove d3d12 DLL overrides
            # that might force Vulkan usage
            if not self.is_opencl_enabled():
                self.log(
                    "Removing d3d12 DLL overrides to prevent Vulkan initialization",
                    "info",
                )
                try:
                    wine = self.get_wine_path("wine")
                    reg_env = os.environ.copy()
                    reg_env["WINEPREFIX"] = self.directory
                    # Remove d3d12 and d3d12core overrides
                    self.run_command(
                        [
                            str(wine),
                            "reg",
                            "delete",
                            "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                            "/v",
                            "d3d12",
                            "/f",
                        ],
                        check=False,
                        env=reg_env,
                        capture=True,
                    )
                    self.run_command(
                        [
                            str(wine),
                            "reg",
                            "delete",
                            "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides",
                            "/v",
                            "d3d12core",
                            "/f",
                        ],
                        check=False,
                        env=reg_env,
                        capture=True,
                    )
                except Exception as e:
                    self.log(
                        f"Warning: Could not remove d3d12 DLL overrides: {e}", "warning"
                    )

        # Prefer AffinityHook.exe if AffinityPluginLoader has been installed —
        # launching Affinity.exe directly bypasses the hook, so the plugin
        # loader silently never loads even though it's installed correctly.
        hook_exe = affinity_exe.parent / "AffinityHook.exe"
        if hook_exe.exists():
            launch_target = "C:/Program Files/Affinity/Affinity/AffinityHook.exe"
            self.log("AffinityPluginLoader detected — launching via AffinityHook.exe", "info")
        else:
            launch_target = "C:/Program Files/Affinity/Affinity/Affinity.exe"

        self.log("✓ Environment variables configured", "success")
        self.log(f"Wine: {wine_bin}", "info")
        self.log(f"WINEPREFIX: {self.directory}", "info")
        self.log(f"Affinity: {affinity_exe}", "info")

        # Launch Affinity directly; wine start was less reliable for Affinity v3 here.
        self.log("\nLaunching Affinity v3...", "info")

        wine_launch_cmd = [
            str(wine_bin),
            str(affinity_exe)
        ]
        launch_prefix = self.get_gpu_launch_prefix()
        if launch_prefix:
            wine_launch_cmd = launch_prefix + wine_launch_cmd

        try:
            # Launch in background (non-blocking)
            process = subprocess.Popen(
                wine_launch_cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            self.log("✓ Affinity v3 launched successfully", "success")
            self.log("The application should open in a moment...", "info")

        except Exception as e:
            self.log(f"✗ Failed to launch Affinity v3: {e}", "error")
            self.show_message(
                "Launch Failed",
                f"Failed to launch Affinity v3:\n\n{str(e)}",
                QMessageBox.Icon.Critical,
            )

    def download_affinity_installer(self):
        """Download the Affinity installer by itself"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Download Affinity Installer", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Ask user where to save the file
        downloads_dir = Path.home() / "Downloads"
        default_path = downloads_dir / "Affinity-x64.exe"

        # Suggest Downloads folder by default, but let user choose
        suggested_path = str(default_path)

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Affinity Installer",
            suggested_path,
            "Executable files (*.exe);;All files (*.*)",
        )

        if not save_path:
            self.log("Download cancelled.", "warning")
            return

        save_path_obj = Path(save_path)

        # Start operation and thread to download
        self.start_operation("Download Affinity Installer")
        threading.Thread(
            target=self._download_affinity_installer_thread,
            args=(save_path_obj,),
            daemon=True,
        ).start()

        # The rest of the logic should be in the _download_affinity_installer_thread method
        # This is just a placeholder to fix the syntax error
        pass



    def _extract_zip_verified(self, zip_path, dest_dir):
        """Extract a zip file into dest_dir, verifying every member extracts successfully.

        Returns True on success, False (with error logged) on failure.
        """
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(str(zip_path), "r") as zf:
                members = zf.namelist()
                self.log(f"  Archive contains {len(members)} file(s)", "info")
                failed = []
                for member in members:
                    try:
                        zf.extract(member, str(dest_dir))
                    except Exception as ex:
                        failed.append((member, str(ex)))

                if failed:
                    self.log(f"  ✗ {len(failed)} file(s) failed to extract:", "error")
                    for name, err in failed:
                        self.log(f"    • {name}: {err}", "error")
                    return False

                # Post-extraction verification: every file that isn't a dir must exist
                verify_errors = []
                for member in members:
                    if member.endswith("/"):
                        continue  # directory entry
                    target = dest_dir / member
                    if not target.exists():
                        verify_errors.append(member)

                if verify_errors:
                    self.log(
                        f"  ✗ {len(verify_errors)} file(s) missing after extraction:",
                        "error",
                    )
                    for name in verify_errors:
                        self.log(f"    • {name}", "error")
                    return False

                self.log(
                    f"  ✓ All {len(members)} entries extracted and verified", "success"
                )
                return True

        except zipfile.BadZipFile as e:
            self.log(f"  ✗ Bad zip file {zip_path.name}: {e}", "error")
            return False
        except Exception as e:
            self.log(f"  ✗ Extraction error for {zip_path.name}: {e}", "error")
            return False

    def _copy_tree_verified(self, src_dir, dst_dir):
        """Recursively copy src_dir contents into dst_dir, logging each file."""
        src_dir = Path(src_dir)
        dst_dir = Path(dst_dir)
        copied = 0
        for src_file in src_dir.rglob("*"):
            if src_file.is_dir():
                continue
            rel = src_file.relative_to(src_dir)
            dst_file = dst_dir / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src_file), str(dst_file))
            self.log(f"  ✓ {rel}", "success")
            copied += 1
        self.log(f"  Copied {copied} file(s) total", "info")

    def _infer_app_path_for_desktop_file(self, desktop_file):
        """Deterministically resolve the correct, fully-qualified exe path for a
        known Affinity*.desktop file, keyed off its filename. Used as the
        fallback when an existing Exec= line can't be reliably parsed (e.g. the
        exe path isn't quoted). Deliberately does NOT fall back to naive
        whitespace-splitting of the Exec= line, since a bare space inside
        "Program Files" causes that approach to truncate the path down to just
        "Files/Affinity/Affinity/AffinityHook.exe"."""
        base = Path(self.directory) / "drive_c" / "Program Files" / "Affinity"
        name = desktop_file.name
        if name == "Affinity.desktop":
            install_dir = base / "Affinity"
            hook_exe = install_dir / "AffinityHook.exe"
            exe = "AffinityHook.exe" if hook_exe.exists() else "Affinity.exe"
            return str(install_dir / exe).replace("\\", "/")
        if name == "AffinityPhoto.desktop":
            return str(base / "Photo 2" / "Photo.exe").replace("\\", "/")
        if name == "AffinityDesigner.desktop":
            return str(base / "Designer 2" / "Designer.exe").replace("\\", "/")
        if name == "AffinityPublisher.desktop":
            return str(base / "Publisher 2" / "Publisher.exe").replace("\\", "/")
        return None

    def _build_affinity_exec_line(self, prefer_hook=True):
        """Deterministically build a correct, fully-qualified Exec= line for the
        Affinity (Unified) app, rather than trying to parse/patch whatever text
        happens to already be in a .desktop file.

        Using AffinityHook.exe (when present and prefer_hook is True) instead of
        Affinity.exe is what makes AffinityPluginLoader actually load. Building the
        line from known-good Path objects (instead of regex/whitespace parsing of
        an existing Exec= line) avoids corrupting the path — e.g. the space inside
        "Program Files" previously caused naive whitespace-splitting fallbacks
        elsewhere in this file to truncate the path down to just
        "Files/Affinity/Affinity/AffinityHook.exe".
        """
        install_dir = (
            Path(self.directory) / "drive_c" / "Program Files" / "Affinity" / "Affinity"
        )
        hook_exe = install_dir / "AffinityHook.exe"
        handler_exe = install_dir / "affinity-on-linux.exe"

        # affinity-on-linux.exe wins over both when it is installed: it is what
        # lets a document be opened from the file manager, and a cold start still
        # goes through AffinityHook.exe, so preferring it here does not stop the
        # plugin loader from loading. Without it, behaviour is unchanged.
        if handler_exe.exists():
            exe_name = "affinity-on-linux.exe"
        elif prefer_hook and hook_exe.exists():
            exe_name = "AffinityHook.exe"
        else:
            exe_name = "Affinity.exe"
        app_path_str = str(install_dir / exe_name).replace("\\", "/")

        wine_str = str(self.get_wine_path("wine"))
        directory_str = str(self.directory).rstrip("/")

        # get_gpu_env_vars()/get_dxvk_env_vars() already return a trailing space
        # when non-empty, so strip before joining to avoid doubled-up spaces.
        gpu_env = self.get_gpu_env_vars().strip()
        dxvk_env = self.get_dxvk_env_vars().strip()

        segments = [f"env WINEPREFIX={directory_str}"]
        if gpu_env:
            segments.append(gpu_env)
        if dxvk_env:
            segments.append(dxvk_env)
        segments.append(wine_str)
        segments.append(f'"{app_path_str}"')
        # %F, not %f: every selected document goes to one invocation rather than
        # racing one process per file.
        if exe_name == "affinity-on-linux.exe":
            segments.append("%F")

        return "Exec=" + " ".join(segments), exe_name

    def _patch_affinity_desktop_for_hook(self):
        """Rewrite ~/.local/share/applications/Affinity.desktop's Exec= line so it
        launches AffinityHook.exe (via a deterministically rebuilt, fully-qualified
        path) instead of Affinity.exe. Creates the desktop entry if it doesn't
        exist yet, since the plugin loader install can run before any entry has
        been created."""
        desktop_file = (
            Path.home() / ".local" / "share" / "applications" / "Affinity.desktop"
        )
        if not self.manages_host_entries():
            return
        # The fixed-name entry may launch another prefix; rewriting its Exec=
        # moved the menu entry and document double-click to this one.
        if desktop_file.exists() and not self._entry_serves_this_prefix(desktop_file):
            self.log(f"Leaving {desktop_file.name}: it launches another prefix", "info")
            return

        if not desktop_file.exists():
            self.log(
                f"⚠ Affinity.desktop not found at {desktop_file} — creating it",
                "warning",
            )
            try:
                self.create_desktop_entry("Add")
            except Exception as e:
                self.log(f"✗ Failed to create Affinity.desktop: {e}", "error")
                return

        self.log(f"\nPatching {desktop_file}...", "info")
        try:
            with open(desktop_file, "r") as f:
                lines = f.readlines()

            new_exec_line, exe_name = self._build_affinity_exec_line(prefer_hook=True)

            new_lines = []
            patched = False
            for line in lines:
                if line.startswith("Exec="):
                    original = line.rstrip()
                    new_lines.append(new_exec_line + "\n")
                    patched = True
                    self.log(f"  Before: {original}", "info")
                    self.log(f"  After:  {new_exec_line}", "success")
                else:
                    new_lines.append(line)

            if not patched:
                # No Exec= line was found at all — append one.
                new_lines.append(new_exec_line + "\n")
                patched = True

            with open(desktop_file, "w") as f:
                f.writelines(new_lines)
            self.log(
                f"✓ Affinity.desktop updated to launch {exe_name}", "success"
            )
            self.create_affinity_url_handler()

        except Exception as e:
            self.log(f"✗ Failed to patch Affinity.desktop: {e}", "error")

    def install_affinity_plugin_loader(self):
        """Download and install the latest AffinityPluginLoader + WineFix from GitHub"""
        self.log(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        self.log("Install AffinityPluginLoader + WineFix", "info")
        self.log(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        install_dir = (
            Path(self.directory) / "drive_c" / "Program Files" / "Affinity" / "Affinity"
        )
        if not install_dir.exists():
            self.log("✗ Affinity installation directory not found:", "error")
            self.log(f"  {install_dir}", "error")
            self.log("Please install Affinity first.", "info")
            self.show_message(
                "Affinity Not Installed",
                f"Could not find:\n{install_dir}\n\nPlease install Affinity first.",
                QMessageBox.Icon.Warning,
            )
            return

        self.start_operation("Install AffinityPluginLoader")
        threading.Thread(
            target=self._install_affinity_plugin_loader_thread, daemon=True
        ).start()

    def _install_affinity_plugin_loader_thread(self, standalone=True):
        """Worker thread: fetch latest release, download both zips, extract, patch desktop file"""
        try:
            install_dir = (
                Path(self.directory)
                / "drive_c"
                / "Program Files"
                / "Affinity"
                / "Affinity"
            )

            # ── 1. Fetch the pinned release's metadata ────────────────────────────────
            self.log(f"Fetching plugin loader release {APL_RELEASE_TAG}...", "info")
            api_url = apl_release_api_url()
            request = urllib.request.Request(api_url)
            request.add_header("User-Agent", "AffinityLinuxInstaller")

            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    release_data = json.loads(response.read().decode())
            except Exception as e:
                self.log(f"✗ Failed to fetch release info: {e}", "error")
                if standalone:
                    self.end_operation()
                return

            tag = release_data.get("tag_name", "unknown")
            assets = release_data.get("assets", [])
            self.log(f"Release: {tag}", "info")

            if not assets:
                self.log("✗ No assets found in the release.", "error")
                if standalone:
                    self.end_operation()
                return

            # ── 2. Locate the two zip assets by prefix ────────────────────────────────
            apl_asset = next(
                (
                    a
                    for a in assets
                    if a["name"].lower().startswith("affinitypluginloader")
                    and a["name"].endswith(".zip")
                ),
                None,
            )
            winefix_asset = next(
                (
                    a
                    for a in assets
                    # Released as apl-winefix-*.zip up to v0.2.x and winefix-*.zip
                    # since. Accept either, or an older pinned release installs
                    # nothing and the whole plugin-loader step aborts.
                    if (
                        a["name"].lower().startswith("winefix")
                        or a["name"].lower().startswith("apl-winefix")
                    )
                    and a["name"].endswith(".zip")
                ),
                None,
            )

            if not apl_asset:
                self.log(
                    "✗ Could not find affinitypluginloader zip in release assets.",
                    "error",
                )
                self.log("Assets found:", "info")
                for a in assets:
                    self.log(f"  - {a['name']}", "info")
                if standalone:
                    self.end_operation()
                return

            if not winefix_asset:
                self.log(
                    "✗ Could not find a winefix-*.zip or apl-winefix-*.zip in release assets.",
                    "error",
                )
                self.log("Assets found:", "info")
                for a in assets:
                    self.log(f"  - {a['name']}", "info")
                if standalone:
                    self.end_operation()
                return

            self.log(f"Found: {apl_asset['name']}", "success")
            self.log(f"Found: {winefix_asset['name']}", "success")

            # ── 3. Download and extract each zip into a temp directory ─────────────────
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)

                for asset, label in [
                    (apl_asset, "AffinityPluginLoader"),
                    (winefix_asset, "WineFix"),
                ]:
                    url = asset["browser_download_url"]
                    dest_zip = tmp_path / asset["name"]
                    self.log(f"Downloading {label} ({asset['name']})...", "info")
                    self.update_progress(0)

                    try:

                        def _progress(block_num, block_size, total_size):
                            if total_size > 0:
                                pct = min(
                                    100.0, block_num * block_size / total_size * 100
                                )
                                self.update_progress(pct)

                        urllib.request.urlretrieve(
                            url, str(dest_zip), reporthook=_progress
                        )
                        self.update_progress(100)
                        self.log(f"✓ Downloaded {asset['name']}", "success")
                    except Exception as e:
                        self.log(f"✗ Failed to download {asset['name']}: {e}", "error")
                        if standalone:
                            self.end_operation()
                        return

                    # The build this installer pins, or nothing: a release
                    # re-uploaded or renamed under the same tag is refused.
                    want = APL_ASSET_SHA256.get(asset["name"])
                    got = _sha256_of(dest_zip)
                    if got != want:
                        self.log(
                            f"✗ {asset['name']} is not the build this installer pins "
                            f"(got {got[:16]}..., wanted {(want or 'no pin')[:16]}...). "
                            "Not installing it.",
                            "error",
                        )
                        if standalone:
                            self.end_operation()
                        return
                    self.log(f"✓ {asset['name']}: checksum matches", "success")

                    # Verify it is a valid zip
                    if not zipfile.is_zipfile(str(dest_zip)):
                        self.log(
                            f"✗ Downloaded file is not a valid zip: {asset['name']}",
                            "error",
                        )
                        if standalone:
                            self.end_operation()
                        return

                    extract_dir = tmp_path / f"extracted_{label}"
                    extract_dir.mkdir()

                    self.log(f"Extracting {label}...", "info")
                    try:
                        with zipfile.ZipFile(str(dest_zip), "r") as zf:
                            members = zf.namelist()
                            self.log(f"  Contents: {', '.join(members)}", "info")
                            zf.extractall(str(extract_dir))
                        self.log(f"✓ Extracted {label}", "success")
                    except Exception as e:
                        self.log(f"✗ Failed to extract {asset['name']}: {e}", "error")
                        if standalone:
                            self.end_operation()
                        return

                    # ── 4. Copy files into the Affinity install directory ──────────────
                    self.log(
                        f"Installing {label} files into Affinity directory...", "info"
                    )
                    installed_count = 0
                    try:
                        for item in extract_dir.rglob("*"):
                            if item.is_file():
                                # Preserve relative sub-directory structure (e.g. apl/d2d1.dll)
                                relative = item.relative_to(extract_dir)
                                dest_file = install_dir / relative
                                dest_file.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(str(item), str(dest_file))
                                self.log(f"  Installed: {relative}", "info")
                                installed_count += 1
                    except Exception as e:
                        self.log(f"✗ Failed to copy {label} files: {e}", "error")
                        if standalone:
                            self.end_operation()
                        return

                    if installed_count == 0:
                        self.log(
                            f"⚠ No files were installed from {label} — archive may be empty or structured unexpectedly.",
                            "warning",
                        )
                    else:
                        self.log(
                            f"✓ {label}: {installed_count} file(s) installed", "success"
                        )

                    # WineFix's d2d1.dll ships under apl/ in the zip, and the loop
                    # above preserves that. It has to end up BESIDE Affinity.exe:
                    # Wine resolves a DLL through the executable's own directory,
                    # which is how this copy shadows Wine's d2d1 at all. Left under
                    # apl/ it is never loaded and WineFix silently does nothing.
                    #
                    # Newer WineFix ships no d2d1.dll at all: its Direct2D fixes
                    # are runtime patches applied to the d2d1 Wine provides. A
                    # copy left beside Affinity.exe by an older WineFix -- built
                    # from Wine 10.18 -- would go on shadowing Wine's, so it is
                    # renamed aside rather than left to win.
                    if label == "WineFix":
                        beside = install_dir / "d2d1.dll"
                        found = next(
                            (f for f in extract_dir.rglob("d2d1.dll") if f.is_file()),
                            None,
                        )
                        if found:
                            if not beside.exists():
                                shutil.copy2(str(found), str(beside))
                                self.log(
                                    f"  Moved d2d1.dll up from {found.relative_to(extract_dir)}"
                                    " so Affinity.exe can find it",
                                    "success",
                                )
                            self.log("  ✓ d2d1.dll is beside Affinity.exe", "success")
                        elif beside.exists():
                            aside = beside.with_name("d2d1.dll.winefix-old")
                            beside.replace(aside)
                            self.log(
                                "  ✓ This WineFix patches Wine's own d2d1 at runtime; "
                                f"the old copy beside Affinity.exe is now {aside.name}",
                                "success",
                            )
                        else:
                            self.log(
                                "  ✓ WineFix patches Wine's own d2d1 at runtime", "success"
                            )

            # ── 5. Verify AffinityHook.exe is present after install ───────────────────
            hook_exe = install_dir / "AffinityHook.exe"
            if not hook_exe.exists():
                self.log(
                    "⚠ AffinityHook.exe not found after installation — desktop file will NOT be patched.",
                    "warning",
                )
                self.log(
                    "  The plugin files were installed but the launcher hook is missing.",
                    "warning",
                )
                if standalone:
                    self.end_operation()
                return

            self.log("✓ AffinityHook.exe confirmed present", "success")

            # ── 6. Inform user, then immediately run AffinityHook ────────────────────
            self.log(
                "\nInforming user about AffinityPluginLoader installation...", "info"
            )
            self.show_message(
                "AffinityPluginLoader Installed",
                "AffinityPluginLoader + WineFix have been installed!\n\n"
                "The installer will now run AffinityHook.exe once in the background "
                "to complete its initialisation.\n\n"
                "You do not need to do anything — this will take a few seconds.",
                "info",
            )
            self.log("Running AffinityHook.exe to complete initialisation...", "info")
            try:
                # Use the exact same wine + env as the .desktop entry does
                wine_bin = str(self.get_wine_path("wine"))
                hook_exe_path = str(
                    Path(self.directory)
                    / "drive_c"
                    / "Program Files"
                    / "Affinity"
                    / "Affinity"
                    / "AffinityHook.exe"
                )
                env = os.environ.copy()
                env["WINEPREFIX"] = self.directory
                env["WINEDEBUG"] = "-all,fixme-all"
                # Apply GPU and DXVK env vars exactly as the .desktop does
                gpu_env = self.get_gpu_env_vars()
                dxvk_env = self.get_dxvk_env_vars()
                if gpu_env:
                    for var in gpu_env.strip().split():
                        if "=" in var:
                            k, v = var.split("=", 1)
                            env[k] = v
                if dxvk_env:
                    for var in dxvk_env.strip().split():
                        if "=" in var:
                            k, v = var.split("=", 1)
                            env[k] = v
                self.log(f'Launching: {wine_bin} "{hook_exe_path}"', "info")
                proc = subprocess.Popen(
                    [wine_bin, hook_exe_path],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.log(
                    "AffinityHook.exe launched — waiting 15 seconds then closing...",
                    "info",
                )
                try:
                    proc.wait(timeout=15)
                    self.log(
                        "AffinityHook.exe exited on its own within 15 seconds.", "info"
                    )
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    wineserver_bin = str(self.get_wine_path("wineserver"))
                    subprocess.run(
                        [wineserver_bin, "-k"],
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    self.log("✓ AffinityHook.exe closed after 15 seconds.", "success")
            except Exception as e:
                self.log(f"⚠ Could not run AffinityHook.exe: {e}", "warning")
                self.log("  You may need to run it once manually.", "info")

            # ── 7. Patch Affinity.desktop to launch AffinityHook.exe ─────────────────
            self.log("\nPatching Affinity.desktop to use AffinityHook.exe...", "info")
            self._patch_affinity_desktop_for_hook()

            self.log(
                "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "info",
            )
            self.log("AffinityPluginLoader + WineFix installation complete!", "success")
            self.log(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
                "info",
            )
            if standalone:
                self.end_operation()

        except Exception as e:
            self.log(
                f"✗ Unexpected error during AffinityPluginLoader installation: {e}",
                "error",
            )
            if standalone:
                self.end_operation()

    def show_thanks(self):
        """Show special thanks window"""
        thanks = QMessageBox()  # No parent to avoid threading issues
        thanks.setWindowTitle("Special Thanks")
        thanks.setStyleSheet(self.get_messagebox_stylesheet())
        thanks.setText(
            "Special Thanks\n\n"
            "Ardishco (github.com/raidenovich)\n"
            "Deviaze\n"
            "Kemal\n"
            "Jacazimbo <3\n"
            "Kharoon\n"
            "Jediclank134"
        )
        thanks.setStandardButtons(QMessageBox.StandardButton.Ok)
        thanks.adjustSize()
        thanks.exec()


HELPER_NAMES = ("winetricks", "winedevice.exe", "winedevice", "wineserver")


def _prefix_of_pid(pid):
    """The WINEPREFIX a process itself was started with, resolved, or None.

    A process's own environment is the only trustworthy answer. Matching on the
    command line instead is what made this function dangerous."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            for entry in f.read().split(b"\0"):
                if entry.startswith(b"WINEPREFIX="):
                    value = entry[len("WINEPREFIX="):].decode("utf-8", "replace")
                    return os.path.realpath(os.path.expanduser(value))
    except OSError:
        pass
    return None


def _looks_like_wine_helper(pid):
    """Is this one of the helper processes worth clearing?

    Checked against both comm and the command line's own basenames: comm is
    truncated at 15 characters and, for winetricks, names the interpreter rather
    than the script. Being liberal here is safe because the caller still
    requires the WINEPREFIX to match."""
    try:
        with open(f"/proc/{pid}/comm") as f:
            if f.read().strip() in HELPER_NAMES:
                return True
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            argv = f.read().split(b"\0")
    except OSError:
        return False
    for arg in argv:
        if not arg:
            continue
        if os.path.basename(arg.decode("utf-8", "replace")) in HELPER_NAMES:
            return True
    return False


def cleanup_target_prefix():
    """The prefix this run is going to install into.

    Resolved the same way the window will resolve it, and available here because
    parse_overrides() has already put any --install-dir into the environment."""
    directory = os.environ.get(ENV_INSTALL_DIR, "").strip()
    if not directory:
        try:
            saved = Path.home() / ".config" / "AffinityOnLinux" / "install_location"
            if saved.exists():
                directory = saved.read_text().strip()
        except OSError:
            directory = ""
    if not directory:
        directory = str(Path.home() / ".AffinityLinux")
    return os.path.realpath(os.path.expanduser(directory))


def kill_stalled_wine_processes(prefix=None):
    """Clear leftover winetricks/winedevice/wineserver processes IN THE PREFIX
    THIS RUN WILL INSTALL INTO, so the installer does not start on top of a
    stalled one.

    It used to run `pkill -9 -x` and `pkill -9 -f` over "winetricks",
    "winedevice" and "wineserver" with no scoping at all. `-f` matches the whole
    command line, machine-wide, so opening the installer SIGKILLed the wineserver
    of every Wine prefix on the system -- and killing a wineserver takes every
    process it serves with it. On a machine with Affinity open in another prefix
    that meant the session and whatever was unsaved in it, before the window had
    even appeared, and with no way to opt out: this runs before any directory is
    chosen, so --install-dir could not protect you.

    Now each candidate has to name the target prefix in its own environment, and
    if the target prefix has a live Affinity in it nothing is killed at all --
    the point is to clear a stall, not to end a session.

    Returns the lines it would have printed, so a caller that is not a terminal
    can put them where its user will see them. main() prints them; the manager
    puts them in that prefix's log. It used to print unconditionally, which
    meant the hosted installer had to redirect sys.stdout -- process-wide, and
    therefore capturing whatever other threads happened to write at the same
    moment."""
    # Resolved, because _prefix_of_pid resolves what it reads out of
    # /proc/<pid>/environ. Comparing a resolved path with an unresolved one
    # never matches, so with ~/.AffinityLinux reached through any symlinked
    # component this found nothing, killed nothing, and cheerfully reported
    # "no stale Wine processes - starting clean".
    target = os.path.realpath(os.path.expanduser(
        prefix or cleanup_target_prefix()))

    said = []
    live = []
    stale = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        if _prefix_of_pid(pid) != target:
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                comm = f.read().strip()
        except OSError:
            continue
        if comm in ("Affinity.exe", "AffinityHook.ex", "AffinityHook.exe"):
            live.append(pid)
        elif _looks_like_wine_helper(pid):
            stale.append((pid, comm))

    if live:
        said.append(
            f"[Cleanup] Affinity is running in {target} (pid {live[0]}) - "
            "leaving its Wine processes alone. Close it before installing."
        )
        return said

    if not stale:
        said.append(f"[Cleanup] No stale Wine processes in {target} - starting clean")
        return said

    for pid, comm in stale:
        try:
            os.kill(pid, signal.SIGKILL)
            said.append(f"[Cleanup] Killed leftover {comm} (pid {pid}) in {target}")
        except OSError:
            pass
    return said


def parse_overrides(argv):
    """Turn --install-dir / --installer-file into the environment the overrides
    read, so argv and environment cannot disagree and only one path needs
    testing.

    Non-flag arguments are left alone: this script is also piped straight into
    python3, where argv belongs to whatever invoked it. An unrecognised --flag
    is refused, though, because silently dropping it is dangerous here. A
    mistyped `--install-dirr /tmp/scratch` used to be ignored, self.directory
    stayed at the default, and every subsequent operation -- including Uninstall,
    which deletes it -- addressed ~/.AffinityLinux: the working prefix the run
    was trying to stay away from."""
    args = list(argv[1:])
    flags = {"--install-dir": ENV_INSTALL_DIR, "--installer-file": ENV_INSTALLER_FILE}
    i = 0
    while i < len(args):
        arg = args[i]
        name, _, inline = arg.partition("=")
        if name in flags:
            if inline:
                os.environ[flags[name]] = inline
                i += 1
            elif i + 1 < len(args):
                os.environ[flags[name]] = args[i + 1]
                i += 2
            else:
                print(f"{name} needs a value", file=sys.stderr)
                sys.exit(2)
            continue
        if arg in ("-h", "--help"):
            print(
                "AffinityLinuxInstaller.py [--install-dir DIR] [--installer-file EXE]\n"
                "\n"
                f"  --install-dir DIR      install into DIR instead of ~/.AffinityLinux\n"
                f"                         (or ${ENV_INSTALL_DIR})\n"
                f"  --installer-file EXE   install from EXE instead of downloading the\n"
                f"                         current release (or ${ENV_INSTALLER_FILE})\n"
            )
            sys.exit(0)
        if arg.startswith("--"):
            print(
                f"unknown option {name}\n"
                "run with --help for the options this accepts",
                file=sys.stderr,
            )
            sys.exit(2)
        i += 1


def main():
    """Main entry point"""
    import time as time_module

    parse_overrides(sys.argv)

    total_start_time = time_module.time()

    if platform.system() != "Linux":
        app = QApplication(sys.argv)
        QMessageBox.critical(
            None,
            "Unsupported Platform",
            "This installer is designed for Linux systems only.",
        )
        return

    for line in kill_stalled_wine_processes() or []:
        print(line)

    # Enable proper HiDPI / fractional display scaling support
    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    app_init_start = time_module.time()
    app = QApplication(sys.argv)
    app_init_time = time_module.time() - app_init_start

    window_init_start = time_module.time()
    window = AffinityInstallerGUI()
    window_init_time = time_module.time() - window_init_start

    # Show window immediately - slow operations will run in background
    window.show()

    # Process events to ensure window is displayed before background tasks start
    app.processEvents()

    total_init_time = time_module.time() - total_start_time
    print(f"\n[Startup Timing] QApplication init: {app_init_time:.3f}s")
    print(f"[Startup Timing] Window init: {window_init_time:.3f}s")
    print(f"[Startup Timing] Total startup: {total_init_time:.3f}s")
    print(f"[Startup Timing] Window shown immediately - background tasks running...\n")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
