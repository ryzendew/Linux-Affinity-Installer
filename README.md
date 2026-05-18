# Affinity Linux Fixes: OpenCL GPU Acceleration + Canva OAuth Login

Patches and scripts enabling full OpenCL hardware acceleration and Canva/OAuth
sign-in for Affinity Suite v3.2 under Wine (ElementalWarriorWine 11.0).

Tested on EndeavourOS (Arch) with AMD RX 9070 XT + Ryzen 7 7800X3D.
The Wine OpenCL patch uses only standard OpenCL 1.1 API. Tested on AMD ROCm;
should work with NVIDIA and Intel (Mesa Rusticl / compute-runtime) but
untested on those vendors.

## Issues Resolved

These patches resolve two entries previously in `docs/Known-issues.md`:

- **"AMD/Intel GPU OpenCL Issues"** -- fixed on AMD with the Wine
  clSetEventCallback patch + libraster binary patches. Intel untested but
  uses the same standard OpenCL 1.1 API.

- **"Login/Authentication Issues"** -- fixed with the TLS relay + IL patch +
  named pipe IPC.

Also fixes OpenCL rendering corruption (tiled artifacts, blank regions when
using GPU-accelerated filters) caused by Wine's stubbed clSetEventCallback.

## What's Included

### OpenCL GPU Acceleration

| Component | Location | Purpose |
|-----------|----------|---------|
| Wine clSetEventCallback | `Patch/OpenCLEventCallback/` | Implement missing OpenCL callback API (fixes rendering corruption) |
| libraster.dll patcher | `AffinityScripts/AffinityOpenCLPatch.sh` | Bypass DXGI/D3D10/D3D12 device discovery stubs |
| GPU_DEVICE_ORDINAL | Environment variable | Hide APU iGPU on dual-GPU AMD systems |

See [docs/OPENCL-ACCELERATION.md](docs/OPENCL-ACCELERATION.md) for details.

### Canva OAuth Login

| Component | Location | Purpose |
|-----------|----------|---------|
| TLS relay | `AffinityScripts/AffinityTLSRelay.sh` | Bridge Wine-Mono's legacy TLS to modern ECDHE ciphers |
| IL patcher | `Patch/SharedStorageAccessManagerFix/` | Bypass WinRT TypeLoadException in ProcessCommandLineArguments |
| Named pipe IPC | `Patch/SharedStorageAccessManagerFix/AffinitySendURL.cs` | Deliver OAuth callback URL without launching second instance |
| URL handler | `AffinityScripts/AffinityURLHandler.sh` | Desktop protocol handler for affinity:// URLs |

See [docs/CANVA-OAUTH-LOGIN.md](docs/CANVA-OAUTH-LOGIN.md) for details.

### Updated Documentation

| File | Changes |
|------|---------|
| `docs/Known-issues.md` | Removed AMD/Intel OpenCL and Login/Auth entries (now fixed). Added narrower "Intel GPU OpenCL Issues" entry (untested). Removed Canva from WebView2 impact list. |
| `docs/OpenCL-Guide.md` | Updated GPU compatibility (AMD tested, Intel untested). Added Steps 3-5 for Wine OpenCL patch, libraster patch, and env vars. Added troubleshooting for rendering corruption and APU+dGPU crashes. |

## Directory Structure

```
AffinityScripts/
  AffinityLinuxInstaller.py       Modified installer (new OpenCL + Canva buttons/methods)
  AffinityOpenCLPatch.sh          libraster.dll binary patcher
  AffinityTLSRelay.sh             TLS relay for OAuth
  AffinityURLHandler.sh           affinity:// protocol handler
  affinity-url-handler.desktop    XDG desktop entry template for URL handler

Patch/
  OpenCLEventCallback/            Wine clSetEventCallback implementation
    pe_wrappers.patch               Diff against upstream Wine
    pe_thunks.patch                 Diff against upstream Wine
    pe_wrappers.c                   Full patched source
    pe_thunks.c                     Full patched source
    prebuilt/opencl.dll             Pre-built x86_64 DLL
    README.md                       Build instructions
  SharedStorageAccessManagerFix/   IL patcher + OAuth IPC tool
    SharedStorageAccessManagerFix.cs
    SharedStorageAccessManagerFix.csproj
    AffinitySendURL.cs

docs/
  Known-issues.md                 Updated known issues
  OpenCL-Guide.md                 Updated OpenCL setup guide
  OPENCL-ACCELERATION.md          Technical details of OpenCL patches
  CANVA-OAUTH-LOGIN.md            Technical details of OAuth fixes
```

## Quick Start

### OpenCL GPU Acceleration

```bash
# 1. Install Wine OpenCL patch (one-time)
WINE_DIR="$HOME/.AffinityLinux/ElementalWarriorWine"
cp "$WINE_DIR/lib/wine/x86_64-windows/opencl.dll" "$WINE_DIR/lib/wine/x86_64-windows/opencl.dll.orig"
cp Patch/OpenCLEventCallback/prebuilt/opencl.dll "$WINE_DIR/lib/wine/x86_64-windows/opencl.dll"
cp Patch/OpenCLEventCallback/prebuilt/opencl.dll "$HOME/.AffinityLinux/drive_c/windows/system32/opencl.dll"

# 2. Patch libraster.dll (re-run after Affinity updates)
AffinityScripts/AffinityOpenCLPatch.sh
```

### Canva OAuth Login

```bash
# 3. Build IL patcher (one-time)
cd Patch/SharedStorageAccessManagerFix && dotnet build -c Release && cd ../..

# 4. Patch Serif.Affinity.dll (re-run after Affinity updates)
dotnet Patch/SharedStorageAccessManagerFix/bin/Release/net8.0/SharedStorageAccessManagerFix.dll \
    "$HOME/.AffinityLinux/drive_c/Program Files/Affinity/Affinity/Serif.Affinity.dll"

# 5. Set up TLS relay (one-time, requires sudo)
AffinityScripts/AffinityTLSRelay.sh setup

# 6. Build and install URL handler (one-time)
WINE="$HOME/.AffinityLinux/ElementalWarriorWine/bin/wine"
$WINE mcs -out:AffinityScripts/AffinitySendURL.exe \
    Patch/SharedStorageAccessManagerFix/AffinitySendURL.cs

SCRIPT_DIR="$(cd AffinityScripts && pwd)"
sed "s|PLACEHOLDER_SCRIPT_PATH|${SCRIPT_DIR}/AffinityURLHandler.sh|" \
    AffinityScripts/affinity-url-handler.desktop \
    > ~/.local/share/applications/affinity-url-handler.desktop
xdg-mime default affinity-url-handler.desktop x-scheme-handler/affinity
```

## Compatibility

These patches are for the **Python GUI installer** method (`AffinityLinuxInstaller.py`).
They are not compatible with the AppImage distribution, which bundles its own
Wine and wineprefix internally. AppImage integration would require rebuilding
the AppImage with the patched `opencl.dll` and scripts included.

## Dependencies

- ElementalWarriorWine 11.0
- .NET SDK 8.0+ (for building IL patcher)
- `python3` (for libraster binary patcher)
- `socat` (for TLS relay)
- `dig` (from `bind-tools` or `dnsutils`)
