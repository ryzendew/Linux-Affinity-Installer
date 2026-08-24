# Zorin OS Compatibility: Affinity Installer and Runtime

## Purpose

This document consolidates the installation and launch issues reproduced on Zorin OS 18.1 while installing Affinity v3 with the Affinity Linux Installer. It is intended to support a pull request, future regression testing, and end-user troubleshooting.

## Tested environment

| Component | Observed value |
|---|---|
| Distribution | Zorin OS 18.1 |
| GPU | Intel Raptor Lake-P Iris Xe |
| RAM | 15.2 GB |
| Wine prefix | `~/.AffinityLinux` |
| System Wine | Wine 10.0 (`Ubuntu 10.0~repack-6ubuntu1+zorin5`) |
| Legacy bundled Wine | ElementalWarrior Wine 11.12 |
| Active installer/runtime Wine | wine-tkg 11.16 staging, wow64 |
| Graphics path | Vulkan; OpenCL disabled for Intel |
| Affinity application | Unified Affinity v3 |

## Executive summary

The failure was not caused by one isolated incompatibility. Several independent installer and runtime defects occurred in sequence:

1. The Affinity installer was initially run with system Wine and its .NET/WPF `SetupUI.exe` crashed with exception `0xe0434352`.
2. The installer flow reported success without verifying that Affinity binaries were actually installed.
3. WebView2 detection did not recognize versioned installation directories.
4. GUI error dialogs passed `QMessageBox.Icon` values through a signal declared to accept strings.
5. Update buttons were disabled when an application was not already installed.
6. Generated desktop entries selected the legacy Wine build and launched the executable directly instead of using the active wine-tkg build with `start /unix`.
7. Most importantly, vkd3d-proton was downloaded and staged but its native `d3d12.dll` and `d3d12core.dll` files were not copied into the Wine prefix. Registry overrides forced those DLLs to `native`, causing Wine to reject its builtin DLL and report `d3d12.dll` as missing. This cascaded through Affinity's rendering libraries and caused the application to hang.

Reinstalling Affinity alone would not reliably solve these problems. The Wine prefix configuration and installer logic had to be repaired.

## Issue matrix

| Area | Symptom | Root cause | Resolution |
|---|---|---|---|
| Affinity installer | `SetupUI.exe` crashed with `0xe0434352` | Affinity installer used Zorin's system Wine instead of the selected wine-tkg runtime | Use `get_wine_tkg_for_installer()` for Affinity and WebView2 installer execution |
| Success reporting | Installer displayed completion while app directory was empty | Process completion was treated as installation success | Verify `Affinity.exe` or `Serif.Affinity.dll` before reporting success or creating launchers |
| Diagnostics | Failures were difficult to distinguish from successful short runs | Exit code, elapsed time, and complete installer output were not retained | Capture streaming return code and installer output |
| GUI messages | Error dialogs raised a signal type exception | Signal expected strings but call sites passed `QMessageBox.Icon` values | Pass `"warning"`, `"error"`, or `"info"` |
| Update controls | Uninstalled apps could not be selected for update/install | Buttons required both Wine and an existing installation | Enable controls when a usable Wine runtime exists |
| WebView2 | Installed runtime was reported missing | Detection only checked `Application/msedgewebview2.exe` | Search versioned `Application/<version>/msedgewebview2.exe` directories |
| Desktop entries | Menu launch used obsolete Wine and hung | Desktop writers called `get_wine_path("wine")` and invoked the EXE directly | Use active wine-tkg selection and `wine start /unix` |
| Plugin loader | Launcher rewrites could bypass `AffinityHook.exe` | Separate desktop rewrite paths reconstructed inconsistent commands | Prefer `AffinityHook.exe` when present, otherwise `Affinity.exe` |
| Graphics runtime | `Affinity.exe` hung and was eventually killed with `rc=137` | Native d3d12 overrides existed, but vkd3d-proton DLLs were absent from the prefix system directories | Install x64 DLLs into `system32`, x86 DLLs into `syswow64`, and use `native,builtin` fallback |
| Wine selection | Setup logs referenced Wine 11.12 while parts of setup used wine-tkg 11.16 | Multiple Wine selectors were used for related operations | Use the selected Wine consistently for installation and launch paths |

## Failure chronology

### 1. Initial environment setup

System dependencies, wine-tkg 11.16, .NET, fonts, Visual C++ runtime, XML components, and Vulkan configuration were installed. The setup logs also exposed a Wine-version inconsistency: the UI reported ElementalWarrior Wine 11.12 as active while winetricks and later operations used wine-tkg 11.16.

A cache entry for Wine 11.12-v4 was also reported as successful despite the expected cache directory being absent. This was not the final launch blocker, but it made Wine selection harder to reason about.

### 2. Affinity installer crash and false success

The original app installation path selected system Wine. Affinity's `SetupUI.exe` failed with an unhandled CLR/WPF exception:

```text
wine: Unhandled exception 0xe0434352 ...
```

No app payload was written to:

```text
~/.AffinityLinux/drive_c/Program Files/Affinity/Affinity
```

Nevertheless, the installer continued into post-install actions and reported success. `Serif.Affinity.dll` was missing, patching was skipped, and the final status still showed Affinity as not installed.

The installer must treat the presence of real artifacts as the success condition. A zero exit code, a debugger process, or a short-lived installer process is not sufficient evidence that installation completed.

### 3. WebView2 and UI secondary failures

The first WebView2 attempt encountered:

```text
MSASN1.dll.ASN1DEREncBeginBlk
```

A later attempt found WebView2 through registry state, but file detection still missed valid versioned installations. Detection now searches both 32-bit and 64-bit standard roots and their versioned subdirectories.

At the same time, attempts to display failure dialogs raised:

```text
show_message_signal[str, str, str].emit(): argument 3 has unexpected type 'Icon'
```

This hid useful error messages from the user and was corrected by passing string severity values.

### 4. Desktop launcher regeneration failure

After Affinity was installed, installer actions could regenerate `Affinity.desktop` with two regressions:

- the legacy ElementalWarrior Wine path;
- direct executable invocation.

On this system, direct invocation behaved as follows:

```text
wine ".../Affinity.exe"                 -> hangs, later killed, rc=137
wine start /unix ".../Affinity.exe"     -> returns rc=0
```

The launcher must use the same selected Wine runtime as the installer:

```text
Exec=env WINEPREFIX=<prefix> <selected-wine> start /unix "<linux-exe-path>"
```

All desktop creation and GPU/backend rewrite paths must preserve this format. The unified launcher must target `AffinityHook.exe` when the plugin loader is installed and fall back to `Affinity.exe` otherwise.

### 5. Final runtime blocker: broken vkd3d-proton installation

Correcting the launcher exposed a deeper graphics failure. Wine debug output repeatedly reported:

```text
Library d3d12.dll (which is needed by libdxcore.dll) not found
```

The error then cascaded through:

```text
libdxcore.dll
  -> libraster.dll
  -> librenderer.dll / libStory.dll / libpsd.dll
  -> libpersona.dll
  -> Affinity startup failure
```

The prefix contained files named `d3d12.dll` and `d3d12core.dll`, but they were Wine builtin modules. The registry forced:

```text
"d3d12"="native"
"d3d12core"="native"
```

Wine will not satisfy a native-only override with its builtin module. The actual vkd3d-proton DLLs existed under the installer cache but had only been copied to a staging directory and a Wine installation library directory. They were never installed into the prefix locations used by native DLL lookup.

The working installation is:

| Architecture | vkd3d-proton source | Prefix destination |
|---|---|---|
| 64-bit | `vkd3d-proton-<version>/x64/*.dll` | `drive_c/windows/system32/` |
| 32-bit | `vkd3d-proton-<version>/x86/*.dll` | `drive_c/windows/syswow64/` |

The safer overrides are:

```text
"d3d12"="native,builtin"
"d3d12core"="native,builtin"
```

This loads vkd3d-proton when correctly installed while avoiding a complete dependency failure if a native DLL is unavailable.

## Implemented code behavior

The installer now includes or is expected to include the following behavior:

- Select wine-tkg through `get_wine_tkg_for_installer()` for Affinity and WebView2 installers.
- Put the selected Wine binary directory first in `PATH` so helper processes use the same runtime.
- Record streaming command return codes, elapsed runtime, and detailed Affinity installer output.
- Verify installed artifacts before reporting success.
- Detect WebView2 executables inside versioned installation directories.
- Generate and rebuild desktop entries with the selected Wine runtime and `start /unix`.
- Preserve `AffinityHook.exe` preference for the plugin-loader path.
- Locate cached x64 and x86 vkd3d-proton DLLs.
- Back up existing prefix d3d12 files before replacement.
- Copy x64 DLLs into `system32` and x86 DLLs into `syswow64`.
- Configure d3d12 overrides as `native,builtin`.

Primary implementation areas in `AffinityScripts/AffinityLinuxInstaller.py` include:

- `verify_affinity_artifacts`
- `_run_installer_and_capture`
- `update_existing_desktop_entries`
- `install_d3d12_dlls`
- `_find_vkd3d_dll_sources`
- `install_vkd3d_dlls_to_prefix`
- `setup_d3d12_overrides`
- `_find_webview2_executable`
- `create_desktop_entry`
- `launch_affinity_v3`
- `_build_affinity_exec_line`

## Validation results

The repaired prefix was validated with the following outcomes:

- Python syntax validation passed:

```bash
python3 -m py_compile AffinityScripts/AffinityLinuxInstaller.py
```

- The desktop entry uses wine-tkg and `start /unix`:

```text
Exec=env WINEPREFIX=/home/blade/.AffinityLinux /home/blade/.AffinityLinux/wine-tkg/wine-11.16-staging-tkg-amd64-wow64/bin/wine start /unix "/home/blade/.AffinityLinux/drive_c/Program Files/Affinity/Affinity/Affinity.exe"
```

- The x64 vkd3d-proton DLL sizes in `system32` matched the cached x64 sources.
- The x86 vkd3d-proton DLL sizes in `syswow64` matched the cached x86 sources.
- `d3d12` and `d3d12core` registry values were verified as `native,builtin`.
- The exact desktop command returned `rc=0`.
- `Affinity.exe` remained running after 5, 15, and 30 seconds.
- The prior `Library d3d12.dll ... not found` error disappeared.

## Pull request scope and rationale

### Problem solved

Zorin OS users could complete setup yet receive a missing application, a broken launcher, or an Affinity process that hung during startup. Reinstalling could reproduce the same state because the root defects were in Wine selection, success validation, launcher regeneration, and vkd3d-proton placement.

### User impact

- Failed installs are no longer reported as successful.
- Error dialogs display correctly.
- Existing WebView2 installations are recognized.
- Launchers consistently use the tested Wine runtime and reliable invocation form.
- Affinity's D3D12 dependency chain can load correctly from the prefix.
- Plugin-loader launch behavior is preserved.

### Suggested PR summary

- Make Affinity installation and launcher generation consistently use the selected wine-tkg runtime, and reject false-positive installations when required app files are absent.
- Install vkd3d-proton DLLs into the Wine prefix with safe overrides so Affinity's D3D12 rendering dependencies load reliably on Zorin OS.

## Regression checklist

Before merging, test on at least one supported distribution and verify:

1. A fresh unified Affinity install creates `Affinity.exe` or `Serif.Affinity.dll` before reporting success.
2. A deliberately failed installer does not create a desktop entry or show a success dialog.
3. `Affinity.desktop` uses the selected wine-tkg path and `start /unix`.
4. `AffinityHook.exe` is selected when installed.
5. Photo, Designer, and Publisher desktop entries still point to their correct executable paths.
6. GPU/backend switching does not rewrite launchers back to legacy Wine or direct invocation.
7. `system32/d3d12.dll` and `system32/d3d12core.dll` are the x64 vkd3d-proton files.
8. `syswow64/d3d12.dll` and `syswow64/d3d12core.dll` are the x86 vkd3d-proton files.
9. Registry overrides are `native,builtin`.
10. Affinity remains running for at least 30 seconds after launch.
11. WebView2 is detected in a versioned directory.
12. `python3 -m py_compile AffinityScripts/AffinityLinuxInstaller.py` passes.

## End-user recovery guidance

Do not recommend reinstalling Affinity as the first action when the executable exists. First determine whether the failure is installation, launcher selection, or graphics runtime configuration:

1. Confirm `Affinity.exe` exists.
2. Inspect the desktop `Exec=` line.
3. Confirm the selected Wine binary runs.
4. Capture Wine errors and look specifically for the first missing dependency.
5. Verify vkd3d-proton DLL architecture and placement.
6. Verify DLL overrides.
7. Reinstall only if the Affinity payload itself is missing or corrupt after the installer path has been corrected.

## Source diagnostic documents

This compatibility report consolidates:

- `logs/INSTALL_DEBUG_SUMMARY.md`
- `logs/AFFINITY_V3_INSTALL_DEBUG_2026-08-24.md`
- `logs/AFFINITY_V3_STATUS_2026-08-24.md`
- `logs/ZORIN_OS_INSTALLER_ISSUE_PROMPT_2026-08-24.md`
- Runtime diagnostics performed on 2026-08-24 after the launcher fix
