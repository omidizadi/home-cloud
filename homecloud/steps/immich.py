"""Step 3: Launch the Immich stack (server + ML + redis + postgres).

Immich runs behind Tailscale Serve, which terminates TLS with a valid cert
for ``https://<pi>.<tailnet>.ts.net`` and forwards plain HTTP to the Immich
web server on :2283. This works on DS-Lite / CGNAT (no public IPv4, no port
forwarding) because Tailscale issues the cert via DNS-01 over its own mesh.

Immich ships as a docker-compose stack (not a single container like Nextcloud
AIO), so this step renders the compose file + .env from Jinja2 templates and
runs ``docker compose up -d``. No occ, no trusted_domains, no AIO web API —
much simpler than the old NextcloudAioStep.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..constants import (
    IMMICH_COMPOSE_DIR,
    IMMICH_DATADIR,
    IMMICH_WEB_PORT,
)
from ..services import container_status
from ..utils import run, which, write_file_sudo
from .base import Step, StepResult


class ImmichStep(Step):
    name = "immich"
    label = "Install Immich"
    description = "Launch Immich (server + ML + redis + postgres) behind Tailscale Serve"
    # Tailscale must be up first: we need the tailnet hostname for the cert
    # and `tailscale serve` to terminate TLS in front of Immich.
    depends_on = ["docker", "tailscale"]

    # ── run ────────────────────────────────────────────────────────────────

    def run(self) -> StepResult:
        ts_fqdn = self._tailscale_fqdn()
        if not ts_fqdn:
            return StepResult(
                self.name, False,
                "Tailscale not ready — cannot determine tailnet hostname",
                "Tailscale Serve needs the Pi on the tailnet to issue a cert.\n"
                "Run the Tailscale step first, then re-run this step.",
            )

        # Store the tailnet hostname in config so other steps (bot, etc.) can use it.
        self.cfg.immich_domain = ts_fqdn

        # Create data subdirectories on the SSD. Immich containers manage
        # their own file perms, so root:root is fine here.
        self.log(f"Creating data directories under {IMMICH_DATADIR}...")
        for sub in ["uploads", "library", "encoded-video", "profile", "thumbs"]:
            run(f"mkdir -p {IMMICH_DATADIR / sub}", sudo=True, dry_run=self.dry_run)

        # Render compose + .env from templates.
        self.log("Rendering Immich docker-compose.yml + .env...")
        self._render_compose()

        # Launch the stack.
        self.log("Starting Immich stack (docker compose up -d)...")
        r = run(
            f"docker compose -f {IMMICH_COMPOSE_DIR / 'docker-compose.yml'} up -d",
            sudo=True, dry_run=self.dry_run, timeout=300,
        )
        if not r.ok and not self.dry_run:
            # If postgres is in a crash loop (stale/corrupt pgdata from a
            # previous failed attempt), wipe pgdata and retry.  This is safe
            # during initial install because there is no user data yet.
            if self._pgdata_corrupt(r.stderr):
                self.log("Postgres crashed — wiping stale pgdata and retrying...")
                run(
                    f"docker compose -f {IMMICH_COMPOSE_DIR / 'docker-compose.yml'} down -v",
                    sudo=True, capture=True, timeout=60,
                )
                run(f"rm -rf {IMMICH_DATADIR / 'pgdata'}", sudo=True)
                run(f"mkdir -p {IMMICH_DATADIR / 'pgdata'}", sudo=True)
                r = run(
                    f"docker compose -f {IMMICH_COMPOSE_DIR / 'docker-compose.yml'} up -d",
                    sudo=True, dry_run=self.dry_run, timeout=300,
                )
            if not r.ok:
                return StepResult(self.name, False, f"docker compose up failed: {r.stderr}", r.stderr)

        # Wait for Immich web to be reachable.
        if not self.dry_run:
            self.log(f"Waiting for Immich web on :{IMMICH_WEB_PORT}...")
            if not self._wait_for_port(IMMICH_WEB_PORT, timeout=120):
                return StepResult(
                    self.name, False,
                    f"Immich web did not come up on :{IMMICH_WEB_PORT}",
                    f"Check: sudo docker compose -f {IMMICH_COMPOSE_DIR / 'docker-compose.yml'} logs",
                )

        # Wire Tailscale Serve → Immich web (:2283).
        self.log(f"Configuring Tailscale Serve (https://<tailnet> → http://127.0.0.1:{IMMICH_WEB_PORT})...")
        if not self.dry_run:
            run("tailscale serve reset", sudo=True, capture=True)
            r = run(
                f"tailscale serve --bg --https=443 http://127.0.0.1:{IMMICH_WEB_PORT}",
                sudo=True, capture=True, timeout=60,
            )
            if not r.ok:
                return StepResult(
                    self.name, False,
                    "Tailscale Serve failed to start",
                    r.stderr or r.stdout,
                )

        self.mark_done({
            "web_port": IMMICH_WEB_PORT,
            "datadir": str(IMMICH_DATADIR),
            "tailnet_fqdn": ts_fqdn,
        })
        return StepResult(
            self.name, True,
            f"Immich running. Open https://{ts_fqdn} to create your admin account.",
            "OPEN IMMICH IN YOUR BROWSER:\n"
            f"  1. Go to https://{ts_fqdn}\n"
            f"     (or https://<pi-tailscale-ip>)\n"
            "  2. Create your admin account\n"
            "  3. (For the Telegram bot) Settings → API Keys → New API key\n"
            "     Copy the key, then run `homecloud` → Edit Config → paste into immich_api_key.\n"
            "  4. The bot won't work until you've pasted the API key into config.\n"
            "  5. Immich is reachable from any device on your tailnet — no port forwarding.",
        )

    # ── status ──────────────────────────────────────────────────────────────

    def status(self) -> StepResult:
        if self.dry_run:
            return StepResult(self.name, True, "[dry-run]")
        st = container_status("immich-server")
        if st != "running":
            return StepResult(self.name, False, f"immich-server: {st}")
        ts_fqdn = self._tailscale_fqdn()
        serve_ok = self._serve_configured()
        url = f"https://{ts_fqdn}" if ts_fqdn else "https://<pi>.<tailnet>.ts.net"
        if not serve_ok:
            return StepResult(
                self.name, False,
                f"immich-server: running | Serve: ❌ (run repair)",
                f"Tailscale Serve not configured — Immich unreachable at {url}.\n"
                "Run the repair action to wire Tailscale Serve → Immich.",
            )
        web_ok = self._web_responds()
        if not web_ok:
            return StepResult(
                self.name, False,
                f"immich-server: running | Serve: ✅ | Web: ❌ (run repair)",
                f"Immich web not responding on :{IMMICH_WEB_PORT}.\n"
                "Run the repair action to restart the stack.",
            )
        return StepResult(
            self.name, True,
            f"immich-server: running | Serve: ✅ | Web: ✅",
            f"Immich URL: {url}",
        )

    # ── repair ───────────────────────────────────────────────────────────────

    def repair(self) -> StepResult:
        ts_fqdn = self._tailscale_fqdn()
        if not ts_fqdn:
            return StepResult(
                self.name, False,
                "Tailscale not ready — cannot repair",
                "Run the Tailscale step first (it must be up and authenticated).",
            )
        self.cfg.immich_domain = ts_fqdn

        # Re-render compose in case secrets/config changed.
        self.log("Re-rendering Immich docker-compose.yml + .env...")
        self._render_compose()

        # Restart the stack.
        self.log("Restarting Immich stack...")
        if not self.dry_run:
            r = run(
                f"docker compose -f {IMMICH_COMPOSE_DIR / 'docker-compose.yml'} up -d",
                sudo=True, capture=True, timeout=300,
            )
            if not r.ok:
                # Attempt pgdata recovery if postgres is in a crash loop.
                if self._pgdata_corrupt(r.stderr):
                    self.log("Postgres crashed — wiping stale pgdata and retrying...")
                    run(
                        f"docker compose -f {IMMICH_COMPOSE_DIR / 'docker-compose.yml'} down -v",
                        sudo=True, capture=True, timeout=60,
                    )
                    run(f"rm -rf {IMMICH_DATADIR / 'pgdata'}", sudo=True)
                    run(f"mkdir -p {IMMICH_DATADIR / 'pgdata'}", sudo=True)
                    r = run(
                        f"docker compose -f {IMMICH_COMPOSE_DIR / 'docker-compose.yml'} up -d",
                        sudo=True, capture=True, timeout=300,
                    )
                if not r.ok:
                    return StepResult(self.name, False, f"docker compose up failed: {r.stderr}", r.stderr)
            if not self._wait_for_port(IMMICH_WEB_PORT, timeout=120):
                return StepResult(self.name, False, f"Immich web did not come up on :{IMMICH_WEB_PORT}")

        # Re-wire Tailscale Serve.
        self.log(f"Configuring Tailscale Serve (https://<tailnet> → http://127.0.0.1:{IMMICH_WEB_PORT})...")
        if not self.dry_run:
            run("tailscale serve reset", sudo=True, capture=True)
            r = run(
                f"tailscale serve --bg --https=443 http://127.0.0.1:{IMMICH_WEB_PORT}",
                sudo=True, capture=True, timeout=60,
            )
            if not r.ok:
                return StepResult(self.name, False, "Tailscale Serve failed to start", r.stderr or r.stdout)

        # Verify over HTTPS. Use --resolve because the Pi runs with
        # --accept-dns=false and cannot resolve its own MagicDNS name via getent.
        if not self.dry_run:
            self.log("Verifying Immich is reachable over Tailscale HTTPS...")
            time.sleep(5)
            ts_ip = self._tailscale_ip()
            resolve_opt = f"--resolve {ts_fqdn}:443:{ts_ip}" if ts_ip else ""
            r = run(
                f"curl -sk --max-time 10 {resolve_opt} "
                f"-o /dev/null -w %{{http_code}} https://{ts_fqdn}",
                capture=True,
            )
            code = r.stdout.strip()
            if r.ok and code in ("200", "301", "302", "303"):
                return StepResult(
                    self.name, True,
                    f"Immich live at https://{ts_fqdn} (HTTP {code})",
                    "Tailscale Serve is terminating TLS and forwarding to Immich.\n"
                    f"Open https://{ts_fqdn} from any device on your tailnet.\n"
                    "No port forwarding needed for access.",
                )
            return StepResult(
                self.name, False,
                f"Immich not reachable over HTTPS (HTTP {code})",
                "Tailscale Serve is configured but Immich did not answer.\n"
                "Check: sudo tailscale serve status\n"
                "       sudo docker compose -f "
                f"{IMMICH_COMPOSE_DIR / 'docker-compose.yml'} ps",
            )

        return StepResult(self.name, True, "[dry-run] repair complete")

    # ── undo ─────────────────────────────────────────────────────────────────

    def undo(self) -> StepResult:
        self.log("Conservative undo: stopping Immich stack (data on SSD preserved)")
        if which("tailscale"):
            run("tailscale serve reset", sudo=True, dry_run=self.dry_run, capture=True)
        run(
            f"docker compose -f {IMMICH_COMPOSE_DIR / 'docker-compose.yml'} down -v",
            sudo=True, dry_run=self.dry_run, capture=True,
        )
        # Remove compose dir (on SD card) but preserve data on SSD.
        run(f"rm -rf {IMMICH_COMPOSE_DIR}", sudo=True, dry_run=self.dry_run, capture=True)
        self.mark_undone()
        return StepResult(self.name, True, "Immich stack removed (user data on SSD preserved)")

    # ── helpers ──────────────────────────────────────────────────────────────

    def _render_compose(self) -> None:
        """Render docker-compose.yml + .env from Jinja2 templates into IMMICH_COMPOSE_DIR."""
        from ..constants import TEMPLATES_DIR

        env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR / "immich")),
            autoescape=False,
            keep_trailing_newline=True,
        )
        ctx = {
            "immich_datadir": str(IMMICH_DATADIR),
            "immich_web_port": IMMICH_WEB_PORT,
            "db_password": self.cfg.immich_db_password,
            "jwt_secret": self.cfg.immich_jwt_secret,
            "upload_location": str(IMMICH_DATADIR / "uploads"),
            "timezone": self.cfg.timezone,
        }
        compose = env.get_template("docker-compose.yml.j2").render(**ctx)
        env_file = env.get_template("env.j2").render(**ctx)

        if self.dry_run:
            self.log(f"[dry-run] would write {IMMICH_COMPOSE_DIR / 'docker-compose.yml'}")
            self.log(f"[dry-run] would write {IMMICH_COMPOSE_DIR / '.env'}")
            return

        run(f"mkdir -p {IMMICH_COMPOSE_DIR}", sudo=True, capture=True)
        write_file_sudo(IMMICH_COMPOSE_DIR / "docker-compose.yml", compose, mode=0o644)
        write_file_sudo(IMMICH_COMPOSE_DIR / ".env", env_file, mode=0o600)

    def _tailscale_fqdn(self) -> str:
        """Return the Pi's tailnet FQDN, e.g. homecloud.tail665a7d.ts.net."""
        if self.dry_run or not which("tailscale"):
            return ""
        r = run("tailscale status --json", sudo=True, capture=True)
        if not r.ok:
            return ""
        try:
            data = json.loads(r.stdout)
            dns = data.get("Self", {}).get("DNSName", "")
            return dns.rstrip(".")
        except (json.JSONDecodeError, KeyError):
            return ""

    def _pgdata_corrupt(self, stderr: str) -> bool:
        """True if docker compose failed because postgres is in a crash loop."""
        return "is unhealthy" in stderr and "immich-postgres" in stderr

    def _serve_configured(self) -> bool:
        """True if `tailscale serve` is forwarding :443 to Immich's web port."""
        if self.dry_run or not which("tailscale"):
            return True
        r = run("tailscale serve status --json", sudo=True, capture=True)
        if not r.ok:
            return False
        try:
            data = json.loads(r.stdout or "{}")
        except json.JSONDecodeError:
            return False
        tcp = data.get("TCP") or data.get("tcp") or {}
        return "443" in tcp

    def _tailscale_ip(self) -> str:
        """Return the Pi's Tailscale IPv4, or empty string."""
        if self.dry_run or not which("tailscale"):
            return ""
        r = run("tailscale ip -4", sudo=True, capture=True)
        return r.stdout.strip().splitlines()[0] if r.ok and r.stdout.strip() else ""

    def _wait_for_port(self, port: int, *, timeout: int = 60) -> bool:
        """Wait until something is listening on the given port."""
        for _ in range(timeout // 3):
            r = run(f"curl -s --max-time 3 -o /dev/null http://127.0.0.1:{port}", capture=True)
            if r.ok or r.returncode == 52:  # 52 = empty reply = port open
                return True
            time.sleep(3)
        return False

    def _web_responds(self) -> bool:
        """True if Immich web is listening on :IMMICH_WEB_PORT and answering."""
        if self.dry_run:
            return True
        r = run(
            f"curl -s --max-time 5 -o /dev/null http://127.0.0.1:{IMMICH_WEB_PORT}",
            capture=True,
        )
        return r.ok or r.returncode == 52
