# Known Issues ⚠️

This document lists known issues and their workarounds. For the latest updates, check the [GitHub Issues](https://github.com/ryzendew/AffinityOnLinux/issues) page.

## Application Crashes

### Crash After Affinity Window Appears
**Issue:** Some users report that the application crashes immediately after the Affinity window is displayed.

**Status:** Open ([#89](https://github.com/ryzendew/AffinityOnLinux/issues/89))

**Workaround:**
- Try the other Wine version (11.18 / 11.19)
- Check GPU drivers are up to date
- Use vkd3d-proton or DXVK instead of OpenCL (see [Hardware Acceleration](HARDWARE-ACCELERATION.md))

### Startup Crash in Font Layout (Tahoma)
**Issue:** Affinity v3 exits during startup, or shortly after the window appears, with `System.Environment.FailFast` ("Unrecoverable system error") raised from `MS.Internal.Shaping.TypefaceMap.MapUnresolvedCharacters`. The exit code is `-2146232797`.

**Cause:** The native Tahoma font installed by the winetricks `tahoma` verb. The bundled Wine build already ships its own Tahoma.

**Workaround:** Build the prefix without the `tahoma` verb. On Ubuntu 26.04 (RTX 3070 laptop), moving the Tahoma files out of `drive_c/windows/Fonts` let an existing prefix start, but it still crashed intermittently with the same stack. A clean prefix built with only `remove_mono vcrun2022 dotnet48 corefonts win11` has not shown the crash across dozens of launches.

### AppImage 3.2.0 Crashes at Launch (UriFormatException)
**Issue:** The 3.2.0 AppImage sets up the prefix and then exits before any window appears with `System.UriFormatException: Invalid URI: The format of the URI could not be determined.`, raised from `MS.Internal.FontCache.Util.CombineUriWithFaceIndex` via `System.Windows.Media.Typeface.get_Symbol()`.

**Status:** Open ([Discussion #173](https://github.com/ryzendew/Linux-Affinity-Installer/discussions/173))

**Cause:** The AppImage copies its bundled prefix into `~/.affinity-appimage-wineprefix` and skips every drive letter except `c:`, including `z:`. Wine only creates `z:` for a new prefix, so the copied prefix never gets one. Without `z:`, Wine passes font paths to WPF as `\??\unix\...`, which WPF cannot parse as a URI. This includes the `Symbol` font bundled with the AppImage itself, so hiding system fonts through fontconfig does not reliably help.

**Workaround:** Create the missing `z:` drive and start the AppImage again. Wine then registers the fonts with `Z:\` paths:
```bash
ln -s / "$HOME/.affinity-appimage-wineprefix/dosdevices/z:"
```

### White or Blank Welcome Window
**Issue:** The main window renders correctly, but the Welcome (Home) window is white, showing only a plain "Home" button and sometimes the tutorial cards. New dialogs can also flash white before drawing.

**Cause:** The Direct3D 9 path that WPF (the Affinity UI toolkit) uses. The bundled Wine build uses the wined3d Vulkan renderer for d3d9, and the Welcome window, which is a transparent layered window, does not render through it. Ruled out by testing: the GPU (same result on AMD and NVIDIA), the Windows theme, DPI, the Affinity profile, launcher environment variables, and network access.

**Workaround:** Use DXVK for d3d9 only. Copy `x64/d3d9.dll` from a [DXVK release](https://github.com/doitsujin/dxvk/releases) into the Affinity install folder and add the override `d3d9=n,b`:
```bash
cp dxvk-*/x64/d3d9.dll "$HOME/.AffinityLinux/drive_c/Program Files/Affinity/Affinity/"
WINEDLLOVERRIDES="d3d9=n,b" wine "$HOME/.AffinityLinux/drive_c/Program Files/Affinity/Affinity/Affinity.exe"
```
A slower alternative is to force WPF software rendering:
```bash
WINEPREFIX="$HOME/.AffinityLinux" wine reg add 'HKCU\Software\Microsoft\Avalon.Graphics' /v DisableHWAcceleration /t REG_DWORD /d 1 /f
```
When DXVK provides d3d9, leave `DXVK_CONFIG` unset. `d3d9.deferSurfaceCreation = True` makes new windows such as Welcome and Settings render white (reproduced every time with it set, never with it unset), and `d3d9.shaderModel = 1` drops WPF below shader model 2, which makes the UI sluggish.

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

### Affinity Installer (SetupUI.exe) Crashes
**Issue:** The Affinity v3 setup program crashes under Wine with `Value cannot be null. Parameter name: icon` in `SetupUI.Util.GetShieldIcon`.

**Seen on:** Ubuntu 26.04, where the setup runs under the packaged Wine 10.0 and crashes this way. Its log is `drive_c/users/<user>/AppData/Local/Temp/AffinitySetup/<id>/SetupUI.log` in the prefix.

**What the installer does:** When the setup finishes without installing Affinity v3, the installer offers to install the MSI package embedded in `Affinity-x64.exe`. The setup window installs the same package. The installer uses `msiexec` and the prefix's own Wine. This needs `7z` and about 700 MB of temporary space in the prefix. The MSI install is logged to `affinity-msi.log` in the prefix (default `~/.AffinityLinux`). If it does not install Affinity, the installer stops with a message and runs none of the post-install steps. Tested with ElementalWarrior Wine 11.19, 7-Zip 26.00 and Affinity 3.3.0.4850.

**Workaround:** Canva also distributes Affinity as `Affinity x64.msix`, which is a zip archive. Extract its `App/` folder into the install location instead of running the setup program:
```bash
D="$HOME/.AffinityLinux/drive_c/Program Files/Affinity/Affinity"
mkdir -p "$D" && cd "$D"
unzip -q "$HOME/Downloads/Affinity x64.msix" 'App/*' && cp -a App/. . && rm -rf App
```

### Ubuntu 26.04: Dependency Installation Fails
**Issue:** The dependency step fails because Ubuntu 26.04 no longer has `p7zip-full` or `dotnet-sdk-8.0`, and apt aborts the whole install when one requested package is missing.

**Status:** Fixed. The installer now requests `7zip` when `p7zip-full` is unavailable, and only the .NET SDK versions that apt can actually install.

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

### Ubuntu Snapshot Launcher Resets the Profile or Forces NVIDIA
**Issue:** `AffinityUbuntuLauncher.sh` moved the v3 profile to `3.0.backup-*` and relaunched whenever startup took longer than 25 seconds, which is normal on a cold start. With AffinityPluginLoader installed it also never detected the main window, because the window belongs to `affinity.real.exe`. On hybrid laptops booted with the NVIDIA driver unloaded, it still forced NVIDIA-only Vulkan.

**Status:** Fixed. The startup timeout is now 180 seconds (`AFFINITY_STARTUP_TIMEOUT` overrides it), window detection matches both `affinity.exe` and `affinity.real.exe`, and NVIDIA offload is only applied when `/proc/driver/nvidia` exists (`AFFINITY_GPU=default` skips it). `AFFINITY_WINE` can point the launcher at a Wine build outside the prefix.

### UI Is Tiny With Fractional Scaling (GNOME Wayland)
**Issue:** At 125% or 133% scaling with Xwayland native scaling enabled, Wine windows get a 2x canvas and the Affinity UI renders at half size.

**Workaround:** Use the installer's "Set DPI Scaling" button, or set the DPI to 192 directly:
```bash
WINEPREFIX="$HOME/.AffinityLinux" wine reg add 'HKCU\Control Panel\Desktop' /v LogPixels /t REG_DWORD /d 192 /f
```

### Microsoft Edge WebView2: Help Window Is Empty
**Issue:** In Affinity v3 the Help window opens but stays empty. Affinity shows the Help with the Microsoft Edge WebView2 Runtime.

**Cause:** With `msedgewebview2.exe` set to Windows 11 compatibility, the WebView2 GPU process fails at startup and WebView2 stops with `GPU process isn't usable. Goodbye.`

**Fix:** The runtime is installed as Windows 11, and `msedgewebview2.exe` is then set to Windows 7 compatibility. Troubleshooting → "WebView2 Runtime (v3)" installs the runtime if it is missing and applies the WebView2 settings again if it is already installed. To set it by hand with the prefix's Wine:
```bash
WINEPREFIX="$HOME/.AffinityLinux" "$HOME/.AffinityLinux/ElementalWarriorWine/bin/wine" reg add 'HKCU\Software\Wine\AppDefaults\msedgewebview2.exe' /v Version /d win7 /f
```
Restart Affinity afterwards.

Tested with ElementalWarrior Wine 10.10, WebView2 Runtime 142.0.3595.94 and Affinity 3.3.0.4850 on Ubuntu 26.04. On Wine 11.19 with the same runtime, all WebView2 processes stay up as Windows 7 while its GPU processes die as Windows 11. Other WebView2 dialogs were not tested.

For the Canva sign-in, see [Login/Authentication Issues](#loginauthentication-issues).

### Login/Authentication Issues
**Issue:** After signing in to Canva in the browser, the `affinity://` callback never reaches Affinity v3, or Affinity crashes when it arrives.

**Cause:** Affinity handles the callback in `ProcessCommandLineArguments`, which the .NET runtime cannot compile without WinMetadata and `System.Runtime.WindowsRuntime`. `winetricks dotnet48` does not install the second one. Wine's generated `affinity://` handler also uses `wine start`, which crashes on URLs longer than about 300 characters (seen on older stock Wine builds).

**Fix:** For Affinity v3 the installer copies the WinRT facades from the .NET 4.8 offline installer into the prefix, then registers `affinity-url-handler.desktop` as the `affinity://` handler. It needs `7z` and about 350 MB of temporary space in the prefix. It downloads the .NET installer (about 70 MB) if the winetricks cache no longer has it. The handler is only registered when the prefix also has WinMetadata. Both Wine 11.18 and 11.19 carry the login metadata, so the fix applies on either. For an existing install, use **Troubleshooting → Fix Canva Sign-in (v3)**.

**Notes:**
- WineFix 0.3.0 patches out the Canva sign-in dialog. With WineFix 0.3.0, a forwarded `affinity://` URL no longer crashes the running Affinity. Sign-in was not tested with it.
- The installer replaces Wine's generated `wine-protocol-affinity.desktop`. It does not replace an `affinity://` handler from another setup (Bottles, Lutris). Check with `xdg-mime query default x-scheme-handler/affinity`.
- Affinity works offline without signing in.

## Wine Version Issues

### Wine 10.17 Bugs
**Issue:** Wine 10.17 has major bugs and issues.

**Workaround:** The installer does not use Wine 10.17. Use Wine 11.19 (recommended) or 11.18 (fallback). See [Wine Versions](WINE-VERSIONS.md) for details.

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

### Running a Prefix With a Different Wine Build
**Issue:** After launching a prefix even once with a different Wine build (for example the distribution's WineHQ package instead of the bundled ElementalWarrior build), Affinity may stop reaching its main window.

**Cause:** Wine updates the prefix in place the first time a different build uses it.

**Workaround:** Use one Wine build per prefix. If it already happened, recreate the prefix.

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
