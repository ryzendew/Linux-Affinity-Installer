#!/bin/bash

################################################################################
# Affinity OAuth URL Handler
# Sends the affinity:// callback URL to the running Affinity instance via
# named pipe IPC, avoiding the TypeLoadException that occurs when Wine
# launches a second Affinity.exe for the protocol handler.
#
# Register as the affinity:// protocol handler:
#   xdg-mime default affinity-url-handler.desktop x-scheme-handler/affinity
################################################################################

# Enforce bash execution
if [ -z "$BASH_VERSION" ]; then
    exec bash "$0" "$@"
fi

WINEPREFIX="${WINEPREFIX:-$HOME/.AffinityLinux}"
WINE="${WINE:-$WINEPREFIX/ElementalWarriorWine/bin/wine}"
WINE_DIR="$(dirname "$WINE")"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Use XDG_RUNTIME_DIR for per-user log (avoids world-readable /tmp)
_RUNTIME="${XDG_RUNTIME_DIR:-/tmp}"
LOG="$_RUNTIME/affinity-url-handler.log"

URL="$1"
# Log scheme and host only — OAuth callback URLs contain tokens
URL_REDACTED="${URL%%\?*}"
echo "[$(date)] AffinityURLHandler called with: $URL_REDACTED" >> "$LOG"

if [ -z "$URL" ]; then
    echo "[$(date)] ERROR: No URL provided" >> "$LOG"
    exit 1
fi

# Validate URL starts with affinity://
case "$URL" in
    affinity://*)
        ;;
    *)
        echo "[$(date)] ERROR: Not an affinity:// URL: $URL_REDACTED" >> "$LOG"
        exit 1
        ;;
esac

# Check Wine binary exists
if [ ! -x "$WINE" ]; then
    echo "[$(date)] ERROR: Wine not found at $WINE" >> "$LOG"
    exit 1
fi

# Find the AffinitySendURL.exe tool
SENDURL_EXE=""
for candidate in \
    "$WINEPREFIX/tools/AffinitySendURL.exe" \
    "$SCRIPT_DIR/AffinitySendURL.exe" \
    "$WINEPREFIX/Patch/SharedStorageAccessManagerFix/AffinitySendURL.exe"; do
    if [ -f "$candidate" ]; then
        SENDURL_EXE="$candidate"
        break
    fi
done

if [ -z "$SENDURL_EXE" ]; then
    echo "[$(date)] ERROR: AffinitySendURL.exe not found" >> "$LOG"
    exit 1
fi

SENDURL_WIN=$("$WINE_DIR/winepath" -w "$SENDURL_EXE" 2>/dev/null || echo "Z:${SENDURL_EXE//\//\\\\}")

echo "[$(date)] WINEPREFIX=$WINEPREFIX" >> "$LOG"
echo "[$(date)] WINE=$WINE" >> "$LOG"
echo "[$(date)] SENDURL_EXE=$SENDURL_EXE" >> "$LOG"
echo "[$(date)] Sending URL to Affinity via named pipe..." >> "$LOG"
WINEPREFIX="$WINEPREFIX" "$WINE" "$SENDURL_WIN" "$URL" >> "$LOG" 2>&1
EXIT_CODE=$?
echo "[$(date)] sendurl exit code: $EXIT_CODE" >> "$LOG"
exit $EXIT_CODE
