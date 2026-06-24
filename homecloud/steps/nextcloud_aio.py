"""Step 3: Launch Nextcloud AIO master container."""

from __future__ import annotations

import time

from ..constants import (
    AIO_ADMIN_PORT,
    AIO_MASTER_CONTAINER,
    NEXTCLOUD_DATADIR,
)
from ..services import container_status, remove_container
from ..utils import run
from .base import Step, StepResult


class NextcloudAioStep(Step):
    name = "nextcloud_aio"
    label = "Install Nextcloud AIO"
    description = "Launch the Nextcloud AIO master container with data dir on the SSD"
    depends_on = ["docker"]

    def run(self) -> StepResult:
        # Remove existing master container if present (so we can re-create with right config)
        if container_status(AIO_MASTER_CONTAINER) != "not-found" and not self.dry_run:
            self.log("Removing existing AIO master container to re-create...")
            remove_container(AIO_MASTER_CONTAINER, dry_run=self.dry_run)

        cmd = (
            "docker run -d "
            "--init "
            "--sig-proxy=false "
            f"--name {AIO_MASTER_CONTAINER} "
            "--restart always "
            "--publish 80:80 "
            f"--publish {AIO_ADMIN_PORT}:{AIO_ADMIN_PORT} "
            "--publish 8443:8443 "
            "--volume nextcloud_aio_mastercontainer:/mnt/docker-aio-config "
            "--volume /var/run/docker.sock:/var/run/docker.sock:ro "
            f'-e NEXTCLOUD_DATADIR="{NEXTCLOUD_DATADIR}" '
            "ghcr.io/nextcloud-releases/all-in-one:latest"
        )
        self.log("Launching Nextcloud AIO master container...")
        r = run(cmd, sudo=True, dry_run=self.dry_run, timeout=120)
        if not r.ok and not self.dry_run:
            return StepResult(self.name, False, f"AIO launch failed: {r.stderr}", r.stderr)

        # Wait for AIO to be reachable
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

        self.mark_done({"admin_port": AIO_ADMIN_PORT, "datadir": str(NEXTCLOUD_DATADIR)})
        url = f"https://<pi-ip>:{AIO_ADMIN_PORT}"
        return StepResult(
            self.name, True,
            f"AIO master container running. Open {url} to complete setup.",
            "OPEN THE AIO PANEL IN YOUR BROWSER:\n"
            f"  1. Go to https://<pi-ip>:{AIO_ADMIN_PORT} (accept cert warning)\n"
            "  2. Enter your DuckDNS domain (e.g. yoursub.duckdns.org)\n"
            "  3. Pick optional containers: Talk ✅, Collabora optional, skip ClamAV/FTS\n"
            "  4. Set the admin password\n"
            "  5. Click 'Start containers' (takes 5-10 min on a Pi)\n"
            "  6. Once done → Nextcloud is live at https://yoursub.duckdns.org\n"
            "\n"
            "REQUIREMENTS:\n"
            "  • Port 443 (TCP) forwarded to Pi — for domain validation + HTTPS\n"
            "  • Ports 3478, 5349 (TCP+UDP) forwarded — for Talk video calls\n"
            "  • Port 80 (TCP) forwarded — for Let's Encrypt cert renewal",
        )

    def status(self) -> StepResult:
        if self.dry_run:
            return StepResult(self.name, True, "[dry-run]")
        st = container_status(AIO_MASTER_CONTAINER)
        if st == "running":
            nc_st = container_status("nextcloud-aio-nextcloud")
            return StepResult(
                self.name, True,
                f"Master: running | Nextcloud: {nc_st}",
            )
        return StepResult(self.name, False, f"Master container: {st}")

    def repair(self) -> StepResult:
        self.log("Restarting AIO master container...")
        run(f"docker restart {AIO_MASTER_CONTAINER}", sudo=True, dry_run=self.dry_run)
        return self.status()

    def undo(self) -> StepResult:
        self.log("Conservative undo: stopping AIO containers (data on SSD preserved)")
        for c in [
            AIO_MASTER_CONTAINER,
            "nextcloud-aio-nextcloud",
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
