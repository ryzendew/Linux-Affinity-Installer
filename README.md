# AffinityOnLinux

Here is my Own project! https://github.com/Event-Horizon-desktop-environment/pittore-studio/releases/tag/0.1.0 Feel free to test and report issues or features requests
<img width="2560" height="1364" alt="image" src="https://github.com/user-attachments/assets/f70d4d0a-d2d6-4929-a166-7d832d66ba1f" />



> **⚠️ IMPORTANT: Before Opening Issues**
> 
> **DO NOT open GitHub issues until you have:**
> - Read this README completely
> - Read all documentation pages (Installation Guide, Known Issues, System Requirements, etc.)
> - Searched existing issues for similar problems
> - Checked the [Known Issues](docs/Known-issues.md) page
> 
> **Issues opened without reading the documentation will be closed immediately.**
> 
> Please take the time to read through all the documentation - it contains answers to most common questions and problems.

---

A comprehensive solution for running [Affinity software](https://www.affinity.studio/) on GNU/Linux systems using Wine with hardware acceleration support.

<img width="1277" height="1361" alt="image" src="https://github.com/user-attachments/assets/8def9258-46f4-4301-be0f-9e8ebd70bd01" />


## What is This?

AffinityOnLinux provides an easy way to install and run Affinity Photo, Designer, Publisher, and the unified Affinity v3 application on Linux. The installer automatically sets up Wine (a compatibility layer for running Windows applications) with all necessary configurations, dependencies, and optimizations.

## What the installer does

One run of **One-Click Full Setup** gives you a working Affinity:

- **Wine with the Affinity patches.** Wine 11.19 (recommended) or 11.18, built with a set of patches for Affinity: the interface rendered on the GPU, lower brush and pan lag, drag and drop from the file manager, pen pressure, Help pages, and much more. See [Wine Versions](docs/WINE-VERSIONS.md). Every download is checked against a pinned SHA-256 and refused if it differs.
- **The Windows parts Affinity needs:** .NET Framework 4.8, the core fonts, the Visual C++ runtime and MSXML. Affinity's .NET code is compiled ahead of time for a faster start.
- **Affinity itself**, from Serif's installer (downloaded for you, or a file you already have), with Affinity's settings fixes applied.
- **GPU rendering** through vkd3d-proton (or DXVK on AMD), and OpenCL where your driver provides it. See [Hardware Acceleration](docs/HARDWARE-ACCELERATION.md).
- **Help** works: the WebView2 runtime is installed with Affinity.
- **WineFix** and its plugin loader, for fixes inside Affinity that Wine cannot make: the color picker, the Leading dropdown, the sub-tool panel's columns, crashes at startup.
- **Your desktop**: an Affinity entry in the application menu, a desktop icon, **double-clicking an Affinity document** in your file manager opens it in Affinity, and the Canva sign-in completes in the browser.
- **Checks at the end** of the install: font registrations and the renderer setting are verified and repaired.

Afterwards, the same window updates or switches the Wine build without touching your settings, repairs the document handler and the Canva sign-in, and opens Wine's own tools.

The installer sets up one Affinity, in `~/.AffinityLinux` unless you choose another folder, and points your menu and documents at it. Installing again into another folder moves them there.

## Quick Start

**New to Linux or want the easiest option?** Use the AppImage:

1. Download the AppImage from [GitHub Releases](https://github.com/ryzendew/AffinityOnLinux/releases/latest)
2. Make it executable: `chmod +x Affinity-3-x86_64.AppImage`
3. Run it: `./Affinity-3-x86_64.AppImage`

**Want full features and latest updates?** Use the Python GUI Installer:

```bash
curl -sSL https://raw.githubusercontent.com/ryzendew/AffinityOnLinux/refs/heads/main/AffinityScripts/AffinityLinuxInstaller.py | python3
```

> **This fork.** The command above is upstream's installer. This fork carries
> the Affinity 3.3 work described above and installs with:
>
> ```bash
> curl -sSL https://github.com/jfacemyer/Linux-Affinity-Manager/raw/main/AffinityScripts/AffinityLinuxInstaller.py | python3
> ```
>
> or from a clone, which needs no downloads for its own files:
>
> ```bash
> git clone https://github.com/jfacemyer/Linux-Affinity-Manager.git
> python3 Linux-Affinity-Manager/AffinityScripts/AffinityLinuxInstaller.py
> ```
>
> The download sources that are forks rather than upstream are listed, with
> what each must become, in [`AffinityHandler/README.md`](AffinityHandler/README.md#temporary-download-sources--must-be-repointed-before-merging).

## More than one Affinity? The manager

[**Affinity on Linux Manager**](AffinityManager/README.md) is optional, and changes nothing about the installer above. Use it when one install is not enough:

- **Several prefixes side by side**, such as a working install and a copy to try a new Wine build in, each installed by this installer running inside the manager.
- **The Default**: choose which install your menu, double-clicked documents and the Canva sign-in use, and give the others menu entries of their own.
- **Back up, restore, clone and snapshot** installs, and copy settings and drive letters from one to another.
- **Repairs** on existing installs (fonts, renderer), cleaning up old Wine builds, renaming and moving installs, and launching that never starts Affinity twice.

```bash
curl -sSL https://github.com/jfacemyer/Linux-Affinity-Manager/raw/main/AffinityManager/run.py | python3
```

It needs PyQt6, which the installer needs anyway, and installs nothing on your system. See the [manager's README](AffinityManager/README.md).

<details>
<summary><strong>Python GUI Dependencies</strong></summary>

The installer will attempt to install PyQt6 automatically if missing. If automatic installation fails, install it manually:

**Arch/Artix/CachyOS/EndeavourOS/XeroLinux:**
```bash
sudo pacman -S python-pyqt6
```

**Fedora/Nobara:**
```bash
sudo dnf install python3-pyqt6 python3-pyqt6-svg
```

**openSUSE (Tumbleweed/Leap):**
```bash
sudo zypper install python313-PyQt6
```

**PikaOS:** 
```bash
sudo apt install python3-pyqt6.qtsvg
```

**Ubuntu 25.10:** If you encounter GUI issues, also install:
```bash
sudo apt install python3-pyqt6.qtsvg
```

</details>

## Documentation

### Getting Started
- **[Installation Guide](docs/INSTALLATION.md)** - Complete installation instructions for all methods
- **[System Requirements](docs/SYSTEM-REQUIREMENTS.md)** - Supported distributions and dependencies
- **[GUI Installer Guide](Guide/GUI-Installer-Guide.md)** - Step-by-step GUI installer instructions

### Technical Details
- **[Wine Versions](docs/WINE-VERSIONS.md)** - Available Wine versions and recommendations
- **[Hardware Acceleration](docs/HARDWARE-ACCELERATION.md)** - GPU acceleration options (vkd3d-proton, DXVK, OpenCL)
- **[OpenCL Guide](docs/OpenCL-Guide.md)** - Detailed OpenCL configuration
- **[Legacy Scripts](docs/LEGACY-SCRIPTS.md)** - Command-line installation scripts

### Per-Distribution Dependencies
- **[Arch Linux](docs/Arch-Linux.md)** - Arch, Artix, CachyOS, EndeavourOS, XeroLinux
- **[Fedora](docs/Fedora.md)** - Fedora, Nobara
- **[Ubuntu](docs/Ubuntu.md)** - Ubuntu (24.04+ and older)
- **[Linux Mint](docs/Linux-Mint.md)**
- **[Zorin OS](docs/Zorin-OS.md)**
- **[Pop!_OS](docs/Pop-OS.md)**
- **[PikaOS](docs/PikaOS.md)**
- **[openSUSE](docs/openSUSE.md)** - Tumbleweed, Leap

### Additional Resources
- **[Known Issues](docs/Known-issues.md)** - Common problems and solutions
- **[Settings Guide](Guide/Settings.md)** - Configuration options

## Getting Help

- **Discord Community:** [Join our Discord server](https://discord.gg/DW2X8MHQuh) for support and discussions
- **GitHub Issues:** Report bugs and request features on GitHub
- **Documentation:** Check the guides and documentation linked above

## Important Notes

### Support Limitations

- **AMD/Intel GPU Issues:** I cannot fix OpenCL or Wine GPU bugs for AMD/Intel GPUs as I do not have access to these GPUs for testing. Use vkd3d-proton or DXVK instead (see [Hardware Acceleration](docs/HARDWARE-ACCELERATION.md)).
- **Unsupported Distributions:** No support provided for Bazzite, Manjaro. Use AppImage at your own risk (see [System Requirements](docs/SYSTEM-REQUIREMENTS.md)).

## Contributing

Contributions are welcome! See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines.

## License

This project provides installation scripts and configurations for running Affinity software on Linux. Affinity software is a commercial product by Serif (Europe) Ltd. Please ensure you have a valid license before installing.

---

**Disclaimer:** This project is not affiliated with, endorsed by, or associated with Serif (Europe) Ltd. All trademarks and registered trademarks are the property of their respective owners.
