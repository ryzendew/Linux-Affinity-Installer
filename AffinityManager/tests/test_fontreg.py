"""Font registrations: the check the installer runs last, and Check fonts runs on demand.

The bug it repairs: a fresh prefix had the core fonts on disk in windows\\Fonts
but not registered in the 64-bit Fonts keys, and Microsoft Yahei registered
from another Wine's font folder. Affinity's bold UI text fell back to Arial
Narrow and Yahei. The code lives in the installer (one file, piped into
python3), and the manager calls it.

The plan is tested against a fake prefix built here; one test runs the whole
repair through a real Wine, and skips where there is none.
"""
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import aol  # noqa: E402

try:
    inst = aol.module()
    HAVE = hasattr(inst, "repair_font_registrations")
except aol.NotAvailable:
    inst, HAVE = None, False

pytestmark = pytest.mark.skipif(not HAVE, reason="installer without the font check")

NT, WIN = (inst.FONT_KEYS_64 if HAVE else ("", ""))


def font(path, full_name):
    """The smallest file font_full_name can read: a table directory holding
    one 'name' table with name ID 4 for Windows/US English."""
    text = full_name.encode("utf-16-be")
    name = struct.pack(">HHH", 0, 1, 6 + 12) + \
        struct.pack(">HHHHHH", 3, 1, 0x409, 4, len(text), 0) + text
    offset = 12 + 16
    data = struct.pack(">IHHHH", 0x00010000, 1, 0, 0, 0) + \
        struct.pack(">4sIII", b"name", 0, offset, len(name)) + name
    path.write_bytes(data)
    return path


@pytest.fixture
def fonts(tmp_path):
    d = tmp_path / "prefix" / "drive_c" / "windows" / "Fonts"
    d.mkdir(parents=True)
    font(d / "tahoma.ttf", "Tahoma")
    font(d / "tahomabd.ttf", "Tahoma Bold")
    font(d / "arial.ttf", "Arial")
    return d


OWN = "/home/x/.prefix/ElementalWarrior-wine-11.16"


def test_the_name_is_read_from_the_font(fonts):
    assert inst.font_full_name(fonts / "tahomabd.ttf") == "Tahoma Bold"
    assert inst.font_full_name(fonts / "missing.ttf") is None


def test_unregistered_fonts_are_registered_in_both_keys(fonts):
    """The bug: on disk, not registered."""
    registered = {NT: {"Tahoma (TrueType)": "tahoma.ttf"},
                  WIN: {"Tahoma (TrueType)": "tahoma.ttf"}}
    add, remove = inst.plan_font_registry_repair(fonts, registered, {}, OWN)
    assert add == {"Tahoma Bold (TrueType)": "tahomabd.ttf",
                   "Arial (TrueType)": "arial.ttf"}
    patch = inst.font_registry_patch(add, remove)
    for key in ("Windows NT\\CurrentVersion\\Fonts]", "\\Windows\\CurrentVersion\\Fonts]"):
        section = patch.split(key, 1)[1].split("\r\n\r\n", 1)[0]
        assert '"Tahoma Bold (TrueType)"="tahomabd.ttf"' in section


def test_a_font_registered_in_one_key_only_keeps_its_name(fonts):
    """Only the 32-bit view had them in the broken prefix; the name already
    used is the one to repeat, not one made up from the file."""
    registered = {NT: {"Tahoma (TrueType)": "tahoma.ttf", "Arial (TrueType)": "arial.ttf"},
                  WIN: {"Tahoma (TrueType)": "tahoma.ttf", "Arial (TrueType)": "arial.ttf",
                        "Tahoma Gras (TrueType)": "tahomabd.ttf"}}
    add, _ = inst.plan_font_registry_repair(fonts, registered, {}, OWN)
    assert add == {"Tahoma Gras (TrueType)": "tahomabd.ttf"}


def test_a_complete_prefix_needs_nothing(fonts):
    full = {"Tahoma (TrueType)": "tahoma.ttf", "Tahoma Bold (TrueType)": "tahomabd.ttf",
            "Arial (TrueType)": "C:\\windows\\Fonts\\arial.ttf"}
    add, remove = inst.plan_font_registry_repair(fonts, {NT: full, WIN: full}, {}, OWN)
    assert add == {} and remove == {}


def test_fonts_from_another_wine_are_removed_and_host_fonts_kept(fonts):
    full = {"Tahoma (TrueType)": "tahoma.ttf", "Tahoma Bold (TrueType)": "tahomabd.ttf",
            "Arial (TrueType)": "arial.ttf"}
    strays = {
        # the distro Wine's folder -- what the real prefix had
        "Microsoft Yahei (TrueType)": "Z:\\usr\\share\\wine\\fonts\\msyh.ttf",
        # wine-tkg's own folder inside the prefix
        "@Microsoft Yahei (TrueType)":
            "Z:\\home\\x\\.prefix\\wine-tkg\\wine-11.18\\share\\wine\\fonts\\msyh.ttf",
    }
    keep = {
        # the prefix's own Wine: its fonts are its own
        "Wine Own (TrueType)": "Z:\\home\\x\\.prefix\\ElementalWarrior-wine-11.16\\share\\wine\\fonts\\own.ttf",
        # the user's fonts: Wine's normal host integration
        "Noto Sans (TrueType)": "Z:\\usr\\share\\fonts\\noto\\NotoSans-Regular.ttf",
        "Arial Narrow (TrueType)": "Z:\\home\\x\\.fonts\\Clean\\ArialNarrow.ttf",
    }
    both = {**full, **strays, **keep}
    external = {**strays, **keep}
    add, remove = inst.plan_font_registry_repair(fonts, {NT: both, WIN: both}, external, OWN)
    assert add == {}
    for key in (NT, WIN, inst.EXTERNAL_FONTS_KEY):
        assert sorted(remove[key]) == sorted(strays)


def test_names_with_quotes_and_backslashes_survive_the_reg_file():
    patch = inst.font_registry_patch({'Odd "Name" (TrueType)': "o\\dd.ttf"}, {})
    assert '"Odd \\"Name\\" (TrueType)"="o\\\\dd.ttf"' in patch


def test_reg_query_output_is_parsed():
    out = ("\r\nHKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Fonts\r\n"
           "    Tahoma Bold (TrueType)    REG_SZ    tahomabd.ttf\r\n"
           "    @Microsoft Yahei (TrueType)    REG_SZ    Z:\\usr\\share\\wine\\fonts\\msyh.ttf\r\n"
           "    LogPixels    REG_DWORD    0xb7\r\n")
    assert inst.parse_reg_query(out) == {
        "Tahoma Bold (TrueType)": "tahomabd.ttf",
        "@Microsoft Yahei (TrueType)": "Z:\\usr\\share\\wine\\fonts\\msyh.ttf"}


def test_it_never_raises(tmp_path):
    """Called at the end of an install: a font check must not fail one."""
    notes = inst.repair_font_registrations(tmp_path, tmp_path / "no-wine", lambda *a: None)
    assert notes == []


# ── through a real Wine ──────────────────────────────────────────────────────

def _a_wine():
    for candidate in sorted(Path.home().glob(".AffinityLinuxManager/*/ElementalWarrior-wine-11.16/bin/wine")):
        if candidate.exists():
            return candidate
    return None


@pytest.mark.skipif(_a_wine() is None or not os.environ.get("AFFINITY_WINE_TESTS"),
                    reason="builds a real Wine prefix (~1 min): set AFFINITY_WINE_TESTS=1")
def test_end_to_end_in_a_throwaway_prefix(tmp_path):
    wine = _a_wine()
    prefix = tmp_path / "pfx"
    env = dict(os.environ, WINEPREFIX=str(prefix), WINEDEBUG="-all",
               WINEDLLOVERRIDES="mscoree,mshtml=")
    server = wine.parent / "wineserver"
    try:
        subprocess.run([str(wine.parent / "wineboot"), "-i"], env=env, timeout=180,
                       capture_output=True)
        fontdir = prefix / "drive_c" / "windows" / "Fonts"
        font(fontdir / "zzprobe.ttf", "Zz Probe Bold")
        stray = (prefix / "drive_c" / "stray.reg")
        stray.write_text(
            'REGEDIT4\r\n\r\n[HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Fonts]\r\n'
            '"Stray (TrueType)"="Z:\\\\usr\\\\share\\\\wine\\\\fonts\\\\msyh.ttf"\r\n')
        subprocess.run([str(wine), "regedit", "/S", "C:\\stray.reg"], env=env,
                       timeout=60, capture_output=True)
        notes = inst.repair_font_registrations(prefix, wine, lambda *a: None)
        assert "registered Zz Probe Bold (TrueType) (zzprobe.ttf)" in notes
        assert any(n.startswith("removed Stray") for n in notes)
        assert inst.repair_font_registrations(prefix, wine, lambda *a: None) == [], \
            "a second run must find nothing to do"
    finally:
        subprocess.run([str(server), "-k"], env=env, timeout=30, capture_output=True)
        shutil.rmtree(prefix, ignore_errors=True)
