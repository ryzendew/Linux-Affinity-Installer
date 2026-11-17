# Wine Versions

The installer supports two Wine versions, both built from [Affinity-Wine-Builder](https://github.com/jfacemyer/Affinity-Wine-Builder/releases) and patched for Affinity compatibility:

| Version | Best For | Description |
|---------|----------|-------------|
| **11.21** (Recommended) | Most users | Latest build with the full Affinity patch set on Wine 11.21: Direct2D throughput and brush-latency fixes, Vulkan and OpenGL presentation fixes, OpenCL event dispatcher, pen pressure, plus color, printing, login and installer fixes |
| **11.20** | Fallback | Previous build: the same Affinity patch set on Wine 11.20. Use if 11.21 has issues |

Wine 11.18 (`11.18-r1`, with the Affinity login fix and performance patches) is still installable but no longer offered.

## Features

**Both versions include:**
- OpenCL support patches
- AMD GPU compatibility fixes
- Affinity-specific optimizations (WinRT/WinMetadata, window management, Direct2D)
- Canva sign-in (login metadata) support

The installer defaults to Wine 11.21. You can switch between versions anytime using the GUI installer.

## Download Links

The installer downloads these releases and checks each against a SHA-256 pinned in `AffinityLinuxInstaller.py`; a tarball that does not match is refused:

- 11.21: [`11.21-r6`](https://github.com/jfacemyer/Affinity-Wine-Builder/releases/tag/11.21-r6), `ElementalWarrior-wine-11.21.tar.xz`
- 11.20: [`11.20-r8`](https://github.com/jfacemyer/Affinity-Wine-Builder/releases/tag/11.20-r8), `ElementalWarrior-wine-11.20.tar.xz`
- 11.19: [`11.19-r10`](https://github.com/jfacemyer/Affinity-Wine-Builder/releases/tag/11.19-r10), `ElementalWarrior-wine-11.19.tar.xz`
- 11.18: [`11.18-r1`](https://github.com/jfacemyer/Affinity-Wine-Builder/releases/tag/11.18-r1), `ElementalWarrior-wine-11.18.tar.xz`

## Important Notes

### Wine 10.17 Warning

Wine 10.17 has major bugs and issues. This installer does not use it.
