"""Step 10: Hardening — reboot survival, fsck, service checks, SSD hot-replug."""

from __future__ import annotations

from ..services import (
    daemon_reload,
    install_replug_support,
    remove_replug_support,
    unit_enabled,
    unit_status,
    write_docker_ssd_dependency,
)
from ..utils import file_exists_sudo, run
from .base import Step, StepResult


class HardeningStep(Step):
    name = "hardening"
    label = "Apply Hardening"
    description = "Docker→SSD mount dependency, fsck, verify all services auto-start"
    depends_on = ["telegram_bot"]

    def run(self) -> StepResult:
        issues: list[str] = []

        # 1. Docker waits for SSD mount
        self.log("Configuring Docker→SSD mount dependency...")
        write_docker_ssd_dependency("/mnt/data", dry_run=self.dry_run)

        # 2. Verify fstab fsck pass number is 2 for SSD
        self.log("Verifying fstab fsck settings...")
        if not self.dry_run:
            r = run("grep /mnt/data /etc/fstab", capture=True)
            if r.ok:
                fields = r.stdout.split()
                # last field should be 2
                if len(fields) >= 6 and fields[-1] != "2":
                    issues.append("SSD fstab entry fsck pass should be 2 (auto-repair on boot)")
            else:
                issues.append("SSD not found in /etc/fstab")

        # 3. Verify all services are enabled
        self.log("Verifying service auto-start...")
        for svc in ["docker", "homecloud-bot", "cron", "tailscaled"]:
            if not unit_enabled(svc):
                issues.append(f"{svc} is not enabled for boot")
                run(f"systemctl enable {svc}", sudo=True, dry_run=self.dry_run)

        # 4. SSD hot-replug support (udev + systemd service)
        self.log("Installing SSD hot-replug support...")
        replug_issues = install_replug_support(
            ssd_label=self.cfg.ssd_label, dry_run=self.dry_run
        )
        issues.extend(replug_issues)

        # 5. Optional: apcupsd (UPS) — just check, don't install
        if not self.dry_run and unit_status("apcupsd") == "not-found":
            self.log("No UPS daemon (apcupsd) detected — recommended for power-cut protection")

        self.mark_done({"issues": issues})
        if issues:
            return StepResult(
                self.name, True,
                f"Hardening applied with {len(issues)} note(s)",
                "\n".join(f"• {i}" for i in issues),
            )
        return StepResult(self.name, True, "All hardening checks passed")

    def status(self) -> StepResult:
        if self.dry_run:
            return StepResult(self.name, True, "[dry-run]")
        checks = []
        all_ok = True
        for svc in ["docker", "homecloud-bot", "cron", "tailscaled"]:
            ok = unit_enabled(svc)
            checks.append(f"{svc}: {'✅' if ok else '❌'}")
            if not ok:
                all_ok = False
        # Check replug components
        from ..constants import REPLUG_SCRIPT, REPLUG_SERVICE, REPLUG_UDEV_RULE
        for label, path in [("udev", REPLUG_UDEV_RULE), ("replug-svc", REPLUG_SERVICE), ("replug-sh", REPLUG_SCRIPT)]:
            ok = file_exists_sudo(path)
            checks.append(f"{label}: {'✅' if ok else '❌'}")
            if not ok:
                all_ok = False
        return StepResult(self.name, all_ok, " | ".join(checks))

    def repair(self) -> StepResult:
        return self.run()

    def undo(self) -> StepResult:
        self.log("Conservative undo: removing Docker→SSD override and replug support")
        from ..constants import DOCKER_SSD_OVERRIDE
        if not self.dry_run and file_exists_sudo(DOCKER_SSD_OVERRIDE):
            run(f"sudo -n rm -f {DOCKER_SSD_OVERRIDE}", capture=True)
        remove_replug_support(dry_run=self.dry_run)
        self.mark_undone()
        return StepResult(self.name, True, "Hardening override and replug support removed")
