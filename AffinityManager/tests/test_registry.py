"""Tests for the parts that must not lose track of a prefix.

Run: python3 -m pytest tests -q   (or: python3 tests/test_registry.py)
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from affinity_manager import probe, registry


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ[registry.ENV_BASE_DIR] = self.tmp.name
        self.reg = registry.Registry()

    def tearDown(self):
        os.environ.pop(registry.ENV_BASE_DIR, None)
        self.tmp.cleanup()

    def test_base_dir_follows_the_environment(self):
        self.assertEqual(registry.base_dir(), Path(self.tmp.name))

    def test_add_and_reload(self):
        self.reg.add("Affinity 3.3", Path(self.tmp.name) / "p33")
        self.assertIsNotNone(registry.Registry().by_name("affinity 3.3"))

    def test_duplicate_name_is_refused(self):
        self.reg.add("live", Path(self.tmp.name) / "a")
        with self.assertRaises(registry.DuplicateName):
            self.reg.add("LIVE", Path(self.tmp.name) / "b")

    def test_same_path_twice_is_refused(self):
        # Two names for one directory would make "stop managing" ambiguous and
        # let two rows launch the same prefix, which kills the running session.
        self.reg.add("one", Path(self.tmp.name) / "shared")
        with self.assertRaises(registry.PathInUse):
            self.reg.add("two", Path(self.tmp.name) / "shared")

    def test_bad_names_are_refused(self):
        for bad in ("", "  ", "../escape", "has/slash", "-leading", "x" * 65):
            with self.assertRaises(registry.InvalidName, msg=bad):
                self.reg.add(bad, Path(self.tmp.name) / "x")

    def test_forget_leaves_the_directory_alone(self):
        path = Path(self.tmp.name) / "keepme"
        path.mkdir()
        (path / "marker").write_text("still here")
        self.reg.add("gone", path)
        self.reg.forget("gone")
        self.assertEqual([], registry.Registry().entries)
        self.assertTrue((path / "marker").is_file())

    def test_corrupt_registry_does_not_raise(self):
        registry.registry_path().parent.mkdir(parents=True, exist_ok=True)
        registry.registry_path().write_text("{not json")
        self.assertEqual([], registry.Registry().entries)

    def test_slug_keeps_distinct_names_distinct(self):
        self.assertNotEqual(registry.slug("Affinity 3.3"), registry.slug("Affinity33"))


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.prefix = Path(self.tmp.name) / "prefix"
        (self.prefix / "drive_c").mkdir(parents=True)
        (self.prefix / "dosdevices").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_recognises_a_prefix(self):
        self.assertTrue(probe.is_prefix(self.prefix))
        self.assertFalse(probe.is_prefix(Path(self.tmp.name)))

    def test_describe_handles_a_missing_directory(self):
        info = probe.describe(Path(self.tmp.name) / "nope")
        self.assertFalse(info["exists"])
        self.assertFalse(info["running"])

    def test_wine_builds_need_a_wine_binary(self):
        (self.prefix / "NotWine").mkdir()
        self.assertEqual([], probe.wine_builds(self.prefix))
        binary = self.prefix / "ElementalWarrior-wine-11.16" / "bin"
        binary.mkdir(parents=True)
        (binary / "wine").write_text("#!/bin/sh\n")
        self.assertEqual(["ElementalWarrior-wine-11.16"], probe.wine_builds(self.prefix))

    def test_human_size(self):
        self.assertEqual("512B", probe.human_size(512))
        self.assertEqual("1.0K", probe.human_size(1024))
        self.assertEqual("1.5G", probe.human_size(int(1.5 * 1024**3)))



class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ[registry.ENV_BASE_DIR] = self.tmp.name
        self.reg = registry.Registry()

    def tearDown(self):
        os.environ.pop(registry.ENV_BASE_DIR, None)
        self.tmp.cleanup()

    def test_metadata_lives_in_the_manager_subdir(self):
        self.assertEqual(registry.manager_dir(), Path(self.tmp.name) / "Manager")
        self.assertEqual(
            registry.registry_path(), Path(self.tmp.name) / "Manager" / "prefixes.json"
        )

    def test_prefix_dirs_sit_directly_under_the_base(self):
        self.assertEqual(
            registry.path_for("Affinity 3.3"),
            Path(self.tmp.name) / "Affinity_3.3",
        )

    def test_spaces_become_underscores_without_collapsing_names(self):
        self.assertEqual(registry.dir_name("My Test  Build"), "My_Test_Build")
        self.assertNotEqual(registry.dir_name("Affinity 33"), registry.dir_name("Affinity33"))

    def test_suggested_names_are_dated_and_numbered_in_order(self):
        import datetime

        day = datetime.datetime(2026, 9, 15)
        first = self.reg.suggest_name(when=day)
        self.assertEqual("AffinityLinux 2026-09-15 01", first)
        self.reg.add(first, registry.path_for(first))
        self.assertEqual("AffinityLinux 2026-09-15 02", self.reg.suggest_name(when=day))

    def test_suggestion_skips_a_directory_nobody_registered(self):
        import datetime

        day = datetime.datetime(2026, 9, 15)
        (Path(self.tmp.name) / "AffinityLinux_2026-09-15_01").mkdir(parents=True)
        self.assertEqual("AffinityLinux 2026-09-15 02", self.reg.suggest_name(when=day))


class CollisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ[registry.ENV_BASE_DIR] = self.tmp.name

    def tearDown(self):
        os.environ.pop(registry.ENV_BASE_DIR, None)
        self.tmp.cleanup()

    def test_rename_aside_moves_and_never_deletes(self):
        path = Path(self.tmp.name) / "Busy"
        path.mkdir()
        (path / "payload").write_text("irreplaceable")
        moved = registry.rename_aside(path)
        self.assertFalse(path.exists())
        self.assertTrue(moved.exists())
        self.assertEqual("irreplaceable", (moved / "payload").read_text())
        self.assertTrue(moved.name.startswith("Busy.old-"))

    def test_aside_path_does_not_reuse_an_existing_one(self):
        path = Path(self.tmp.name) / "Busy"
        path.mkdir()
        first = registry.rename_aside(path)
        path.mkdir()
        second = registry.aside_path(path)
        self.assertNotEqual(first, second)

    def test_describe_collision_reports_an_empty_directory(self):
        path = Path(self.tmp.name) / "Empty"
        path.mkdir()
        info = registry.describe_collision(path)
        self.assertTrue(info["exists"])
        self.assertTrue(info["empty"])


class ProtectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ[registry.ENV_BASE_DIR] = self.tmp.name
        self.reg = registry.Registry()
        self.reg.add("keepme", Path(self.tmp.name) / "keepme")

    def tearDown(self):
        os.environ.pop(registry.ENV_BASE_DIR, None)
        self.tmp.cleanup()

    def test_new_prefixes_are_not_protected(self):
        self.assertFalse(registry.is_protected(self.reg.by_name("keepme")))

    def test_protection_round_trips_through_disk(self):
        self.reg.set_protected("keepme", True)
        self.assertTrue(registry.is_protected(registry.Registry().by_name("keepme")))
        self.reg.set_protected("keepme", False)
        self.assertFalse(registry.is_protected(registry.Registry().by_name("keepme")))


class DesktopEntryTests(unittest.TestCase):
    def setUp(self):
        from affinity_manager import commands, desktopentry

        self.commands, self.desktopentry = commands, desktopentry
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["XDG_DATA_HOME"] = self.tmp.name
        self.command = commands.Command(
            group="Affinity (test)",
            label="Affinity, with plugins",
            detail="detail",
            argv=["/opt/wine bin/wine", "/prefix/Program Files/App.exe"],
            env={"WINEPREFIX": "/prefix with space"},
        )

    def tearDown(self):
        os.environ.pop("XDG_DATA_HOME", None)
        self.tmp.cleanup()

    def test_exec_line_quotes_paths_with_spaces(self):
        line = self.desktopentry.exec_line(self.command)
        self.assertIn("'/prefix with space'", line)
        self.assertIn("'/opt/wine bin/wine'", line)
        self.assertTrue(line.startswith("env "))

    def test_write_read_remove(self):
        de, name = self.desktopentry, "Test Prefix"
        self.assertFalse(de.exists(name, self.command))
        path = de.write(name, self.command, name="Custom Label")
        self.assertTrue(path.is_file())
        self.assertTrue(de.exists(name, self.command))
        self.assertEqual("Custom Label", de.read_name(name, self.command))
        self.assertEqual([path], de.entries_for(name))
        self.assertTrue(de.remove(name, self.command))
        self.assertFalse(de.exists(name, self.command))

    def test_refuses_to_overwrite_someone_elses_entry(self):
        de, name = self.desktopentry, "Test Prefix"
        path = de.entry_path(name, self.command.label)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[Desktop Entry]\nName=Somebody else's\n")
        with self.assertRaises(FileExistsError):
            de.write(name, self.command)
        self.assertIn("Somebody else", path.read_text())


class CommandTests(unittest.TestCase):
    def test_shell_line_is_what_would_run(self):
        from affinity_manager import commands

        c = commands.Command("g", "l", "d", ["/bin/echo", "a b"], {"X": "y z"})
        self.assertEqual("X='y z' /bin/echo 'a b'", c.shell)



class InstallerSourceTests(unittest.TestCase):
    """Which installer builds new prefixes, and whether it can be trusted to."""

    def setUp(self):
        from affinity_manager import installer

        self.installer = installer
        self.tmp = tempfile.TemporaryDirectory()
        os.environ[registry.ENV_BASE_DIR] = self.tmp.name
        os.environ.pop(installer.ENV_SCRIPT, None)

    def tearDown(self):
        os.environ.pop(registry.ENV_BASE_DIR, None)
        os.environ.pop(self.installer.ENV_SCRIPT, None)
        self.tmp.cleanup()

    def _write(self, text) -> Path:
        script = Path(self.tmp.name) / "AffinityLinuxInstaller.py"
        script.write_text(text)
        return script

    def test_an_installer_without_the_variable_is_refused(self):
        # The failure this guards against is not an error message: it is an
        # install into ~/.AffinityLinux, over the prefix being protected.
        script = self._write("print('old installer')\n")
        self.assertFalse(self.installer.supports_install_dir(script))
        with self.assertRaises(self.installer.InstallerTooOld):
            self.installer.check_installer(script)

    def test_an_installer_with_the_variable_is_accepted(self):
        script = self._write(f"X = '{self.installer.ENV_INSTALL_DIR}'\n")
        self.assertEqual(script, self.installer.check_installer(script))

    def test_describe_reports_unusable_scripts_plainly(self):
        script = self._write("print('old installer')\n")
        info = self.installer.describe(script)
        self.assertTrue(info["found"])
        self.assertFalse(info["supports_install_dir"])
        self.assertIn("cannot be pointed at a prefix", self.installer.summary(info))

    def test_the_configured_script_wins_over_discovery(self):
        from affinity_manager import settings

        script = self._write(f"X = '{self.installer.ENV_INSTALL_DIR}'\n")
        settings.set("installer_script", str(script))
        self.assertEqual(script, self.installer.find_installer())

    def test_the_environment_wins_over_the_setting(self):
        from affinity_manager import settings

        configured = self._write(f"X = '{self.installer.ENV_INSTALL_DIR}'\n")
        settings.set("installer_script", str(configured))
        other = Path(self.tmp.name) / "other.py"
        other.write_text(f"X = '{self.installer.ENV_INSTALL_DIR}'\n")
        os.environ[self.installer.ENV_SCRIPT] = str(other)
        self.assertEqual(other, self.installer.find_installer())

    def test_launch_passes_the_prefix_and_the_pin(self):
        script = self._write(f"X = '{self.installer.ENV_INSTALL_DIR}'\n")
        captured = {}

        class FakePopen:
            def __init__(self, argv, env=None):
                captured["argv"] = argv
                captured["env"] = env

        real = self.installer.subprocess.Popen
        self.installer.subprocess.Popen = FakePopen
        try:
            self.installer.launch("/prefixes/Test", installer_file=__file__, script=script)
        finally:
            self.installer.subprocess.Popen = real
        self.assertEqual("/prefixes/Test", captured["env"][self.installer.ENV_INSTALL_DIR])
        self.assertEqual(__file__, captured["env"][self.installer.ENV_INSTALLER_FILE])
        self.assertIn(str(script), captured["argv"])

    def test_launch_clears_a_stale_pin(self):
        script = self._write(f"X = '{self.installer.ENV_INSTALL_DIR}'\n")
        captured = {}

        class FakePopen:
            def __init__(self, argv, env=None):
                captured["env"] = env

        real = self.installer.subprocess.Popen
        self.installer.subprocess.Popen = FakePopen
        try:
            self.installer.launch(
                "/prefixes/Test",
                script=script,
                env={self.installer.ENV_INSTALLER_FILE: "/left/over.exe"},
            )
        finally:
            self.installer.subprocess.Popen = real
        self.assertNotIn(self.installer.ENV_INSTALLER_FILE, captured["env"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


# ----------------------------------------------------------------------------
# The prefix list is the only record that a prefix is managed at all. Losing it
# is the worst thing this module can do, so both ways of losing it are pinned.


def test_a_corrupt_registry_falls_back_to_the_previous_copy(tmp_path):
    path = tmp_path / "prefixes.json"
    r = registry.Registry(path)
    r.entries = [{"name": "Working", "path": "/home/x/.AffinityLinux"}]
    r.save()
    r.entries = [{"name": "Working", "path": "/home/x/.AffinityLinux"},
                 {"name": "Test", "path": "/home/x/.Test"}]
    r.save()                                     # now there is a .bak

    path.write_text("{ this is not json")
    again = registry.Registry(path)
    assert [e["name"] for e in again.entries] == ["Working"]
    assert again.recovered_from_backup


def test_a_corrupt_registry_with_no_backup_still_starts(tmp_path):
    """Empty is the right answer when there is genuinely nothing to recover --
    it must not raise and take the application down."""
    path = tmp_path / "prefixes.json"
    path.write_text("{ nope")
    r = registry.Registry(path)
    assert r.entries == [] and not r.recovered_from_backup


def test_save_keeps_exactly_one_previous_copy(tmp_path):
    path = tmp_path / "prefixes.json"
    r = registry.Registry(path)
    for n in range(3):
        r.entries = [{"name": f"P{n}", "path": f"/p{n}"}]
        r.save()
    backup = json.loads(path.with_suffix(".json.bak").read_text())
    assert [e["name"] for e in backup["prefixes"]] == ["P1"]     # the one before last
    assert [e["name"] for e in r.entries] == ["P2"]


def test_no_temporary_file_is_left_behind(tmp_path):
    path = tmp_path / "prefixes.json"
    r = registry.Registry(path)
    r.entries = [{"name": "A", "path": "/a"}]
    r.save()
    assert not path.with_suffix(".json.tmp").exists()


# ----------------------------------------------------------------------------
# Operation state. Written before the work, cleared after, so a manager that
# dies in the middle leaves a row that says so.


def _reg(tmp_path, name="Working"):
    r = registry.Registry(tmp_path / "prefixes.json")
    r.entries = [{"name": name, "path": str(tmp_path / name)}]
    r.save()
    return r


def test_working_is_recorded_before_the_work(tmp_path):
    r = _reg(tmp_path)
    r.set_working("Working", "Install Affinity", log_offset=4096)
    again = registry.Registry(tmp_path / "prefixes.json")
    row = again.by_name("Working")
    assert row["state"] == "working"
    assert row["operation"] == "Install Affinity"
    assert row["log_offset"] == 4096 and row["operation_started"]


def test_clearing_forgets_the_operation_happened(tmp_path):
    r = _reg(tmp_path)
    r.set_working("Working", "Install Affinity", log_offset=10)
    r.clear_state("Working")
    row = registry.Registry(tmp_path / "prefixes.json").by_name("Working")
    assert all(k not in row for k in
               ("state", "operation", "operation_started", "log_offset"))


def test_recovery_marks_an_interrupted_operation_and_keeps_what_describes_it(tmp_path):
    """The operation name and the log offset are what the message about it is
    made of, so they survive the transition."""
    r = _reg(tmp_path)
    r.set_working("Working", "One-Click Full Setup", log_offset=8192)

    restarted = registry.Registry(tmp_path / "prefixes.json")
    changed = restarted.recover()
    assert [e["name"] for e in changed] == ["Working"]
    row = restarted.by_name("Working")
    assert row["state"] == "incomplete"
    assert row["operation"] == "One-Click Full Setup" and row["log_offset"] == 8192

    # and it persisted, not just changed in memory
    assert registry.Registry(tmp_path / "prefixes.json").by_name(
        "Working")["state"] == "incomplete"


def test_recovery_is_quiet_when_there_is_nothing_to_recover(tmp_path):
    r = _reg(tmp_path)
    assert r.recover() == []


def test_state_survives_a_corrupt_registry_via_the_backup(tmp_path):
    """The two hardenings have to work together: an interrupted operation is
    only useful if the row recording it is still there."""
    path = tmp_path / "prefixes.json"
    r = _reg(tmp_path)
    r.set_working("Working", "Install Affinity")     # writes, and makes a .bak
    r.clear_state("Working")                         # .bak now holds the working row
    path.write_text("{ corrupt")
    recovered = registry.Registry(path)
    assert recovered.recovered_from_backup
    assert recovered.by_name("Working")["state"] == "working"
    assert recovered.recover()[0]["state"] == "incomplete"
