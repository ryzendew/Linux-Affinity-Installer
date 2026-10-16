"""run.py: the single file that starts the manager straight from the repository.

Never touches the network. Each test builds a tarball shaped like a git forge's --
one top directory, the commit in the pax header -- and hands it to run.py in
place of the download.
"""
import importlib.util
import io
import os
import sys
import tarfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bootstrap", ROOT / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

COMMIT_A = "a" * 40
COMMIT_B = "b" * 40


def tarball(commit=COMMIT_A, extra=None, missing=(), top="affinityonlinux"):
    files = {
        "AffinityManager/AffinityLinuxManager.py": b"# the manager\n",
        "AffinityManager/affinity_manager/__init__.py": b"",
        "AffinityScripts/AffinityLinuxInstaller.py": b"# the installer\n",
    }
    for name in missing:
        files.pop(name)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.PAX_FORMAT,
                      pax_headers={"comment": commit} if commit else {}) as tf:
        root = tarfile.TarInfo(top)
        root.type = tarfile.DIRTYPE
        tf.addfile(root)
        for name, data in files.items():
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        for info, data in (extra or []):
            tf.addfile(info, io.BytesIO(data) if data is not None else None)
    return buf.getvalue()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(run, "check_environment", lambda: None)
    monkeypatch.setattr(run, "in_use", lambda path: False)
    calls = []
    served = {"data": tarball()}

    def download(url):
        calls.append(url)
        if isinstance(served["data"], Exception):
            raise served["data"]
        return served["data"]

    monkeypatch.setattr(run, "download", download)
    started = []
    return type("Env", (), {
        "root": run.cache_root(run.BRANCH), "calls": calls, "served": served,
        "started": started,
        "go": staticmethod(lambda *args: run.main(list(args),
                                                  run=lambda exe, cmd: started.append(cmd))),
    })()


def test_it_downloads_the_branch_and_starts_the_manager_from_it(env):
    assert env.go("--some-flag") == 0
    assert env.calls == [f"{run.REPO}/archive/{run.BRANCH}.tar.gz"]
    command = env.started[0]
    assert command[0] == sys.executable
    entry = Path(command[1])
    assert entry.name == "AffinityLinuxManager.py" and entry.is_file()
    assert entry.parents[1].name == COMMIT_A[:12]
    # The installer is beside it, which is where the manager looks first.
    assert (entry.parents[1] / "AffinityScripts" / "AffinityLinuxInstaller.py").is_file()
    assert command[2:] == ["--some-flag"]


def test_the_same_commit_is_not_unpacked_twice(env):
    env.go()
    first = Path(env.started[0][1])
    marker = first.parent / "touched"
    marker.write_text("x")
    env.go()
    assert Path(env.started[1][1]) == first and marker.exists()


def test_a_new_commit_gets_its_own_copy(env):
    env.go()
    env.served["data"] = tarball(COMMIT_B)
    env.go()
    assert Path(env.started[1][1]).parents[1].name == COMMIT_B[:12]
    assert len(run.copies(env.root)) == 2


def test_offline_starts_the_newest_copy_it_has(env):
    env.go()
    env.served["data"] = OSError("Network is unreachable")
    assert env.go() == 0
    assert Path(env.started[1][1]) == Path(env.started[0][1])


def test_offline_with_nothing_cached_refuses_and_says_why(env, capsys):
    env.served["data"] = OSError("Network is unreachable")
    assert env.go() == 1
    assert env.started == []
    assert "no earlier copy" in capsys.readouterr().err


def test_a_branch_without_the_manager_is_refused(env, capsys):
    env.served["data"] = tarball(missing=["AffinityManager/AffinityLinuxManager.py"])
    assert env.go() == 1
    assert env.started == [] and run.copies(env.root) == []
    assert "right branch" in capsys.readouterr().err


def test_an_interrupted_unpack_is_never_started(env, monkeypatch):
    """Built under a temporary name and renamed into place; a half-unpacked
    copy must not be the one the next offline run picks."""
    real_extract = tarfile.TarFile.extract
    count = {"n": 0}

    def flaky(self, member, path="", **kw):
        count["n"] += 1
        if count["n"] == 2:
            raise OSError(28, "No space left on device")
        return real_extract(self, member, path, **kw)

    monkeypatch.setattr(tarfile.TarFile, "extract", flaky)
    with pytest.raises(OSError):
        env.go()
    assert run.copies(env.root) == []
    assert not [p for p in env.root.iterdir() if ".partial-" in p.name]


@pytest.mark.parametrize("name", ["affinityonlinux/../../escape.py",
                                  "/etc/passwd"])
def test_a_path_escaping_the_cache_is_refused(env, name):
    info = tarfile.TarInfo(name)
    info.size = 1
    env.served["data"] = tarball(extra=[(info, b"x")])
    assert env.go() == 1
    assert not (env.root.parent / "escape.py").exists()
    assert run.copies(env.root) == []


def test_a_link_in_the_tarball_is_refused(env):
    """The repository holds no links, so a tarball with one is not it."""
    info = tarfile.TarInfo("affinityonlinux/AffinityManager/evil")
    info.type = tarfile.SYMTYPE
    info.linkname = "/home"
    env.served["data"] = tarball(extra=[(info, None)])
    assert env.go() == 1 and env.started == []


def test_without_a_commit_in_the_header_the_contents_name_the_copy(env):
    env.served["data"] = tarball(commit=None)
    env.go()
    assert Path(env.started[0][1]).parents[1].name.startswith("sha256-")


def test_old_copies_are_pruned_but_never_one_in_use(env, monkeypatch):
    for i in range(5):
        env.served["data"] = tarball(f"{i:x}" * 40)
        env.go()
        os.utime(Path(env.started[-1][1]).parents[1], (time.time() + i, time.time() + i))
    oldest = sorted(run.copies(env.root), key=lambda p: p.stat().st_mtime)[0]
    monkeypatch.setattr(run, "in_use", lambda path: path == oldest)
    run.prune(env.root)
    left = run.copies(env.root)
    assert oldest in left, "a copy a manager is running from was deleted"
    assert len(left) == run.KEEP + 1


def test_the_branch_and_repository_can_be_overridden(env, monkeypatch):
    monkeypatch.setenv("AFFINITY_MANAGER_REPO", "https://example.org/me/AffinityOnLinux/")
    monkeypatch.setenv("AFFINITY_MANAGER_BRANCH", "feature/x")
    env.go()
    assert env.calls[-1] == "https://example.org/me/AffinityOnLinux/archive/feature/x.tar.gz"
    assert run.cache_root("feature/x").name == "feature-x"


def test_a_missing_pyqt6_stops_before_downloading(env, monkeypatch, capsys):
    def no_qt():
        raise run.Refused(run.PYQT_HINT)

    monkeypatch.setattr(run, "check_environment", no_qt)
    assert env.go() == 1
    assert env.calls == [] and "pacman" in capsys.readouterr().err


def test_the_url_in_the_docstring_is_the_one_the_code_uses():
    """The docstring's curl line is what people copy. It must name this file
    on the branch the code downloads."""
    expected = run.raw_url(run.REPO, run.BRANCH, "AffinityManager/run.py")
    assert expected in run.__doc__


def test_the_manager_is_told_which_commit_it_is_running(env, monkeypatch):
    """A tarball is not a git checkout; without this the manager could only
    say 'shipped with this manager' about a build nobody could identify."""
    monkeypatch.delenv("AFFINITY_MANAGER_SOURCE", raising=False)
    env.go()
    assert os.environ["AFFINITY_MANAGER_SOURCE"] == f"{run.BRANCH} @ {COMMIT_A[:12]}"
    monkeypatch.delenv("AFFINITY_MANAGER_SOURCE")


def test_the_readme_gives_the_same_command():
    """The README's curl line is the one people copy. If the repository or
    branch moves, it must move with the code."""
    readme = (ROOT / "README.md").read_text()
    url = run.raw_url(run.REPO, run.BRANCH, "AffinityManager/run.py")
    assert f"curl -sSL {url} | python3" in readme


def test_raw_urls_are_spelled_for_the_service():
    assert run.raw_url("https://github.com/o/r", "main", "a/b.py") == \
        "https://github.com/o/r/raw/main/a/b.py"
    assert run.raw_url("https://git.example.org/o/r", "dev", "a/b.py") == \
        "https://git.example.org/o/r/raw/branch/dev/a/b.py"


def test_the_source_used_is_passed_on(env, monkeypatch):
    """The installer fetches its own files from wherever this run came from,
    so a staging run must hand its repository and branch down."""
    monkeypatch.setenv("AFFINITY_MANAGER_REPO", "https://git.example.org/o/r")
    monkeypatch.setenv("AFFINITY_MANAGER_BRANCH", "staging")
    env.go()
    assert os.environ["AFFINITY_MANAGER_REPO"] == "https://git.example.org/o/r"
    assert os.environ["AFFINITY_MANAGER_BRANCH"] == "staging"
