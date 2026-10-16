"""Attribution: whose is this artifact?

Everything the manager does to the host turns on this. Getting it wrong in the
generous direction means editing or deleting somebody else's launcher; getting
it wrong in the shy direction means a removal that leaves the menu full of dead
entries. Both cases are tested.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import desktopentry, hoststate  # noqa: E402


@pytest.fixture
def data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    (tmp_path / "applications").mkdir(parents=True)
    (tmp_path / "mime" / "packages").mkdir(parents=True)
    (tmp_path / "icons").mkdir(parents=True)
    return tmp_path


def our_mime(path: Path, prefix: str, types=hoststate.DOCUMENT_TYPES):
    body = "".join(f'  <mime-type type="{t}"/>\n' for t in types)
    path.write_text(
        "<?xml version='1.0'?>\n"
        f"<!-- {hoststate.MIME_MARKER}: {prefix} -->\n"
        f"<mime-info>\n{body}</mime-info>\n"
    )


def test_names_are_per_prefix_and_cannot_collapse(data_home):
    """'Affinity 33' and 'Affinity33' must not share a file."""
    a = hoststate.mime_path("Affinity 33")
    b = hoststate.mime_path("Affinity33")
    assert a != b
    assert hoststate.icon_path("Affinity 33") != hoststate.icon_path("Affinity33")


def test_our_naming_avoids_winemenubuilders_scheme(data_home):
    """winemenubuilder generates x-wine-extension-<ext>.xml for every
    association a prefix registers, into this same directory."""
    for name in ("Working", "3.3 Test"):
        assert not hoststate.mime_path(name).name.startswith("x-wine-extension-")


def test_an_unmarked_mime_package_is_never_ours(data_home):
    path = hoststate.mime_packages_dir() / "x-wine-extension-afphoto.xml"
    path.write_text('<?xml version="1.0"?><mime-info>'
                    '<mime-type type="application/afphoto"/></mime-info>')
    owner, prefix = hoststate.mime_owner(path)
    assert owner == hoststate.FOREIGN and prefix is None


def test_a_marked_mime_package_names_its_prefix(data_home):
    path = hoststate.mime_path("Working Copy")
    our_mime(path, "Working Copy")
    owner, prefix = hoststate.mime_owner(path)
    assert owner == hoststate.OURS and prefix == "Working Copy"


def test_artifacts_for_returns_only_that_prefixs_things(data_home):
    our_mime(hoststate.mime_path("Alpha"), "Alpha")
    our_mime(hoststate.mime_path("Beta"), "Beta")
    hoststate.icon_path("Alpha").write_text("<svg/>")
    found = hoststate.artifacts_for("Alpha")
    kinds = {(a.kind, a.path.name) for a in found}
    assert ("mime", hoststate.mime_path("Alpha").name) in kinds
    assert ("icon", hoststate.icon_path("Alpha").name) in kinds
    assert all("Beta" not in a.path.name for a in found)
    assert all(a.owner == hoststate.OURS for a in found)


def test_foreign_includes_someone_elses_entry_and_excludes_ours(data_home):
    apps = hoststate.applications_dir()
    (apps / "Affinity.desktop").write_text(
        "[Desktop Entry]\nExec=env WINEPREFIX=/somewhere wine Affinity.exe\n")
    (apps / "affinity-manager-ours-launch.desktop").write_text(
        f"[Desktop Entry]\nExec=/bin/true\n{desktopentry.MARKER}=Ours\n")
    names = {a.path.name for a in hoststate.foreign_artifacts()}
    assert "Affinity.desktop" in names
    assert "affinity-manager-ours-launch.desktop" not in names


def test_foreign_ignores_mime_files_for_unrelated_types(data_home):
    """winemenubuilder writes plenty of these; only the ones claiming OUR
    document types are worth reporting."""
    packages = hoststate.mime_packages_dir()
    (packages / "x-wine-extension-crd.xml").write_text(
        '<?xml version="1.0"?><mime-info>'
        '<mime-type type="application/x-wine-extension-crd"/></mime-info>')
    (packages / "x-wine-extension-afphoto.xml").write_text(
        '<?xml version="1.0"?><mime-info>'
        '<mime-type type="application/afphoto"/></mime-info>')
    names = {a.path.name for a in hoststate.foreign_artifacts()}
    assert "x-wine-extension-afphoto.xml" in names
    assert "x-wine-extension-crd.xml" not in names


def test_handler_prefix_reads_the_prefix_out_of_our_own_entry(data_home):
    apps = hoststate.applications_dir()
    entry = apps / "affinity-manager-working-launch.desktop"
    entry.write_text(f"[Desktop Entry]\nExec=/bin/true\n{desktopentry.MARKER}=Working\n")
    handlers = [hoststate.Artifact("default-handler", None, hoststate.SHARED,
                                   None, "", value=entry.name)]
    assert hoststate.handler_prefix(handlers) == "Working"


def test_handler_prefix_is_unknown_for_a_fixed_name_entry(data_home):
    """AffinityOnLinux's Affinity.desktop carries no marker, and every install
    rewrites it -- so the honest answer is None, not a guess."""
    apps = hoststate.applications_dir()
    (apps / "Affinity.desktop").write_text(
        "[Desktop Entry]\nExec=env WINEPREFIX=/home/x/.AffinityLinux wine Affinity.exe\n")
    handlers = [hoststate.Artifact("default-handler", None, hoststate.SHARED,
                                   None, "", value="Affinity.desktop")]
    assert hoststate.handler_prefix(handlers) is None


def test_a_missing_handler_does_not_raise(data_home):
    handlers = [hoststate.Artifact("default-handler", None, hoststate.SHARED,
                                   None, "", value=None)]
    assert hoststate.handler_prefix(handlers) is None


# ----------------------------------------------------------------------------
# Viewing, editing and deleting assets. The attribution rules are what make
# these safe, so both sides are tested: ours goes through, foreign is refused
# until asked for, and nothing is ever lost.


def test_all_artifacts_lists_ours_foreign_and_shared(data_home, monkeypatch):
    our_mime(hoststate.mime_path("Alpha"), "Alpha")
    (hoststate.applications_dir() / "Affinity.desktop").write_text("[Desktop Entry]\n")
    monkeypatch.setattr(hoststate, "default_handlers", lambda: [
        hoststate.Artifact("default-handler", None, hoststate.SHARED, None, "af -> x")])
    owners = {a.owner for a in hoststate.all_artifacts(["Alpha"])}
    assert owners == {hoststate.OURS, hoststate.FOREIGN, hoststate.SHARED}


def test_editing_ours_keeps_the_previous_copy(data_home):
    path = hoststate.mime_path("Alpha")
    our_mime(path, "Alpha")
    before = path.read_text()
    art = next(a for a in hoststate.artifacts_for("Alpha") if a.kind == "mime")
    kept = hoststate.write(art, "<mime-info/>\n")
    assert path.read_text() == "<mime-info/>\n"
    assert kept.exists() and kept.read_text() == before


def test_editing_a_foreign_artifact_is_refused_until_asked_for(data_home):
    path = hoststate.applications_dir() / "Affinity.desktop"
    path.write_text("[Desktop Entry]\nExec=/bin/true\n")
    art = next(a for a in hoststate.foreign_artifacts() if a.path == path)
    with pytest.raises(hoststate.NotOurs):
        hoststate.write(art, "broken")
    assert path.read_text().startswith("[Desktop Entry]")      # untouched
    hoststate.write(art, "[Desktop Entry]\nExec=/bin/false\n", force=True)
    assert "false" in path.read_text()


def test_deleting_keeps_a_copy_aside(data_home):
    path = hoststate.icon_path("Alpha")
    path.write_text("<svg/>")
    art = next(a for a in hoststate.artifacts_for("Alpha") if a.kind == "icon")
    kept = hoststate.delete(art)
    assert not path.exists()
    assert kept.exists() and kept.read_text() == "<svg/>"


def test_deleting_a_foreign_artifact_is_refused_until_asked_for(data_home):
    path = hoststate.applications_dir() / "Affinity.desktop"
    path.write_text("[Desktop Entry]\n")
    art = next(a for a in hoststate.foreign_artifacts() if a.path == path)
    with pytest.raises(hoststate.NotOurs):
        hoststate.delete(art)
    assert path.exists()
    assert hoststate.delete(art, force=True).exists() and not path.exists()


def test_a_shared_handler_cannot_be_edited_as_a_file(data_home):
    art = hoststate.Artifact("default-handler", None, hoststate.SHARED, None, "af -> x")
    for call in (lambda: hoststate.read(art),
                 lambda: hoststate.write(art, "x"),
                 lambda: hoststate.delete(art)):
        with pytest.raises(ValueError):
            call()


# ----------------------------------------------------------------------------
# The document association. One global value, so changing it always takes it
# away from somebody -- the plan has to say from whom before anything is called.


def test_handover_plan_names_both_sides(data_home):
    apps = hoststate.applications_dir()
    losing = apps / "affinity-manager-working-launch.desktop"
    losing.write_text(f"[Desktop Entry]\nExec=/bin/true\n{desktopentry.MARKER}=Working\n")
    handlers = [hoststate.Artifact("default-handler", None, hoststate.SHARED,
                                   None, "", value=losing.name)]
    plan = hoststate.plan_handover("3.3 Test", "Launch", handlers=handlers)
    assert plan.from_prefix == "Working" and plan.to_prefix == "3.3 Test"
    assert "Working" in plan.summary and "3.3 Test" in plan.summary
    assert not plan.foreign_current


def test_handover_plan_says_so_when_the_current_handler_is_not_ours(data_home):
    apps = hoststate.applications_dir()
    (apps / "Affinity.desktop").write_text("[Desktop Entry]\nExec=/bin/true\n")
    handlers = [hoststate.Artifact("default-handler", None, hoststate.SHARED,
                                   None, "", value="Affinity.desktop")]
    plan = hoststate.plan_handover("3.3 Test", "Launch", handlers=handlers)
    assert plan.foreign_current and plan.from_prefix is None
    assert "did not create" in plan.summary


def test_handover_refuses_when_the_entry_does_not_exist(data_home):
    """Pointing the desktop at a .desktop that is not there gives you documents
    that silently do not open."""
    plan = hoststate.plan_handover("Ghost", "Launch", handlers=[])
    with pytest.raises(FileNotFoundError):
        hoststate.apply_handover(plan)


def test_handover_calls_xdg_mime_once_per_type(data_home, monkeypatch):
    apps = hoststate.applications_dir()
    entry = apps / desktopentry.entry_path("Alpha", "Launch").name
    entry.write_text(f"[Desktop Entry]\nExec=/bin/true\n{desktopentry.MARKER}=Alpha\n")
    calls = []

    class Done:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(hoststate.subprocess, "run",
                        lambda cmd, **k: calls.append(cmd) or Done())
    monkeypatch.setattr(hoststate.desktopentry, "refresh_menu", lambda: None)
    plan = hoststate.plan_handover("Alpha", "Launch", handlers=[])
    assert hoststate.apply_handover(plan) == []
    assert len(calls) == len(hoststate.DOCUMENT_TYPES)
    assert all(c[:2] == ["xdg-mime", "default"] for c in calls)
    assert {c[3] for c in calls} == set(hoststate.DOCUMENT_TYPES)
