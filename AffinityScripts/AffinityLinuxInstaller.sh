#!/bin/bash

################################################################################
# Affinity Linux Installer - All-in-One Installation Script
# This script provides a unified installation interface for all Affinity
# applications with OpenCL support enabled.
################################################################################

# Check if script is executable, if not make it executable
if [ ! -x "$(readlink -f "$0")" ]; then
    echo "Making script executable..."
    chmod +x "$(readlink -f "$0")"
fi

# Ensure script is being run with bash
if [ -z "$BASH_VERSION" ]; then
    echo "Running script in bash"
    # Check bash existence
    if command -v bash >/dev/null 2>&1; then
        exec bash "$0" "$@"
    else
        echo "This script must be run with bash" >&2
        exit 1
    fi
fi

# ==========================================
# Constants and Configuration
# ==========================================

# Color codes for terminal output (if supported)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    CYAN=''
    BOLD=''
    NC=''
fi

# Helper functions for formatted output
print_header() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${CYAN}$1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

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

print_progress() {
    echo -e "${GREEN}  →${NC} $1"
}

# ==========================================
# Utility Functions
# ==========================================

# Function to fetch the latest vkd3d-proton version from GitHub API
# Falls back to a known-good version if the API is unreachable
get_latest_vkd3d_version() {
    local fallback="3.0.1"
    local version

    if command -v curl &> /dev/null; then
        version=$(curl -sf "https://api.github.com/repos/HansKristian-Work/vkd3d-proton/releases/latest" \
            | grep '"tag_name"' | sed -E 's/.*"v([^"]+)".*/\1/')
    elif command -v wget &> /dev/null; then
        version=$(wget -qO- "https://api.github.com/repos/HansKristian-Work/vkd3d-proton/releases/latest" \
            | grep '"tag_name"' | sed -E 's/.*"v([^"]+)".*/\1/')
    fi

    if [ -z "$version" ]; then
        print_warning "Could not fetch latest vkd3d-proton version from GitHub. Using fallback: $fallback"
        echo "$fallback"
    else
        echo "$version"
    fi
}

# Function to download files with progress bar
download_file() {
    local url=$1
    local output=$2
    local description=$3
    
    print_progress "Downloading $description..."
    
    # Try curl first with progress bar
    if command -v curl &> /dev/null; then
        if curl -# -L "$url" -o "$output"; then
            return 0
        fi
    fi
    
    # Fallback to wget if curl fails or isn't available
    if command -v wget &> /dev/null; then
        if wget --progress=bar:force:noscroll "$url" -O "$output" 2>/dev/null; then
            return 0
        fi
    fi
    
    print_error "Failed to download $description"
    return 1
}

# ==========================================
# System Detection and Setup Functions
# ==========================================

# Function to detect Linux distribution
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        RAW_DISTRO=$ID
        DISTRO=$(echo "$ID" | tr '[:upper:]' '[:lower:]')
        VERSION=$VERSION_ID
        DISTRO_LIKE="${ID_LIKE:-}"
        # Normalize "pika" to "pikaos" if detected
        if [ "$DISTRO" = "pika" ]; then
            DISTRO="pikaos"
        # Treat Ubuntu derivatives as Ubuntu for dependency and Wine setup.
        elif [ "$DISTRO" != "ubuntu" ] && [ "$DISTRO" != "linuxmint" ] && [ "$DISTRO" != "zorin" ] && [ "$DISTRO" != "pop" ] && echo " ${DISTRO_LIKE} " | grep -q " ubuntu "; then
            DISTRO="ubuntu"
        fi
    else
        print_error "Could not detect Linux distribution"
        exit 1
    fi
}

is_ubuntu_based_distro() {
    case $DISTRO in
        "ubuntu"|"linuxmint"|"zorin"|"pop")
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

get_wine_runner_dir() {
    echo "$HOME/.AffinityLinux/ElementalWarriorWine"
}

get_wine_binary() {
    echo "$(get_wine_runner_dir)/bin/wine"
}

get_winecfg_binary() {
    echo "$(get_wine_runner_dir)/bin/winecfg"
}

get_regedit_binary() {
    echo "$(get_wine_runner_dir)/bin/regedit"
}

get_wineserver_binary() {
    echo "$(get_wine_runner_dir)/bin/wineserver"
}

get_wine_vkd3d_dir() {
    echo "$(get_wine_runner_dir)/lib/wine/vkd3d-proton/x86_64-windows"
}

minimum_supported_wine_version() {
    echo "9.14"
}

preferred_ubuntu_wine_version() {
    echo "10.20~noble-1"
}

preferred_ubuntu_wine_numeric_version() {
    echo "10.20"
}

get_installed_wine_version() {
    local version_output
    local version

    if ! command -v wine &> /dev/null; then
        return 1
    fi

    version_output=$(wine --version 2>/dev/null || true)
    version=$(echo "$version_output" | sed -E 's/.*wine-([0-9]+(\.[0-9]+)?).*/\1/')

    if [ -z "$version" ] || [ "$version" = "$version_output" ]; then
        return 1
    fi

    echo "$version"
}

is_supported_ubuntu_wine_version() {
    local wine_version

    if ! is_ubuntu_based_distro; then
        return 0
    fi

    wine_version=$(get_installed_wine_version 2>/dev/null || true)
    if [ -z "$wine_version" ]; then
        return 1
    fi

    if ! dpkg --compare-versions "$wine_version" ge "$(minimum_supported_wine_version)"; then
        return 1
    fi

    # Wine 11+ currently triggers winetricks hangs in Ubuntu Noble's new WoW64 mode.
    if dpkg --compare-versions "$wine_version" ge "11.0"; then
        return 1
    fi

    return 0
}

install_preferred_ubuntu_winehq_staging() {
    local wine_version
    local package_args=()

    wine_version=$(preferred_ubuntu_wine_version)

    if apt-cache madison winehq-staging 2>/dev/null | awk '{print $3}' | grep -Fxq "$wine_version"; then
        print_info "Pinning Ubuntu-family WineHQ staging to $wine_version to avoid Wine 11 new WoW64 hangs in winetricks."
        package_args=(
            --allow-downgrades
            "winehq-staging=$wine_version"
            "wine-staging=$wine_version"
            "wine-staging-amd64=$wine_version"
            "wine-staging-i386:i386=$wine_version"
        )
    else
        print_warning "Preferred WineHQ version $wine_version is unavailable for this Ubuntu release. Falling back to the latest WineHQ staging package."
        package_args=("winehq-staging")
    fi

    sudo apt-get install --install-recommends -y "${package_args[@]}"
}

backup_incomplete_ubuntu_prefix() {
    local directory="$HOME/.AffinityLinux"
    local backup_dir

    if ! is_ubuntu_based_distro; then
        return 0
    fi

    if [ ! -f "$directory/system.reg" ]; then
        return 0
    fi

    if [ -n "$(detect_installed_affinity 2>/dev/null)" ]; then
        return 0
    fi

    backup_dir="${directory}.backup-$(date +%Y%m%d-%H%M%S)"
    print_warning "Detected an existing Ubuntu Wine prefix without installed Affinity applications."
    print_info "Backing it up to $backup_dir so a clean prefix can be recreated with the pinned Wine version."
    wineserver -k 2>/dev/null || true
    mv "$directory" "$backup_dir" || return 1
    mkdir -p "$directory" || return 1
    print_success "Incomplete Wine prefix backed up"
}

has_dotnet48_runtime() {
    local directory="$HOME/.AffinityLinux"
    local reg_file="$directory/system.reg"
    local full_block

    if [ ! -f "$reg_file" ]; then
        return 1
    fi

    for key in \
        '[Software\\Microsoft\\NET Framework Setup\\NDP\\v4\\Full]' \
        '[Software\\Wow6432Node\\Microsoft\\NET Framework Setup\\NDP\\v4\\Full]'; do
        full_block=$(awk -v key="$key" '
            $0 == key { in_block=1; print; next }
            in_block && /^\[/ { exit }
            in_block { print }
        ' "$reg_file")

        if [ -n "$full_block" ] && printf '%s\n' "$full_block" | rg -q '"Install"=dword:00000001|"Release"=dword:' 2>/dev/null; then
            return 0
        fi
    done

    return 1
}

get_winetricks_timeout_seconds() {
    echo "${AFFINITY_WINETRICKS_TIMEOUT_SECONDS:-1800}"
}

terminate_prefix_wine_processes() {
    local directory="$HOME/.AffinityLinux"

    if [ -x "$(get_wineserver_binary)" ]; then
        WINEPREFIX="$directory" "$(get_wineserver_binary)" -k >/dev/null 2>&1 || true
    fi

    wineserver -k >/dev/null 2>&1 || true
    pkill -f "$directory" >/dev/null 2>&1 || true
}

run_winetricks_verb() {
    local directory="$HOME/.AffinityLinux"
    local description=$1
    local verb=$2
    local required=${3:-0}
    local timeout_seconds=${4:-$(get_winetricks_timeout_seconds)}
    local status

    print_step "Installing $description..."
    if command -v timeout >/dev/null 2>&1; then
        env WINEPREFIX="$directory" timeout --signal=TERM --kill-after=30 "$timeout_seconds" \
            winetricks --unattended --force --no-isolate --optout "$verb"
        status=$?
    else
        WINEPREFIX="$directory" winetricks --unattended --force --no-isolate --optout "$verb"
        status=$?
    fi

    if [ "$status" -eq 0 ]; then
        print_progress "$description installation attempted"
        return 0
    fi

    if [ "$status" -eq 124 ] || [ "$status" -eq 137 ]; then
        print_error "$description installation timed out after ${timeout_seconds}s"
        terminate_prefix_wine_processes
    fi

    if [ "$required" -eq 1 ]; then
        print_error "Failed to install required runtime via winetricks: $verb"
        return 1
    fi

    print_warning "$description installation failed; continuing"
    return 0
}

verify_required_wine_runtimes() {
    if has_dotnet48_runtime; then
        return 0
    fi

    print_error ".NET Framework 4.8 is not installed in the Wine prefix."
    print_info "Affinity's SetupUI.exe crashes without it, which causes the JIT debugger dialog you saw."
    print_info "Current Ubuntu Wine builds are still exposing experimental new WoW64 behavior for this 64-bit prefix."
    print_info "Aborting before launching the Affinity installer."
    return 1
}

setup_system_wine_runner() {
    local directory="$HOME/.AffinityLinux"
    local runner_dir
    runner_dir="$(get_wine_runner_dir)"
    local runner_bin="$runner_dir/bin"
    local wine_version

    print_step "Configuring local Wine runner using system Wine..."
    mkdir -p "$directory" "$runner_bin" "$(get_wine_vkd3d_dir)"

    if is_ubuntu_based_distro && ! is_supported_ubuntu_wine_version; then
        wine_version=$(get_installed_wine_version 2>/dev/null || echo "unknown")
        print_error "Detected Wine $wine_version on this Ubuntu-family system."
        print_info "Ubuntu-family systems currently support Wine versions from $(minimum_supported_wine_version) up to 10.x in this installer."
        print_info "The installer will pin WineHQ staging to $(preferred_ubuntu_wine_numeric_version) to avoid Wine 11 new WoW64 hangs."
        return 1
    fi

    for cmd in wine winecfg regedit wineserver; do
        local system_cmd
        system_cmd=$(command -v "$cmd" 2>/dev/null || true)
        if [ -z "$system_cmd" ]; then
            print_error "Required Wine command not found: $cmd"
            print_info "Please ensure Wine is installed correctly and available in PATH."
            return 1
        fi
        ln -sfn "$system_cmd" "$runner_bin/$cmd"
    done

    wine_version=$(get_installed_wine_version 2>/dev/null || echo "unknown")
    print_success "System Wine runner configured at $runner_dir"
    print_info "Using system Wine command: $(command -v wine) (version: $wine_version)"
    return 0
}

install_ubuntu_based_dependencies() {
    local codename="jammy"
    local ubuntu_version="22.04"
    local distro_label="${RAW_DISTRO:-$DISTRO}"
    local winehq_install_failed=0

    if [ -f /etc/os-release ]; then
        codename=$(. /etc/os-release && echo "${UBUNTU_CODENAME:-${VERSION_CODENAME:-jammy}}")
        ubuntu_version=$(. /etc/os-release && echo "${VERSION_ID:-22.04}")
    fi

    print_header "Ubuntu-Based Dependency Installation"
    print_info "Detected Ubuntu-family system: $distro_label ($ubuntu_version / $codename)"

    print_progress "Adding i386 architecture support..."
    sudo dpkg --add-architecture i386 || return 1

    print_info "Ubuntu-family systems need newer Wine than the stock distro package usually provides."
    print_info "Installing WineHQ staging for improved Affinity compatibility"
    sudo mkdir -pm755 /etc/apt/keyrings || return 1
    wget -qO- https://dl.winehq.org/wine-builds/winehq.key | \
        sudo gpg --dearmor -o /etc/apt/keyrings/winehq-archive.key || return 1
    sudo rm -f /etc/apt/sources.list.d/winehq-*.sources 2>/dev/null || true
    sudo wget -NP /etc/apt/sources.list.d/ \
        "https://dl.winehq.org/wine-builds/ubuntu/dists/$codename/winehq-$codename.sources" || return 1
    sudo apt-get update || return 1

    if ! install_preferred_ubuntu_winehq_staging; then
        winehq_install_failed=1
        print_warning "Initial WineHQ staging install failed. Trying Noble t64 dependency transition workaround..."

        if apt-cache show libpgm-5.3-0t64 >/dev/null 2>&1 && \
           apt-cache show libieee1284-3t64 >/dev/null 2>&1; then
            sudo apt-get install -y \
                libpgm-5.3-0t64 \
                libpgm-5.3-0t64:i386 \
                libieee1284-3t64 \
                libieee1284-3t64:i386 || return 1
        fi

        print_info "Retrying WineHQ staging after dependency transition..."
        install_preferred_ubuntu_winehq_staging || return 1
    fi

    sudo apt-get install -y winetricks wget curl p7zip-full tar jq zstd unzip cabextract winbind || return 1

    if [ "$winehq_install_failed" -eq 1 ]; then
        print_success "Ubuntu-based dependencies installed using the Noble t64 workaround"
    else
        print_success "Ubuntu-based dependencies installed"
    fi
}

# Function to check dependencies
check_dependencies() {
    print_header "Dependency Verification"
    
    # Check if this is an unsupported distribution
    case $DISTRO in
        "bazzite")
            print_header ""
            echo ""
            echo -e "${RED}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${RED}${BOLD}                    ⚠️   WARNING: UNSUPPORTED DISTRIBUTION   ⚠️${NC}"
            echo -e "${RED}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo ""
            echo -e "${RED}${BOLD}YOU ARE ON YOUR OWN!${NC}"
            echo ""
            echo -e "${YELLOW}${BOLD}The distribution you are using ($DISTRO) is OUT OF DATE and the script${NC}"
            echo -e "${YELLOW}${BOLD}will NOT be built around it.${NC}"
            echo ""
            echo -e "${CYAN}${BOLD}For a modern, stable Linux experience with proper support, please consider${NC}"
            echo -e "${CYAN}${BOLD}switching to one of these recommended distributions:${NC}"
            echo ""
            echo -e "${GREEN}  • PikaOS 4${NC}"
            echo -e "${GREEN}  • CachyOS${NC}"
            echo -e "${GREEN}  • Nobara${NC}"
            echo ""
            ;;
    esac
    
    print_info "Checking for required system dependencies..."
    
    local missing_deps=""
    
    for dep in wine winetricks wget curl 7z tar jq unzip cabextract; do
        print_progress "Checking for $dep..."
        if ! command -v "$dep" &> /dev/null; then
            missing_deps+="$dep "
            print_error "$dep is not installed"
        else
            print_success "$dep is installed"
        fi
    done
    
    # Check for zstd support (needed for vkd3d-proton)
    if ! command -v unzstd &> /dev/null && ! command -v zstd &> /dev/null; then
        missing_deps+="zstd "
        print_error "zstd or unzstd is not installed"
    else
        print_success "zstd support is available"
    fi

    if is_ubuntu_based_distro && ! command -v ntlm_auth &> /dev/null; then
        missing_deps+="winbind "
        print_error "ntlm_auth is not installed (package: winbind)"
    fi

    if is_ubuntu_based_distro && command -v wine &> /dev/null; then
        local wine_version
        wine_version=$(get_installed_wine_version 2>/dev/null || echo "")
        if [ -z "$wine_version" ]; then
            missing_deps+="winehq-staging "
            print_error "Could not determine Wine version. WineHQ staging is required on Ubuntu-family systems."
        elif ! is_supported_ubuntu_wine_version; then
            missing_deps+="winehq-staging "
            print_error "Wine $wine_version is outside the Ubuntu-supported range for this installer."
            print_info "Ubuntu-family systems currently support Wine versions from $(minimum_supported_wine_version) up to 10.x here."
            print_info "The installer will pin WineHQ staging to $(preferred_ubuntu_wine_numeric_version)."
        else
            print_success "Wine version $wine_version is supported"
        fi
    fi
    
    # For unsupported distributions, check if we can continue
    case $DISTRO in
        "bazzite")
            if [ -n "$missing_deps" ]; then
                echo ""
                echo -e "${RED}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
                echo -e "${RED}${BOLD}                    ⚠️   WARNING: UNSUPPORTED DISTRIBUTION   ⚠️${NC}"
                echo -e "${RED}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
                echo ""
                echo -e "${RED}${BOLD}Missing dependencies detected: $missing_deps${NC}"
                echo ""
                echo -e "${YELLOW}${BOLD}This script will NOT automatically install dependencies for unsupported distributions.${NC}"
                echo -e "${YELLOW}Please install the required dependencies manually:${NC}"
                echo -e "${CYAN}  winehq-staging winetricks wget curl p7zip-full tar jq zstd unzip cabextract winbind${NC}"
                echo ""
                while true; do
                    echo -e "${YELLOW}Press Enter to check dependencies again, or 'q' to exit:${NC}"
                    read -r response
                    if [ "$response" = "q" ] || [ "$response" = "Q" ]; then
                        echo -e "${RED}${BOLD}Exiting...${NC}"
                        exit 1
                    fi
                    # Re-check dependencies
                    missing_deps=""
                    for dep in wine winetricks wget curl tar jq unzip cabextract; do
                        if ! command -v "$dep" &> /dev/null; then
                            missing_deps+="$dep "
                        fi
                    done
                    # Check for 7z or unzip
                    if ! command -v 7z &> /dev/null && ! command -v unzip &> /dev/null; then
                        missing_deps+="7z or unzip "
                    fi
                    # Check for zstd
                    if ! command -v unzstd &> /dev/null && ! command -v zstd &> /dev/null; then
                        missing_deps+="zstd "
                    fi
                    if is_ubuntu_based_distro && command -v wine &> /dev/null && ! is_supported_ubuntu_wine_version; then
                        missing_deps+="winehq-staging "
                    fi
                    if [ -z "$missing_deps" ]; then
                        print_success "All dependencies are now installed!"
                        break
                    else
                        print_error "Still missing: ${missing_deps}"
                    fi
                done
            else
                echo ""
                echo -e "${YELLOW}${BOLD}All required dependencies are installed.${NC}"
                echo -e "${YELLOW}${BOLD}The script will continue, but you are still on an unsupported distribution.${NC}"
                echo -e "${YELLOW}${BOLD}No support will be provided if issues arise.${NC}"
                echo ""
                echo -e "${RED}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
                echo ""
                print_success "Continuing with installation..."
            fi
            ;;
        *)
    if [ -n "$missing_deps" ]; then
        print_warning "Missing dependencies: $missing_deps"
        install_dependencies
    else
        print_success "All required dependencies are installed!"
    fi
            ;;
    esac
    echo ""
}

# Function to install dependencies based on distribution
install_dependencies() {
    print_step "Installing dependencies for $DISTRO..."
    
    case $DISTRO in
        "pikaos")
            # PikaOS has a special case: its built-in Wine causes issues with Affinity
            # We need to replace it with WineHQ staging from Debian for proper compatibility
            print_header "PikaOS Special Configuration"
            print_info "PikaOS's built-in Wine has compatibility issues with Affinity applications."
            print_info "Replacing with WineHQ staging from Debian for better compatibility..."
            echo ""
            
            print_step "Setting up WineHQ repository..."
            print_progress "Creating APT keyrings directory..."
            sudo mkdir -pm755 /etc/apt/keyrings
            
            print_progress "Adding WineHQ GPG key..."
            if wget -O - https://dl.winehq.org/wine-builds/winehq.key | sudo gpg --dearmor -o /etc/apt/keyrings/winehq-archive.key - 2>/dev/null; then
                print_success "WineHQ GPG key added"
            else
                print_error "Failed to add WineHQ GPG key"
                exit 1
            fi
            
            print_progress "Adding i386 architecture support..."
            if sudo dpkg --add-architecture i386; then
                print_success "i386 architecture added"
            else
                print_error "Failed to add i386 architecture"
                exit 1
            fi
            
            print_progress "Adding WineHQ repository..."
            # Always use Debian testing repository for the newest WineHQ packages
            # This ensures we get the latest WineHQ versions without needing to update
            # the script every Debian release. Debian testing codename is currently "forky"
            codename="forky"  # Debian testing
            print_info "Using Debian testing (forky) repository for latest WineHQ packages"
            
            # Remove existing WineHQ repository files first
            sudo rm -f /etc/apt/sources.list.d/winehq-*.sources 2>/dev/null
            
            # Add the repository using the detected codename
            # Use -NP flags: -N for timestamping, -P for directory
            if sudo wget -NP /etc/apt/sources.list.d/ "https://dl.winehq.org/wine-builds/debian/dists/$codename/winehq-$codename.sources" 2>/dev/null; then
                print_success "WineHQ repository added for $codename"
            else
                print_error "Failed to add WineHQ repository for $codename"
                exit 1
            fi
            
            print_progress "Updating package lists..."
            if sudo apt update; then
                print_success "Package lists updated"
            else
                print_error "Failed to update package lists"
                exit 1
            fi
            
            print_step "Installing WineHQ staging (replaces built-in Wine)..."
            if sudo apt install --install-recommends -y winehq-staging; then
                print_success "WineHQ staging installed"
            else
                print_error "Failed to install WineHQ staging"
                exit 1
            fi
            
            print_step "Installing remaining dependencies..."
            sudo apt install -y winetricks wget curl p7zip-full tar jq zstd winbind
            print_success "All dependencies installed for PikaOS"
            ;;
        "pop")
            # Pop!_OS also has a special case for Wine
            print_header "Pop!_OS Special Configuration"
            print_info "Pop!_OS's built-in Wine can have compatibility issues."
            print_info "Setting up WineHQ staging from Ubuntu for better compatibility..."
            echo ""
            
            print_step "Setting up WineHQ repository..."
            print_progress "Creating APT keyrings directory..."
            sudo mkdir -pm755 /etc/apt/keyrings
            
            print_progress "Adding WineHQ GPG key..."
            if wget -O - https://dl.winehq.org/wine-builds/winehq.key | sudo gpg --dearmor -o /etc/apt/keyrings/winehq-archive.key - 2>/dev/null; then
                print_success "WineHQ GPG key added"
            else
                print_error "Failed to add WineHQ GPG key"
                exit 1
            fi
            
            print_progress "Adding i386 architecture support..."
            if sudo dpkg --add-architecture i386; then
                print_success "i386 architecture added"
            else
                print_error "Failed to add i386 architecture"
                exit 1
            fi
            
            print_progress "Adding WineHQ repository..."
            # Get Ubuntu version codename
            local codename="jammy"
            if [ -f /etc/os-release ]; then
                codename=$(. /etc/os-release && echo "$VERSION_CODENAME")
            fi
            
            if sudo wget -NP /etc/apt/sources.list.d/ "https://dl.winehq.org/wine-builds/ubuntu/dists/$codename/winehq-$codename.sources" 2>/dev/null; then
                print_success "WineHQ repository added"
            else
                print_error "Failed to add WineHQ repository"
                exit 1
            fi
            
            print_progress "Updating package lists..."
            if sudo apt update; then
                print_success "Package lists updated"
            else
                print_error "Failed to update package lists"
                exit 1
            fi
            
            print_step "Installing WineHQ staging..."
            if sudo apt install --install-recommends -y winehq-staging; then
                print_success "WineHQ staging installed"
            else
                print_error "Failed to install WineHQ staging"
                exit 1
            fi
            
            print_step "Installing remaining dependencies..."
            sudo apt install -y winetricks wget curl p7zip-full tar jq zstd winbind
            print_success "All dependencies installed for Pop!_OS"
            ;;
        "ubuntu"|"linuxmint"|"zorin")
            if install_ubuntu_based_dependencies; then
                print_success "All dependencies installed for Ubuntu-based system"
            else
                print_error "Failed to install Ubuntu-based dependencies"
                exit 1
            fi
            ;;
        "bazzite")
            print_error "Unsupported distribution detected in install_dependencies()"
            print_error "This function should not be called for unsupported distributions"
            exit 1
            ;;
        "arch"|"cachyos"|"endeavouros"|"xerolinux")
            sudo pacman -S --needed wine winetricks wget curl p7zip tar jq zstd dotnet-sdk
            ;;
        "fedora"|"nobara")
            sudo dnf install -y wine winetricks wget curl p7zip p7zip-plugins tar jq zstd
            # Install msttcore-fonts to fix font rendering bug with Affinity
            local msttcore_rpm="/tmp/msttcore-fonts-installer-2.6-1.noarch.rpm"
            local msttcore_url="https://github.com/isboston/msttcore-fonts/releases/download/fonts/msttcore-fonts-installer-2.6-1.noarch.rpm"
            print_step "Downloading msttcore-fonts to fix font rendering bug..."
            if download_file "$msttcore_url" "$msttcore_rpm" "msttcore-fonts"; then
                print_step "Installing msttcore-fonts..."
                if sudo dnf install -y "$msttcore_rpm"; then
                    print_success "msttcore-fonts installed successfully"
                else
                    print_warning "Failed to install msttcore-fonts (may already be installed)"
                fi
                rm -f "$msttcore_rpm"
            else
                print_warning "Failed to download msttcore-fonts (font rendering may have issues)"
            fi
            ;;
        "opensuse-tumbleweed"|"opensuse-leap")
            sudo zypper install -y wine winetricks wget curl p7zip tar jq zstd
            ;;
        *)
            print_error "Unsupported distribution: $DISTRO"
            print_info "Please install the following packages manually:"
            print_info "wine winetricks wget curl p7zip tar jq zstd"
            exit 1
            ;;
    esac
}

# ==========================================
# Wine Setup Functions
# ==========================================

# ==========================================
# GPU Detection and Selection Functions
# ==========================================

# Function to detect and select GPU for hybrid graphics systems
detect_and_select_gpu() {
    local directory=$1
    
    print_header "GPU Detection"
    
    # Arrays to store GPU information
    declare -a GPU_LIST
    declare -a GPU_TYPE
    declare -a GPU_ID
    
    print_step "Detecting available GPUs..."
    
    # Parse lspci output for VGA/3D controllers
    while IFS= read -r line; do
        # Extract bus ID (e.g., "01:00.0")
        bus_id=$(echo "$line" | cut -d' ' -f1)
        
        # Extract GPU info (everything after the third colon)
        gpu_info=$(echo "$line" | cut -d':' -f3-)
        gpu_info_lower=$(echo "$gpu_info" | tr '[:upper:]' '[:lower:]')
        
        # Determine GPU type and add to arrays
        if echo "$gpu_info_lower" | grep -Eq '(^|[^[:alpha:]])nvidia([^[:alpha:]]|$)'; then
            GPU_LIST+=("$gpu_info")
            GPU_TYPE+=("nvidia")
            GPU_ID+=("$bus_id")
            print_info "Found NVIDIA GPU: $gpu_info"
        elif echo "$gpu_info_lower" | grep -Eq '(^|[^[:alpha:]])(amd|radeon|ati)([^[:alpha:]]|$)'; then
            GPU_LIST+=("$gpu_info")
            GPU_TYPE+=("amd")
            GPU_ID+=("$bus_id")
            print_info "Found AMD GPU: $gpu_info"
        elif echo "$gpu_info_lower" | grep -Eq '(^|[^[:alpha:]])intel([^[:alpha:]]|$)'; then
            GPU_LIST+=("$gpu_info")
            GPU_TYPE+=("intel")
            GPU_ID+=("$bus_id")
            print_info "Found Intel GPU: $gpu_info"
        fi
    done < <(lspci | grep -iE 'vga|3d|display')
    
    # Count GPUs
    local gpu_count=${#GPU_LIST[@]}
    
    if [ $gpu_count -eq 0 ]; then
        print_warning "No GPU detected. Installation will continue with default settings."
        export SELECTED_GPU_TYPE="unknown"
        return 0
    fi
    
    echo ""
    print_success "Found $gpu_count GPU(s)"
    echo ""
    
    # If only one GPU, use it automatically
    if [ $gpu_count -eq 1 ]; then
        print_info "Single GPU detected, using: ${GPU_LIST[0]}"
        export SELECTED_GPU_TYPE="${GPU_TYPE[0]}"
        export SELECTED_GPU_NAME="${GPU_LIST[0]}"
        
        # Set environment variables based on GPU type
        case "${GPU_TYPE[0]}" in
            nvidia)
                print_success "Configuring for NVIDIA GPU"
                export __NV_PRIME_RENDER_OFFLOAD=1
                export __VK_LAYER_NV_optimus=NVIDIA_only
                export __GLX_VENDOR_LIBRARY_NAME=nvidia
                export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.x86_64.json
                export DRI_PRIME=1
                ;;
            amd)
                print_success "Configuring for AMD GPU"
                export DRI_PRIME=1
                export RADV_PERFTEST=aco
                export AMD_VULKAN_ICD=RADV
                ;;
            intel)
                print_success "Configuring for Intel iGPU"
                export DRI_PRIME=0
                ;;
        esac
    else
        # Multiple GPUs detected - show selection menu
        print_warning "Multiple GPUs detected. Please select which one to use for Affinity:"
        echo ""
        
        for i in "${!GPU_LIST[@]}"; do
            idx=$((i + 1))
            gpu_name="${GPU_LIST[$i]}"
            gpu_type="${GPU_TYPE[$i]}"
            
            # Add visual indicator based on type
            case "$gpu_type" in
                nvidia)
                    echo -e "  ${GREEN}[$idx] 🟢 NVIDIA:${NC} $gpu_name"
                    ;;
                amd)
                    echo -e "  ${RED}[$idx] 🔴 AMD:${NC} $gpu_name"
                    ;;
                intel)
                    echo -e "  ${BLUE}[$idx] 🔵 Intel:${NC} $gpu_name"
                    ;;
            esac
        done
        
        echo ""
        
        # Recommend discrete GPU if available
        local recommended=""
        for i in "${!GPU_TYPE[@]}"; do
            if [[ "${GPU_TYPE[$i]}" == "nvidia" ]] || [[ "${GPU_TYPE[$i]}" == "amd" ]]; then
                recommended=$((i + 1))
                break
            fi
        done
        
        if [ -n "$recommended" ]; then
            print_info "Recommended: Option $recommended (discrete GPU for better performance)"
            echo ""
        fi
        
        # Get user selection
        # If not running in an interactive terminal, auto-select the recommended GPU
        local selection=""
        if [ -n "$recommended" ] && ! [ -t 0 ]; then
            selection="$recommended"
            print_info "Non-interactive mode: auto-selecting recommended GPU (Option $recommended)"
        else
            while true; do
                echo -n "Select GPU [1-$gpu_count]: "
                read -r selection

                # Validate input
                if [[ "$selection" =~ ^[0-9]+$ ]] && [ "$selection" -ge 1 ] && [ "$selection" -le "$gpu_count" ]; then
                    break
                else
                    print_error "Invalid selection. Please enter a number between 1 and $gpu_count."
                fi
            done
        fi
        
        # Adjust for 0-based array indexing
        local selected_idx=$((selection - 1))
        local selected_gpu="${GPU_LIST[$selected_idx]}"
        local selected_type="${GPU_TYPE[$selected_idx]}"
        
        echo ""
        print_success "Selected: $selected_gpu"
        echo ""
        
        export SELECTED_GPU_TYPE="$selected_type"
        export SELECTED_GPU_NAME="$selected_gpu"
        
        # Set environment variables based on selection
        case "$selected_type" in
            nvidia)
                print_info "Configuring environment for NVIDIA GPU..."
                export __NV_PRIME_RENDER_OFFLOAD=1
                export __VK_LAYER_NV_optimus=NVIDIA_only
                export __GLX_VENDOR_LIBRARY_NAME=nvidia
                export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.x86_64.json
                export DRI_PRIME=1
                print_success "NVIDIA GPU environment configured"
                ;;
            amd)
                print_info "Configuring environment for AMD GPU..."
                export DRI_PRIME=1
                export RADV_PERFTEST=aco
                export AMD_VULKAN_ICD=RADV
                print_success "AMD GPU environment configured"
                ;;
            intel)
                print_info "Configuring environment for Intel iGPU..."
                export DRI_PRIME=0
                print_success "Intel iGPU environment configured"
                ;;
            *)
                print_warning "Unknown GPU type, using default settings"
                ;;
        esac
        
        # Verify GPU is active
        if command -v glxinfo &> /dev/null; then
            print_step "Verifying GPU selection..."
            local renderer=$(glxinfo 2>/dev/null | grep "OpenGL renderer" | cut -d':' -f2 | xargs)
            if [ -n "$renderer" ]; then
                print_success "Active renderer: $renderer"
            fi
        fi
    fi
    
    echo ""
    print_info "GPU configuration complete."
    read -n 1 -s -r -p "Press any key to continue..."
    echo ""
}

# Function to verify Windows version
verify_windows_version() {
    local directory="$HOME/.AffinityLinux"
    print_progress "Setting Windows compatibility mode to Windows 11..."
    WINEPREFIX="$directory" "$(get_winecfg_binary)" -v win11 >/dev/null 2>&1 || true
    print_success "Windows version configured"
    return 0
}

# Function to download and setup Wine
setup_wine() {
    print_header "Wine Binary Setup"
    print_info "Preparing Wine runner..."
    
    local directory="$HOME/.AffinityLinux"
    local wine_url="https://github.com/seapear/AffinityOnLinux/releases/download/Legacy/ElementalWarriorWine-x86_64.tar.gz"
    local filename="ElementalWarriorWine-x86_64.tar.gz"
    
    # Kill any running wine processes
    print_step "Stopping any running Wine processes..."
    wineserver -k 2>/dev/null || true
    print_success "Wine processes stopped"
    
    # Create install directory
    print_step "Creating installation directory: $directory"
    mkdir -p "$directory"
    print_success "Installation directory created"

    if is_ubuntu_based_distro; then
        print_info "Ubuntu-based system detected. Using system Wine instead of the legacy bundled Wine tarball."
        backup_incomplete_ubuntu_prefix || exit 1
        if ! setup_system_wine_runner; then
            exit 1
        fi
    else
    
    # Download the specific Wine version
    print_step "Downloading Wine binary from GitHub releases..."
    if download_file "$wine_url" "$directory/$filename" "Wine binaries"; then
        print_success "Wine binary downloaded successfully"
    else
        print_error "Failed to download Wine binary"
        exit 1
    fi
    
    # Extract wine binary
    print_step "Extracting Wine binary archive..."
    if tar -xzf "$directory/$filename" -C "$directory" 2>/dev/null; then
        print_success "Wine binary extracted successfully"
        rm "$directory/$filename"
    else
        print_error "Failed to extract Wine binary archive"
        exit 1
    fi
    
    # Find the actual Wine directory and create a symlink if needed
    print_step "Locating Wine installation directory..."
    wine_dir=$(find "$directory" -name "ElementalWarriorWine*" -type d | head -1)
    if [ -n "$wine_dir" ] && [ "$wine_dir" != "$directory/ElementalWarriorWine" ]; then
        print_info "Creating symlink for Wine directory..."
        ln -sf "$wine_dir" "$directory/ElementalWarriorWine"
        print_success "Symlink created: $directory/ElementalWarriorWine"
    fi
    
    # Verify Wine binary exists
    print_step "Verifying Wine binary exists..."
    if [ ! -f "$(get_wine_binary)" ]; then
        print_error "Wine binary not found at expected location"
        print_info "Checking directory structure..."
        echo "Contents of $directory:"
        ls -la "$directory" || true
        if [ -n "$wine_dir" ]; then
            echo "Contents of $wine_dir:"
            ls -la "$wine_dir" || true
        fi
        exit 1
    fi
    print_success "Wine binary verified: $(get_wine_binary)"
    fi
    
    # Create icons directory if it doesn't exist
    print_step "Setting up application icons..."
    mkdir -p "$HOME/.local/share/icons"
    
    # Download and setup additional files
    download_file "https://upload.wikimedia.org/wikipedia/commons/f/f5/Affinity_Photo_V2_icon.svg" "$HOME/.local/share/icons/AffinityPhoto.svg" "Affinity Photo icon" || true
    download_file "https://upload.wikimedia.org/wikipedia/commons/3/3c/Affinity_Designer_2-logo.svg" "$HOME/.local/share/icons/AffinityDesigner.svg" "Affinity Designer icon" || true
    download_file "https://upload.wikimedia.org/wikipedia/commons/9/9c/Affinity_Publisher_V2_icon.svg" "$HOME/.local/share/icons/AffinityPublisher.svg" "Affinity Publisher icon" || true
    
    # Download official Affinity V3 icon
    download_file "https://github.com/seapear/AffinityOnLinux/raw/main/Assets/Icons/Affinity-Canva.svg" "$HOME/.local/share/icons/Affinity.svg" "Affinity V3 icon" || true
    
    # Download WinMetadata
    print_header "Windows Metadata Installation"
    print_info "Fetching Windows metadata files..."
    
    print_step "Downloading Windows metadata from archive.org..."
    # Use the same reliable method as individual scripts (wget with -q --show-progress)
    if wget -q --show-progress "https://archive.org/download/win-metadata/WinMetadata.zip" -O "$directory/Winmetadata.zip"; then
        # Verify the file was downloaded and has content (not zero bytes)
        if [ -s "$directory/Winmetadata.zip" ]; then
            print_success "Windows metadata downloaded successfully"
        else
            print_error "Downloaded file is empty or corrupted"
            rm -f "$directory/Winmetadata.zip"
        fi
    else
        print_warning "Failed to download Windows metadata (this may cause minor issues)"
        rm -f "$directory/Winmetadata.zip"
    fi
    
    # Ensure the system32 directory exists before extraction
    mkdir -p "$directory/drive_c/windows/system32"
    
    # Extract WinMetadata
    if [ -f "$directory/Winmetadata.zip" ] && [ -s "$directory/Winmetadata.zip" ]; then
        print_step "Extracting Windows metadata archive..."
        if command -v 7z &> /dev/null; then
            if 7z x "$directory/Winmetadata.zip" -o"$directory/drive_c/windows/system32" -y >/dev/null 2>&1; then
                print_success "Windows metadata extracted successfully using 7z"
            else
                print_warning "7z extraction had issues, trying unzip..."
                unzip -o "$directory/Winmetadata.zip" -d "$directory/drive_c/windows/system32" >/dev/null 2>&1 || true
                if [ $? -eq 0 ]; then
                    print_success "Windows metadata extracted using unzip"
                else
                    print_error "Extraction failed with both 7z and unzip. File may be corrupted."
                    print_info "You may need to manually download WinMetadata.zip and extract it"
                fi
            fi
        elif command -v unzip &> /dev/null; then
            if unzip -o "$directory/Winmetadata.zip" -d "$directory/drive_c/windows/system32" >/dev/null 2>&1; then
                print_success "Windows metadata extracted successfully using unzip"
            else
                print_error "Failed to extract Windows metadata"
                print_info "The downloaded file may be corrupted. Please check your internet connection and try again."
            fi
        else
            print_error "Neither 7z nor unzip is available to extract Windows metadata"
            print_info "Please install either 7z or unzip and rerun the script"
        fi
        
        print_step "Keeping metadata archive for future restoration..."
        print_info "WinMetadata.zip will be kept to restore after Affinity installations"
        print_success "Archive preserved for restoration"
    else
        print_warning "WinMetadata.zip was not downloaded successfully or is corrupted"
        print_info "Installation will continue, but some Windows metadata features may not work"
    fi
    
    # Download and install vkd3d-proton for OpenCL support (skip if AMD GPU detected)
    print_header "OpenCL Support Setup"
    
    # Use GPU type from detection function
    has_amd_gpu=false
    if [ "$SELECTED_GPU_TYPE" = "amd" ]; then
        has_amd_gpu=true
    fi
    
    if [ "$SELECTED_GPU_TYPE" = "intel" ]; then
        print_info "Intel iGPU detected - skipping vkd3d-proton installation"
        print_info "Using Intel integrated graphics"
    elif [ "$has_amd_gpu" = true ]; then
        print_info "AMD GPU detected - skipping vkd3d-proton installation, will use DXVK instead"
        print_info "DXVK will be configured in desktop shortcuts"
    else
        print_info "Installing vkd3d-proton for hardware acceleration and OpenCL support..."
        print_info "This enables GPU acceleration features in Affinity applications"

        local vkd3d_version
        vkd3d_version=$(get_latest_vkd3d_version)
        local vkd3d_url="https://github.com/HansKristian-Work/vkd3d-proton/releases/download/v${vkd3d_version}/vkd3d-proton-${vkd3d_version}.tar.zst"
        local vkd3d_filename="vkd3d-proton-${vkd3d_version}.tar.zst"

        print_step "Downloading vkd3d-proton v${vkd3d_version} from GitHub..."
    if download_file "$vkd3d_url" "$directory/$vkd3d_filename" "vkd3d-proton"; then
        print_success "vkd3d-proton downloaded successfully"
    else
        print_error "Failed to download vkd3d-proton"
        print_warning "OpenCL support may not work correctly"
    fi
    
    # Extract vkd3d-proton
    print_step "Extracting vkd3d-proton archive..."
    extracted=false
    if command -v unzstd &> /dev/null; then
        if unzstd -f "$directory/$vkd3d_filename" -o "$directory/vkd3d-proton.tar" 2>/dev/null; then
            if tar -xf "$directory/vkd3d-proton.tar" -C "$directory" 2>/dev/null; then
                rm "$directory/vkd3d-proton.tar"
                extracted=true
                print_success "vkd3d-proton extracted using unzstd"
            fi
        fi
    elif command -v zstd &> /dev/null && tar --help 2>&1 | grep -q "use-compress-program"; then
        if tar --use-compress-program=zstd -xf "$directory/$vkd3d_filename" -C "$directory" 2>/dev/null; then
            extracted=true
            print_success "vkd3d-proton extracted using zstd with tar"
        fi
    fi
    
    if [ "$extracted" = false ]; then
        print_error "Cannot extract .tar.zst file. Please install zstd (e.g., sudo pacman -S zstd)"
        print_warning "Skipping vkd3d-proton installation. OpenCL will not work!"
        rm -f "$directory/$vkd3d_filename" 2>/dev/null || true
    elif [ "$has_amd_gpu" = true ]; then
        # Skip vkd3d installation for AMD GPU, clean up if downloaded
        rm -f "$directory/$vkd3d_filename"
        print_info "AMD GPU detected - skipping vkd3d-proton installation, will use DXVK instead"
    else
        rm -f "$directory/$vkd3d_filename"
        
        # Extract vkd3d-proton DLLs for later use (will be copied to Affinity directory after installation)
        local vkd3d_dir=$(find "$directory" -type d -name "vkd3d-proton-*" | head -1)
        if [ -n "$vkd3d_dir" ]; then
            # Store DLLs in a temporary location for later copying
            local vkd3d_temp="$directory/vkd3d_dlls"
            mkdir -p "$vkd3d_temp"
            
            print_step "Extracting vkd3d-proton DLLs..."
            # Copy DLL files to temp location (typical locations: x64/ or root)
            dll_count=0
            if [ -f "$vkd3d_dir/x64/d3d12.dll" ]; then
                cp "$vkd3d_dir/x64/d3d12.dll" "$vkd3d_temp/" 2>/dev/null && ((dll_count++))
            elif [ -f "$vkd3d_dir/d3d12.dll" ]; then
                cp "$vkd3d_dir/d3d12.dll" "$vkd3d_temp/" 2>/dev/null && ((dll_count++))
            fi
            
            if [ -f "$vkd3d_dir/x64/d3d12core.dll" ]; then
                cp "$vkd3d_dir/x64/d3d12core.dll" "$vkd3d_temp/" 2>/dev/null && ((dll_count++))
            elif [ -f "$vkd3d_dir/d3d12core.dll" ]; then
                cp "$vkd3d_dir/d3d12core.dll" "$vkd3d_temp/" 2>/dev/null && ((dll_count++))
            fi
            
            # Also install to Wine library directory
            wine_lib_dir="$(get_wine_vkd3d_dir)"
            mkdir -p "$wine_lib_dir"
            if [ -f "$vkd3d_temp/d3d12.dll" ]; then
                cp "$vkd3d_temp/d3d12.dll" "$wine_lib_dir/" 2>/dev/null || true
            fi
            if [ -f "$vkd3d_temp/d3d12core.dll" ]; then
                cp "$vkd3d_temp/d3d12core.dll" "$wine_lib_dir/" 2>/dev/null || true
            fi
            
            # Remove extracted vkd3d-proton directory
            rm -rf "$vkd3d_dir"
            if [ $dll_count -gt 0 ]; then
                print_success "Extracted $dll_count DLL file(s) for OpenCL support"
            fi
        else
            print_warning "Could not find vkd3d-proton directory after extraction"
        fi
    fi
    fi
    
    # Setup Wine
    print_header "Wine Configuration"
    print_info "Installing required Windows libraries and configuring Wine..."
    
    run_winetricks_verb ".NET Framework 3.5" "dotnet35" 0 || exit 1
    run_winetricks_verb ".NET Framework 4.8" "dotnet48" 1 || exit 1
    run_winetricks_verb "Windows core fonts" "corefonts" 0 || exit 1
    run_winetricks_verb "Visual C++ Redistributables 2022" "vcrun2022" 0 || exit 1
    run_winetricks_verb "MSXML 3.0" "msxml3" 0 || exit 1
    run_winetricks_verb "MSXML 6.0" "msxml6" 0 || exit 1
    run_winetricks_verb "Tahoma font" "tahoma" 0 || exit 1
    run_winetricks_verb "Wine Vulkan renderer" "renderer=vulkan" 0 || exit 1

    verify_required_wine_runtimes || exit 1
    print_success "Wine configured with Vulkan renderer"
    
    print_info "Note: The above installations may take several minutes. Errors are normal if components are already installed."
    
    # Set and verify Windows version to 11
    verify_windows_version
    
    # Apply dark theme
    print_step "Applying Wine dark theme..."
    if download_file "https://raw.githubusercontent.com/seapear/AffinityOnLinux/refs/heads/main/Auxiliary/Other/wine-dark-theme.reg" "$directory/wine-dark-theme.reg" "dark theme"; then
        WINEPREFIX="$directory" "$(get_regedit_binary)" "$directory/wine-dark-theme.reg" >/dev/null 2>&1 || true
        rm -f "$directory/wine-dark-theme.reg"
        print_success "Dark theme applied to Wine"
    else
        print_warning "Could not download dark theme registry file"
    fi
    
    print_success "Wine setup completed successfully!"
    echo ""
}

# ==========================================
# Affinity Installation Functions
# ==========================================

# Function to configure OpenCL support for an application
configure_opencl() {
    local app_dir=$1
    local app_name=$2
    local directory="$HOME/.AffinityLinux"
    local wine_lib_dir
    wine_lib_dir="$(get_wine_vkd3d_dir)"
    local vkd3d_temp="$directory/vkd3d_dlls"
    
    if [ -d "$app_dir" ] && [ -d "$wine_lib_dir" ]; then
        print_info "Configuring OpenCL support for $app_name..."
        dll_copied=0
        
        # Try to copy from temp location first, then fallback to wine lib directory
        if [ -f "$vkd3d_temp/d3d12.dll" ]; then
            if cp "$vkd3d_temp/d3d12.dll" "$app_dir/" 2>/dev/null; then
                print_progress "Copied d3d12.dll to $app_name directory"
                ((dll_copied++))
            fi
        elif [ -f "$wine_lib_dir/d3d12.dll" ]; then
            if cp "$wine_lib_dir/d3d12.dll" "$app_dir/" 2>/dev/null; then
                print_progress "Copied d3d12.dll to $app_name directory"
                ((dll_copied++))
            fi
        fi
        
        if [ -f "$vkd3d_temp/d3d12core.dll" ]; then
            if cp "$vkd3d_temp/d3d12core.dll" "$app_dir/" 2>/dev/null; then
                print_progress "Copied d3d12core.dll to $app_name directory"
                ((dll_copied++))
            fi
        elif [ -f "$wine_lib_dir/d3d12core.dll" ]; then
            if cp "$wine_lib_dir/d3d12core.dll" "$app_dir/" 2>/dev/null; then
                print_progress "Copied d3d12core.dll to $app_name directory"
                ((dll_copied++))
            fi
        fi
        
        if [ $dll_copied -gt 0 ]; then
            print_success "Copied $dll_copied OpenCL DLL file(s) to $app_name directory"
        fi
        
        print_info "Configuring Wine DLL overrides for OpenCL support..."
        reg_file="$directory/dll_overrides.reg"
        {
            echo "REGEDIT4"
            echo "[HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides]"
            echo "\"d3d12\"=\"native\""
            echo "\"d3d12core\"=\"native\""
        } > "$reg_file"
        
        if WINEPREFIX="$directory" "$(get_regedit_binary)" "$reg_file" >/dev/null 2>&1; then
            print_success "DLL overrides configured in Wine registry"
        else
            print_warning "Could not apply DLL overrides (OpenCL may not work)"
        fi
        
        rm -f "$reg_file"
        
        if [ $dll_copied -gt 0 ]; then
            print_success "OpenCL support fully configured for $app_name!"
        fi
    else
        if [ ! -d "$app_dir" ]; then
            print_warning "$app_name installation directory not found. OpenCL configuration skipped."
        fi
    fi
}

# Function to create desktop entry
create_desktop_entry() {
    local app_name=$1
    local app_path=$2
    local icon_path=$3
    local desktop_file="$HOME/.local/share/applications/Affinity$app_name.desktop"
    # Normalize paths to avoid double slashes
    local directory="${HOME}/.AffinityLinux"
    directory="${directory%/}"
    # Normalize path: ensure forward slashes, remove double slashes
    app_path="${app_path//\\/\/}"
    app_path="${app_path//\/\//\/}"
    # Convert Windows path (C:/...) to Linux path if needed
    if [[ "$app_path" == C:/ ]]; then
        app_path="${app_path#C:/}"
        app_path="$directory/drive_c/$app_path"
    fi
    
    # Check for AMD GPU for DXVK configuration
    local dxvk_env=""
    if command -v lspci &> /dev/null; then
        if lspci | grep -qiE "(amd|radeon|amd/ati).*vga\|3d\|display"; then
            dxvk_env='DXVK_ASYNC=0 DXVK_CONFIG="d3d9.deferSurfaceCreation = True; d3d9.shaderModel = 1" '
        fi
    fi
    
    echo "[Desktop Entry]" > "$desktop_file"
    echo "Name=Affinity $app_name" >> "$desktop_file"
    echo "Comment=A powerful $app_name software." >> "$desktop_file"
    echo "Icon=$icon_path" >> "$desktop_file"
    echo "Path=$directory" >> "$desktop_file"
    echo "Exec=env WINEPREFIX=$directory ${dxvk_env}$(get_wine_binary) \"$app_path\"" >> "$desktop_file"
    echo "Terminal=false" >> "$desktop_file"
    echo "NoDisplay=false" >> "$desktop_file"
    echo "StartupWMClass=${app_name,,}.exe" >> "$desktop_file"
    echo "Type=Application" >> "$desktop_file"
    echo "Categories=Graphics;" >> "$desktop_file"
    echo "StartupNotify=true" >> "$desktop_file"
}

# Function to create Affinity desktop entry
create_all_in_one_desktop_entry() {
    local icon_path=$1
    local desktop_file="$HOME/.local/share/applications/Affinity.desktop"
    local directory="$HOME/.AffinityLinux"
    # Normalize directory path (remove trailing slash if present)
    directory="${directory%/}"
    
    # Check for AMD GPU for DXVK configuration
    local dxvk_env=""
    if command -v lspci &> /dev/null; then
        if lspci | grep -qiE "(amd|radeon|amd/ati).*vga\|3d\|display"; then
            dxvk_env='DXVK_ASYNC=0 DXVK_CONFIG="d3d9.deferSurfaceCreation = True; d3d9.shaderModel = 1" '
        fi
    fi
    
    echo "[Desktop Entry]" > "$desktop_file"
    echo "Name=Affinity" >> "$desktop_file"
    echo "Comment=The unified Affinity application for photo editing, design, and publishing" >> "$desktop_file"
    echo "Icon=$icon_path" >> "$desktop_file"
    echo "Path=$directory" >> "$desktop_file"
    echo "Exec=env WINEPREFIX=$directory ${dxvk_env}$(get_wine_binary) \"$directory/drive_c/Program Files/Affinity/Affinity/Affinity.exe\"" >> "$desktop_file"
    echo "Terminal=false" >> "$desktop_file"
    echo "NoDisplay=false" >> "$desktop_file"
    echo "Type=Application" >> "$desktop_file"
    echo "Categories=Graphics;" >> "$desktop_file"
    echo "StartupNotify=true" >> "$desktop_file"
    echo "StartupWMClass=affinity.exe" >> "$desktop_file"
}

# Function to normalize and validate file path
normalize_path() {
    local path="$1"
    
    # Remove quotes and trim whitespace
    path=$(echo "$path" | tr -d '"' | xargs)
    
    # Handle file:// URLs (common when dragging from file managers)
    if [[ "$path" == file://* ]]; then
        path=$(echo "$path" | sed 's|^file://||')
        # URL decode the path
        path=$(printf '%b' "${path//%/\\x}")
    fi
    
    # Convert to absolute path if relative
    if [[ ! "$path" = /* ]]; then
        path="$(pwd)/$path"
    fi
    
    # Normalize path (remove . and .. components)
    path=$(realpath -q "$path" 2>/dev/null || echo "$path")
    
    echo "$path"
}

# Function to restore WinMetadata after Affinity installation
restore_winmetadata() {
    local directory="$HOME/.AffinityLinux"
    
    print_step "Restoring Windows metadata files..."
    
    # Kill any running Wine processes to prevent file locks
    print_progress "Stopping Wine processes to prevent file locks..."
    wineserver -k 2>/dev/null || true
    # Wait a moment for processes to fully terminate
    sleep 2
    
    # Ensure system32 directory exists
    mkdir -p "$directory/drive_c/windows/system32"
    
    # Check if we have a cached WinMetadata.zip
    if [ -f "$directory/Winmetadata.zip" ] && [ -s "$directory/Winmetadata.zip" ]; then
        print_progress "Found cached WinMetadata.zip, re-extracting..."
        
        # Try extraction with 7z first (more reliable)
        if command -v 7z &> /dev/null; then
            if 7z x "$directory/Winmetadata.zip" -o"$directory/drive_c/windows/system32" -y >/dev/null 2>&1; then
                print_success "Windows metadata restored successfully using 7z"
                return 0
            else
                print_warning "7z extraction had issues, trying unzip..."
                # unzip -o means overwrite without prompting, -q means quiet mode
                if unzip -o -q "$directory/Winmetadata.zip" -d "$directory/drive_c/windows/system32" 2>/dev/null; then
                    print_success "Windows metadata restored using unzip"
                    return 0
                else
                    print_warning "Both 7z and unzip extraction failed for cached file"
                fi
            fi
        elif command -v unzip &> /dev/null; then
            if unzip -o -q "$directory/Winmetadata.zip" -d "$directory/drive_c/windows/system32" 2>/dev/null; then
                print_success "Windows metadata restored successfully using unzip"
                return 0
            else
                print_warning "unzip extraction failed for cached file"
            fi
        else
            print_warning "No extraction tools available for cached file"
        fi
        
        print_warning "Failed to extract cached WinMetadata.zip, attempting to re-download..."
    fi
    
    # If no cache or extraction failed, try to re-download
    print_progress "Downloading Windows metadata from archive.org..."
    if wget -q --show-progress "https://archive.org/download/win-metadata/WinMetadata.zip" -O "$directory/Winmetadata.zip"; then
        if [ -s "$directory/Winmetadata.zip" ]; then
            print_success "Windows metadata downloaded successfully"
            
            # Now extract it
            if command -v 7z &> /dev/null; then
                if 7z x "$directory/Winmetadata.zip" -o"$directory/drive_c/windows/system32" -y >/dev/null 2>&1; then
                    print_success "Windows metadata extracted successfully using 7z"
                    return 0
                else
                    print_warning "7z extraction had issues, trying unzip..."
                    if unzip -o -q "$directory/Winmetadata.zip" -d "$directory/drive_c/windows/system32" 2>/dev/null; then
                        print_success "Windows metadata extracted using unzip"
                        return 0
                    else
                        print_error "Both 7z and unzip extraction failed"
                    fi
                fi
            elif command -v unzip &> /dev/null; then
                if unzip -o -q "$directory/Winmetadata.zip" -d "$directory/drive_c/windows/system32" 2>/dev/null; then
                    print_success "Windows metadata extracted successfully using unzip"
                    return 0
                else
                    print_error "unzip extraction failed"
                fi
            else
                print_error "Neither 7z nor unzip is available to extract Windows metadata"
            fi
        else
            print_error "Downloaded file is empty or corrupted"
            rm -f "$directory/Winmetadata.zip"
            return 1
        fi
    else
        print_warning "Failed to download Windows metadata (this may cause minor issues)"
        rm -f "$directory/Winmetadata.zip"
        return 1
    fi
    
    print_warning "Could not restore Windows metadata"
    return 1
}

# Function to install Affinity app
install_affinity() {
    local app_name=$1
    local directory="$HOME/.AffinityLinux"
    
    print_header "Affinity $app_name Installation"
    print_info "You will now install Affinity $app_name using its Windows installer"
    
    # Verify Windows version before installation
    verify_windows_version
    
    echo ""
    print_step "How would you like to proceed?"
    echo ""
    echo -e "  ${GREEN}1.${NC} Provide my own Affinity installer file"
    echo -e "  ${GREEN}2.${NC} Have the script download the installer for me"
    echo ""
    echo -n -e "${BOLD}Please select an option (1 or 2): ${NC}"
    read -r installer_choice
    
    local installer_path=""
    local filename=""
    
    case $installer_choice in
        1)
            # User provides their own installer
            echo ""
            print_step "Please download the Affinity $app_name installer (.exe) from:"
            echo -e "  ${CYAN}https://www.affinity.studio/account/licenses/${NC}"
            echo ""
            print_step "Once downloaded, drag and drop the installer into this terminal and press Enter:"
            read installer_path
            
            # Normalize the path
            installer_path=$(normalize_path "$installer_path")
            
            # Check if file exists and is readable
            if [ ! -f "$installer_path" ] || [ ! -r "$installer_path" ]; then
                print_error "Invalid file path or file is not readable: $installer_path"
                return 1
            fi
            
            # Get the filename from the path and sanitize it (replace spaces)
            filename=$(basename "$installer_path")
            # Replace spaces with dashes to avoid issues
            filename=$(echo "$filename" | tr ' ' '-')
            
            # Copy installer to Affinity directory
            print_step "Copying installer to installation directory..."
            cp "$installer_path" "$directory/$filename"
            print_success "Installer copied"
            ;;
        2)
            # Script downloads the installer
            echo ""
            print_step "Downloading Affinity $app_name installer..."
            
            # Determine download URL based on app name
            local download_url=""
            case $app_name in
                "Add")
                    download_url="https://downloads.affinity.studio/Affinity%20x64.exe"
                    filename="Affinity-x64.exe"
                    ;;
                "Photo")
                    download_url="https://downloads.affinity.studio/Affinity%20Photo%20x64.exe"
                    filename="Affinity-Photo-x64.exe"
                    ;;
                "Designer")
                    download_url="https://downloads.affinity.studio/Affinity%20Designer%20x64.exe"
                    filename="Affinity-Designer-x64.exe"
                    ;;
                "Publisher")
                    download_url="https://downloads.affinity.studio/Affinity%20Publisher%20x64.exe"
                    filename="Affinity-Publisher-x64.exe"
                    ;;
                *)
                    print_error "Unknown application: $app_name"
                    print_info "Please use option 1 to provide your own installer"
                    return 1
                    ;;
            esac
            
            installer_path="$directory/$filename"
            
            # Download the installer
            if download_file "$download_url" "$installer_path" "Affinity $app_name installer"; then
                print_success "Installer downloaded successfully"
            else
                print_error "Failed to download installer"
                print_info "You can try option 1 to provide your own installer, or download manually from:"
                echo -e "  ${CYAN}https://www.affinity.studio/account/licenses/${NC}"
                return 1
            fi
            ;;
        *)
            print_error "Invalid option. Please select 1 or 2."
            return 1
            ;;
    esac
    
    # Run installer
    print_step "Launching Affinity $app_name installer..."
    print_info "Follow the installation wizard in the window that opens"
    print_warning "If you encounter any errors during installation, click 'No' to continue"
    print_info "Press any key to start the installation..."
    read -n 1 -s
    echo ""
    
    # Run installer with debug messages suppressed
    WINEPREFIX="$directory" WINEDEBUG=-all "$(get_wine_binary)" "$directory/$filename"
    
    # Wait for installer to fully complete and any Wine processes to finish
    print_step "Waiting for installer processes to complete..."
    sleep 3
    
    # Clean up installer
    print_step "Cleaning up installer file..."
    rm -f "$directory/$filename"
    print_success "Installer file removed"
    
    # Restore WinMetadata (may have been corrupted by installer)
    restore_winmetadata
    
    # Configure OpenCL support based on which app was installed
    print_header "Post-Installation Configuration"
    print_info "Applying final configuration settings..."
    
    case $app_name in
        "Photo")
            configure_opencl "$directory/drive_c/Program Files/Affinity/Photo 2" "Affinity Photo"
            ;;
        "Designer")
            configure_opencl "$directory/drive_c/Program Files/Affinity/Designer 2" "Affinity Designer"
            ;;
        "Publisher")
            configure_opencl "$directory/drive_c/Program Files/Affinity/Publisher 2" "Affinity Publisher"
            ;;
        "Add")
            configure_opencl "$directory/drive_c/Program Files/Affinity/Affinity" "Affinity"
            ;;
    esac
    
    # Remove Wine's default desktop entry
    print_step "Removing default Wine desktop entry..."
    rm -f "/home/$USER/.local/share/applications/wine/Programs/Affinity $app_name 2.desktop"
    # Also remove Affinity.desktop for the unified Affinity app
    if [ "$app_name" = "Add" ]; then
        rm -f "/home/$USER/.local/share/applications/wine/Programs/Affinity.desktop"
    fi
    print_success "Default entry removed"
    
    # Create desktop entry
    print_step "Creating custom desktop entry..."
    case $app_name in
        "Photo")
            create_desktop_entry "Photo" "$directory/drive_c/Program Files/Affinity/Photo 2/Photo.exe" "$HOME/.local/share/icons/AffinityPhoto.svg"
            ;;
        "Designer")
            create_desktop_entry "Designer" "$directory/drive_c/Program Files/Affinity/Designer 2/Designer.exe" "$HOME/.local/share/icons/AffinityDesigner.svg"
            ;;
        "Publisher")
            create_desktop_entry "Publisher" "$directory/drive_c/Program Files/Affinity/Publisher 2/Publisher.exe" "$HOME/.local/share/icons/AffinityPublisher.svg"
            ;;
        "Add")
            # Create Affinity desktop entry using official V3 icon
            icon_path="$HOME/.local/share/icons/Affinity.svg"
            if [ ! -f "$icon_path" ]; then
                # Download the official icon if it wasn't already downloaded
                print_progress "Downloading official Affinity V3 icon..."
                if download_file "https://github.com/seapear/AffinityOnLinux/raw/main/Assets/Icons/Affinity-V3.svg" "$icon_path" "Affinity V3 icon"; then
                    print_success "Official Affinity V3 icon downloaded"
                else
                    print_warning "Failed to download official icon, using Photo icon as fallback"
                    icon_path="$HOME/.local/share/icons/AffinityPhoto.svg"
                fi
            fi
            create_all_in_one_desktop_entry "$icon_path"
            ;;
    esac
    
    # Create desktop shortcut
    desktop_file="$HOME/.local/share/applications/Affinity${app_name}.desktop"
    if [ "$app_name" = "Add" ]; then
        desktop_file="$HOME/.local/share/applications/Affinity.desktop"
    fi
    mkdir -p ~/Desktop
    cp "$desktop_file" ~/Desktop/ 2>/dev/null || true
    print_success "Desktop shortcut created"
    
    print_success "Affinity $app_name installation completed!"
    echo ""
    print_info "You can now launch Affinity $app_name from your application menu or desktop shortcut."
    print_info "OpenCL hardware acceleration should be enabled. You can verify this in:"
    echo -e "  ${CYAN}•${NC} Affinity Preferences → Performance → Hardware Acceleration"
    echo ""
}

# ==========================================
# User Interface Functions
# ==========================================

# Function to show special thanks
show_special_thanks() {
    print_header "Special Thanks"
    echo "Ardishco (github.com/raidenovich)"
    echo "Deviaze"
    echo "Kemal"
    echo "Jacazimbo <3"
    echo "Kharoon"
    echo "Jediclank134"
    echo ""
}

# Main menu
show_menu() {
    clear
    print_header "Affinity Linux Installer"
    echo ""
    echo -e "${BOLD}Available Applications:${NC}"
    echo ""
    echo -e "  ${GREEN}1.${NC} ${BOLD}Affinity${NC} (Unified Application)"
    echo -e "      ${CYAN}The new unified Affinity application that combines Photo, Designer," 
    echo -e "      Publisher, and more into a single modern interface.${NC}"
    echo ""
    echo -e "  ${GREEN}2.${NC} ${BOLD}Affinity Photo${NC}"
    echo -e "      ${CYAN}Professional photo editing and image manipulation software with" 
    echo -e "      advanced tools for photographers and digital artists.${NC}"
    echo ""
    echo -e "  ${GREEN}3.${NC} ${BOLD}Affinity Designer${NC}"
    echo -e "      ${CYAN}Vector graphic design software for creating illustrations, logos," 
    echo -e "      UI designs, print projects, and mock-ups.${NC}"
    echo ""
    echo -e "  ${GREEN}4.${NC} ${BOLD}Affinity Publisher${NC}"
    echo -e "      ${CYAN}Desktop publishing application for creating professional layouts," 
    echo -e "      magazines, books, and print materials.${NC}"
    echo ""
    echo -e "  ${GREEN}5.${NC} ${BOLD}Show Special Thanks${NC}"
    echo ""
    echo -e "  ${GREEN}6.${NC} ${BOLD}Exit${NC}"
    echo ""
    echo -n -e "${BOLD}Please select an option (1-6): ${NC}"
}

# ==========================================
# Detection Functions
# ==========================================

# Function to quickly check if all dependencies are installed (without installing)
check_dependencies_quick() {
    local missing_deps=""
    
    for dep in wine winetricks wget curl 7z tar jq unzip cabextract; do
        if ! command -v "$dep" &> /dev/null; then
            missing_deps+="$dep "
        fi
    done
    
    # Check for zstd support
    if ! command -v unzstd &> /dev/null && ! command -v zstd &> /dev/null; then
        missing_deps+="zstd "
    fi

    if is_ubuntu_based_distro && ! command -v ntlm_auth &> /dev/null; then
        missing_deps+="winbind "
    fi

    if is_ubuntu_based_distro && command -v wine &> /dev/null && ! is_supported_ubuntu_wine_version; then
        missing_deps+="winehq-staging "
    fi
    
    if [ -n "$missing_deps" ]; then
        return 1  # Dependencies missing
    else
        return 0  # All dependencies present
    fi
}

# Function to check if Wine is set up
check_wine_setup() {
    local directory="$HOME/.AffinityLinux"
    
    if [ -f "$(get_wine_binary)" ]; then
        return 0  # Wine is set up
    else
        return 1  # Wine is not set up
    fi
}

# Function to detect installed Affinity products
detect_installed_affinity() {
    local directory="$HOME/.AffinityLinux"
    local installed_products=()
    
    # Check for unified Affinity (V3)
    if [ -f "$directory/drive_c/Program Files/Affinity/Affinity/Affinity.exe" ]; then
        installed_products+=("Affinity")
    fi
    
    # Check for Affinity Photo
    if [ -f "$directory/drive_c/Program Files/Affinity/Photo 2/Photo.exe" ]; then
        installed_products+=("Photo")
    fi
    
    # Check for Affinity Designer
    if [ -f "$directory/drive_c/Program Files/Affinity/Designer 2/Designer.exe" ]; then
        installed_products+=("Designer")
    fi
    
    # Check for Affinity Publisher
    if [ -f "$directory/drive_c/Program Files/Affinity/Publisher 2/Publisher.exe" ]; then
        installed_products+=("Publisher")
    fi
    
    # Output installed products as a space-separated string
    echo "${installed_products[@]}"
}

# Function to show detected installations
show_installed_affinity() {
    local installed=$(detect_installed_affinity)
    
    if [ -n "$installed" ]; then
        print_info "Detected installed Affinity products:"
        for product in $installed; do
            case $product in
                "Affinity")
                    print_progress "  ✓ Affinity (Unified Application)"
                    ;;
                "Photo")
                    print_progress "  ✓ Affinity Photo"
                    ;;
                "Designer")
                    print_progress "  ✓ Affinity Designer"
                    ;;
                "Publisher")
                    print_progress "  ✓ Affinity Publisher"
                    ;;
            esac
        done
        echo ""
    fi
}

# ==========================================
# Main Script
# ==========================================

main() {
    local directory="$HOME/.AffinityLinux"
    
    # Detect distribution
    detect_distro
    
    # Detect and select GPU (must be done early to set environment variables)
    detect_and_select_gpu "$directory"
    
    # Quick check: Are dependencies and Wine already set up?
    if check_dependencies_quick && check_wine_setup; then
        # Everything is ready, skip setup and show menu directly
        local installed=$(detect_installed_affinity)
        
        print_header "Affinity Linux Installer"
        print_info "Detected distribution: $DISTRO $VERSION"
        echo ""
        
        if [ -n "$installed" ]; then
            print_success "System is ready! All dependencies and Wine are installed."
            echo ""
            show_installed_affinity
            print_info "Ready to install additional Affinity products or manage existing installations."
            echo ""
            read -n 1 -s -r -p "Press any key to continue to the menu..."
            echo ""
        else
            print_success "System is ready! All dependencies and Wine are installed."
            echo ""
            print_info "Ready to install Affinity products."
            echo ""
            read -n 1 -s -r -p "Press any key to continue to the menu..."
            echo ""
        fi
    else
        # Need to set things up
        print_header "Affinity Linux Installer - Initialization"
        print_info "Detected distribution: $DISTRO $VERSION"
        echo ""
        
        # Check and install dependencies
        check_dependencies
        
        # Setup Wine (only once)
        setup_wine
        
        # Show what's already installed
        show_installed_affinity
    fi
    
    while true; do
        show_menu
        read -r choice
        
        case $choice in
            1)
                install_affinity "Add"
                ;;
            2)
                install_affinity "Photo"
                ;;
            3)
                install_affinity "Designer"
                ;;
            4)
                install_affinity "Publisher"
                ;;
            5)
                show_special_thanks
                ;;
            6)
                print_header "Thank You"
                print_success "Thank you for using the Affinity Installation Script!"
                exit 0
                ;;
            *)
                print_error "Invalid option. Please select a number between 1 and 6."
                ;;
        esac
        
        if [ "$choice" != "6" ]; then
            echo ""
            read -n 1 -s -r -p "Press any key to continue..."
        fi
    done
}

# Run main function
main
