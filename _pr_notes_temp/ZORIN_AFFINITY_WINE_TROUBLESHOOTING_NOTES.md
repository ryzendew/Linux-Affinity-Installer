# AI Notes: Debugging Affinity on Wine

## Purpose

This document is a technical handoff for AI agents and maintainers diagnosing Affinity installation and startup failures under Wine. It records the reasoning model, important Wine semantics, failure signatures, safe investigation order, and lessons learned from the Zorin OS 18.1 incident.

The central lesson is that "Affinity does not start" is not one problem. It may mean:

- the application was never installed;
- the launcher selects the wrong Wine runtime;
- Wine invocation hangs even though another invocation works;
- a native DLL override points to a file that is absent or is actually a builtin module;
- a low-level graphics DLL failure produces dozens of misleading higher-level missing-library errors;
- the process starts but exits after initialization;
- the process remains alive but no window is visible;
- the installer reports success based on process behavior rather than installed artifacts.

Do not reinstall until these states have been distinguished.

## Repository and runtime model

### Main artifact

The active installer is:

```text
AffinityScripts/AffinityLinuxInstaller.py
```

It is a large PyQt6 application. Long operations run in worker threads and must communicate with Qt widgets through signals. The prefix and runtime are managed by the installer rather than by system Wine alone.

### Important paths

```text
Installer root:       ~/.AffinityLinux
Wine prefix:          ~/.AffinityLinux
Current wine-tkg:     ~/.AffinityLinux/wine-tkg/<version>/bin/wine
Legacy bundled Wine:  ~/.AffinityLinux/ElementalWarriorWine/bin/wine
Unified Affinity:     ~/.AffinityLinux/drive_c/Program Files/Affinity/Affinity/Affinity.exe
Plugin loader target: ~/.AffinityLinux/drive_c/Program Files/Affinity/Affinity/AffinityHook.exe
Desktop entry:        ~/.local/share/applications/Affinity.desktop
Installer log:        ~/AffinitySetup.log
Wine debug log:       ~/wine-tkg-debug.log
```

The prefix path is `~/.AffinityLinux`, not `~/.AffinityLinux/Prefix`.

## Mental model: diagnose in layers

Always debug from the lowest unambiguous layer upward.

### Layer 1: installation artifacts

First determine whether the application exists:

```bash
ls -la "$HOME/.AffinityLinux/drive_c/Program Files/Affinity/Affinity"
```

For unified Affinity, require at least one of:

```text
Affinity.exe
Serif.Affinity.dll
```

If neither exists, this is an installation failure. Launcher changes cannot fix it. Investigate the installer process and do not report installation success.

If the app directory is populated, do not reinstall immediately. Continue to launcher and runtime checks.

### Layer 2: Wine binary selection

Multiple Wine installations can coexist:

```text
system Wine
ElementalWarrior Wine
wine-tkg
```

A Wine binary merely existing does not mean it is the runtime used by all subprocesses. Check:

- the full executable path;
- `wine --version` for each candidate;
- whether the binary passes a functional smoke test;
- whether its directory is first in `PATH` for `wineserver`, `wineboot`, and helper programs;
- whether installer, winetricks, launcher, and desktop regeneration all use the same selector.

The correct shared selector in this installer is generally:

```python
get_wine_tkg_for_installer("wine")
```

The legacy selector:

```python
get_wine_path("wine")
```

may resolve to the older ElementalWarrior tree and should not be used when writing current Affinity launchers.

### Layer 3: command form

The command form matters independently of the Wine binary.

On the diagnosed Zorin system:

```text
wine ".../Affinity.exe"              -> hangs; killed later; rc=137
wine start /unix ".../Affinity.exe"  -> starts asynchronously; launcher rc=0
```

`rc=137` means the process received `SIGKILL` (`128 + 9`). It does not mean Wine naturally returned an Affinity error code. Usually a timeout or manual kill terminated a hung process.

`wine start /unix` returning zero only proves Wine accepted the launch request. It does not prove Affinity remained alive. Always check the process after a delay.

Recommended launcher form:

```bash
env WINEPREFIX="$HOME/.AffinityLinux" \
  "$HOME/.AffinityLinux/wine-tkg/<version>/bin/wine" \
  start /unix "$HOME/.AffinityLinux/drive_c/Program Files/Affinity/Affinity/Affinity.exe"
```

If `AffinityHook.exe` exists and plugin-loader behavior is desired, target it instead.

### Layer 4: desktop-entry regeneration

A manually repaired desktop file can be broken again by:

- application installation;
- application update;
- GPU configuration changes;
- DXVK/vkd3d backend switching;
- plugin-loader installation;
- generic desktop-entry update functions.

Search every code path that writes or patches `Exec=`. Fixing only `create_desktop_entry()` is incomplete if backend switching later reconstructs a legacy command.

Required invariants:

```text
selected Wine = get_wine_tkg_for_installer("wine")
command form  = wine start /unix "<full Linux path>"
unified target = AffinityHook.exe if present, otherwise Affinity.exe
```

When parsing existing desktop entries, recognize both forms:

```text
wine "...exe"
wine start /unix "...exe"
```

Never split executable paths on whitespace. `Program Files` makes that approach corrupt the path.

### Layer 5: DLL loading and graphics stack

If the executable exists and the launch command is correct, capture Wine loader errors. The earliest dependency failure is usually more important than the last error line.

Use a bounded command so a hang does not block debugging indefinitely:

```bash
timeout 45 env \
  WINEPREFIX="$HOME/.AffinityLinux" \
  WINEDEBUG=+loaddll,+err \
  "$HOME/.AffinityLinux/wine-tkg/<version>/bin/wine" \
  "C:/Program Files/Affinity/Affinity/Affinity.exe" \
  > /tmp/affinity.out 2> /tmp/affinity.err
```

Then inspect:

```bash
grep -E ':err:|not found|failed|exception' /tmp/affinity.err
tail -50 /tmp/affinity.err
```

Do not assume every "not found" message means the named Affinity DLL is absent on disk. Wine's loader reports a dependent module as unavailable when any of its imports cannot be resolved.

## The vkd3d-proton failure in depth

### Observed cascade

The first meaningful failure was:

```text
Library d3d12.dll (which is needed by libdxcore.dll) not found
```

That caused subsequent failures:

```text
libdxcore.dll not found
libraster.dll not found
librenderer.dll not found
libStory.dll not found
libpsd.dll not found
libpersona.dll not found
```

Most of those files existed. They were reported unavailable because their dependency chain included `d3d12.dll` through `libdxcore.dll`.

The correct reasoning is:

```text
d3d12 fails
  -> libdxcore cannot load
  -> libraster cannot load
  -> rendering/story/PSD libraries cannot load
  -> libpersona cannot load
  -> Affinity startup cannot complete
```

Fix the first dependency failure, not every downstream error.

### Why an existing d3d12.dll was still "not found"

The prefix contained:

```text
drive_c/windows/system32/d3d12.dll
drive_c/windows/system32/d3d12core.dll
```

Architecture checks showed they were 64-bit, which initially looked correct. However, string/import inspection showed the installed `d3d12.dll` imported `wined3d.dll`; it was Wine's builtin PE module, not the downloaded vkd3d-proton native DLL.

The registry contained:

```text
"d3d12"="native"
"d3d12core"="native"
```

Wine DLL override semantics matter:

- `builtin`: load Wine's implementation;
- `native`: load a Windows/native DLL from the prefix;
- `native,builtin`: prefer native, then fall back to builtin;
- `builtin,native`: prefer builtin, then native.

A builtin module stored in `system32` does not satisfy a native-only request merely because the filename exists. Wine rejects it for the requested load order and reports the library as unavailable.

### Where the real DLLs were

The real vkd3d-proton files had been downloaded and extracted under:

```text
~/.AffinityLinux/dxvk/vkd3d-proton-<version>/x64/
~/.AffinityLinux/dxvk/vkd3d-proton-<version>/x86/
```

The installer also staged only 64-bit copies under:

```text
~/.AffinityLinux/vkd3d_dlls/
<Wine tree>/lib/wine/vkd3d-proton/x86_64-windows/
```

Staging them outside the prefix was insufficient for Wine's native DLL lookup in this configuration.

### Correct installation

Copy architecture-matched files:

```text
x64/d3d12.dll       -> drive_c/windows/system32/d3d12.dll
x64/d3d12core.dll   -> drive_c/windows/system32/d3d12core.dll
x86/d3d12.dll       -> drive_c/windows/syswow64/d3d12.dll
x86/d3d12core.dll   -> drive_c/windows/syswow64/d3d12core.dll
```

Remember Wine's directory convention:

- `system32` contains 64-bit DLLs in a 64-bit prefix;
- `syswow64` contains 32-bit DLLs.

This naming is historically counterintuitive. Do not swap architectures based on directory names.

Back up existing files before replacement. Configure:

```text
"d3d12"="native,builtin"
"d3d12core"="native,builtin"
```

After repair, verify source and destination architecture and size, then launch again with bounded logging.

### Why reinstalling Affinity would not fix this

Affinity's installer owns the app payload. The broken files and overrides were in the Wine prefix graphics runtime. Reinstalling the application could leave the same d3d12 configuration untouched and reproduce the hang.

Reinstall only when:

- app payload files are missing;
- app payload checksums or file sizes indicate corruption;
- installer/update interrupted replacement of Affinity files;
- runtime and launcher layers have already been validated.

## Installer false-positive success

### Failure pattern

The installer process started, exited quickly, and the script proceeded as though the update completed. Immediately afterward:

```text
Serif.Affinity.dll not found
Affinity (Unified): Not installed
```

This is a process-success versus outcome-success bug.

### Required success rule

After every Affinity install/update attempt:

1. capture the return code;
2. record elapsed time;
3. preserve relevant stdout/stderr;
4. wait for related Wine processes only when appropriate;
5. verify actual installation artifacts;
6. report success only if artifacts exist;
7. do not create a launcher pointing at a missing executable.

For unified Affinity, verify:

```text
Affinity.exe OR Serif.Affinity.dll
```

For v2 apps, verify the app-specific executable:

```text
Photo 2/Photo.exe
Designer 2/Designer.exe
Publisher 2/Publisher.exe
```

A debugger appearing, a launcher returning zero, or `wineserver -w` completing are not substitutes for artifact verification.

## .NET/WPF installer exception

The original Affinity `SetupUI.exe` crashed under Zorin's system Wine with:

```text
0xe0434352
```

This is a generic CLR exception code. It identifies a managed exception, not its exact cause. The stack referenced WPF/CLR components such as PresentationFramework, WindowsBase, and mscorlib.

Correct response:

- preserve the complete installer output;
- note the exact Wine build used;
- compare behavior under the selected wine-tkg build;
- verify installed .NET and fonts;
- do not interpret the generic exception code as proof of one specific missing DLL;
- do not report success without artifacts.

Changing the installer path to wine-tkg was necessary for consistency, but runtime validation remained necessary because the eventual launch blocker was separate.

## WebView2 lessons

### Detection layout

WebView2 commonly installs the executable under a version directory:

```text
Program Files (x86)/Microsoft/EdgeWebView/Application/<version>/msedgewebview2.exe
```

Checking only:

```text
Application/msedgewebview2.exe
```

produces a false negative.

Search both standard roots:

```text
Program Files (x86)/Microsoft/EdgeWebView/Application
Program Files/Microsoft/EdgeWebView/Application
```

Check a direct executable and versioned child directories.

### MSASN1 failure

One installation attempt failed at:

```text
MSASN1.dll.ASN1DEREncBeginBlk
```

This indicates an unimplemented or unresolved Wine API path during that attempt. It should be recorded separately from Affinity's d3d12 launch failure. Do not collapse all errors into one root cause merely because they occur in the same prefix.

## Qt threading and messages

The GUI declares message signals using strings. Passing `QMessageBox.Icon.Warning` or similar enum values through a signal declared as `pyqtSignal(str, str, str)` raises a runtime type error and suppresses the user-facing dialog.

Use the established string values:

```text
warning
error
info
```

Worker threads must not manipulate widgets directly. Emit signals to the corresponding safe main-thread slots.

## GPU/backend rewrite risks

DXVK and vkd3d-proton are distinct components:

- DXVK primarily translates D3D8/9/10/11 to Vulkan;
- vkd3d-proton translates D3D12 to Vulkan.

Affinity v3's dependency chain includes D3D12 through `libdxcore.dll`, even when other parts of the app emit wined3d or D3D11 messages. Seeing wined3d/D3D11 logs does not prove D3D12 is irrelevant.

Backend-switch functions often:

- copy or remove DLLs;
- change registry overrides;
- rebuild desktop entries;
- alter GPU environment variables.

Therefore, every backend switch must preserve:

- correct d3d12 DLL placement;
- architecture matching;
- safe overrides;
- selected Wine path;
- `start /unix` invocation;
- plugin-loader target selection.

## Reliable diagnostic procedure

### Phase A: establish state

1. Read `~/AffinitySetup.log` and `~/wine-tkg-debug.log`.
2. Confirm distro, GPU, Wine versions, and prefix path.
3. Check whether Affinity artifacts exist.
4. Inspect the exact desktop `Exec=` line.
5. Check whether `AffinityHook.exe` exists.

### Phase B: isolate launcher behavior

1. Run the exact desktop command.
2. Record immediate return code.
3. Check the process after 5, 15, and 30 seconds.
4. Compare direct Wine invocation and `wine start /unix` only when needed.
5. Avoid assuming asynchronous launcher success means app success.

### Phase C: isolate loader failure

1. Stop stale Wine processes with the selected Wine tree's `wineserver`.
2. Run with a timeout and targeted `WINEDEBUG` channels.
3. Save stdout and stderr to files.
4. Find the earliest meaningful `import_dll` or exception error.
5. Build the dependency chain from that error.
6. Inspect actual DLL architecture and imports.
7. Inspect `DllOverrides` in the registry or `user.reg`.

### Phase D: repair safely

1. Back up files being replaced.
2. Use cached, already downloaded vkd3d-proton files when available.
3. Copy x64 to `system32` and x86 to `syswow64`.
4. Use `native,builtin` unless there is a documented reason for native-only.
5. Restart the Wine server.
6. Re-run the exact desktop command.
7. Confirm the process remains alive.
8. Confirm the original first loader error is absent.

### Phase E: make the fix persistent

1. Find all installer functions that stage, copy, or remove the affected DLLs.
2. Find all functions that set or remove DLL overrides.
3. Find all desktop-entry generation and rewrite paths.
4. Use one Wine selector consistently.
5. Add artifact-based install validation.
6. Syntax-check the Python script.
7. Test an installer-created launcher, not only a manually edited one.

## Commands and interpretation

### Confirm artifact presence

```bash
ls -la "$HOME/.AffinityLinux/drive_c/Program Files/Affinity/Affinity"
```

Empty or missing directory: installation problem.

### Inspect launcher

```bash
grep '^Exec=' "$HOME/.local/share/applications/Affinity.desktop"
```

Check Wine path, `WINEPREFIX`, `start /unix`, quoting, and target executable.

### Inspect DLL architecture

```bash
file "$HOME/.AffinityLinux/drive_c/windows/system32/d3d12.dll"
file "$HOME/.AffinityLinux/drive_c/windows/syswow64/d3d12.dll"
```

Expected:

```text
system32: PE32+ x86-64
syswow64: PE32 Intel 80386
```

### Distinguish builtin-like and vkd3d-proton DLLs

```bash
strings "$HOME/.AffinityLinux/drive_c/windows/system32/d3d12.dll" \
  | grep -iE 'wined3d|d3d12core|vulkan'
```

This is a heuristic, not a formal signature check. Compare against the known extracted vkd3d-proton source and file size.

### Inspect overrides

```bash
awk '/\[Software\\\\Wine\\\\DllOverrides\]/,/^$/' \
  "$HOME/.AffinityLinux/user.reg"
```

Registry commands are preferable for changing values while Wine is not actively mutating the prefix.

### Check process persistence

```bash
pgrep -af 'Affinity.exe|AffinityHook.exe'
```

Check after multiple delays. A process that appears briefly and exits is a different failure from a launch request that never creates it.

## Common reasoning mistakes

### Mistake: recommend reinstalling immediately

Why wrong: application reinstall does not repair the Wine runtime, DLL overrides, desktop regeneration code, or mismatched Wine selection.

### Mistake: trust the installer success message

Why wrong: the original flow reported success with an empty app directory.

### Mistake: trust `rc=0` from `wine start`

Why wrong: `start` is asynchronous. It confirms request acceptance, not a healthy persistent app.

### Mistake: treat `rc=137` as an Affinity exit code

Why wrong: it usually indicates forced termination after a hang.

### Mistake: fix every missing Affinity DLL

Why wrong: one low-level dependency failure can make many present DLLs appear unloadable.

### Mistake: assume a filename proves the correct DLL implementation

Why wrong: a Wine builtin PE module and a native vkd3d-proton DLL can share the same filename and architecture.

### Mistake: copy x86 to `system32`

Why wrong: in a 64-bit Wine prefix, `system32` is 64-bit and `syswow64` is 32-bit.

### Mistake: fix one desktop writer

Why wrong: backend switching or plugin-loader installation can rewrite the entry later.

### Mistake: mix Wine builds within one operation

Why wrong: invoking one `wine` while helpers resolve from another Wine tree can produce inconsistent server and prefix behavior.

## Current known-good state from the Zorin case

The successful state included:

```text
Wine: wine-tkg 11.16 staging wow64
Launcher: wine start /unix <full Linux path>
d3d12 x64: vkd3d-proton files in system32
d3d12 x86: vkd3d-proton files in syswow64
Overrides: native,builtin
Unified target: Affinity.exe (AffinityHook.exe absent)
```

Validation showed:

- launcher return code `0`;
- no `d3d12.dll ... not found` error;
- `Affinity.exe` running after 5, 15, and 30 seconds;
- installer Python syntax check passing.

## Code areas to inspect first in future sessions

Use symbol search because the main file is large:

```text
verify_affinity_artifacts
_run_installer_and_capture
update_existing_desktop_entries
install_d3d12_dlls
_find_vkd3d_dll_sources
install_vkd3d_dlls_to_prefix
setup_d3d12_overrides
remove_d3d12_overrides
_find_webview2_executable
create_desktop_entry
launch_affinity_v3
_build_affinity_exec_line
_patch_affinity_desktop_for_hook
```

Also inspect every occurrence of:

```text
Exec=env WINEPREFIX
get_wine_path("wine")
get_wine_tkg_for_installer("wine")
d3d12core
DllOverrides
```

## Completion criteria for an AI agent

Do not declare this class of task complete until all applicable conditions hold:

1. The requested app artifacts exist.
2. The installer does not claim success without them.
3. The desktop entry selects the intended Wine runtime.
4. The launch command uses the validated command form.
5. Plugin-loader behavior is preserved.
6. Relevant native DLLs are in the prefix, not merely staged elsewhere.
7. DLL architecture matches the target directory.
8. Overrides have a safe and intentional load order.
9. The original first loader error is gone.
10. The app process remains alive after a meaningful delay.
11. Installer regeneration does not undo the repair.
12. `python3 -m py_compile AffinityScripts/AffinityLinuxInstaller.py` passes.

## Source material

These notes consolidate the repository logs and live debugging from 2026-08-24:

- `logs/INSTALL_DEBUG_SUMMARY.md`
- `logs/AFFINITY_V3_INSTALL_DEBUG_2026-08-24.md`
- `logs/AFFINITY_V3_STATUS_2026-08-24.md`
- `logs/ZORIN_OS_INSTALLER_ISSUE_PROMPT_2026-08-24.md`
- `docs/ZORIN_OS_COMPATIBILITY.md`
