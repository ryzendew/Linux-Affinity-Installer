"""The Default entry and the per-prefix menu entries.

Run against a throw-away XDG data directory with xdg-mime and the menu refresh
stubbed, so nothing here touches the real menu or document associations.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import defaultentry, desktopentry, registry  # noqa: E402


def make_prefix(root: Path, name: str, build="ElementalWarrior-wine-11.19", handler=True):
    prefix = root / name
    wine = prefix / build / "bin" / "wine"
    wine.parent.mkdir(parents=True)
    wine.write_text("")
    (prefix / build / "lib" / "wine" / "x86_64-windows").mkdir(parents=True)
    (prefix / build / "lib" / "wine" / "x86_64-windows" / "wintypes.dll").write_bytes(
        "WinMetaData".encode("utf-16-le"))
    (prefix / "ElementalWarriorWine").symlink_to(prefix / build)
    app = prefix / "drive_c" / "Program Files" / "Affinity" / "Affinity"
    app.mkdir(parents=True)
    (app / "AffinityHook.exe").write_text("")
    if handler:
        (app / "affinity-on-linux.exe").write_text("")
    return prefix


@pytest.fixture
def host(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(registry, "manager_dir", lambda: tmp_path / "meta")
    monkeypatch.setattr(desktopentry, "refresh_menu", lambda: None)
    monkeypatch.setattr(desktopentry, "find_icon", lambda: None)
    defaults = {}
    monkeypatch.setattr(defaultentry, "xdg_mime_default",
                        lambda entry, mime: defaults.__setitem__(mime, entry))
    return tmp_path, defaults


def test_making_a_prefix_the_default_takes_the_menu_entry_documents_and_sign_in(host):
    root, defaults = host
    work = make_prefix(root, "Work")
    defaultentry.apply(defaultentry.plan("Work", work))
    main = defaultentry.main_entry().read_text()
    assert defaultentry.current() == "Work"
    assert f"WINEPREFIX={work}" in main and "affinity-on-linux.exe" in main and main.count("%F") == 1
    assert "MimeType=application/af;" in main
    assert "%u" in defaultentry.url_handler().read_text()
    assert defaults["application/afphoto"] == "Affinity.desktop"
    assert defaults["x-scheme-handler/affinity"] == "affinity-url-handler.desktop"


def test_switching_the_default_names_both_prefixes(host):
    root, _ = host
    work, test = make_prefix(root, "Work"), make_prefix(root, "Test")
    defaultentry.apply(defaultentry.plan("Work", work))
    plan = defaultentry.plan("Test", test)
    assert "Work" in plan.summary and "Test" in plan.summary
    defaultentry.apply(plan)
    assert defaultentry.current() == "Test"
    assert f"WINEPREFIX={test}" in defaultentry.main_entry().read_text()


def test_an_entry_somebody_else_wrote_is_moved_aside_not_deleted(host):
    root, _ = host
    work = make_prefix(root, "Work")
    apps = desktopentry.applications_dir()
    apps.mkdir(parents=True)
    defaultentry.main_entry().write_text("[Desktop Entry]\nName=Affinity\nExec=env WINEPREFIX=/old wine x\n")
    plan = defaultentry.plan("Work", work)
    assert plan.foreign and plan.from_launches == "/old" and "/old" in plan.summary
    notes = defaultentry.apply(plan)
    kept = list(defaultentry.backup_dir().glob("Affinity.desktop.*"))
    assert len(kept) == 1 and "WINEPREFIX=/old" in kept[0].read_text()
    assert any("moved" in n for n in notes)


def test_without_the_handler_exe_documents_are_not_claimed(host):
    root, defaults = host
    work = make_prefix(root, "Work", handler=False)
    notes = defaultentry.apply(defaultentry.plan("Work", work))
    main = defaultentry.main_entry().read_text()
    assert "AffinityHook.exe" in main and "%F" not in main and "MimeType" not in main
    assert "application/af" not in defaults
    assert any("affinity-on-linux.exe" in n for n in notes)


def test_a_wine_that_cannot_take_the_sign_in_leaves_the_handler_alone(host):
    root, defaults = host
    work = make_prefix(root, "Old", build="ElementalWarrior-wine-11.12")
    (work / "ElementalWarrior-wine-11.12" / "lib" / "wine" / "x86_64-windows" / "wintypes.dll").write_bytes(b"")
    plan = defaultentry.plan("Old", work)
    assert not plan.sign_in and "sign-in" in plan.summary
    defaultentry.apply(plan)
    assert not defaultentry.url_handler().exists()
    assert "x-scheme-handler/affinity" not in defaults


def test_a_named_entry_is_separate_and_takes_no_documents(host):
    root, _ = host
    work = make_prefix(root, "Work")
    path = defaultentry.add_menu_entry("Work", work)
    text = path.read_text()
    assert path.name != defaultentry.MAIN and "Name=Affinity — Work" in text
    assert "MimeType" not in text and defaultentry.has_menu_entry("Work")
    assert defaultentry.remove_menu_entry("Work") and not path.exists()


def test_the_default_belongs_to_its_prefix_for_removal(host):
    root, _ = host
    work = make_prefix(root, "Work")
    defaultentry.apply(defaultentry.plan("Work", work))
    assert defaultentry.main_entry() in desktopentry.entries_for("Work")


def test_launch_uses_the_prefixs_wine_not_system_wine(tmp_path, monkeypatch):
    """active_wine says "<build> (link)" for a prefix that is not running; that
    label used as a directory sent Affinity to system Wine."""
    from affinity_manager import installer, probe
    prefix = make_prefix(tmp_path, "Work")
    started = {}
    monkeypatch.setattr(installer.subprocess, "Popen",
                        lambda argv, **kw: started.setdefault("argv", argv))
    monkeypatch.setattr(probe, "active_wine", lambda p: "ElementalWarrior-wine-11.19 (link)")
    installer.launch_affinity(prefix)
    assert started["argv"][0] == str(prefix / "ElementalWarrior-wine-11.19" / "bin" / "wine")
