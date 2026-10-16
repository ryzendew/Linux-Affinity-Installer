"""The Wine build the installer downloads is pinned by content.

The 11.16 release was published once and never rebuilt; new installs went
three weeks without eight Wine fixes the local builds had, and nothing noticed.
The installer now carries the release's SHA-256 and refuses any other tarball.
"""
import re
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import aol  # noqa: E402

try:
    inst = aol.module()
    HAVE = hasattr(inst, "WINE_11_19_SHA256")
    HAVE_1118 = hasattr(inst, "WINE_11_18_SHA256")
except aol.NotAvailable:
    inst, HAVE, HAVE_1118 = None, False, False

pytestmark = pytest.mark.skipif(not HAVE, reason="installer without the Wine pin")


def check(path, config):
    logged = []
    stub = types.SimpleNamespace(log=lambda message, level="info": logged.append((level, message)))
    ok = inst.AffinityInstallerGUI._wine_download_matches(stub, path, config)
    return ok, logged


def test_the_pin_is_a_real_checksum():
    assert re.fullmatch(r"[0-9a-f]{64}", inst.WINE_11_19_SHA256), \
        "the placeholder was never replaced with the release's checksum"


def test_the_11_19_download_carries_the_pin():
    config = inst.AffinityInstallerGUI._get_wine_version_config(None, "11.19")
    assert config["wine_sha256"] == inst.WINE_11_19_SHA256
    # A rebuilt release goes up under a new tag (11.19-rN); the old one stays
    # for rollback, so the URL names a revision.
    assert "/releases/download/11.19-r" in config["wine_url"]


def test_a_different_tarball_is_refused(tmp_path):
    f = tmp_path / "ElementalWarrior-wine-11.16.tar.xz"
    f.write_bytes(b"not the release")
    ok, logged = check(f, {"wine_sha256": "0" * 64, "wine_display_name": "Wine 11.16"})
    assert not ok
    assert any(level == "error" and "Not installing" in m for level, m in logged)


def test_the_right_tarball_is_accepted(tmp_path):
    f = tmp_path / "w.tar.xz"
    f.write_bytes(b"the release")
    ok, _ = check(f, {"wine_sha256": inst._sha256_of(f), "wine_display_name": "Wine 11.16"})
    assert ok


def test_an_unpinned_build_is_not_checked(tmp_path):
    ok, logged = check(tmp_path / "missing.tar.xz", {"wine_display_name": "Wine 10.10"})
    assert ok and logged == []


@pytest.mark.skipif(not HAVE_1118, reason="installer without Wine 11.18")
def test_the_11_18_download_carries_its_own_pin():
    assert re.fullmatch(r"[0-9a-f]{64}", inst.WINE_11_18_SHA256)
    assert inst.WINE_11_18_SHA256 != inst.WINE_11_19_SHA256
    config = inst.AffinityInstallerGUI._get_wine_version_config(None, "11.18")
    assert config["wine_sha256"] == inst.WINE_11_18_SHA256
    assert config["wine_url"].endswith("/ElementalWarrior-wine-11.18.tar.xz")
    assert config["wine_dir_pattern"] == "ElementalWarrior-wine-11.18*"
