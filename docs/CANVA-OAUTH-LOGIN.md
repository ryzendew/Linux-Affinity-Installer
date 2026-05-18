# Canva OAuth Login for Affinity

This document describes the patches required to enable Canva sign-in and
OAuth authentication for Affinity Suite running under Wine.

## Overview

Canva sign-in requires three fixes:

1. **TLS relay** -- bridge Wine-Mono's legacy TLS to modern ciphers
2. **IL patch** -- bypass a WinRT type that Wine can't resolve
3. **Named pipe IPC** -- deliver the OAuth callback URL without crashing

## Fix 1: TLS Relay

**Location:** `AffinityScripts/AffinityTLSRelay.sh`

Wine-Mono's TLS implementation lacks ECDHE ciphers required by
`affinity.api.serifservices.com`. The TLS relay uses `socat` to accept
connections on localhost port 443 with legacy RSA+ECDHE ciphers, then
proxies them to the real server using the system's modern TLS stack.

### One-time setup

```bash
# Run the automated setup
AffinityScripts/AffinityTLSRelay.sh setup
```

This does three things:
1. Adds `127.0.0.1 affinity.api.serifservices.com` to `/etc/hosts`
2. Grants socat the `cap_net_bind_service` capability for port 443
3. Generates a self-signed certificate for the local relay

### Dependencies
- `socat`
- `openssl` (for certificate generation)
- `dig` (from `bind-tools` or `dnsutils`)

## Fix 2: SharedStorageAccessManager IL Patch

**Location:** `Patch/SharedStorageAccessManagerFix/`

Affinity's `ProcessCommandLineArguments` method references the WinRT type
`SharedStorageAccessManager` in its `affinity-open-file:` handler. Wine's
`RoResolveNamespace` is stubbed, so the CLR can't resolve this type. The
resulting `TypeLoadException` crashes the JIT for the **entire method**,
not just the unreachable branch -- which also breaks the `affinity://`
OAuth callback handler in the same method.

The fix uses Mono.Cecil to retarget the `brfalse` guard instruction to
skip the SSA block entirely, jumping past it to the `leave` instruction.

### Building

```bash
cd Patch/SharedStorageAccessManagerFix
dotnet build -c Release
```

### Running

```bash
dotnet Patch/SharedStorageAccessManagerFix/bin/Release/net8.0/SharedStorageAccessManagerFix.dll \
    "$WINEPREFIX/drive_c/Program Files/Affinity/Affinity/Serif.Affinity.dll"
```

The patcher is idempotent and must be re-run after Affinity updates.

## Fix 3: Named Pipe IPC (AffinitySendURL)

**Location:** `Patch/SharedStorageAccessManagerFix/AffinitySendURL.cs`
**URL Handler:** `AffinityScripts/AffinityURLHandler.sh`

When the user clicks "Sign in with Canva" in Affinity, the browser
redirects to an `affinity://` callback URL. The OS would normally launch
a second `Affinity.exe` to handle this URL, but that second instance
hits the same TypeLoadException crash.

Instead, `AffinitySendURL.exe` sends the callback URL to the running
Affinity instance via its `Affinity3Release` named pipe (the same pipe
Affinity uses for single-instance enforcement).

### Building

Compile with Wine's Mono and place the output next to the URL handler script
(so `AffinityURLHandler.sh` finds it automatically via `$SCRIPT_DIR`):

```bash
WINE="$HOME/.AffinityLinux/ElementalWarriorWine/bin/wine"
SCRIPT_DIR="/path/to/AffinityScripts"

cd Patch/SharedStorageAccessManagerFix
$WINE mcs -out:"$SCRIPT_DIR/AffinitySendURL.exe" AffinitySendURL.cs
```

### Registering the URL handler

A template `.desktop` file is included at
`AffinityScripts/affinity-url-handler.desktop`. Install it by updating the
`Exec=` path and copying to your applications directory:

```bash
SCRIPT_DIR="/path/to/AffinityScripts"

sed "s|PLACEHOLDER_SCRIPT_PATH|${SCRIPT_DIR}/AffinityURLHandler.sh|" \
    "$SCRIPT_DIR/affinity-url-handler.desktop" \
    > ~/.local/share/applications/affinity-url-handler.desktop

xdg-mime default affinity-url-handler.desktop x-scheme-handler/affinity
```

## Notes

- The pipe name `Affinity3Release` is derived from: Name + major version +
  BuildType. It may change with major Affinity version updates.
- The IL patch and TLS relay are independent -- you can use either without
  the other, but both are needed for full Canva sign-in flow.
