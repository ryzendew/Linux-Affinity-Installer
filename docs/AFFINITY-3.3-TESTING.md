# Testing Affinity 3.3

Affinity 3.3 was published on **2026-09-15**. This branch exists to make trying
it safe, not to make it possible — it was already possible, which is the
problem.

## The installer has no version pinning

`downloads.affinity.studio/Affinity%20x64.exe` is version-less. It serves
whatever the current release is:

```
$ curl -sI 'https://downloads.affinity.studio/Affinity%20x64.exe'
content-length: 673188936
last-modified: Tue, 15 Sep 2026 10:00:39 GMT
```

Nothing in the installer records or requests a version. So as of this morning,
every fresh install and every use of Update takes 3.3, with no opt-out and no
way back — unless someone happened to keep the previous installer, because
there is no URL that serves it.

**Keep the installer for any version you may want to return to.** It is the
only rollback that exists. The installer's *Provide my own installer file*
option reinstalls from a kept copy, and `AFFINITY_INSTALLER_FILE` does the same
without a dialog.

## What this branch adds

Two environment variables, also settable as `--install-dir` and
`--installer-file`:

| Variable | Effect |
|---|---|
| `AFFINITY_INSTALL_DIR` | install into this directory, verbatim, instead of `~/.AffinityLinux` |
| `AFFINITY_INSTALLER_FILE` | install from this `.exe` instead of downloading the current release |

Together they make a side-by-side test possible: 3.3 into a new prefix, the
working install untouched.

## Testing 3.3 without risking a working install

```sh
AFFINITY_INSTALL_DIR=~/.AffinityLinux-3.3 python3 AffinityScripts/AffinityLinuxInstaller.py
```

Or through [Affinity on Linux Manager](../AffinityManager/README.md),
which was written for this and keeps track of the prefixes afterwards.

To put a known version back:

```sh
AFFINITY_INSTALL_DIR=~/.AffinityLinux \
AFFINITY_INSTALLER_FILE=~/installers/Affinity-x64-3.2.3.4646.exe \
  python3 AffinityScripts/AffinityLinuxInstaller.py
```

## Version assumptions that were checked and left alone

Affinity's per-user settings live under
`AppData/Roaming/Affinity/Affinity/3.0/`, where `3.0` is the schema version for
the whole of Affinity v3 — 3.2.3 uses it, and 3.3 is expected to as well. The
installer prefers whatever version folder already exists and only falls back to
`3.0`, so it does not need changing unless 3.3 turns out to introduce a new one.
Worth confirming on a first 3.3 install: if a different folder appears beside
`3.0`, the settings-migration step needs revisiting.

## Still to confirm on 3.3

- whether the WinRT metadata work still applies unchanged
- whether AffinityPluginLoader and WineFix load against it
- whether the file-manager handler still opens documents
- whether the settings schema folder is still `3.0`
