# Affinity hangs at startup when OpenCL is on

Symptom: the splash screen never clears, the window comes up with no UI in it,
and nothing further happens. Not a crash — no dialog, no crash report, no error
in the log. A double-clicked document never opens, because the application
never finishes starting.

## Recognising it

The process sits at a couple of dozen threads. A finished startup reaches
around 150.

```sh
tools/afprocs.sh            # threads=24 and no growth, versus threads=145
```

`Log.txt` stops after the path banner — ten lines — and never reaches
`Attempting to create Direct3D device`.

The backtrace is the same every time:

```
=>0 ntdll      (+0xec84)        waiting
  1 kernelbase (+0x76d5d)       WaitForMultipleObjects
  2 libkernel
  3 libraster
  4 libraster
  5 libpersona
```

Affinity's rasteriser waiting on an event that is never signalled. Nothing in
win32u, winex11, vulkan or vkd3d — this is not a renderer or GPU-driver fault.

## Cause

OpenCL initialising on a real GPU, on every Wine from 11.11 onward. Established
by building 11.16 three ways and testing each with OpenCL enabled: even the
exact OpenCL code from EW 11.0, which works there, deadlocks on the newer base.
The regression is upstream, between 11.0 and 11.11; OpenCL initialisation
merely walks into it.

The long-standing "11.12 + lavapipe works" report is the same bug seen from the
other side: with an unsupported GPU Affinity never initialises OpenCL, so it
never enters the broken path.

## Fix

`opencl` set to disabled in the prefix's `HKCU\Software\Wine\DllOverrides`.
The installer does this for any Wine from 11.11, at the end of Wine setup and
again at the end of the install, so a prefix whose Wine changed along the way
still ends up correct. Older Wine is left alone — OpenCL works there, and
choosing one of those builds is how to have it.

This is **not** conditional on the installer's "Enable OpenCL Support?" answer.
That question installs OpenCL packages and vkd3d-proton, which is a different
thing from letting Affinity load `opencl.dll` and hang. A prefix with
`.opencl_enabled = 1` and no DLL override is exactly the broken state.

Check a prefix with:

```sh
grep -a '"opencl"' ~/.AffinityLinux/user.reg     # want: "opencl"=""
```

## Why this took so long to find

It only reproduces through the desktop entry. Every launch made by hand during
debugging passed `WINEDLLOVERRIDES="opencl=d"` on the command line — the
project's own documented habit — and started cleanly, so the failure could not
be reproduced while the user hit it every time.

Three unrelated bugs were found and fixed along the way (WinRT metadata
ordering, the wrong metadata set, and handing a document to a shutting-down
process), each looking like the cause because each produced the same visible
symptom: a window with no document in it.

**When a failure cannot be reproduced by hand, compare the environments before
theorising about the code.** `tr '\0' '\n' < /proc/<pid>/environ` against a
working launch and a failing one would have shown this in a minute.
