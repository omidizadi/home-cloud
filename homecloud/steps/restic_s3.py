"""Step 8: restic + S3 Glacier Deep Archive nightly backup."""

from __future__ import annotations

import os
from pathlib import Path

from ..constants import BACKUP_SCRIPT, NEXTCLOUD_DATADIR
from ..services import add_cron_block, remove_cron_block
from ..utils import run, which
from .base import Step, StepResult

BACKUP_LOG = Path("/var/log/nextcloud-s3-backup.log")


class ResticS3Step(Step):
    name = "restic_s3"
    label = "Configure restic + S3 Backup"
    description = "Install restic, init S3 repo, deploy nightly backup script"
    depends_on = ["nextcloud_aio"]

    def run(self) -> StepResult:
        # Install restic
        if not which("restic") and not self.dry_run:
            self.log("Installing restic...")
            run("apt-get update -qq", sudo=True, dry_run=self.dry_run, timeout=120)
            r = run("apt-get install -y -qq restic", sudo=True, dry_run=self.dry_run, timeout=120)
            if not r.ok:
                return StepResult(self.name, False, f"restic install failed: {r.stderr}", r.stderr)
        else:
            self.log("restic already installed")

        # Init repo
        env = self._restic_env()
        if not self.dry_run:
            self.log("Initializing restic repository on S3...")
            r = run("restic init", env=env, capture=True, timeout=60)
            if not r.ok and "config file already exists" not in r.stderr:
                return StepResult(self.name, False, f"restic init failed: {r.stderr}", r.stderr)
            self.log("restic repo ready")

        # Write backup script
        self._write_backup_script(env)

        # Add cron
        add_cron_block(f"0 3 * * * {BACKUP_SCRIPT}", dry_run=self.dry_run)

        self.mark_done({
            "repository": self.cfg.restic_repository,
            "schedule": "0 3 * * *",
        })
        return StepResult(
            self.name, True,
            "restic + S3 backup configured",
            (
                "AWS S3 Lifecycle rule (do this in AWS Console):\n"
                f"  Bucket → {self.cfg.s3_bucket} → Management → Lifecycle\n"
                "  Rule: transition objects in 'data/' prefix to Glacier Deep Archive after 1 day.\n"
                "  This keeps index/keys/ in S3 Standard (cheap) and bulk data in Deep Archive.\n\n"
                "First backup will run at 3 AM. Run it now with: /runbackup in the Telegram bot."
            ),
        )

    def _restic_env(self) -> dict[str, str]:
        return {
            **os.environ,
            "AWS_ACCESS_KEY_ID": self.cfg.aws_access_key_id,
            "AWS_SECRET_ACCESS_KEY": self.cfg.aws_secret_access_key,
            "RESTIC_PASSWORD": self.cfg.restic_password,
            "RESTIC_REPOSITORY": self.cfg.restic_repository,
        }

    def _write_backup_script(self, env: dict[str, str]) -> None:
        script = f"""#!/bin/bash
set -e

export AWS_ACCESS_KEY_ID="{env['AWS_ACCESS_KEY_ID']}"
export AWS_SECRET_ACCESS_KEY="{env['AWS_SECRET_ACCESS_KEY']}"
export RESTIC_PASSWORD="{env['RESTIC_PASSWORD']}"
export RESTIC_REPOSITORY="{env['RESTIC_REPOSITORY']}"

TELEGRAM_TOKEN="{self.cfg.telegram_bot_token}"
CHAT_ID="{self.cfg.telegram_chat_id}"

LOG="{BACKUP_LOG}"
exec >> "$LOG" 2>&1
echo "=== Backup started: $(date) ==="

# Alert if system just rebooted
UPTIME_SECS=$(awk '{{print int($1)}}' /proc/uptime)
if [ "$UPTIME_SECS" -lt 300 ]; then
  curl -s -X POST "https://api.telegram.org/bot${{TELEGRAM_TOKEN}}/sendMessage" \\
    -d chat_id="$CHAT_ID" \\
    -d text="⚠️ *Pi just rebooted* (uptime: ${{UPTIME_SECS}}s). Running first backup post-reboot." \\
    -d parse_mode="Markdown"
fi

# Wait for AIO borg backup if running
while [ -f /mnt/ncdata/borg-backup/aio-lockfile ]; do
  echo "Waiting for AIO borg backup to finish..."
  sleep 60
done

restic backup \\
  {NEXTCLOUD_DATADIR} \\
  --tag nextcloud \\
  --exclude="*.tmp" \\
  --exclude="*/cache/*" \\
  --exclude="*/updater-*" \\
  -o s3.storage-class=DEEP_ARCHIVE

restic forget \\
  --keep-daily 7 \\
  --keep-weekly 4 \\
  --keep-monthly 12 \\
  --prune

echo "=== Backup finished: $(date) ==="
"""
        if self.dry_run:
            self.log(f"[dry-run] would write {BACKUP_SCRIPT}")
            return
        BACKUP_SCRIPT.write_text(script)
        run(f"chmod +x {BACKUP_SCRIPT}", sudo=True)
        self.log(f"Wrote {BACKUP_SCRIPT}")

    def status(self) -> StepResult:
        if self.dry_run:
            return StepResult(self.name, True, "[dry-run]")
        if not BACKUP_SCRIPT.exists():
            return StepResult(self.name, False, "Backup script not found")
        if not BACKUP_LOG.exists():
            return StepResult(self.name, True, "Configured (no backup run yet)")
        # Read last run
        content = BACKUP_LOG.read_text()
        if "=== Backup finished" in content.split("=== Backup started")[-1]:
            return StepResult(self.name, True, "Last backup completed")
        return StepResult(self.name, False, "Last backup may be incomplete")

    def repair(self) -> StepResult:
        self.log("Re-checking restic repo...")
        env = self._restic_env()
        if not self.dry_run:
            r = run("restic check", env=env, capture=True, timeout=120)
            if r.ok:
                return StepResult(self.name, True, "restic repo check passed")
            return StepResult(self.name, False, f"restic check failed: {r.stderr}", r.stderr)
        return StepResult(self.name, True, "[dry-run]")

    def undo(self) -> StepResult:
        self.log("Conservative undo: removing backup script + cron (S3 data preserved)")
        remove_cron_block(dry_run=self.dry_run)
        run(f"rm -f {BACKUP_SCRIPT}", sudo=True, dry_run=self.dry_run)
        self.mark_undone()
        return StepResult(
            self.name, True,
            "Backup script + cron removed (S3 repo + snapshots preserved in AWS)",
        )
