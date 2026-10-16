"""Clone and clean, against prefixes built in a temporary directory.

The dangerous cases are the ones worth pinning: removing a Wine build that is
in use, removing something outside the prefix, and a clone whose symlinks still
point at the original.
"""
import os
import sys
from collections import namedtuple
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import maintenance  # noqa: E402


def make_prefix(root: Path, builds=("wine-a", "wine-b"), link_to="wine-a") -> Path:
    p = root / "prefix"
    (p / "drive_c" / "windows").mkdir(parents=True)
    (p / "dosdevices").mkdir(parents=True)
    (p / "system.reg").write_text("WINE REGISTRY Version 2\n")
    (p / "user.reg").write_text("WINE REGISTRY Version 2\n")
    os.symlink("../drive_c", p / "dosdevices" / "c:")
    os.symlink("/", p / "dosdevices" / "z:")
    for b in builds:
        (p / b / "bin").mkdir(parents=True)
        (p / b / "bin" / "wine").write_text("#!/bin/sh\n")
        (p / b / "bin" / "wine").chmod(0o755)
        (p / b / "payload").write_bytes(b"x" * 4096)
    if link_to:
        os.symlink(link_to, p / "ElementalWarriorWine")
    return p


def test_cleanable_never_offers_the_build_the_symlink_names(tmp_path):
    p = make_prefix(tmp_path)
    offered = {i.path.name for i in maintenance.cleanable(p)}
    assert "wine-a" not in offered      # ElementalWarriorWine -> wine-a
    assert "ElementalWarriorWine" not in offered
    assert "wine-b" in offered


def test_clean_refuses_a_target_outside_the_prefix(tmp_path):
    p = make_prefix(tmp_path)
    outsider = tmp_path / "not-mine"
    outsider.mkdir()
    item = maintenance.Item(outsider, "wine-build", 0, "planted")
    freed, problems = maintenance.clean(p, [item])
    assert outsider.exists()
    assert any("outside the prefix" in m for m in problems)


def test_clean_rechecks_protection_rather_than_trusting_the_plan(tmp_path):
    """A plan can be built before the symlink moves. The build it now names
    must survive even though the caller asked for it."""
    p = make_prefix(tmp_path, link_to="wine-a")
    plan = [i for i in maintenance.cleanable(p) if i.path.name == "wine-b"]
    assert plan
    (p / "ElementalWarriorWine").unlink()
    os.symlink("wine-b", p / "ElementalWarriorWine")
    freed, problems = maintenance.clean(p, plan)
    assert (p / "wine-b").exists()
    assert any("in use" in m for m in problems)


def test_clean_removes_what_it_offers(tmp_path):
    p = make_prefix(tmp_path)
    (p / "wine.tar.xz").write_bytes(b"y" * 2048)
    items = maintenance.cleanable(p)
    assert any(i.kind == "archive" for i in items)
    freed, problems = maintenance.clean(p, items)
    assert problems == []
    assert not (p / "wine-b").exists()
    assert not (p / "wine.tar.xz").exists()
    assert (p / "wine-a").exists()
    assert freed > 4096


def test_clone_keeps_symlinks_as_symlinks(tmp_path):
    p = make_prefix(tmp_path)
    dest = tmp_path / "copy"
    plan = maintenance.plan_clone(p, dest)
    maintenance.clone(plan)
    assert (dest / "dosdevices" / "c:").is_symlink()
    assert os.readlink(dest / "dosdevices" / "c:") == "../drive_c"
    assert os.readlink(dest / "dosdevices" / "z:") == "/"


def test_clone_repoints_absolute_links_that_pointed_into_the_source(tmp_path):
    p = make_prefix(tmp_path)
    (p / "ElementalWarriorWine").unlink()
    os.symlink(str(p / "wine-a"), p / "ElementalWarriorWine")   # absolute
    dest = tmp_path / "copy"
    maintenance.clone(maintenance.plan_clone(p, dest))
    target = os.readlink(dest / "ElementalWarriorWine")
    assert str(dest) in target, target
    assert str(p) not in target


def test_clone_leaves_links_pointing_outside_the_prefix_alone(tmp_path):
    p = make_prefix(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(str(elsewhere), p / "external")
    dest = tmp_path / "copy"
    maintenance.clone(maintenance.plan_clone(p, dest))
    assert os.readlink(dest / "external") == str(elsewhere)


def test_clone_keeps_exactly_the_builds_named(tmp_path):
    p = make_prefix(tmp_path, builds=("wine-a", "wine-b", "wine-c"), link_to="wine-a")
    dest = tmp_path / "copy"
    plan = maintenance.plan_clone(p, dest, keep_builds=["wine-c"])
    assert set(plan.drop_builds) == {"wine-a", "wine-b"}
    maintenance.clone(plan)
    assert (dest / "wine-c").is_dir()
    assert not (dest / "wine-a").exists()
    assert not (dest / "wine-b").exists()


def test_clone_keeps_everything_when_no_choice_is_given(tmp_path):
    """The old default guessed from the symlink and kept the wrong build."""
    p = make_prefix(tmp_path, builds=("wine-a", "wine-b"), link_to="wine-a")
    dest = tmp_path / "copy"
    plan = maintenance.plan_clone(p, dest)
    assert plan.drop_builds == []
    maintenance.clone(plan)
    assert (dest / "wine-a").is_dir() and (dest / "wine-b").is_dir()


def test_describe_builds_does_not_present_the_symlink_as_fact(tmp_path):
    """With nothing running the symlink is the only evidence, and it can be
    stale -- so it must be reported as a claim, not as 'this is the one'."""
    p = make_prefix(tmp_path, builds=("wine-a", "wine-b"), link_to="wine-a")
    rows = {b["name"]: b for b in maintenance.describe_builds(p)}
    assert rows["wine-a"]["suggested"] is True
    assert "stale" in rows["wine-a"]["note"]
    assert rows["wine-b"]["suggested"] is False


def test_clone_refuses_a_destination_inside_the_source(tmp_path):
    p = make_prefix(tmp_path)
    with pytest.raises(maintenance.DestinationInUse):
        maintenance.plan_clone(p, p / "inner")


def test_clone_refuses_a_non_empty_destination(tmp_path):
    p = make_prefix(tmp_path)
    dest = tmp_path / "copy"
    dest.mkdir()
    (dest / "something").write_text("occupied")
    with pytest.raises(maintenance.DestinationInUse):
        maintenance.plan_clone(p, dest)


def test_plan_clone_rejects_a_directory_that_is_not_a_prefix(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(maintenance.NotAPrefix):
        maintenance.plan_clone(plain, tmp_path / "copy")


def test_launchers_outrank_the_symlink(tmp_path):
    """The case that caused a bad clone: the symlink says one build, the
    desktop entry launches another, and the desktop entry is the truth."""
    p = make_prefix(tmp_path, builds=("wine-old", "wine-new"), link_to="wine-old")
    apps = tmp_path / "applications"
    apps.mkdir()
    (apps / "Affinity.desktop").write_text(
        "[Desktop Entry]\n"
        f"Exec=env WINEPREFIX={p} {p}/wine-new/bin/wine \"C:/Affinity.exe\"\n"
    )
    named = maintenance.builds_named_by_launchers(p, dirs=[str(apps)])
    assert named == {"wine-new"}


def test_describe_builds_reports_launcher_evidence_as_fact(tmp_path, monkeypatch):
    p = make_prefix(tmp_path, builds=("wine-old", "wine-new"), link_to="wine-old")
    apps = tmp_path / "applications"
    apps.mkdir()
    (apps / "a.desktop").write_text(f"Exec={p}/wine-new/bin/wine\n")
    monkeypatch.setattr(maintenance, "LAUNCHER_DIRS", (str(apps),))
    rows = {b["name"]: b for b in maintenance.describe_builds(p)}
    assert rows["wine-new"]["suggested"] is True
    assert "launcher" in rows["wine-new"]["note"]
    # the stale symlink is still offered, but as a claim
    assert "stale" in rows["wine-old"]["note"]


def test_protected_builds_keeps_what_a_launcher_names(tmp_path, monkeypatch):
    p = make_prefix(tmp_path, builds=("wine-old", "wine-new"), link_to="wine-old")
    apps = tmp_path / "applications"
    apps.mkdir()
    (apps / "a.desktop").write_text(f"Exec={p}/wine-new/bin/wine\n")
    monkeypatch.setattr(maintenance, "LAUNCHER_DIRS", (str(apps),))
    assert "wine-new" in maintenance.protected_builds(p)
    offered = {i.path.name for i in maintenance.cleanable(p)}
    assert "wine-new" not in offered


def test_clone_repoints_a_symlink_left_dangling_by_a_dropped_build(tmp_path):
    """The installer resolves Wine through ElementalWarriorWine. Drop the build
    it names and the copy looks like it has no Wine at all."""
    p = make_prefix(tmp_path, builds=("wine-old", "wine-new"), link_to="wine-old")
    dest = tmp_path / "copy"
    maintenance.clone(maintenance.plan_clone(p, dest, keep_builds=["wine-new"]))
    link = dest / "ElementalWarriorWine"
    assert link.is_symlink()
    assert link.exists(), "symlink is dangling"
    assert os.readlink(link) == "wine-new"


def test_fix_wine_symlink_removes_the_link_when_there_is_no_wine(tmp_path):
    p = make_prefix(tmp_path, builds=("wine-a",), link_to="wine-a")
    shutil_rm = __import__("shutil").rmtree
    shutil_rm(p / "wine-a")
    assert maintenance.fix_wine_symlink(p) is None
    assert not (p / "ElementalWarriorWine").is_symlink()


def test_fix_wine_symlink_leaves_a_working_link_alone(tmp_path):
    p = make_prefix(tmp_path, builds=("wine-a", "wine-b"), link_to="wine-a")
    assert maintenance.fix_wine_symlink(p) == "wine-a"
    assert os.readlink(p / "ElementalWarriorWine") == "wine-a"


# ----------------------------------------------------------------------------
# The refusals. An audit found that nothing here exercised the module's most
# important property -- that it will not act on a running prefix -- and that a
# failed copy was reported as a successful clone.


def test_clone_refuses_a_running_prefix(tmp_path, monkeypatch):
    p = make_prefix(tmp_path)
    plan = maintenance.plan_clone(p, tmp_path / "copy")
    monkeypatch.setattr(maintenance.probe, "running_pids", lambda _p: [4242])
    with pytest.raises(maintenance.Busy) as e:
        maintenance.clone(plan)
    assert "4242" in str(e.value)
    assert not (tmp_path / "copy").exists() or not any((tmp_path / "copy").iterdir())


def test_clean_refuses_a_running_prefix(tmp_path, monkeypatch):
    p = make_prefix(tmp_path)
    items = maintenance.cleanable(p)
    monkeypatch.setattr(maintenance.probe, "running_pids", lambda _p: [4242])
    with pytest.raises(maintenance.Busy):
        maintenance.clean(p, items)
    assert (p / "wine-b").exists()          # nothing was removed


def test_clean_dry_run_is_allowed_on_a_running_prefix(tmp_path, monkeypatch):
    """Reading and reporting is safe; only removal needs an idle prefix."""
    p = make_prefix(tmp_path)
    items = maintenance.cleanable(p)
    monkeypatch.setattr(maintenance.probe, "running_pids", lambda _p: [4242])
    freed, problems = maintenance.clean(p, items, dry_run=True)
    assert freed > 0 and not problems
    assert (p / "wine-b").exists()


def test_a_failed_copy_raises_rather_than_returning_problems(tmp_path, monkeypatch):
    """The caller announces success on a return and failure on an exception, so
    a partial copy must not come back as a list of notes."""
    p = make_prefix(tmp_path)
    plan = maintenance.plan_clone(p, tmp_path / "copy")

    class FakeProc:
        returncode = 23                      # rsync: partial transfer
        stdout = None
        def wait(self): return 23

    monkeypatch.setattr(maintenance.shutil, "which", lambda _n: "/usr/bin/rsync")
    monkeypatch.setattr(maintenance.subprocess, "Popen", lambda *a, **k: FakeProc())
    with pytest.raises(maintenance.CloneFailed) as e:
        maintenance.clone(plan)
    assert "23" in str(e.value)


def test_clone_refuses_when_the_destination_lacks_room(tmp_path, monkeypatch):
    p = make_prefix(tmp_path)
    plan = maintenance.plan_clone(p, tmp_path / "copy")
    assert plan.est_size > 0
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(maintenance.shutil, "disk_usage", lambda _p: Usage(0, 0, 1))
    with pytest.raises(maintenance.NotEnoughSpace):
        maintenance.clone(plan)


def test_clean_refuses_something_inside_a_protected_build(tmp_path):
    """The guard used to key on item.kind, so anything not classed "wine-build"
    was removable even when it sat inside the build that is in use -- including
    the saved-aside copies of patched DLLs, which are the only way back."""
    p = make_prefix(tmp_path)                 # ElementalWarriorWine -> wine-a
    inside = p / "wine-a" / "lib" / "d2d1.dll.bak"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(b"x" * 2048)
    item = maintenance.Item(path=inside, kind="backup", size=2048, reason="saved aside")
    freed, problems = maintenance.clean(p, [item])
    assert inside.exists()
    assert freed == 0
    assert any("wine-a" in m and "in use" in m for m in problems)


def test_newest_build_is_chosen_by_version_not_alphabetically(tmp_path):
    """sorted()[-1] picked ...11.16.stock-2026-09-08 over ...11.16 -- the stock
    build, with none of the prefix's patches."""
    p = make_prefix(tmp_path, builds=(
        "ElementalWarrior-wine-11.12",
        "ElementalWarrior-wine-11.16",
        "ElementalWarrior-wine-11.16.stock-2026-09-08",
    ), link_to=None)
    assert maintenance.fix_wine_symlink(p) == "ElementalWarrior-wine-11.16"


def test_fix_wine_symlink_accepts_a_real_directory(tmp_path):
    """The stock installer unpacks Wine straight into ElementalWarriorWine/.
    Treating that as a stale link meant unlink() on a directory."""
    p = make_prefix(tmp_path, builds=("ElementalWarriorWine", "wine-11.16"), link_to=None)
    assert maintenance.fix_wine_symlink(p) == "ElementalWarriorWine"
    assert (p / "ElementalWarriorWine" / "bin" / "wine").is_file()   # not unlinked


def test_repoint_handles_a_source_named_through_a_symlink(tmp_path):
    """This machine has ~/work -> /mnt/work, so a link can be stored with a
    spelling that never matches the resolved source as plain text. Missing it
    leaves the clone able to write back into the original."""
    real = tmp_path / "real"; real.mkdir()
    (tmp_path / "link").symlink_to(real)                 # an aliased path to the same place
    src = maintenance.Path(str(tmp_path / "link" / "prefix"))
    p = make_prefix(real)                                 # real/prefix
    assert src.exists()
    # a link inside the prefix written through the aliased spelling
    os.symlink(str(src / "wine-a"), p / "aliased-link")
    dst = tmp_path / "copy"
    plan = maintenance.plan_clone(src, dst)
    maintenance.clone(plan)
    target = os.readlink(dst / "aliased-link")
    assert not os.path.realpath(target).startswith(str(real / "prefix")), target
    assert os.path.realpath(target).startswith(str(dst.resolve()))


def test_clean_empties_a_temp_directory_rather_than_removing_it(tmp_path):
    """Wine and the installer write into %TEMP% without creating it, and these
    rows are ticked by default, so removing the directory broke the prefix."""
    p = make_prefix(tmp_path)
    tmp = p / "drive_c" / "windows" / "temp"
    tmp.mkdir(parents=True)
    (tmp / "junk.dat").write_bytes(b"x" * 1024)
    (tmp / "sub").mkdir(); (tmp / "sub" / "more.dat").write_bytes(b"x" * 512)
    item = maintenance.Item(path=tmp, kind="temp", size=1536, reason="temp")
    freed, problems = maintenance.clean(p, [item])
    assert tmp.is_dir()                       # still there
    assert not any(tmp.iterdir())             # and empty
    assert freed == 1536 and not problems


def test_launcher_scan_ignores_files_too_big_to_be_a_launcher(tmp_path):
    """It read every regular file in ~/bin whole -- 107MB here, 3.98s a call,
    once per selected item on the GUI thread."""
    p = make_prefix(tmp_path)
    d = tmp_path / "bin"; d.mkdir()
    (d / "launcher").write_text(f"exec {p}/wine-b/bin/wine\n")
    big = d / "hugebinary"
    big.write_text(f"{p}/wine-a/bin/wine\n" + "#" * (maintenance.LAUNCHER_MAX_BYTES + 1))
    named = maintenance.builds_named_by_launchers(p, dirs=[str(d)])
    assert named == {"wine-b"}                # the big one was not read
