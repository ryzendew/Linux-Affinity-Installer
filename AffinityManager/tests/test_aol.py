"""Loading the installer instead of copying it.

The contract this rests on: the installer file stays byte-identical upstream,
and the manager reaches into it by name. So the test that matters is not "does
it load" but "are the names still there" -- because a rename upstream is
silent, and the symptom without this is a blank window or an AttributeError an
hour into a session.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import aol, ui  # noqa: E402


def installer_available() -> bool:
    try:
        aol.module()
        return True
    except aol.NotAvailable:
        return False


needs_installer = pytest.mark.skipif(
    not installer_available(), reason="no AffinityOnLinux checkout to load")


@needs_installer
def test_every_name_the_manager_reaches_for_is_present():
    """If this fails, upstream renamed something and the message says which."""
    assert aol.verify() == []


@needs_installer
def test_loading_is_cached():
    assert aol.module() is aol.module()


@needs_installer
def test_loading_starts_no_gui_and_no_threads():
    """It is import-safe because everything at column zero is a def, a class or
    the __main__ guard -- but that is upstream's file, so check rather than
    trust it."""
    import threading
    before = threading.active_count()
    aol.module()
    assert threading.active_count() == before
    assert "QApplication" not in repr(getattr(aol.module(), "app", None))


@needs_installer
def test_all_three_themes_still_produce_a_stylesheet():
    for theme in ui.THEMES:
        css = ui.stylesheet(theme)
        assert len(css) > 1000, f"{theme} produced {len(css)} characters"
        assert "QPushButton" in css


@needs_installer
def test_the_widgets_resolve_to_classes():
    assert isinstance(ui.log_widget_class(), type)
    assert isinstance(ui.spinner_class(), type)


@needs_installer
def test_target_env_sets_and_restores():
    key = aol.module().ENV_INSTALL_DIR
    os.environ[key] = "/was/here"
    try:
        with aol.target_env("/tmp/somewhere"):
            assert os.environ[key] == "/tmp/somewhere"
        assert os.environ[key] == "/was/here"
    finally:
        os.environ.pop(key, None)


@needs_installer
def test_target_env_restores_even_when_the_block_raises():
    """The installer is constructed inside this block. If construction throws,
    a leaked AFFINITY_INSTALL_DIR would redirect every later subprocess."""
    key = aol.module().ENV_INSTALL_DIR
    os.environ.pop(key, None)
    with pytest.raises(RuntimeError):
        with aol.target_env("/tmp/somewhere"):
            raise RuntimeError("construction failed")
    assert key not in os.environ


@needs_installer
def test_target_env_clears_a_stale_installer_file():
    """An installer file left from a previous prefix must not be inherited by
    the next one."""
    mod = aol.module()
    os.environ[mod.ENV_INSTALLER_FILE] = "/old/Affinity.exe"
    try:
        with aol.target_env("/tmp/p"):
            assert mod.ENV_INSTALLER_FILE not in os.environ
        assert os.environ[mod.ENV_INSTALLER_FILE] == "/old/Affinity.exe"
    finally:
        os.environ.pop(mod.ENV_INSTALLER_FILE, None)


def test_a_missing_installer_is_reported_not_raised_as_anything_else(monkeypatch):
    monkeypatch.setattr(aol, "_module", None)
    monkeypatch.setattr(aol.installer, "check_installer",
                        lambda script=None: (_ for _ in ()).throw(
                            aol.installer.InstallerNotFound("nowhere")))
    with pytest.raises(aol.NotAvailable):
        aol.module()
    monkeypatch.setattr(aol, "_module", None)
    assert aol.verify() and "nowhere" in aol.verify()[0]


# ── living inside AffinityOnLinux as AffinityManager/ ───────────────────────
#
# The merged layout is AffinityOnLinux/{AffinityScripts,AffinityManager}, so
# the installer is two directories up and across. These pin that, because the
# path is computed from __file__ and a directory rename would otherwise break
# it silently -- the manager would simply fall back to a fetched checkout and
# drive a different installer than the one it shipped with.

def test_the_vendored_installer_is_the_sibling_of_this_directory():
    from affinity_manager import installer

    root = Path(installer.__file__).resolve().parent.parent
    assert installer.vendored_installer() == \
        root.parent / "AffinityScripts" / installer.SCRIPT_NAME


def test_the_vendored_copy_outranks_a_fetched_checkout(monkeypatch):
    """A manager shipped inside AffinityOnLinux should drive the installer it
    shipped with, not one pulled from a branch."""
    from affinity_manager import installer, settings

    monkeypatch.delenv(installer.ENV_SCRIPT, raising=False)
    monkeypatch.setattr(settings, "get", lambda *a, **k: "")
    paths = installer.candidate_paths()
    assert paths.index(installer.vendored_installer()) < \
        paths.index(installer.managed_checkout() / "AffinityScripts"
                    / installer.SCRIPT_NAME)


def test_a_vendored_installer_is_not_warned_about_for_its_branch():
    """The branch warning is there because a checkout on main has an installer
    that ignores the prefix it is handed. Once merged, the branch is whatever
    AffinityOnLinux is on, and warning every time is how a real warning stops
    being read."""
    from affinity_manager import installer

    info = {
        "found": True, "script": "/x/AffinityScripts/AffinityLinuxInstaller.py",
        "branch": "some-feature", "commit": "abc1234", "dirty": False,
        "supports_install_dir": True, "on_preferred_branch": False,
        "vendored": True,
    }
    line = installer.summary(info)
    assert installer.PREFERRED_BRANCH not in line
    assert "shipped with this manager" in line

    info["vendored"] = False
    assert installer.PREFERRED_BRANCH in installer.summary(info)


# ── the installer's two path helpers, used correctly ────────────────────────
#
# Both of these encode a bug that shipped. script_dir() and checkout_root()
# return None for the documented `curl ... | python3` install, and both failure
# modes were invisible because the methods involved wrap everything in
# `except Exception` -- so the download that should have followed never ran and
# nothing was logged.

def _installer_tree():
    import ast
    from affinity_manager import installer as installer_mod

    path = installer_mod.find_installer()
    return ast.parse(path.read_text()), path


def test_no_function_shadows_the_path_helpers():
    """A local named script_dir shadows the module function for the WHOLE body.

    _ensure_icons_directory bound `script_dir = Path.home() / ...` ten lines
    above `here = script_dir()`, so the call raised TypeError: 'PosixPath'
    object is not callable, every time, for every user. Python's scoping makes
    this invisible to the eye and trivial to catch here."""
    import ast

    tree, path = _installer_tree()
    guilty = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        bound = {t.id for n in ast.walk(node) if isinstance(n, ast.Assign)
                 for t in n.targets if isinstance(t, ast.Name)}
        bound |= {a.arg for a in node.args.args}
        clash = bound & {"script_dir", "checkout_root"}
        if clash:
            guilty.append(f"{node.name} (line {node.lineno}) shadows {sorted(clash)}")
    assert not guilty, f"in {path}:\n  " + "\n  ".join(guilty)


def test_every_helper_result_is_guarded_before_it_is_joined():
    """None / "filename" raises, and the raise is swallowed.

    ensure_patcher_files did `source_patch_dir = root / ... if root else None`
    and then `source_patch_dir / filename` unconditionally, which killed the
    method -- and the GitHub download below it -- for the piped install.

    The taint has to propagate one hop. An earlier version of this test tracked
    only names assigned directly from a helper call, so it followed `root` and
    missed `source_patch_dir` -- and passed against the exact bug it was
    written for. A name is "may be None" if it comes from a helper, or from a
    conditional with a None branch, which is how the value actually travels."""
    import ast

    tree, path = _installer_tree()
    complaints = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        maybe_none = set()
        for _ in range(4):                  # a fixed point; the chains are short
            before = set(maybe_none)
            for node in ast.walk(func):
                if not isinstance(node, ast.Assign):
                    continue
                value = node.value
                # Only what descends from the two helpers. Tainting every
                # may-be-None value instead flagged six unrelated places that
                # guard with an early return, which is a perfectly good guard
                # and not what this test is about.
                tainted = any(
                    isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                    and c.func.id in ("script_dir", "checkout_root")
                    for c in ast.walk(value)
                ) or any(
                    isinstance(n, ast.Name) and n.id in maybe_none
                    for n in ast.walk(value)
                )
                if tainted:
                    maybe_none |= {t.id for t in node.targets
                                   if isinstance(t, ast.Name)}
            if maybe_none == before:
                break

        for node in ast.walk(func):
            if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
                continue
            if not (isinstance(node.left, ast.Name) and node.left.id in maybe_none):
                continue
            name = node.left.id
            guarded = False
            # The three shapes a guard actually takes here: an if statement, a
            # conditional expression, and a short-circuit `and` -- the last one
            # puts the join inside the TEST rather than the body, which an
            # earlier version of this test did not recognise and reported as a
            # defect.
            for scope in ast.walk(func):
                pairs = []
                if isinstance(scope, ast.If):
                    pairs = [([scope.test], scope.body)]
                elif isinstance(scope, ast.IfExp):
                    pairs = [([scope.test], [scope.body])]
                elif isinstance(scope, ast.BoolOp) and isinstance(scope.op, ast.And):
                    pairs = [(scope.values[:i + 1], scope.values[i + 1:])
                             for i in range(len(scope.values) - 1)]
                for tests, body in pairs:
                    mentions = any(n.id == name for t in tests
                                   for n in ast.walk(t) if isinstance(n, ast.Name))
                    if mentions and any(node is n for b in body for n in ast.walk(b)):
                        guarded = True
                        break
                if guarded:
                    break
            if not guarded:
                complaints.append(
                    f"{func.name} (line {node.lineno}): {name} / ... with no "
                    f"`if {name}` around it")
    assert not complaints, f"in {path}:\n  " + "\n  ".join(complaints)


def test_choosing_a_different_installer_says_a_restart_is_needed(monkeypatch, tmp_path):
    """Loading a second copy would build a second set of Qt classes with the
    same names. Silently continuing with the first was worse: Settings reported
    the new path everywhere while the manager went on running the old one --
    the one thing the installer reporting exists to prevent."""
    from affinity_manager import aol as aol_mod, installer as installer_mod

    other = tmp_path / "AffinityLinuxInstaller.py"
    other.write_text("# " + installer_mod.ENV_INSTALL_DIR + "\n")

    monkeypatch.setattr(aol_mod, "_module", object())
    monkeypatch.setattr(aol_mod, "_source", tmp_path / "somewhere-else.py")
    with pytest.raises(aol_mod.NeedsRestart) as caught:
        aol_mod.module(other)
    assert str(other) in str(caught.value)


def test_the_same_installer_path_keeps_the_cached_module(monkeypatch, tmp_path):
    from affinity_manager import aol as aol_mod, installer as installer_mod

    same = tmp_path / "AffinityLinuxInstaller.py"
    same.write_text("# " + installer_mod.ENV_INSTALL_DIR + "\n")
    sentinel = object()
    monkeypatch.setattr(aol_mod, "_module", sentinel)
    monkeypatch.setattr(aol_mod, "_source", same)
    assert aol_mod.module(same) is sentinel


def test_a_broken_path_does_not_discard_a_working_installer(monkeypatch, tmp_path):
    """A loaded installer beats a path that no longer resolves."""
    from affinity_manager import aol as aol_mod

    sentinel = object()
    monkeypatch.setattr(aol_mod, "_module", sentinel)
    monkeypatch.setattr(aol_mod, "_source", tmp_path / "loaded.py")
    assert aol_mod.module(tmp_path / "does-not-exist.py") is sentinel
