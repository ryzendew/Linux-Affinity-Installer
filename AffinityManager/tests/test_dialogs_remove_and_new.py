"""New prefix and Remove, as dialogs: the real widgets, offscreen.

New prefix: the name rule is shown before anything is typed, a refused name
says which character is wrong, and the dialog says which Affinity it will
install. Remove: several prefixes in one list, nothing removed twice, and the
tick that arms the button really is required.
"""
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem  # noqa: E402

import AffinityLinuxManager as app  # noqa: E402
from affinity_manager import liveness, registry, release, removal  # noqa: E402

QAPP = QApplication.instance() or QApplication([])


# ── New prefix ───────────────────────────────────────────────────────────────

@pytest.fixture
def new_dialog(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(registry, "manager_dir", lambda: tmp_path / "meta")
    monkeypatch.setattr(registry, "base_dir", lambda: tmp_path / "base")
    monkeypatch.setattr(release, "current",
                        lambda *a, **k: release.Release("3.3.0.4850", "2026-09-15"))
    reg = registry.Registry(tmp_path / "prefixes.json")
    d = app.NewPrefixDialog(None, reg)
    yield d
    d.reject()


def test_new_prefix_starts_with_stock_settings_unless_asked(new_dialog):
    assert new_dialog.carry_from() is None
    assert not new_dialog.carry.isEnabled()


def test_new_prefix_offers_the_settings_of_other_prefixes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setattr(registry, "manager_dir", lambda: tmp_path / "meta")
    monkeypatch.setattr(registry, "base_dir", lambda: tmp_path / "base")
    monkeypatch.setattr(release, "current",
                        lambda *a, **k: release.Release("3.3.0.4850", "2026-09-15"))
    old = tmp_path / "Old"
    settings = old / "drive_c/users/someone/AppData/Roaming/Affinity/Affinity/3.0/Settings"
    settings.mkdir(parents=True)
    (settings / "preferences.dat").write_bytes(b"x")
    reg = registry.Registry(tmp_path / "prefixes.json")
    reg.add("Old", str(old))
    d = app.NewPrefixDialog(None, reg)
    try:
        assert d.carry.isEnabled() and d.carry.count() == 2
        assert d.carry_from() is None
        d.carry.setCurrentIndex(1)
        assert d.carry_from() == old
    finally:
        d.reject()


def test_new_prefix_offers_an_unmanaged_default_install(tmp_path, monkeypatch):
    """An AppImage or plain AffinityOnLinux install leaves ~/.AffinityLinux,
    which the manager does not list -- and is what people move from."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(registry, "manager_dir", lambda: tmp_path / "meta")
    monkeypatch.setattr(registry, "base_dir", lambda: tmp_path / "base")
    monkeypatch.setattr(release, "current",
                        lambda *a, **k: release.Release("3.3.0.4850", "2026-09-15"))
    settings = home / ".AffinityLinux/drive_c/users/someone/AppData/Roaming/Affinity/Affinity/3.0/Settings"
    settings.mkdir(parents=True)
    (settings / "RecentFiles.xml").write_text("<x/>")
    d = app.NewPrefixDialog(None, registry.Registry(tmp_path / "prefixes.json"))
    try:
        assert d.carry.count() == 2
        d.carry.setCurrentIndex(1)
        assert d.carry_from() == home / ".AffinityLinux"
    finally:
        d.reject()


def settle(d, until):
    import time
    t = time.time()
    while not until() and time.time() - t < 5:
        QAPP.processEvents()


def test_the_name_rule_is_shown_before_anything_is_typed(new_dialog):
    rule = new_dialog.name_rule.text()
    for part in ("A–Z", "0–9", "space", "dot", "underscore", "hyphen", "64"):
        assert part in rule
    assert not new_dialog.name_rule.isHidden()


@pytest.mark.parametrize("name, says", [
    ("AffinityLinux 3.3 (clean)", "“(”  “)”"),
    ("Affinity/test", "“/”"),
    ("Café", "“é”"),
    ("-leading", "start with a letter or digit"),
    ("", "Give the prefix a name"),
])
def test_a_refused_name_says_exactly_what_is_wrong(new_dialog, name, says):
    new_dialog.name.setText(name)
    assert not new_dialog.ok.isEnabled()
    assert says in new_dialog.path_note.text()


def test_the_dialog_rule_and_the_registry_rule_agree(new_dialog):
    """The words on screen and the check that enforces them must not drift."""
    for name in ("Good name 1", "a.b_c-d", "x" * 64, "(no)", "é", "x" * 65, " lead"):
        new_dialog.name.setText(name)
        typed = new_dialog.name.text()       # the field stops at 64
        try:
            registry.validate_name(typed)
            ok = True
        except registry.InvalidName:
            ok = False
        assert new_dialog.ok.isEnabled() == ok, name
    new_dialog.name.setText("x" * 65)
    assert len(new_dialog.name.text()) == 64


def test_it_says_which_affinity_the_current_release_is(new_dialog):
    settle(new_dialog, lambda: new_dialog.current_release is not None)
    text = new_dialog.will_install.text()
    assert "Affinity 3.3.0.4850" in text and "2026-09-15" in text


def test_a_kept_installer_shows_its_own_version(new_dialog, tmp_path):
    from test_release import installer
    kept = tmp_path / "Affinity-x64-3.2.3.exe"
    kept.write_bytes(installer((3, 2, 3, 4646)))
    new_dialog.pin.setChecked(True)
    new_dialog.installer_file.setText(str(kept))
    assert "Affinity 3.2.3.4646" in new_dialog.will_install.text()


def test_it_is_clear_the_installer_is_affinity_not_wine(new_dialog):
    assert "Affinity" in new_dialog.pin.text()
    assert "not Wine" in new_dialog.note.text()


# ── Remove, several at once ──────────────────────────────────────────────────

def plan(name, *, shared=None):
    p = removal.Plan(name, Path("/nonexistent") / name)
    p.items = [
        removal.Item("prefix", "The prefix", str(p.path), p.path, 10_000),
        removal.Item("menu", "Menu entry", name, Path(f"/x/{name}.desktop"), 10),
        removal.Item("settings-backup", "Snapshots", "", Path(f"/x/s{name}"), 5,
                     default=False),
    ]
    if shared:
        p.items.append(removal.Item("mime", "Shared definition", "", shared, 1))
    return p


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(app.liveness, "scan",
                        lambda p, *a, **k: liveness.Activity(str(p)))


def test_several_prefixes_are_grouped_and_chosen_per_prefix(quiet):
    d = app.RemovalDialog(None, [plan("a"), plan("b")])
    chosen = d.chosen_by_plan()
    assert [p.name for p, _ in chosen] == ["a", "b"]
    assert all({i.kind for i in its} == {"prefix", "menu"} for _, its in chosen)
    # Unticking a group's row takes all its items with it.
    d.groups[0][1].setCheckState(0, Qt.CheckState.Unchecked)
    assert [p.name for p, _ in d.chosen_by_plan()] == ["b"]


def test_a_file_two_prefixes_claim_is_listed_once(quiet):
    shared = Path("/x/shared.xml")
    d = app.RemovalDialog(None, [plan("a", shared=shared), plan("b", shared=shared)])
    rows = [r for _, _, rs in d.groups for r in rs
            if r.data(0, Qt.ItemDataRole.UserRole).path == shared]
    assert len(rows) == 1


def test_remove_needs_the_tick(quiet):
    d = app.RemovalDialog(None, [plan("a"), plan("b")])
    assert not d.ok.isEnabled()
    assert "Required" in d.arm.line.text()
    d.arm.setChecked(True)
    assert d.ok.isEnabled() and "2 prefixes" in d.ok.text()


def test_affinity_running_in_one_of_them_holds_the_button(monkeypatch):
    def scan(p, *a, **k):
        procs = [liveness.Proc(4242, "Affinity.exe", 0, liveness.AFFINITY)] \
            if str(p).endswith("/b") else []
        return liveness.Activity(str(p), procs)

    monkeypatch.setattr(app.liveness, "scan", scan)
    a, b = plan("a"), plan("b")
    for p in (a, b):
        p.path = Path("/tmp")       # exists, so the banner is live
    b.path = Path("/tmp/b")
    monkeypatch.setattr(Path, "exists", lambda self: True)
    d = app.RemovalDialog(None, [a, b])
    d.arm.setChecked(True)
    assert not d.ok.isEnabled()
    assert "b" in d.arm.line.text()
    # Untick b entirely: a alone can go.
    d.groups[1][1].setCheckState(0, Qt.CheckState.Unchecked)
    assert d.ok.isEnabled()


# ── the list: several selected ───────────────────────────────────────────────

def test_only_delete_acts_on_several(tmp_path):
    reg = registry.Registry(tmp_path / "p.json")
    reg.entries = [{"name": n, "path": str(tmp_path / n)} for n in ("a", "b")]
    tree = QTreeWidget()
    for n in ("a", "b"):
        item = QTreeWidgetItem([n])
        item.setData(0, Qt.ItemDataRole.UserRole, n)
        tree.addTopLevelItem(item)
    w = types.SimpleNamespace(tree=tree, reg=reg)
    for name in ("selected_entry", "selected_entries"):
        setattr(w, name, types.MethodType(getattr(app.ManagerWindow, name), w))
    tree.topLevelItem(0).setSelected(True)
    assert w.selected_entry()["name"] == "a"
    tree.topLevelItem(1).setSelected(True)
    assert w.selected_entry() is None, "a single-prefix action must not pick one"
    assert [e["name"] for e in w.selected_entries()] == ["a", "b"]
