"""Backups: an exact copy of a prefix and its desktop files, and putting it back.

A backup exists to undo an install, so the round trip is the test that
matters: take one, let an "install" rewrite the prefix and the shared desktop
files, restore, and check everything is as it was -- including the parts of
mimeapps.list that have nothing to do with Affinity, which must NOT be as they
were at the backup but as the user has left them since.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import backups, liveness, maintenance, registry, settings  # noqa: E402


def activity_of(*groups):
    """A stand-in for liveness.scan: one process per group named."""
    names = {liveness.AFFINITY: "Affinity.exe", liveness.HOOK: "AffinityHook.ex",
             liveness.SERVICE: "services.exe", liveness.OTHER: "keyspy.exe"}
    a = liveness.Activity("p")
    for i, g in enumerate(groups):
        a.procs.append(liveness.Proc(4242 + i, names[g], 1e9, g))
    return a


@pytest.fixture
def world(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".local" / "share" / "applications" / "wine" / "Programs").mkdir(parents=True)
    (home / ".local" / "share" / "mime" / "packages").mkdir(parents=True)
    (home / ".local" / "bin").mkdir(parents=True)
    (home / ".config").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    meta = tmp_path / "meta"
    meta.mkdir()
    monkeypatch.setattr(registry, "manager_dir", lambda: meta)
    monkeypatch.setattr(registry, "base_dir", lambda: tmp_path / "base")
    monkeypatch.setattr(maintenance, "LAUNCHER_DIRS", (str(home / ".local" / "bin"),))
    monkeypatch.setattr(backups, "_refresh_databases", lambda: None)
    monkeypatch.setattr(backups, "activity", lambda prefix: activity_of())
    # pytest's tmp_path lives on tmpfs, which backups rightly refuse -- a backup
    # in memory is gone at reboot. The fixture says what it pretends to be on;
    # tests about filesystems override it.
    monkeypatch.setattr(backups, "filesystem_type", lambda path: "ext4")

    prefix = home / ".AffinityLinux"
    (prefix / "drive_c" / "windows").mkdir(parents=True)
    (prefix / "dosdevices").mkdir()
    (prefix / "dosdevices" / "c:").symlink_to("../drive_c")
    (prefix / "dosdevices" / "w:").symlink_to("/mnt/work")
    (prefix / "system.reg").write_text("WINE REGISTRY v1\n")
    (prefix / "drive_c" / "windows" / "notepad.exe").write_bytes(b"MZ" + b"x" * 2000)
    build = prefix / "ElementalWarrior-wine-11.12" / "bin"
    build.mkdir(parents=True)
    (build / "wine").write_text("#!/bin/sh\n")
    (prefix / "ElementalWarriorWine").symlink_to("ElementalWarrior-wine-11.12")

    apps = home / ".local" / "share" / "applications"
    (apps / "Affinity.desktop").write_text(f"Exec=env WINEPREFIX={prefix} wine\n")
    (apps / "wine-extension-afphoto.desktop").write_text(f"WINEPREFIX={prefix}\n")
    (apps / "wine" / "Programs" / "Affinity.desktop").write_text("old wine entry\n")
    (apps / "firefox.desktop").write_text("not ours\n")
    mime = home / ".local" / "share" / "mime" / "packages"
    (mime / "x-wine-extension-afphoto.xml").write_text("<old/>")
    (home / ".local" / "bin" / "affinity-gpu").write_text(f'PFX="{prefix}"\n')
    (home / ".config" / "mimeapps.list").write_text(
        "[Default Applications]\n"
        "application/afphoto=Affinity.desktop;\n"
        "application/pdf=okular.desktop;\n"
        "[Added Associations]\n"
        "application/x-wine-extension-afphoto=wine-extension-afphoto.desktop;\n")

    location = tmp_path / "backups"
    return type("World", (), {"home": home, "prefix": prefix, "apps": apps,
                              "mime": mime, "location": location,
                              "tmp": tmp_path})()


def take(world, label=""):
    plan = backups.plan_backup("AffinityLinux", world.prefix, world.location,
                               label=label)
    return backups.create(plan)


def simulate_install(world):
    """What installing into a new prefix does to the shared files."""
    new = world.home / ".AffinityLinuxManager" / "AffinityLinux_3.3"
    (world.apps / "Affinity.desktop").write_text(f"Exec=env WINEPREFIX={new} wine\n")
    (world.apps / "wine-extension-afphoto.desktop").write_text(f"WINEPREFIX={new}\n")
    (world.apps / "wine-extension-xaml.desktop").write_text(f"WINEPREFIX={new}\n")
    (world.mime / "x-wine-extension-afphoto.xml").unlink()
    (world.mime / "affinity-x-wine-extension-afphoto.xml").write_text("<new/>")
    (world.home / ".config" / "mimeapps.list").write_text(
        "[Default Applications]\n"
        "application/afphoto=Affinity-new.desktop;\n"
        "application/afpub=Affinity-new.desktop;\n"
        "application/pdf=evince.desktop;\n"          # the user's own change
        "[Added Associations]\n"
        "application/x-wine-extension-afphoto=wine-extension-afphoto.desktop;\n")


# ── taking one ─────────────────────────────────────────────────────────────

def test_the_prefix_is_copied_exactly_symlinks_and_all(world):
    b = take(world)
    copy = b.path / "prefix"
    assert (copy / "drive_c" / "windows" / "notepad.exe").read_bytes().startswith(b"MZ")
    assert os.readlink(copy / "dosdevices" / "c:") == "../drive_c"
    assert os.readlink(copy / "dosdevices" / "w:") == "/mnt/work"
    # Not repointed, unlike a clone: a backup goes back where it came from.
    assert os.readlink(copy / "ElementalWarriorWine") == "ElementalWarrior-wine-11.12"
    assert b.status == "ok" and b.files > 0 and b.bytes > 0


def test_the_desktop_files_are_captured_and_nothing_else(world):
    b = take(world)
    captured = {i["path"] for i in b.host_files}
    assert ".local/share/applications/Affinity.desktop" in captured
    assert ".local/share/applications/wine-extension-afphoto.desktop" in captured
    assert ".local/share/applications/wine/Programs/Affinity.desktop" in captured
    assert ".local/share/mime/packages/x-wine-extension-afphoto.xml" in captured
    assert ".local/bin/affinity-gpu" in captured
    assert ".local/share/applications/firefox.desktop" not in captured


def test_only_affinity_keys_of_mimeapps_are_recorded(world):
    b = take(world)
    recorded = b.mimeapps[".config/mimeapps.list"]
    assert recorded["[Default Applications]"] == {"application/afphoto": "Affinity.desktop;"}
    assert "application/pdf" not in json.dumps(recorded)


def test_a_backup_inside_the_prefix_is_refused(world):
    with pytest.raises(backups.BackupError):
        backups.plan_backup("AffinityLinux", world.prefix, world.prefix / "bk")


def test_a_running_prefix_is_not_backed_up(world, monkeypatch):
    plan = backups.plan_backup("AffinityLinux", world.prefix, world.location)
    monkeypatch.setattr(backups, "activity",
                        lambda prefix: activity_of(liveness.AFFINITY))
    with pytest.raises(backups.InUse) as caught:
        backups.create(plan)
    assert "4242" in str(caught.value)
    assert not plan.partial.exists() and not plan.dest.exists()


def test_leftovers_do_not_stop_a_backup(world, monkeypatch):
    """Two-week-old Wine services with no wineserver, a stranded launcher:
    nothing is writing the prefix. Refusing on them is what made the manager
    say "running" about an Affinity closed a fortnight ago."""
    monkeypatch.setattr(backups, "activity", lambda prefix: activity_of(
        liveness.HOOK, liveness.SERVICE, liveness.OTHER))
    b = take(world)
    assert b.status == "ok"


def test_not_enough_space_is_refused_before_anything_is_written(world, monkeypatch):
    real = backups.describe_location

    def tiny(path, prefix, why=""):
        loc = real(path, prefix, why)
        loc.free = 10
        return loc

    monkeypatch.setattr(backups, "describe_location", tiny)
    with pytest.raises(maintenance.NotEnoughSpace):
        backups.plan_backup("AffinityLinux", world.prefix, world.location)
    assert not world.location.exists()


def test_an_interrupted_backup_is_never_listed_as_usable(world, monkeypatch):
    plan = backups.plan_backup("AffinityLinux", world.prefix, world.location)

    def die(*a, **k):
        raise maintenance.CloneFailed("disk unplugged")

    monkeypatch.setattr(maintenance, "copy_tree", die)
    with pytest.raises(maintenance.CloneFailed):
        backups.create(plan)
    listed = backups.listing()
    assert [b.status for b in listed] == ["partial"]
    with pytest.raises(backups.NotABackup):
        backups.plan_restore(listed[0])


def test_a_label_cannot_escape_the_location(world):
    b = take(world, label="../../etc")
    assert b.path.parent == world.location


def test_a_hyphenated_prefix_name_keeps_its_date(world):
    plan = backups.plan_backup("AffinityLinux-winetest", world.prefix, world.location)
    b = backups.create(plan)
    assert b.prefix_name == "AffinityLinux-winetest"
    assert b.when[:4].isdigit(), b.when


# ── finding them again ─────────────────────────────────────────────────────

def test_a_backup_is_found_even_if_the_index_is_lost(world):
    b = take(world)
    (registry.manager_dir() / "backups.json").unlink()
    assert [x.path for x in backups.listing()] == [b.path]


def test_an_unplugged_disk_is_listed_not_dropped(world):
    b = take(world)
    elsewhere = world.tmp / "moved"
    b.path.rename(elsewhere)
    statuses = {x.path: x.status for x in backups.listing()}
    assert statuses[b.path] == "unreachable"


def test_a_hostile_manifest_is_reported_not_crashed_on(world):
    b = take(world)
    (b.path / backups.MANIFEST).write_text("[1, 2, 3]")
    assert backups.read(b.path).status == "damaged"
    (b.path / backups.MANIFEST).write_text('{"files": "lots", "prefix_name": 7}')
    again = backups.read(b.path)
    assert again.files == 0 and again.prefix_name != 7


def test_verify_notices_a_damaged_copy(world):
    b = take(world)
    assert backups.verify(b) == []
    (b.path / "prefix" / "drive_c" / "windows" / "notepad.exe").unlink()
    assert backups.verify(b)


def test_only_our_own_directories_can_be_deleted(world):
    stranger = world.tmp / "someone-elses"
    (stranger / "prefix").mkdir(parents=True)
    with pytest.raises(backups.NotABackup):
        backups.remove(backups.Backup(stranger))
    assert stranger.is_dir()
    b = take(world)
    backups.remove(b)
    assert not b.path.exists() and backups.listing() == []


# ── putting it back ────────────────────────────────────────────────────────

def test_the_full_round_trip_undoes_an_install(world):
    b = take(world)
    (world.prefix / "system.reg").write_text("WINE REGISTRY v2 -- changed\n")
    simulate_install(world)

    plan = backups.plan_restore(b)
    notes = backups.restore(plan)

    # The prefix is as it was, and the one that was there is kept, not deleted.
    assert (world.prefix / "system.reg").read_text() == "WINE REGISTRY v1\n"
    assert plan.moved_aside_to.is_dir()
    assert (plan.moved_aside_to / "system.reg").read_text().endswith("changed\n")

    # The shared desktop files point at the old prefix again.
    assert str(world.prefix) in (world.apps / "Affinity.desktop").read_text()
    assert (world.mime / "x-wine-extension-afphoto.xml").read_text() == "<old/>"
    # What the install added is moved aside, not left to compete.
    assert not (world.mime / "affinity-x-wine-extension-afphoto.xml").exists()
    assert not (world.apps / "wine-extension-xaml.desktop").exists()
    assert any("kept in" in n for n in notes)


def test_restore_puts_back_only_the_affinity_associations(world):
    """The user changed their PDF viewer after the backup. A restore that put
    the whole mimeapps.list back would silently undo that."""
    b = take(world)
    simulate_install(world)
    backups.restore(backups.plan_restore(b, restore_prefix=False))
    text = (world.home / ".config" / "mimeapps.list").read_text()
    assert "application/afphoto=Affinity.desktop;" in text
    assert "application/afpub" not in text, "an association the install added survived"
    assert "application/pdf=evince.desktop;" in text, "the user's own change was undone"


def test_what_a_restore_replaced_can_itself_be_recovered(world):
    b = take(world)
    simulate_install(world)
    backups.restore(backups.plan_restore(b, restore_prefix=False))
    kept = list((registry.manager_dir() / "restores").rglob("Affinity.desktop"))
    assert kept and "AffinityLinux_3.3" in kept[0].read_text()


def test_restoring_only_the_desktop_files_leaves_the_prefix_alone(world):
    b = take(world)
    (world.prefix / "system.reg").write_text("changed\n")
    simulate_install(world)
    plan = backups.plan_restore(b, restore_prefix=False)
    backups.restore(plan)
    assert (world.prefix / "system.reg").read_text() == "changed\n"
    assert not list(world.prefix.parent.glob("*.before-restore-*"))


def test_a_failed_restore_leaves_the_current_prefix_where_it_was(world, monkeypatch):
    b = take(world)
    (world.prefix / "system.reg").write_text("current\n")

    def die(*a, **k):
        raise maintenance.CloneFailed("disk unplugged")

    monkeypatch.setattr(maintenance, "copy_tree", die)
    with pytest.raises(maintenance.CloneFailed):
        backups.restore(backups.plan_restore(b))
    assert (world.prefix / "system.reg").read_text() == "current\n"
    assert not list(world.prefix.parent.glob("*.restoring"))
    assert not list(world.prefix.parent.glob("*.before-restore-*"))


def test_a_running_prefix_is_not_restored_over(world, monkeypatch):
    b = take(world)
    plan = backups.plan_restore(b)
    monkeypatch.setattr(backups, "activity",
                        lambda prefix: activity_of(liveness.AFFINITY))
    with pytest.raises(backups.InUse):
        backups.restore(plan)
    assert (world.prefix / "system.reg").read_text() == "WINE REGISTRY v1\n"


def test_leftovers_must_be_ended_before_a_restore_replaces_the_prefix(world, monkeypatch):
    """They have the prefix open, and it is about to be swapped for another."""
    b = take(world)
    plan = backups.plan_restore(b)
    monkeypatch.setattr(backups, "activity",
                        lambda prefix: activity_of(liveness.SERVICE))
    with pytest.raises(backups.InUse) as caught:
        backups.restore(plan)
    assert "End them first" in str(caught.value)


def test_the_plan_says_what_will_happen_before_it_happens(world):
    b = take(world)
    simulate_install(world)
    lines = " ".join(backups.plan_restore(b).describe())
    assert "renamed" in lines and "not deleted" in lines
    assert "moved aside" in lines


# ── locations ──────────────────────────────────────────────────────────────

def test_recently_used_locations_are_offered(world, monkeypatch):
    store = {}
    monkeypatch.setattr(settings, "get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(settings, "set", lambda k, v: store.__setitem__(k, v))
    take(world)
    offered = [str(l.path) for l in backups.candidate_locations(world.prefix)]
    assert str(world.location) in offered


def test_a_partition_is_reported_as_its_disk(monkeypatch, tmp_path):
    """/home and /mnt/work on this machine are nvme0n1p3 and nvme0n1p4: one
    drive. A backup that is "elsewhere" by filesystem is not elsewhere when
    that drive fails."""
    fake = tmp_path / "sys" / "nvme0n1" / "nvme0n1p4"
    fake.mkdir(parents=True)
    (fake / "partition").write_text("4\n")
    real_path = backups.Path

    class FakeNode(type(tmp_path)):
        pass

    monkeypatch.setattr(os, "stat", lambda p: type("S", (), {"st_dev": os.makedev(259, 4)})())
    original = backups.Path.resolve

    def resolve(self, strict=False):
        if str(self).startswith("/sys/dev/block/259:4"):
            return fake
        return original(self, strict=strict)

    monkeypatch.setattr(backups.Path, "resolve", resolve)
    assert backups.physical_disk(tmp_path) == "nvme0n1"


@pytest.mark.parametrize("name", [
    "AffinityLinux",
    "AffinityLinux 26-09-16 - Working Copy - 3.3 Test with a much longer name",
    "Weird (name) with [brackets]",
])
def test_the_replaced_prefix_always_gets_a_name_the_list_accepts(name):
    """The first version used parentheses, which the registry refuses, so the
    replaced prefix never appeared in the list where it could be removed."""
    aside = backups.aside_name(name)
    assert registry.validate_name(aside) == aside
    assert aside.endswith(backups.time.strftime("%Y-%m-%d %H%M")) or "before restore" in aside


# ── what a location can and cannot hold ────────────────────────────────────

def mounts(monkeypatch, text):
    real_read = backups.Path.read_text

    def read_text(self, *a, **k):
        if str(self) == "/proc/self/mounts":
            return text
        return real_read(self, *a, **k)

    monkeypatch.setattr(backups.Path, "read_text", read_text)


def test_a_mount_point_with_a_space_is_decoded(monkeypatch, tmp_path):
    """/proc/self/mounts writes "Work Backup" as "Work\\040Backup". Without
    decoding it, a removable drive with a space in its label looked like part
    of the filesystem above it."""
    drive = tmp_path / "Work Backup"
    (drive / "Work").mkdir(parents=True)
    escaped = str(drive).replace(" ", "\\040")
    mounts(monkeypatch, f"/dev/nvme0n1p3 / ext4 rw 0 0\n/dev/sda1 {escaped} exfat rw 0 0\n")
    assert backups.filesystem_type(drive / "Work" / "Affinity backups") == "exfat"


@pytest.mark.parametrize("fstype,usable", [
    ("ext4", True), ("btrfs", True), ("xfs", True),
    ("exfat", False), ("vfat", False),        # no symlinks
    ("tmpfs", False), ("ramfs", False),       # gone at reboot
    ("ntfs3", True),                          # allowed, with the reason said
])
def test_which_filesystems_can_hold_a_backup(world, monkeypatch, fstype, usable):
    monkeypatch.setattr(backups, "filesystem_type", lambda p: fstype)
    loc = backups.describe_location(world.location, world.prefix)
    assert loc.usable is usable
    if not usable:
        with pytest.raises(backups.BackupError):
            backups.plan_backup("AffinityLinux", world.prefix, world.location)


def test_an_unwritable_location_names_the_folder_in_the_way(world, tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        loc = backups.describe_location(locked / "backups", world.prefix)
        assert not loc.usable and loc.blocker == locked
        assert str(locked) in loc.describe(1)
    finally:
        locked.chmod(0o755)
