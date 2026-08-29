#!/bin/bash

################################################################################
# Affinity Wine 10.17+ Installation Script
# This script follows the Wine 10.17+ guide for installing Affinity apps
# with Windows Runtime (WinRT) support.
# Guide: https://raw.githubusercontent.com/seapear/AffinityOnLinux/refs/heads/main/Guides/Wine/Guide.md
################################################################################

# Check if script is executable, if not make it executable
if [ ! -x "$(readlink -f "$0")" ]; then
    echo "Making script executable..."
    chmod +x "$(readlink -f "$0")"
fi

# Ensure script is being run with bash
if [ -z "$BASH_VERSION" ]; then
    echo "Running script in bash"
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

# Wine prefix - use environment variable if set, otherwise prompt user

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

# Function to check if command exists
check_command() {
    command -v "$1" &> /dev/null
}

# Function to download files
download_file() {
    local url=$1
    local output=$2
    local description=$3
    
    print_progress "Downloading $description..."
    
    if command -v curl &> /dev/null; then
        if curl -# -L "$url" -o "$output"; then
            return 0
        fi
    elif command -v wget &> /dev/null; then
        if wget --progress=bar:force -O "$output" "$url" 2>&1 | grep -q "100%"; then
            return 0
        fi
    fi
    
    return 1
}

# Function to check Wine version
check_wine_version() {
    if ! check_command wine; then
        return 1
    fi
    
    local wine_version=$(wine --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1)
    if [ -z "$wine_version" ]; then
        return 1
    fi
    
    # Compare version (need 10.17 or newer)
    local major=$(echo "$wine_version" | cut -d. -f1)
    local minor=$(echo "$wine_version" | cut -d. -f2)
    
    if [ "$major" -gt 10 ] || ([ "$major" -eq 10 ] && [ "$minor" -ge 17 ]); then
        return 0
    fi
    
    return 1
}

# Function to detect distribution
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "$ID" | tr '[:upper:]' '[:lower:]'
    else
        echo "unknown"
    fi
}

# ==========================================
# Main Installation Functions
# ==========================================

install_wine_and_winetricks() {
    print_header "Installing Wine 10.17+ and Winetricks"
    
    local distro=$(detect_distro)
    
    case $distro in
        "fedora"|"nobara")
            print_step "Installing Wine and Winetricks for Fedora/Nobara..."
            print_info "Setting up WineHQ repository..."
            
            if ! check_command curl; then
                print_progress "Installing curl..."
                sudo dnf install curl -y || {
                    print_error "Failed to install curl"
                    return 1
                }
            fi
            
            # Remove existing winehq repo if present
            sudo rm -f /etc/yum.repos.d/winehq.repo
            
            # Add WineHQ repo
            print_progress "Adding WineHQ repository..."
            sudo tee /etc/yum.repos.d/winehq.repo <<'EOF'
[winehq-devel]
name=WineHQ packages for Fedora 41
baseurl=https://dl.winehq.org/wine-builds/fedora/41/
enabled=1
gpgcheck=0
EOF
            
            sudo dnf makecache || {
                print_warning "Failed to update cache, continuing anyway..."
            }
            
            print_progress "Installing winehq-devel..."
            sudo dnf install winehq-devel -y || {
                print_error "Failed to install winehq-devel"
                return 1
            }
            
            # Try to install winetricks via dnf, fallback to manual if needed
            if ! sudo dnf install winetricks -y 2>/dev/null; then
                print_warning "Failed to install winetricks via dnf, installing manually..."
                install_winetricks_manual
            fi
            ;;
            
        "arch"|"manjaro"|"endeavouros"|"cachyos"|"xerolinux")
            print_step "Installing Wine and Winetricks for Arch-based systems..."
            sudo pacman -S --needed wine winetricks curl || {
                print_error "Failed to install Wine and Winetricks"
                return 1
            }
            ;;
            
        "ubuntu"|"debian"|"pop")
            print_step "Installing Wine and Winetricks for Ubuntu/Debian/Pop..."
            
            if ! check_command curl; then
                print_progress "Installing curl..."
                sudo apt update && sudo apt install curl -y || {
                    print_error "Failed to install curl"
                    return 1
                }
            fi
            
            print_progress "Setting up WineHQ repository..."
            sudo dpkg --add-architecture i386
            sudo mkdir -pm755 /etc/apt/keyrings
            sudo wget -O /etc/apt/keyrings/winehq.asc https://dl.winehq.org/wine-builds/winehq.key || {
                print_error "Failed to download WineHQ key"
                return 1
            }
            
            local codename=$(lsb_release -cs)
            sudo sh -c "echo \"deb [signed-by=/etc/apt/keyrings/winehq.asc] https://dl.winehq.org/wine-builds/ubuntu $codename main\" > /etc/apt/sources.list.d/winehq.list"
            
            sudo apt update || {
                print_error "Failed to update package list"
                return 1
            }
            
            sudo apt install --install-recommends winehq-devel winetricks curl -y || {
                print_error "Failed to install Wine and Winetricks"
                return 1
            }
            ;;
            
        *)
            print_warning "Unsupported distribution: $distro"
            print_info "Please install Wine 10.17+ and Winetricks manually"
            print_info "Then run this script again"
            return 1
            ;;
    esac
    
    # Verify Wine version
    if check_wine_version; then
        local wine_version=$(wine --version)
        print_success "Wine installed: $wine_version"
    else
        print_error "Wine 10.17+ is required, but found: $(wine --version 2>/dev/null || echo 'not installed')"
        return 1
    fi
    
    # Verify Winetricks
    if check_command winetricks; then
        print_success "Winetricks installed"
    else
        print_warning "Winetricks not found, installing manually..."
        install_winetricks_manual
    fi
    
    return 0
}

install_winetricks_manual() {
    print_step "Installing Winetricks manually..."
    
    local winetricks_path="$HOME/winetricks"
    
    if download_file "https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks" "$winetricks_path" "winetricks"; then
        chmod +x "$winetricks_path"
        print_success "Winetricks downloaded to $winetricks_path"
        print_info "You can use it with: $winetricks_path"
        print_info "Or install globally with: sudo mv $winetricks_path /usr/local/bin/winetricks"
        
        # Ask if user wants to install globally
        read -p "Install winetricks globally? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo mv "$winetricks_path" /usr/local/bin/winetricks || {
                print_warning "Failed to move to /usr/local/bin, using local copy"
            }
        fi
    else
        print_error "Failed to download winetricks"
        return 1
    fi
}

create_wine_prefix() {
    print_header "Creating Wine Prefix"
    
    local prefix=$(get_wine_prefix)
    print_step "Initializing Wine prefix at: $prefix"
    
    # Only export WINEPREFIX if it was set in environment
    if [ -n "$WINEPREFIX" ]; then
        export WINEPREFIX
    fi
    
    # Check if prefix already exists
    if [ -d "$prefix" ] && [ -f "$prefix/system.reg" ]; then
        print_info "Wine prefix already exists, skipping initialization"
    else
        if [ -n "$WINEPREFIX" ]; then
            wineboot --init || {
                print_error "Failed to initialize Wine prefix"
                return 1
            }
        else
            WINEPREFIX="$prefix" wineboot --init || {
                print_error "Failed to initialize Wine prefix"
                return 1
            }
        fi
        print_success "Wine prefix created"
    fi
    
    return 0
}

# Function to get Wine prefix path (use environment or default)
get_wine_prefix() {
    if [ -n "$WINEPREFIX" ]; then
        echo "$WINEPREFIX"
    else
        # Use .affinity as default to match guide, but allow .wine for compatibility
        if [ -d "$HOME/.affinity" ] && [ -f "$HOME/.affinity/system.reg" ]; then
            echo "$HOME/.affinity"
        else
            echo "$HOME/.wine"
        fi
    fi
}

# Function to check if a winetricks component is already installed
check_winetricks_component() {
    local component=$1
    local winetricks_cmd=$2
    local prefix=$(get_wine_prefix)
    
    # Use winetricks list-installed to check
    if WINEPREFIX="$prefix" "$winetricks_cmd" list-installed 2>/dev/null | grep -q "^$component$"; then
        return 0  # Component is installed
    fi
    
    # Additional checks for specific components
    case $component in
        "dotnet35")
            # Check for .NET 3.5 installation - verify both files and registry
            local net35_installed=false
            
            # Check for .NET 3.5 files
            if [ -d "$prefix/drive_c/windows/Microsoft.NET/Framework/v2.0.50727" ] && \
               [ -f "$prefix/drive_c/windows/Microsoft.NET/Framework/v2.0.50727/mscorlib.dll" ]; then
                net35_installed=true
            fi
            
            # Also check for v3.5 directory
            if [ -d "$prefix/drive_c/windows/Microsoft.NET/Framework/v3.5" ]; then
                net35_installed=true
            fi
            
            # Verify via registry that .NET 3.5 is enabled
            if [ "$net35_installed" = true ]; then
                # Check registry for .NET 3.5 installation status
                if WINEPREFIX="$prefix" wine reg query "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\NET Framework Setup\\NDP\\v3.5" /v Install 2>/dev/null | grep -q "0x1"; then
                    return 0
                elif WINEPREFIX="$prefix" wine reg query "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\NET Framework Setup\\NDP\\v2.0.50727" /v Install 2>/dev/null | grep -q "0x1"; then
                    return 0
                elif [ "$net35_installed" = true ]; then
                    # Files exist, assume it's installed even if registry check fails
                    return 0
                fi
            fi
            ;;
        "dotnet48")
            # Check for .NET 4.8 installation
            if [ -d "$prefix/drive_c/windows/Microsoft.NET/Framework64/v4.0.30319" ] || \
               [ -d "$prefix/drive_c/windows/Microsoft.NET/Framework/v4.0.30319" ]; then
                return 0
            fi
            ;;
        "vcrun2022")
            # Check for VC++ 2022 redistributables
            if [ -f "$prefix/drive_c/windows/system32/vcruntime140.dll" ] || \
               [ -f "$prefix/drive_c/windows/syswow64/vcruntime140.dll" ]; then
                return 0
            fi
            ;;
        "corefonts")
            # Check for core fonts
            if [ -d "$prefix/drive_c/windows/Fonts" ] && \
               [ -f "$prefix/drive_c/windows/Fonts/arial.ttf" ]; then
                return 0
            fi
            ;;
        "tahoma")
            # Check for Tahoma font
            if [ -f "$prefix/drive_c/windows/Fonts/tahoma.ttf" ] || \
               [ -f "$prefix/drive_c/windows/Fonts/tahomabd.ttf" ]; then
                return 0
            fi
            ;;
        "win11")
            # Check Windows version in registry
            if WINEPREFIX="$prefix" wine reg query "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\Windows NT\\CurrentVersion" /v CurrentVersion 2>/dev/null | grep -q "10.0"; then
                return 0
            fi
            ;;
        "renderer=vulkan")
            # Check for Vulkan renderer setting
            if WINEPREFIX="$prefix" wine reg query "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "winevulkan" 2>/dev/null | grep -q "native"; then
                return 0
            fi
            ;;
    esac
    
    return 1  # Component is not installed
}

install_runtime_dependencies() {
    print_header "Installing Runtime Dependencies"
    
    print_info "Checking and installing core components via Winetricks..."
    print_warning "This may take 10-20 minutes, especially for .NET 4.8"
    
    local prefix=$(get_wine_prefix)
    
    # Only export WINEPREFIX if it was set in environment
    if [ -n "$WINEPREFIX" ]; then
        export WINEPREFIX
    fi
    
    # Get winetricks path (prefer system, fallback to local)
    local winetricks_cmd="winetricks"
    if ! check_command winetricks; then
        if [ -f "$HOME/winetricks" ]; then
            winetricks_cmd="$HOME/winetricks"
        else
            print_error "Winetricks not found"
            return 1
        fi
    fi
    
    # Function to install component if not already installed
    install_component_if_needed() {
        local component=$1
        local description=$2
        
        if check_winetricks_component "$component" "$winetricks_cmd"; then
            print_success "$description is already installed, skipping..."
            return 0
        fi
        
        print_step "Installing $description..."
        if [ "$component" = "dotnet48" ]; then
            print_warning "This is a large download and may take 10-20 minutes..."
        fi
        
        # Show winetricks output for progress tracking
        echo ""
        print_info "Winetricks output (this may take a while):"
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        
        # Run winetricks and show output in real-time
        local winetricks_exit=0
        
        # Show output in real-time with basic filtering
        if [ -n "$WINEPREFIX" ]; then
            export WINEPREFIX
            WINEPREFIX="$prefix" "$winetricks_cmd" --unattended --force "$component" 2>&1 | while IFS= read -r line; do
                # Show important progress indicators
                if [[ "$line" =~ (downloading|Downloading|extracting|Extracting|installing|Installing|executing|Executing|progress|Progress|%) ]]; then
                    echo -e "${CYAN}  →${NC} $line"
                elif [[ "$line" =~ (error|Error|ERROR|failed|Failed|FAILED) ]]; then
                    echo -e "${YELLOW}  ⚠${NC} $line"
                elif [[ "$line" =~ (success|Success|SUCCESS|done|Done|DONE|complete|Complete|COMPLETE) ]]; then
                    echo -e "${GREEN}  ✓${NC} $line"
                elif [[ "$line" =~ (warning|Warning|WARNING) ]]; then
                    echo -e "${YELLOW}  ⚠${NC} $line"
                elif [[ -n "$line" && ! "$line" =~ (fixme|FIXME|trace|TRACE|warn:|WARN:|debug|DEBUG) ]]; then
                    # Show other non-empty lines, but filter out debug messages
                    echo "  $line"
                fi
            done
            # Capture exit code (note: pipe makes this tricky, so we'll verify after)
            winetricks_exit=${PIPESTATUS[0]}
        else
            WINEPREFIX="$prefix" "$winetricks_cmd" --unattended --force "$component" 2>&1 | while IFS= read -r line; do
                # Show important progress indicators
                if [[ "$line" =~ (downloading|Downloading|extracting|Extracting|installing|Installing|executing|Executing|progress|Progress|%) ]]; then
                    echo -e "${CYAN}  →${NC} $line"
                elif [[ "$line" =~ (error|Error|ERROR|failed|Failed|FAILED) ]]; then
                    echo -e "${YELLOW}  ⚠${NC} $line"
                elif [[ "$line" =~ (success|Success|SUCCESS|done|Done|DONE|complete|Complete|COMPLETE) ]]; then
                    echo -e "${GREEN}  ✓${NC} $line"
                elif [[ "$line" =~ (warning|Warning|WARNING) ]]; then
                    echo -e "${YELLOW}  ⚠${NC} $line"
                elif [[ -n "$line" && ! "$line" =~ (fixme|FIXME|trace|TRACE|warn:|WARN:|debug|DEBUG) ]]; then
                    # Show other non-empty lines, but filter out debug messages
                    echo "  $line"
                fi
            done
            # Capture exit code
            winetricks_exit=${PIPESTATUS[0]}
        fi
        
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        
        # Verify installation regardless of exit code (winetricks can be unreliable)
        if check_winetricks_component "$component" "$winetricks_cmd"; then
            print_success "$description installation completed"
        else
            # Winetricks often returns non-zero even on success
            if [ $winetricks_exit -eq 0 ]; then
                print_success "$description installation completed"
            else
                print_warning "$description installation may have had issues (checking...)"
                # Sometimes components install but winetricks reports failure
                sleep 1
                if check_winetricks_component "$component" "$winetricks_cmd"; then
                    print_success "$description is now installed"
                else
                    print_warning "$description may not have installed correctly (this is sometimes normal)"
                fi
            fi
        fi
        echo ""
    }
    
    # Install required components (matching guide order)
    # Guide: winetricks --unattended --force remove_mono vcrun2022 dotnet48 corefonts win11
    # Note: Guide also mentions optional renderer=vulkan and tahoma, but we install them by default
    install_component_if_needed "remove_mono" "Remove Mono"
    install_component_if_needed "vcrun2022" "Visual C++ Redistributables 2022"
    install_component_if_needed "dotnet48" ".NET Framework 4.8"
    install_component_if_needed "corefonts" "Windows Core Fonts"
    install_component_if_needed "win11" "Windows 11 compatibility"
    install_component_if_needed "tahoma" "Tahoma font"
    install_component_if_needed "renderer=vulkan" "Vulkan renderer"
    
    # Configure Wine to use Windows 11 compatibility mode
    print_step "Configuring Wine to use Windows 11 compatibility mode..."
    if [ -n "$WINEPREFIX" ]; then
        export WINEPREFIX
        winecfg -v win11 >/dev/null 2>&1 || true
    else
        WINEPREFIX="$prefix" winecfg -v win11 >/dev/null 2>&1 || true
    fi
    print_success "Wine configured for Windows 11"
    
    print_success "Runtime dependencies check and installation completed"
    return 0
}

download_helper_files() {
    print_header "Downloading Helper Files"
    
    local tmp_dir="/tmp"
    local winmd_url="https://github.com/microsoft/windows-rs/raw/master/crates/libs/bindgen/default/Windows.winmd"
    local dll_url="https://github.com/ElementalWarrior/wine-wintypes.dll-for-affinity/raw/refs/heads/master/wintypes_shim.dll.so"
    
    # Check if Windows.winmd already exists
    if [ -f "$tmp_dir/Windows.winmd" ]; then
        print_success "Windows.winmd already exists, skipping download"
    else
        print_step "Downloading Windows.winmd..."
        if download_file "$winmd_url" "$tmp_dir/Windows.winmd" "Windows.winmd"; then
            print_success "Windows.winmd downloaded"
        else
            print_error "Failed to download Windows.winmd"
            return 1
        fi
    fi
    
    # Check if wintypes.dll already exists
    if [ -f "$tmp_dir/wintypes.dll" ] || [ -f "$tmp_dir/wintypes.dll.so" ]; then
        print_success "wintypes.dll already exists, skipping download"
        # Ensure it's named correctly
        if [ -f "$tmp_dir/wintypes.dll.so" ] && [ ! -f "$tmp_dir/wintypes.dll" ]; then
            mv "$tmp_dir/wintypes.dll.so" "$tmp_dir/wintypes.dll" 2>/dev/null || true
        fi
    else
        print_step "Downloading wintypes.dll..."
        if download_file "$dll_url" "$tmp_dir/wintypes.dll.so" "wintypes.dll"; then
            # Rename if needed
            if [ -f "$tmp_dir/wintypes.dll.so" ]; then
                mv "$tmp_dir/wintypes.dll.so" "$tmp_dir/wintypes.dll" 2>/dev/null || true
            fi
            print_success "wintypes.dll downloaded"
        else
            print_error "Failed to download wintypes.dll"
            return 1
        fi
    fi
    
    return 0
}


install_opencl_support() {
    print_header "Installing OpenCL Support (vkd3d-proton)"
    
    # Check for AMD GPU
    local has_amd_gpu=false
    if command -v lspci &> /dev/null; then
        if lspci | grep -qiE "(amd|radeon|amd/ati).*vga\|3d\|display"; then
            has_amd_gpu=true
        fi
    fi
    
    if [ "$has_amd_gpu" = true ]; then
        print_info "AMD GPU detected - skipping vkd3d-proton installation, will use DXVK instead"
        print_info "DXVK will be configured in desktop shortcuts"
        return 0
    fi
    
    print_info "Installing vkd3d-proton for hardware acceleration and OpenCL support..."
    print_info "This enables GPU acceleration features in Affinity applications"
    
    local prefix=$(get_wine_prefix)
    local work_dir="/tmp"
    # Fetch latest vkd3d-proton version from GitHub API (fallback: 3.0.1)
    local vkd3d_version=""
    if command -v curl &> /dev/null; then
        vkd3d_version=$(curl -sf "https://api.github.com/repos/HansKristian-Work/vkd3d-proton/releases/latest" \
            | grep '"tag_name"' | sed -E 's/.*"v([^"]+)".*/\1/')
    elif command -v wget &> /dev/null; then
        vkd3d_version=$(wget -qO- "https://api.github.com/repos/HansKristian-Work/vkd3d-proton/releases/latest" \
            | grep '"tag_name"' | sed -E 's/.*"v([^"]+)".*/\1/')
    fi
    if [ -z "$vkd3d_version" ]; then
        vkd3d_version="3.0.1"
        print_warning "Could not fetch latest vkd3d-proton version. Using fallback: $vkd3d_version"
    fi

    local vkd3d_url="https://github.com/HansKristian-Work/vkd3d-proton/releases/download/v${vkd3d_version}/vkd3d-proton-${vkd3d_version}.tar.zst"
    local vkd3d_archive="$work_dir/vkd3d-proton-${vkd3d_version}.tar.zst"

    # Check if vkd3d-proton is already installed (check both possible locations)
    local wine_lib_dir_64="$prefix/lib64/wine/vkd3d-proton/x86_64-windows"
    local wine_lib_dir_32="$prefix/lib/wine/vkd3d-proton/x86_64-windows"
    local wine_lib_dir=""
    
    # Determine which lib directory exists
    if [ -d "$prefix/lib64" ]; then
        wine_lib_dir="$wine_lib_dir_64"
    elif [ -d "$prefix/lib" ]; then
        wine_lib_dir="$wine_lib_dir_32"
    else
        # Default to lib64
        wine_lib_dir="$wine_lib_dir_64"
    fi
    
    if [ -d "$wine_lib_dir" ] && [ -f "$wine_lib_dir/d3d12.dll" ]; then
        print_success "vkd3d-proton appears to be already installed, skipping download"
    else
        print_step "Downloading vkd3d-proton v${vkd3d_version} from GitHub..."
        if download_file "$vkd3d_url" "$vkd3d_archive" "vkd3d-proton"; then
            print_success "vkd3d-proton downloaded successfully"
        else
            print_error "Failed to download vkd3d-proton"
            print_warning "OpenCL support may not work correctly"
            return 1
        fi
        
        print_step "Extracting vkd3d-proton archive..."
        local extracted=false
        if command -v unzstd &> /dev/null; then
            if unzstd -f "$vkd3d_archive" -o "$work_dir/vkd3d-proton.tar" 2>/dev/null; then
                if tar -xf "$work_dir/vkd3d-proton.tar" -C "$work_dir" 2>/dev/null; then
                    rm -f "$work_dir/vkd3d-proton.tar"
                    extracted=true
                    print_success "vkd3d-proton extracted using unzstd"
                fi
            fi
        elif command -v zstd &> /dev/null && tar --help 2>&1 | grep -q "use-compress-program"; then
            if tar --use-compress-program=zstd -xf "$vkd3d_archive" -C "$work_dir" 2>/dev/null; then
                extracted=true
                print_success "vkd3d-proton extracted using zstd with tar"
            fi
        fi
        
        if [ "$extracted" = false ]; then
            print_error "Cannot extract .tar.zst file. Please install zstd (e.g., sudo pacman -S zstd)"
            print_warning "Skipping vkd3d-proton installation. OpenCL will not work!"
            rm -f "$vkd3d_archive"
            return 1
        fi
        
        rm -f "$vkd3d_archive"
    fi
    
    # Find extracted vkd3d-proton directory
    local vkd3d_dir=$(find "$work_dir" -maxdepth 1 -type d -name "vkd3d-proton-*" | head -1)
    if [ -z "$vkd3d_dir" ]; then
        # Check if already in wine lib directory
        if [ -d "$wine_lib_dir" ] && [ -f "$wine_lib_dir/d3d12.dll" ]; then
            print_success "vkd3d-proton DLLs already installed"
            return 0
        fi
        print_warning "Could not locate vkd3d-proton directory after extraction"
        return 1
    fi
    
    print_step "Installing vkd3d-proton DLLs to Wine library directory..."
    mkdir -p "$wine_lib_dir"
    
    local dll_count=0
    if [ -f "$vkd3d_dir/x64/d3d12.dll" ]; then
        cp "$vkd3d_dir/x64/d3d12.dll" "$wine_lib_dir/" 2>/dev/null && ((dll_count++))
    elif [ -f "$vkd3d_dir/d3d12.dll" ]; then
        cp "$vkd3d_dir/d3d12.dll" "$wine_lib_dir/" 2>/dev/null && ((dll_count++))
    fi
    
    if [ -f "$vkd3d_dir/x64/d3d12core.dll" ]; then
        cp "$vkd3d_dir/x64/d3d12core.dll" "$wine_lib_dir/" 2>/dev/null && ((dll_count++))
    elif [ -f "$vkd3d_dir/d3d12core.dll" ]; then
        cp "$vkd3d_dir/d3d12core.dll" "$wine_lib_dir/" 2>/dev/null && ((dll_count++))
    fi
    
    if [ -f "$vkd3d_dir/x64/dxgi.dll" ]; then
        cp "$vkd3d_dir/x64/dxgi.dll" "$wine_lib_dir/" 2>/dev/null && ((dll_count++))
    elif [ -f "$vkd3d_dir/dxgi.dll" ]; then
        cp "$vkd3d_dir/dxgi.dll" "$wine_lib_dir/" 2>/dev/null && ((dll_count++))
    fi
    
    if [ $dll_count -gt 0 ]; then
        print_success "Installed $dll_count DLL file(s) to Wine library directory"
    else
        print_warning "No DLL files were found or copied"
    fi
    
    # Clean up extracted directory
    print_step "Cleaning up extracted vkd3d-proton directory..."
    rm -rf "$vkd3d_dir"
    
    # Always configure Wine DLL overrides for OpenCL support (even if Affinity isn't installed yet)
    if [ -d "$wine_lib_dir" ]; then
        # Check if OpenCL DLL overrides are already configured
        local d3d12_configured=false
        local d3d12core_configured=false
        local prefix=$(get_wine_prefix)
        
        if [ -n "$WINEPREFIX" ]; then
            export WINEPREFIX
            if wine reg query "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "d3d12" 2>/dev/null | grep -q "native"; then
                d3d12_configured=true
            fi
            if wine reg query "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "d3d12core" 2>/dev/null | grep -q "native"; then
                d3d12core_configured=true
            fi
        else
            if WINEPREFIX="$prefix" wine reg query "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "d3d12" 2>/dev/null | grep -q "native"; then
                d3d12_configured=true
            fi
            if WINEPREFIX="$prefix" wine reg query "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "d3d12core" 2>/dev/null | grep -q "native"; then
                d3d12core_configured=true
            fi
        fi
        
        if [ "$d3d12_configured" = true ] && [ "$d3d12core_configured" = true ]; then
            print_success "OpenCL DLL overrides are already configured"
        else
            print_step "Configuring Wine DLL overrides for OpenCL support..."
            local reg_file="$work_dir/dll_overrides.reg"
            {
                echo "REGEDIT4"
                echo "[HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides]"
                echo "\"d3d12\"=\"native\""
                echo "\"d3d12core\"=\"native\""
            } > "$reg_file"
            
            if [ -n "$WINEPREFIX" ]; then
                export WINEPREFIX
                if wine regedit "$reg_file" >/dev/null 2>&1; then
                    print_success "DLL overrides configured in Wine registry"
                else
                    # Try alternative method
                    if wine reg add "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "d3d12" /t REG_SZ /d "native" /f >/dev/null 2>&1 && \
                       wine reg add "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "d3d12core" /t REG_SZ /d "native" /f >/dev/null 2>&1; then
                        print_success "DLL overrides configured in Wine registry (alternative method)"
                    else
                        print_warning "Could not apply DLL overrides (OpenCL may not work)"
                    fi
                fi
            else
                if WINEPREFIX="$prefix" wine regedit "$reg_file" >/dev/null 2>&1; then
                    print_success "DLL overrides configured in Wine registry"
                else
                    # Try alternative method
                    if WINEPREFIX="$prefix" wine reg add "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "d3d12" /t REG_SZ /d "native" /f >/dev/null 2>&1 && \
                       WINEPREFIX="$prefix" wine reg add "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "d3d12core" /t REG_SZ /d "native" /f >/dev/null 2>&1; then
                        print_success "DLL overrides configured in Wine registry (alternative method)"
                    else
                        print_warning "Could not apply DLL overrides (OpenCL may not work)"
                    fi
                fi
            fi
            
            rm -f "$reg_file"
        fi
    fi
    
    # Configure OpenCL support in Affinity application (if already installed)
    print_step "Configuring OpenCL support in Affinity application..."
    local affinity_dir="$prefix/drive_c/Program Files/Affinity/Affinity"
    
    if [ -d "$affinity_dir" ] && [ -d "$wine_lib_dir" ]; then
        # Check if DLLs are already copied
        local dlls_already_present=false
        if [ -f "$affinity_dir/d3d12.dll" ] && [ -f "$affinity_dir/d3d12core.dll" ]; then
            dlls_already_present=true
        fi
        
        if [ "$dlls_already_present" = true ]; then
            print_success "OpenCL DLLs already present in Affinity directory"
        else
            print_info "Copying vkd3d-proton DLLs to Affinity application directory..."
            local dll_copied=0
            
            if [ -f "$wine_lib_dir/d3d12.dll" ] && [ ! -f "$affinity_dir/d3d12.dll" ]; then
                if cp "$wine_lib_dir/d3d12.dll" "$affinity_dir/" 2>/dev/null; then
                    print_progress "Copied d3d12.dll to Affinity directory"
                    ((dll_copied++))
                fi
            fi
            
            if [ -f "$wine_lib_dir/d3d12core.dll" ] && [ ! -f "$affinity_dir/d3d12core.dll" ]; then
                if cp "$wine_lib_dir/d3d12core.dll" "$affinity_dir/" 2>/dev/null; then
                    print_progress "Copied d3d12core.dll to Affinity directory"
                    ((dll_copied++))
                fi
            fi
            
            if [ $dll_copied -gt 0 ]; then
                print_success "Copied $dll_copied OpenCL DLL file(s) to Affinity directory"
                print_success "OpenCL support fully configured!"
            fi
        fi
    else
        if [ ! -d "$affinity_dir" ]; then
            print_info "Affinity installation directory not found. OpenCL DLLs will be copied after Affinity is installed."
        fi
        if [ -d "$wine_lib_dir" ]; then
            print_success "OpenCL support is ready (DLLs will be copied to Affinity after installation)"
        fi
    fi
    
    print_success "vkd3d-proton setup completed"
    return 0
}

copy_helper_files() {
    print_header "Copying Helper Files to Wine Prefix"
    
    local winmd_source="/tmp/Windows.winmd"
    local dll_source="/tmp/wintypes.dll"
    
    if [ ! -f "$winmd_source" ]; then
        print_error "Windows.winmd not found at $winmd_source"
        return 1
    fi
    
    if [ ! -f "$dll_source" ]; then
        print_error "wintypes.dll not found at $dll_source"
        return 1
    fi
    
    local prefix=$(get_wine_prefix)
    
    # Only export WINEPREFIX if it was set in environment
    if [ -n "$WINEPREFIX" ]; then
        export WINEPREFIX
    fi
    
    # Create winmetadata directory
    local winmetadata_dir="$prefix/drive_c/windows/system32/winmetadata"
    local winmd_dest="$winmetadata_dir/Windows.winmd"
    
    # Check if Windows.winmd is already in place
    if [ -f "$winmd_dest" ]; then
        print_success "Windows.winmd already in place, skipping..."
    else
        print_step "Creating winmetadata directory..."
        mkdir -p "$winmetadata_dir" || {
            print_error "Failed to create winmetadata directory"
            return 1
        }
        
        # Copy Windows.winmd
        print_step "Copying Windows.winmd..."
        cp "$winmd_source" "$winmd_dest" || {
            print_error "Failed to copy Windows.winmd"
            return 1
        }
        print_success "Windows.winmd copied"
    fi
    
    # Find Affinity installation directory
    local affinity_dir="$prefix/drive_c/Program Files/Affinity"
    local files_copied=false
    
    # Check for Affinity 3.x (unified)
    if [ -d "$affinity_dir/Affinity" ]; then
        local dll_dest="$affinity_dir/Affinity/wintypes.dll"
        if [ -f "$dll_dest" ]; then
            print_success "wintypes.dll already in Affinity 3.x, skipping..."
        else
            print_step "Copying wintypes.dll to Affinity 3.x..."
            cp "$dll_source" "$dll_dest" || {
                print_error "Failed to copy wintypes.dll"
                return 1
            }
            print_success "wintypes.dll copied to Affinity 3.x"
            files_copied=true
        fi
    fi
    
    # Check for Affinity 2.x (separate apps - guide uses "Photo 2", "Designer 2", "Publisher 2")
    for app in "Photo 2" "Designer 2" "Publisher 2"; do
        local app_dir="$affinity_dir/$app"
        if [ -d "$app_dir" ]; then
            local dll_dest="$app_dir/wintypes.dll"
            if [ -f "$dll_dest" ]; then
                print_success "wintypes.dll already in $app, skipping..."
            else
                print_step "Copying wintypes.dll to $app..."
                cp "$dll_source" "$dll_dest" || {
                    print_warning "Failed to copy wintypes.dll to $app"
                }
                print_success "wintypes.dll copied to $app"
                files_copied=true
            fi
        fi
    done
    
    if [ "$files_copied" = false ] && [ ! -d "$affinity_dir/Affinity" ] && [ ! -d "$affinity_dir/Photo 2" ]; then
        print_warning "No Affinity installation found. Files will be copied when you install Affinity."
    fi
    
    print_success "Helper files check and copy completed"
    return 0
}

enable_dotnet35_registry() {
    local prefix=$1
    
    # Check if .NET 3.5 registry keys are already set
    local net35_enabled=false
    if [ -n "$WINEPREFIX" ]; then
        export WINEPREFIX
        if wine reg query "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\NET Framework Setup\\NDP\\v3.5" /v Install 2>/dev/null | grep -q "0x1"; then
            net35_enabled=true
        elif wine reg query "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\NET Framework Setup\\NDP\\v2.0.50727" /v Install 2>/dev/null | grep -q "0x1"; then
            net35_enabled=true
        fi
    else
        if WINEPREFIX="$prefix" wine reg query "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\NET Framework Setup\\NDP\\v3.5" /v Install 2>/dev/null | grep -q "0x1"; then
            net35_enabled=true
        elif WINEPREFIX="$prefix" wine reg query "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\NET Framework Setup\\NDP\\v2.0.50727" /v Install 2>/dev/null | grep -q "0x1"; then
            net35_enabled=true
        fi
    fi
    
    if [ "$net35_enabled" = true ]; then
        print_success ".NET Framework 3.5 is already enabled in registry"
        return 0
    fi
    
    # Enable .NET 3.5 via registry (equivalent to "Turn Windows features on or off")
    local work_dir="/tmp"
    local reg_file="$work_dir/dotnet35_enable.reg"
    
    # Create registry file to enable .NET 3.5
    {
        echo "REGEDIT4"
        echo ""
        echo "[HKEY_LOCAL_MACHINE\\Software\\Microsoft\\NET Framework Setup\\NDP\\v2.0.50727]"
        echo "\"Install\"=dword:00000001"
        echo "\"Version\"=\"2.0.50727.4927\""
        echo "\"SP\"=dword:00000002"
        echo ""
        echo "[HKEY_LOCAL_MACHINE\\Software\\Microsoft\\NET Framework Setup\\NDP\\v3.5]"
        echo "\"Install\"=dword:00000001"
        echo "\"Version\"=\"3.5.30729.4926\""
        echo "\"SP\"=dword:00000001"
        echo ""
        echo "[HKEY_LOCAL_MACHINE\\Software\\Microsoft\\NET Framework Setup\\NDP\\v3.5\\1033]"
        echo "\"Version\"=\"3.5.30729.4926\""
        echo "\"SP\"=dword:00000001"
    } > "$reg_file"
    
    # Apply the registry file
    if [ -n "$WINEPREFIX" ]; then
        export WINEPREFIX
        if wine regedit "$reg_file" >/dev/null 2>&1; then
            print_success ".NET Framework 3.5 enabled via registry (Windows features equivalent)"
            rm -f "$reg_file"
            return 0
        else
            print_warning "Failed to enable .NET 3.5 via regedit, trying alternative method..."
            rm -f "$reg_file"
            # Try using wine reg add as alternative
            if wine reg add "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\NET Framework Setup\\NDP\\v2.0.50727" /v Install /t REG_DWORD /d 1 /f >/dev/null 2>&1 && \
               wine reg add "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\NET Framework Setup\\NDP\\v3.5" /v Install /t REG_DWORD /d 1 /f >/dev/null 2>&1; then
                print_success ".NET Framework 3.5 enabled using alternative method"
                return 0
            else
                print_warning "Could not enable .NET 3.5 via registry (may still work)"
                return 1
            fi
        fi
    else
        if WINEPREFIX="$prefix" wine regedit "$reg_file" >/dev/null 2>&1; then
            print_success ".NET Framework 3.5 enabled via registry (Windows features equivalent)"
            rm -f "$reg_file"
            return 0
        else
            print_warning "Failed to enable .NET 3.5 via regedit, trying alternative method..."
            rm -f "$reg_file"
            # Try using wine reg add as alternative
            if WINEPREFIX="$prefix" wine reg add "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\NET Framework Setup\\NDP\\v2.0.50727" /v Install /t REG_DWORD /d 1 /f >/dev/null 2>&1 && \
               WINEPREFIX="$prefix" wine reg add "HKEY_LOCAL_MACHINE\\Software\\Microsoft\\NET Framework Setup\\NDP\\v3.5" /v Install /t REG_DWORD /d 1 /f >/dev/null 2>&1; then
                print_success ".NET Framework 3.5 enabled using alternative method"
                return 0
            else
                print_warning "Could not enable .NET 3.5 via registry (may still work)"
                return 1
            fi
        fi
    fi
}

configure_wintypes_dll() {
    print_header "Configuring wintypes DLL Override"
    
    print_step "Automatically configuring wintypes DLL override..."
    
    local prefix=$(get_wine_prefix)
    local work_dir="/tmp"
    local reg_file="$work_dir/wintypes_override.reg"
    
    # Check if wintypes override is already configured
    local override_exists=false
    if [ -n "$WINEPREFIX" ]; then
        export WINEPREFIX
        if wine reg query "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "wintypes" 2>/dev/null | grep -q "native"; then
            override_exists=true
        fi
    else
        if WINEPREFIX="$prefix" wine reg query "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "wintypes" 2>/dev/null | grep -q "native"; then
            override_exists=true
        fi
    fi
    
    if [ "$override_exists" = true ]; then
        print_success "wintypes DLL override is already configured"
        return 0
    fi
    
    # Create registry file for wintypes override
    {
        echo "REGEDIT4"
        echo "[HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides]"
        echo "\"wintypes\"=\"native\""
    } > "$reg_file"
    
    # Apply the registry file
    if [ -n "$WINEPREFIX" ]; then
        export WINEPREFIX
        if wine regedit "$reg_file" >/dev/null 2>&1; then
            print_success "wintypes DLL override configured automatically"
            rm -f "$reg_file"
            return 0
        else
            print_warning "Failed to configure wintypes DLL override via regedit, trying alternative method..."
            rm -f "$reg_file"
            # Try using wine reg add as alternative
            if wine reg add "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "wintypes" /t REG_SZ /d "native" /f >/dev/null 2>&1; then
                print_success "wintypes DLL override configured using alternative method"
                return 0
            else
                print_error "Failed to configure wintypes DLL override automatically"
                return 1
            fi
        fi
    else
        if WINEPREFIX="$prefix" wine regedit "$reg_file" >/dev/null 2>&1; then
            print_success "wintypes DLL override configured automatically"
            rm -f "$reg_file"
            return 0
        else
            print_warning "Failed to configure wintypes DLL override via regedit, trying alternative method..."
            rm -f "$reg_file"
            # Try using wine reg add as alternative
            if WINEPREFIX="$prefix" wine reg add "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "wintypes" /t REG_SZ /d "native" /f >/dev/null 2>&1; then
                print_success "wintypes DLL override configured using alternative method"
                return 0
            else
                print_error "Failed to configure wintypes DLL override automatically"
                return 1
            fi
        fi
    fi
}

launch_affinity() {
    print_header "Launching Affinity"
    
    local prefix=$(get_wine_prefix)
    
    # Only export WINEPREFIX if it was set in environment
    if [ -n "$WINEPREFIX" ]; then
        export WINEPREFIX
    fi
    
    # Check for Affinity 3.x (unified)
    local affinity_exe="$prefix/drive_c/Program Files/Affinity/Affinity/Affinity.exe"
    if [ -f "$affinity_exe" ]; then
        print_step "Launching Affinity 3.x..."
        if [ -n "$WINEPREFIX" ]; then
            wine "$affinity_exe" &
        else
            WINEPREFIX="$prefix" wine "$affinity_exe" &
        fi
        print_success "Affinity 3.x launched"
        return 0
    fi
    
    # Check for Affinity 2.x apps
    local apps=("Photo" "Designer" "Publisher")
    local found=false
    
    for app in "${apps[@]}"; do
        local app_exe="$prefix/drive_c/Program Files/Affinity/Affinity $app 2/Affinity $app 2.exe"
        if [ -f "$app_exe" ]; then
            print_step "Found Affinity $app 2"
            found=true
        fi
    done
    
    if [ "$found" = true ]; then
        print_info "Multiple Affinity apps found. Please launch them manually:"
        for app in "${apps[@]}"; do
            local app_exe="$prefix/drive_c/Program Files/Affinity/Affinity $app 2/Affinity $app 2.exe"
            if [ -f "$app_exe" ]; then
                if [ -n "$WINEPREFIX" ]; then
                    echo "  WINEPREFIX=\"$WINEPREFIX\" wine \"$app_exe\""
                else
                    echo "  wine \"$app_exe\""
                fi
            fi
        done
    else
        print_warning "No Affinity installation found"
        print_info "If you installed Affinity, you can launch it with:"
        if [ -n "$WINEPREFIX" ]; then
            echo "  WINEPREFIX=\"$WINEPREFIX\" wine \"$prefix/drive_c/Program Files/Affinity/[App]/[App].exe\""
        else
            echo "  wine \"$prefix/drive_c/Program Files/Affinity/[App]/[App].exe\""
        fi
    fi
    
    return 0
}

# ==========================================
# Main Script
# ==========================================

show_introduction() {
    clear
    print_header "Affinity Wine 10.17+ Installation Script"
    echo ""
    echo -e "${BOLD}${CYAN}Welcome to the Affinity Wine 10.17+ Installation Script${NC}"
    echo ""
    echo -e "${YELLOW}This script will help you install Affinity applications on Linux using Wine 10.17+${NC}"
    echo -e "${YELLOW}with Windows Runtime (WinRT) support and OpenCL hardware acceleration.${NC}"
    echo ""
    echo -e "${BOLD}What this script does:${NC}"
    echo ""
    echo -e "  ${GREEN}✓${NC} Installs Wine 10.17+ and Winetricks (if not already installed)"
    echo -e "  ${GREEN}✓${NC} Creates and configures a Wine prefix"
    echo -e "  ${GREEN}✓${NC} Installs required Windows runtime dependencies (.NET, VC++, fonts, etc.)"
    echo -e "  ${GREEN}✓${NC} Downloads and installs WinRT helper files (Windows.winmd, wintypes.dll)"
    echo -e "  ${GREEN}✓${NC} Sets up OpenCL support via vkd3d-proton for GPU acceleration"
    echo -e "  ${GREEN}✓${NC} Configures Wine for optimal Affinity application compatibility"
    echo ""
    echo -e "${BOLD}Requirements:${NC}"
    echo ""
    echo -e "  • Wine 10.17+ (will be installed if needed)"
    echo -e "  • Winetricks (will be installed if needed)"
    echo -e "  • About 10 GB of free disk space"
    echo -e "  • Internet connection"
    echo ""
    echo -e "${BOLD}Wine Prefix:${NC}"
    if [ -n "$WINEPREFIX" ]; then
        echo -e "  ${CYAN}Using: $WINEPREFIX${NC}"
    else
        local default_prefix=$(get_wine_prefix)
        echo -e "  ${CYAN}Using: $default_prefix${NC}"
        echo -e "  ${YELLOW}Note: You can set WINEPREFIX environment variable to use a custom location${NC}"
        echo -e "  ${YELLOW}Example: WINEPREFIX=\"\$HOME/.affinity\" $0${NC}"
    fi
    echo ""
    echo -e "${RED}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "${YELLOW}${BOLD}Note:${NC} This script follows the Wine 10.17+ guide for installing Affinity apps"
    echo -e "${YELLOW}with Windows Runtime (WinRT) support. For more information, visit:${NC}"
    echo -e "${CYAN}https://raw.githubusercontent.com/seapear/AffinityOnLinux/refs/heads/main/Guides/Wine/Guide.md${NC}"
    echo ""
    echo -e "${RED}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    read -p "Do you want to continue? (y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Installation cancelled by user."
        exit 0
    fi
    echo ""
}

show_affinity_menu() {
    clear
    print_header "Affinity Installation Menu"
    echo ""
    echo -e "${BOLD}Which Affinity product would you like to install?${NC}"
    echo ""
    echo -e "  ${GREEN}1.${NC} ${BOLD}Affinity${NC} (Unified Application v3)"
    echo -e "      ${CYAN}The new unified Affinity application that combines Photo, Designer,"
    echo -e "      Publisher, and more into a single modern interface.${NC}"
    echo ""
    echo -e "  ${GREEN}2.${NC} ${BOLD}Affinity Photo${NC} (v2)"
    echo -e "      ${CYAN}Professional photo editing and image manipulation software with"
    echo -e "      advanced tools for photographers and digital artists.${NC}"
    echo ""
    echo -e "  ${GREEN}3.${NC} ${BOLD}Affinity Designer${NC} (v2)"
    echo -e "      ${CYAN}Vector graphic design software for creating illustrations, logos,"
    echo -e "      UI designs, print projects, and mock-ups.${NC}"
    echo ""
    echo -e "  ${GREEN}4.${NC} ${BOLD}Affinity Publisher${NC} (v2)"
    echo -e "      ${CYAN}Desktop publishing application for creating professional layouts,"
    echo -e "      magazines, books, and print materials.${NC}"
    echo ""
    echo -e "  ${GREEN}5.${NC} ${BOLD}Exit${NC}"
    echo ""
    echo -n -e "${BOLD}Please select an option (1-5): ${NC}"
}

install_affinity_product() {
    local product=$1
    # Use cache directory like Python script for Affinity v3, Downloads for v2
    local cache_dir="$HOME/.cache/affinity-installer"
    local downloads_dir="$HOME/Downloads"
    local installer_file=""
    local download_url=""
    
    case $product in
        "Affinity"|"Add")
            print_header "Installing Affinity (Unified Application v3)"
            download_url="https://downloads.affinity.studio/Affinity%20x64.exe"
            # Use cache directory for v3 like Python script
            mkdir -p "$cache_dir"
            installer_file="$cache_dir/Affinity-x64.exe"
            ;;
        "Photo")
            print_header "Installing Affinity Photo v2"
            download_url="https://downloads.affinity.studio/Affinity%20Photo%20x64.exe"
            installer_file="$downloads_dir/Affinity-Photo-x64.exe"
            ;;
        "Designer")
            print_header "Installing Affinity Designer v2"
            download_url="https://downloads.affinity.studio/Affinity%20Designer%20x64.exe"
            installer_file="$downloads_dir/Affinity-Designer-x64.exe"
            ;;
        "Publisher")
            print_header "Installing Affinity Publisher v2"
            download_url="https://downloads.affinity.studio/Affinity%20Publisher%20x64.exe"
            installer_file="$downloads_dir/Affinity-Publisher-x64.exe"
            ;;
        *)
            print_error "Unknown product: $product"
            return 1
            ;;
    esac
    
    # For Affinity v3, always download the latest version (remove old installer if it exists)
    if [ "$product" = "Affinity" ] || [ "$product" = "Add" ]; then
        if [ -f "$installer_file" ]; then
            print_info "Removing old installer to ensure we get the latest version..."
            rm -f "$installer_file"
        fi
        
        print_step "Downloading latest Affinity v3 installer..."
        print_warning "This is a large download (~500MB), please be patient..."
        print_info "Downloading from: $download_url"
        print_info "Saving to: $installer_file"
        
        if download_file "$download_url" "$installer_file" "Affinity v3 installer"; then
            print_success "Affinity v3 installer downloaded successfully (latest version)"
        else
            print_error "Failed to download Affinity v3 installer"
            print_info "You can download it manually from: https://downloads.affinity.studio/Affinity%20x64.exe"
            return 1
        fi
    else
        # For v2 apps, check if file exists first, then download if needed
        if [ -f "$installer_file" ]; then
            print_info "Installer found at: $installer_file"
            read -p "Use existing installer or download latest? (u/d): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Dd]$ ]]; then
                print_info "Removing old installer to ensure we get the latest version..."
                rm -f "$installer_file"
            fi
        fi
        
        if [ ! -f "$installer_file" ]; then
            print_step "Downloading latest $product installer..."
            print_warning "This is a large download (~500MB), please be patient..."
            mkdir -p "$downloads_dir"
            
            if download_file "$download_url" "$installer_file" "$product installer"; then
                print_success "$product installer downloaded successfully (latest version)"
            else
                print_error "Failed to download $product installer"
                print_info "You can download it manually from: https://www.affinity.studio/get-affinity"
                read -p "Enter the full path to your $product installer (.exe file): " installer_file
                
                if [ ! -f "$installer_file" ]; then
                    print_error "File not found: $installer_file"
                    return 1
                fi
            fi
        fi
    fi
    
    print_step "Found installer: $installer_file"
    
    # Verify installer file exists and is executable
    if [ ! -f "$installer_file" ]; then
        print_error "Installer file not found: $installer_file"
        return 1
    fi
    
    if [ ! -r "$installer_file" ]; then
        print_error "Installer file is not readable: $installer_file"
        return 1
    fi
    
    print_info "Installer file verified: $installer_file"
    print_info "File size: $(du -h "$installer_file" | cut -f1)"
    
    # For Affinity v3, fix UI Automation issue
    if [ "$product" = "Affinity" ] || [ "$product" = "Add" ]; then
        print_step "Configuring UI Automation support for Affinity v3 installer..."
        local prefix=$(get_wine_prefix)
        
        # Check if DLL exists
        local uia_dll_found=false
        if [ -f "$prefix/drive_c/windows/system32/uiautomationcore.dll" ]; then
            uia_dll_found=true
        elif [ -f "$prefix/drive_c/windows/syswow64/uiautomationcore.dll" ]; then
            uia_dll_found=true
        fi
        
        if [ "$uia_dll_found" = false ]; then
            print_warning "UI Automation Core DLL not found - attempting to fix..."
            
            # Try installing .NET Desktop Runtime 8 which may include UI Automation
            print_info "Trying .NET Desktop Runtime 8 (may include UI Automation support)..."
            if [ -n "$WINEPREFIX" ]; then
                export WINEPREFIX
                "$winetricks_cmd" --unattended --force dotnetdesktop8 >/dev/null 2>&1 || true
            else
                WINEPREFIX="$prefix" "$winetricks_cmd" --unattended --force dotnetdesktop8 >/dev/null 2>&1 || true
            fi
            sleep 2
            
            # Check again
            if [ -f "$prefix/drive_c/windows/system32/uiautomationcore.dll" ] || \
               [ -f "$prefix/drive_c/windows/syswow64/uiautomationcore.dll" ]; then
                print_success "UI Automation Core DLL found after installing .NET Desktop Runtime 8"
                uia_dll_found=true
            fi
        fi
        
        # Set DLL override to use Wine's built-in implementation (even if incomplete)
        print_info "Configuring DLL override for uiautomationcore..."
        local work_dir="/tmp"
        local reg_file="$work_dir/uiautomationcore_override.reg"
        {
            echo "REGEDIT4"
            echo "[HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides]"
            echo "\"uiautomationcore\"=\"builtin\""
        } > "$reg_file"
        
        if [ -n "$WINEPREFIX" ]; then
            export WINEPREFIX
            wine regedit "$reg_file" >/dev/null 2>&1 || \
            wine reg add "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "uiautomationcore" /t REG_SZ /d "builtin" /f >/dev/null 2>&1 || true
        else
            WINEPREFIX="$prefix" wine regedit "$reg_file" >/dev/null 2>&1 || \
            WINEPREFIX="$prefix" wine reg add "HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides" /v "uiautomationcore" /t REG_SZ /d "builtin" /f >/dev/null 2>&1 || true
        fi
        rm -f "$reg_file"
        
        if [ "$uia_dll_found" = true ]; then
            print_success "UI Automation Core configured"
        else
            print_warning "UI Automation Core DLL still not found"
            print_info "Wine's built-in implementation will be used (may show errors but installer should work)"
            print_info "If installer fails, you can manually copy uiautomationcore.dll from Windows to:"
            print_info "  $prefix/drive_c/windows/system32/"
        fi
    fi
    
    print_info "Launching $product installer..."
    print_info "Installer path: $installer_file"
    print_info "Wine prefix: $prefix"
    print_warning "Follow the installation prompts in the installer window"
    if [ "$product" != "Affinity" ] && [ "$product" != "Add" ]; then
        print_info "Note: For Affinity v2 apps, you may need to run the installer 3 times for each app"
    fi
    
    # For Affinity v3, set environment variables to help with UI Automation errors
    local wine_env=""
    if [ "$product" = "Affinity" ] || [ "$product" = "Add" ]; then
        # Suppress some Wine errors that might be related to UI Automation
        export WINEDEBUG=-all
        wine_env="WINEDEBUG=-all"
    fi
    
    # Launch the installer and wait for it to complete
    # Try wine start /wait /unix first (like Python script), then fallback to wine
    print_step "Executing installer with Wine..."
    local installer_exit_code=0
    local installer_launched=false
    
    # Set up environment variables
    if [ -n "$WINEPREFIX" ]; then
        export WINEPREFIX
        print_info "Using WINEPREFIX from environment: $WINEPREFIX"
    else
        export WINEPREFIX="$prefix"
        print_info "Using WINEPREFIX: $prefix"
    fi
    
    # Try wine start /wait /unix first (more reliable for installers)
    print_info "Attempt 1: Trying 'wine start /wait /unix'..."
    if [ -n "$wine_env" ]; then
        # Parse wine_env (e.g., "WINEDEBUG=-all") and export it
        if [[ "$wine_env" =~ ^([^=]+)=(.*)$ ]]; then
            export "${BASH_REMATCH[1]}=${BASH_REMATCH[2]}"
        fi
    fi
    
    if wine start /wait /unix "$installer_file" 2>&1; then
        installer_exit_code=$?
        installer_launched=true
        print_info "Installer launched successfully with 'wine start /wait /unix'"
    else
        installer_exit_code=$?
        print_warning "First attempt returned exit code $installer_exit_code, trying fallback method..."
        installer_launched=false
    fi
    
    # Fallback to direct wine command if first attempt failed or exited too quickly
    if [ "$installer_launched" = false ] || [ $installer_exit_code -ne 0 ]; then
        print_info "Attempt 2: Trying 'wine' directly..."
        if wine "$installer_file" 2>&1; then
            installer_exit_code=$?
            installer_launched=true
            print_info "Installer launched successfully with 'wine'"
        else
            installer_exit_code=$?
            print_warning "Second attempt returned exit code $installer_exit_code"
            # Don't fail here - some installers return non-zero even on success
        fi
    fi
    
    # Wait for all Wine processes to finish (like Python script)
    print_info "Waiting for Wine processes to finish (wineserver -w)..."
    wineserver -w 2>/dev/null || true
    
    print_info "Installer process completed with exit code: $installer_exit_code"
    
    # Restore WINEDEBUG if we changed it
    if [ "$product" = "Affinity" ] || [ "$product" = "Add" ]; then
        unset WINEDEBUG
    fi
    
    # Wait a moment for installer to fully complete and files to be written
    print_info "Waiting for installation to complete..."
    sleep 3
    
    # Check if installation was successful
    if [ $installer_exit_code -ne 0 ]; then
        print_warning "Installer exited with code $installer_exit_code"
        print_info "This may be normal - some installers return non-zero codes even on success"
    fi
    
    # Finalize OpenCL configuration after installation
    print_step "Finalizing OpenCL configuration for $product..."
    local affinity_dir=""
    case $product in
        "Affinity"|"Add")
            affinity_dir="$prefix/drive_c/Program Files/Affinity/Affinity"
            ;;
        "Photo")
            affinity_dir="$prefix/drive_c/Program Files/Affinity/Photo 2"
            ;;
        "Designer")
            affinity_dir="$prefix/drive_c/Program Files/Affinity/Designer 2"
            ;;
        "Publisher")
            affinity_dir="$prefix/drive_c/Program Files/Affinity/Publisher 2"
            ;;
    esac
    
    if [ -d "$affinity_dir" ]; then
        local wine_lib_dir_64="$prefix/lib64/wine/vkd3d-proton/x86_64-windows"
        local wine_lib_dir_32="$prefix/lib/wine/vkd3d-proton/x86_64-windows"
        local wine_lib_dir=""
        
        if [ -d "$prefix/lib64" ]; then
            wine_lib_dir="$wine_lib_dir_64"
        elif [ -d "$prefix/lib" ]; then
            wine_lib_dir="$wine_lib_dir_32"
        else
            wine_lib_dir="$wine_lib_dir_64"
        fi
        
        if [ -d "$wine_lib_dir" ]; then
            local dll_copied=0
            if [ -f "$wine_lib_dir/d3d12.dll" ] && [ ! -f "$affinity_dir/d3d12.dll" ]; then
                if cp "$wine_lib_dir/d3d12.dll" "$affinity_dir/" 2>/dev/null; then
                    print_progress "Copied d3d12.dll to $product directory"
                    ((dll_copied++))
                fi
            fi
            if [ -f "$wine_lib_dir/d3d12core.dll" ] && [ ! -f "$affinity_dir/d3d12core.dll" ]; then
                if cp "$wine_lib_dir/d3d12core.dll" "$affinity_dir/" 2>/dev/null; then
                    print_progress "Copied d3d12core.dll to $product directory"
                    ((dll_copied++))
                fi
            fi
            if [ $dll_copied -gt 0 ]; then
                print_success "OpenCL DLLs copied to $product directory - OpenCL support is now active!"
            elif [ -f "$affinity_dir/d3d12.dll" ] && [ -f "$affinity_dir/d3d12core.dll" ]; then
                print_success "OpenCL DLLs already present in $product directory"
            else
                print_warning "OpenCL DLLs not found in Wine library directory"
            fi
        else
            print_warning "vkd3d-proton library directory not found. Please run setup again to install OpenCL support."
        fi
    else
        print_warning "$product installation directory not found. OpenCL configuration skipped."
        print_info "If you just finished installing, the directory may not be created yet."
        print_info "You can run the OpenCL configuration manually later, or re-run this script."
    fi
    
    # Verify installation actually completed
    case $product in
        "Affinity"|"Add")
            local check_exe="$prefix/drive_c/Program Files/Affinity/Affinity/Affinity.exe"
            ;;
        "Photo")
            local check_exe="$prefix/drive_c/Program Files/Affinity/Photo 2/Photo 2.exe"
            ;;
        "Designer")
            local check_exe="$prefix/drive_c/Program Files/Affinity/Designer 2/Designer 2.exe"
            ;;
        "Publisher")
            local check_exe="$prefix/drive_c/Program Files/Affinity/Publisher 2/Publisher 2.exe"
            ;;
    esac
    
    if [ -f "$check_exe" ]; then
        print_success "$product installation completed successfully!"
        
        # Offer to install AffinityPluginLoader + WineFix (optional enhancement)
        if [ "$product" = "Affinity" ] || [ "$product" = "Add" ]; then
            echo ""
            print_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            print_info "Optional Enhancement: AffinityPluginLoader + WineFix"
            print_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo ""
            print_info "${BOLD}What is AffinityPluginLoader + WineFix?${NC}"
            echo ""
            print_info "This is a community-made patch (by Noah C3) that provides runtime fixes for"
            print_info "Affinity when running on Linux under Wine. It uses Harmony library for"
            print_info "dynamic code patching without modifying DLL files on disk."
            echo ""
            print_info "${BOLD}What does it fix?${NC}"
            echo ""
            print_success "  ✓ Preferences and settings will now save correctly on Linux"
            print_info "  • Plugin loading support enabled (for custom plugins)"
            print_info "  • Dynamic patch injection at runtime (no DLL modifications needed)"
            echo ""
            print_warning "${BOLD}Important Notes:${NC}"
            echo ""
            print_warning "  • This is a community patch, NOT official from Canva/Serif"
            print_warning "  • Currently disables the Canva sign-in dialog (temporary fix)"
            print_warning "  • If you update Affinity, you may need to reinstall this patch"
            print_warning "  • Updates to Affinity may overwrite the launcher files"
            echo ""
            print_info "For more information, visit:"
            print_info "  https://github.com/noahc3/AffinityPluginLoader"
            echo ""
            read -p "Would you like to install AffinityPluginLoader + WineFix? (y/n): " -n 1 -r
            echo ""
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                install_affinity_plugin_loader "$product"
            else
                print_info "Skipping AffinityPluginLoader installation"
                print_info "You can install it later if needed"
            fi
        fi
    else
        print_warning "$product installation may not have completed successfully."
        print_info "The executable was not found at: $check_exe"
        print_info "Please verify the installation completed in the installer window."
    fi
    
    return 0
}

install_affinity_plugin_loader() {
    local product=$1
    print_header "Installing AffinityPluginLoader + WineFix"
    
    local prefix=$(get_wine_prefix)
    local affinity_dir=""
    
    case $product in
        "Affinity"|"Add")
            affinity_dir="$prefix/drive_c/Program Files/Affinity/Affinity"
            ;;
        "Photo")
            affinity_dir="$prefix/drive_c/Program Files/Affinity/Photo 2"
            ;;
        "Designer")
            affinity_dir="$prefix/drive_c/Program Files/Affinity/Designer 2"
            ;;
        "Publisher")
            affinity_dir="$prefix/drive_c/Program Files/Affinity/Publisher 2"
            ;;
        *)
            print_error "Unknown product: $product"
            return 1
            ;;
    esac
    
    if [ ! -d "$affinity_dir" ]; then
        print_error "Affinity installation directory not found: $affinity_dir"
        return 1
    fi
    
    # Check if already installed
    if [ -f "$affinity_dir/AffinityHook.exe" ] && [ -f "$affinity_dir/Affinity.real.exe" ]; then
        print_success "AffinityPluginLoader + WineFix appears to be already installed"
        return 0
    fi
    
    local tmp_dir="/tmp"
    local bundle_url="https://github.com/noahc3/AffinityPluginLoader/releases/latest/download/affinitypluginloader-plus-winefix.tar.xz"
    local bundle_file="$tmp_dir/affinitypluginloader-plus-winefix.tar.xz"
    
    print_step "Downloading AffinityPluginLoader + WineFix bundle..."
    if download_file "$bundle_url" "$bundle_file" "AffinityPluginLoader + WineFix"; then
        print_success "Bundle downloaded successfully"
    else
        print_error "Failed to download AffinityPluginLoader + WineFix bundle"
        print_info "You can download it manually from:"
        print_info "  https://github.com/noahc3/AffinityPluginLoader/releases/latest"
        return 1
    fi
    
    print_step "Extracting bundle to Affinity directory..."
    cd "$affinity_dir" || {
        print_error "Failed to change to Affinity directory"
        return 1
    }
    
    if tar -xf "$bundle_file" 2>/dev/null; then
        print_success "Bundle extracted successfully"
    else
        print_error "Failed to extract bundle"
        rm -f "$bundle_file"
        return 1
    fi
    
    # Replace launcher for compatibility
    if [ -f "$affinity_dir/Affinity.exe" ] && [ -f "$affinity_dir/AffinityHook.exe" ]; then
        print_step "Replacing launcher for compatibility..."
        if [ ! -f "$affinity_dir/Affinity.real.exe" ]; then
            mv "$affinity_dir/Affinity.exe" "$affinity_dir/Affinity.real.exe" || {
                print_error "Failed to rename Affinity.exe"
                return 1
            }
        fi
        mv "$affinity_dir/AffinityHook.exe" "$affinity_dir/Affinity.exe" || {
            print_error "Failed to rename AffinityHook.exe"
            return 1
        }
        print_success "Launcher replaced - AffinityPluginLoader will load automatically"
    else
        print_warning "Expected files not found after extraction"
    fi
    
    # Clean up
    rm -f "$bundle_file"
    
    print_success "AffinityPluginLoader + WineFix installed successfully!"
    echo ""
    print_info "${BOLD}What's been fixed:${NC}"
    print_success "  ✓ Preferences and settings will now save correctly on Linux"
    print_info "  • Plugin loading support is now enabled"
    print_info "  • Canva sign-in dialog is temporarily disabled (until browser redirect is fixed)"
    echo ""
    print_warning "${BOLD}Important:${NC}"
    print_warning "  • If you update Affinity, you may need to reinstall this patch"
    print_warning "  • Updates may overwrite the launcher files"
    print_warning "  • Always download from official releases:"
    print_info "    https://github.com/noahc3/AffinityPluginLoader/releases"
    echo ""
    print_info "You can now launch Affinity normally - the patch will load automatically!"
    
    return 0
}

main() {
    # Show introduction and ask for confirmation
    show_introduction
    
    # Use WINEPREFIX from environment, or default (~/.wine) if not set
    if [ -n "$WINEPREFIX" ]; then
        export WINEPREFIX
        print_info "Wine prefix: $WINEPREFIX"
    else
        print_info "Wine prefix: ~/.wine (default)"
    fi
    echo ""
    
    # Setup phase: Prepare Wine environment
    print_header "Setup Phase"
    print_info "Preparing Wine environment for Affinity applications..."
    echo ""
    
    # Check if Wine 10.17+ is installed
    if ! check_wine_version; then
        print_warning "Wine 10.17+ is required but not found"
        read -p "Would you like to install Wine 10.17+ and Winetricks now? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            if ! install_wine_and_winetricks; then
                print_error "Failed to install Wine and Winetricks"
                exit 1
            fi
        else
            print_error "Wine 10.17+ is required. Exiting."
            exit 1
        fi
    else
        print_success "Wine 10.17+ is installed: $(wine --version)"
    fi
    
    # Step 1: Create Wine prefix
    if ! create_wine_prefix; then
        print_error "Failed to create Wine prefix"
        exit 1
    fi
    
    # Step 2: Install runtime dependencies
    if ! install_runtime_dependencies; then
        print_error "Failed to install runtime dependencies"
        exit 1
    fi
    
    # Step 3: Download helper files
    if ! download_helper_files; then
        print_error "Failed to download helper files"
        exit 1
    fi
    
    # Step 4: Install OpenCL support (vkd3d-proton)
    print_info "Installing OpenCL support..."
    if ! install_opencl_support; then
        print_error "Failed to install OpenCL support"
        print_warning "OpenCL is required for hardware acceleration. Installation may continue, but OpenCL features may not work."
        read -p "Continue anyway? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    # Step 5: Copy helper files
    if ! copy_helper_files; then
        print_error "Failed to copy helper files"
        exit 1
    fi
    
    # Step 6: Configure wintypes DLL
    local prefix=$(get_wine_prefix)
    if ! configure_wintypes_dll; then
        print_warning "Failed to configure wintypes DLL override automatically"
        print_info "You can try configuring it manually with:"
        if [ -n "$WINEPREFIX" ]; then
            echo "  WINEPREFIX=\"$WINEPREFIX\" wine reg add \"HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides\" /v \"wintypes\" /t REG_SZ /d \"native\" /f"
        else
            echo "  wine reg add \"HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides\" /v \"wintypes\" /t REG_SZ /d \"native\" /f"
        fi
    fi
    
    print_header "Setup Complete"
    print_success "Wine environment is ready for Affinity installation!"
    echo ""
    print_info "You can now install Affinity applications from the menu."
    echo ""
    read -n 1 -s -r -p "Press any key to continue to the installation menu..."
    echo ""
    
    # Show menu and handle user selection
    while true; do
        show_affinity_menu
        read -r choice
        
        case $choice in
            1)
                install_affinity_product "Affinity"
                ;;
            2)
                install_affinity_product "Photo"
                ;;
            3)
                install_affinity_product "Designer"
                ;;
            4)
                install_affinity_product "Publisher"
                ;;
            5)
                print_header "Thank You"
                print_success "Thank you for using the Affinity Wine 10.17+ Installation Script!"
                exit 0
                ;;
            *)
                print_error "Invalid option. Please select a number between 1 and 5."
                sleep 2
                continue
                ;;
        esac
        
        if [ "$choice" != "5" ]; then
            echo ""
            read -n 1 -s -r -p "Press any key to return to the menu..."
        fi
    done
}

# Run main function
main "$@"

