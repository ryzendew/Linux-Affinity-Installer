"""What the manager should offer the first time it is opened.

Three situations, and they want different first sentences:

  MANAGED     The prefix list has entries. Nothing to ask; this is every run
              after the first.

  ADOPTABLE   No list yet, but there is an Affinity install on this machine --
              usually ~/.AffinityLinux, put there by AffinityOnLinux before the
              manager existed. The one thing that must not happen here is the
              manager quietly taking it over, or quietly moving it. Both are
              offered, separately, each saying what it would do.

  FRESH       No list and nothing found. Offer to make one.

The decision lives here rather than in the dialog because it is the part worth
testing: what gets offered on somebody's real machine, the first time, against
a prefix they have been using for a year.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import discover, maintenance, probe, registry

MANAGED = "managed"
ADOPTABLE = "adoptable"
FRESH = "fresh"


@dataclass
class Situation:
    state: str
    installs: list = field(default_factory=list)
    base: Path = None
    base_configured: bool = False

    @property
    def asks_anything(self) -> bool:
        return self.state != MANAGED


FIRST_RUN_DONE = "first_run_done"


def look(reg=None, *, search=True) -> Situation:
    """Decide which of the three this is.

    The search only happens when the list is empty, which is the first run, so
    the cost of walking a home directory is paid once and never again."""
    reg = reg or registry.Registry()
    base = registry.base_dir()
    configured = registry.base_dir_is_configured()

    if reg.entries:
        return Situation(MANAGED, [], base, configured)

    # Asked once. The registry going empty again -- forgetting the last prefix,
    # or removing it -- is not a first run, and re-arming the search every time
    # it happens would mean an unasked-for machine-wide walk whenever somebody
    # tidies up.
    from . import settings

    if settings.get(FIRST_RUN_DONE):
        return Situation(MANAGED, [], base, configured)

    installs = [i for i in discover.find_installations()] if search else []
    # Anything already managed is not adoptable, and with an empty list there
    # should be none -- but the search reads the registry itself, so a race or
    # a hand-edited file should not produce an offer to adopt what is held.
    installs = [i for i in installs if not i.get("managed_as")]
    # And it has to have Affinity in it. discover now reports every Wine
    # prefix, which is right for "Find installations" -- the user went looking,
    # and an interrupted install is exactly what they need to see. It is wrong
    # here: this is an unasked-for modal on somebody's first run, and offering
    # to MOVE ~/.wine while calling it "an Affinity install" is both untrue and
    # the kind of thing this application must never do.
    installs = [i for i in installs if i.get("has_affinity")]
    if installs:
        return Situation(ADOPTABLE, installs, base, configured)
    return Situation(FRESH, [], base, configured)


# ── what each choice would do, in words ──────────────────────────────────────
#
# The user asked for these to be offered and acted on separately, with clear
# explanations of what would take place. So the explanation is built from the
# same facts the action uses, rather than written once in a dialog and left to
# drift away from what the code does.


def explain_in_place(install) -> list[str]:
    path = Path(install["path"])
    return [
        f"{path} stays exactly where it is.",
        "Nothing inside it is read, written or moved.",
        "The manager records its location, so it appears in the list and can "
        "be launched, cloned, cleaned and backed up from here.",
        "Every launcher and menu entry you already have keeps working, because "
        "nothing they name has changed.",
    ]


def mark_asked() -> None:
    """Record that the first-run offer has been made, whatever came of it."""
    from . import settings

    settings.set(FIRST_RUN_DONE, True)


def explain_move(install, name, base=None, size=None) -> list[str]:
    """`size`, when the caller already measured it.

    Without it this walks the whole prefix, and the caller is a dialog that
    re-renders on every keystroke in the name field -- so a several-gigabyte
    du ran per character typed."""
    src = Path(install["path"])
    dest = Path(base or registry.base_dir()) / registry.dir_name(name)
    lines = [f"{src} is moved to {dest}."]
    try:
        plan = maintenance.plan_relocate(src, dest, size=size)
    except (maintenance.NotAPrefix, maintenance.DestinationInUse,
            maintenance.NotEnoughSpace) as exc:
        lines.append(f"This cannot be done right now: {exc}")
        return lines

    if plan.same_filesystem:
        lines.append(
            "Both paths are on the same filesystem, so this is a rename: "
            "instant, and nothing is copied.")
    else:
        lines.append(
            f"They are on different filesystems, so about "
            f"{probe.human_size(plan.size)} has to be copied. The original is "
            f"left in place afterwards; removing it is a separate decision.")

    if plan.launchers:
        lines.append(
            "These name the old path and would be updated, with a copy of each "
            "kept beside it: " + ", ".join(f.name for f in plan.launchers) + ".")
    else:
        lines.append(
            "No launcher or desktop entry names the old path, so there is "
            "nothing to update. If you start it some other way, that will need "
            "changing by hand.")
    return lines


# ── acting on it ─────────────────────────────────────────────────────────────


def adopt_in_place(reg, install, name) -> dict:
    """Record an existing prefix without touching it."""
    return reg.add(name, install["path"])


def adopt_by_moving(reg, install, name, *, base=None, progress=None,
                    remove_source=False) -> tuple[dict, list[str]]:
    """Move an existing prefix under the base directory and record it there.

    Ordered so that a failure leaves the truth on disk rather than in the list:
    the move happens first, the launchers follow it, and only then is anything
    written to the registry. A registry entry pointing at a move that did not
    happen would be worse than no entry at all."""
    src = Path(install["path"])
    dest = Path(base or registry.base_dir()) / registry.dir_name(name)
    plan = maintenance.plan_relocate(src, dest)
    notes = maintenance.relocate(plan, progress=progress,
                                 remove_source=remove_source)
    notes += maintenance.repoint_launchers(src, dest)
    entry = reg.add(name, dest)
    return entry, notes
