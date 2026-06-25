"""Service managers: systemd, docker, cron."""

from __future__ import annotations

import re
from pathlib import Path

from ..constants import BOT_SERVICE as BOT_SERVICE
from ..constants import DOCKER_SSD_OVERRIDE
from ..utils import Result, file_exists_sudo, log, run, write_file_sudo

# ── systemd ───────────────────────────────────────────────────────────────────


def write_unit(path: Path, content: str, *, dry_run: bool = False) -> None:
    """Write a systemd unit file (creating parent dir)."""
    if dry_run:
        log.info("[dry-run] would write unit file: %s", path)
        return
    write_file_sudo(path, content, mode=0o644)
    log.info("wrote unit file: %s", path)


def daemon_reload(*, dry_run: bool = False) -> Result:
    return run("systemctl daemon-reload", sudo=True, dry_run=dry_run)


def enable_unit(name: str, *, dry_run: bool = False) -> Result:
    return run(f"systemctl enable {name}", sudo=True, dry_run=dry_run)


def disable_unit(name: str, *, dry_run: bool = False) -> Result:
    return run(f"systemctl disable {name}", sudo=True, dry_run=dry_run)


def start_unit(name: str, *, dry_run: bool = False) -> Result:
    return run(f"systemctl start {name}", sudo=True, dry_run=dry_run)


def restart_unit(name: str, *, dry_run: bool = False) -> Result:
    return run(f"systemctl restart {name}", sudo=True, dry_run=dry_run)


def stop_unit(name: str, *, dry_run: bool = False) -> Result:
    return run(f"systemctl stop {name}", sudo=True, dry_run=dry_run)


def unit_status(name: str) -> str:
    """Return active/inactive/failed/not-found."""
    r = run(f"systemctl is-active {name}", capture=True)
    return r.stdout.strip() or "unknown"


def unit_enabled(name: str) -> bool:
    return run(f"systemctl is-enabled {name}", capture=True).stdout.strip() == "enabled"


def write_docker_ssd_dependency(mount_point: str = "/mnt/data", *, dry_run: bool = False) -> None:
    """Make Docker wait for the SSD mount before starting."""
    unit = mount_point.replace("/", "-").strip("-")
    content = (
        "[Unit]\n"
        f"After={unit}.mount\n"
        f"Requires={unit}.mount\n"
    )
    write_unit(DOCKER_SSD_OVERRIDE, content, dry_run=dry_run)
    daemon_reload(dry_run=dry_run)


def install_replug_support(ssd_label: str = "data", *, dry_run: bool = False) -> list[str]:
    """Install udev rule + systemd service + shell script for SSD hot-replug.

    Returns a list of issues encountered (empty = success).
    """
    from ..constants import REPLUG_SCRIPT, REPLUG_SERVICE, REPLUG_UDEV_RULE, TEMPLATES_DIR

    issues: list[str] = []

    # 1. udev rule
    udev_tpl = (TEMPLATES_DIR / "99-data.rules").read_text()
    udev_content = udev_tpl.replace("{{SSD_LABEL}}", ssd_label)
    if dry_run:
        log.info("[dry-run] would write udev rule: %s", REPLUG_UDEV_RULE)
    else:
        write_file_sudo(REPLUG_UDEV_RULE, udev_content, mode=0o644)
        run("udevadm control --reload-rules", sudo=True, dry_run=dry_run)
        run("udevadm trigger", sudo=True, dry_run=dry_run)
    log.info("udev rule installed: %s", REPLUG_UDEV_RULE)

    # 2. systemd service
    svc_tpl = (TEMPLATES_DIR / "data-replug.service").read_text()
    if dry_run:
        log.info("[dry-run] would write service: %s", REPLUG_SERVICE)
    else:
        write_file_sudo(REPLUG_SERVICE, svc_tpl, mode=0o644)

    # 3. shell script
    script_src = (TEMPLATES_DIR / "homecloud-replug.sh").read_text()
    if dry_run:
        log.info("[dry-run] would write script: %s", REPLUG_SCRIPT)
    else:
        write_file_sudo(REPLUG_SCRIPT, script_src, mode=0o755)

    # 4. reload
    daemon_reload(dry_run=dry_run)
    return issues


def remove_replug_support(*, dry_run: bool = False) -> None:
    """Remove udev rule, systemd service, and shell script for SSD hot-replug."""
    from ..constants import REPLUG_SCRIPT, REPLUG_SERVICE, REPLUG_UDEV_RULE

    for path in [REPLUG_UDEV_RULE, REPLUG_SERVICE, REPLUG_SCRIPT]:
        if file_exists_sudo(path):
            run(f"rm -f {path}", sudo=True, dry_run=dry_run)
            log.info("removed replug file: %s", path)
    run("udevadm control --reload-rules", sudo=True, dry_run=dry_run)
    daemon_reload(dry_run=dry_run)


# ── docker ────────────────────────────────────────────────────────────────────


def container_status(name: str) -> str:
    """Return running/exited/not-found."""
    r = run(f"docker inspect --format='{{{{.State.Status}}}}' {name}", sudo=True, capture=True)
    out = r.stdout.strip()
    if r.ok and out:
        return out
    return "not-found"


def container_running(name: str) -> bool:
    return container_status(name) == "running"


def restart_container(name: str, *, dry_run: bool = False) -> Result:
    return run(f"docker restart {name}", sudo=True, dry_run=dry_run)


def stop_container(name: str, *, dry_run: bool = False) -> Result:
    return run(f"docker stop {name}", sudo=True, dry_run=dry_run)


def remove_container(name: str, *, dry_run: bool = False) -> Result:
    return run(f"docker rm -f {name}", sudo=True, dry_run=dry_run)


def list_containers(all_: bool = False) -> list[dict]:
    """List containers as dicts."""
    flag = "-a" if all_ else ""
    r = run(
        f"docker ps {flag} --format '{{{{.Names}}}}\\t{{{{.Image}}}}\\t{{{{.Status}}}}'",        sudo=True,        capture=True,
    )
    containers = []
    if r.ok:
        for line in r.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                containers.append({"name": parts[0], "image": parts[1], "status": parts[2]})
    return containers


# ── cron ──────────────────────────────────────────────────────────────────────


CRON_MARKER_BEGIN = "# >>> homecloud begin >>>"
CRON_MARKER_END = "# <<< homecloud end <<<"


def _current_crontab() -> str:
    r = run("crontab -l", capture=True, sudo=False)
    return r.stdout if r.ok else ""


def _write_crontab(content: str) -> Result:
    return run(f"cat <<'HOMECLOUD_CRON' | crontab -\n{content}\nHOMECLOUD_CRON", capture=True)


def add_cron_block(block: str, *, dry_run: bool = False) -> None:
    """Add (or replace) a managed cron block identified by markers.

    Idempotent: if the block already exists, it's replaced.
    """
    if dry_run:
        log.info("[dry-run] would add cron block:\n%s", block)
        return
    current = _current_crontab()
    # Remove existing managed block
    pattern = re.compile(
        rf"{re.escape(CRON_MARKER_BEGIN)}.*?{re.escape(CRON_MARKER_END)}",
        re.DOTALL,
    )
    cleaned = pattern.sub("", current).strip()
    new = f"{cleaned}\n\n{CRON_MARKER_BEGIN}\n{block}\n{CRON_MARKER_END}\n"
    _write_crontab(new)
    log.info("cron block added")


def remove_cron_block(*, dry_run: bool = False) -> None:
    """Remove the managed cron block."""
    if dry_run:
        log.info("[dry-run] would remove managed cron block")
        return
    current = _current_crontab()
    pattern = re.compile(
        rf"{re.escape(CRON_MARKER_BEGIN)}.*?{re.escape(CRON_MARKER_END)}",
        re.DOTALL,
    )
    cleaned = pattern.sub("", current).strip()
    _write_crontab(cleaned)
    log.info("cron block removed")


def list_cron() -> str:
    return _current_crontab()
