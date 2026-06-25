"""Step 1: Mount the 5TB SSD at /mnt/data."""

from __future__ import annotations

from pathlib import Path

from ..constants import DATA_MOUNT, IMMICH_DATADIR
from ..utils import read_file_sudo, run
from .base import Step, StepResult


class SsdStep(Step):
    name = "ssd"
    label = "Mount 5TB SSD"
    description = "Format (if needed) and mount the external SSD at /mnt/data"
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
        run(f"mkdir -p {DATA_MOUNT}", sudo=True, dry_run=self.dry_run)

        # Add to fstab (idempotent)
        self._ensure_fstab_entry(part)

        # Mount via fstab
        r = run("mount -a", sudo=True, dry_run=self.dry_run)
        if not r.ok and not self.dry_run:
            return StepResult(self.name, False, f"mount -a failed: {r.stderr}", r.stderr)

        # Verify mounted; if mount -a missed us, try direct mount
        if not self.dry_run:
            r = run(f"findmnt --source {part} --target {DATA_MOUNT}", capture=True)
            if not r.ok:
                self.log(f"mount -a didn't mount {part}, trying direct mount...")
                r2 = run(f"mount {part} {DATA_MOUNT}", sudo=True)
                if not r2.ok:
                    return StepResult(self.name, False,
                                      f"Mount failed ({part} → {DATA_MOUNT}): {r2.stderr}", r2.stderr)
                r = run(f"findmnt --source {part} --target {DATA_MOUNT}", capture=True)
                if not r.ok:
                    return StepResult(self.name, False, f"{DATA_MOUNT} not mounted after direct mount")

        # Create Immich data directory (containers manage their own perms)
        run(f"mkdir -p {IMMICH_DATADIR}", sudo=True, dry_run=self.dry_run)

        self.mark_done({"device": dev, "partition": part, "mount": str(DATA_MOUNT)})
        return StepResult(self.name, True, f"SSD mounted at {DATA_MOUNT}")

    def _detect_partition(self, dev: str) -> str:
        """Find the best partition of the device.

        Picks the **largest** partition by size. A device may carry small
        leftover partitions from a previous install (e.g. a 182MB ``ncdata``
        partition from an old Nextcloud setup) alongside the real multi-TB
        data partition. Naively taking the first partition mounts the tiny
        one and Postgres runs out of space during ``initdb``.
        """
        if self.dry_run:
            return f"{dev}1"
        # Ask lsblk for partition name + size in bytes, parse, and pick max.
        r = run(
            f"lsblk -ln -b -o NAME,SIZE {dev}",
            capture=True,
        )
        if r.ok:
            best_name: str | None = None
            best_size: int = -1
            for line in r.stdout.splitlines():
                parts = line.split()
                if len(parts) < 2:
                    continue
                name = parts[0]
                try:
                    size = int(parts[1])
                except ValueError:
                    continue
                # First line is the parent device itself; skip it by name.
                if name == dev.replace("/dev/", ""):
                    continue
                if size > best_size:
                    best_size = size
                    best_name = name
            if best_name:
                return f"/dev/{best_name}"
        return f"{dev}1"

    def _is_ext4(self, part: str) -> bool:
        if self.dry_run:
            return True
        # Use sudo: blkid lives in /usr/sbin which is on root's secure_path
        # but often missing from a non-interactive user shell's PATH.
        r = run(f"blkid -o value -s TYPE {part}", sudo=True, capture=True)
        return r.ok and r.stdout.strip() == "ext4"

    def _get_uuid(self, part: str) -> str:
        """Get the UUID of a partition."""
        r = run(f"blkid -o value -s UUID {part}", sudo=True, capture=True)
        if r.ok and r.stdout.strip():
            return r.stdout.strip()
        return ""

    def _ensure_fstab_entry(self, part: str) -> None:
        """Idempotently add the SSD to /etc/fstab using UUID."""
        # Prefer UUID over LABEL — works even if the existing partition
        # has a different label than our default "data".
        uid = self._get_uuid(part)
        if uid:
            identifier = f"UUID={uid}"
        else:
            identifier = f"LABEL={self.cfg.ssd_label}"
        entry = f"{identifier}  {DATA_MOUNT}  ext4  defaults,nofail  0  2"
        if self.dry_run:
            self.log(f"[dry-run] would add fstab entry: {entry}")
            return
        fstab = Path("/etc/fstab")
        content = read_file_sudo(fstab) or ""
        if str(DATA_MOUNT) in content:
            self.log("fstab entry already exists")
            return
        r = run(f"bash -c 'echo \"{entry}\" >> {fstab}'", sudo=True)
        if r.ok:
            self.log(f"fstab entry added ({identifier})")

    def status(self) -> StepResult:
        if self.dry_run:
            return StepResult(self.name, True, "[dry-run]")
        r = run(f"findmnt -n -o TARGET {DATA_MOUNT}", capture=True)
        if r.ok:
            usage = run(f"df -h {DATA_MOUNT}", capture=True).stdout
            return StepResult(self.name, True, "Mounted", usage)
        return StepResult(self.name, False, f"{DATA_MOUNT} not mounted")

    def undo(self) -> StepResult:
        """Conservative: unmount and remove fstab entry, but DO NOT format/erase."""
        self.log("Conservative undo: unmounting SSD (data preserved)")
        run(f"umount {DATA_MOUNT}", sudo=True, dry_run=self.dry_run)
        # Remove fstab entry
        if not self.dry_run:
            fstab = Path("/etc/fstab")
            content = read_file_sudo(fstab) or ""
            new_lines = [
                ln for ln in content.splitlines()
                if str(DATA_MOUNT) not in ln
            ]
            run(f"bash -c 'cat > {fstab} <<\"EOF\"\n" + "\n".join(new_lines) + "\nEOF'", sudo=True)
        self.mark_undone()
        return StepResult(self.name, True, "SSD unmounted (data preserved on disk)")
