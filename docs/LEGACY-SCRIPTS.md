# Legacy Scripts

Command-line installers for users who prefer terminal-based installation.

## All-in-One Installer

Install any Affinity application with automatic dependency management:

```bash
bash -c "$(curl -s https://raw.githubusercontent.com/ryzendew/AffinityOnLinux/refs/heads/main/AffinityScripts/AffinityLinuxInstaller.sh)"
```

## Individual Application Installers

### Affinity Photo

```bash
bash -c "$(curl -s https://raw.githubusercontent.com/ryzendew/AffinityOnLinux/refs/heads/main/AffinityScripts/AffinityPhoto.sh)"
```

### Affinity Designer

```bash
bash -c "$(curl -s https://raw.githubusercontent.com/ryzendew/AffinityOnLinux/refs/heads/main/AffinityScripts/AffinityDesigner.sh)"
```

### Affinity Publisher

```bash
bash -c "$(curl -s https://raw.githubusercontent.com/ryzendew/AffinityOnLinux/refs/heads/main/AffinityScripts/AffinityPublisher.sh)"
```

### Affinity v3 (Unified)

```bash
bash -c "$(curl -s https://raw.githubusercontent.com/ryzendew/AffinityOnLinux/refs/heads/main/AffinityScripts/Affinityv3.sh)"
```

## Ubuntu/NVIDIA Launcher Snapshot

For the current Ubuntu + KDE/Wayland + NVIDIA working state, this repo now also contains a standalone launcher snapshot:

```bash
bash AffinityScripts/AffinityUbuntuLauncher.sh status
bash AffinityScripts/AffinityUbuntuLauncher.sh desktop
bash AffinityScripts/AffinityUbuntuLauncher.sh launch
```

This script does not require the Python GUI installer at runtime. It preserves the currently working launch path:

- Forces Wine to use the X11 driver inside Wayland sessions
- Applies the known-good NVIDIA offload and Vulkan environment variables
- Disables `VK_KHR_present_id` and `VK_KHR_present_wait` on Wayland
- Can rewrite the desktop launcher so future starts use the same script

## Affinity Updater

Update existing installations without full reinstallation:

```bash
bash -c "$(curl -s https://raw.githubusercontent.com/ryzendew/AffinityOnLinux/refs/heads/main/AffinityScripts/AffinityUpdater.sh)"
```

## Note

For most users, the [Python GUI Installer](INSTALLATION.md#2-python-gui-installer-recommended-for-full-features) is recommended as it provides a better user experience and more features.
