"""Configuration & secrets management via /etc/homecloud/.env.

Includes:
  - typed config schema with defaults
  - load/save with 0600 perms (root-owned)
  - validation
  - secrets export for offline recovery
"""

from __future__ import annotations

import io
import json
import os
import secrets as pysecrets
import string
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from .constants import CONFIG_DIR, ENV_FILE
from .utils import file_exists_sudo, log, read_file_sudo, run, write_file_sudo

# ── Schema ────────────────────────────────────────────────────────────────────


@dataclass
class Config:
    """All user-supplied configuration. Persisted to .env."""

    # ── SSD ──
    ssd_device: str = ""  # e.g. /dev/sda
    ssd_label: str = "data"

    # ── AWS S3 ──
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_bucket: str = ""
    s3_region: str = "eu-central-1"

    # ── restic ──
    restic_password: str = ""

    # ── Telegram ──
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # ── Immich ──
    # Auto-generated secrets (set blank to generate during config):
    immich_jwt_secret: str = ""
    immich_db_password: str = ""
    # API key generated in the Immich web UI post-install (manual entry).
    # The bot needs this to query the Immich REST API.
    immich_api_key: str = ""
    # Set at runtime by ImmichStep from the Tailscale tailnet hostname
    # (e.g. homecloud.tail665a7d.ts.net). Not in .env, not required for is_complete().
    immich_domain: str = ""

    # ── Tailscale (external access, bypasses DS-Lite/CGNAT) ──
    tailscale_auth_key: str = ""  # tskey-... from https://login.tailscale.com/admin/settings/keys

    # ── WiFi (optional) ──
    wifi_ssid: str = ""
    wifi_password: str = ""

    # ── Misc ──
    timezone: str = "Europe/Berlin"

    # ── Internal flags (not persisted) ──
    _internal: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        # immich_domain is set at runtime by the ImmichStep
        # using the Tailscale tailnet hostname.
        pass

    @property
    def restic_repository(self) -> str:
        return f"s3:s3.{self.s3_region}.amazonaws.com/{self.s3_bucket}"

    @property
    def immich_url(self) -> str:
        return f"https://{self.immich_domain}" if self.immich_domain else "https://<pi>.<tailnet>.ts.net"

    def is_complete(self) -> bool:
        """True if all required fields are set."""
        required = [
            "ssd_device",
            "aws_access_key_id",
            "aws_secret_access_key",
            "s3_bucket",
            "restic_password",
            "telegram_bot_token",
            "telegram_chat_id",
            "immich_jwt_secret",
            "immich_db_password",
        ]
        return all(getattr(self, f) for f in required)

    def missing_fields(self) -> list[str]:
        required = [
            "ssd_device",
            "aws_access_key_id",
            "aws_secret_access_key",
            "s3_bucket",
            "restic_password",
            "telegram_bot_token",
            "telegram_chat_id",
            "immich_jwt_secret",
            "immich_db_password",
        ]
        return [f for f in required if not getattr(self, f)]


# ── Load / Save ───────────────────────────────────────────────────────────────


def load_config() -> Config:
    """Load config from .env, falling back to defaults.

    The .env file is root-owned with 0600 perms, so when running as a
    non-root user we must read it through sudo.
    """
    if not file_exists_sudo(ENV_FILE):
        return Config()
    content = read_file_sudo(ENV_FILE)
    if content is None:
        return Config()
    values = dotenv_values(stream=io.StringIO(content))
    data: dict[str, Any] = {}
    for f in fields(Config):
        if f.name.startswith("_"):
            continue
        env_key = f.name.upper()
        if env_key in values and values[env_key] is not None:
            data[f.name] = values[env_key]
    return Config(**data)


def save_config(cfg: Config, *, dry_run: bool = False) -> None:
    """Persist config to .env with 0600 perms, root-owned.

    Writes go through sudo so this works when the app is running as a
    non-root user (the normal case — see install.sh).
    """
    lines = []
    for f in fields(Config):
        if f.name.startswith("_"):
            continue
        val = getattr(cfg, f.name)
        if val:
            lines.append(f"{f.name.upper()}={val}")
    content = "\n".join(lines) + "\n"
    if dry_run:
        log.info("[dry-run] would write %s:\n%s", ENV_FILE, content)
        return
    write_file_sudo(ENV_FILE, content, mode=0o600)
    log.info("config saved to %s", ENV_FILE)


def delete_config(*, dry_run: bool = False) -> None:
    """Remove the .env file (used by uninstall)."""
    if not ENV_FILE.exists():
        return
    if dry_run:
        log.info("[dry-run] would remove %s", ENV_FILE)
        return
    ENV_FILE.unlink()
    log.info("config removed: %s", ENV_FILE)


# ── Validation ────────────────────────────────────────────────────────────────


def validate(cfg: Config) -> list[str]:
    """Return a list of human-readable validation errors (empty = valid)."""
    errors: list[str] = []
    if not cfg.ssd_device.startswith("/dev/"):
        errors.append("SSD device must be a /dev/ path (e.g. /dev/sda)")
    if cfg.s3_bucket and not all(
        c in string.ascii_lowercase + string.digits + ".-" for c in cfg.s3_bucket
    ):
        errors.append("S3 bucket name invalid (lowercase, numbers, ., -)")
    if cfg.telegram_bot_token and ":" not in cfg.telegram_bot_token:
        errors.append("Telegram bot token looks invalid (expected format 123:ABC)")
    if cfg.telegram_chat_id and not cfg.telegram_chat_id.lstrip("-").isdigit():
        errors.append("Telegram chat ID must be numeric")
    if cfg.restic_password and len(cfg.restic_password) < 12:
        errors.append("restic password must be at least 12 characters")
    return errors


# ── Secrets generation ────────────────────────────────────────────────────────


def generate_password(length: int = 32) -> str:
    """Generate a strong random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(pysecrets.choice(alphabet) for _ in range(length))


# ── Recovery export ───────────────────────────────────────────────────────────


def export_recovery_bundle(output_path: Path | None = None) -> Path:
    """Export all secrets + config to a JSON bundle for offline safekeeping.

    The bundle includes:
      - all .env values
      - restic repo location
      - immich URL
      - install state markers
      - a restore command hint

    Returns the path to the written bundle.
    """
    from .utils.state import all_steps

    cfg = load_config()
    bundle: dict[str, Any] = {
        "_warning": (
            "This file contains ALL secrets for your home cloud. "
            "Store it somewhere safe and offline (e.g. a USB stick in a drawer). "
            "Delete it from the Pi after saving."
        ),
        "_restore_hint": (
            "To restore on a fresh Pi: install homecloud, then run "
            "`homecloud secrets import <this-file>` before starting install."
        ),
        "exported_at": __import__("datetime").datetime.now().isoformat(),
        "config": {f.name: getattr(cfg, f.name) for f in fields(Config) if not f.name.startswith("_")},
        "derived": {
            "restic_repository": cfg.restic_repository,
            "immich_url": cfg.immich_url,
        },
        "install_state": all_steps(),
    }

    if output_path is None:
        output_path = Path.home() / "homecloud-recovery-bundle.json"
    output_path.write_text(json.dumps(bundle, indent=2))
    try:
        os.chmod(output_path, 0o600)
    except PermissionError:
        pass
    log.info("recovery bundle written to %s", output_path)
    return output_path


def import_recovery_bundle(path: Path) -> Config:
    """Import a recovery bundle and write it to .env."""
    bundle = json.loads(path.read_text())
    cfg_data = bundle.get("config", {})
    cfg = Config(**{k: v for k, v in cfg_data.items() if not k.startswith("_")})
    save_config(cfg)
    log.info("recovery bundle imported from %s", path)
    return cfg
