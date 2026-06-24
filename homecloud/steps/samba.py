"""Step 6: Samba share for /mnt/ncdata/files."""

from __future__ import annotations

from pathlib import Path

from ..constants import SAMBA_SHARE_DIR
from ..services import disable_unit, enable_unit, restart_unit, unit_status
from ..utils import file_exists_sudo, read_file_sudo, run, write_file_sudo
from .base import Step, StepResult

SMB_CONF = Path("/etc/samba/smb.conf")
SHARE_NAME = "NAS Files"


class SambaStep(Step):
    name = "samba"
    label = "Configure Samba Share"
    description = "Expose /mnt/ncdata/files as a Samba share for non-Nextcloud file access"
    depends_on = ["ssd"]

    def run(self) -> StepResult:
        user = self.cfg.samba_user
        if not user:
            return StepResult(self.name, False, "Samba user not configured")

        self.log("Installing Samba...")
        run("apt-get update -qq", sudo=True, dry_run=self.dry_run, timeout=120)
        r = run(
            "apt-get install -y -qq samba samba-common-bin",
            sudo=True, dry_run=self.dry_run, timeout=180,
        )
        if not r.ok and not self.dry_run:
            return StepResult(self.name, False, f"Samba install failed: {r.stderr}", r.stderr)

        # Ensure share dir exists
        run(f"mkdir -p {SAMBA_SHARE_DIR}", sudo=True, dry_run=self.dry_run)

        # Ensure the samba user exists as a system user
        if not self.dry_run:
            id_check = run(f"id -u {user}", sudo=True, capture=True)
            if not id_check.ok:
                return StepResult(
                    self.name, False,
                    f"System user '{user}' does not exist. Create it first: sudo useradd -m {user}",
                )

        r = run(f"chown -R {user}:{user} {SAMBA_SHARE_DIR}", sudo=True, dry_run=self.dry_run)
        if not r.ok and not self.dry_run:
            return StepResult(self.name, False, f"chown failed: {r.stderr}", r.stderr)

        # Ensure system user exists in Samba and set password
        pw = self.cfg.samba_password
        if pw:
            self.log(f"Setting Samba password for {user}...")
            # smbpasswd reads password twice from stdin (confirm + set)
            r = run(
                f"smbpasswd -a -s {user}",
                sudo=True, dry_run=self.dry_run, capture=True,
                input_text=f"{pw}\n{pw}\n",
            )
            if not r.ok and not self.dry_run:
                return StepResult(self.name, False, f"smbpasswd failed: {r.stderr}", r.stderr)

        # Add share to smb.conf (idempotent)
        self._ensure_share_config(user)

        # Enable + restart
        enable_unit("smbd", dry_run=self.dry_run)
        restart_unit("smbd", dry_run=self.dry_run)

        self.mark_done({"user": user, "share": str(SAMBA_SHARE_DIR)})
        return StepResult(
            self.name, True,
            f"Samba share '{SHARE_NAME}' configured",
            f"Connect from Mac: Finder → Go → Connect to Server → smb://<pi-ip>/{SHARE_NAME}",
        )

    def _ensure_share_config(self, user: str) -> None:
        block = (
            f"\n[{SHARE_NAME}]\n"
            f"   path = {SAMBA_SHARE_DIR}\n"
            "   browseable = yes\n"
            "   read only = no\n"
            "   guest ok = no\n"
            f"   valid users = {user}\n"
            "   create mask = 0664\n"
            "   directory mask = 0775\n"
        )
        if self.dry_run:
            self.log(f"[dry-run] would append to {SMB_CONF}:\n{block}")
            return
        content = read_file_sudo(SMB_CONF) or ""
        if f"[{SHARE_NAME}]" in content:
            self.log("Samba share already configured")
            return
        write_file_sudo(SMB_CONF, content + block)
        self.log(f"Added share '{SHARE_NAME}' to {SMB_CONF}")

    def status(self) -> StepResult:
        if self.dry_run:
            return StepResult(self.name, True, "[dry-run]")
        st = unit_status("smbd")
        return StepResult(self.name, st == "active", f"smbd: {st}")

    def repair(self) -> StepResult:
        restart_unit("smbd", dry_run=self.dry_run)
        return self.status()

    def undo(self) -> StepResult:
        self.log("Conservative undo: disabling Samba share (data on SSD preserved)")
        disable_unit("smbd", dry_run=self.dry_run)
        run("systemctl stop smbd", sudo=True, dry_run=self.dry_run)
        # Remove share block from smb.conf
        if not self.dry_run and file_exists_sudo(SMB_CONF):
            content = read_file_sudo(SMB_CONF) or ""
            if f"[{SHARE_NAME}]" in content:
                idx = content.find(f"\n[{SHARE_NAME}]")
                content = content[:idx] if idx >= 0 else content
                write_file_sudo(SMB_CONF, content)
                self.log("Removed share from smb.conf")
        self.mark_undone()
        return StepResult(self.name, True, "Samba disabled (share data preserved on SSD)")
