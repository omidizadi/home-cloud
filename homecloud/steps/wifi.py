"""Step 7: WiFi connection (optional, via NetworkManager)."""

from __future__ import annotations

from ..utils import run
from .base import Step, StepResult


class WifiStep(Step):
    name = "wifi"
    label = "Connect to WiFi"
    description = "Connect the Pi to WiFi via NetworkManager (optional)"
    depends_on: list[str] = []

    def run(self) -> StepResult:
        ssid = self.cfg.wifi_ssid
        pw = self.cfg.wifi_password
        if not ssid:
            self.log("WiFi not configured — skipping (Ethernet only)")
            self.mark_done({"enabled": False})
            return StepResult(self.name, True, "Skipped (no WiFi configured)")

        self.log(f"Connecting to WiFi '{ssid}'...")
        r = run(
            f'nmcli dev wifi connect "{ssid}" password "{pw}"',
            sudo=True, dry_run=self.dry_run, capture=True,
        )
        if not r.ok and not self.dry_run:
            return StepResult(self.name, False, f"WiFi connect failed: {r.stderr}", r.stderr)

        # Verify
        if not self.dry_run:
            r = run("nmcli -t -f NAME,TYPE con show --active", capture=True)
            if "wireless" in r.stdout:
                self.log("WiFi connected")
            else:
                return StepResult(self.name, False, "WiFi connection not active")

        self.mark_done({"ssid": ssid, "enabled": True})
        return StepResult(
            self.name, True,
            f"Connected to WiFi '{ssid}'",
            "Tip: assign a static IP in your router's DHCP settings (bind by MAC).",
        )

    def status(self) -> StepResult:
        if self.dry_run:
            return StepResult(self.name, True, "[dry-run]")
        r = run("nmcli -t -f TYPE,STATE dev status", capture=True)
        if "wifi:connected" in r.stdout:
            return StepResult(self.name, True, "WiFi connected")
        if not self.cfg.wifi_ssid:
            return StepResult(self.name, True, "WiFi not configured (Ethernet only)")
        return StepResult(self.name, False, "WiFi not connected")

    def undo(self) -> StepResult:
        if not self.cfg.wifi_ssid:
            return StepResult(self.name, True, "Nothing to undo (WiFi was not configured)")
        self.log(f"Removing WiFi connection '{self.cfg.wifi_ssid}'")
        run(f'nmcli con delete "{self.cfg.wifi_ssid}"', sudo=True, dry_run=self.dry_run)
        self.mark_undone()
        return StepResult(self.name, True, "WiFi connection removed")
