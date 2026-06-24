"""Step: Install Tailscale for external access (bypasses DS-Lite / CGNAT).

Tailscale creates a WireGuard mesh VPN. Every device that installs the
Tailscale client gets a stable `100.x.y.z` IP and can reach the Pi without
any port forwarding. This is the recommended way to expose Nextcloud when
the ISP assigns a DS-Lite / CGNAT IPv4 (no real public IPv4).

The Pi runs `tailscaled` + authenticates with an auth key (pre-generated
from https://login.tailscale.com/admin/settings/keys). Once up, the Pi is
reachable at `http://<pi-tailscale-ip>` from any device on the tailnet.
"""

from __future__ import annotations

from ..services import unit_status
from ..utils import run, which
from .base import Step, StepResult

# Tailscale's official install script
TAILSCALE_INSTALL_URL = "https://tailscale.com/install.sh"


class TailscaleStep(Step):
    name = "tailscale"
    label = "Install Tailscale"
    description = (
        "Install Tailscale for external access (bypasses DS-Lite / CGNAT). "
        "No port forwarding needed."
    )
    depends_on = ["docker"]  # needs network + apt; docker is a safe anchor

    def run(self) -> StepResult:
        auth_key = self.cfg.tailscale_auth_key

        # 1. Install the Tailscale binary if missing
        if which("tailscale") and not self.dry_run:
            self.log("Tailscale already installed")
        else:
            self.log("Installing Tailscale...")
            r = run(
                f"curl -fsSL {TAILSCALE_INSTALL_URL} | sh",
                sudo=True, dry_run=self.dry_run, timeout=180,
            )
            if not r.ok and not self.dry_run:
                return StepResult(
                    self.name, False,
                    f"Tailscale install failed: {r.stderr}",
                    r.stderr,
                )

        # 2. Enable + start the daemon
        run("systemctl enable tailscaled", sudo=True, dry_run=self.dry_run)
        run("systemctl start tailscaled", sudo=True, dry_run=self.dry_run)

        # 3. Authenticate
        if self.dry_run:
            self.log("[dry-run] would run: tailscale up --accept-routes --ssh")
            self.mark_done({"hostname": "homecloud", "ip": "100.x.y.z (dry-run)"})
            return StepResult(self.name, True, "[dry-run] Tailscale installed")

        # Check if already authenticated
        r = run("tailscale status", sudo=True, capture=True)
        if r.ok and "logged out" not in r.stdout.lower() and r.stdout.strip():
            self.log("Tailscale already authenticated")
        else:
            self.log("Authenticating with Tailscale...")
            up_cmd = (
                "tailscale up "
                "--hostname=homecloud "
                "--accept-routes "
                "--accept-dns=false "
                "--ssh"
            )
            if auth_key:
                # Non-interactive auth with a pre-generated key
                up_cmd = f"{up_cmd} --auth-key={auth_key}"
                r = run(up_cmd, sudo=True, capture=True, timeout=60)
                if not r.ok:
                    return StepResult(
                        self.name, False,
                        f"Tailscale auth failed: {r.stderr}",
                        (
                            "The auth key may be expired or invalid.\n"
                            "Generate a new one at:\n"
                            "  https://login.tailscale.com/admin/settings/keys\n"
                            "Then update config: TAILSCALE_AUTH_KEY=tskey-...\n"
                            "Or run interactively on the Pi:\n"
                            "  sudo tailscale up --hostname=homecloud --accept-routes --ssh"
                        ),
                    )
            else:
                # Interactive — print the URL the user must visit
                r = run(up_cmd, sudo=True, capture=True, timeout=30)
                # tailscale up prints a login URL to stderr/stdout when not authed
                url = self._extract_login_url(r.stdout + r.stderr)
                if url:
                    return StepResult(
                        self.name, False,
                        "Tailscale needs interactive login",
                        (
                            f"Open this URL in your browser to authorize the Pi:\n"
                            f"  {url}\n\n"
                            "After authorizing, re-run this step or run on the Pi:\n"
                            "  sudo tailscale up --hostname=homecloud --accept-routes --ssh\n\n"
                            "Tip: to make this non-interactive, generate an auth key at\n"
                            "  https://login.tailscale.com/admin/settings/keys\n"
                            "and set TAILSCALE_AUTH_KEY in the config."
                        ),
                    )
                if not r.ok:
                    return StepResult(
                        self.name, False,
                        f"Tailscale up failed: {r.stderr}",
                        r.stderr,
                    )

        # 4. Fetch the Tailscale IP
        ts_ip = self._tailscale_ip()
        ts_hostname = self._tailscale_name() or "homecloud"

        self.mark_done({"ip": ts_ip, "hostname": ts_hostname})
        return StepResult(
            self.name, True,
            f"Tailscale up — Pi reachable at http://{ts_ip}",
            (
                "Tailscale is running. The Pi is now reachable from any device\n"
                "on your tailnet (devices with Tailscale installed & logged in).\n\n"
                f"  Nextcloud:  https://{ts_ip}\n"
                f"  AIO panel:  https://{ts_ip}:8080\n\n"
                "Install the Tailscale client on your phone/laptop:\n"
                "  https://tailscale.com/download\n"
                "Log in with the same account you used for the Pi.\n\n"
                "No port forwarding needed — Tailscale punches through NAT/DS-Lite."
            ),
        )

    def status(self) -> StepResult:
        if self.dry_run:
            return StepResult(self.name, True, "[dry-run]")
        if not which("tailscale"):
            return StepResult(self.name, False, "tailscale binary not found")
        st = unit_status("tailscaled")
        if st != "active":
            return StepResult(self.name, False, f"tailscaled: {st}")
        r = run("tailscale status", sudo=True, capture=True)
        if not r.ok or "logged out" in r.stdout.lower():
            return StepResult(self.name, False, "Tailscale not authenticated")
        ts_ip = self._tailscale_ip()
        return StepResult(self.name, True, f"Connected — IP: {ts_ip}")

    def repair(self) -> StepResult:
        self.log("Restarting tailscaled...")
        run("systemctl restart tailscaled", sudo=True, dry_run=self.dry_run)
        return self.status()

    def undo(self) -> StepResult:
        self.log("Conservative undo: logging out + disabling Tailscale (binary kept)")
        run("tailscale down", sudo=True, dry_run=self.dry_run)
        run("tailscale logout", sudo=True, dry_run=self.dry_run, capture=True)
        run("systemctl stop tailscaled", sudo=True, dry_run=self.dry_run)
        run("systemctl disable tailscaled", sudo=True, dry_run=self.dry_run)
        self.mark_undone()
        return StepResult(self.name, True, "Tailscale logged out + disabled (binary kept)")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _tailscale_ip(self) -> str:
        r = run("tailscale ip -4", sudo=True, capture=True)
        ip = r.stdout.strip().splitlines()[0] if r.ok and r.stdout.strip() else "unknown"
        return ip

    def _tailscale_name(self) -> str:
        r = run("tailscale status --json", sudo=True, capture=True)
        if not r.ok:
            return ""
        import json
        try:
            data = json.loads(r.stdout)
            return data.get("Self", {}).get("HostName", "")
        except (json.JSONDecodeError, KeyError):
            return ""

    def _extract_login_url(self, output: str) -> str:
        """Extract the https://login.tailscale.com/... URL from tailscale up output."""
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("https://login.tailscale.com"):
                return line
        return ""
