"""Step 4: DuckDNS dynamic DNS updater."""

from __future__ import annotations

from ..constants import DUCKDNS_SCRIPT
from ..services import add_cron_block, remove_cron_block
from ..utils import file_exists_sudo, read_file_sudo, run, write_file_sudo
from .base import Step, StepResult

DUCKDNS_DIR = DUCKDNS_SCRIPT.parent
DUCKDNS_LOG = DUCKDNS_DIR / "duck.log"


class DuckDnsStep(Step):
    name = "duckdns"
    label = "Configure DuckDNS"
    description = "Set up DuckDNS dynamic DNS updater with a 5-minute cron job"
    depends_on: list[str] = []  # parallel-safe

    def run(self) -> StepResult:
        domain = self.cfg.duckdns_domain
        token = self.cfg.duckdns_token
        if not domain or not token:
            return StepResult(self.name, False, "DuckDNS domain/token not configured")

        self.log(f"Configuring DuckDNS for {domain}.duckdns.org")

        # Create script
        run(f"mkdir -p {DUCKDNS_DIR}", sudo=True, dry_run=self.dry_run)
        script_content = (
            f'echo url="https://www.duckdns.org/update?domains={domain}'
            f'&token={token}&ip=" | curl -k -o {DUCKDNS_LOG} -K -\n'
        )
        if self.dry_run:
            self.log(f"[dry-run] would write {DUCKDNS_SCRIPT}:\n{script_content}")
        else:
            write_file_sudo(DUCKDNS_SCRIPT, script_content, mode=0o755)
            self.log(f"Wrote {DUCKDNS_SCRIPT}")

        # Run once to verify
        r = run(str(DUCKDNS_SCRIPT), sudo=True, dry_run=self.dry_run, capture=True)
        if not self.dry_run:
            if r.ok and "OK" in (r.stdout + self._read_log()):
                self.log("DuckDNS update successful")
            else:
                self.log("DuckDNS update may have failed (check log)")

        # Add cron
        add_cron_block(f"*/5 * * * * {DUCKDNS_SCRIPT} >/dev/null 2>&1", dry_run=self.dry_run)

        self.mark_done({"domain": f"{domain}.duckdns.org"})
        return StepResult(
            self.name, True,
            f"DuckDNS configured for {domain}.duckdns.org",
            "Remember to forward ports 80, 443, and 3478 on your router to the Pi's IP.",
        )

    def _read_log(self) -> str:
        return read_file_sudo(DUCKDNS_LOG) or ""

    def status(self) -> StepResult:
        if self.dry_run:
            return StepResult(self.name, True, "[dry-run]")
        if not file_exists_sudo(DUCKDNS_SCRIPT):
            return StepResult(self.name, False, "DuckDNS script not found")
        log_content = self._read_log()
        ok = "OK" in log_content
        return StepResult(
            self.name, ok,
            f"Last update: {'OK' if ok else 'check log'}",
            log_content,
        )

    def undo(self) -> StepResult:
        self.log("Removing DuckDNS script and cron")
        remove_cron_block(dry_run=self.dry_run)
        run(f"rm -f {DUCKDNS_SCRIPT} {DUCKDNS_LOG}", sudo=True, dry_run=self.dry_run)
        self.mark_undone()
        return StepResult(self.name, True, "DuckDNS removed")
