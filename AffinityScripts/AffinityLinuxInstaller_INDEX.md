# AffinityLinuxInstaller.py AI Index

Source: `AffinityScripts/AffinityLinuxInstaller.py` (lines `1-19007`)

## Fast Navigation

- **Entrypoint**: `main()` at `AffinityScripts/AffinityLinuxInstaller.py:18962`
- **Main application class**: `AffinityInstallerGUI` at `AffinityScripts/AffinityLinuxInstaller.py:294`
- **Huge method container**: `AffinityInstallerGUI` methods span `315-18927`

## Top-Level Structure

| Section | Line Range | Purpose |
|---|---:|---|
| Bootstrap + dependency install helpers | `27-79` | Detect distro and install missing Python packages |
| PyQt6 import/bootstrap logic | `82-220` | Import PyQt6 and fallback install path |
| UI helper widgets | `223-291` | `ZoomableTextEdit`, `ProgressSpinner` |
| Main GUI class | `294-18927` | All installer logic, UI, workflows, system integration |
| Cleanup helper | `18930-18959` | Kill stalled Wine processes |
| Entrypoint | `18962-19007` | Start QApplication and GUI |

## Main Class Section Map (`AffinityInstallerGUI`)

### 1) App initialization and theming
- `__init__`: `315-482`
- Deferred startup + install status checks: `484-717`
- Zoom and icon utilities: `719-834`
- Theme switching and style sheets: `836-2394`

### 2) UI construction
- Build primary UI/layout sections: `2396-2965`
- Reusable button groups and button wiring: `2967-3095`
- Spinner and icon loading helpers: `3097-3211`
- Window close and logging/spec utilities: `3213-3399`

### 3) Operation lifecycle, dialogs, auth
- Progress and cancellation lifecycle: `3401-3489`
- Message dialogs and thread-safe UI updates: `3491-3515`
- Sudo password + interactive prompts: `3517-3800`
- Wine version dialog and question dialogs: `3802-4341`

### 4) Wine runtime discovery and process execution
- CPU generation and Wine path/version helpers: `4343-4698`
- Wine-TKG acquisition/verification: `4718-5265`
- Process registry/termination + command runners: `5339-6305`
- Distro detection and icon prep: `6311-6478`

### 5) GPU and graphics backend management
- GPU detection and selection: `6480-7060`
- DXVK/VKD3D env, switching, backend reconfiguration: `7079-7802`
- Desktop entry updates after backend changes: `7804-7903`

### 6) Initialization, dependency install, core setup
- Init flow + persisted install location: `7984-8066`
- One-click setup workflow: `8068-8422`
- Install entrypoints and dependency installers (per distro): `8424-10363`
- Wine setup + winmetadata setup/reinstall: `10365-10859`

### 7) DXVK/VKD3D versioning and override setup
- Fetch/store latest and installed versions: `10861-10994`
- Install/remove DLLs and overrides: `10996-11443`
- VKD3D + Wine config: `11445-11657`

### 8) Wine switching and dependency tools
- Environment prep and cached downloads: `11664-11969`
- Wine version switch UI + thread workers: `11971-12314`
- System/winetricks dependency install routines: `12316-12652`

### 9) Affinity settings, WebView2, custom installs, update
- Affinity settings install + registry checks: `12654-13168`
- WebView2 detection/install: `13170-13452`
- Additional settings flow + custom file install: `13454-14149`
- Update workflow + installation workflow: `14151-14646`

### 10) Runtime patching, OpenCL, .NET, desktop entries
- wintypes/winmetadata handling: `14648-14871`
- OpenCL and renderer config: `14873-15288`
- .NET SDK checks/install: `15308-17157`
- Patcher build/run and DLL patching: `15629-16183`
- Desktop entry creation + optional plugin loader: `16185-18909`
- Thank-you dialog: `18911-18927`

## High-Value Functions (Quick Jump)

- `run_command`: `AffinityScripts/AffinityLinuxInstaller.py:5387`
- `run_command_streaming`: `AffinityScripts/AffinityLinuxInstaller.py:5655`
- `run_command_interactive`: `AffinityScripts/AffinityLinuxInstaller.py:6134`
- `ensure_wine_tkg`: `AffinityScripts/AffinityLinuxInstaller.py:4718`
- `check_dependencies`: `AffinityScripts/AffinityLinuxInstaller.py:8863`
- `setup_wine`: `AffinityScripts/AffinityLinuxInstaller.py:10365`
- `switch_to_vkd3d`: `AffinityScripts/AffinityLinuxInstaller.py:7361`
- `switch_to_dxvk`: `AffinityScripts/AffinityLinuxInstaller.py:7548`
- `install_affinity_settings`: `AffinityScripts/AffinityLinuxInstaller.py:12654`
- `run_installation`: `AffinityScripts/AffinityLinuxInstaller.py:14438`
- `launch_affinity_v3`: `AffinityScripts/AffinityLinuxInstaller.py:17994`

## AI Exploration Strategy (Context-Efficient)

1. Start with this index and only open the line range you need.
2. For workflow bugs, open the entrypoint method and immediately open called helpers.
3. For backend issues, focus on `6480-7802` and skip UI style blocks.
4. For install failures, focus on `8424-11657` and command runners `5387-6305`.
5. For patcher/.NET issues, focus on `15308-17379`.

## Suggested Chunking for LLM Reads

- Chunk A: `1-834` (bootstrap + widgets + core init)
- Chunk B: `836-2394` (themes/styles only)
- Chunk C: `2396-3800` (UI build + dialogs + operation lifecycle)
- Chunk D: `3802-6305` (dialogs, Wine runtime, command execution)
- Chunk E: `6311-8422` (distro/gpu/init/one-click)
- Chunk F: `8424-11657` (dependency + Wine setup + DXVK/VKD3D setup)
- Chunk G: `11664-14646` (switching, settings, custom/update/install flows)
- Chunk H: `14648-17379` (wintypes/opencl/.NET/patching)
- Chunk I: `17381-19007` (dpi/uninstall/launch/plugin loader/entrypoint)

## Generated Symbol Summary

Top-level symbols:
- `detect_distro_for_install`: `27-40`
- `install_package`: `43-79`
- `ZoomableTextEdit`: `223-249`
- `ProgressSpinner`: `252-291`
- `AffinityInstallerGUI`: `294-18927`
- `kill_stalled_wine_processes`: `18930-18959`
- `main`: `18962-19007`
