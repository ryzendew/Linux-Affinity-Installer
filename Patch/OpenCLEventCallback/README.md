# Wine OpenCL clSetEventCallback Patch

Wine's built-in `clSetEventCallback` forwards to the Unix side, but the
Unix-side OpenCL wrapper has no callback bridging infrastructure and returns
`CL_INVALID_OPERATION`. Affinity relies on event callbacks for GPU work
completion tracking -- without them, race conditions cause severe rendering
corruption (tiled artifacts, blank regions).

## How it works

The patch replaces the Unix thunk with a PE-side implementation that spawns
a Windows thread per callback:

- **CL_COMPLETE**: blocks efficiently on `clWaitForEvents`
- **CL_RUNNING / CL_SUBMITTED**: polls `clGetEventInfo` with `Sleep(1)`

This avoids all Unix-to-Windows ABI and thread-initialization issues.

Uses only standard OpenCL 1.1 API -- works with any GPU vendor (AMD ROCm,
NVIDIA, Intel, Mesa Rusticl).

## Files

- `pe_wrappers.patch` / `pe_thunks.patch` -- diffs against upstream Wine
- `pe_wrappers.c` / `pe_thunks.c` -- full patched source files
- `prebuilt/opencl.dll` -- pre-built for x86_64 (ElementalWarriorWine 11.0)

## Installing the pre-built DLL

```bash
WINE_DIR="$HOME/.AffinityLinux/ElementalWarriorWine"
WINEPREFIX="$HOME/.AffinityLinux"

cp "$WINE_DIR/lib/wine/x86_64-windows/opencl.dll" \
   "$WINE_DIR/lib/wine/x86_64-windows/opencl.dll.orig"

cp prebuilt/opencl.dll "$WINE_DIR/lib/wine/x86_64-windows/opencl.dll"
cp prebuilt/opencl.dll "$WINEPREFIX/drive_c/windows/system32/opencl.dll"
```

## Building from source

Apply patches to Wine source and rebuild, or compile just the PE DLL:

```bash
WINE_SRC=/path/to/wine-source
WINE_INSTALL=$HOME/.AffinityLinux/ElementalWarriorWine

cd $WINE_SRC/dlls/opencl
patch -p0 < pe_wrappers.patch
patch -p0 < pe_thunks.patch

clang -D_UCRT -D__WINESRC__ -D__WINE_PE_BUILD -D__STDC__ -c \
    -o pe_wrappers.o pe_wrappers.c \
    -I. -I../../include -I../../include/msvcrt \
    -Wall -target x86_64-windows -fuse-ld=lld --no-default-config -O2

$WINE_INSTALL/bin/winegcc -target x86_64-windows -shared \
    -o opencl.dll pe_wrappers.o pe_thunks.o \
    -Wl,--wine-builtin opencl.spec -lkernel32 -lntdll
```
