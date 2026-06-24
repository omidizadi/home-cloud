"""Step 5: Coturn / Nextcloud Talk (AIO built-in)."""

from __future__ import annotations

from ..constants import TURN_PORT, TURN_TLS_PORT
from ..utils import run
from .base import Step, StepResult


class CoturnStep(Step):
    name = "coturn"
    label = "Configure Talk (Coturn)"
    description = "Guide enabling Nextcloud Talk with AIO's built-in Coturn TURN server"
    depends_on = ["nextcloud_aio", "duckdns"]

    def run(self) -> StepResult:
        domain = self.cfg.nextcloud_domain or f"{self.cfg.duckdns_domain}.duckdns.org"
        self.log(f"Configuring Talk with domain {domain}")

        # This step is mostly guidance — AIO handles Coturn automatically.
        # We verify the Talk container is running after the user enables it.
        instructions = (
            f"In the AIO admin panel (https://<pi-ip>:8080):\n"
            f"  1. Scroll to 'Nextcloud Talk'\n"
            f"  2. Enter domain: {domain}\n"
            f"  3. Enter Talk port: {TURN_PORT}\n"
            f"  4. AIO will auto-configure Coturn and inject credentials into Talk.\n"
            f"  5. Start/restart containers.\n\n"
            f"Then forward these ports on your router to the Pi:\n"
            f"  - {TURN_PORT} TCP+UDP  (TURN/STUN, required)\n"
            f"  - {TURN_TLS_PORT} TCP+UDP (TURN over TLS, optional)\n"
            f"  - 443 TCP (Nextcloud HTTPS)\n"
            f"  - 80 TCP (Let's Encrypt renewal)\n\n"
            f"In Nextcloud → Admin → Talk, verify STUN/TURN servers show a green checkmark."
        )

        # Check if Talk container exists
        r = run("docker inspect nextcloud-aio-talk --format='{{.State.Status}}'", sudo=True, capture=True)
        talk_status = r.stdout.strip() if r.ok else "not-running"

        self.mark_done({"domain": domain, "talk_status": talk_status})
        return StepResult(
            self.name, True,
            f"Talk configuration guidance (container: {talk_status})",
            instructions,
        )

    def status(self) -> StepResult:
        if self.dry_run:
            return StepResult(self.name, True, "[dry-run]")
        r = run("docker inspect nextcloud-aio-talk --format='{{.State.Status}}'", sudo=True, capture=True)
        st = r.stdout.strip() if r.ok else "not-found"
        return StepResult(self.name, st == "running", f"Talk container: {st}")

    def repair(self) -> StepResult:
        self.log("Restarting Talk container...")
        run("docker restart nextcloud-aio-talk", sudo=True, dry_run=self.dry_run)
        return self.status()

    def undo(self) -> StepResult:
        self.log("Conservative undo: stopping Talk container (config kept in AIO)")
        run("docker stop nextcloud-aio-talk", sudo=True, dry_run=self.dry_run)
        self.mark_undone()
        return StepResult(self.name, True, "Talk container stopped")
