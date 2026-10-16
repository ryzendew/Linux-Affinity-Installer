"""Wine-free unit tests for AffinityLinuxInstaller.py.

Run with::

    python3 -m pytest tests/ -q

Nothing here starts Qt or Wine. The GUI class's pure helpers are bound onto a
small stand-in object, and every process-scoped test uses throw-away prefixes
under pytest's ``tmp_path`` — plus a unique prefix marker for the startup sweep
— so a live install is never touched.
"""

import importlib.util
import inspect
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

# Importing the installer module tries to pip-install PyQt6 when it is missing,
# which is not a side effect a test run should ever trigger.
pytest.importorskip(
    "PyQt6", reason="importing the installer would try to pip-install PyQt6"
)

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "AffinityScripts" / "AffinityLinuxInstaller.py"
)

# Helpers that only need `directory`, `cancel_event`, `_process_lock`,
# `_active_processes`, `log` — i.e. no Qt, no Wine.
HELPER_METHODS = (
    "build_winetricks_command",
    "_prefix_wine_pids",
    "stop_prefix_wine_processes",
    "run_command_streaming",
    "run_command",
    "get_stall_timeout",
    "_pump_child_output",
    "get_wine_dir",
    "get_wine_path",
    "_register_process",
    "_unregister_process",
    "_terminate_process",
    "has_dotnet48_runtime",
    "verify_required_wine_runtimes",
    "_release_webview2_wait",
)


@pytest.fixture(scope="session")
def ali():
    """The installer module, loaded without running the GUI."""
    spec = importlib.util.spec_from_file_location(
        "affinity_linux_installer", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def harness(ali, tmp_path):
    """A stand-in object carrying the installer's pure helpers."""

    class StandIn:
        pass

    for name in HELPER_METHODS:
        # getattr_static keeps @staticmethod wrappers. Plain getattr unwraps
        # them, so _pump_child_output became an instance method here, every
        # call passed one argument too many, the reader thread died before
        # posting its EOF sentinel, and the streaming tests hung for the full
        # stall timeout (1800s). The real class was never affected.
        setattr(StandIn, name, inspect.getattr_static(ali.AffinityInstallerGUI, name))

    StandIn.WINE_SERVICE_EXES = ali.AffinityInstallerGUI.WINE_SERVICE_EXES
    obj = StandIn()
    obj.directory = str(tmp_path)
    obj.cancel_event = threading.Event()
    obj._process_lock = threading.Lock()
    obj._active_processes = set()
    obj._stalled_components = set()
    obj._log_queue = []
    obj._log_queue_lock = threading.Lock()
    obj.log_lines = []

    def log(message, level="info"):
        obj.log_lines.append((level, str(message)))

    obj.log = log
    return obj


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def spawn_with_prefix(prefix, seconds=60, executable="sleep"):
    """Start `sleep` carrying a WINEPREFIX, in its own session.

    Own session matters: `_prefix_wine_pids()` deliberately skips our own
    process group, so a child sharing pytest's group would be invisible."""
    env = {**os.environ, "WINEPREFIX": str(prefix)}
    return subprocess.Popen(
        [executable, str(seconds)], env=env, start_new_session=True
    )


def wait_dead(popen, timeout=10):
    """Wait for a child we spawned (reaps it, so /proc/pid disappears)."""
    try:
        popen.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        return False


def kill_quietly(*popens):
    for popen in popens:
        if popen is None:
            continue
        try:
            popen.kill()
        except Exception:
            pass
        try:
            popen.wait(timeout=5)
        except Exception:
            pass


def copy_as(source, target_dir, name):
    """Copy an ELF binary under a different process name."""
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / name
    shutil.copy(os.path.realpath(source), destination)
    destination.chmod(0o755)
    return destination


# --------------------------------------------------------------------------- #
# winetricks command construction
# --------------------------------------------------------------------------- #


def test_dotnet_verbs_omit_force(harness):
    """--force would re-run the whole .NET chain on every attempt."""
    for verb in ("dotnet35sp1", "dotnet48", "dotnet40", "dotnet45"):
        command = harness.build_winetricks_command(verb)
        assert "--force" not in command, command
        assert command[-1] == verb
        assert command[0] == "winetricks"
        assert "--unattended" in command


def test_other_verbs_keep_force(harness):
    assert "--force" in harness.build_winetricks_command("corefonts")
    assert "--force" in harness.build_winetricks_command("renderer=vulkan")


def test_verbose_flag_is_optional(harness):
    assert "--verbose" in harness.build_winetricks_command("dxvk")
    assert "--verbose" not in harness.build_winetricks_command("dxvk", verbose=False)


def test_component_list_is_single_source(ali):
    verbs = [verb for verb, _ in ali.WINETRICKS_COMPONENTS]
    assert verbs[0] == "dotnet48", "dotnet must come first"
    assert "dotnet35sp1" not in verbs, "Affinity 3 needs 4.8, and 3.5 doubled its install time"
    assert len(verbs) == len(set(verbs)), "duplicate verbs would install twice"
    assert "renderer=vulkan" in verbs
    for verb, description in ali.WINETRICKS_COMPONENTS:
        assert verb and description


# --------------------------------------------------------------------------- #
# stall timeout
# --------------------------------------------------------------------------- #


def test_stall_timeout_default_and_override(harness, monkeypatch):
    monkeypatch.delenv("AFFINITY_STALL_TIMEOUT", raising=False)
    assert harness.get_stall_timeout() == 1800

    monkeypatch.setenv("AFFINITY_STALL_TIMEOUT", "42")
    assert harness.get_stall_timeout() == 42

    monkeypatch.setenv("AFFINITY_STALL_TIMEOUT", "not-a-number")
    assert harness.get_stall_timeout() == 1800

    monkeypatch.setenv("AFFINITY_STALL_TIMEOUT", "0")
    assert harness.get_stall_timeout() == 1800


# --------------------------------------------------------------------------- #
# component status
# --------------------------------------------------------------------------- #


def _status_harness(ali, tmp_path):
    class StandIn:
        directory = str(tmp_path)
    for name in ("_check_winetricks_component", "_winetricks_logged_verbs"):
        setattr(StandIn, name, inspect.getattr_static(ali.AffinityInstallerGUI, name))
    return StandIn()


def test_tahoma_reads_installed_when_its_font_is_there(ali, tmp_path):
    h = _status_harness(ali, tmp_path)
    fonts = tmp_path / "drive_c" / "windows" / "Fonts"
    fonts.mkdir(parents=True)
    assert not h._check_winetricks_component("tahoma", None, {})
    (fonts / "tahoma.ttf").write_bytes(b"")
    assert h._check_winetricks_component("tahoma", None, {})
    # and Tahoma alone is not the core fonts
    assert not h._check_winetricks_component("corefonts", None, {})


def test_a_component_without_a_check_goes_by_winetricks_log(ali, tmp_path):
    h = _status_harness(ali, tmp_path)
    assert not h._check_winetricks_component("somefont", None, {})
    (tmp_path / "winetricks.log").write_text("remove_mono\nsomefont\n")
    assert h._check_winetricks_component("somefont", None, {})


# --------------------------------------------------------------------------- #
# caching the other Wine versions
# --------------------------------------------------------------------------- #


def test_other_wine_versions_are_cached_only_on_request(ali, monkeypatch):
    monkeypatch.delenv("AFFINITY_CACHE_ALL_WINE", raising=False)
    assert not ali.cache_all_wine_versions()
    monkeypatch.setenv("AFFINITY_CACHE_ALL_WINE", "0")
    assert not ali.cache_all_wine_versions()
    monkeypatch.setenv("AFFINITY_CACHE_ALL_WINE", "1")
    assert ali.cache_all_wine_versions()


# --------------------------------------------------------------------------- #
# release host override
# --------------------------------------------------------------------------- #


def test_release_downloads_default_to_github(ali, monkeypatch):
    monkeypatch.delenv("AFFINITY_RELEASES_FROM", raising=False)
    config = ali.AffinityInstallerGUI._get_wine_version_config(None, "11.19")
    assert config["wine_url"].startswith("https://github.com/jfacemyer/Affinity-Wine-Builder/")
    assert config["wine_sha256"] == ali.WINE_11_19_SHA256
    assert ali.apl_release_api_url() == (
        f"https://api.github.com/repos/{ali.APL_RELEASE_REPO}/releases/tags/{ali.APL_RELEASE_TAG}"
    )


def test_release_downloads_follow_the_override(ali, monkeypatch):
    monkeypatch.setenv("AFFINITY_RELEASES_FROM", "https://git.example.org/someone/")
    config = ali.AffinityInstallerGUI._get_wine_version_config(None, "11.19")
    assert config["wine_url"] == (
        "https://git.example.org/someone/Affinity-Wine-Builder/releases/download/11.19-r10/"
        "ElementalWarrior-wine-11.19.tar.xz"
    )
    # The pin is the same: only the identical build installs from either host.
    assert config["wine_sha256"] == ali.WINE_11_19_SHA256
    # 11.18 is the fork's build too, so it follows the override as well.
    other = ali.AffinityInstallerGUI._get_wine_version_config(None, "11.18")
    assert other["wine_url"].startswith("https://git.example.org/someone/Affinity-Wine-Builder/")
    assert other["wine_sha256"] == ali.WINE_11_18_SHA256
    assert ali.apl_release_api_url() == (
        "https://git.example.org/api/v1/repos/someone/AffinityPluginLoader/releases/tags/"
        + ali.APL_RELEASE_TAG
    )


# --------------------------------------------------------------------------- #
# run_command_streaming
# --------------------------------------------------------------------------- #


def test_streaming_stall_watchdog_kills_the_child(harness, tmp_path):
    """A silent child must be stopped, reported, and leave no orphan."""
    pid_file = tmp_path / "child.pid"
    command = ["bash", "-c", f"echo $$ > '{pid_file}'; exec sleep 300"]

    started = time.monotonic()
    ok = harness.run_command_streaming(command, stall_timeout=2)
    elapsed = time.monotonic() - started

    assert ok is False
    assert harness._last_command_stalled is True
    assert elapsed < 20, f"stall watchdog took {elapsed:.1f}s"

    child_pid = int(pid_file.read_text().strip())
    deadline = time.monotonic() + 5
    while Path(f"/proc/{child_pid}").exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not Path(f"/proc/{child_pid}").exists(), "child survived the watchdog"

    assert any("stuck" in message for _, message in harness.log_lines)


def test_streaming_honours_cancel_while_silent(harness):
    harness.cancel_event.set()
    started = time.monotonic()
    ok = harness.run_command_streaming(["sleep", "300"], stall_timeout=300)
    elapsed = time.monotonic() - started

    assert ok is False
    assert elapsed < 10, f"cancel took {elapsed:.1f}s"


def test_streaming_tolerates_undecodable_output(harness):
    """Wine used to be able to kill a run with UnicodeDecodeError."""
    ok = harness.run_command_streaming(
        ["bash", "-c", "printf '\\377\\376 bad bytes\\n'; exit 0"]
    )
    assert ok is True
    assert "bad bytes" in harness._last_stream_output_text


def test_streaming_reports_failure_and_stores_output(harness):
    ok = harness.run_command_streaming(["bash", "-c", "printf 'hello\\n'; exit 3"])
    assert ok is False
    assert "hello" in harness._last_stream_output_text

    ok = harness.run_command_streaming(["bash", "-c", "printf 'hello\\n'; exit 0"])
    assert ok is True


def test_streaming_does_not_flag_normal_failure_as_stall(harness):
    harness.run_command_streaming(["bash", "-c", "exit 1"])
    assert harness._last_command_stalled is False


# --------------------------------------------------------------------------- #
# run_command
# --------------------------------------------------------------------------- #


def test_run_command_success(harness):
    ok, out, err = harness.run_command(["bash", "-c", "echo hi"], check=False)
    assert ok is True
    assert out.strip() == "hi"


def test_run_command_deadline(harness):
    """No non-streaming command may block the GUI forever."""
    started = time.monotonic()
    ok, out, err = harness.run_command(["sleep", "300"], check=False, timeout=2)
    elapsed = time.monotonic() - started

    assert ok is False
    assert "Timed out" in err
    assert elapsed < 20, f"deadline took {elapsed:.1f}s"

    remaining = subprocess.run(["pgrep", "-f", "^sleep 300$"], capture_output=True)
    assert remaining.returncode != 0, "timed-out child was left running"


def test_run_command_cancel(harness):
    harness.cancel_event.set()
    ok, out, err = harness.run_command(["sleep", "300"], check=False, timeout=300)
    assert ok is False
    assert err == "Cancelled"


def test_run_command_tolerates_undecodable_output(harness):
    ok, out, err = harness.run_command(
        ["bash", "-c", "printf '\\377\\376'; exit 0"], check=False
    )
    assert ok is True


# --------------------------------------------------------------------------- #
# prefix process scoping
# --------------------------------------------------------------------------- #


def test_prefix_pids_only_our_prefix(harness, tmp_path):
    ours = spawn_with_prefix(tmp_path)
    foreign = spawn_with_prefix(tmp_path.parent / "someone-elses-prefix")
    try:
        pids = harness._prefix_wine_pids()
        assert ours.pid in pids
        assert foreign.pid not in pids
        assert os.getpid() not in pids, "never list ourselves"
    finally:
        kill_quietly(ours, foreign)


def test_stop_prefix_wine_processes_spares_other_prefixes(harness, tmp_path):
    ours = spawn_with_prefix(tmp_path)
    foreign = spawn_with_prefix(tmp_path.parent / "someone-elses-prefix")
    try:
        assert harness.stop_prefix_wine_processes({}, reason="test") is True
        assert wait_dead(ours), "our prefix's process should be gone"
        assert foreign.poll() is None, "a foreign prefix must not be touched"
    finally:
        kill_quietly(ours, foreign)


def test_stop_prefix_wine_processes_is_a_noop_when_idle(harness):
    assert harness.stop_prefix_wine_processes({}) is True


def test_stop_prefix_wine_processes_respects_cancel_unless_forced(harness, tmp_path):
    process = spawn_with_prefix(tmp_path)
    try:
        harness.cancel_event.set()
        assert harness.stop_prefix_wine_processes({}) is False
        assert process.poll() is None, "cancelled call must not kill anything"
        harness.cancel_event.clear()
        assert (
            harness.stop_prefix_wine_processes({}, wait_seconds=5, force=True) is True
        )
        assert wait_dead(process)
    finally:
        kill_quietly(process)


def test_startup_sweep_is_scoped_to_owned_prefixes(ali, tmp_path):
    """The old `pkill -9 -f winetricks` matched unrelated command lines.

    Scoped to the exact prefix being installed into, not to a name suffix:
    `.AffinityLinux` is also a prefix of `.AffinityLinuxManager/...`, so a
    suffix or substring match reaches every managed prefix and the working
    one, and killing a wineserver ends the Affinity session it serves."""
    marker = f".AffinityLinux-test-{os.getpid()}"
    owned_prefix = tmp_path / marker
    foreign_prefix = tmp_path / "steam-compat"
    owned_prefix.mkdir()
    foreign_prefix.mkdir()

    bin_dir = tmp_path / "bin"
    fake_wineserver = copy_as("/bin/sleep", bin_dir, "wineserver")
    fake_sleep = copy_as("/bin/sleep", bin_dir, "sleep")

    target = spawn_with_prefix(owned_prefix, executable=str(fake_wineserver))
    # Right prefix, wrong name: must survive.
    decoy = spawn_with_prefix(owned_prefix, executable=str(fake_sleep))
    # Right name, wrong prefix: must survive.
    foreign = spawn_with_prefix(foreign_prefix, executable=str(fake_wineserver))
    try:
        ali.kill_stalled_wine_processes(prefix=str(owned_prefix))

        assert wait_dead(target), "stale wineserver of our prefix must be killed"
        assert decoy.poll() is None, "unrelated process in our prefix must survive"
        assert foreign.poll() is None, "another prefix's wineserver must survive"
    finally:
        kill_quietly(target, decoy, foreign)


# --------------------------------------------------------------------------- #
# .NET detection
# --------------------------------------------------------------------------- #


NET48_KEY = (
    "[Software\\\\Microsoft\\\\NET Framework Setup\\\\NDP\\\\v4\\\\Full]\n"
)


def test_has_dotnet48_runtime(harness, tmp_path):
    reg_file = tmp_path / "system.reg"
    assert harness.has_dotnet48_runtime() is False, "no system.reg yet"

    reg_file.write_text(
        NET48_KEY + '"Install"=dword:00000001\n' + '"Release"=dword:80e18\n'
    )
    assert harness.has_dotnet48_runtime() is True
    assert harness.verify_required_wine_runtimes() is True

    reg_file.write_text(NET48_KEY + '"Install"=dword:00000000\n')
    assert harness.has_dotnet48_runtime() is False, "Install=0 means not installed"


def test_has_dotnet48_runtime_ignores_other_keys(harness, tmp_path):
    reg_file = tmp_path / "system.reg"
    reg_file.write_text(
        '[Software\\\\Microsoft\\\\NET Framework Setup\\\\NDP\\\\v2.0\\\\50727]\n'
        '"Install"=dword:00000001\n'
    )
    assert harness.has_dotnet48_runtime() is False


# --------------------------------------------------------------------------- #
# native images (ngen)

def _ngen_harness(ali, harness, tmp_path, run_result):
    """precompile_affinity on the stand-in, with Wine, .NET and run_command stubbed."""
    for name in ("precompile_affinity", "prefix_windows_path", "affinity_v3_exe_path"):
        setattr(type(harness), name, inspect.getattr_static(ali.AffinityInstallerGUI, name))
    harness.calls = []
    harness.has_dotnet48_runtime = lambda: True
    harness.update_progress_text = lambda text: None
    wine = tmp_path / "wine-dist" / "bin" / "wine"
    wine.parent.mkdir(parents=True)
    wine.write_text("")
    harness.get_wine_path = lambda binary="wine": wine

    def run_command(command, check=True, shell=False, capture=True, env=None, timeout=None):
        harness.calls.append((command, env, timeout))
        return run_result

    harness.run_command = run_command
    framework = tmp_path / "drive_c" / "windows" / "Microsoft.NET" / "Framework64" / "v4.0.30319"
    framework.mkdir(parents=True)
    (framework / "ngen.exe").write_text("")
    exe = tmp_path / "drive_c" / "Program Files" / "Affinity" / "Affinity" / "Affinity.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    return harness


def test_prefix_windows_path(ali, tmp_path):
    conv = ali.AffinityInstallerGUI.prefix_windows_path
    assert conv(tmp_path, tmp_path / "drive_c" / "Program Files" / "Affinity" / "A.exe") == \
        "C:\\Program Files\\Affinity\\A.exe"
    assert conv(tmp_path, "/mnt/work/x.afphoto") == "Z:\\mnt\\work\\x.afphoto"


def test_precompile_affinity_runs_ngen_install_with_a_deadline(ali, harness, tmp_path):
    h = _ngen_harness(ali, harness, tmp_path, (True, "", ""))
    assert h.precompile_affinity() is True
    (command, env, timeout), = h.calls
    assert command[1:] == [
        "C:\\windows\\Microsoft.NET\\Framework64\\v4.0.30319\\ngen.exe",
        "install",
        "C:\\Program Files\\Affinity\\Affinity\\Affinity.exe",
    ]
    assert env["WINEPREFIX"] == str(tmp_path)
    assert timeout and timeout <= 900


def test_precompile_affinity_failure_is_only_a_warning(ali, harness, tmp_path):
    h = _ngen_harness(ali, harness, tmp_path, (False, "", "ngen: something broke"))
    assert h.precompile_affinity() is False
    assert not any(level == "error" for level, _ in h.log_lines)
    assert any("without native images" in message for _, message in h.log_lines)


def test_precompile_affinity_skips_without_dotnet(ali, harness, tmp_path):
    h = _ngen_harness(ali, harness, tmp_path, (True, "", ""))
    h.has_dotnet48_runtime = lambda: False
    assert h.precompile_affinity() is False
    assert h.calls == []


def test_precompile_affinity_skips_when_affinity_is_missing(ali, harness, tmp_path):
    h = _ngen_harness(ali, harness, tmp_path, (True, "", ""))
    assert h.precompile_affinity(tmp_path / "drive_c" / "nope.exe") is False
    assert h.calls == []


def test_the_hook_patch_leaves_another_prefixs_entry_alone(ali, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    apps = tmp_path / ".local" / "share" / "applications"
    apps.mkdir(parents=True)
    entry = apps / "Affinity.desktop"
    body = "[Desktop Entry]\nExec=env WINEPREFIX=/other/prefix wine x.exe %F\n"
    entry.write_text(body)

    class StandIn:
        directory = str(tmp_path / "this-prefix")
        log = staticmethod(lambda *a, **k: None)
        manages_host_entries = staticmethod(lambda: True)
    for name in ("_patch_affinity_desktop_for_hook", "_entry_serves_this_prefix"):
        setattr(StandIn, name, inspect.getattr_static(ali.AffinityInstallerGUI, name))
    StandIn()._patch_affinity_desktop_for_hook()
    assert entry.read_text() == body


def test_kept_installers_newest_first_with_their_dates(ali, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    d = ali.kept_installers_dir()
    d.mkdir(parents=True)
    for v, t in (("3.2.3.4646", 1000000000), ("3.3.0.4850", 1100000000), ("3.10.0.1", 1200000000)):
        f = d / f"Affinity-x64-{v}.exe"
        f.write_bytes(b"x")
        os.utime(f, (t, t))
    (d / "Affinity-x64.exe").write_bytes(b"unversioned, not offered")
    kept = ali.kept_installers()
    assert [v for v, _, _ in kept] == ["3.10.0.1", "3.3.0.4850", "3.2.3.4646"]
    assert kept[1][2] == 1100000000


def test_update_wine_version_applies_the_new_install_fixes(ali, tmp_path):
    ran = []

    class StandIn:
        directory = str(tmp_path)
        log = staticmethod(lambda *a, **k: None)
        update_progress_text = staticmethod(lambda *a: None)
        check_cancelled = staticmethod(lambda: False)
        wine_resolves_winrt_namespaces = staticmethod(lambda: True)
        affinity_v3_exe_path = staticmethod(lambda: tmp_path)          # exists
        setup_winmetadata = staticmethod(lambda: ran.append("winmetadata-old"))
        install_combined_winmetadata = staticmethod(lambda: ran.append("winmetadata"))
        disable_opencl_if_needed = staticmethod(lambda v: ran.append(f"opencl {v}"))
        install_windowsruntime_facades = staticmethod(lambda: 1 / 0)  # fails
        install_file_manager_handler = staticmethod(lambda: ran.append("handler"))
        repair_fonts = staticmethod(lambda: ran.append("fonts"))
    StandIn._apply_wine_version_fixes = inspect.getattr_static(
        ali.AffinityInstallerGUI, "_apply_wine_version_fixes")
    StandIn()._apply_wine_version_fixes("11.19")
    # a failing step (the facades here) does not stop the rest
    assert ran == ["winmetadata", "opencl 11.19", "handler", "fonts"]


def _sudo_harness(ali, can_sudo, distro="arch"):
    shown, logged = [], []

    class StandIn:
        sudo_password_validated = False
        sudo_password = None
        _account_can_sudo = can_sudo
        log = staticmethod(lambda m, level="info": logged.append(m))
        show_message = staticmethod(lambda title, text, level="info": shown.append((title, text)))
        is_ubuntu_family_distro = staticmethod(lambda: False)
    StandIn.distro = distro
    for name in ("get_sudo_password", "account_can_sudo", "admin_install_command",
                 "explain_admin_needed", "_distro_install_commands",
                 "opencl_advice", "opencl_family"):
        setattr(StandIn, name, inspect.getattr_static(ali.AffinityInstallerGUI, name))
    return StandIn(), shown, logged


def test_an_account_without_sudo_is_not_asked_for_a_password(ali):
    h, shown, logged = _sudo_harness(ali, can_sudo=False)
    assert h.get_sudo_password() is None
    assert any("cannot use sudo" in m for m in logged)


def test_an_administrator_gets_the_exact_command(ali):
    h, shown, _ = _sudo_harness(ali, can_sudo=False, distro="arch")
    h.explain_admin_needed(["winetricks", "jq"])
    title, text = shown[0]
    assert "administrator" in title.lower()
    assert "winetricks, jq" in text
    assert "sudo pacman -S --needed --noconfirm wine winetricks" in text
    assert "home folder" in text


# --------------------------------------------------------------------------- #
# the stall watchdog with an activity probe
# --------------------------------------------------------------------------- #


def _probe_harness(harness, monkeypatch):
    harness.ACTIVITY_PROBE_INTERVAL = 0.3
    harness._log_prefix_snapshot = lambda: None
    return harness


def test_a_silent_child_that_is_working_is_not_stopped(harness, monkeypatch):
    h = _probe_harness(harness, monkeypatch)
    ticks = iter(range(1000))
    ok = h.run_command_streaming(["sh", "-c", "sleep 3; echo done"], stall_timeout=1,
                                 activity_probe=lambda: next(ticks))
    assert ok and not h._last_command_stalled


def test_a_silent_idle_child_is_still_stopped(harness, monkeypatch):
    h = _probe_harness(harness, monkeypatch)
    ok = h.run_command_streaming(["sleep", "30"], stall_timeout=1, activity_probe=lambda: 0)
    assert not ok and h._last_command_stalled


def test_the_hard_limit_stops_a_child_that_keeps_busy(harness, monkeypatch):
    h = _probe_harness(harness, monkeypatch)
    ticks = iter(range(1000))
    ok = h.run_command_streaming(["sleep", "30"], stall_timeout=1,
                                 activity_probe=lambda: next(ticks), hard_limit=2)
    assert not ok and h._last_command_stalled


# --------------------------------------------------------------------------- #
# OpenCL driver advice
# --------------------------------------------------------------------------- #


def test_gpu_vendors_and_opencl_drivers_are_read_from_the_system_files(ali, tmp_path):
    drm = tmp_path / "drm"
    for card, vendor in (("card0", "0x8086"), ("card1", "0x1002"), ("card0-DP-1", "0x10de")):
        (drm / card / "device").mkdir(parents=True)
        (drm / card / "device" / "vendor").write_text(vendor + "\n")
    assert ali.gpu_vendors(str(drm)) == ["intel", "amd"]      # connectors are not cards
    vendors = tmp_path / "vendors"
    vendors.mkdir()
    (vendors / "intel.icd").write_text("/nonexistent/libigdrcl.so\n")
    assert ali.opencl_drivers(str(vendors)) == []             # its library is missing
    (vendors / "mesa.icd").write_text("libRusticlOpenCL.so.1\n")
    assert ali.opencl_drivers(str(vendors)) == ["mesa"]


def test_the_advice_names_the_package_for_this_gpu_and_distro(ali, monkeypatch):
    h, _, _ = _sudo_harness(ali, can_sudo=True, distro="manjaro")
    monkeypatch.setattr(ali, "opencl_drivers", lambda *a: [])
    monkeypatch.setattr(ali, "gpu_vendors", lambda *a: ["intel"])
    assert "intel-compute-runtime" in h.opencl_advice()
    monkeypatch.setattr(ali, "opencl_drivers", lambda *a: ["intel"])
    assert h.opencl_advice() is None


@pytest.mark.parametrize("method", ["run_installation", "run_update"])
def test_installing_or_updating_affinity_compiles_native_images(ali, method):
    # The manager installs through run_installation; an update replaces the assemblies the
    # old images were made from. Both must compile, not only the "Add" path.
    source = inspect.getsource(getattr(ali.AffinityInstallerGUI, method))
    assert "self.precompile_affinity(" in source
    # The settings patch rewrites Serif.Affinity.dll without changing its identity, so
    # images compiled before it are stale yet still loaded: Affinity then crashed in
    # clr.dll at every start (fresh manager install, 2026-10-15). Compile after patching.
    assert source.index("self.patch_affinity_dll(") < source.index("self.precompile_affinity(")


@pytest.mark.parametrize("method", ["run_installation", "run_custom_installation"])
def test_installing_affinity_installs_the_webview2_runtime(ali, method):
    # Help is a WebView2 page. It came only from its own button, so installs made by
    # One-Click Full Setup and the manager had a blank Help (r8 fresh install, 2026-10-15).
    assert "self.ensure_webview2_runtime(" in inspect.getsource(getattr(ali.AffinityInstallerGUI, method))


def test_webview2_is_configured_not_reinstalled_when_present(ali, monkeypatch):
    gui = ali.AffinityInstallerGUI.__new__(ali.AffinityInstallerGUI)
    calls = []
    monkeypatch.setattr(gui, "check_webview2_installed", lambda: True, raising=False)
    monkeypatch.setattr(gui, "configure_webview2_runtime", lambda *a: calls.append("configure"), raising=False)
    monkeypatch.setattr(gui, "_install_webview2_runtime_thread", lambda: calls.append("install"), raising=False)
    monkeypatch.setattr(gui, "update_progress_text", lambda *a: None, raising=False)
    assert gui.ensure_webview2_runtime() is True
    assert calls == ["configure"]


def test_a_failed_webview2_install_does_not_fail_the_install(ali, monkeypatch):
    gui = ali.AffinityInstallerGUI.__new__(ali.AffinityInstallerGUI)
    logged = []
    monkeypatch.setattr(gui, "check_webview2_installed", lambda: False, raising=False)
    monkeypatch.setattr(gui, "_install_webview2_runtime_thread", lambda: False, raising=False)
    monkeypatch.setattr(gui, "update_progress_text", lambda *a: None, raising=False)
    monkeypatch.setattr(gui, "log", lambda msg, level="info": logged.append(level), raising=False)
    assert gui.ensure_webview2_runtime() is False
    assert "warning" in logged


def test_stop_prefix_wine_processes_does_not_wait_out_a_straggler(harness, tmp_path):
    """After `wineserver -k` a process that ignores SIGTERM is force-killed
    within a couple of seconds, not after the full wait (20 s per winetricks
    verb, for a winedevice.exe that never left by itself)."""
    fake_server = tmp_path / "wineserver"
    fake_server.write_text("#!/bin/sh\nexit 0\n")
    fake_server.chmod(0o755)
    env = {**os.environ, "WINEPREFIX": str(tmp_path)}
    straggler = subprocess.Popen(
        ["bash", "-c", "trap '' TERM; sleep 60"], env=env, start_new_session=True
    )
    try:
        time.sleep(0.3)
        started = time.monotonic()
        assert harness.stop_prefix_wine_processes(
            {"WINESERVER": str(fake_server)}, wait_seconds=20) is True
        assert time.monotonic() - started < 6
        assert wait_dead(straggler)
    finally:
        kill_quietly(straggler)


def test_stop_prefix_wine_processes_lets_the_wineserver_save(harness, tmp_path):
    """A wineserver writing the registry after SIGTERM is waited for, not
    force-killed after the straggler grace: killing it lost renderer=vulkan."""
    fake_server = tmp_path / "wineserver"
    fake_server.write_text("#!/bin/sh\nexit 0\n")
    fake_server.chmod(0o755)
    saved = tmp_path / "saved"
    server = tmp_path / "bin" / "wineserver"
    server.parent.mkdir()
    server.write_text(
        "#!/bin/bash\n"
        f"trap 'sleep 3; touch {saved}; exit 0' TERM\n"
        "while :; do sleep 0.1; done\n"
    )
    server.chmod(0o755)
    env = {**os.environ, "WINEPREFIX": str(tmp_path)}
    proc = subprocess.Popen([str(server)], env=env, start_new_session=True)
    try:
        time.sleep(0.3)
        started = time.monotonic()
        assert harness.stop_prefix_wine_processes(
            {"WINESERVER": str(fake_server)}, wait_seconds=20) is True
        assert saved.exists()
        assert time.monotonic() - started < 10
    finally:
        kill_quietly(proc)


# --------------------------------------------------------------------------- #
# fonts installed without winetricks
# --------------------------------------------------------------------------- #


def test_direct_font_verbs_match_winetricks(ali):
    """Every file, checksum and registered name is the one winetricks uses."""
    winetricks = shutil.which("winetricks")
    if not winetricks:
        pytest.skip("winetricks not installed")
    text = Path(winetricks).read_text(errors="replace")
    for verb, (_, packages) in ali.DIRECT_FONT_VERBS.items():
        for _, name, url, sha256, _, fonts in packages:
            assert sha256 in text, f"{verb}: {name}'s checksum is not winetricks'"
            assert name in text
            for file_name, font_name in fonts:
                assert f'w_register_font {file_name} "{font_name}"' in text, (verb, file_name)


def _fake_font_env(tmp_path, monkeypatch, ali):
    """A one-package verb, a fake cabextract and a fake wine that keeps a copy
    of the .reg file it is given."""
    import hashlib
    cache = tmp_path / "cache"
    (cache / "winetricks" / "fakefonts").mkdir(parents=True)
    package = cache / "winetricks" / "fakefonts" / "fake32.exe"
    package.write_bytes(b"not really a cab")
    sha = hashlib.sha256(package.read_bytes()).hexdigest()
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    monkeypatch.setitem(ali.DIRECT_FONT_VERBS, "fakefonts", (
        ["fakefonts"],
        [("fakefonts", "fake32.exe", "https://example.invalid/fake32.exe", sha,
          "Fake*.TTF", [("fake.ttf", "Fake Sans"), ("fakebd.ttf", "Fake Sans Bold")])],
    ))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cab = bin_dir / "cabextract"
    cab.write_text('#!/bin/sh\n# -q -d DIR FILE\nprintf x > "$3/Fake.TTF"; printf y > "$3/FakeBd.TTF"; printf z > "$3/Other.TTF"\n')
    cab.chmod(0o755)
    seen = tmp_path / "seen.reg"
    wine = bin_dir / "wine"
    wine.write_text(f'#!/bin/sh\necho "$@" >> "{tmp_path}/wine-args"\n'
                    f'cp "$WINEPREFIX/drive_c/windows/temp/$(basename "$(echo "$3" | tr "\\\\\\\\" /)")" "{seen}"\n')
    wine.chmod(0o755)
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    return prefix, wine, cab, seen


def test_install_font_verb_copies_registers_and_logs(ali, tmp_path, monkeypatch):
    prefix, wine, cab, seen = _fake_font_env(tmp_path, monkeypatch, ali)
    fetched = []
    assert ali.install_font_verb(prefix, wine, "fakefonts",
                                 lambda url, path: fetched.append(url) or False,
                                 cabextract=str(cab)) is True
    assert not fetched, "a cached file with the right checksum is not downloaded"
    fonts = prefix / "drive_c" / "windows" / "Fonts"
    assert (fonts / "fake.ttf").read_text() == "x"
    assert (fonts / "fakebd.ttf").read_text() == "y"
    assert not (fonts / "other.ttf").exists(), "only the verb's glob is copied"
    reg = seen.read_text(encoding="utf-16")
    for key in (r"[HKEY_LOCAL_MACHINE\Software\Microsoft\Windows NT\CurrentVersion\Fonts]",
                r"[HKEY_LOCAL_MACHINE\Software\Microsoft\Windows\CurrentVersion\Fonts]",
                r"[HKEY_LOCAL_MACHINE\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Fonts]"):
        assert key in reg
    assert reg.count('"Fake Sans Bold (TrueType)"="fakebd.ttf"') == 3
    assert (tmp_path / "wine-args").read_text().count("regedit") == 1, "one Wine start"
    assert (prefix / "winetricks.log").read_text().splitlines() == ["fakefonts"]
    assert not list((prefix / "drive_c" / "windows" / "temp").glob("*.reg"))


def test_install_font_verb_refuses_a_bad_download(ali, tmp_path, monkeypatch):
    prefix, wine, cab, _ = _fake_font_env(tmp_path, monkeypatch, ali)
    cached = tmp_path / "cache" / "winetricks" / "fakefonts" / "fake32.exe"
    cached.unlink()

    def fetch(url, path):
        Path(path).write_bytes(b"tampered")
        return True

    assert ali.install_font_verb(prefix, wine, "fakefonts", fetch, cabextract=str(cab)) is False
    assert not cached.exists(), "a file with the wrong checksum is not kept"
    assert not (prefix / "winetricks.log").exists()


def test_install_font_verb_falls_back_without_cabextract(ali, tmp_path, monkeypatch):
    prefix, wine, _, _ = _fake_font_env(tmp_path, monkeypatch, ali)
    monkeypatch.setattr(ali.shutil, "which", lambda name: None)
    assert ali.install_font_verb(prefix, wine, "fakefonts", lambda u, p: False) is False


# --------------------------------------------------------------------------- #
# WebView2 setup: Edge Update left behind
# --------------------------------------------------------------------------- #


def spawn_named(prefix, argv0, seconds=60):
    """A process in the prefix whose argv[0] reads like a Windows program's."""
    env = {**os.environ, "WINEPREFIX": str(prefix)}
    return subprocess.Popen(["bash", "-c", f'exec -a "{argv0}" sleep {seconds}'],
                            env=env, start_new_session=True)


def _webview2_installed(tmp_path):
    app = tmp_path / "drive_c" / "Program Files (x86)" / "Microsoft" / "EdgeWebView" / "Application" / "142.0"
    app.mkdir(parents=True)
    (app / "msedgewebview2.exe").write_bytes(b"MZ")


def test_release_webview2_wait_stops_the_leftover_updater(harness, tmp_path):
    _webview2_installed(tmp_path)
    updater = spawn_named(tmp_path, r"C:\\Program Files (x86)\\Microsoft\\EdgeUpdate\\MicrosoftEdgeUpdate.exe")
    service = spawn_named(tmp_path, r"C:\\windows\\system32\\services.exe")
    try:
        stop = threading.Event()
        thread = threading.Thread(target=harness._release_webview2_wait, args=(stop,),
                                  kwargs={"settle_seconds": 0.3, "interval": 0.1})
        thread.start()
        assert wait_dead(updater), "the updater should be stopped"
        thread.join(5)
        assert not thread.is_alive()
        assert service.poll() is None, "Wine's services are left alone"
    finally:
        stop.set()
        kill_quietly(updater, service)


def test_release_webview2_wait_waits_for_the_setup(harness, tmp_path):
    _webview2_installed(tmp_path)
    updater = spawn_named(tmp_path, r"C:\\Program Files (x86)\\Microsoft\\EdgeUpdate\\MicrosoftEdgeUpdate.exe")
    setup = spawn_named(tmp_path, r"C:\\users\\me\\Temp\\setup.exe")
    stop = threading.Event()
    thread = threading.Thread(target=harness._release_webview2_wait, args=(stop,),
                              kwargs={"settle_seconds": 0.3, "interval": 0.1})
    try:
        thread.start()
        time.sleep(1.5)
        assert updater.poll() is None, "not while the setup still runs"
    finally:
        stop.set()
        thread.join(5)
        kill_quietly(updater, setup)


def test_release_webview2_wait_needs_the_runtime(harness, tmp_path):
    updater = spawn_named(tmp_path, r"C:\\Program Files (x86)\\Microsoft\\EdgeUpdate\\MicrosoftEdgeUpdate.exe")
    stop = threading.Event()
    thread = threading.Thread(target=harness._release_webview2_wait, args=(stop,),
                              kwargs={"settle_seconds": 0.3, "interval": 0.1})
    try:
        thread.start()
        time.sleep(1.5)
        assert updater.poll() is None, "not before msedgewebview2.exe exists"
    finally:
        stop.set()
        thread.join(5)
        kill_quietly(updater)


# --------------------------------------------------------------------------- #
# operation clock
# --------------------------------------------------------------------------- #


def test_format_elapsed(ali):
    f = ali.AffinityInstallerGUI.format_elapsed
    assert f(5) == "0:05" and f(754) == "12:34" and f(3723) == "1:02:03"


@pytest.fixture
def clock(ali):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QLabel
    app = QApplication.instance() or QApplication([])

    class StandIn:
        pass

    for name in ("_operation_clock_safe", "_show_clock", "_stop_clock", "format_elapsed"):
        setattr(StandIn, name, inspect.getattr_static(ali.AffinityInstallerGUI, name))
    obj = StandIn()
    obj.timer_label = QLabel("")
    obj._clock_started = None
    obj._clock_tick = QTimer()
    obj._clock_tick.setInterval(1000)
    obj._clock_settle = QTimer()
    obj._clock_settle.setSingleShot(True)
    obj._clock_settle.setInterval(100)
    obj._clock_settle.timeout.connect(obj._stop_clock)
    obj.logged = []
    obj.log = lambda message, level="info": obj.logged.append(message)
    obj.app = app
    return obj


def _spin(app, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def test_the_clock_runs_through_a_nested_end(clock):
    clock._operation_clock_safe(True)
    started = clock._clock_started
    assert clock.timer_label.text().startswith("Started ") and "Elapsed 0:0" in clock.timer_label.text()
    clock._operation_clock_safe(False)          # One-Click: the Wine step ends...
    _spin(clock.app, 0.03)
    clock._operation_clock_safe(True)           # ...and the next step starts
    assert clock._clock_started == started, "one run, one clock"
    assert not clock.logged


def test_the_clock_stops_after_the_last_end(clock):
    clock._operation_clock_safe(True)
    clock._operation_clock_safe(False)
    _spin(clock.app, 0.4)
    assert clock._clock_started is None
    assert "Finished in 0:00" in clock.timer_label.text()
    assert clock.logged and clock.logged[0].startswith("Finished in 0:00 (started ")
    clock._operation_clock_safe(False)          # a stray end changes nothing
    assert len(clock.logged) == 1


# --------------------------------------------------------------------------- #
# the renderer setting
# --------------------------------------------------------------------------- #

def _renderer_gui(ali, monkeypatch, tmp_path, user_reg):
    gui = ali.AffinityInstallerGUI.__new__(ali.AffinityInstallerGUI)
    gui.directory = str(tmp_path)
    (tmp_path / "user.reg").write_text(user_reg)
    calls = []

    def run_command(command, check=True, env=None, timeout=None, **kw):
        calls.append(list(command))
        if "add" in command:
            with open(tmp_path / "user.reg", "a") as f:
                f.write('\n[Software\\\\Wine\\\\Direct3D] 1\n"renderer"="vulkan"\n')
        return True, "", ""

    monkeypatch.setattr(gui, "run_command", run_command, raising=False)
    monkeypatch.setattr(gui, "stop_prefix_wine_processes", lambda *a, **k: True, raising=False)
    monkeypatch.setattr(gui, "get_wine_path", lambda name: tmp_path / name, raising=False)
    monkeypatch.setattr(gui, "log", lambda *a, **k: None, raising=False)
    return gui, calls


def test_a_missing_renderer_setting_is_set_to_vulkan_again(ali, monkeypatch, tmp_path):
    gui, calls = _renderer_gui(ali, monkeypatch, tmp_path, "WINE REGISTRY Version 2\n")
    assert gui.ensure_vulkan_renderer({}) is True
    assert any("add" in c and "vulkan" in c for c in calls)
    assert gui._read_wine_reg_value("HKCU", r"Software\Wine\Direct3D", "renderer") == "vulkan"


def test_a_chosen_renderer_is_kept(ali, monkeypatch, tmp_path):
    gui, calls = _renderer_gui(ali, monkeypatch, tmp_path,
        'WINE REGISTRY Version 2\n\n[Software\\\\Wine\\\\Direct3D] 1\n"renderer"="gl"\n')
    assert gui.ensure_vulkan_renderer({}) is True
    assert calls == []


def test_prefix_temp_dir_folds_a_capitalised_copy_into_wines_temp(ali, tmp_path):
    """A second "Temp" beside Wine's "temp" is what Wine opens for
    C:\\windows\\Temp, so winetricks' .reg files (written into "temp") were
    not found and its registry changes were lost."""
    windows = tmp_path / "drive_c" / "windows"
    (windows / "temp" / "_vcrun2022").mkdir(parents=True)
    (windows / "Temp").mkdir()
    (windows / "Temp" / "font-corefonts.reg").write_text("x")
    (windows / "Temp" / "_vcrun2022").mkdir()
    temp = ali.prefix_temp_dir(tmp_path)
    assert temp == windows / "temp"
    assert sorted(p.name for p in windows.iterdir()) == ["temp"]
    assert sorted(p.name for p in temp.iterdir()) == ["_vcrun2022", "font-corefonts.reg"]


def test_prefix_temp_dir_creates_wines_name(ali, tmp_path):
    (tmp_path / "drive_c" / "windows").mkdir(parents=True)
    assert ali.prefix_temp_dir(tmp_path).name == "temp"


# --------------------------------------------------------------------------- #
# one action at a time
# --------------------------------------------------------------------------- #

def _click_gui(ali, monkeypatch):
    gui = ali.AffinityInstallerGUI.__new__(ali.AffinityInstallerGUI)
    gui.operation_in_progress = False
    gui.current_operation = None
    shown = []
    monkeypatch.setattr(ali.QMessageBox, "information", lambda *a, **k: shown.append(a), raising=False)
    monkeypatch.setattr(gui, "dialog_parent", lambda: None, raising=False)
    monkeypatch.setattr(gui, "log", lambda *a, **k: None, raising=False)
    return gui, shown


def test_a_second_click_while_an_action_runs_is_refused(ali, monkeypatch):
    """One-Click Full Setup ran twice at once on a second click: the two runs
    unpacked Wine over each other and deleted each other's download."""
    gui, shown = _click_gui(ali, monkeypatch)
    release = threading.Event()
    calls = []

    def action():
        calls.append(1)
        def work():
            gui.operation_in_progress = True
            release.wait(10)
        threading.Thread(target=work, daemon=True).start()
        time.sleep(0.2)

    gui._handle_button_click(None, action)
    gui._handle_button_click(None, action)
    assert calls == [1] and len(shown) == 1
    release.set()
    for t in gui._action_threads:
        t.join(5)
    # The thread is gone: a path that skipped end_operation() does not lock the buttons.
    gui._handle_button_click(None, lambda: calls.append(2))
    assert calls == [1, 2]
