# Installation Guide

This guide covers all installation methods for AffinityOnLinux.

## Quick Start

**New to Linux or want the easiest option?** Use the AppImage:

1. Download the AppImage from [GitHub Releases](https://github.com/ryzendew/AffinityOnLinux/releases/latest)
2. Make it executable: `chmod +x Affinity-3-x86_64.AppImage`
3. Run it: `./Affinity-3-x86_64.AppImage`

**Want full features and latest updates?** Use the Python GUI Installer:

```bash
curl -sSL https://raw.githubusercontent.com/ryzendew/AffinityOnLinux/refs/heads/main/AffinityScripts/AffinityLinuxInstaller.py | python3
```

## Installation Methods

### 1. AppImage (Recommended for Beginners)

The AppImage is a portable, self-contained installer that works on most Linux distributions without requiring system-wide dependencies.

**Best for:**
- Users on unsupported distributions (Bazzite, Linux Mint, Zorin OS, Manjaro, Ubuntu, Pop!_OS)
- Users who prefer not to install Python/PyQt6 system-wide
- Quick testing or portable installations
- Older CPUs (use AppImage v2 for best compatibility)

**Features:**
- ✅ No installation required - just download and run
- ✅ Self-contained - includes all dependencies
- ✅ DXVK support for excellent graphics performance
- ✅ Full GUI installer functionality

**Limitations:**
- Does not include OpenCL/vkd3d support (use Python GUI installer for this)
- Uses DXVK by default (which is recommended for most users)

**CPU Compatibility:** AppImage v2 works on any CPU. Other versions may have issues on older CPUs.

### 2. Python GUI Installer (Recommended for Full Features)

A modern graphical installer with comprehensive features and automatic dependency management.

**Best for:**
- Users on supported distributions
- Users who need OpenCL/vkd3d support
- Permanent installations
- Users who want the latest features

**Features:**
- One-click full setup with automatic dependency installation
- Multiple Wine versions to choose from (11.21 recommended, 11.20 fallback)
- Wine version switching without reinstalling applications
- Automatic WebView2 Runtime installation for Affinity v3
- DPI scaling configuration
- Comprehensive troubleshooting tools
- Real-time status monitoring

**Installation:**

```bash
# Run directly from GitHub (recommended)
curl -sSL https://raw.githubusercontent.com/ryzendew/AffinityOnLinux/refs/heads/main/AffinityScripts/AffinityLinuxInstaller.py | python3

# Or download and run locally
curl -sSL https://raw.githubusercontent.com/ryzendew/AffinityOnLinux/refs/heads/main/AffinityScripts/AffinityLinuxInstaller.py -o install.py && python3 install.py
```

**Dependencies:** The installer will attempt to install PyQt6 automatically if missing. For manual installation, see the [Python GUI Dependencies](#python-gui-dependencies) section below.

**Usage:**
1. Run the installer
2. Click **"One-Click Full Setup"** for automatic configuration
3. Choose your Wine version (11.21 recommended, 11.20 fallback)
4. Use **"Update Affinity Applications"** to install or update Affinity apps
5. Check the status log to see what's installed

📖 **Detailed Guide:** See the [GUI Installer Guide](../Guide/GUI-Installer-Guide.md) for step-by-step instructions.

### 3. Legacy Shell Scripts

Command-line installers for users who prefer terminal-based installation.

**Available Scripts:**
- **All-in-One Installer** - Install any Affinity application
- **Individual Installers** - Affinity Photo, Designer, Publisher, or v3 (Unified)
- **Affinity Updater** - Update existing installations

See the [Legacy Scripts Guide](LEGACY-SCRIPTS.md) for details.

## Python GUI Dependencies

If the installer cannot automatically install PyQt6, install it manually:

**Arch/CachyOS/EndeavourOS/XeroLinux:**
```bash
sudo pacman -S python-pyqt6
```

**Fedora/Nobara:**
```bash
sudo dnf install python3-pyqt6
```

**openSUSE (Tumbleweed/Leap):**
```bash
sudo zypper install python313-PyQt6
```

**PikaOS:** Does not work with GUI installer. Use [AppImage](#1-appimage-recommended-for-beginners) instead.

**Ubuntu 25.10:** If you encounter GUI issues, also install:
```bash
sudo apt install python3-pyqt6.qtsvg
```

## Supported Applications

The installer supports all Affinity applications:

- **Affinity Photo** - Professional photo editing
- **Affinity Designer** - Vector graphic design
- **Affinity Publisher** - Desktop publishing
- **Affinity v3 (Unified)** - All-in-one application combining Photo, Designer, and Publisher

