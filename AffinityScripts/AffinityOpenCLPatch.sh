#!/bin/bash

################################################################################
# Affinity OpenCL Hardware Acceleration Patcher
# Patches libraster.dll to bypass Windows-only OpenCL device discovery APIs
# that don't exist under Wine/ROCm/Mesa.
#
# Three patches applied:
# 1. Bypass DXGI<->OpenCL device matching (Wine stubs clGetDeviceIDsFromD3D10KHR)
# 2. Bypass cl_khr_d3d10_sharing extension checks in all IsSupported instances
# 3. Bypass D3D12<->OpenCL interop check in IsSupported
#
# Safe to run repeatedly -- exits early if already patched.
# Backs up the original on first patch.
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
# Main
################################################################################

WINEPREFIX="${WINEPREFIX:-$HOME/.AffinityLinux}"
DLL="${1:-$WINEPREFIX/drive_c/Program Files/Affinity/Affinity/libraster.dll}"

if [ ! -f "$DLL" ]; then
    print_error "libraster.dll not found: $DLL"
    exit 1
fi

print_header "Affinity OpenCL Hardware Acceleration Patcher"
print_info "Target: $DLL"

python3 - "$DLL" << 'PYEOF'
import sys, shutil, os

dll_path = sys.argv[1]

with open(dll_path, 'rb') as f:
    data = bytearray(f.read())

total_applied = 0
total_already = 0

# --- Patch 1: Bypass DXGI adapter matching ---
PATCH1_SEARCH  = bytes([0x49, 0x39, 0x07, 0x0F, 0x85])
PATCH1_TRAILER = bytes([0x40, 0x32, 0xF6, 0x48, 0x8D, 0x0D])
PATCH1_DONE    = bytes([0x49, 0x39, 0x07, 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0x40, 0x32, 0xF6, 0x48, 0x8D, 0x0D])

if data.find(PATCH1_DONE) >= 0:
    print("[✓] Patch 1: already applied (DXGI matching bypassed)")
    total_already += 1
else:
    pos = 0
    found = -1
    while True:
        pos = data.find(PATCH1_SEARCH, pos)
        if pos < 0:
            break
        jne_end = pos + 3 + 6
        if jne_end + len(PATCH1_TRAILER) <= len(data):
            if data[jne_end:jne_end + len(PATCH1_TRAILER)] == PATCH1_TRAILER:
                found = pos
                break
        pos += 1
    if found < 0:
        print("[ERROR] Patch 1: signature not found", file=sys.stderr)
        sys.exit(1)
    data[found + 3:found + 3 + 6] = b'\x90' * 6
    total_applied += 1
    print("[✓] Patch 1: DXGI<->OpenCL matching bypassed")

# --- Patch 2: Bypass cl_khr_d3d10_sharing in ALL IsSupported checks ---
pattern = bytes([0x84, 0xC0, 0x75, 0x04, 0x32, 0xC0, 0xEB])
patched = bytes([0x84, 0xC0, 0xEB, 0x04, 0x32, 0xC0, 0xEB])

pos = 0
count = 0
while True:
    pos = data.find(pattern, pos)
    if pos < 0:
        break
    data[pos + 2] = 0xEB
    count += 1
    print(f"[✓] Patch 2.{count}: d3d10_sharing check bypassed at 0x{pos:x}")
    pos += len(pattern)

pos = 0
already = 0
while True:
    pos = data.find(patched, pos)
    if pos < 0:
        break
    already += 1
    pos += len(patched)
already -= count

if count > 0:
    total_applied += count
elif already > 0:
    print(f"[✓] Patch 2: already applied ({already} instance(s))")
    total_already += already

# --- Patch 3: Bypass D3D12 Feature Level 12.0 interop check ---
PATCH3_SEARCH = bytes([0x48, 0x85, 0xDB, 0x74, 0x17])
PATCH3_DONE   = bytes([0x48, 0x85, 0xDB, 0xEB, 0x12])
PATCH3_CONTEXT = bytes([0xBA, 0x00, 0xC0, 0x00, 0x00])

if data.find(PATCH3_DONE) >= 0:
    print("[✓] Patch 3: already applied (D3D12 interop check bypassed)")
    total_already += 1
else:
    pos = 0
    found = -1
    while True:
        pos = data.find(PATCH3_SEARCH, pos)
        if pos < 0:
            break
        nearby = data[pos:pos + 30]
        if nearby.find(PATCH3_CONTEXT) >= 0:
            found = pos
            break
        pos += 1
    if found < 0:
        print("[WARNING] Patch 3: D3D12 interop signature not found (may not be needed)", file=sys.stderr)
    else:
        data[found + 3] = 0xEB
        data[found + 4] = 0x12
        total_applied += 1
        print(f"[✓] Patch 3: D3D12 interop check bypassed at 0x{found:x}")

if total_applied == 0:
    print("[INFO] All patches already applied.")
    sys.exit(0)

backup = dll_path + ".orig"
if not os.path.exists(backup):
    shutil.copy2(dll_path, backup)
    print(f"[INFO] Backed up original to {os.path.basename(backup)}")

with open(dll_path, 'wb') as f:
    f.write(data)

print(f"[✓] Done: {total_applied} patch(es) applied.")
PYEOF

exit_code=$?
if [ $exit_code -eq 0 ]; then
    print_success "OpenCL patches complete"
else
    print_error "OpenCL patching failed (exit code $exit_code)"
fi
exit $exit_code
