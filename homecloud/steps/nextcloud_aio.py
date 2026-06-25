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
import os
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
        if not serve_ok:
            return StepResult(
                self.name, False,
                f"Master: running | Nextcloud: {nc_st} | Serve: ❌ (run repair)",
                f"Tailscale Serve not configured — Nextcloud unreachable at {url}.\n"
                "Run the repair action to wire Tailscale Serve → AIO.",
            )
        # Serve is configured, but is Apache actually listening on :11000 and
        # answering? If not, repair is needed (e.g. Apache still on :443 with
        # the old DuckDNS domain).
        apache_ok = self._apache_responds()
        if not apache_ok:
            return StepResult(
                self.name, False,
                f"Master: running | Nextcloud: {nc_st} | Serve: ✅ | Apache: ❌ (run repair)",
                f"Apache not responding on :{AIO_APACHE_PORT} — likely still on :443 with the old domain.\n"
                "Run the repair action to recreate Apache on :11000.",
            )
        return StepResult(
            self.name, True,
            f"Master: running | Nextcloud: {nc_st} | Serve: ✅ | Apache: ✅",
            f"Nextcloud URL: {url}",
        )

    # ── repair ───────────────────────────────────────────────────────────────
    #
    # This is the heart of the CGNAT fix. It:
    #   0. Updates AIO's stored domain to the tailnet hostname (so Caddy stops
    #      trying Let's Encrypt for the unreachable DuckDNS domain).
    #   1. Ensures the mastercontainer runs with APACHE_PORT=11000 (reverse-proxy
    #      mode). If it was launched the old way (APACHE_PORT=443 + Let's
    #      Encrypt), it is recreated with the correct env.
    #   2. Force-recreates the Apache container so the mastercontainer respawns it
    #      on :11000 with the new domain (the mastercontainer only re-reads its
    #      env/domain when Apache is absent).
    #   3. Configures `tailscale serve` to terminate TLS on :443 and forward to
    #      AIO's Apache on :11000. Tailscale obtains the cert via DNS-01, which
    #      works on CGNAT.
    #   4. Points Nextcloud's trusted_domains / overwritehost at the tailnet
    #      hostname so the web UI stops redirecting to the unreachable DuckDNS
    #      domain.
    #   5. Verifies Nextcloud answers over HTTPS.

    def repair(self) -> StepResult:
        ts_fqdn = self._tailscale_fqdn()
        if not ts_fqdn:
            return StepResult(
                self.name, False,
                "Tailscale not ready — cannot repair",
                "Run the Tailscale step first (it must be up and authenticated).",
            )

        # 0. Update AIO's stored domain so Caddy stops trying Let's Encrypt for
        #    the DuckDNS domain (which always times out on CGNAT).
        self._update_aio_domain(ts_fqdn)

        # 1. Ensure mastercontainer is in reverse-proxy mode.
        if not self._master_uses_reverse_proxy():
            self.log("Mastercontainer not in reverse-proxy mode — recreating with APACHE_PORT=11000...")
            if not self.dry_run:
                # Free :443 first: Tailscale Serve (if any) and the old Apache
                # container still bound to it. The mastercontainer will respawn
                # Apache on :11000 after we recreate it.
                run("tailscale serve reset", sudo=True, capture=True)
                run("docker stop nextcloud-aio-apache", sudo=True, capture=True)
                run("docker rm -f nextcloud-aio-apache", sudo=True, capture=True)
                remove_container(AIO_MASTER_CONTAINER, dry_run=self.dry_run)
            res = self.run()
            if not res.success:
                return res

        # 2. Force-recreate the Apache container via the AIO API. Simply
        #    restarting the mastercontainer does NOT respawn Apache — AIO only
        #    creates containers when triggered via its web API. We:
        #      a. Remove the old Apache (still on :443 with DuckDNS domain).
        #      b. Call POST /api/docker/start (auth via AIO_TOKEN + CSRF).
        #    The mastercontainer then recreates Apache on :11000 with the new
        #    domain from configuration.json.
        self.log("Force-recreating Apache container via AIO API...")
        if not self.dry_run:
            run("tailscale serve reset", sudo=True, capture=True)  # free :443
            run("docker stop nextcloud-aio-apache", sudo=True, capture=True)
            run("docker rm -f nextcloud-aio-apache", sudo=True, capture=True)
            if not self._aio_start_containers():
                return StepResult(
                    self.name, False,
                    "AIO API failed to start containers",
                    "Could not trigger container start via the AIO API.\n"
                    f"Check: sudo docker logs --tail 30 {AIO_MASTER_CONTAINER}",
                )
            # Wait for Apache to come up on :11000.
            if not self._wait_for_port(AIO_APACHE_PORT, timeout=120):
                return StepResult(
                    self.name, False,
                    f"Apache did not come up on :{AIO_APACHE_PORT}",
                    "The mastercontainer should respawn nextcloud-aio-apache.\n"
                    f"Check: sudo docker logs --tail 30 {AIO_MASTER_CONTAINER}",
                )

        # 3. Wire Tailscale Serve → AIO Apache (:11000).
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

        # 4. Point Nextcloud at the tailnet hostname.
        if not self.dry_run and container_status(AIO_NEXTCLOUD_CONTAINER) == "running":
            self.log(f"Setting trusted_domains / overwritehost to {ts_fqdn}...")
            occ = f"docker exec --user www-data {AIO_NEXTCLOUD_CONTAINER} php occ"
            run(f"{occ} config:system:set trusted_domains 1 --value={ts_fqdn}", sudo=True, capture=True)
            run(f"{occ} config:system:set trusted_domains 2 --value=100.64.0.0/10", sudo=True, capture=True)
            run(f"{occ} config:system:set overwrite.cli.url --value=https://{ts_fqdn}/", sudo=True, capture=True)
            run(f"{occ} config:system:set overwritehost --value={ts_fqdn}", sudo=True, capture=True)
            run(f"{occ} config:system:set trusted_proxies 2 --value=127.0.0.1", sudo=True, capture=True)
            run(f"{occ} config:system:set trusted_proxies 3 --value=100.64.0.0/10", sudo=True, capture=True)

        # 5. Verify. Use --resolve because the Pi runs with --accept-dns=false
        #    and cannot resolve its own MagicDNS name via getent.
        if not self.dry_run:
            self.log("Verifying Nextcloud is reachable over Tailscale HTTPS...")
            time.sleep(5)  # let Caddy pick up the new config
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
        """True if `tailscale serve` is forwarding :443 to AIO's Apache.

        Tailscale's JSON uses capitalized keys ("TCP", "Web", "Handlers",
        "Proxy"), not the lowercase ones the Go struct tags would suggest.
        """
        if self.dry_run or not which("tailscale"):
            return True
        r = run("tailscale serve status --json", sudo=True, capture=True)
        if not r.ok:
            return False
        try:
            data = json.loads(r.stdout or "{}")
        except json.JSONDecodeError:
            return False
        # Config shape:
        # {"TCP": {"443": {"HTTPS": true}},
        #  "Web": {"<fqdn>:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:11000"}}}}}
        tcp = data.get("TCP") or data.get("tcp") or {}
        return "443" in tcp

    def _tailscale_ip(self) -> str:
        """Return the Pi's Tailscale IPv4, or empty string."""
        if self.dry_run or not which("tailscale"):
            return ""
        r = run("tailscale ip -4", sudo=True, capture=True)
        return r.stdout.strip().splitlines()[0] if r.ok and r.stdout.strip() else ""

    def _update_aio_domain(self, new_domain: str) -> None:
        """Update the domain stored in AIO's configuration.json.

        AIO's Apache (Caddy) reads this to decide which hostname to obtain a
        cert for. If it still points at the DuckDNS domain, Caddy keeps trying
        (and failing) Let's Encrypt on CGNAT. We rewrite it to the tailnet
        hostname so Caddy stops the ACME attempts.
        """
        if self.dry_run:
            return
        # configuration.json lives in the mastercontainer volume, mounted at
        # /mnt/docker-aio-config inside the container. Edit it on the host via
        # the volume's mountpoint to avoid `docker exec` JSON-parsing quirks.
        r = run(
            "docker volume inspect nextcloud_aio_mastercontainer "
            "--format='{{.Mountpoint}}'",
            sudo=True, capture=True,
        )
        if not r.ok:
            self.log("Could not find mastercontainer volume — skipping domain update")
            return
        mp = r.stdout.strip()
        cfg_path = f"{mp}/data/configuration.json"
        # Read current JSON, update domain, write back.
        r = run(f"cat {cfg_path}", sudo=True, capture=True)
        if not r.ok:
            self.log("Could not read configuration.json — skipping domain update")
            return
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            self.log("configuration.json is not valid JSON — skipping domain update")
            return
        old = data.get("domain", "")
        if old == new_domain:
            return
        data["domain"] = new_domain
        # Write via a temp file + sudo install (we're not root).
        import tempfile
        fd, tmp = tempfile.mkstemp(prefix="homecloud-aio-cfg-")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
            run(f"install -m 644 -o root -g root {tmp} {cfg_path}", sudo=True, capture=True)
            self.log(f"Updated AIO domain: {old} → {new_domain}")
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def _wait_for_port(self, port: int, *, timeout: int = 60) -> bool:
        """Wait until something is listening on the given port."""
        for _ in range(timeout // 3):
            r = run(f"curl -s --max-time 3 -o /dev/null http://127.0.0.1:{port}",
                    capture=True)
            if r.ok or r.returncode == 52:  # 52 = empty reply = port open
                return True
            time.sleep(3)
        return False

    def _apache_responds(self) -> bool:
        """True if AIO's Apache is listening on :11000 and answering."""
        if self.dry_run:
            return True
        r = run(
            f"curl -s --max-time 5 -o /dev/null http://127.0.0.1:{AIO_APACHE_PORT}",
            capture=True,
        )
        return r.ok or r.returncode == 52

    def _aio_start_containers(self) -> bool:
        """Trigger AIO's container-start via its web API.

        AIO only creates/recreates containers when triggered via the API —
        restarting the mastercontainer alone does NOT respawn Apache. The flow:
          1. GET /api/auth/getlogin?token=<AIO_TOKEN>  (authenticates session)
          2. GET /containers                           (fetch CSRF token)
          3. POST /api/docker/stop                      (stop all containers)
          4. GET /containers + POST /api/docker/start   (recreate with new config)

        The stop+start is necessary because AIO sets OVERWRITEHOST and other
        env vars from configuration.json when it *creates* the Nextcloud
        container — simply starting an existing container won't pick up the
        new domain.
        """
        import re as _re
        import tempfile as _tempfile

        # Read AIO_TOKEN from configuration.json on the host.
        r = run(
            "docker volume inspect nextcloud_aio_mastercontainer "
            "--format='{{.Mountpoint}}'",
            sudo=True, capture=True,
        )
        if not r.ok:
            return False
        cfg_path = f"{r.stdout.strip()}/data/configuration.json"
        r = run(f"cat {cfg_path}", sudo=True, capture=True)
        if not r.ok:
            return False
        try:
            aio_token = json.loads(r.stdout).get("AIO_TOKEN", "")
        except json.JSONDecodeError:
            return False
        if not aio_token:
            return False

        cookie_file = _tempfile.mkstemp(prefix="aio-cookies-")[1]

        def _get_csrf() -> tuple[str, str] | tuple[None, None]:
            r = run(
                f"curl -sk -b {cookie_file} "
                f"https://localhost:{AIO_ADMIN_PORT}/containers",
                sudo=True, capture=True,
            )
            if not r.ok:
                return None, None
            m_name = _re.search(r'name="csrf_name"\s+value="([^"]+)"', r.stdout)
            m_value = _re.search(r'name="csrf_value"\s+value="([^"]+)"', r.stdout)
            if not m_name or not m_value:
                return None, None
            return m_name.group(1), m_value.group(1)

        def _api_post(endpoint: str) -> str:
            csrf_name, csrf_value = _get_csrf()
            if not csrf_name:
                self.log(f"Could not get CSRF for {endpoint}")
                return ""
            r = run(
                f"curl -sk -b {cookie_file} -X POST "
                f"https://localhost:{AIO_ADMIN_PORT}{endpoint} "
                f"--data-urlencode csrf_name={csrf_name} "
                f"--data-urlencode csrf_value={csrf_value} "
                f"-o /dev/null -w %{{http_code}}",
                sudo=True, capture=True, timeout=180,
            )
            return r.stdout.strip()

        try:
            # 1. Login (don't follow redirect — just save the cookie from 302).
            r = run(
                f"curl -sk -c {cookie_file} -o /dev/null "
                f"https://localhost:{AIO_ADMIN_PORT}/api/auth/getlogin?token={aio_token}",
                sudo=True, capture=True, timeout=30,
            )
            if not r.ok:
                self.log("AIO API login failed")
                return False

            # 2. Stop containers (so they get recreated with new env on start).
            code = _api_post("/api/docker/stop")
            self.log(f"AIO /api/docker/stop → HTTP {code}")
            if code not in ("200", "302"):
                self.log("Stop failed — trying start anyway")

            time.sleep(10)  # let containers fully stop

            # 3. Start containers (recreates them with updated configuration.json).
            code = _api_post("/api/docker/start")
            self.log(f"AIO /api/docker/start → HTTP {code}")
            return code in ("200", "302")
        finally:
            run(f"rm -f {cookie_file}", sudo=True, capture=True)
