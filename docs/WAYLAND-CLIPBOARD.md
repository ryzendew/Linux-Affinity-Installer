# Wayland Clipboard: Paste Images and Files into Affinity

## Symptom

On a Wayland desktop, text can be copied into Affinity, but either of these fails:

- copying pixels from Spectacle, a browser, or an image editor and pressing `Ctrl+V` in Affinity;
- copying a PNG or another file in a Wayland file manager and pressing `Ctrl+V` in Affinity.

This workaround applies when Affinity runs through Wine's `winex11.drv` on Xwayland.

## Why it happens

The clipboard has different formats for different operations:

| Copy operation | Wayland MIME type | Wine/Windows format |
| --- | --- | --- |
| Plain text | `text/plain` | `CF_UNICODETEXT` |
| Copied file(s) | `text/uri-list` | `CF_HDROP` |
| Copied image pixels | `image/png` | registered `PNG` format |

KDE/Klipper and Xwayland generally synchronize plain text, but may drop `text/uri-list` and `image/png` on the Wayland-to-X11 path. Wine never receives those formats, so Affinity has nothing useful to paste.

`winewayland.drv` can theoretically avoid Xwayland, but it currently causes dead clipboard or rendering issues on some ElementalWarrior Wine/Affinity setups. The bridge below keeps the known-working X11 graphics path and mirrors only the missing clipboard formats.

## Requirements

Install `wl-clipboard`, `xclip`, and Python 3.

### Arch, Artix, CachyOS, EndeavourOS

```bash
sudo pacman -S wl-clipboard xclip python
```

### Fedora or Nobara

```bash
sudo dnf install wl-clipboard xclip python3
```

### Ubuntu, Debian, Linux Mint, Pop!_OS, Zorin OS

```bash
sudo apt install wl-clipboard xclip python3
```

### openSUSE

```bash
sudo zypper install wl-clipboard xclip python3
```

## Install the bridge

```bash
mkdir -p ~/.local/bin ~/.config/systemd/user
curl -fsSL \
  https://raw.githubusercontent.com/ryzendew/Linux-Affinity-Installer/main/AffinityScripts/AffinityClipboardBridge.py \
  -o ~/.local/bin/affinity-clipboard-bridge.py
curl -fsSL \
  https://raw.githubusercontent.com/ryzendew/Linux-Affinity-Installer/main/AffinityScripts/affinity-clipboard-bridge.service \
  -o ~/.config/systemd/user/affinity-clipboard-bridge.service
chmod 700 ~/.local/bin/affinity-clipboard-bridge.py
systemctl --user daemon-reload
systemctl --user enable --now affinity-clipboard-bridge.service
```

Check that it is running:

```bash
systemctl --user status affinity-clipboard-bridge.service
journalctl --user -u affinity-clipboard-bridge.service -f
```

On KDE Plasma and GNOME, `graphical-session.target` normally starts the service
with `DISPLAY` and `WAYLAND_DISPLAY` already imported. Sway and Hyprland users
must add the compositor-specific startup commands in
[Troubleshooting](#wayland-display-or-display-is-not-set). The service restarts
after transient failures, but not after a missing-session error (exit status 2).

## What the bridge does

- reacts to clipboard-change events via `wl-paste --watch` instead of polling;
- mirrors only `image/png` and `text/uri-list` from Wayland to X11;
- passes PNG data as raw bytes (no text conversion);
- rejects payloads larger than 256 MiB before they can exhaust memory;
- uses SHA-256 deduplication to prevent image feedback loops;
- canonicalizes URI-list line endings to prevent a slow newline feedback loop;
- does not change Wine, DXVK, VKD3D, or the Affinity prefix.

The daemon does not mirror plain text. However, `xclip` becomes the X11
selection owner for one MIME target. A source selection that originally exposed
several formats can therefore be reduced to the mirrored image or URI-list
target after Xwayland synchronizes it back. Disable the bridge if that trade-off
conflicts with another clipboard workflow.

Do not replace the script with a shell expression such as `content=$(wl-paste)`. Shell command substitution cannot preserve NUL bytes and corrupts PNG clipboard data.

## Verify

Copy image pixels in Spectacle and run:

```bash
wl-paste --list-types
# Must include image/png

wl-paste --type image/png | sha256sum
xclip -selection clipboard -o -t image/png | sha256sum
# Both hashes should match.
```

For a file copied in a Wayland file manager:

```bash
wl-paste --list-types
# Must include text/uri-list

xclip -selection clipboard -o -t TARGETS
# Must include text/uri-list.
```

Finally, paste into Affinity. Clipboard format inspection alone does not prove that the application accepts the data.

## Uninstall

```bash
systemctl --user disable --now affinity-clipboard-bridge.service
rm ~/.config/systemd/user/affinity-clipboard-bridge.service
rm ~/.local/bin/affinity-clipboard-bridge.py
systemctl --user daemon-reload
```

This removes only the bridge. It does not modify or remove Affinity or its Wine prefix.

## Troubleshooting

### Service exits with “Required command not found”

Install both `wl-clipboard` and `xclip`, then restart the service:

```bash
systemctl --user restart affinity-clipboard-bridge.service
```

### `WAYLAND_DISPLAY` or `DISPLAY` is not set

The systemd user manager must inherit the graphical-session environment. A
manual repair for the current login is:

```bash
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR
systemctl --user restart affinity-clipboard-bridge.service
```

For Sway, make that persistent by adding these lines to the Sway config:

```text
exec systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR
exec systemctl --user start affinity-clipboard-bridge.service
```

For Hyprland, add:

```text
exec-once = systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XDG_RUNTIME_DIR
exec-once = systemctl --user start affinity-clipboard-bridge.service
```

Other compositors need equivalent session-start commands. Verify the imported
values with:

```bash
systemctl --user show-environment | grep -E '^(DISPLAY|WAYLAND_DISPLAY)='
```

### Payload is too large

The default limit is 256 MiB. An oversized selection is rejected and logged as
`too-large`. To choose a different bounded limit, add `--max-bytes BYTES` to the
service's `ExecStart` line, run `systemctl --user daemon-reload`, and restart the
service.

### Text works but copied images do not

Inspect `wl-paste --list-types`. A Spectacle pixel copy should offer `image/png`. Copying only a filename or path as text is a different operation and will not create image clipboard data.
