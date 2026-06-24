#!/usr/bin/env bash
# Home Cloud — bootstrap installer for Raspberry Pi 5
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/omidizadi/home-cloud/main/install.sh | bash
#
# This script:
#   1. Verifies it's running on a Raspberry Pi 5 with 64-bit OS
#   2. Installs Python 3 + pip + venv if needed
#   3. Clones the home-cloud repo to /opt/homecloud
#   4. Creates a venv and installs dependencies
#   5. Launches the interactive CLI menu

set -euo pipefail

REPO="omidizadi/home-cloud"
INSTALL_DIR="/opt/homecloud"
VENV_DIR="/opt/homecloud-venv"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Pre-flight checks ─────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root (use sudo)."
    exit 1
fi

info "Checking hardware..."
if [[ -f /proc/device-tree/model ]]; then
    MODEL=$(tr -d '\0' < /proc/device-tree/model)
    info "Detected: $MODEL"
    if [[ "$MODEL" != *"Raspberry Pi 5"* ]]; then
        warn "This doesn't appear to be a Raspberry Pi 5. Proceed at your own risk."
        read -p "Continue anyway? (y/N) " -n 1 -r
        echo
        [[ $REPLY =~ ^[Yy]$ ]] || exit 1
    fi
else
    warn "Cannot detect hardware model. Proceeding anyway."
fi

ARCH=$(uname -m)
if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
    error "64-bit OS required (detected: $ARCH). Re-flash with Raspberry Pi OS Lite 64-bit."
    exit 1
fi
ok "Architecture: $ARCH"

# ── Install system deps ───────────────────────────────────────────────────────
info "Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git curl

# ── Clone repo ────────────────────────────────────────────────────────────────
if [[ -d "$INSTALL_DIR/.git" ]]; then
    info "Repo exists, pulling latest..."
    git -C "$INSTALL_DIR" pull --ff-only
else
    info "Cloning home-cloud to $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR"
    git clone "https://github.com/$REPO.git" "$INSTALL_DIR"
fi
ok "Repo ready at $INSTALL_DIR"

# ── Create venv + install ─────────────────────────────────────────────────────
info "Creating Python virtualenv..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e "$INSTALL_DIR"
ok "Dependencies installed"

# ── Create CLI wrapper ────────────────────────────────────────────────────────
WRAPPER="/usr/local/bin/homecloud"
info "Creating CLI wrapper at $WRAPPER..."
cat > "$WRAPPER" << EOF
#!/usr/bin/env bash
exec "$VENV_DIR/bin/python3" -m homecloud "\$@"
EOF
chmod +x "$WRAPPER"
ok "You can now run 'homecloud' from anywhere"

# ── Grant passwordless sudo to the invoking user ──────────────────────────────
# The app runs as SUDO_USER (non-root) but needs to write to /etc, /opt, /var
# and manage systemd services. Without passwordless sudo, every privileged
# operation fails with PermissionError.
SUDO_USER="${SUDO_USER:-pi}"
SUDOERS_FILE="/etc/sudoers.d/homecloud"
info "Granting passwordless sudo to '$SUDO_USER'..."
echo "$SUDO_USER ALL=(ALL) NOPASSWD: ALL" > "$SUDOERS_FILE"
chmod 0440 "$SUDOERS_FILE"
# Validate sudoers syntax before committing (visudo -c)
if command -v visudo >/dev/null 2>&1; then
    if ! visudo -cf "$SUDOERS_FILE" >/dev/null 2>&1; then
        warn "sudoers syntax check failed — removing $SUDOERS_FILE to stay safe"
        rm -f "$SUDOERS_FILE"
        error "Could not configure passwordless sudo. Aborting."
        exit 1
    fi
fi
ok "Passwordless sudo enabled for '$SUDO_USER'"

# ── Launch ────────────────────────────────────────────────────────────────────
echo
ok "Setup complete! Launching Home Cloud..."
echo
echo -e "${CYAN}Tip:${NC} Run with --dry-run first to preview commands:"
echo -e "  ${YELLOW}homecloud --dry-run${NC}"
echo

info "Launching as user '$SUDO_USER'..."
exec sudo -u "$SUDO_USER" "$VENV_DIR/bin/python3" -m homecloud "$@"
