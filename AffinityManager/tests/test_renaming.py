"""Renaming a prefix: everything keyed by its name follows it.

Against a throw-away manager directory and XDG data directory, with the menu
refresh and document associations stubbed, so the real menu is never touched.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import (  # noqa: E402
    defaultentry, desktopentry, prefixlog, registry, renaming, snapshots)
from test_defaultentry import make_prefix  # noqa: E402


@pytest.fixture
def host(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(registry, "manager_dir", lambda: tmp_path / "meta")
    monkeypatch.setattr(desktopentry, "refresh_menu", lambda: None)
    monkeypatch.setattr(desktopentry, "find_icon", lambda: None)
    monkeypatch.setattr(defaultentry, "xdg_mime_default", lambda entry, mime: None)
    prefix = make_prefix(tmp_path, "Work_Prefix")
    (prefix / "dosdevices").mkdir()
    (prefix / "dosdevices" / "c:").symlink_to("../drive_c")
    reg = registry.Registry(tmp_path / "meta" / "prefixes.json")
    reg.add("Work Prefix", str(prefix))
    return tmp_path, prefix, reg


def test_the_name_log_snapshots_and_menu_entries_follow(host):
    root, prefix, reg = host
    prefixlog.write("Work Prefix", "before the rename")
    reg.by_name("Work Prefix")["log"] = str(prefixlog.path_for("Work Prefix"))
    reg.save()
    snaps = snapshots.dir_for("Work Prefix")
    (snaps / "2026-10-14").mkdir(parents=True)
    defaultentry.add_menu_entry("Work Prefix", prefix)
    defaultentry.apply(defaultentry.plan("Work Prefix", prefix))

    assert renaming.rename(reg, "Work Prefix", "Client Work") == []

    entry = reg.by_name("Client Work")
    assert entry is not None and reg.by_name("Work Prefix") is None
    assert entry["path"] == str(prefix), "the folder does not move"
    assert "before the rename" in prefixlog.path_for("Client Work").read_text()
    assert entry["log"] == str(prefixlog.path_for("Client Work"))
    assert not prefixlog.path_for("Work Prefix").exists()
    assert (snapshots.dir_for("Client Work") / "2026-10-14").is_dir()
    assert not snaps.exists()

    assert defaultentry.has_menu_entry("Client Work")
    assert not defaultentry.has_menu_entry("Work Prefix")
    named = desktopentry.entry_path("Client Work", defaultentry.MENU_LABEL).read_text()
    assert f"Name={defaultentry.menu_name('Client Work')}" in named
    assert f"{desktopentry.MARKER}=Client Work" in named
    assert defaultentry.current() == "Client Work", "the Default follows too"
    assert desktopentry.entries_for("Work Prefix") == []


def test_a_taken_or_invalid_name_changes_nothing(host):
    root, prefix, reg = host
    other = make_prefix(root, "Other")
    reg.add("Other", str(other))
    prefixlog.write("Work Prefix", "x")
    with pytest.raises(registry.DuplicateName):
        renaming.rename(reg, "Work Prefix", "Other")
    with pytest.raises(registry.InvalidName):
        renaming.rename(reg, "Work Prefix", "../escape")
    assert reg.by_name("Work Prefix") is not None
    assert prefixlog.path_for("Work Prefix").exists()


def test_entries_of_a_prefix_whose_name_contains_this_one_are_left_alone(host):
    root, prefix, reg = host
    longer = make_prefix(root, "Work_Prefix_2")
    reg.add("Work Prefix 2", str(longer))
    defaultentry.add_menu_entry("Work Prefix 2", longer)
    renaming.rename(reg, "Work Prefix", "Renamed")
    assert defaultentry.has_menu_entry("Work Prefix 2")
    assert desktopentry.entries_for("Work Prefix 2") != []


def test_moving_takes_the_launchers_and_the_default_along(host):
    root, prefix, reg = host
    defaultentry.add_menu_entry("Work Prefix", prefix)
    defaultentry.apply(defaultentry.plan("Work Prefix", prefix))
    renaming.rename(reg, "Work Prefix", "Client Work")
    dest = prefix.parent / registry.dir_name("Client Work")

    renaming.move(reg, "Client Work", dest)

    assert dest.is_dir() and not prefix.exists()
    assert reg.by_name("Client Work")["path"] == str(dest)
    main = defaultentry.main_entry().read_text()
    assert str(dest) in main and f"{prefix}/" not in main and f"Path={prefix}\n" not in main
    assert "Comment=Default Affinity: Client Work" in main
    named = desktopentry.entry_path("Client Work", defaultentry.MENU_LABEL).read_text()
    assert str(dest) in named and f"{prefix}/" not in named
    assert (dest / "ElementalWarriorWine").resolve() == (dest / "ElementalWarrior-wine-11.19").resolve()


def test_a_move_onto_an_existing_folder_is_refused_and_nothing_changes(host):
    root, prefix, reg = host
    taken = root / "Taken"
    (taken / "something").mkdir(parents=True)
    with pytest.raises(renaming.CannotMove):
        renaming.move(reg, "Work Prefix", taken)
    assert reg.by_name("Work Prefix")["path"] == str(prefix) and prefix.is_dir()


def test_the_dialog_offers_a_move_only_when_the_folder_would_change(host):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication, QDialogButtonBox
    QApplication.instance() or QApplication([])
    import AffinityLinuxManager as app
    root, prefix, reg = host
    d = app.RenameMoveDialog(None, reg, reg.by_name("Work Prefix"))
    ok = d.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert not ok.isEnabled(), "nothing changed yet"
    assert not d.move_box.isEnabled(), "Work Prefix already lives in Work_Prefix"
    d.field.setText("Client Work")
    assert ok.isEnabled() and d.move_box.isEnabled()
    d.move_box.setChecked(True)
    assert d.result() == ("Client Work", prefix.parent / "Client_Work")
    d.field.setText("bad/name")
    assert not ok.isEnabled()


def test_wines_own_menu_entries_in_subfolders_follow_a_move(host):
    root, prefix, reg = host
    wine_menu = root / "data" / "applications" / "wine" / "Programs" / "Affinity"
    wine_menu.mkdir(parents=True)
    entry = wine_menu / "Affinity.desktop"
    entry.write_text(f"[Desktop Entry]\nExec=env WINEPREFIX=\"{prefix}\" wine Affinity.exe\n")
    dest = prefix.parent / "Moved"
    renaming.move(reg, "Work Prefix", dest)
    assert f'WINEPREFIX="{dest}"' in entry.read_text()
