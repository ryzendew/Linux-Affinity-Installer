# Changelog

## [2026-10-16] - Wine 11.19-r10, no architecture warning

### Changed
- **The 11.19 choice installs [`11.19-r10`](https://github.com/jfacemyer/Affinity-Wine-Builder/releases/tag/11.19-r10)**, pinned by SHA-256 like r9. Affinity's own installer no longer warns that installing is "not recommended" for this processor: it asks Windows' management service (WMI) for the processor type from its window, Wine gave it no answer, and it took that for an ARM machine. Four Wine fixes make that query answer; they also help other .NET programs that query WMI or use COM objects from their window.

---

## [2026-10-16] - Wine 11.19-r9, OpenGL

### Changed
- **The 11.19 choice installs [`11.19-r9`](https://github.com/jfacemyer/Affinity-Wine-Builder/releases/tag/11.19-r9)**, pinned by SHA-256 like r8. It fixes Affinity on Wine's OpenGL renderer (the "OpenGL" renderer choice, or a prefix without a renderer setting):
  - **Tool flyouts and tooltips** were black boxes.
  - **The floating Help panel** came back from a studio switch with an empty white frame.
  
  Nothing changes on the Vulkan renderer.

### Fixed
- **A second click no longer starts a second setup.** While an action runs, the other action buttons say so instead of starting another one beside it. Two One-Click Full Setups at once unpacked Wine over each other, one deleted the other's download, and the setup stopped with "Wine setup failed".
- **Wine components after the fonts were missing their registry settings.** The direct font install created a second `C:\windows\Temp` folder (`Temp` beside Wine's `temp`), and winetricks' registry files were then not found: vcrun2022's and msxml's DLL overrides and the Vulkan renderer were never set. Affinity ran on Wine's own C++ runtime and crashed, and its setup could report .NET 3.5 missing. Fonts now use Wine's `temp`, and a stray `Temp` is folded back into it before the components are installed.
- **A prefix that lost its renderer setting gets Vulkan back.** The installer checks for the setting after the Wine components and sets it again if it is missing, and the manager does the same for each of its prefixes while nothing runs in it (noted in the prefix's log). A renderer that was chosen, such as OpenGL, is kept.

---

## [2026-10-16] - Faster setup, WineFix wine-fixes-4

### Changed
- **The plugin loader and WineFix come from [`wine-fixes-4`](https://github.com/jfacemyer/AffinityPluginLoader/releases/tag/wine-fixes-4)**, pinned by SHA-256 like wine-fixes-3. New in it: the sub-tool panel (the shape tools, for example) keeps two columns after a studio switch, instead of coming back as one column running the height of the window.
- **Faster setup:** the core fonts and Tahoma are copied and registered directly (about 6 s each, from 94 s and 16 s), and stopping Wine between steps no longer waits 20 s for a process that never leaves by itself.
- **The WebView2 step no longer stalls:** its setup leaves Edge Update running, which held the step for up to an hour. Edge Update is stopped once the runtime is in place.
- The progress line shows when the current operation started and how long it has taken, and the log records the total.
- The installer's dialogs stay above its window.

### Fixed
- A fresh install could come up on Wine's OpenGL renderer instead of Vulkan: stopping Wine right after a setting was written could cut off Wine's registry save. Wine's server now always gets time to finish saving.

---
## [2026-10-15] - Wine 11.19-r8, Help works

### Changed
- **The 11.19 choice installs [`11.19-r8`](https://github.com/jfacemyer/Affinity-Wine-Builder/releases/tag/11.19-r8)**, pinned by SHA-256 like r7. It fixes:
  - **Help:** the Help panel shows its pages on every opening, floating or docked, and they stay while you work in Affinity. Before, it was blank from the second opening, went blank whenever Affinity redrew its panels, and showed black boxes when the pointer moved over a page.
  - **Updating Wine in an existing install** no longer shows "This application could not be started" two to four times.
  - **Faster drawing of selections and node edits** (about 7% and 15% more frames), and less waiting in Affinity's thread pool.
  - **Ctrl and Shift drops** from the file manager reach Affinity as such.
- **Installing Affinity v3 also installs the WebView2 runtime**, so Help works without the separate button. If that install fails, the installer says so and points to the button.
- .NET native images are compiled after the settings patch, not before: a fresh install could otherwise crash at the first start.
- The OpenCL prompt describes the current state, and the checksum check in the log names the Wine release it verified.

---

## [2026-10-13] - Wine 11.19-r7

### Changed
- **The 11.19 choice installs [`11.19-r7`](https://github.com/jfacemyer/Affinity-Wine-Builder/releases/tag/11.19-r7)**, pinned by SHA-256 like r6. It fixes:
  - **Dragging files from Wayland applications onto the canvas:** drops from Dolphin on Plasma were refused or canceled, and could crash Affinity with "Unrecoverable system error".
  - **Copy and paste between documents:** the paste sometimes did nothing until a second copy. The clipboard briefly had no owner during a copy, and Klipper restored its previous entry.
  - **Dropping a file on the toolbar:** after the drag had passed over the canvas, the file opened only once focus moved to another window.
  - The OpenCL bridge work and wined3d fixes from the 11.18 set, sign-in metadata, and much faster reads in Affinity's PDF importer.

---

## [2026-10-13] - Pinned Wine builds, merged upstream

### Changed
- **The 11.19 and 11.18 choices install pinned builds**: 11.19 is [`11.19-r6`](https://github.com/jfacemyer/Affinity-Wine-Builder/releases/tag/11.19-r6) (adds pen pressure through WinTab and correct window coordinates across DPI awareness) and 11.18 is [`11.18-r1`](https://github.com/jfacemyer/Affinity-Wine-Builder/releases/tag/11.18-r1). Each download is checked against a SHA-256 in `AffinityLinuxInstaller.py` and refused if it differs.
- Merged the upstream changes of 2026-10-10: the two-version picker, the WebView2 runtime installed as Windows 11, and the updated documentation. `msedgewebview2.exe` itself stays set to Windows 7: on Wine 11.19 with runtime 142 its processes all stay up as Windows 7, while as Windows 11 its GPU processes die and the Help window stays empty.
- WinMetadata is still set up by asking the Wine build whether it implements `RoResolveNamespace`, not by version number.

---

## [2026-10-10] - Wine 11.18/11.19 and WebView2 Install Fix

### Changed

#### Wine versions replaced with 11.18 and 11.19
- **Installer now offers only Wine 11.19 (Recommended) and Wine 11.18 (fallback)**
  - Removed 9.14, 10.10, 11.12, and 11.12-v4 options from all version pickers in `AffinityLinuxInstaller.py`
  - Both builds come from [Affinity-Wine-Builder](https://github.com/ryzendew/Affinity-Wine-Builder/releases/tag/11.18)
  - 11.19: full Affinity patch set through 0085 (Direct2D throughput/brush-latency, wined3d Vulkan presentation, OpenCL dispatcher, color/printing/login fixes)
  - 11.18: login fix + performance patches (D2D geometry cache, OpenCL cache, SDR white-level, printer mapping)
- **Updated documentation** (`README.md`, `docs/WINE-VERSIONS.md`, `docs/INSTALLATION.md`, `docs/Known-issues.md`, `Guide/GUI-Installer-Guide.md`) to reference only 11.18/11.19

### Fixed

#### WebView2 Runtime stays on Windows 11 (Win7 breaks it)
- **WebView2 requires Windows 10 or higher — no Win7 anywhere in its path**
  - Pinning `msedgewebview2.exe` to Windows 7 makes it abort with "Microsoft Edge requires Windows 10 or higher"
  - The installer installs the runtime under Win11 and pins `msedgewebview2.exe` to Win11 explicitly
  - Removed the now-resolved "Microsoft Edge WebView2: Help Window Is Empty" entry from Known Issues
- **Removed the obsolete "Wine 11.12 skips the Canva sign-in fix" note** — both 11.18 and 11.19 carry the login metadata, so the fix applies on either

---

## [2025-12-04] - Documentation Restructure and Updates

### Added

#### Merged Pull Requests
- **[#91](https://github.com/ryzendew/AffinityOnLinux/pull/91)** - Implement GPU detection and selection in installer for multi-GPU users
  - Added GPU detection functionality to help users with multiple GPUs select the correct one
  - Enhanced `AffinityLinuxInstaller.sh` with 212+ lines of GPU selection logic
  - Improves compatibility for laptops and systems with integrated + dedicated GPUs

#### New Documentation Structure
- **Created comprehensive documentation files** in new `docs/` folder
  - `INSTALLATION.md` - Complete installation guide for all methods
  - `SYSTEM-REQUIREMENTS.md` - Supported distributions and dependencies
  - `WINE-VERSIONS.md` - Wine version information and recommendations
  - `HARDWARE-ACCELERATION.md` - GPU acceleration options guide
  - `LEGACY-SCRIPTS.md` - Command-line installation scripts documentation
  - `CONTRIBUTING.md` - Contributing guidelines for the project

#### Enhanced Documentation
- **OpenCL Guide improvements**
  - Added Fedora/Nobara installation instructions for AMD GPUs
  - Added Arch Linux installation instructions for AMD GPUs
  - Complete rewrite with professional structure, verification steps, and troubleshooting
- **Python GUI Dependencies section** in README
  - Added collapsible details section with installation commands for all supported distributions

### Changed

#### Documentation Organization
- **Major README restructure**
  - Separated detailed content into dedicated documentation files
  - Cleaner, more navigable structure with organized documentation links
  - Maintained quick start guide in README for easy access
- **Wine version updates**
  - Updated supported Wine versions to 9.14 and 10.10 only
  - Removed references to 10.4, 10.4 v2, and 10.11
  - Updated all documentation to reflect current Wine version support
- **Hardware Acceleration guide rewrite**
  - More natural, professional tone
  - Better organization and flow
  - Clearer explanations of vkd3d-proton, DXVK, and OpenCL options
- **Known Issues comprehensive update**
  - Added all current GitHub issues (#89, #68, #53, #10, #41)
  - Organized by category (Application Crashes, Installation Issues, Distribution-Specific, etc.)
  - Added workarounds and links to GitHub issues
  - Better structure with clear sections

### Removed

#### Deprecated Documentation
- **Removed WARP.md** - Developer documentation file no longer needed
- **Removed OtherSoftware-on-Linux.md** - Content no longer relevant
- Removed references to deprecated files from README

### Fixed

#### PyQt6 Import Issues on Fedora
- **Fixed QSvgWidget import failure** on Fedora and other distributions where SVG support is in a separate package
  - Added graceful fallback when `PyQt6.QtSvgWidgets.QSvgWidget` is not available
  - Installer now continues to work even when SVG widget is missing (with warning)
  - Some icons may not display correctly when SVG widget is unavailable
- **Updated Fedora installation instructions** to include `python3-pyqt6-svg` package
  - Added to both README and installation documentation

#### Merged Pull Requests
- **[#90](https://github.com/ryzendew/AffinityOnLinux/pull/90)** - Fixed missing `fi` statement in shell script
  - Corrected syntax error in `AffinityLinuxInstaller.sh` that could cause script failures
  - Ensures proper script execution flow

#### Documentation Accuracy
- **Updated all cross-references** after file reorganization
- Fixed relative paths in documentation files after moving to `docs/` folder
- Updated Wine version references throughout all documentation files
- **Added window management crash issue** to known issues
  - Documented UI element moving causing crashes ([#108](https://github.com/ryzendew/Linux-Affinity-Installer/issues/108))
  - Clarified this is a Wine limitation that cannot be fixed
- **Added AppImage memory issue** to known issues
  - Documented excessive RAM usage and random crashes ([#106](https://github.com/ryzendew/Linux-Affinity-Installer/issues/106))
  - Noted this appears to be a random bug affecting the AppImage build
- **Added login/authentication issue** to known issues
  - Documented that logging into Affinity applications does not work due to Wine limitations
  - Clarified that applications work fully offline without authentication

### Technical Details

#### Files Modified
- `README.md` - Complete restructure with organized documentation links
- `docs/INSTALLATION.md` - New comprehensive installation guide
- `docs/SYSTEM-REQUIREMENTS.md` - New system requirements documentation
- `docs/WINE-VERSIONS.md` - Updated Wine version information
- `docs/HARDWARE-ACCELERATION.md` - Complete rewrite for better clarity
- `docs/OpenCL-Guide.md` - Professional rewrite with new installation instructions
- `docs/Known-issues.md` - Comprehensive update with current GitHub issues
- `docs/LEGACY-SCRIPTS.md` - New documentation file
- `docs/CONTRIBUTING.md` - New contributing guidelines

#### Files Removed
- `docs/WARP.md` - Deprecated developer documentation
- `docs/OtherSoftware-on-Linux.md` - No longer relevant

#### Statistics
- **New documentation files**: 6
- **Files removed**: 2
- **Files restructured**: 8
- **Documentation lines added**: ~500+
- **Documentation lines rewritten**: ~300+

---

### Summary

This update focused on improving documentation organization and accuracy:

1. **Better structure** - Separated long README into focused documentation files
2. **Cleaner organization** - All documentation now in dedicated `docs/` folder
3. **Updated information** - Wine versions, known issues, and installation instructions all current
4. **Professional presentation** - Rewritten guides with better clarity and natural tone
5. **Easier navigation** - Clear documentation links and organized sections

All documentation now reflects current project state and provides better user guidance.

---

## [2025-11-06] - Development Session

### Added

#### Enhanced Logging System
- **Comprehensive logging implementation** in `AffinityLinuxInstaller.py`
  - Added extensive logging throughout the installer script
  - Improved error tracking and debugging capabilities
  - Enhanced user feedback during installation processes
  - 290+ lines of logging code added

#### AMD GPU Support Enhancement
- **New launch option for Affinity v3 without OpenCL**
  - Added dedicated button/option for AMD users experiencing OpenCL compatibility issues
  - Created `AffinityWine10.17.sh` script (1,631 lines)
  - Provides alternative launch method for better AMD GPU compatibility

#### Funding and Sponsorship
- **Added funding support options**
  - Implemented Ko-fi integration
  - Added custom sponsorship link support
  - Created `.github/FUNDING.yml` configuration file

### Fixed

#### Font Rendering Issues
- **Resolved font display problems** across all Affinity application launchers
  - Fixed font issues in `AffinityDesigner.sh`
  - Fixed font issues in `AffinityPhoto.sh`
  - Fixed font issues in `AffinityPublisher.sh`
  - Fixed font issues in `Affinityv3.sh`
  - Fixed font issues in `AffinityLinuxInstaller.py`
  - Fixed font issues in `AffinityLinuxInstaller.sh`
  - Improved font handling and rendering consistency

### Changed

#### Documentation Updates
- **README.md improvements**
  - Updated project image/reference
  - Enhanced documentation content and clarity
  - Multiple iterative improvements to documentation structure
  - 122+ lines of documentation updates

#### Installer Enhancements
- **Major installer script improvements**
  - Significant code refactoring and feature additions
  - Enhanced user experience and error handling
  - Improved installation workflow
  - 626+ lines of code changes in `AffinityLinuxInstaller.py`

### Technical Details

#### Files Modified
- `AffinityScripts/AffinityLinuxInstaller.py` - Major updates with logging and features
- `AffinityScripts/AffinityWine10.17.sh` - New file for AMD OpenCL workaround
- `AffinityScripts/AffinityDesigner.sh` - Font fixes
- `AffinityScripts/AffinityPhoto.sh` - Font fixes
- `AffinityScripts/AffinityPublisher.sh` - Font fixes
- `AffinityScripts/Affinityv3.sh` - Font fixes
- `AffinityScripts/AffinityLinuxInstaller.sh` - Font fixes
- `README.md` - Documentation updates
- `.github/FUNDING.yml` - New funding configuration

#### Statistics
- **Total commits**: 11
- **Lines added**: ~2,000+
- **Lines modified**: ~100+
- **New files**: 2
- **Files modified**: 7

---

### Summary

This development session focused on improving the overall user experience and stability of the Affinity on Linux project. Key achievements include:

1. **Enhanced debugging capabilities** through comprehensive logging
2. **Better AMD GPU support** with dedicated OpenCL workaround
3. **Improved font rendering** across all application launchers
4. **Expanded funding options** for project sustainability
5. **Documentation improvements** for better user guidance

All changes maintain backward compatibility while adding new features and fixing critical issues.


