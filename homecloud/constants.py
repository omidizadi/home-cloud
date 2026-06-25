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
DATA_MOUNT = Path("/mnt/data")
IMMICH_DATADIR = DATA_MOUNT / "immich"

# Script / service locations
BACKUP_SCRIPT = Path("/opt/homecloud-backup.sh")
BACKUP_LOG = Path("/var/log/homecloud-backup.log")
BOT_SCRIPT = Path("/opt/homecloud-bot.py")
BOT_VENV = Path("/opt/homecloud-bot-env")
BOT_SERVICE = Path("/etc/systemd/system/homecloud-bot.service")
BOT_SERVICE_NAME = "homecloud-bot"
TAILSCALE_SERVICE = Path("/etc/systemd/system/tailscaled.service")
DOCKER_SSD_OVERRIDE = Path("/etc/systemd/system/docker.service.d/wait-for-ssd.conf")
REPLUG_UDEV_RULE = Path("/etc/udev/rules.d/99-data.rules")
REPLUG_SERVICE = Path("/etc/systemd/system/data-replug.service")
REPLUG_SERVICE_NAME = "data-replug"
REPLUG_SCRIPT = Path("/usr/local/bin/homecloud-replug.sh")

# Immich compose location (compose files live on the SD card; data on the SSD)
IMMICH_COMPOSE_DIR = Path("/opt/homecloud/immich")

# Container names
IMMICH_SERVER_CONTAINER = "immich-server"
IMMICH_ML_CONTAINER = "immich-machine-learning"
IMMICH_DB_CONTAINER = "immich-postgres"
IMMICH_REDIS_CONTAINER = "immich-redis"

# Ports
IMMICH_WEB_PORT = 2283

# GitHub
GITHUB_REPO = "omidizadi/home-cloud"
GITHUB_RAW = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main"
INSTALL_URL = f"{GITHUB_RAW}/install.sh"

# Templates
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
