"""The plugin loader the installer downloads is pinned, like the Wine build.

Upstream's latest release (v0.3.0) predates Canva sign-in, the command-line
open fix and the runtime Direct2D patches, so the installer takes a named
release instead and refuses any zip whose SHA-256 is not the one it carries.

That build also stopped shipping WineFix's own d2d1.dll -- its Direct2D fixes
patch Wine's d2d1 at runtime -- so a copy an older WineFix left beside
Affinity.exe must not stay there shadowing Wine's.

The install runs for real against local zips; "wine" is /bin/true, so the
step that starts AffinityHook.exe once launches nothing.
"""
import hashlib
import io
import json
import re
import shutil
import sys
import types
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import aol  # noqa: E402

try:
    inst = aol.module()
    HAVE = hasattr(inst, "APL_ASSET_SHA256")
except aol.NotAvailable:
    inst, HAVE = None, False

pytestmark = pytest.mark.skipif(not HAVE, reason="installer without the plugin loader pin")


def test_the_pins_are_real_checksums_for_both_archives():
    names = sorted(inst.APL_ASSET_SHA256)
    assert any(n.startswith("affinitypluginloader") and n.endswith(".zip") for n in names)
    assert any(n.startswith("winefix") and n.endswith(".zip") for n in names)
    for digest in inst.APL_ASSET_SHA256.values():
        assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert inst.APL_RELEASE_TAG and "/" in inst.APL_RELEASE_REPO


def _zip(path, files):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return path


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def release(tmp_path, monkeypatch):
    """Two archives laid out like the real release, served from file:// URLs."""
    srv = tmp_path / "srv"
    srv.mkdir()
    apl = _zip(srv / "affinitypluginloader-v0.3.0.zip", {
        "AffinityHook.exe": b"MZ hook", "AffinityPluginLoader.dll": b"MZ apl",
        "AffinityBootstrap.dll": b"MZ boot", "0Harmony.dll": b"MZ harmony",
        "LICENSE": b"MIT"})
    winefix = _zip(srv / "winefix-v0.3.0.zip", {
        "apl/plugins/WineFix.dll": b"MZ winefix", "LICENSE": b"GPLv2"})
    payload = {"tag_name": "test", "assets": [
        {"name": p.name, "browser_download_url": p.as_uri()} for p in (apl, winefix)]}

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    real_urlopen = inst.urllib.request.urlopen

    def urlopen(url, *a, **k):
        # Only the release API is faked; urlretrieve fetches the file:// zips
        # through urlopen too, and those must be read for real.
        full = getattr(url, "full_url", url)
        if str(full).startswith("https://api.github.com/"):
            return Response(json.dumps(payload).encode())
        return real_urlopen(url, *a, **k)

    monkeypatch.setattr(inst.urllib.request, "urlopen", urlopen)
    return apl, winefix


def _run(tmp_path):
    prefix = tmp_path / "pfx"
    app = prefix / "drive_c" / "Program Files" / "Affinity" / "Affinity"
    app.mkdir(parents=True, exist_ok=True)
    logged = []
    true = shutil.which("true")
    stub = types.SimpleNamespace(
        directory=str(prefix),
        log=lambda message, level="info": logged.append((level, message)),
        update_progress=lambda *a: None,
        end_operation=lambda: None,
        show_message=lambda *a, **k: None,
        get_wine_path=lambda binary: Path(true),
        get_gpu_env_vars=lambda: "",
        get_dxvk_env_vars=lambda: "",
        _patch_affinity_desktop_for_hook=lambda: None,
    )
    return app, stub, logged


def test_the_pinned_build_installs_and_moves_an_old_d2d1_aside(tmp_path, release, monkeypatch):
    apl, winefix = release
    monkeypatch.setattr(inst, "APL_ASSET_SHA256", {apl.name: _sha(apl), winefix.name: _sha(winefix)})
    app, stub, logged = _run(tmp_path)
    (app / "d2d1.dll").write_bytes(b"MZ wine 10.18 d2d1 from an old WineFix")

    inst.AffinityInstallerGUI._install_affinity_plugin_loader_thread(stub, standalone=False)

    assert (app / "AffinityHook.exe").read_bytes() == b"MZ hook"
    assert (app / "apl" / "plugins" / "WineFix.dll").read_bytes() == b"MZ winefix"
    assert not (app / "d2d1.dll").exists(), "the old d2d1.dll would shadow Wine's"
    assert (app / "d2d1.dll.winefix-old").read_bytes().startswith(b"MZ wine 10.18")
    assert not [m for level, m in logged if level == "error"]


def test_a_fresh_prefix_needs_no_d2d1(tmp_path, release, monkeypatch):
    apl, winefix = release
    monkeypatch.setattr(inst, "APL_ASSET_SHA256", {apl.name: _sha(apl), winefix.name: _sha(winefix)})
    app, stub, logged = _run(tmp_path)

    inst.AffinityInstallerGUI._install_affinity_plugin_loader_thread(stub, standalone=False)

    assert not (app / "d2d1.dll").exists() and not (app / "d2d1.dll.winefix-old").exists()
    assert not any("check its layout" in m for _, m in logged)


def test_a_zip_that_is_not_the_pinned_build_is_refused(tmp_path, release, monkeypatch):
    apl, winefix = release
    monkeypatch.setattr(inst, "APL_ASSET_SHA256", {apl.name: "0" * 64, winefix.name: _sha(winefix)})
    app, stub, logged = _run(tmp_path)

    inst.AffinityInstallerGUI._install_affinity_plugin_loader_thread(stub, standalone=False)

    assert not (app / "AffinityHook.exe").exists()
    assert any(level == "error" and "not the build this installer pins" in m for level, m in logged)
