# Why the WinRT metadata has to be fixed last

Symptom: a completed install where double-clicking a document silently does
nothing. Affinity opens, or is already open, and the document never arrives.

## What is wrong in the prefix

`drive_c/windows/system32/WinMetadata` holds two sets of metadata at once:

```
Windows.winmd                       7.3 MB   Microsoft's combined metadata
windows.applicationmodel.winmd               Wine's ten per-namespace files
windows.globalization.winmd   … (10 files)
```

The ten shadow the combined file rather than supplementing it.
`RoResolveNamespace` resolves a namespace by walking it up —
`Windows.Storage.Streams`, then `Windows.Storage`, then `Windows` — and returns
the **first** file that exists. With `windows.storage.winmd` present it never
reaches `Windows.winmd`, so Affinity resolves against Wine's own
widl-generated metadata and fails with `TypeLoadException` when handed a
document.

A prefix with both sets therefore behaves exactly like a prefix with no
combined metadata at all.

## Why clearing them once is not enough

The ten are not a leftover. They are part of Wine, listed in `loader/wine.inf`:

```ini
[WinmdFiles]
windows.applicationmodel.winmd
…
[DestinationDirs]
WinmdFiles = 11,winmetadata        ; system32\winmetadata
```

referenced from `[BaseInstall]` and `[BaseWow64Install]`, which `wineboot`
re-runs through `InstallHinfSection DefaultInstall` on **every prefix update**.
The Wine build ships all ten in `share/wine/winmd/`.

So anything that boots the prefix — a Wine version change, winetricks,
installing .NET, the Affinity installer itself — copies all ten straight back.

Clearing them during Wine setup and stopping there produces an install that
looks complete and is broken, which is what shipped: `install_combined_winmetadata()`
runs inside `setup_wine()`, and every later step undoes it.

## Where the clearing now happens

`clear_shadowing_winmds()` is the single implementation, called from three
places:

1. `install_combined_winmetadata()` — so installing the metadata leaves a
   correct directory, and so the action can repair a prefix.
2. **The end of `run_installation()`**, after the plugin loader install, which
   is the last step that can boot the prefix. This is the one that matters.
3. `install_file_manager_handler()` — the feature that depends on it, so the
   repair action is self-sufficient rather than trusting whatever ran earlier.

It refuses to move anything when `Windows.winmd` is absent: without it, removing
the ten would leave the prefix with no WinRT metadata at all, which is worse
than the wrong metadata. Files are moved to `.wine-shadowed/` rather than
deleted — they are Wine's, not ours.

## Checking a prefix by hand

```sh
ls ~/.AffinityLinux/drive_c/windows/system32/WinMetadata
```

`Windows.winmd` alone is correct. `Windows.winmd` plus lowercase
`windows.*.winmd` files is the broken state; run **File Manager Integration**
in the installer to repair it.
