# Affinity on Linux Manager

Run Affinity on Linux, and keep several installs side by side: a working
install you cannot afford to break, plus a copy to try a new Wine build or
Affinity release in, backups before an upgrade, or a test copy of a client's
setup.

```bash
curl -sSL https://github.com/jfacemyer/Linux-Affinity-Manager/raw/main/AffinityManager/run.py | python3
```

That starts the manager straight from this repository. It needs Python 3.10 or
newer and PyQt6, and installs nothing on your system.

![The manager's window: two prefixes, one of them the Default](/AffinityManager/docs/manager-window.png)

## What it does

- **New prefix** sets up an Affinity install in its own Wine prefix, through
  **Setup**: the Affinity on Linux installer, run as a page of the manager's
  window. You get Wine with the Affinity patches, the Windows components,
  Affinity itself, GPU rendering, Help, and WineFix.
- **The Default**: choose which install your application menu, double-clicked
  Affinity documents and the Canva sign-in use. Other installs can have menu
  entries of their own.
- **Launch** never starts Affinity twice in one prefix.
- **Back up, restore, clone and snapshot** installs, and copy settings and
  drive letters from one to another.
- **Repairs and tidying**: fonts, the renderer setting, old Wine builds,
  renaming and moving installs, removing them cleanly.
- **One operation at a time** across all installs, with a log for each.

The full guide is the [manager's README](/AffinityManager/README.md).

## Just one Affinity?

The installer also runs on its own. It sets up one Affinity, with the menu
entry, document double-click and Canva sign-in pointing at it:

```bash
curl -sSL https://github.com/jfacemyer/Linux-Affinity-Manager/raw/main/AffinityScripts/AffinityLinuxInstaller.py | python3
```

See the [installer's README](/README.md) for what it sets up, supported
distributions, dependencies and known issues.

## About this repository

This is a fork of
[ryzendew/Linux-Affinity-Installer](https://github.com/ryzendew/Linux-Affinity-Installer)
with the Affinity 3.3 work: Wine builds with the Affinity patches, opening
documents from the file manager, the plugin loader with its newest fixes, and
the manager. The installer's README is the one at the top of the repository.

Affinity is a commercial product of Serif (Europe) Ltd; you need your own
license to install it. This project is not affiliated with Serif or Canva.
