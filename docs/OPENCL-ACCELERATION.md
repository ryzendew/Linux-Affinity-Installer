# OpenCL Hardware Acceleration for Affinity

This document describes the patches required to enable OpenCL GPU acceleration
for Affinity Suite running under Wine.

## Overview

Affinity's raster engine (`libraster.dll`) uses OpenCL for GPU-accelerated
image processing (blur, sharpen, denoise, etc). Under Windows, it discovers
GPU devices through DXGI/D3D10/D3D12 interop APIs. Under Wine, these APIs
are stubs, so the engine falls back to CPU-only rendering and displays an
"Unsupported Graphics Card" dialog.

Three patches are needed:

1. **Wine `clSetEventCallback`** -- implement the missing OpenCL callback API
2. **libraster.dll binary patches** -- bypass Windows-only device discovery
3. **`GPU_DEVICE_ORDINAL` env var** -- hide APU iGPU on dual-GPU AMD systems

## Patch 1: Wine clSetEventCallback

**Location:** `Patch/OpenCLEventCallback/`

Wine's `clSetEventCallback` returns `CL_INVALID_OPERATION` because the
Unix-side OpenCL wrapper has no callback bridging infrastructure. Affinity
uses event callbacks for GPU work completion tracking. Without them, race
conditions cause rendering corruption (tiled artifacts, blank regions).

The patch implements `clSetEventCallback` entirely on the PE (Windows) side
using a thread-per-callback approach:

- **CL_COMPLETE:** efficient blocking wait via `clWaitForEvents`
- **CL_RUNNING / CL_SUBMITTED:** polls `clGetEventInfo` with `Sleep(1)`

Uses only standard OpenCL 1.1 API -- tested on AMD ROCm. Should work with
NVIDIA and Intel (Mesa Rusticl / compute-runtime) but untested on those.

**Installation:** Copy the pre-built `opencl.dll` to replace Wine's built-in,
or apply the source patches and rebuild. See `Patch/OpenCLEventCallback/README.md`.

## Patch 2: libraster.dll Binary Patches

**Location:** `AffinityScripts/AffinityOpenCLPatch.sh`

Three binary patches to `libraster.dll` (~68MB native x86-64 PE DLL):

### 2a. DXGI Adapter Matching Bypass

Wine stubs `clGetDeviceIDsFromD3D10KHR`. The patch NOPs out the JNE after
the DXGI adapter comparison so the code falls through to standard `clGetDeviceIDs`.

### 2b. cl_khr_d3d10_sharing Extension Bypass (5 instances)

ROCm/Mesa don't provide this Windows-only extension. Pattern changes JNE to JMP
to skip the "return false" path. Multiple instances exist due to C++ template
instantiations in IsSupported checks.

### 2c. D3D12 Interop Bypass

After d3d10_sharing passes, IsSupported tries to create a D3D12 device from
the OpenCL device handle (for `D3D_FEATURE_LEVEL_12_0` check). Under Wine
this returns NULL. The patch changes the null-check JE to jump to the
"return true" path.

The patcher is idempotent (safe to run repeatedly) and backs up the original
on first run. It must be re-run after each Affinity update.

## Patch 3: GPU_DEVICE_ORDINAL

On AMD systems with both an APU (integrated GPU) and a discrete GPU,
ROCm exposes both devices to OpenCL. When Affinity attempts to use both,
cross-device memory operations cause segfaults.

Set `GPU_DEVICE_ORDINAL=0` to hide the APU iGPU and only expose the
discrete GPU. This is only needed on dual-GPU AMD systems.

## Environment Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `PersonaIsOpenCLCPUBackendEnabled` | `1` | Makes libraster use `CL_DEVICE_TYPE_ALL` for device discovery |
| `GPU_DEVICE_ORDINAL` | `0` | Hides APU iGPU on dual-GPU AMD systems |
| `WINEDLLOVERRIDES` | `d3d9=b` or `opencl=;d3d9=b` | If the patched `opencl.dll` is installed, use `d3d9=b`. If not, keep the original `opencl=` disable to prevent Wine's stubbed clSetEventCallback from crashing. |
