#!/bin/bash

################################################################################
# Affinity TLS Relay
# Accepts legacy Mono TLS on port 443, proxies to serifservices.com via system
# TLS. Bridges Wine-Mono's legacy RSA key exchange to the server's required
# ECDHE ciphers, enabling Canva OAuth sign-in.
#
# One-time setup:
#   sudo setcap 'cap_net_bind_service=+ep' /usr/bin/socat
#   echo "127.0.0.1 affinity.api.serifservices.com" | sudo tee -a /etc/hosts
################################################################################

# Enforce bash execution
if [ -z "$BASH_VERSION" ]; then
    exec bash "$0" "$@"
fi

# Color codes for terminal output (if supported)
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

print_info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

################################################################################
# Configuration
################################################################################

WINEPREFIX="${WINEPREFIX:-$HOME/.AffinityLinux}"
RELAY_DIR="${RELAY_DIR:-$WINEPREFIX/tls-relay}"
SERVER_PEM="$RELAY_DIR/server.pem"
# CA bundle path varies by distro
if [ -f "/etc/ssl/certs/ca-certificates.crt" ]; then
    SYS_CA="/etc/ssl/certs/ca-certificates.crt"          # Arch, Debian, Ubuntu
elif [ -f "/etc/pki/tls/certs/ca-bundle.crt" ]; then
    SYS_CA="/etc/pki/tls/certs/ca-bundle.crt"            # Fedora, RHEL
elif [ -f "/etc/ssl/ca-bundle.pem" ]; then
    SYS_CA="/etc/ssl/ca-bundle.pem"                      # openSUSE
else
    SYS_CA="/etc/ssl/certs/ca-certificates.crt"          # fallback
fi

# Use XDG_RUNTIME_DIR for per-user temp files (avoids /tmp symlink attacks)
_RUNTIME="${XDG_RUNTIME_DIR:-/tmp}"
LOG="$_RUNTIME/affinity-tls-relay.log"
PID_FILE="$_RUNTIME/affinity-tls-relay.pid"
PORT=443

# RSA + ECDHE ciphers: allows Mono's legacy RSA key exchange at TLS 1.2
CIPHERS="ECDHE+AES:RSA+AES:@SECLEVEL=1"

################################################################################
# Functions
################################################################################

generate_cert() {
    print_info "Generating self-signed certificate for TLS relay..."
    mkdir -p "$RELAY_DIR"
    (umask 077 && openssl req -x509 -newkey rsa:2048 \
        -keyout "$RELAY_DIR/key.pem" -out "$RELAY_DIR/cert.pem" \
        -days 3650 -nodes \
        -subj "/CN=affinity.api.serifservices.com" 2>/dev/null)
    cat "$RELAY_DIR/cert.pem" "$RELAY_DIR/key.pem" > "$SERVER_PEM"
    chmod 600 "$SERVER_PEM"
    rm -f "$RELAY_DIR/key.pem" "$RELAY_DIR/cert.pem"
    print_success "Certificate generated at $SERVER_PEM"
}

start() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        print_info "TLS relay already running (pid $(cat "$PID_FILE"))"
        return 0
    fi

    if [ ! -f "$SERVER_PEM" ]; then
        generate_cert
    fi

    if ! command -v socat >/dev/null 2>&1; then
        print_error "socat not found. Install it with your package manager."
        return 1
    fi

    # Resolve real IP via DNS (bypasses /etc/hosts override)
    if ! command -v dig >/dev/null 2>&1; then
        print_error "dig not found. Install bind-tools (Arch), bind-utils (Fedora), or dnsutils (Debian)."
        return 1
    fi
    # Query public DNS directly to bypass /etc/hosts override (avoids loopback
    # on dnsmasq-based systems that serve hosts entries over DNS)
    REAL_IP=$(dig +short affinity.api.serifservices.com A @1.1.1.1 2>/dev/null | grep -E '^[0-9]+\.' | head -1)
    if [ -z "$REAL_IP" ]; then
        # Fallback to default resolver if public DNS is unreachable
        REAL_IP=$(dig +short affinity.api.serifservices.com A 2>/dev/null | grep -E '^[0-9]+\.' | head -1)
    fi
    if [ -z "$REAL_IP" ] || [ "$REAL_IP" = "127.0.0.1" ]; then
        print_error "Cannot resolve affinity.api.serifservices.com (got: ${REAL_IP:-empty})"
        return 1
    fi

    print_info "Starting TLS relay on port $PORT (upstream $REAL_IP)..."

    socat \
        "openssl-listen:${PORT},cert=${SERVER_PEM},verify=0,reuseaddr,fork,min-proto-version=TLS1.2,ciphers=${CIPHERS}" \
        "openssl-connect:${REAL_IP}:443,cafile=${SYS_CA},commonname=affinity.api.serifservices.com" \
        >>"$LOG" 2>&1 &

    RELAY_PID=$!
    echo "$RELAY_PID" > "$PID_FILE"
    sleep 0.5

    if kill -0 $RELAY_PID 2>/dev/null; then
        print_success "TLS relay started (pid $RELAY_PID)"
    else
        print_error "TLS relay failed to start. Check $LOG"
        echo ""
        print_info "If you see 'permission denied', run this once:"
        echo "  sudo setcap 'cap_net_bind_service=+ep' /usr/bin/socat"
        rm -f "$PID_FILE"
        return 1
    fi
}

stop() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        kill "$PID" 2>/dev/null
        pkill -P "$PID" 2>/dev/null
        rm -f "$PID_FILE"
        print_success "TLS relay stopped"
    else
        print_info "TLS relay not running"
    fi
}

setup() {
    # One-time setup: /etc/hosts entry + socat capability
    echo ""
    print_info "TLS Relay One-Time Setup"
    echo ""

    # Check /etc/hosts
    if grep -qE '^\s*127\.0\.0\.1\s+affinity\.api\.serifservices\.com' /etc/hosts 2>/dev/null; then
        print_success "/etc/hosts entry already present"
    else
        print_info "Adding /etc/hosts entry (requires sudo)..."
        echo "127.0.0.1 affinity.api.serifservices.com" | sudo tee -a /etc/hosts >/dev/null
        if [ $? -eq 0 ]; then
            print_success "/etc/hosts entry added"
        else
            print_error "Failed to add /etc/hosts entry"
            return 1
        fi
    fi

    # Check socat capability
    if ! command -v socat >/dev/null 2>&1; then
        print_error "socat not installed. Install it first."
        return 1
    fi

    SOCAT_PATH=$(readlink -f "$(command -v socat)")
    if getcap "$SOCAT_PATH" 2>/dev/null | grep -q "cap_net_bind_service"; then
        print_success "socat already has port-binding capability"
    else
        print_info "Granting socat port-binding capability (requires sudo)..."
        sudo setcap 'cap_net_bind_service=+ep' "$SOCAT_PATH"
        if [ $? -eq 0 ]; then
            print_success "socat capability granted"
        else
            print_error "Failed to set socat capability"
            return 1
        fi
    fi

    # Generate cert if needed
    if [ ! -f "$SERVER_PEM" ]; then
        generate_cert
    else
        print_success "TLS certificate already exists"
    fi

    echo ""
    print_success "TLS relay setup complete"
}

################################################################################
# Entry Point
################################################################################

case "${1:-start}" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; sleep 1; start ;;
    setup)   setup ;;
    status)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            print_success "TLS relay running (pid $(cat "$PID_FILE"))"
        else
            print_info "TLS relay not running"
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|setup|status}"
        echo ""
        echo "  start    Start the TLS relay (default)"
        echo "  stop     Stop the TLS relay"
        echo "  restart  Restart the TLS relay"
        echo "  setup    One-time setup (/etc/hosts, socat capability, certificate)"
        echo "  status   Check if relay is running"
        ;;
esac
