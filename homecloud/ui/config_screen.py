"""Configuration screen — collect all user inputs via TUI forms."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label

from ..config import Config, generate_password, save_config, validate
from ..utils import run


class ConfigScreen(Screen):
    DEFAULT_CSS = """
    ConfigScreen {
        align: center middle;
    }
    ConfigScreen ScrollableContainer {
        width: 80;
        height: 80%;
        padding: 1 2;
        border: round $primary;
    }
    ConfigScreen .section {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }
    ConfigScreen Input {
        margin-bottom: 1;
    }
    ConfigScreen .actions {
        dock: bottom;
        height: 3;
        align: center middle;
    }
    ConfigScreen .actions Button {
        margin: 0 1;
    }
    """

    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with ScrollableContainer():
            cfg = self.app.cfg

            yield Label("⚙️  Configuration", id="title", classes="section")

            yield Label("💾 SSD", classes="section")
            yield self._auto_detect_label()
            yield Input(placeholder="SSD device (e.g. /dev/sda)", id="ssd_device", value=cfg.ssd_device)

            yield Label("🌐 DuckDNS", classes="section")
            yield Input(placeholder="DuckDNS subdomain (e.g. omid)", id="duckdns_domain", value=cfg.duckdns_domain)
            yield Input(placeholder="DuckDNS token", id="duckdns_token", value=cfg.duckdns_token, password=True)

            yield Label("☁️ AWS S3", classes="section")
            yield Input(placeholder="AWS Access Key ID", id="aws_access_key_id", value=cfg.aws_access_key_id)
            yield Input(placeholder="AWS Secret Access Key", id="aws_secret_access_key", value=cfg.aws_secret_access_key, password=True)
            yield Input(placeholder="S3 bucket name", id="s3_bucket", value=cfg.s3_bucket)
            yield Input(placeholder="S3 region (default: eu-central-1)", id="s3_region", value=cfg.s3_region or "eu-central-1")

            yield Label("🔐 restic", classes="section")
            yield Input(placeholder="restic password (leave blank to generate)", id="restic_password", value=cfg.restic_password, password=True)

            yield Label("✈️ Telegram", classes="section")
            yield Input(placeholder="Bot token (123:ABC...)", id="telegram_bot_token", value=cfg.telegram_bot_token)
            yield Input(placeholder="Chat ID", id="telegram_chat_id", value=cfg.telegram_chat_id)

            yield Label("☁️ Nextcloud", classes="section")
            yield Input(placeholder="Admin password", id="nextcloud_admin_password", value=cfg.nextcloud_admin_password, password=True)

            yield Label("📁 Samba", classes="section")
            yield Input(placeholder="Samba username", id="samba_user", value=cfg.samba_user)
            yield Input(placeholder="Samba password", id="samba_password", value=cfg.samba_password, password=True)

            yield Label("📶 WiFi (optional)", classes="section")
            yield Input(placeholder="WiFi SSID (leave blank for Ethernet)", id="wifi_ssid", value=cfg.wifi_ssid)
            yield Input(placeholder="WiFi password", id="wifi_password", value=cfg.wifi_password, password=True)

            yield Label("🕐 Misc", classes="section")
            yield Input(placeholder="Timezone (default: Europe/Berlin)", id="timezone", value=cfg.timezone or "Europe/Berlin")

        with Container(classes="actions"):
            yield Button("💾 Save", id="btn-save", variant="primary")
            yield Button("🎲 Generate Passwords", id="btn-gen", variant="default")
            yield Button("↩️ Back", id="btn-back", variant="default")

        yield Footer()

    def _auto_detect_label(self) -> Label:
        """Show detected block devices to help the user pick the SSD."""
        if self.app.dry_run:
            return Label("[dry-run] device detection skipped", classes="hint")
        r = run("lsblk -dln -o NAME,SIZE,TYPE,MODEL", capture=True)
        if r.ok:
            lines = r.stdout.strip().splitlines()
            text = "Detected devices:\n" + "\n".join(f"  /dev/{ln}" for ln in lines[:10])
        else:
            text = "Could not detect devices"
        return Label(text, classes="hint")

    def _collect_config(self) -> Config:
        cfg = self.app.cfg
        fields_map = {
            "ssd_device": "ssd_device",
            "duckdns_domain": "duckdns_domain",
            "duckdns_token": "duckdns_token",
            "aws_access_key_id": "aws_access_key_id",
            "aws_secret_access_key": "aws_secret_access_key",
            "s3_bucket": "s3_bucket",
            "s3_region": "s3_region",
            "restic_password": "restic_password",
            "telegram_bot_token": "telegram_bot_token",
            "telegram_chat_id": "telegram_chat_id",
            "nextcloud_admin_password": "nextcloud_admin_password",
            "samba_user": "samba_user",
            "samba_password": "samba_password",
            "wifi_ssid": "wifi_ssid",
            "wifi_password": "wifi_password",
            "timezone": "timezone",
        }
        for widget_id, attr in fields_map.items():
            val = self.query_one(f"#{widget_id}", Input).value.strip()
            if val:
                setattr(cfg, attr, val)
        return cfg

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-save":
            cfg = self._collect_config()
            # Generate restic password if empty
            if not cfg.restic_password:
                cfg.restic_password = generate_password()
                self.query_one("#restic_password", Input).value = cfg.restic_password
            errors = validate(cfg)
            if errors:
                self.app.notify("\n".join(errors), title="Validation errors", severity="error")
                return
            save_config(cfg, dry_run=self.app.dry_run)
            self.app.cfg = cfg
            self.app.notify("Configuration saved ✅", severity="information")
            self.app.pop_screen()
        elif bid == "btn-gen":
            pw = generate_password()
            self.query_one("#restic_password", Input).value = pw
            self.query_one("#nextcloud_admin_password", Input).value = generate_password(20)
            self.query_one("#samba_password", Input).value = generate_password(20)
            self.app.notify("Generated strong passwords", severity="information")
        elif bid == "btn-back":
            self.app.pop_screen()
