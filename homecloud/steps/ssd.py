"""Step 1: Mount the 5TB SSD at /mnt/ncdata."""

from __future__ import annotations

from pathlib import Path

from ..constants import BORG_BACKUP_DIR, NCDATA_MOUNT, NEXTCLOUD_DATADIR, SAMBA_SHARE_DIR
from ..utils import read_file_sudo, run
from .base import Step, StepResult


class SsdStep(Step):
    name = "ssd"
    label = "Mount 5TB SSD"
    description = "Format (if needed) and mount the external SSD at /mnt/ncdata"
    depends_on: list[str] = []

    def run(self) -> StepResult:
        dev = self.cfg.ssd_device
        if not dev:
            return StepResult(self.name, False, "No SSD device configured")

        self.log(f"Using device {dev}")

        # Check device exists
        if not Path(dev).exists() and not self.dry_run:
            return StepResult(self.name, False, f"Device {dev} not found")

        # Detect partition
        part = self._detect_partition(dev)
        self.log(f"Detected partition: {part}")

        # Format if no valid ext4 partition exists
        if not self._is_ext4(part) and not self.dry_run:
            self.log(f"Formatting {part} as ext4 (label={self.cfg.ssd_label})...")
            r = run(f"mkfs.ext4 -F -L {self.cfg.ssd_label} {part}", sudo=True, dry_run=self.dry_run)
            if not r.ok:
                return StepResult(self.name, False, f"Format failed: {r.stderr}", r.stderr)

        # Create mount point
        run(f"mkdir -p {NCDATA_MOUNT}", sudo=True, dry_run=self.dry_run)

        # Add to fstab (idempotent)
        self._ensure_fstab_entry(part)

        # Mount
        r = run("mount -a", sudo=True, dry_run=self.dry_run)
        if not r.ok and not self.dry_run:
            return StepResult(self.name, False, f"mount -a failed: {r.stderr}", r.stderr)

        # Verify mounted
        if not self.dry_run:
            r = run(f"findmnt --source {part} --target {NCDATA_MOUNT}", capture=True)
            if not r.ok:
                return StepResult(self.name, False, f"{NCDATA_MOUNT} not mounted")

        # Create subdirectories
        for d, uid, gid in [
            (NEXTCLOUD_DATADIR, 33, 33),  # www-data
            (SAMBA_SHARE_DIR, 1000, 1000),
            (BORG_BACKUP_DIR, 0, 0),
        ]:
            run(f"mkdir -p {d}", sudo=True, dry_run=self.dry_run)
            run(f"chown -R {uid}:{gid} {d}", sudo=True, dry_run=self.dry_run)

        self.mark_done({"device": dev, "partition": part, "mount": str(NCDATA_MOUNT)})
        return StepResult(self.name, True, f"SSD mounted at {NCDATA_MOUNT}")

    def _detect_partition(self, dev: str) -> str:
        """Find the first partition of the device."""
        if self.dry_run:
            return f"{dev}1"
        r = run(f"lsblk -ln -o NAME {dev}", capture=True)
        if r.ok:
            lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
            # First line is the device itself, subsequent are partitions
            for line in lines[1:]:
                name = line.split()[0]
                return f"/dev/{name}"
        return f"{dev}1"

    def _is_ext4(self, part: str) -> bool:
        if self.dry_run:
            return True
        r = run(f"blkid -o value -s TYPE {part}", capture=True)
        return r.ok and r.stdout.strip() == "ext4"

    def _ensure_fstab_entry(self, part: str) -> None:
        """Idempotently add the SSD to /etc/fstab."""
        entry = f"LABEL={self.cfg.ssd_label}  {NCDATA_MOUNT}  ext4  defaults,nofail  0  2"
        if self.dry_run:
            self.log(f"[dry-run] would add fstab entry: {entry}")
            return
        fstab = Path("/etc/fstab")
        content = read_file_sudo(fstab) or ""
        if str(NCDATA_MOUNT) in content:
            self.log("fstab entry already exists")
            return
        r = run(f"bash -c 'echo \"{entry}\" >> {fstab}'", sudo=True)
        if r.ok:
            self.log("fstab entry added")

    def status(self) -> StepResult:
        if self.dry_run:
            return StepResult(self.name, True, "[dry-run]")
        r = run(f"findmnt -n -o TARGET {NCDATA_MOUNT}", capture=True)
        if r.ok:
            usage = run(f"df -h {NCDATA_MOUNT}", capture=True).stdout
            return StepResult(self.name, True, "Mounted", usage)
        return StepResult(self.name, False, f"{NCDATA_MOUNT} not mounted")

    def undo(self) -> StepResult:
        """Conservative: unmount and remove fstab entry, but DO NOT format/erase."""
        self.log("Conservative undo: unmounting SSD (data preserved)")
        run(f"umount {NCDATA_MOUNT}", sudo=True, dry_run=self.dry_run)
        # Remove fstab entry
        if not self.dry_run:
            fstab = Path("/etc/fstab")
            content = read_file_sudo(fstab) or ""
            new_lines = [
                ln for ln in content.splitlines()
                if str(NCDATA_MOUNT) not in ln
            ]
            run(f"bash -c 'cat > {fstab} <<\"EOF\"\n" + "\n".join(new_lines) + "\nEOF'", sudo=True)
        self.mark_undone()
        return StepResult(self.name, True, "SSD unmounted (data preserved on disk)")
