"""Removing a prefix, and the snapshots that outlive it.

The two properties worth protecting. Nothing unattributable is ever removed --
AffinityOnLinux's own Affinity.desktop is reported as left alone, not deleted.
And the confirmation is the list: every row that would go is a row, so there is
no summary for the one you would have objected to to hide behind.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import (  # noqa: E402
    desktopentry, hoststate, prefixlog, prefsseed, registry, removal, snapshots,
)


@pytest.fixture
def host(tmp_path, monkeypatch):
    """A throwaway XDG data home and manager directory."""
    data = tmp_path / "data"
    (data / "applications").mkdir(parents=True)
    (data / "mime" / "packages").mkdir(parents=True)
    (data / "icons").mkdir(parents=True)
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setattr(registry, "manager_dir", lambda: tmp_path / "meta")
    (tmp_path / "meta").mkdir()
    monkeypatch.setattr(desktopentry, "refresh_menu", lambda: None)

    prefix = tmp_path / "Working"
    (prefix / "drive_c" / "windows").mkdir(parents=True)
    (prefix / "dosdevices").mkdir(parents=True)
    (prefix / "system.reg").write_text("WINE REGISTRY\n")

    reg = registry.Registry(tmp_path / "meta" / "prefixes.json")
    reg.add("Working", str(prefix))
    return type("Host", (), {"tmp": tmp_path, "data": data,
                             "prefix": prefix, "reg": reg})()


def settings_in(prefix: Path, user="joshua", version="3.0") -> Path:
    s = prefix.joinpath("drive_c", "users", user, *prefsseed.APPDATA_TAIL,
                        version, "Settings")
    s.mkdir(parents=True)
    (s / "preferences.dat").write_text("mine")
    (s / "RecentFiles.xml").write_text("<recent>a year of work</recent>")
    (s.parent / "sess.db").write_text("session")
    (s.parent / "loose.dat").write_text("beside Settings")
    return s


def kinds(plan):
    return [i.kind for i in plan.items]


# ── the plan ───────────────────────────────────────────────────────────────

def test_the_plan_lists_the_directory_and_the_registry_row(host):
    plan = removal.plan(host.reg, "Working")
    assert "prefix" in kinds(plan) and "registry" in kinds(plan)
    assert plan.size > 0


def test_the_plan_includes_the_menu_entry_it_wrote(host):
    from affinity_manager import commands as commands_mod

    command = commands_mod.for_prefix(host.prefix)[0]
    desktopentry.write("Working", command)
    plan = removal.plan(host.reg, "Working")
    assert "menu" in kinds(plan)


def test_a_desktop_file_that_is_not_ours_is_reported_not_offered(host):
    """AffinityOnLinux writes Affinity.desktop with a fixed name and every
    install rewrites it. It is not the manager's to remove."""
    foreign = host.data / "applications" / "Affinity.desktop"
    foreign.write_text("[Desktop Entry]\nName=Affinity\nExec=wine\n")
    plan = removal.plan(host.reg, "Working")
    assert all(i.path != foreign for i in plan.items)
    assert any(a.path == foreign for a in plan.left_alone)


def test_the_prefix_log_is_offered(host):
    prefixlog.write("Working", "something happened")
    plan = removal.plan(host.reg, "Working")
    assert "log" in kinds(plan)


def test_snapshots_are_listed_but_not_ticked(host):
    """Losing the backups of a thing along with the thing is the wrong
    default, and they are kilobytes."""
    settings_in(host.prefix)
    snapshots.take("Working", host.prefix, "before 3.3")
    plan = removal.plan(host.reg, "Working")
    backup = [i for i in plan.items if i.kind == "settings-backup"]
    assert len(backup) == 1 and backup[0].default is False
    assert backup[0] not in plan.chosen()


def test_a_prefix_whose_directory_has_gone_still_plans(host):
    import shutil
    shutil.rmtree(host.prefix)
    plan = removal.plan(host.reg, "Working")
    row = [i for i in plan.items if i.kind == "prefix"][0]
    assert row.default is False and "Not there" in row.detail
    assert "registry" in kinds(plan)


def test_an_unknown_prefix_is_a_keyerror_not_an_empty_plan(host):
    with pytest.raises(KeyError):
        removal.plan(host.reg, "Nonexistent")


# ── applying it ────────────────────────────────────────────────────────────

def test_only_the_ticked_rows_are_acted_on(host):
    prefixlog.write("Working", "keep me")
    plan = removal.plan(host.reg, "Working")
    only_registry = [i for i in plan.items if i.kind == "registry"]
    removal.apply(host.reg, plan, only_registry)
    assert host.reg.by_name("Working") is None
    assert host.prefix.is_dir()                       # not ticked, not touched
    assert prefixlog.path_for("Working").exists()


def test_everything_ticked_removes_the_prefix_and_the_row(host):
    plan = removal.plan(host.reg, "Working")
    notes = removal.apply(host.reg, plan, plan.chosen())
    assert not host.prefix.exists()
    assert host.reg.by_name("Working") is None
    assert any("Removed" in n for n in notes)


def test_a_running_prefix_removes_nothing_at_all(host, monkeypatch):
    monkeypatch.setattr(removal.probe, "running_pids", lambda *a: [4242])
    plan = removal.plan(host.reg, "Working")
    notes = removal.apply(host.reg, plan, plan.chosen())
    assert host.prefix.is_dir() and host.reg.by_name("Working") is not None
    assert "4242" in notes[0]


def test_what_was_left_alone_is_said_out_loud(host):
    foreign = host.data / "applications" / "Affinity.desktop"
    foreign.write_text("[Desktop Entry]\nName=Affinity\n")
    plan = removal.plan(host.reg, "Working")
    notes = removal.apply(host.reg, plan, plan.chosen())
    assert any("not ours" in n and "Affinity.desktop" in n for n in notes)
    assert foreign.exists()


def test_an_undeletable_item_is_reported_and_the_rest_still_goes(host, monkeypatch):
    """A removal that stopped half way because one file was read-only would be
    worse than one that reports it."""
    plan = removal.plan(host.reg, "Working")
    monkeypatch.setattr(removal.shutil, "rmtree",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("busy")))
    notes = removal.apply(host.reg, plan, plan.chosen())
    assert any("Could not remove" in n for n in notes)
    assert host.reg.by_name("Working") is None        # the rest still happened


# ── snapshots ──────────────────────────────────────────────────────────────

def test_a_snapshot_carries_the_settings_and_the_state_beside_them(host):
    settings_in(host.prefix)
    snap = snapshots.take("Working", host.prefix, "before 3.3")
    assert (snap.path / "Settings" / "RecentFiles.xml").is_file()
    assert (snap.path / "sess.db").is_file()
    assert (snap.path / "loose.dat").is_file()
    assert snap.prefix == "Working" and snap.label == "before-3.3"


def test_a_prefix_with_no_settings_says_so(host):
    with pytest.raises(snapshots.NoSettings):
        snapshots.take("Working", host.prefix)


@pytest.mark.parametrize("label", [
    "../../etc/passwd",
    "..",
    "../sibling",
    "/absolute",
    "a/b",
    ".hidden",
])
def test_a_label_cannot_escape_the_snapshots_directory(host, label):
    """The old single case could not fail: take() prepends YYYYmmdd-HHMMSS-,
    which turns a leading ".." into part of a literal directory name whatever
    _safe_label does. It passed with _safe_label replaced by a pass-through.
    These reach the separator and the leading dot as well."""
    settings_in(host.prefix)
    root = snapshots.dir_for("Working").resolve()
    snap = snapshots.take("Working", host.prefix, label)
    assert snap.path.resolve().parent == root
    assert "/" not in snap.path.name.split("-", 2)[-1]


def test_snapshots_are_listed_newest_first(host, monkeypatch):
    settings_in(host.prefix)
    stamps = iter(["20260101-000000", "20260202-000000", "20260303-000000"])
    monkeypatch.setattr(snapshots, "_stamp", lambda: next(stamps))
    for label in ("first", "second", "third"):
        snapshots.take("Working", host.prefix, label)
    assert [s.label for s in snapshots.listing("Working")] == \
        ["third", "second", "first"]


def test_a_snapshot_with_no_manifest_is_still_a_snapshot(host):
    settings_in(host.prefix)
    snap = snapshots.take("Working", host.prefix, "labelled")
    (snap.path / snapshots.MANIFEST).unlink()
    again = snapshots.read_manifest(snap.path)
    assert again.prefix == "unknown" and again.notes
    assert snapshots.listing("Working")          # still listed


# ── restoring ──────────────────────────────────────────────────────────────

def test_restoring_replaces_the_settings_and_keeps_the_old_ones(host):
    settings = settings_in(host.prefix)
    snap = snapshots.take("Working", host.prefix, "known-good")
    (settings / "RecentFiles.xml").write_text("<recent>changed since</recent>")

    plan = snapshots.plan_restore(snap, "Working", host.prefix)
    assert plan.crosses_prefixes is False
    notes = snapshots.restore(plan)
    assert (settings / "RecentFiles.xml").read_text() == \
        "<recent>a year of work</recent>"
    assert any("Replaced settings kept at" in n for n in notes)
    assert any("snapshotted as" in n for n in notes)


def test_restoring_into_another_prefix_is_allowed_and_says_so(host):
    settings_in(host.prefix)
    snap = snapshots.take("Working", host.prefix, "known-good")

    other = host.tmp / "Test33"
    (other / "drive_c" / "users" / "joshua").mkdir(parents=True)
    (other / "dosdevices").mkdir(parents=True)
    (other / "system.reg").write_text("WINE REGISTRY\n")

    plan = snapshots.plan_restore(snap, "Test33", other)
    assert plan.crosses_prefixes is True
    assert any("was taken from Working" in line for line in plan.describe())
    snapshots.restore(plan, snapshot_first=False)
    assert (plan.destination / "RecentFiles.xml").is_file()


def test_restoring_into_a_running_prefix_is_refused(host, monkeypatch):
    settings_in(host.prefix)
    snap = snapshots.take("Working", host.prefix)
    plan = snapshots.plan_restore(snap, "Working", host.prefix)
    monkeypatch.setattr(snapshots.probe if hasattr(snapshots, "probe")
                        else snapshots.maintenance.probe,
                        "running_pids", lambda *a: [999])
    with pytest.raises(snapshots.maintenance.Busy):
        snapshots.restore(plan)


def test_removing_something_outside_the_snapshots_directory_is_refused(host):
    """The manifest is a file on disk, and nothing stops somebody editing it."""
    settings_in(host.prefix)
    snap = snapshots.take("Working", host.prefix)
    snap.path = host.prefix                      # as an edited manifest might
    with pytest.raises(snapshots.NotASnapshot):
        snapshots.remove(snap)
    assert host.prefix.is_dir()


def test_the_stamp_is_shown_as_a_date_a_person_can_read(host):
    settings_in(host.prefix)
    snap = snapshots.take("Working", host.prefix, "known-good")
    assert snap.when.count("-") == 2 and ":" in snap.when
    assert snap.when in str(snap) and "known-good" in str(snap)


def test_an_unparseable_stamp_falls_back_to_itself(host):
    settings_in(host.prefix)
    snap = snapshots.take("Working", host.prefix)
    snap.taken = "handmade"
    assert snap.when == "handmade"


def test_a_mime_file_at_our_path_without_our_marker_is_not_removed(host):
    """The path is ours by convention; the marker is what makes the file ours.

    This is the branch the previous test does not reach: a foreign
    Affinity.desktop arrives through foreign_artifacts, never through
    artifacts_for. Something sitting at exactly the filename this prefix would
    use -- hand-written, or left by a version that named it differently -- goes
    through artifacts_for with owner FOREIGN, and must be reported rather than
    offered. Removing it would be this application deleting a file it did not
    write, at a path it guessed."""
    mime = hoststate.mime_path("Working")
    mime.parent.mkdir(parents=True, exist_ok=True)
    mime.write_text("<?xml version='1.0'?>\n<mime-info>not ours</mime-info>\n")
    assert hoststate.mime_owner(mime)[0] == hoststate.FOREIGN

    plan = removal.plan(host.reg, "Working")
    assert all(i.path != mime for i in plan.items), \
        "a file without our marker was offered for removal"
    assert any(a.path == mime for a in plan.left_alone)

    removal.apply(host.reg, plan, plan.chosen())
    assert mime.exists()


def test_a_mime_file_carrying_our_marker_is_removed(host):
    """The other half, so the test above is not passing for the wrong reason."""
    mime = hoststate.mime_path("Working")
    mime.parent.mkdir(parents=True, exist_ok=True)
    mime.write_text(
        f"<?xml version='1.0'?>\n<!-- {hoststate.MIME_MARKER}: Working -->\n"
        "<mime-info/>\n")
    plan = removal.plan(host.reg, "Working")
    assert any(i.path == mime for i in plan.items)
    removal.apply(host.reg, plan, plan.chosen())
    assert not mime.exists()


# ── the document association is actually released ──────────────────────────

def write_mimeapps(config: Path, entry: str) -> Path:
    path = config / "mimeapps.list"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Added Associations]\n"
        f"application/afphoto={entry};\n"
        "[Default Applications]\n"
        f"application/afphoto={entry};\n"
        f"application/afdesign=someone-else.desktop;{entry};\n"
        "application/pdf=okular.desktop;\n"
        # A type the USER associated with Affinity by hand. The manager only
        # ever sets the four document types, so this one is not its to undo.
        f"image/png={entry};\n"
    )
    return path


def test_clearing_a_handler_drops_only_the_lines_naming_it(host, monkeypatch, tmp_path):
    config = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    path = write_mimeapps(config, "affinity-manager-working-launch.desktop")

    hoststate.clear_handlers("affinity-manager-working-launch.desktop")
    text = path.read_text()

    # The type it solely held now has no default at all.
    assert "application/afphoto=" not in text.split("[Default Applications]")[1]
    # The one it shared keeps the other application.
    assert "application/afdesign=someone-else.desktop;" in text
    # Somebody else's type is untouched, and so is the other section.
    assert "application/pdf=okular.desktop;" in text
    assert "[Added Associations]" in text
    # And a type outside the four this application manages is left alone even
    # though it names the same entry: the manager did not set it, so removing
    # a prefix does not get to undo it.
    assert f"image/png=affinity-manager-working-launch.desktop;" in text


def test_clearing_a_handler_nobody_records_changes_nothing(host, monkeypatch, tmp_path):
    config = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    path = write_mimeapps(config, "affinity-manager-working-launch.desktop")
    before = path.read_text()
    assert hoststate.clear_handlers("not-ours.desktop") == []
    assert path.read_text() == before


def test_a_default_handler_row_does_not_abort_the_removal(host, monkeypatch, tmp_path):
    """hoststate.delete raises ValueError for an artifact with no path, and
    that ValueError used to escape apply() -- after the prefix directory had
    already been deleted, leaving the registry still listing it."""
    config = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    entry = "affinity-manager-working-launch.desktop"
    write_mimeapps(config, entry)
    monkeypatch.setattr(hoststate, "default_handlers", lambda: [
        hoststate.Artifact("default-handler", None, hoststate.SHARED, None,
                           "application/afphoto opens with " + entry, value=entry)])
    monkeypatch.setattr(desktopentry, "entries_for",
                        lambda name: [host.data / "applications" / entry])

    plan = removal.plan(host.reg, "Working")
    assert any(i.kind == "default-handler" for i in plan.items)

    notes = removal.apply(host.reg, plan, plan.chosen())      # must not raise
    assert not host.prefix.exists()
    assert host.reg.by_name("Working") is None
    assert any("no default handler now" in n for n in notes)


def test_a_prefix_started_while_the_dialog_was_open_is_not_deleted(host, monkeypatch):
    """The plan's pids are read when the dialog is built. It can sit open for
    as long as somebody reads it -- long enough to double-click a document and
    have the desktop start Affinity in the prefix being removed."""
    from affinity_manager import liveness

    plan = removal.plan(host.reg, "Working")
    assert plan.running == []
    running = liveness.Activity(str(host.prefix))
    running.procs.append(liveness.Proc(4242, "Affinity.exe", 1e9, liveness.AFFINITY))
    monkeypatch.setattr(liveness, "scan", lambda *a, **k: running)
    notes = removal.apply(host.reg, plan, plan.chosen())
    assert host.prefix.is_dir() and host.reg.by_name("Working") is not None
    assert "4242" in notes[0]


# ── snapshots: completeness, atomicity, and a manifest that lies ───────────

def test_a_snapshot_carries_the_directories_beside_settings_too(host):
    """Affinity keeps keyboard shortcuts and workspace layouts in DIRECTORIES
    beside Settings. The dialog promises the snapshot holds the shortcuts, and
    a files-only rule meant it did not."""
    settings = settings_in(host.prefix)
    version = settings.parent
    (version / "Workspaces").mkdir()
    (version / "Workspaces" / "mine.xml").write_text("<workspace/>")
    (version / "Shortcuts").mkdir()
    (version / "Shortcuts" / "keys.bin").write_bytes(b"\x01\x02")

    snap = snapshots.take("Working", host.prefix, "with-everything")
    assert (snap.path / "Workspaces" / "mine.xml").is_file()
    assert (snap.path / "Shortcuts" / "keys.bin").is_file()
    assert (snap.path / "sess.db").is_file()


def test_an_interrupted_take_is_never_offered_as_a_snapshot(host, monkeypatch):
    """A half-copied directory presented as a finished backup is the worst
    thing a backup can be."""
    settings_in(host.prefix)
    real_copytree = snapshots.shutil.copytree

    def fail_partway(src, dst, **kw):
        real_copytree(src, dst, **kw)
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(snapshots.shutil, "copytree", fail_partway)
    with pytest.raises(OSError):
        snapshots.take("Working", host.prefix, "doomed")

    assert snapshots.listing("Working") == []
    leftovers = [p for p in snapshots.dir_for("Working").iterdir()]
    assert leftovers == [], f"staging left behind: {leftovers}"


def test_a_manifest_that_is_not_an_object_does_not_take_the_dialog_down(host):
    """Valid JSON that is not a dict passed the except and then met .get(),
    and the AttributeError took both the snapshots dialog and the removal plan
    with it -- listing() is on both paths."""
    settings_in(host.prefix)
    snap = snapshots.take("Working", host.prefix, "fine")
    (snap.path / snapshots.MANIFEST).write_text("[1, 2, 3]")

    listed = snapshots.listing("Working")
    assert len(listed) == 1 and listed[0].prefix == "unknown"
    assert removal.plan(host.reg, "Working")          # must not raise


def test_a_manifest_with_wrong_types_does_not_crash(host):
    settings_in(host.prefix)
    snap = snapshots.take("Working", host.prefix, "fine")
    (snap.path / snapshots.MANIFEST).write_text(
        '{"prefix": 7, "label": null, "taken": [], "version": {}}')
    listed = snapshots.listing("Working")
    assert len(listed) == 1 and listed[0].version == "unknown"
    assert isinstance(listed[0].when, str)


def test_restoring_replaces_the_loose_state_and_removes_what_is_stale(host):
    """The swap is of the whole version folder. Copying the loose state in
    afterwards, one file at a time, left exactly the mixed configuration the
    docstring said was impossible -- and never removed siblings the snapshot
    did not have."""
    settings = settings_in(host.prefix)
    version = settings.parent
    (version / "Workspaces").mkdir()
    (version / "Workspaces" / "mine.xml").write_text("original")
    snap = snapshots.take("Working", host.prefix, "known-good")

    # The prefix moves on: the session changes and a workspace is added.
    (version / "sess.db").write_text("a later session")
    (version / "Workspaces" / "mine.xml").write_text("edited since")
    (version / "Workspaces" / "added-later.xml").write_text("new")

    plan = snapshots.plan_restore(snap, "Working", host.prefix)
    snapshots.restore(plan, snapshot_first=False)

    assert (version / "sess.db").read_text() == "session"
    assert (version / "Workspaces" / "mine.xml").read_text() == "original"
    assert not (version / "Workspaces" / "added-later.xml").exists(), \
        "a stale sibling survived the restore"


def test_the_safety_net_snapshots_the_folder_being_overwritten(host):
    """A prefix carried from 3.0 to 3.3 has two version folders. Backing up
    whichever is newest instead of the one about to be replaced is the same as
    not backing up at all."""
    old_settings = settings_in(host.prefix, version="3.0")
    (old_settings / "preferences.dat").write_text("the 3.0 preferences")
    new_settings = settings_in(host.prefix, version="3.3")
    (new_settings / "preferences.dat").write_text("the 3.3 preferences")
    source = snapshots.prefsseed.Settings(host.prefix, new_settings, "3.3",
                                          1, 1, 0.0)
    snap = snapshots.take("Working", host.prefix, "from-33", settings=source)

    # Restore it into the 3.0 folder. The net must back up 3.0, not 3.3.
    plan = snapshots.plan_restore(snap, "Working", host.prefix)
    plan.destination = old_settings
    snapshots.restore(plan, snapshot_first=True)

    before = [s for s in snapshots.listing("Working") if s.label == "before-restore"]
    assert len(before) == 1
    assert (before[0].path / "Settings" / "preferences.dat").read_text() \
        == "the 3.0 preferences"


def test_staging_left_by_a_killed_process_is_not_listed(host):
    """The cleanup in take() covers an exception. It cannot cover SIGKILL or
    the machine losing power, and what is on disk then looks exactly like a
    snapshot directory -- so listing() skips the name outright."""
    settings_in(host.prefix)
    snapshots.take("Working", host.prefix, "real")

    orphan = snapshots.dir_for("Working") / "20260101-000000-doomed.taking"
    (orphan / "Settings").mkdir(parents=True)
    (orphan / "Settings" / "preferences.dat").write_text("half a copy")

    listed = snapshots.listing("Working")
    assert [s.label for s in listed] == ["real"]
    assert orphan.is_dir(), "the orphan is skipped, not deleted behind the user's back"


# ── attribution by exact value, not by substring ───────────────────────────

def test_a_prefix_whose_name_starts_another_keeps_its_menu_entries(host, monkeypatch):
    """Prefix names may contain spaces, so "Test" is a string prefix of
    "Test 33". Matching the substring "X-AffinityManager-Prefix=Test" claimed
    both, and removing "Test" deleted the other prefix's menu entries."""
    apps = host.data / "applications"
    short = apps / "affinity-manager-test-launch.desktop"
    longer = apps / "affinity-manager-test-33-launch.desktop"
    short.write_text(f"[Desktop Entry]\nName=Test\n{desktopentry.MARKER}=Test\n")
    longer.write_text(f"[Desktop Entry]\nName=Test 33\n{desktopentry.MARKER}=Test 33\n")

    assert desktopentry.entries_for("Test") == [short]
    assert desktopentry.entries_for("Test 33") == [longer]
    assert desktopentry.owner_of(longer) == "Test 33"


def test_two_names_that_become_one_directory_are_refused(host):
    """dir_name substitutes rather than strips, so "Affinity 33" and
    "Affinity_33" are different names with the SAME slug -- and the slug names
    the snapshots directory, the log, the MIME package and the icon. Removing
    one would have deleted the other's."""
    host.reg.add("Affinity 33", str(host.tmp / "a"))
    with pytest.raises(registry.DuplicateName) as caught:
        host.reg.add("Affinity_33", str(host.tmp / "b"))
    assert "Affinity_33" in str(caught.value)
    assert host.reg.by_name("Affinity_33") is None


def test_renaming_onto_a_colliding_slug_is_refused(host):
    host.reg.add("Affinity 33", str(host.tmp / "a"))
    host.reg.add("Something else", str(host.tmp / "b"))
    with pytest.raises(registry.DuplicateName):
        host.reg.rename("Something else", "Affinity_33")
    assert host.reg.by_name("Something else") is not None


def test_renaming_a_prefix_to_itself_is_not_a_collision(host):
    host.reg.add("Affinity 33", str(host.tmp / "a"))
    host.reg.rename("Affinity 33", "Affinity  33")   # same slug, same prefix
    assert host.reg.by_name("Affinity  33") is not None


def test_a_snapshot_leaves_out_autosaves_and_the_webview_profile(host):
    """Every snapshot of the working prefix was 224 MB, 205 of it crash-recovery
    autosaves. A backup of settings is not a backup of those."""
    settings = settings_in(host.prefix)
    version = settings.parent
    for d in ("autosave", "EBWebView", "temp"):
        (version / d).mkdir()
        (version / d / "big").write_bytes(b"x" * 4096)
    (version / "pid").write_text("12345")
    (version / "Workspaces").mkdir()

    snap = snapshots.take("Working", host.prefix, "lean")
    for name in ("autosave", "EBWebView", "temp", "pid"):
        assert not (snap.path / name).exists(), f"{name} was snapshotted"
    assert (snap.path / "Workspaces").is_dir()
    assert (snap.path / "sess.db").is_file(), "unrecognised state is kept in a backup"
