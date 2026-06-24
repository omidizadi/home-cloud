"""Global constants and paths used across Home Cloud."""

from __future__ import annotations

from pathlib import Path

# Install locations
INSTALL_DIR = Path("/opt/homecloud")
VENV_DIR = Path("/opt/homecloud-venv")
STATE_DIR = Path("/etc/homecloud/state")
CONFIG_DIR = Path("/etc/homecloud")
ENV_FILE = CONFIG_DIR / ".env"
LOG_DIR = Path("/var/log/homecloud")

# Data locations
NCDATA_MOUNT = Path("/mnt/ncdata")
NEXTCLOUD_DATADIR = NCDATA_MOUNT / "nextcloud"
SAMBA_SHARE_DIR = NCDATA_MOUNT / "files"
BORG_BACKUP_DIR = NCDATA_MOUNT / "borg-backup"

# Script / service locations
BACKUP_SCRIPT = Path("/opt/nextcloud-s3-backup.sh")
DUCKDNS_SCRIPT = Path("/opt/duckdns/duck.sh")
BOT_SCRIPT = Path("/opt/ncbot.py")
BOT_VENV = Path("/opt/ncbot-env")
BOT_SERVICE = Path("/etc/systemd/system/ncbot.service")
TAILSCALE_SERVICE = Path("/etc/systemd/system/tailscaled.service")
DOCKER_SSD_OVERRIDE = Path("/etc/systemd/system/docker.service.d/wait-for-ssd.conf")
REPLUG_UDEV_RULE = Path("/etc/udev/rules.d/99-ncdata.rules")
REPLUG_SERVICE = Path("/etc/systemd/system/ncdata-replug.service")
REPLUG_SCRIPT = Path("/usr/local/bin/homecloud-replug.sh")

# Container names
AIO_MASTER_CONTAINER = "nextcloud-aio-mastercontainer"
AIO_NEXTCLOUD_CONTAINER = "nextcloud-aio-nextcloud"

# Ports
AIO_ADMIN_PORT = 8080
NEXTCLOUD_HTTPS_PORT = 443
NEXTCLOUD_HTTP_PORT = 80
TURN_PORT = 3478
TURN_TLS_PORT = 5349

# GitHub
GITHUB_REPO = "omidizadi/home-cloud"
GITHUB_RAW = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main"
INSTALL_URL = f"{GITHUB_RAW}/install.sh"

# Templates
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
