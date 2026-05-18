# OpenCL Hardware Acceleration Guide

This guide explains how to set up OpenCL hardware acceleration for Affinity applications on Linux. OpenCL enables GPU-accelerated processing for improved performance in Affinity Photo, Designer, and Publisher.

## Prerequisites

- AffinityOnLinux installer has been run and Affinity applications are installed
- Your GPU drivers are properly installed
- You have administrator (sudo) access

## GPU Compatibility

**NVIDIA GPUs:** OpenCL support with proper driver installation. The patches use standard OpenCL 1.1 API and should work, but are untested on NVIDIA.

**AMD GPUs:** Full OpenCL support with ROCm drivers and the patches below. On systems with both an APU (integrated GPU) and a discrete GPU, set `GPU_DEVICE_ORDINAL=0` to hide the iGPU and prevent cross-device memory faults.

**Intel GPUs:** Should work via Mesa Rusticl or Intel compute-runtime with the patches below, but untested. Reports welcome.

## Installation

### Step 1: Install OpenCL Drivers

Install the appropriate OpenCL drivers for your GPU and distribution:

#### Arch Linux (NVIDIA)

```bash
sudo pacman -S opencl-nvidia
```

#### Arch Linux (AMD)

```bash
sudo pacman -S opencl-amd apr apr-util
yay -S libxcrypt-compat
```

#### Fedora/Nobara (AMD)

```bash
sudo dnf install rocm-opencl apr apr-util zlib libxcrypt-compat libcurl libcurl-devel mesa-libGLU -y
```

### Step 2: Verify OpenCL Installation

After installing the drivers, verify that OpenCL is detected:

```bash
clinfo
```

If `clinfo` is not installed:

**Arch Linux:**
```bash
sudo pacman -S clinfo
```

**Fedora/Nobara:**
```bash
sudo dnf install clinfo
```

### Step 3: Install Wine OpenCL Patch (Required)

Wine's built-in `clSetEventCallback` is a stub that returns an error. Affinity relies on event callbacks for GPU work completion tracking -- without this patch, OpenCL filters produce rendering corruption (tiled artifacts, blank regions).

Install the patched `opencl.dll`:

```bash
WINE_DIR="$HOME/.AffinityLinux/ElementalWarriorWine"
WINEPREFIX="$HOME/.AffinityLinux"

# Back up original
cp "$WINE_DIR/lib/wine/x86_64-windows/opencl.dll" \
   "$WINE_DIR/lib/wine/x86_64-windows/opencl.dll.orig"

# Install patched DLL
cp Patch/OpenCLEventCallback/prebuilt/opencl.dll \
   "$WINE_DIR/lib/wine/x86_64-windows/opencl.dll"
cp Patch/OpenCLEventCallback/prebuilt/opencl.dll \
   "$WINEPREFIX/drive_c/windows/system32/opencl.dll"
```

This only needs to be done once and survives Affinity updates.

See `Patch/OpenCLEventCallback/README.md` for building from source.

### Step 4: Patch libraster.dll (Required)

Affinity's raster engine uses Windows-only APIs (DXGI, `cl_khr_d3d10_sharing`, D3D12 interop) to discover OpenCL devices. These don't exist under Wine. The binary patcher bypasses them to use standard `clGetDeviceIDs` instead.

```bash
AffinityScripts/AffinityOpenCLPatch.sh
```

This must be re-run after each Affinity update. The patcher is idempotent (safe to run repeatedly) and backs up the original on first run.

### Step 5: Configure Environment Variables

Set these environment variables when launching Affinity:

```bash
# Required: expose all OpenCL devices to libraster
export PersonaIsOpenCLCPUBackendEnabled=1

# Required on AMD APU+dGPU systems: hide iGPU to prevent memory faults
export GPU_DEVICE_ORDINAL=0

# If patched opencl.dll is installed (Step 3): use d3d9=b
export WINEDLLOVERRIDES="d3d9=b"
# If patched opencl.dll is NOT installed: keep opencl disabled
# export WINEDLLOVERRIDES="opencl=;d3d9=b"
```

### Step 6: Configure d3d12 DLLs

The installer automatically configures vkd3d-proton for OpenCL support. The necessary DLLs (`d3d12.dll` and `d3d12core.dll`) are automatically copied to each Affinity application directory during installation.

## Verification

To verify that OpenCL is working in Affinity applications:

1. Launch any Affinity application (Photo, Designer, or Publisher)
2. Go to **Edit > Preferences > Performance**
3. Check the **Hardware Acceleration** section
4. You should see your GPU listed and OpenCL enabled
5. Apply a filter (e.g., Gaussian Blur) -- it should render without artifacts

## Troubleshooting

### "Unsupported Graphics Card" Dialog

This appears when libraster.dll can't find an OpenCL device through its
Windows-only discovery path. Run `AffinityScripts/AffinityOpenCLPatch.sh`
to bypass the Windows-only checks.

### Rendering Corruption (Tiled Artifacts, Blank Regions)

This is caused by Wine's stubbed `clSetEventCallback`. Install the patched
`opencl.dll` from `Patch/OpenCLEventCallback/prebuilt/` (see Step 3 above).

### GPU Memory Fault Crash (AMD APU+dGPU Systems)

On AMD systems with both an APU and a discrete GPU (e.g., Ryzen 7000 series
with an RX 7000/9000 series), ROCm exposes both devices. Cross-device memory
operations cause segfaults. Set `GPU_DEVICE_ORDINAL=0` to hide the iGPU.

### OpenCL Not Detected

If OpenCL is not detected in Affinity applications:

1. Verify OpenCL drivers are installed correctly using `clinfo`
2. Ensure your GPU drivers are up to date
3. Try restarting your system after installing OpenCL drivers
4. Verify the Wine OpenCL patch is installed (Step 3)
5. Verify libraster.dll is patched (Step 4)
6. Check that vkd3d-proton DLLs are present:
   ```bash
   ls ~/.AffinityLinux/drive_c/Program\ Files/Affinity/*/d3d12*.dll
   ```

## Additional Resources

- [Hardware Acceleration Guide](HARDWARE-ACCELERATION.md) - Overview of acceleration options
- [OpenCL Acceleration Details](OPENCL-ACCELERATION.md) - Technical details of the patches
- [Known Issues](Known-issues.md) - Common problems and solutions
