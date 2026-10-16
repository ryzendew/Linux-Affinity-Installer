"""The first run, and carrying settings between prefixes.

Two things are being protected here. That an existing ~/.AffinityLinux is
never quietly taken over or quietly moved -- both are offered, separately, and
the explanation is built from the same facts the action uses so it cannot
drift. And that copying settings into a prefix never destroys what is there
without leaving it recoverable: RecentFiles.xml is the one thing a reinstall
cannot give back.
"""
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import coldstart, discover, prefsseed, registry  # noqa: E402


def make_prefix(path: Path, *, affinity=True) -> Path:
    (path / "drive_c" / "windows").mkdir(parents=True)
    (path / "dosdevices").mkdir(parents=True)
    (path / "dosdevices" / "c:").symlink_to("../drive_c")
    (path / "system.reg").write_text("WINE REGISTRY\n")
    if affinity:
        app = path / "drive_c" / "Program Files" / "Affinity" / "Affinity"
        app.mkdir(parents=True)
        (app / "Affinity.exe").write_text("MZ" + "x" * 400)
    return path


def make_settings(prefix: Path, user="joshua", version="3.0", *, recents=True) -> Path:
    root = prefix / "drive_c" / "users" / user
    settings = root.joinpath(*prefsseed.APPDATA_TAIL) / version / "Settings"
    settings.mkdir(parents=True)
    (settings / "preferences.dat").write_text("mine")
    (settings / "shortcuts").mkdir()
    (settings / "shortcuts" / "keys.xml").write_text("<keys/>")
    if recents:
        (settings / "RecentFiles.xml").write_text("<recent>the year of work</recent>")
    return settings


# ── which situation is this ─────────────────────────────────────────────────

@pytest.fixture
def clean_home(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "manager_dir", lambda: tmp_path / "meta")
    monkeypatch.setattr(registry, "base_dir", lambda: tmp_path / "base")
    monkeypatch.setattr(registry, "base_dir_is_configured", lambda: False)
    (tmp_path / "meta").mkdir()
    return tmp_path


def test_a_list_with_entries_asks_nothing(clean_home):
    reg = registry.Registry(clean_home / "meta" / "prefixes.json")
    reg.entries = [{"name": "Working", "path": str(clean_home / "Working")}]
    situation = coldstart.look(reg, search=False)
    assert situation.state == coldstart.MANAGED
    assert situation.asks_anything is False


def test_nothing_found_and_no_list_is_a_fresh_start(clean_home, monkeypatch):
    monkeypatch.setattr(discover, "find_installations", lambda *a, **k: [])
    reg = registry.Registry(clean_home / "meta" / "prefixes.json")
    assert coldstart.look(reg).state == coldstart.FRESH


def test_an_unmanaged_install_makes_it_adoptable(clean_home, monkeypatch):
    found = [{"path": str(clean_home / ".AffinityLinux"), "managed_as": None,
              "has_affinity": True, "suggested_name": "AffinityLinux"}]
    monkeypatch.setattr(discover, "find_installations", lambda *a, **k: found)
    reg = registry.Registry(clean_home / "meta" / "prefixes.json")
    situation = coldstart.look(reg)
    assert situation.state == coldstart.ADOPTABLE
    assert situation.installs == found


def test_a_wine_prefix_with_no_affinity_is_not_offered_on_first_run(clean_home,
                                                                   monkeypatch):
    """discover reports every Wine prefix, which is right for Find
    installations -- the user went looking. It is wrong for an unasked-for
    modal on somebody's first run: offering to MOVE ~/.wine while calling it
    "an Affinity install" is untrue and is the sort of thing this application
    exists not to do."""
    monkeypatch.setattr(discover, "find_installations", lambda *a, **k: [
        {"path": str(clean_home / ".wine"), "managed_as": None,
         "has_affinity": False, "suggested_name": "wine"},
        {"path": str(clean_home / ".illustratorCC17"), "managed_as": None,
         "has_affinity": False, "suggested_name": "illustratorCC17"},
    ])
    reg = registry.Registry(clean_home / "meta" / "prefixes.json")
    assert coldstart.look(reg).state == coldstart.FRESH


def test_the_offer_is_made_once_and_not_again_after_forgetting(clean_home,
                                                               monkeypatch):
    """An empty registry is not by itself a first run. Forgetting the last
    prefix would otherwise re-arm a machine-wide walk every time somebody
    tidies up."""
    from affinity_manager import settings

    store = {}
    monkeypatch.setattr(settings, "get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(settings, "set", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(discover, "find_installations", lambda *a, **k: [
        {"path": str(clean_home / ".AffinityLinux"), "managed_as": None,
         "has_affinity": True, "suggested_name": "AffinityLinux"}])
    reg = registry.Registry(clean_home / "meta" / "prefixes.json")

    assert coldstart.look(reg).state == coldstart.ADOPTABLE
    coldstart.mark_asked()
    assert coldstart.look(reg).state == coldstart.MANAGED


def test_an_install_already_managed_is_not_offered_for_adoption(clean_home, monkeypatch):
    """Belt and braces: with an empty list there should be none, but the search
    reads the registry itself and a hand-edited file should not produce an offer
    to adopt something already held."""
    monkeypatch.setattr(discover, "find_installations", lambda *a, **k: [
        {"path": str(clean_home / ".AffinityLinux"), "managed_as": "Working",
         "has_affinity": True}])
    reg = registry.Registry(clean_home / "meta" / "prefixes.json")
    assert coldstart.look(reg).state == coldstart.FRESH


# ── what each choice says it will do ────────────────────────────────────────

def test_managing_in_place_promises_to_touch_nothing(clean_home):
    prefix = make_prefix(clean_home / ".AffinityLinux")
    lines = " ".join(coldstart.explain_in_place({"path": str(prefix)}))
    assert str(prefix) in lines
    assert "stays exactly where it is" in lines
    assert "keeps working" in lines


def test_a_given_size_skips_the_walk(clean_home, monkeypatch):
    """The dialog re-renders on every keystroke in the name field, so a
    several-gigabyte du ran per character typed."""
    prefix = make_prefix(clean_home / ".AffinityLinux")
    monkeypatch.setattr(coldstart.maintenance, "_du",
                        lambda p: (_ for _ in ()).throw(
                            AssertionError("walked the prefix anyway")))
    lines = " ".join(coldstart.explain_move({"path": str(prefix)}, "Working",
                                            base=clean_home / "base",
                                            size=8 * 1024 ** 3))
    assert "rename" in lines


def test_a_move_on_one_filesystem_says_it_copies_nothing(clean_home):
    prefix = make_prefix(clean_home / ".AffinityLinux")
    lines = " ".join(coldstart.explain_move({"path": str(prefix)}, "Working",
                                            base=clean_home / "base"))
    assert "rename" in lines and "nothing is copied" in lines


def test_a_move_names_the_launchers_it_would_rewrite(clean_home, monkeypatch):
    prefix = make_prefix(clean_home / ".AffinityLinux")
    bins = clean_home / "bin"
    bins.mkdir()
    (bins / "affinity-gpu").write_text('PFX="%s"\n' % prefix)
    monkeypatch.setattr(coldstart.maintenance, "LAUNCHER_DIRS", (str(bins),))
    lines = " ".join(coldstart.explain_move({"path": str(prefix)}, "Working",
                                            base=clean_home / "base"))
    assert "affinity-gpu" in lines and "kept beside it" in lines


def test_a_move_says_so_when_there_is_nothing_to_rewrite(clean_home, monkeypatch):
    prefix = make_prefix(clean_home / ".AffinityLinux")
    empty = clean_home / "nothing"
    empty.mkdir()
    monkeypatch.setattr(coldstart.maintenance, "LAUNCHER_DIRS", (str(empty),))
    lines = " ".join(coldstart.explain_move({"path": str(prefix)}, "Working",
                                            base=clean_home / "base"))
    assert "nothing to update" in lines


def test_an_impossible_move_explains_itself_rather_than_raising(clean_home):
    plain = clean_home / "Documents"
    plain.mkdir()
    lines = " ".join(coldstart.explain_move({"path": str(plain)}, "Working",
                                            base=clean_home / "base"))
    assert "cannot be done" in lines


# ── acting ──────────────────────────────────────────────────────────────────

def test_managing_in_place_leaves_the_prefix_alone(clean_home):
    prefix = make_prefix(clean_home / ".AffinityLinux")
    before = sorted(p.name for p in prefix.iterdir())
    reg = registry.Registry(clean_home / "meta" / "prefixes.json")
    entry = coldstart.adopt_in_place(reg, {"path": str(prefix)}, "Working")
    assert entry["path"] == str(prefix)
    assert sorted(p.name for p in prefix.iterdir()) == before


def test_moving_records_the_new_path_and_repoints_the_launcher(clean_home, monkeypatch):
    prefix = make_prefix(clean_home / ".AffinityLinux")
    bins = clean_home / "bin"
    bins.mkdir()
    launcher = bins / "affinity-gpu"
    launcher.write_text('PFX="%s"\nexec "$PFX/bin/wine"\n' % prefix)
    monkeypatch.setattr(coldstart.maintenance, "LAUNCHER_DIRS", (str(bins),))

    reg = registry.Registry(clean_home / "meta" / "prefixes.json")
    entry, notes = coldstart.adopt_by_moving(reg, {"path": str(prefix)}, "Working",
                                             base=clean_home / "base")
    dest = clean_home / "base" / registry.dir_name("Working")
    assert entry["path"] == str(dest)
    assert (dest / "system.reg").is_file() and not prefix.exists()
    assert str(dest) in launcher.read_text()
    assert notes


def test_a_failed_move_writes_nothing_to_the_list(clean_home):
    """The registry entry comes last on purpose: one pointing at a move that
    did not happen is worse than no entry at all."""
    plain = clean_home / "Documents"
    plain.mkdir()
    reg = registry.Registry(clean_home / "meta" / "prefixes.json")
    with pytest.raises(coldstart.maintenance.NotAPrefix):
        coldstart.adopt_by_moving(reg, {"path": str(plain)}, "Working",
                                  base=clean_home / "base")
    assert reg.by_name("Working") is None


# ── settings, carried over ──────────────────────────────────────────────────

def test_settings_are_found_whatever_the_user_is_called(tmp_path):
    prefix = make_prefix(tmp_path / "Old")
    make_settings(prefix, user="someone-else")
    found = prefsseed.settings_in(prefix)
    assert len(found) == 1 and found[0].version == "3.0"
    assert found[0].has_recents and found[0].files == 3


def test_the_destination_prefix_is_not_offered_as_a_source(tmp_path):
    a, b = make_prefix(tmp_path / "A"), make_prefix(tmp_path / "B")
    make_settings(a)
    make_settings(b)
    offered = prefsseed.sources([a, b], exclude=b)
    assert [s.prefix for s in offered] == [a]


def test_a_source_can_be_given_as_a_prefix_a_version_or_the_settings_itself(tmp_path):
    prefix = make_prefix(tmp_path / "Old")
    settings = make_settings(prefix)
    for given in (prefix, settings.parent, settings):
        resolved = prefsseed.resolve_source(given)
        assert resolved is not None and resolved.path == settings


def test_somewhere_with_no_settings_resolves_to_nothing(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert prefsseed.resolve_source(empty) is None


def test_replacing_saves_the_old_settings_aside_rather_than_deleting_them(tmp_path):
    """RecentFiles.xml is the one thing a reinstall cannot give back."""
    old = make_prefix(tmp_path / "Old")
    new = make_prefix(tmp_path / "New")
    make_settings(old)
    source = prefsseed.settings_in(old)[0]
    stock = make_settings(new, recents=False)
    (stock / "preferences.dat").write_text("stock")

    result = prefsseed.seed(source, stock, mode=prefsseed.REPLACE)
    assert result.saved_aside is not None and result.saved_aside.is_dir()
    assert (result.saved_aside / "preferences.dat").read_text() == "stock"
    assert (stock / "preferences.dat").read_text() == "mine"
    assert (stock / "RecentFiles.xml").is_file()
    assert (stock / "shortcuts" / "keys.xml").is_file()


def test_filling_keeps_what_is_already_there(tmp_path):
    """The installer's rule, and the reason for it: the destination's own
    preferences and RecentFiles.xml survive."""
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    make_settings(old)
    source = prefsseed.settings_in(old)[0]
    theirs = make_settings(new)
    (theirs / "preferences.dat").write_text("theirs")
    (theirs / "RecentFiles.xml").write_text("<recent>their own</recent>")
    (source.path / "extra.dat").write_text("only in the source")

    result = prefsseed.seed(source, theirs, mode=prefsseed.FILL)
    assert (theirs / "preferences.dat").read_text() == "theirs"
    assert (theirs / "RecentFiles.xml").read_text() == "<recent>their own</recent>"
    assert (theirs / "extra.dat").read_text() == "only in the source"
    assert result.saved_aside is None
    assert Path("preferences.dat") in result.kept


def test_the_plan_says_what_would_be_replaced_without_writing(tmp_path):
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    make_settings(old)
    source = prefsseed.settings_in(old)[0]
    theirs = make_settings(new, recents=False)

    before = sorted(p.name for p in theirs.rglob("*"))
    result = prefsseed.plan(source, theirs)
    assert Path("RecentFiles.xml") in result.added
    assert Path("preferences.dat") in result.replaced
    assert sorted(p.name for p in theirs.rglob("*")) == before


def test_a_prefix_with_no_settings_yet_gets_a_sensible_destination(tmp_path):
    new = make_prefix(tmp_path / "New")
    (new / "drive_c" / "users" / "joshua").mkdir(parents=True)
    dest = prefsseed.destination_for(new)
    assert dest.name == "Settings" and dest.parent.name == "3.0"
    assert "joshua" in str(dest)
    assert not dest.exists()          # looking must not create it


def test_an_existing_settings_directory_wins_over_a_guess(tmp_path):
    new = make_prefix(tmp_path / "New")
    settings = make_settings(new, user="someone-else", version="2.0")
    assert prefsseed.destination_for(new) == settings


# ── the search reports everything, and says what each thing is ──────────────

def test_a_prefix_with_no_affinity_is_still_found(tmp_path, monkeypatch):
    """An interrupted install has drive_c, dosdevices and nothing else. It was
    the one case the old filter hid, and the one where somebody most needs the
    manager to admit it can see it."""
    monkeypatch.setattr(discover, "search_roots", lambda: [tmp_path])
    monkeypatch.setattr(discover, "remembered_paths", lambda: [])
    monkeypatch.setattr(registry, "manager_dir", lambda: tmp_path / "meta")
    (tmp_path / "meta").mkdir()
    make_prefix(tmp_path / "Half", affinity=False)
    make_prefix(tmp_path / "Whole")

    found = {Path(r["path"]).name: r for r in discover.find_installations()}
    assert set(found) == {"Half", "Whole"}
    assert found["Whole"]["has_affinity"] is True
    assert found["Half"]["has_affinity"] is False


def test_the_search_does_not_descend_into_a_prefix(tmp_path, monkeypatch):
    """drive_c is enormous and holds nothing that is itself a prefix."""
    monkeypatch.setattr(discover, "search_roots", lambda: [tmp_path])
    monkeypatch.setattr(discover, "remembered_paths", lambda: [])
    monkeypatch.setattr(registry, "manager_dir", lambda: tmp_path / "meta")
    (tmp_path / "meta").mkdir()
    outer = make_prefix(tmp_path / "Outer")
    make_prefix(outer / "drive_c" / "Nested")

    found = [Path(r["path"]).name for r in discover.find_installations()]
    assert found == ["Outer"]


def test_the_affinity_column_says_what_an_incomplete_prefix_is():
    """Read off the dialog's own helper, so the wording cannot drift from the
    three cases it has to cover."""
    import importlib
    app = importlib.import_module("AffinityLinuxManager")
    what = app.FindDialog._what_it_is
    assert what({"has_affinity": True, "affinity_version": "3.3.1"}) == "3.3.1"
    assert what({"has_affinity": True, "affinity_version": None}) == "installed"
    assert what({"has_affinity": False, "wine": "ElementalWarrior-wine-11.16"}) \
        == "not installed yet"
    assert what({"has_affinity": False, "wine": None}) == "empty prefix"


# ── what "carry my settings across" actually carries ───────────────────────

def test_the_workspaces_and_shortcuts_come_across_too(tmp_path):
    """They live BESIDE Settings, not inside it. Copying only Settings left
    the new prefix with the source's preferences and recents next to its own
    workspaces -- a configuration that had never existed anywhere."""
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    make_settings(old)
    version = prefsseed.settings_in(old)[0].path.parent
    (version / "Workspaces").mkdir()
    (version / "Workspaces" / "mine.xml").write_text("my layout")
    (version / "sess.db").write_text("session")

    source = prefsseed.settings_in(old)[0]
    dest = prefsseed.destination_for(new)
    result = prefsseed.seed(source, dest, mode=prefsseed.REPLACE)

    assert (dest.parent / "Workspaces" / "mine.xml").read_text() == "my layout"
    assert "Workspaces" in result.extras
    # sess.db is a session database, not a preference. It is not recognised as
    # configuration, so a carry into a clean prefix leaves it where it is.
    assert not (dest.parent / "sess.db").exists()
    assert "sess.db" not in result.extras


def test_filling_keeps_the_destinations_own_workspaces(tmp_path):
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    make_settings(old)
    make_settings(new)
    for prefix, text in ((old, "theirs"), (new, "mine")):
        version = prefsseed.settings_in(prefix)[0].path.parent
        (version / "Workspaces").mkdir()
        (version / "Workspaces" / "w.xml").write_text(text)

    source = prefsseed.settings_in(old)[0]
    dest = prefsseed.settings_in(new)[0].path
    prefsseed.seed(source, dest, mode=prefsseed.FILL)
    assert (dest.parent / "Workspaces" / "w.xml").read_text() == "mine"


def test_the_plan_names_what_travels_beside_settings(tmp_path):
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    make_settings(old)
    version = prefsseed.settings_in(old)[0].path.parent
    (version / "Workspaces").mkdir()
    result = prefsseed.plan(prefsseed.settings_in(old)[0],
                            prefsseed.destination_for(new))
    assert "Workspaces" in result.extras


# ── which Windows user ─────────────────────────────────────────────────────

def test_the_login_user_wins_over_an_alphabetically_earlier_one(tmp_path, monkeypatch):
    """Wine makes a Default directory. Taking the alphabetically first meant
    settings were written where nothing would ever read them."""
    monkeypatch.setattr(prefsseed.getpass, "getuser", lambda: "joshua")
    new = make_prefix(tmp_path / "New")
    # "alice" is a real account and sorts first, so the skip list alone does
    # not decide this -- only preferring the login name does.
    for name in ("Default", "Public", "alice", "joshua"):
        (new / "drive_c" / "users" / name).mkdir(parents=True)
    assert "/joshua/" in str(prefsseed.destination_for(new))


def test_the_wine_placeholder_accounts_are_never_chosen(tmp_path, monkeypatch):
    """The other half: with no directory for the login name, anything is
    better than Default."""
    monkeypatch.setattr(prefsseed.getpass, "getuser", lambda: "nobody-here")
    new = make_prefix(tmp_path / "New")
    for name in ("Default", "Default User", "Public", "All Users", "zoe"):
        (new / "drive_c" / "users" / name).mkdir(parents=True)
    assert "/zoe/" in str(prefsseed.destination_for(new))


def test_the_aside_copy_can_be_found_again(tmp_path):
    """When a copy fails, REPLACE has already renamed the old settings aside
    and the prefix has no Settings folder at all."""
    new = make_prefix(tmp_path / "New")
    dest = make_settings(new)
    (dest.parent / (dest.name + ".before-copy-20260101-000000")).mkdir()
    (dest.parent / (dest.name + ".before-copy-20260202-000000")).mkdir()
    found = prefsseed.aside_of(dest)
    assert found is not None and found.name.endswith("20260202-000000")


def test_no_aside_copy_is_not_an_error(tmp_path):
    new = make_prefix(tmp_path / "New")
    assert prefsseed.aside_of(make_settings(new)) is None



# ── what is and is not a setting ───────────────────────────────────────────
#
# The names below are the working prefix's version folder, listed on
# 2026-09-29. The previous rule copied all of them.

LIVE_FOLDER = {
    "dirs": ["AffinityFonts", "autosave", "backup", "CrashReports", "EBWebView",
             "LensProfiles", "Plugins", "printing", "profiles", "Samples",
             "shunt", "temp", "temp-critical", "user", "welcome", "Workspaces"],
    "files": ["cs.log", "home_favourites3.dat", "home_newdocument.dat",
              "ipc.log", "lessons.json", "Log.txt", "mcp.json",
              "notificationoptions.dat", "pid", "preferences.dat", "sess.db",
              "studios3.dat"],
}


def build_live_shaped(prefix: Path) -> Path:
    settings = make_settings(prefix)
    version = settings.parent
    for d in LIVE_FOLDER["dirs"]:
        (version / d).mkdir(exist_ok=True)
        (version / d / "x").write_text(d)
    for f in LIVE_FOLDER["files"]:
        (version / f).write_text(f)
    return settings


def test_autosaves_webview_pid_temp_and_logs_are_never_carried(tmp_path):
    """Crash-recovery autosaves (205 MB in the working prefix), the WebView2
    profile, a pid that exists only while Affinity runs, temp, crash reports,
    logs. None of it is a setting, and in a clean prefix the autosaves would
    be offered back as documents to recover."""
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    build_live_shaped(old)
    source = prefsseed.settings_in(old)[0]
    dest = prefsseed.destination_for(new)
    prefsseed.seed(source, dest, mode=prefsseed.REPLACE)

    for name in ("autosave", "backup", "EBWebView", "pid", "temp",
                 "temp-critical", "CrashReports", "Log.txt", "cs.log", "ipc.log"):
        assert not (dest.parent / name).exists(), f"{name} was carried"


def test_every_recognised_setting_is_carried(tmp_path):
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    build_live_shaped(old)
    source = prefsseed.settings_in(old)[0]
    dest = prefsseed.destination_for(new)
    prefsseed.seed(source, dest, mode=prefsseed.REPLACE)
    for name in sorted(prefsseed.CONFIG_NAMES):
        assert (dest.parent / name).exists(), f"{name} was not carried"


def test_what_is_left_behind_is_named(tmp_path):
    old = make_prefix(tmp_path / "Old")
    build_live_shaped(old)
    left = {e.name: kind for e, kind in prefsseed.settings_in(old)[0].left_behind}
    assert left["autosave"] == prefsseed.VOLATILE
    assert left["sess.db"] == prefsseed.UNKNOWN
    assert "Workspaces" not in left and "mcp.json" not in left


def test_replace_renames_displaced_workspaces_aside(tmp_path):
    """The module promised REPLACE deletes nothing. That was true for Settings
    and false for everything beside it, which was rmtree'd."""
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    make_settings(old)
    make_settings(new)
    for prefix, text in ((old, "theirs"), (new, "mine")):
        version = prefsseed.settings_in(prefix)[0].path.parent
        (version / "Workspaces").mkdir()
        (version / "Workspaces" / "w.xml").write_text(text)
    dest = prefsseed.settings_in(new)[0].path
    prefsseed.seed(prefsseed.settings_in(old)[0], dest, mode=prefsseed.REPLACE)

    assert (dest.parent / "Workspaces" / "w.xml").read_text() == "theirs"
    aside = [p for p in dest.parent.iterdir()
             if p.name.startswith("Workspaces.before-copy-")]
    assert len(aside) == 1 and (aside[0] / "w.xml").read_text() == "mine"


# ── Common/<version>, beside Affinity/<version> ────────────────────────────
#
# Found 2026-10-01: a carried prefix came up without its recent fonts, fill
# presets, object styles, document presets or user dictionary, because the
# carry never looked in Common. Names are the working prefix's Common/3.0.

LIVE_COMMON = {
    "dirs": ["Settings", "user", "locks", "clipboard", "modelcache"],
    "files": ["cs.dat", "cs.json", "ipc.dat", "sp.db"],
}


def build_common(prefix: Path, text="mine") -> Path:
    settings = prefsseed.settings_in(prefix)[0]
    common = settings.common_dir
    for d in LIVE_COMMON["dirs"]:
        (common / d).mkdir(parents=True, exist_ok=True)
        (common / d / "x").write_text(text)
    (common / "Settings" / "Fonts.xml").write_text(f"<fonts>{text}</fonts>")
    (common / "user" / "fills.propcol").write_text(text)
    for f in LIVE_COMMON["files"]:
        (common / f).write_text(text)
    return common


def test_the_common_folder_is_found_beside_the_version_folder(tmp_path):
    old = make_prefix(tmp_path / "Old")
    make_settings(old)
    common = prefsseed.settings_in(old)[0].common_dir
    assert common.parts[-3:] == ("Affinity", "Common", "3.0")
    assert common.parent.parent == prefsseed.settings_in(old)[0].path.parent.parent.parent


def test_font_history_and_user_presets_are_carried(tmp_path):
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    make_settings(old)
    build_common(old, "theirs")
    dest = prefsseed.destination_for(new)
    result = prefsseed.seed(prefsseed.settings_in(old)[0], dest, mode=prefsseed.REPLACE)
    common = dest.parent.parent.parent / "Common" / "3.0"
    assert (common / "Settings" / "Fonts.xml").read_text() == "<fonts>theirs</fonts>"
    assert (common / "user" / "fills.propcol").read_text() == "theirs"
    assert {"Common/Settings", "Common/user"} <= set(result.extras)


def test_analytics_locks_clipboard_and_models_are_never_carried(tmp_path):
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    make_settings(old)
    build_common(old)
    dest = prefsseed.destination_for(new)
    prefsseed.seed(prefsseed.settings_in(old)[0], dest, mode=prefsseed.REPLACE)
    common = dest.parent.parent.parent / "Common" / "3.0"
    for name in ("sp.db", "cs.dat", "cs.json", "ipc.dat", "locks", "clipboard"):
        assert not (common / name).exists(), f"Common/{name} was carried"


def test_the_ai_models_are_carried(tmp_path):
    """554 MB that Affinity 3.3 uses and would otherwise download again."""
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    make_settings(old)
    common = build_common(old)
    (common / "modelcache" / "SegmentationEncoder_3.2.2.onnx").write_text("model")
    dest = prefsseed.destination_for(new)
    prefsseed.seed(prefsseed.settings_in(old)[0], dest, mode=prefsseed.REPLACE)
    carried = dest.parent.parent.parent / "Common" / "3.0" / "modelcache"
    assert (carried / "SegmentationEncoder_3.2.2.onnx").read_text() == "model"


def test_windows_favorites_and_links_are_carried_as_links(tmp_path):
    """The working prefix's Favorites are symlinks to client folders; they
    travel as symlinks, pointing where they pointed."""
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    make_settings(old)
    client = tmp_path / "work" / "Client A"
    client.mkdir(parents=True)
    profile = prefsseed.settings_in(old)[0].profile_dir
    assert profile.name == "joshua"
    (profile / "Favorites").mkdir()
    (profile / "Favorites" / "Client A").symlink_to(client)
    (profile / "Links").mkdir()
    (profile / "Links" / "work").symlink_to(tmp_path / "work")
    dest = prefsseed.destination_for(new)
    result = prefsseed.seed(prefsseed.settings_in(old)[0], dest, mode=prefsseed.REPLACE)
    new_profile = dest.parents[5]
    fav = new_profile / "Favorites" / "Client A"
    assert fav.is_symlink() and Path(os.readlink(fav)) == client
    assert (new_profile / "Links" / "work").is_symlink()
    assert {"Favorites", "Links"} <= set(result.extras)


def test_empty_favorites_are_not_carried(tmp_path):
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    make_settings(old)
    (prefsseed.settings_in(old)[0].profile_dir / "Favorites").mkdir()
    plan = prefsseed.plan(prefsseed.settings_in(old)[0], prefsseed.destination_for(new))
    assert "Favorites" not in plan.extras


def test_displaced_common_settings_are_renamed_aside_not_deleted(tmp_path):
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    make_settings(old)
    make_settings(new)
    build_common(old, "theirs")
    build_common(new, "mine")
    dest = prefsseed.settings_in(new)[0].path
    prefsseed.seed(prefsseed.settings_in(old)[0], dest, mode=prefsseed.REPLACE)
    common = prefsseed.settings_in(new)[0].common_dir
    assert (common / "user" / "fills.propcol").read_text() == "theirs"
    aside = [p for p in common.iterdir() if p.name.startswith("user.before-copy-")]
    assert len(aside) == 1 and (aside[0] / "fills.propcol").read_text() == "mine"


def test_fill_keeps_the_destinations_common_settings(tmp_path):
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    make_settings(old)
    make_settings(new)
    build_common(old, "theirs")
    build_common(new, "mine")
    dest = prefsseed.settings_in(new)[0].path
    prefsseed.seed(prefsseed.settings_in(old)[0], dest, mode=prefsseed.FILL)
    common = prefsseed.settings_in(new)[0].common_dir
    assert (common / "user" / "fills.propcol").read_text() == "mine"


def test_the_plan_and_the_left_behind_list_include_common(tmp_path):
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    make_settings(old)
    build_common(old)
    source = prefsseed.settings_in(old)[0]
    plan = prefsseed.plan(source, prefsseed.destination_for(new))
    assert "Common/Settings" in plan.extras and "Common/user" in plan.extras
    left = {e.name: k for e, k in source.common_left_behind}
    assert left["sp.db"] == prefsseed.VOLATILE and left["clipboard"] == prefsseed.VOLATILE
    assert "modelcache" not in left
    assert "user" not in left


def test_a_prefix_without_a_common_folder_still_copies(tmp_path):
    """Affinity 2 has no Common/<version>; the carry must not care."""
    old, new = make_prefix(tmp_path / "Old"), make_prefix(tmp_path / "New")
    make_settings(old)
    result = prefsseed.seed(prefsseed.settings_in(old)[0],
                            prefsseed.destination_for(new), mode=prefsseed.REPLACE)
    assert not any(e.startswith("Common/") for e in result.extras)


# ── drive letters ──────────────────────────────────────────────────────────

def wine_drives(prefix: Path, **letters) -> Path:
    """dosdevices as Wine lays it out: c: relative, z: to /, the user's own
    letters absolute, raw-device entries with two colons, serial ports."""
    dd = prefix / "dosdevices"
    for name in ("c:", "z:"):
        (dd / name).unlink(missing_ok=True)
    (dd / "c:").symlink_to("../drive_c")
    (dd / "z:").symlink_to("/")
    (dd / "d::").symlink_to("/dev/sda1")
    (dd / "com1").symlink_to("/dev/ttyS0")
    for letter, target in letters.items():
        (dd / f"{letter}:").symlink_to(target)
    return prefix


def test_only_the_users_own_letters_are_found(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    old = wine_drives(make_prefix(tmp_path / "Old"), w=str(work),
                      k="/run/media/nobody/NIKON")
    found = {d.letter: d for d in prefsseed.drive_letters(old)}
    assert set(found) == {"w", "k"}, "c:, z:, d:: and com1 are not designations"
    assert found["w"].target == str(work) and found["w"].available
    assert not found["k"].available


def test_a_relative_letter_is_not_carried(tmp_path):
    """A relative target points inside the prefix it came from."""
    old = wine_drives(make_prefix(tmp_path / "Old"))
    (old / "dosdevices" / "e:").symlink_to("../drive_c/stuff")
    assert prefsseed.drive_letters(old) == []


def test_letters_are_not_written_into_a_prefix_wine_has_not_set_up(tmp_path):
    """Wine creates C: and Z: only when it creates dosdevices itself
    (dlls/ntdll/unix/server.c). A W: put there first leaves a prefix with no
    C: drive -- so the import refuses, and creates nothing at all."""
    fresh = tmp_path / "Fresh"
    (fresh / "drive_c" / "users" / "joshua").mkdir(parents=True)
    with pytest.raises(prefsseed.PrefixNotReady):
        prefsseed.import_drive_letters(
            fresh, [prefsseed.DriveLetter("w", "/mnt/work")])
    assert not (fresh / "dosdevices").exists(), "dosdevices was created"


def test_letters_are_imported_into_a_set_up_prefix(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    new = wine_drives(make_prefix(tmp_path / "New"))
    notes = prefsseed.import_drive_letters(
        new, [prefsseed.DriveLetter("w", str(work))])
    link = new / "dosdevices" / "w:"
    assert link.is_symlink() and os.readlink(link) == str(work)
    assert any("W: ->" in n for n in notes)


def test_an_existing_letter_is_never_changed(tmp_path):
    new = wine_drives(make_prefix(tmp_path / "New"), w="/somewhere/else")
    notes = prefsseed.import_drive_letters(
        new, [prefsseed.DriveLetter("w", "/mnt/work")])
    assert os.readlink(new / "dosdevices" / "w:") == "/somewhere/else"
    assert any("left alone" in n for n in notes)


def test_importing_the_same_letter_twice_is_harmless(tmp_path):
    new = wine_drives(make_prefix(tmp_path / "New"))
    letter = [prefsseed.DriveLetter("w", "/mnt/work")]
    prefsseed.import_drive_letters(new, letter)
    notes = prefsseed.import_drive_letters(new, letter)
    assert any("already /mnt/work" in n for n in notes)


def test_wines_own_letters_cannot_be_imported(tmp_path):
    new = wine_drives(make_prefix(tmp_path / "New"))
    prefsseed.import_drive_letters(new, [prefsseed.DriveLetter("c", "/tmp"),
                                         prefsseed.DriveLetter("z", "/tmp")])
    assert os.readlink(new / "dosdevices" / "c:") == "../drive_c"
    assert os.readlink(new / "dosdevices" / "z:") == "/"


def test_recents_are_counted_by_drive(tmp_path):
    old = make_prefix(tmp_path / "Old")
    settings = make_settings(old)
    (settings / "RecentFiles.xml").write_text(
        '<r><f path="W:\\Clients\\a.af"/><f path="W:\\b.af"/>'
        '<f path="Z:\\home\\c.af"/><f path="http://x.y/z"/></r>')
    counts = prefsseed.settings_in(old)[0].recents_by_drive()
    assert counts == {"W": 2, "Z": 1}


def test_a_settings_folder_knows_which_prefix_it_is_in(tmp_path):
    old = wine_drives(make_prefix(tmp_path / "Old"))
    settings = make_settings(old)
    assert prefsseed.prefix_of(settings) == old.resolve()
    loose = tmp_path / "backup-disk" / "Settings"
    loose.mkdir(parents=True)
    assert prefsseed.prefix_of(loose) is None
