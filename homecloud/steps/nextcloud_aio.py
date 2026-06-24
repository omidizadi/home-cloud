"""Step 3: Launch Nextcloud AIO master container.

AIO runs behind Tailscale Serve, which terminates TLS with a valid cert for
``https://<pi>.<tailnet>.ts.net`` and forwards plain HTTP to AIO's Apache
container on :11000. This works on DS-Lite / CGNAT (no public IPv4, no port
forwarding) because Tailscale issues the cert via DNS-01 over its own mesh.

AIO's built-in Let's Encrypt (TLS-ALPN-01 on :443) is *not* used: on CGNAT the
challenge always times out and Caddy refuses to serve any TLS handshake, so
Nextcloud becomes unreachable on every address (domain, Tailscale IP, LAN IP).
"""

from __future__ import annotations

import json
import time

from ..constants import (
    AIO_ADMIN_PORT,
    AIO_APACHE_PORT,
    AIO_MASTER_CONTAINER,
    NEXTCLOUD_DATADIR,
)
from ..services import container_status, remove_container
from ..utils import run, which
from .base import Step, StepResult

# Nextcloud container name (created by the mastercontainer, not by us)
AIO_NEXTCLOUD_CONTAINER = "nextcloud-aio-nextcloud"


class NextcloudAioStep(Step):
    name = "nextcloud_aio"
    label = "Install Nextcloud AIO"
    description = "Launch Nextcloud AIO behind Tailscale Serve (no port forwarding)"
    # Tailscale must be up first: we need the tailnet hostname for the cert
    # and `tailscale serve` to terminate TLS in front of AIO.
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

        # Remove existing master container so we can re-create with the
        # reverse-proxy env vars (AIO does not let you change these after start).
        if container_status(AIO_MASTER_CONTAINER) != "not-found" and not self.dry_run:
            self.log("Removing existing AIO master container to re-create with reverse-proxy config...")
            remove_container(AIO_MASTER_CONTAINER, dry_run=self.dry_run)

        cmd = (
            "docker run -d "
            "--init "
            "--sig-proxy=false "
            f"--name {AIO_MASTER_CONTAINER} "
            "--restart always "
            f"--publish {AIO_ADMIN_PORT}:{AIO_ADMIN_PORT} "
            "--volume nextcloud_aio_mastercontainer:/mnt/docker-aio-config "
            "--volume /var/run/docker.sock:/var/run/docker.sock:ro "
            f'-e NEXTCLOUD_DATADIR="{NEXTCLOUD_DATADIR}" '
            "-e SKIP_DOMAIN_VALIDATION=true "
            # Reverse-proxy mode: AIO's Apache listens on :11000 in plain HTTP.
            # Tailscale Serve terminates TLS and forwards here. AIO's built-in
            # Let's Encrypt (TLS-ALPN-01 on :443) is not used — it cannot work
            # behind CGNAT and would leave Nextcloud without any cert.
            f"-e APACHE_PORT={AIO_APACHE_PORT} "
            "-e APACHE_IP_BINDING=0.0.0.0 "
            "ghcr.io/nextcloud-releases/all-in-one:latest"
        )
        self.log("Launching Nextcloud AIO master container (reverse-proxy mode)...")
        r = run(cmd, sudo=True, dry_run=self.dry_run, timeout=120)
        if not r.ok and not self.dry_run:
            return StepResult(self.name, False, f"AIO launch failed: {r.stderr}", r.stderr)

        # Wait for AIO admin panel to be reachable
        if not self.dry_run:
            self.log("Waiting for AIO admin panel to be reachable...")
            for _ in range(30):
                if run(f"curl -sk https://localhost:{AIO_ADMIN_PORT}", capture=True).ok:
                    break
                time.sleep(2)
            else:
                return StepResult(
                    self.name, False, f"AIO admin panel not reachable on :{AIO_ADMIN_PORT}"
                )

        self.mark_done({
            "admin_port": AIO_ADMIN_PORT,
            "apache_port": AIO_APACHE_PORT,
            "datadir": str(NEXTCLOUD_DATADIR),
            "tailnet_fqdn": ts_fqdn,
        })
        return StepResult(
            self.name, True,
            f"AIO master container running. Open https://{ts_fqdn}:{AIO_ADMIN_PORT} to complete setup.",
            "OPEN THE AIO PANEL IN YOUR BROWSER:\n"
            f"  1. Go to https://{ts_fqdn}:{AIO_ADMIN_PORT} (accept cert warning)\n"
            f"     or https://<pi-tailscale-ip>:{AIO_ADMIN_PORT}\n"
            f"  2. Enter domain: {ts_fqdn}\n"
            "     (Domain validation is auto-skipped — SKIP_DOMAIN_VALIDATION=true.)\n"
            "  3. Pick optional containers: Talk ✅, Collabora optional, skip ClamAV/FTS\n"
            "  4. Set the admin password\n"
            "  5. Click 'Start containers' (takes 5-10 min on a Pi)\n"
            "  6. Once containers are up, run the *repair* action of this step\n"
            "     to wire Tailscale Serve → AIO and fix trusted_domains.\n"
            "     Nextcloud will then be live at:\n"
            f"       https://{ts_fqdn}\n"
            "     (reachable from any device on your tailnet — no port forwarding)",
        )

    # ── status ──────────────────────────────────────────────────────────────

    def status(self) -> StepResult:
        if self.dry_run:
            return StepResult(self.name, True, "[dry-run]")
        st = container_status(AIO_MASTER_CONTAINER)
        if st != "running":
            return StepResult(self.name, False, f"Master container: {st}")
        nc_st = container_status(AIO_NEXTCLOUD_CONTAINER)
        ts_fqdn = self._tailscale_fqdn()
        serve_ok = self._serve_configured()
        url = f"https://{ts_fqdn}" if ts_fqdn else "https://<pi>.<tailnet>.ts.net"
        msg = f"Master: running | Nextcloud: {nc_st} | Serve: {'✅' if serve_ok else '❌ (run repair)'}"
        return StepResult(self.name, True, msg, f"Nextcloud URL: {url}" if serve_ok else "")

    # ── repair ───────────────────────────────────────────────────────────────
    #
    # This is the heart of the CGNAT fix. It:
    #   1. Ensures the mastercontainer runs with APACHE_PORT=11000 (reverse-proxy
    #      mode). If it was launched the old way (APACHE_PORT=443 + Let's
    #      Encrypt), it is recreated with the correct env.
    #   2. Configures `tailscale serve` to terminate TLS on :443 and forward to
    #      AIO's Apache on :11000. Tailscale obtains the cert via DNS-01, which
    #      works on CGNAT.
    #   3. Points Nextcloud's trusted_domains / overwritehost at the tailnet
    #      hostname so the web UI stops redirecting to the unreachable DuckDNS
    #      domain.
    #   4. Verifies Nextcloud answers over HTTPS.

    def repair(self) -> StepResult:
        ts_fqdn = self._tailscale_fqdn()
        if not ts_fqdn:
            return StepResult(
                self.name, False,
                "Tailscale not ready — cannot repair",
                "Run the Tailscale step first (it must be up and authenticated).",
            )

        # 1. Ensure mastercontainer is in reverse-proxy mode.
        if not self._master_uses_reverse_proxy():
            self.log("Mastercontainer not in reverse-proxy mode — recreating with APACHE_PORT=11000...")
            if not self.dry_run:
                remove_container(AIO_MASTER_CONTAINER, dry_run=self.dry_run)
            res = self.run()
            if not res.success:
                return res

        # 2. Wire Tailscale Serve → AIO Apache (:11000).
        self.log("Configuring Tailscale Serve (https://<tailnet> → http://127.0.0.1:11000)...")
        if not self.dry_run:
            # Reset any previous serve config, then publish HTTPS on :443.
            run("tailscale serve reset", sudo=True, capture=True)
            r = run(
                f"tailscale serve --bg --https=443 http://127.0.0.1:{AIO_APACHE_PORT}",
                sudo=True, capture=True, timeout=60,
            )
            if not r.ok:
                return StepResult(
                    self.name, False,
                    "Tailscale Serve failed to start",
                    r.stderr or r.stdout,
                )

        # 3. Point Nextcloud at the tailnet hostname.
        if not self.dry_run and container_status(AIO_NEXTCLOUD_CONTAINER) == "running":
            self.log(f"Setting trusted_domains / overwritehost to {ts_fqdn}...")
            occ = f"docker exec --user www-data {AIO_NEXTCLOUD_CONTAINER} php occ"
            run(f"{occ} config:system:set trusted_domains 1 --value={ts_fqdn}", sudo=True, capture=True)
            run(f"{occ} config:system:set trusted_domains 2 --value=100.64.0.0/10", sudo=True, capture=True)
            run(f"{occ} config:system:set overwrite.cli.url --value=https://{ts_fqdn}/", sudo=True, capture=True)
            run(f"{occ} config:system:set overwritehost --value={ts_fqdn}", sudo=True, capture=True)
            run(f"{occ} config:system:set trusted_proxies 2 --value=127.0.0.1", sudo=True, capture=True)
            run(f"{occ} config:system:set trusted_proxies 3 --value=100.64.0.0/10", sudo=True, capture=True)

        # 4. Verify.
        if not self.dry_run:
            self.log("Verifying Nextcloud is reachable over Tailscale HTTPS...")
            time.sleep(5)  # let Caddy pick up the new config
            r = run(f"curl -sk --max-time 10 -o /dev/null -w '%{{http_code}}' https://{ts_fqdn}",
                    capture=True)
            code = r.stdout.strip()
            if r.ok and code in ("200", "302", "303"):
                return StepResult(
                    self.name, True,
                    f"Nextcloud live at https://{ts_fqdn} (HTTP {code})",
                    "Tailscale Serve is terminating TLS and forwarding to AIO.\n"
                    "Open https://" + ts_fqdn + " from any device on your tailnet.\n"
                    "No port forwarding / DuckDNS domain needed for access.",
                )
            return StepResult(
                self.name, False,
                f"Nextcloud not reachable over HTTPS (HTTP {code})",
                "Tailscale Serve is configured but Nextcloud did not answer.\n"
                "Check: sudo tailscale serve status\n"
                "       sudo docker ps | grep nextcloud-aio\n"
                "       sudo docker logs --tail 20 nextcloud-aio-apache",
            )

        return StepResult(self.name, True, "[dry-run] repair complete")

    # ── undo ─────────────────────────────────────────────────────────────────

    def undo(self) -> StepResult:
        self.log("Conservative undo: stopping AIO containers (data on SSD preserved)")
        # Release :443 back to AIO's Caddy if we were serving.
        if which("tailscale"):
            run("tailscale serve reset", sudo=True, dry_run=self.dry_run, capture=True)
        for c in [
            AIO_MASTER_CONTAINER,
            AIO_NEXTCLOUD_CONTAINER,
            "nextcloud-aio-apache",
            "nextcloud-aio-database",
            "nextcloud-aio-redis",
            "nextcloud-aio-notify-push",
            "nextcloud-aio-talk",
            "nextcloud-aio-talk-recording",
            "nextcloud-aio-borgbackup",
            "nextcloud-aio-watchtower",
            "nextcloud-aio-domaincheck",
            "nextcloud-aio-collabora",
            "nextcloud-aio-imaginary",
            "nextcloud-aio-clamav",
            "nextcloud-aio-fulltextsearch",
        ]:
            run(f"docker stop {c}", sudo=True, dry_run=self.dry_run)
            run(f"docker rm -f {c}", sudo=True, dry_run=self.dry_run)
        # Remove the master volume (config only, not user data)
        run("docker volume rm nextcloud_aio_mastercontainer", sudo=True, dry_run=self.dry_run)
        self.mark_undone()
        return StepResult(self.name, True, "AIO containers removed (user data on SSD preserved)")

    # ── helpers ──────────────────────────────────────────────────────────────

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

    def _master_uses_reverse_proxy(self) -> bool:
        """True if the mastercontainer was launched with APACHE_PORT != 443."""
        if self.dry_run:
            return True
        r = run(
            f"docker inspect {AIO_MASTER_CONTAINER} "
            "--format='{{range .Config.Env}}{{println .}}{{end}}'",
            sudo=True, capture=True,
        )
        if not r.ok:
            return False
        for line in r.stdout.splitlines():
            if line.startswith("APACHE_PORT="):
                return line.split("=", 1)[1].strip() != "443"
        # No APACHE_PORT set → AIO defaults to 443 (integrated mode).
        return False

    def _serve_configured(self) -> bool:
        """True if `tailscale serve` is forwarding :443 to AIO's Apache."""
        if self.dry_run or not which("tailscale"):
            return True
        r = run("tailscale serve status --json", sudo=True, capture=True)
        if not r.ok:
            return False
        try:
            data = json.loads(r.stdout or "{}")
        except json.JSONDecodeError:
            return False
        # Config shape: {"tcp": {"443": {"https": true, "handle": [{"proxy": "http://127.0.0.1:11000"}]}}}
        tcp = data.get("tcp", {})
        return "443" in tcp
