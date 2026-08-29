#!/bin/bash

################################################################################
# Affinity Publisher Installation Script for Linux
# This script automates the installation of Affinity Publisher on Linux
# using Wine with OpenCL support enabled.
################################################################################

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

################################################################################
# Distribution Detection
################################################################################

# Function to detect Linux distribution
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO=$(echo "$ID" | tr '[:upper:]' '[:lower:]')
        VERSION=$VERSION_ID
        # Normalize "pika" to "pikaos" if detected
        if [ "$DISTRO" = "pika" ]; then
            DISTRO="pikaos"
        fi
    else
        print_error "Could not detect Linux distribution"
        exit 1
    fi
}

# Detect distribution
detect_distro

################################################################################
# Distribution Warnings
################################################################################

# Check for unsupported distributions
case $DISTRO in
    "ubuntu"|"linuxmint"|"zorin"|"bazzite")
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
        echo -e "${RED}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo ""
        ;;
    "pikaos")
        print_header "PikaOS Special Notice"
        echo ""
        echo -e "${YELLOW}${BOLD}⚠️  IMPORTANT: PikaOS Wine Configuration Required${NC}"
        echo ""
        echo -e "${CYAN}PikaOS's built-in Wine has compatibility issues with Affinity applications.${NC}"
        echo -e "${CYAN}You must replace it with WineHQ staging from Debian before continuing.${NC}"
        echo ""
        echo -e "${BOLD}Please run these commands manually to set up WineHQ staging:${NC}"
        echo ""
        echo -e "${GREEN}sudo mkdir -pm755 /etc/apt/keyrings${NC}"
        echo ""
        echo -e "${GREEN}wget -O - https://dl.winehq.org/wine-builds/winehq.key | sudo gpg --dearmor -o /etc/apt/keyrings/winehq-archive.key -${NC}"
        echo ""
        echo -e "${GREEN}sudo dpkg --add-architecture i386${NC}"
        echo ""
        echo -e "${CYAN}# Detect your Debian codename (e.g., bookworm, trixie) and replace CODENAME below:${NC}"
        echo -e "${CYAN}# Run: lsb_release -cs (or check /etc/debian_version)${NC}"
        echo -e "${GREEN}sudo wget -NP /etc/apt/sources.list.d/ https://dl.winehq.org/wine-builds/debian/dists/CODENAME/winehq-CODENAME.sources${NC}"
        echo ""
        echo -e "${GREEN}sudo apt update${NC}"
        echo ""
        echo -e "${GREEN}sudo apt install --install-recommends winehq-staging${NC}"
        echo ""
        echo -e "${YELLOW}Press any key to continue after completing the WineHQ staging installation...${NC}"
        read -n 1 -s
        echo ""
        echo ""
        ;;
esac

################################################################################
# SECTION 1: Dependency Verification
################################################################################

print_header "Dependency Verification"
print_info "Checking for required system dependencies..."

missing_deps=""

check_dependency() {
    print_progress "Checking for $1..."
    if ! command -v "$1" &> /dev/null; then
        missing_deps+="$1 "
        print_error "$1 is not installed"
        return 1
    else
        print_success "$1 is installed"
        return 0
    fi
}

check_dependency "wine"
check_dependency "winetricks"
check_dependency "wget"
check_dependency "curl"
# Check for either 7z or unzip (both can extract archives)
if ! command -v 7z &> /dev/null && ! command -v unzip &> /dev/null; then
    missing_deps+="7z or unzip "
    print_error "Neither 7z nor unzip is installed (at least one is required)"
else
    if command -v 7z &> /dev/null; then
        print_success "7z is installed"
    else
        print_success "unzip is installed (will be used instead of 7z)"
    fi
fi
check_dependency "tar"

if [ -n "$missing_deps" ]; then
    print_error "Missing required dependencies: ${missing_deps}"
    echo ""
    case $DISTRO in
        "ubuntu"|"linuxmint"|"zorin"|"bazzite")
            echo -e "${RED}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "${RED}${BOLD}                    ⚠️   WARNING: UNSUPPORTED DISTRIBUTION   ⚠️${NC}"
            echo -e "${RED}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo ""
            echo -e "${YELLOW}${BOLD}This script will NOT automatically install dependencies for unsupported distributions.${NC}"
            echo -e "${YELLOW}Please install the required dependencies manually:${NC}"
            echo -e "${CYAN}  wine winetricks wget curl p7zip-full tar${NC}"
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
                check_dependency "wine"
                check_dependency "winetricks"
                check_dependency "wget"
                check_dependency "curl"
                if ! command -v 7z &> /dev/null && ! command -v unzip &> /dev/null; then
                    missing_deps+="7z or unzip "
                fi
                check_dependency "tar"
                if [ -z "$missing_deps" ]; then
                    print_success "All dependencies are now installed!"
                    break
                else
                    print_error "Still missing: ${missing_deps}"
                fi
            done
            ;;
        *)
            print_info "Please install the missing dependencies and rerun this script."
            print_info "Example for Arch-based systems: sudo pacman -S wine winetricks wget curl p7zip tar"
            exit 1
            ;;
    esac
fi

print_success "All required dependencies are installed!"
case $DISTRO in
    "ubuntu"|"linuxmint"|"zorin"|"bazzite")
        echo ""
        echo -e "${YELLOW}${BOLD}Continuing despite unsupported distribution. No support will be provided if issues arise.${NC}"
        ;;
esac
echo ""
sleep 1

################################################################################
# SECTION 2: Environment Setup
################################################################################

print_header "Environment Setup"
print_info "Preparing installation environment..."

directory="$HOME/.AffinityLinux"
wine_url="https://github.com/seapear/AffinityOnLinux/releases/download/Legacy/ElementalWarriorWine-x86_64.tar.gz"
filename="ElementalWarriorWine-x86_64.tar.gz"

print_step "Stopping any running Wine processes..."
wineserver -k 2>/dev/null || true
print_success "Wine processes stopped"

print_step "Creating installation directory: $directory"
mkdir -p "$directory"
print_success "Installation directory created"

################################################################################
# SECTION 3: Wine Binary Download and Extraction
################################################################################

print_header "Wine Binary Setup"
print_info "Downloading and configuring the custom Wine build (ElementalWarriorWine)..."

print_step "Downloading Wine binary from GitHub releases..."
if wget -q --show-progress "$wine_url" -O "$directory/$filename"; then
    print_success "Wine binary downloaded successfully"
else
    print_error "Failed to download Wine binary"
    exit 1
fi

print_step "Extracting Wine binary archive..."
if tar -xzf "$directory/$filename" -C "$directory" 2>/dev/null; then
    print_success "Wine binary extracted successfully"
else
    print_error "Failed to extract Wine binary archive"
    exit 1
fi

print_step "Locating Wine installation directory..."
wine_dir=$(find "$directory" -name "ElementalWarriorWine*" -type d | head -1)
if [ -n "$wine_dir" ] && [ "$wine_dir" != "$directory/ElementalWarriorWine" ]; then
    print_info "Creating symlink for Wine directory..."
    ln -sf "$wine_dir" "$directory/ElementalWarriorWine"
    print_success "Symlink created: $directory/ElementalWarriorWine"
fi

print_step "Verifying Wine binary exists..."
if [ ! -f "$directory/ElementalWarriorWine/bin/wine" ]; then
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
print_success "Wine binary verified: $directory/ElementalWarriorWine/bin/wine"

print_step "Cleaning up downloaded archive..."
rm -f "$directory/$filename"
print_success "Archive file removed"

################################################################################
# SECTION 4: Additional Resources Download
################################################################################

print_header "Downloading Additional Resources"
print_info "Fetching Windows metadata and application icons..."

print_step "Downloading Windows metadata files..."
if wget -q --show-progress "https://archive.org/download/win-metadata/WinMetadata.zip" -O "$directory/Winmetadata.zip"; then
    print_success "Windows metadata downloaded"
else
    print_warning "Failed to download Windows metadata (this may cause minor issues)"
fi

print_step "Downloading Affinity Publisher icon..."
mkdir -p "/home/$USER/.local/share/icons"
if wget -q "https://upload.wikimedia.org/wikipedia/commons/9/9c/Affinity_Publisher_V2_icon.svg" -O "/home/$USER/.local/share/icons/AffinityPublisher.svg"; then
    print_success "Icon downloaded to ~/.local/share/icons/AffinityPublisher.svg"
else
    print_warning "Could not download icon file (will continue without it)"
fi

################################################################################
# SECTION 5: Wine Configuration and Dependencies
################################################################################

print_header "Wine Configuration"
print_info "Installing required Windows libraries and configuring Wine..."

print_step "Installing .NET Framework 3.5..."
WINEPREFIX="$directory" winetricks --unattended dotnet35 >/dev/null 2>&1 || true
print_progress ".NET 3.5 installation attempted"

print_step "Installing .NET Framework 4.8..."
WINEPREFIX="$directory" winetricks --unattended dotnet48 >/dev/null 2>&1 || true
print_progress ".NET 4.8 installation attempted"

print_step "Installing Windows core fonts..."
WINEPREFIX="$directory" winetricks --unattended corefonts >/dev/null 2>&1 || true
print_progress "Core fonts installation attempted"

print_step "Installing Visual C++ Redistributables 2022..."
WINEPREFIX="$directory" winetricks --unattended vcrun2022 >/dev/null 2>&1 || true
print_progress "VC++ 2022 installation attempted"

print_step "Installing MSXML 3.0..."
WINEPREFIX="$directory" winetricks --unattended msxml3 >/dev/null 2>&1 || true
print_progress "MSXML 3.0 installation attempted"

print_step "Installing MSXML 6.0..."
WINEPREFIX="$directory" winetricks --unattended msxml6 >/dev/null 2>&1 || true
print_progress "MSXML 6.0 installation attempted"

print_step "Installing Tahoma font..."
WINEPREFIX="$directory" winetricks --unattended tahoma >/dev/null 2>&1 || true
print_progress "Tahoma font installation attempted"

print_step "Configuring Wine to use Vulkan renderer..."
WINEPREFIX="$directory" winetricks renderer=vulkan >/dev/null 2>&1 || true
print_success "Wine configured with Vulkan renderer"

print_info "Note: The above installations may take several minutes. Errors are normal if components are already installed."

################################################################################
# SECTION 6: Windows Metadata Extraction
################################################################################

print_header "Windows Metadata Installation"
print_info "Extracting Windows metadata files to system32 directory..."

mkdir -p "$directory/drive_c/windows/system32"

if [ -f "$directory/Winmetadata.zip" ]; then
    print_step "Extracting Windows metadata archive..."
    
    if command -v 7z &> /dev/null; then
        if 7z x "$directory/Winmetadata.zip" -o"$directory/drive_c/windows/system32" -y >/dev/null 2>&1; then
            print_success "Windows metadata extracted successfully using 7z"
        else
            print_warning "7z extraction had issues, trying unzip..."
            unzip -o "$directory/Winmetadata.zip" -d "$directory/drive_c/windows/system32" >/dev/null 2>&1 || true
            print_success "Windows metadata extracted using unzip"
        fi
    elif command -v unzip &> /dev/null; then
        if unzip -o "$directory/Winmetadata.zip" -d "$directory/drive_c/windows/system32" >/dev/null 2>&1; then
            print_success "Windows metadata extracted successfully using unzip"
        else
            print_error "Failed to extract Windows metadata"
        fi
    else
        print_error "Neither 7z nor unzip is available to extract Windows metadata"
        print_info "Please install either 7z or unzip and rerun the script"
    fi
    
    print_step "Cleaning up metadata archive..."
    rm -f "$directory/Winmetadata.zip"
    print_success "Archive removed"
else
    print_warning "WinMetadata.zip was not downloaded successfully"
fi

################################################################################
# SECTION 7: vkd3d-proton Installation for OpenCL Support
################################################################################

print_header "OpenCL Support Setup"
print_info "Installing vkd3d-proton for hardware acceleration and OpenCL support..."
print_info "This enables GPU acceleration features in Affinity Publisher"

# Fetch latest vkd3d-proton version from GitHub API (fallback: 3.0.1)
vkd3d_version=""
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
vkd3d_archive="vkd3d-proton-${vkd3d_version}.tar.zst"
vkd3d_url="https://github.com/HansKristian-Work/vkd3d-proton/releases/download/v${vkd3d_version}/${vkd3d_archive}"

print_step "Downloading vkd3d-proton v${vkd3d_version} from GitHub..."
if wget -q --show-progress "$vkd3d_url" -O "$directory/$vkd3d_archive"; then
    print_success "vkd3d-proton downloaded successfully"
else
    print_error "Failed to download vkd3d-proton"
    print_warning "OpenCL support may not work correctly"
fi

print_step "Extracting vkd3d-proton archive..."
extracted=false
if command -v unzstd &> /dev/null; then
    if unzstd -f "$directory/$vkd3d_archive" -o "$directory/vkd3d-proton.tar" 2>/dev/null; then
        if tar -xf "$directory/vkd3d-proton.tar" -C "$directory" 2>/dev/null; then
            rm "$directory/vkd3d-proton.tar"
            extracted=true
            print_success "vkd3d-proton extracted using unzstd"
        fi
    fi
elif command -v zstd &> /dev/null && tar --help 2>&1 | grep -q "use-compress-program"; then
    if tar --use-compress-program=zstd -xf "$directory/$vkd3d_archive" -C "$directory" 2>/dev/null; then
        extracted=true
        print_success "vkd3d-proton extracted using zstd with tar"
    fi
fi

if [ "$extracted" = false ]; then
    print_error "Cannot extract .tar.zst file. Please install zstd (e.g., sudo pacman -S zstd)"
    print_warning "Skipping vkd3d-proton installation. OpenCL will not work!"
    rm -f "$directory/$vkd3d_archive"
fi

rm -f "$directory/$vkd3d_archive"

print_step "Installing vkd3d-proton DLLs to Wine library directory..."
vkd3d_dir=$(find "$directory" -type d -name "vkd3d-proton-*" | head -1)
if [ -n "$vkd3d_dir" ]; then
    wine_lib_dir="$directory/ElementalWarriorWine/lib/wine/vkd3d-proton/x86_64-windows"
    mkdir -p "$wine_lib_dir"
    
    dll_count=0
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
    
    print_step "Cleaning up extracted vkd3d-proton directory..."
    rm -rf "$vkd3d_dir"
    print_success "vkd3d-proton setup completed"
else
    print_warning "Could not locate vkd3d-proton directory after extraction"
fi

################################################################################
# SECTION 8: Affinity Publisher Installation
################################################################################

print_header "Affinity Publisher Installation"
print_info "You will now install Affinity Publisher using its Windows installer You Already Downloaded Before!"

print_step "Once downloaded, place the .exe file in:"
echo -e "  ${CYAN}$directory${NC}"
echo ""
print_info "Press any key when the installer file is ready..."
read -n 1 -s
echo ""

# Verify .exe exists
if ! ls "$directory"/*.exe 1> /dev/null 2>&1; then
    print_error "No .exe file found in $directory"
    print_info "Please ensure the Affinity Publisher installer is in the correct location and rerun this script"
    exit 1
fi

print_success "Installer file detected"
echo ""
print_warning "If you encounter any errors during installation, click 'No' to continue"
print_info "Press any key to start the installation..."
read -n 1 -s
echo ""

print_step "Configuring Wine to use Windows 11 compatibility mode..."
WINEPREFIX="$directory" "$directory/ElementalWarriorWine/bin/winecfg" -v win11 >/dev/null 2>&1 || true
print_success "Wine configured for Windows 11"

print_step "Launching Affinity Publisher installer..."
print_info "Follow the installation wizard in the window that opens"
WINEPREFIX="$directory" "$directory/ElementalWarriorWine/bin/wine" "$directory"/*.exe

print_step "Cleaning up installer file..."
rm -f "$directory"/affinity*.exe
print_success "Installer file removed"

################################################################################
# SECTION 9: Post-Installation Configuration
################################################################################

print_header "Post-Installation Configuration"
print_info "Applying final configuration settings..."

print_step "Applying Wine dark theme..."
if wget -q "https://raw.githubusercontent.com/seapear/AffinityOnLinux/refs/heads/main/Auxiliary/Other/wine-dark-theme.reg" -O "$directory/wine-dark-theme.reg"; then
    WINEPREFIX="$directory" "$directory/ElementalWarriorWine/bin/regedit" "$directory/wine-dark-theme.reg" >/dev/null 2>&1 || true
    rm -f "$directory/wine-dark-theme.reg"
    print_success "Dark theme applied to Wine"
else
    print_warning "Could not download dark theme registry file"
fi

print_step "Configuring OpenCL support in Affinity Publisher..."
affinity_dir="$directory/drive_c/Program Files/Affinity/Publisher 2"
wine_lib_dir="$directory/ElementalWarriorWine/lib/wine/vkd3d-proton/x86_64-windows"

if [ -d "$affinity_dir" ] && [ -d "$wine_lib_dir" ]; then
    print_info "Copying vkd3d-proton DLLs to Affinity Publisher application directory..."
    dll_copied=0
    
    if [ -f "$wine_lib_dir/d3d12.dll" ]; then
        if cp "$wine_lib_dir/d3d12.dll" "$affinity_dir/" 2>/dev/null; then
            print_progress "Copied d3d12.dll to Affinity Publisher directory"
            ((dll_copied++))
        fi
    fi
    
    if [ -f "$wine_lib_dir/d3d12core.dll" ]; then
        if cp "$wine_lib_dir/d3d12core.dll" "$affinity_dir/" 2>/dev/null; then
            print_progress "Copied d3d12core.dll to Affinity Publisher directory"
            ((dll_copied++))
        fi
    fi
    
    if [ $dll_copied -gt 0 ]; then
        print_success "Copied $dll_copied OpenCL DLL file(s) to Affinity Publisher directory"
    fi
    
    print_info "Configuring Wine DLL overrides for OpenCL support..."
    reg_file="$directory/dll_overrides.reg"
    {
        echo "REGEDIT4"
        echo "[HKEY_CURRENT_USER\\Software\\Wine\\DllOverrides]"
        echo "\"d3d12\"=\"native\""
        echo "\"d3d12core\"=\"native\""
    } > "$reg_file"
    
    if WINEPREFIX="$directory" "$directory/ElementalWarriorWine/bin/regedit" "$reg_file" >/dev/null 2>&1; then
        print_success "DLL overrides configured in Wine registry"
    else
        print_warning "Could not apply DLL overrides (OpenCL may not work)"
    fi
    
    rm -f "$reg_file"
    
    if [ $dll_copied -gt 0 ]; then
        print_success "OpenCL support fully configured!"
    fi
else
    if [ ! -d "$affinity_dir" ]; then
        print_warning "Affinity Publisher installation directory not found. OpenCL configuration skipped."
    fi
    if [ ! -d "$wine_lib_dir" ]; then
        print_warning "vkd3d-proton library directory not found. OpenCL configuration skipped."
    fi
fi

################################################################################
# SECTION 10: Desktop Integration
################################################################################

print_header "Desktop Integration"
print_info "Creating desktop entry and application shortcuts..."

print_step "Removing default Wine desktop entry..."
rm -f "/home/$USER/.local/share/applications/wine/Programs/Affinity Publisher 2.desktop"
print_success "Default entry removed"

print_step "Creating custom desktop entry..."
desktop_file="$HOME/.local/share/applications/AffinityPublisher.desktop"
mkdir -p "$HOME/.local/share/applications"

# Normalize directory path (remove trailing slash if present)
directory="${directory%/}"

# Check for AMD GPU for DXVK configuration
dxvk_env=""
if command -v lspci &> /dev/null; then
    if lspci | grep -qiE "(amd|radeon|amd/ati).*vga\|3d\|display"; then
        dxvk_env='DXVK_ASYNC=0 DXVK_CONFIG="d3d9.deferSurfaceCreation = True; d3d9.shaderModel = 1" '
    fi
fi

{
    echo "[Desktop Entry]"
    echo "Name=Affinity Publisher"
    echo "Comment=Affinity Publisher is a desktop publishing application developed by Serif for iPadOS, macOS and Microsoft Windows."
    echo "Icon=/home/$USER/.local/share/icons/AffinityPublisher.svg"
    echo "Path=$directory"
    echo "Exec=env WINEPREFIX=$directory ${dxvk_env}$directory/ElementalWarriorWine/bin/wine \"$directory/drive_c/Program Files/Affinity/Publisher 2/Publisher.exe\""
    echo "Terminal=false"
    echo "NoDisplay=false"
    echo "StartupWMClass=publisher.exe"
    echo "Type=Application"
    echo "Categories=Graphics;"
    echo "StartupNotify=true"
} > "$desktop_file"

print_success "Desktop entry created: $desktop_file"

print_step "Creating desktop shortcut..."
mkdir -p ~/Desktop
cp "$desktop_file" ~/Desktop/AffinityPublisher.desktop 2>/dev/null || true
print_success "Desktop shortcut created"

################################################################################
# SECTION 11: Installation Complete
################################################################################

print_header "Installation Complete"
print_success "Affinity Publisher has been successfully installed!"
echo ""
print_info "Installation location: $directory"
print_info "Desktop entry: ~/.local/share/applications/AffinityPublisher.desktop"
echo ""
print_info "You can now launch Affinity Publisher from:"
echo -e "  ${CYAN}•${NC} Your application menu (search for 'Affinity Publisher')"
echo -e "  ${CYAN}•${NC} The desktop shortcut"
echo -e "  ${CYAN}•${NC} Command line: wine $directory/drive_c/Program\ Files/Affinity/Publisher\ 2/Publisher.exe"
echo ""
print_info "OpenCL hardware acceleration should be enabled. You can verify this in:"
echo -e "  ${CYAN}•${NC} Affinity Publisher Preferences → Performance → Hardware Acceleration"
echo ""
print_success "Enjoy using Affinity Publisher on Linux!"
