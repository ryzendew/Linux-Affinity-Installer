# Real separation between prefixes

What the manager has to own so that installing, updating or removing one prefix
cannot disturb another. Written before the code, from the state actually on this
machine on 2026-09-17.

## What exists on the host today

Verified, not assumed.

| Artifact | Naming | Per-prefix? |
|---|---|---|
| `~/.local/share/applications/Affinity.desktop` | **fixed** | **no** — rewritten by every AoL install, `Exec` pointing at whichever prefix went last |
| `~/.local/share/applications/Affinity-GPU.desktop` | fixed | no |
| `~/.local/share/applications/affinity-<prefix>-<command>.desktop` | per-prefix, tagged `X-AffinityManager-Prefix` | **yes** — the manager already does this |
| `~/.local/share/mime/packages/x-wine-extension-af{,design,photo,pub}.xml` | **fixed**, and shares winemenubuilder's scheme | **no** |
| `~/.local/share/icons/Affinity{,Designer,Photo,Publisher}.svg` | **fixed** | **no** |
| `xdg-mime default` for the four `application/af*` types | one global choice | **no** — points at `Affinity.desktop`, i.e. the last install |
| `~/.config/AffinityOnLinux/install_location` | single value | **no** |
| `~/AffinitySetup.log` | single file, append | **no** — 28MB here, and two installers writing to it once made one run look like a bug in the other |
| `~/.cache/affinity-launch.log` | single file | no — from the retired launcher |
| `~/.AffinityLinuxManager/Manager/prefixes.json` | the manager's registry | n/a |

On this machine `~/.local/share/mime/packages` holds our four alongside seven of
winemenubuilder's own `x-wine-extension-*.xml`. The collision is not theoretical.

Removal today is `shutil.rmtree(path)` plus dropping the registry row
(`AffinityLinuxManager.py:1817`, `registry.forget`). The menu entry, the MIME
packages, the icons and the document defaults are all left behind.

## Three rules

**1. Everything the manager writes is attributable to a prefix.** Desktop
entries already carry `X-AffinityManager-Prefix`; MIME packages get an XML
comment naming the prefix, icons get the prefix in the filename. Anything
without a marker belongs to somebody else.

**2. Nothing unattributable is ever modified or removed.** `desktopentry.is_ours`
is the model. Foreign artifacts are *reported* — so a removal plan can say "this
was not ours, left alone" — and never touched.

**3. A global choice is only ever changed by being asked for.** There is exactly
one default handler per MIME type, system-wide; it cannot be per-prefix. So
"which prefix opens Affinity documents" becomes an explicit, single setting the
user sets, not a side effect of whichever install ran last. Changing it away
from a prefix that currently holds it requires confirmation naming both.

## Naming

```
applications/affinity-<slug>-<command>.desktop     already implemented
mime/packages/affinity-<slug>-documents.xml        <!-- X-AffinityManager-Prefix: <name> -->
icons/affinity-<slug>.svg
```

`<slug>` comes from `registry.dir_name()`, which already validates and
normalises prefix names.

MIME *types* stay global — `application/afphoto` is an identity, not a per-prefix
thing, and duplicating it per prefix would make the desktop database ambiguous.
What is per-prefix is the handler, and that is rule 3.

## Where does the MIME association belong?

Asked as "should this be in the Launcher, since it's abstracted from prefixes?"
— and the answer decides the shape of the rest.

There is no host-side launcher any more, by design: the launcher scripts were
retired and `affinity-on-linux.exe` runs *inside* a prefix. And a dispatcher
that chooses *between* prefixes cannot live inside one, because the choice has
to be made before entering any. So "put it in the launcher" means bringing back
a host-side dispatcher process.

It is not needed. Each prefix already has its own named `.desktop`, so the
association can simply point at one of them:

```
xdg-mime default affinity-manager-<slug>-launch.desktop application/afphoto
```

That is better than a dispatcher on every axis that matters here. No extra
process. No runtime guessing about which prefix was meant. No fixed-name
`Affinity.desktop` in the picture at all, so nothing for the next install to
clobber. And the **desktop database itself records the choice**, so it survives
without the manager running — which a dispatcher would not.

So the split is:

| Decision | Owner |
|---|---|
| *which* prefix opens a document | the manager — the only component that knows more than one exists |
| *what happens* once inside a prefix | `affinity-on-linux.exe` — handoff, path conversion, reaping |

The manager owns it not because it is convenient but because it is the only
component with the information, and because it is a host management application
and therefore already outside the Wine-native rule. `plan_handover()` computes
what would change and names both prefixes; `apply_handover()` does it only after
that has been shown.

## Removal plan

**Built** — `affinity_manager/removal.py`, and `RemovalDialog`.

Same shape as `maintenance.Plan`: computed, shown, and only then executed. Every
row says what it is, where it is, how big it is, and why it is proposed.

| Category | Example | Default |
|---|---|---|
| `prefix` | the directory itself, with size | tick |
| `menu` | each `affinity-<slug>-*.desktop` we wrote | tick |
| `mime` | `affinity-<slug>-documents.xml` | tick |
| `icon` | `affinity-<slug>.svg` | tick |
| `default-handler` | the four `application/af*` defaults, **if** they point at this prefix | tick, and say what they revert to |
| `registry` | the row in `prefixes.json` | tick |
| `settings-backup` | snapshots taken from this prefix | **untick** — losing a backup with the thing it backs up is the wrong default |
| `foreign` | `Affinity.desktop`, winemenubuilder's MIME files | **not offered**, listed as "left alone, not ours" |

Nothing is removed without the list having been shown. The confirmation is the
list, not a yes/no on a summary.

## Settings snapshots

**Built** — `affinity_manager/snapshots.py`, and `SnapshotsDialog`.

A snapshot is the prefix's own configuration, not the prefix: the `Settings`
directory, plus the loose `.dat` files beside it and `sess.db`.

```
~/.AffinityLinuxManager/Manager/snapshots/<slug>/<stamp><-label>/
```

`<stamp>` is `YYYYmmdd-HHMMSS`; `<label>` is the optional name the user types.
Stored as a directory copy rather than an archive, so it can be inspected and
partially restored by hand.

Restoring into a prefix:

1. refuses if Affinity is running there (`maintenance._require_idle`)
2. **offers to snapshot the current settings first**, and defaults to yes
3. names both sides — "restore `2026-09-17-1830 before-3.3` into `Working`" —
   because restoring into the wrong prefix is the expensive mistake
4. writes to a temporary directory beside the target and renames into place, so
   an interrupted restore cannot leave half of one configuration and half of
   another

Restoring across prefixes is allowed and useful — it is how the settings from
the live prefix get into a test one — so the source snapshot records which
prefix it came from and the confirmation says when they differ.

## What this does not fix

The AoL installer still writes `Affinity.desktop` and still points the document
defaults at it. The manager can protect and restore around that, and report it,
but the installer is the thing that does the clobbering. Its own fix is to name
its entry per prefix; until then `Affinity.desktop` is `foreign` to the manager
and reported rather than managed.
