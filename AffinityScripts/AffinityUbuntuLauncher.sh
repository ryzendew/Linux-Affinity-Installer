#!/usr/bin/env bash

set -euo pipefail

if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    CYAN=''
    BOLD=''
    NC=''
fi

log_info() {
    printf '%b[INFO]%b %s\n' "$CYAN" "$NC" "$1"
}

log_warn() {
    printf '%b[WARN]%b %s\n' "$YELLOW" "$NC" "$1"
}

log_error() {
    printf '%b[ERROR]%b %s\n' "$RED" "$NC" "$1" >&2
}

log_success() {
    printf '%b[OK]%b %s\n' "$GREEN" "$NC" "$1"
}

SCRIPT_PATH="$(readlink -f "$0")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PREFIX="${AFFINITY_PREFIX:-$HOME/.AffinityLinux}"
APP_EXE="${AFFINITY_EXE:-$PREFIX/drive_c/Program Files/Affinity/Affinity/Affinity.exe}"
ICON_PATH="${AFFINITY_ICON:-$HOME/.local/share/icons/Affinity.svg}"
DESKTOP_FILE="${AFFINITY_DESKTOP_FILE:-$HOME/.local/share/applications/Affinity.desktop}"
STARTUP_TIMEOUT="${AFFINITY_STARTUP_TIMEOUT:-25}"
AFFINITY_MAIN_WINDOW_PATTERN='"Affinity": ("affinity.exe" "affinity.exe")'

get_affinity_user_data_dir() {
    local username

    username="${USER:-${LOGNAME:-user}}"
    printf '%s\n' "$PREFIX/drive_c/users/$username/AppData/Roaming/Affinity/Affinity/3.0"
}

find_wine_binary() {
    local candidate
    for candidate in \
        "$PREFIX/ElementalWarriorWine/bin/wine" \
        "$PREFIX/ElementalWarrior-wine-10.10/bin/wine" \
        "$PREFIX/ElementalWarrior-wine-11.0/bin/wine"; do
        if [ -x "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    if command -v wine >/dev/null 2>&1; then
        command -v wine
        return 0
    fi

    return 1
}

find_wineserver_binary() {
    local wine_bin="$1"
    local candidate

    candidate="$(dirname "$wine_bin")/wineserver"
    if [ -x "$candidate" ]; then
        printf '%s\n' "$candidate"
        return 0
    fi

    if command -v wineserver >/dev/null 2>&1; then
        command -v wineserver
        return 0
    fi

    return 1
}

detect_nvidia_pci_id() {
    local pci_id

    if command -v lspci >/dev/null 2>&1; then
        pci_id="$(
            lspci -nn |
            grep -iE 'VGA compatible controller|3D controller' |
            grep -i 'NVIDIA' |
            sed -n 's/.*\[\(10de:[0-9a-fA-F]\{4\}\)\].*/\1/p' |
            head -n 1
        )"
        if [ -n "$pci_id" ]; then
            printf '%s\n' "$pci_id"
            return 0
        fi
    fi

    return 1
}

set_wine_x11_driver() {
    "$WINE_BIN" reg add 'HKEY_CURRENT_USER\Software\Wine\Drivers' \
        /v Graphics \
        /t REG_SZ \
        /d x11 \
        /f >/dev/null 2>&1 || log_warn "Wine-Grafiktreiber konnte nicht auf X11 gesetzt werden."
}

affinity_process_running() {
    pgrep -f '[Aa]ffinity\.exe' >/dev/null 2>&1
}

has_visible_affinity_window() {
    if ! command -v xwininfo >/dev/null 2>&1; then
        return 1
    fi

    DISPLAY="${DISPLAY:-:0}" xwininfo -root -children -all 2>/dev/null |
        grep -F "$AFFINITY_MAIN_WINDOW_PATTERN" >/dev/null 2>&1
}

wait_for_affinity_window() {
    local timeout="${1:-$STARTUP_TIMEOUT}"
    local elapsed=0

    while [ "$elapsed" -lt "$timeout" ]; do
        if has_visible_affinity_window; then
            return 0
        fi

        if ! affinity_process_running; then
            return 1
        fi

        sleep 1
        elapsed=$((elapsed + 1))
    done

    has_visible_affinity_window
}

stop_affinity_runtime() {
    "$WINESERVER_BIN" -k >/dev/null 2>&1 || true
    sleep 2
}

quarantine_affinity_user_data() {
    local user_data_dir
    local backup_dir

    user_data_dir="$(get_affinity_user_data_dir)"
    if [ ! -d "$user_data_dir" ]; then
        return 0
    fi

    backup_dir="${user_data_dir}.backup-$(date +%Y%m%d-%H%M%S)"
    mv "$user_data_dir" "$backup_dir"
    mkdir -p "$user_data_dir"
    log_warn "Affinity v3-Benutzerprofil wurde nach $backup_dir verschoben."
    log_warn "Das bisherige Profil blieb erhalten; es wurde nichts geloescht."
}

start_affinity_process() {
    "$WINE_BIN" "$APP_EXE" &
    LAUNCH_PID=$!
}

require_installation() {
    if [ ! -f "$APP_EXE" ]; then
        log_error "Affinity.exe nicht gefunden: $APP_EXE"
        exit 1
    fi

    if ! WINE_BIN="$(find_wine_binary)"; then
        log_error "Kein Wine-Binary gefunden."
        exit 1
    fi

    if ! WINESERVER_BIN="$(find_wineserver_binary "$WINE_BIN")"; then
        log_error "Kein wineserver-Binary gefunden."
        exit 1
    fi
}

setup_runtime_env() {
    export WINEPREFIX="$PREFIX"
    export WINE="$WINE_BIN"
    export WINESERVER="$WINESERVER_BIN"
    export WINEDEBUG='-all,fixme-all'
    export WINEDLLOVERRIDES='d3d12=n,b;d3d12core=n,b;mscms=n,b'

    if [ -n "${DISPLAY:-}" ]; then
        export DISPLAY
    else
        export DISPLAY=':0'
    fi

    if [ -n "${XAUTHORITY:-}" ]; then
        export XAUTHORITY
    fi

    export __NV_PRIME_RENDER_OFFLOAD=1
    export __GLX_VENDOR_LIBRARY_NAME='nvidia'
    export __VK_LAYER_NV_optimus='NVIDIA_only'

    if NVIDIA_PCI_ID="$(detect_nvidia_pci_id)"; then
        export MESA_VK_DEVICE_SELECT="$NVIDIA_PCI_ID"
        export MESA_VK_DEVICE_SELECT_FORCE_DEFAULT_DEVICE=1
    else
        log_warn "NVIDIA PCI-ID konnte nicht automatisch erkannt werden; Vulkan Device Select bleibt unverändert."
    fi

    export DXVK_ASYNC=0
    export DXVK_CONFIG='d3d9.deferSurfaceCreation = True; d3d9.shaderModel = 1'
    export DXVK_LOG_LEVEL='none'
    export VKD3D_DEBUG='none'
    export VKD3D_CONFIG=''
    export VKD3D_FEATURE_LEVEL='12_1'
    export VKD3D_SHADER_DEBUG='none'
    export VKD3D_SHADER_MODEL='6_5'

    if [ "${XDG_SESSION_TYPE:-}" = 'wayland' ]; then
        export VKD3D_DISABLE_EXTENSIONS='VK_KHR_present_id,VK_KHR_present_wait'
        export VKD3D_CONFIG='swapchain_legacy'
    else
        export VKD3D_DISABLE_EXTENSIONS='VK_KHR_present_id'
    fi
}

print_status() {
    require_installation
    setup_runtime_env

    printf '%bAffinity Ubuntu Launcher%b\n' "$BOLD" "$NC"
    printf 'Repo: %s\n' "$REPO_ROOT"
    printf 'Prefix: %s\n' "$PREFIX"
    printf 'Wine: %s\n' "$WINE_BIN"
    printf 'Wineserver: %s\n' "$WINESERVER_BIN"
    printf 'Affinity: %s\n' "$APP_EXE"
    printf 'Session: %s\n' "${XDG_SESSION_TYPE:-unknown}"
    printf 'Renderer: Vulkan\n'
    printf 'VKD3D_DISABLE_EXTENSIONS=%s\n' "$VKD3D_DISABLE_EXTENSIONS"
    if [ -n "${VKD3D_CONFIG:-}" ]; then
        printf 'VKD3D_CONFIG=%s\n' "$VKD3D_CONFIG"
    fi
    if [ -n "${MESA_VK_DEVICE_SELECT:-}" ]; then
        printf 'MESA_VK_DEVICE_SELECT=%s\n' "$MESA_VK_DEVICE_SELECT"
    fi
}

launch_affinity() {
    require_installation
    setup_runtime_env
    set_wine_x11_driver

    log_info "Starte Affinity mit dem konservierten Ubuntu/NVIDIA-Laufzeitpfad."
    log_info "Wine: $WINE_BIN"
    log_info "Prefix: $PREFIX"

    if has_visible_affinity_window; then
        log_info "Affinity laeuft bereits mit sichtbarem Hauptfenster; kein zweiter Start."
        return 0
    fi

    if affinity_process_running; then
        log_warn "Affinity laeuft bereits ohne sichtbares Hauptfenster; stoppe den haengenden Startversuch."
        stop_affinity_runtime
    fi

    start_affinity_process
    if wait_for_affinity_window; then
        log_success "Affinity-Hauptfenster wurde erkannt."
        wait "$LAUNCH_PID"
        return $?
    fi

    if affinity_process_running; then
        log_warn "Affinity laeuft, aber es wurde kein sichtbares Hauptfenster erkannt."
        quarantine_affinity_user_data
        stop_affinity_runtime
        log_info "Starte Affinity mit frischem v3-Profil erneut."

        start_affinity_process
        if wait_for_affinity_window; then
            log_success "Affinity startete nach dem Profil-Reset wieder mit sichtbarem Hauptfenster."
            wait "$LAUNCH_PID"
            return $?
        fi
    fi

    log_error "Affinity konnte kein sichtbares Hauptfenster erzeugen."
    wait "$LAUNCH_PID" || true
    return 1
}

install_desktop_entry() {
    require_installation
    mkdir -p "$(dirname "$DESKTOP_FILE")"

    if [ ! -f "$ICON_PATH" ]; then
        if [ -f "$REPO_ROOT/icons/Affinity.png" ]; then
            ICON_PATH="$REPO_ROOT/icons/Affinity.png"
        else
            ICON_PATH='applications-graphics'
        fi
    fi

    cat >"$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=Affinity
Comment=Affinity mit konserviertem Ubuntu/NVIDIA-Launcher
Type=Application
Terminal=false
StartupNotify=true
StartupWMClass=affinity.exe
Path=$PREFIX
Icon=$ICON_PATH
Exec=$SCRIPT_PATH launch
Categories=Graphics;
EOF

    log_success "Desktop-Launcher geschrieben: $DESKTOP_FILE"
}

show_help() {
    cat <<EOF
AffinityUbuntuLauncher.sh

Verwendung:
  $(basename "$SCRIPT_PATH") launch
  $(basename "$SCRIPT_PATH") desktop
  $(basename "$SCRIPT_PATH") status

Befehle:
  launch   Startet Affinity mit dem aktuell funktionierenden Ubuntu/NVIDIA-Setup.
  desktop  Schreibt einen .desktop-Launcher, der dieses Skript nutzt.
  status   Zeigt den erkannten Laufzeitpfad und die aktiven Env-Variablen an.

Optionale Umgebungsvariablen:
  AFFINITY_PREFIX        Override fuer den Wine-Prefix
  AFFINITY_EXE           Override fuer die Affinity.exe
  AFFINITY_ICON          Override fuer das Icon im Desktop-Launcher
  AFFINITY_DESKTOP_FILE  Override fuer den Zielpfad der .desktop-Datei
EOF
}

main() {
    case "${1:-launch}" in
        launch)
            launch_affinity
            ;;
        desktop)
            install_desktop_entry
            ;;
        status)
            print_status
            ;;
        help|-h|--help)
            show_help
            ;;
        *)
            log_error "Unbekannter Befehl: $1"
            show_help
            exit 1
            ;;
    esac
}

main "${1:-launch}"
