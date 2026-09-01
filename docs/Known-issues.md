# Known Issues ⚠️

This document lists known issues and their workarounds. For the latest updates, check the [GitHub Issues](https://github.com/ryzendew/AffinityOnLinux/issues) page.

## Application Crashes

### Crash After Affinity Window Appears
**Issue:** Some users report that the application crashes immediately after the Affinity window is displayed.

**Status:** Open ([#89](https://github.com/ryzendew/AffinityOnLinux/issues/89))

**Workaround:**
- Try a different Wine version (9.14 recommended for older systems)
- Check GPU drivers are up to date
- Use vkd3d-proton or DXVK instead of OpenCL (see [Hardware Acceleration](HARDWARE-ACCELERATION.md))

### Window Management Issues (Moving UI Elements Causes Crashes)
**Issue:** Moving or undocking any part of the Affinity UI causes the application to crash. Windows cannot be docked properly and undocked windows are unreliable.

**Status:** Open ([#108](https://github.com/ryzendew/Linux-Affinity-Installer/issues/108))

**Note:** This is a Wine/Windows compatibility limitation that cannot be fixed within the scope of this project. The issue stems from Wine's window management implementation not properly handling Affinity's complex UI layout system.

**Workaround:** Set your preffered Layout with docked panels on an existing Windows or Mac installation of Affinity Studio. Export the studio and import it on Affinity for Linux. The chosen layout will be adopted and can always be restored if a panel is moved by accident.

### AppImage Memory Issues (Excessive RAM Usage and Random Crashes)
**Issue:** The Affinity AppImage consumes unusually large amounts of RAM during normal usage and may randomly crash, affecting system stability.

**Status:** Open ([#106](https://github.com/ryzendew/Linux-Affinity-Installer/issues/106))

**Note:** This appears to be a random bug affecting the AppImage build. The issue occurs inconsistently and may be related to how the AppImage packages Wine and Affinity together.

**Workaround:**
- Use the Python GUI installer instead of AppImage for more stable performance
- Close other memory-intensive applications when using Affinity
- Save work frequently due to potential crashes

## Installation Issues

### GLIBC Version Error
**Issue:** `wine: could not load ntdll.so: /lib/x86_64-linux-gnu/libc.so.6: version 'GLIBC_2.38' not found`

**Workaround:** 
- Use the AppImage installer instead
- Update your system's GLIBC (may require system upgrade)
- Use a distribution with newer dependencies

### Wine mscoree.dll Error
**Issue:** `wine: could not load mscoree.dll`

**Workaround:**
- Reinstall Wine using the GUI installer
- Try a different Wine version
- Use the guide method instead of scripts

### Sudo Authentication Failing on Fingerprint-Enabled Systems
**Issue:** Sudo authentication fails when fingerprint authentication is enabled on the system.

**Status:** Open ([#68](https://github.com/ryzendew/AffinityOnLinux/issues/68))

**Workaround:**
- Temporarily disable fingerprint authentication during installation
- Use `sudo -i` to get a root shell before running the installer
- Configure sudo to use password authentication for the installer

## Distribution-Specific Issues

### Unsupported Distributions
**Issue:** Bazzite, Linux Mint, Zorin OS, Manjaro, Ubuntu, Pop!_OS, and Debian are not officially supported.

**Workaround for Debian/Ubuntu/Pop!_OS/Zorin OS/Linux Mint:** Install .NET 10 using [Microsoft's instructions](https://learn.microsoft.com/en-us/dotnet/core/install/linux-debian?tabs=dotnet10), then run the Python installer as normal.

**Workaround:** Use the [AppImage installer](../INSTALLATION.md#1-appimage-recommended-for-beginners) instead. See [System Requirements](SYSTEM-REQUIREMENTS.md) for details.

**Workaround:** Use the [AppImage installer](../INSTALLATION.md#1-appimage-recommended-for-beginners) instead.

### Read-Only Filesystem Support (SteamOS, Silverblue, etc.)
**Issue:** The installer may not work correctly on read-only filesystems like SteamOS or Silverblue.

**Status:** Open ([#10](https://github.com/ryzendew/AffinityOnLinux/issues/10))

**Workaround:**
- Use the AppImage installer
- Install to a writable location (user home directory)
- Use overlay filesystems if available

## Hardware Acceleration Issues

### AMD/Intel GPU OpenCL Issues
**Issue:** OpenCL may not work correctly on AMD and Intel GPUs.

**Workaround:** Use vkd3d-proton or DXVK instead of OpenCL. See [Hardware Acceleration](HARDWARE-ACCELERATION.md) for details.

**Note:** We cannot fix AMD/Intel GPU OpenCL issues as we do not have access to these GPUs for testing.

## Application Features

### Microsoft Edge WebView2 Runtime Not Working
**Issue:** The Microsoft Edge WebView2 Runtime is broken and does not work properly in Wine. This affects features in Affinity v3 that rely on WebView2, such as the Help system and some web-based dialogs.

**Status:** Known limitation - cannot be fixed

**Impact:**
- Help system in Affinity v3 may not work
- Some web-based dialogs may fail to load
- Canva sign-in dialog may not function properly

**Workaround:**
- Use the application's built-in help files if available
- Access documentation online instead of using in-app help
- This is a Wine limitation and cannot be resolved until Wine improves WebView2 support

**Note:** Do not open issues about WebView2 - this is a known limitation that cannot be fixed.

### Login/Authentication Issues
**Issue:** Logging into Affinity applications does not work properly. Authentication dialogs may fail or not function as expected.

**Note:** This is due to Wine's limited support for web-based authentication systems.

**Workaround:**
- Use Affinity applications without logging in (they work fully offline)
- If account features are needed, consider using the Windows version in a virtual machine

## Wine Version Issues

### Wine 10.17 Bugs
**Issue:** Wine 10.17 has major bugs and issues.

**Workaround:** The installer does not use Wine 10.17. Use Wine 10.10 (recommended) or 9.14 (legacy fallback). See [Wine Versions](WINE-VERSIONS.md) for details.

### Publisher Crashes on Stock Wine (BadImageFormatException / StoreLicense Error)

Issue: When setting up Affinity Publisher manually with a stock or staging build of Wine (rather than the ElementalWarrior fork this project's installer uses), Publisher shows its splash screen and then crashes. Depending on how far you got, the Wine log shows one of:

```
Unhandled Exception: System.BadImageFormatException: Format incorrect. (Exception from HRESULT: 0x8007000B)
```

or, after manually adding `wintypes.dll` and `Windows.winmd`:

```
Unhandled Exception: System.MissingMethodException: Method not found: 'Boolean Windows.Services.Store.StoreLicense.get_IsActive()'.
```

or:

```
Unhandled Exception: System.IO.FileNotFoundException: Could not load file or assembly 'Windows.Services.Store.StoreContract, ...'
```

Cause: stock Wine's `RoResolveNamespace` implementation (the built-in `wintypes` module, or the external `wintypes_shim.dll` some guides recommend) always resolves every WinRT namespace request to a single merged `Windows.winmd` file from the `windows-rs` project. That file doesn't fully implement `Windows.Services.Store`, which Publisher queries at startup for its store-license check. Photo and Designer don't hit this code path, so they can appear to work fine under stock Wine — which makes this limitation easy to miss until someone specifically tries Publisher.

Note: this is why this project uses the ElementalWarrior Wine fork instead of stock Wine — it resolves WinRT namespaces against the full `WinMetadata` folder rather than a single merged file. Anyone trying to reproduce Publisher support with a plain/staging Wine build outside this installer will hit this wall regardless of installer file (`.exe` vs `.msix`), dependency install order, or DLL overrides.

## Feature Requests

### Affinity Pen Path Fix
**Status:** Open ([#53](https://github.com/ryzendew/AffinityOnLinux/issues/53))

Request to add Affinity pen path fix to the Wine runner.

### Alternate Wine Builds
**Status:** Open ([#41](https://github.com/ryzendew/AffinityOnLinux/issues/41))

Discussion about using alternative Wine builds for improved compatibility.

## Getting Help

If you encounter an issue not listed here:

1. Check the [GitHub Issues](https://github.com/ryzendew/AffinityOnLinux/issues) page to see if it's already reported
2. Search existing issues for similar problems
3. Join the [Discord Community](https://discord.gg/DW2X8MHQuh) for support
4. Create a new issue with detailed information about your system and the problem
