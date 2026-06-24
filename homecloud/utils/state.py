"""State tracking for install steps (idempotency + repair).

State markers live under /etc/homecloud/state which is root-owned, so all
reads/writes go through sudo when the app is running as a non-root user.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from ..constants import STATE_DIR
from ..utils import (
    file_exists_sudo,
    log,
    read_file_sudo,
    run,
    write_file_sudo,
)


def _is_root() -> bool:
    return os.geteuid() == 0


def _mkdir_state() -> None:
    if _is_root():
        STATE_DIR.mkdir(parents=True, exist_ok=True)
    else:
        run(f"sudo -n mkdir -p {STATE_DIR}", capture=True)


def _list_markers() -> list[Path]:
    """Return sorted list of *.done marker paths."""
    if _is_root():
        return sorted(STATE_DIR.glob("*.done"))
    r = run(f"sudo -n ls -1 {STATE_DIR}/*.done 2>/dev/null", capture=True)
    if not r.ok or not r.stdout.strip():
        return []
    return [Path(line.strip()) for line in r.stdout.splitlines() if line.strip()]


def step_done(name: str, data: dict | None = None) -> None:
    """Mark a step as completed by writing a marker file."""
    _mkdir_state()
    payload = {
        "step": name,
        "completed_at": datetime.now().isoformat(),
        "data": data or {},
    }
    marker = STATE_DIR / f"{name}.done"
    write_file_sudo(marker, json.dumps(payload, indent=2), mode=0o644)
    log.info("step marked done: %s", name)


def step_undone(name: str) -> None:
    """Remove a step's marker file."""
    marker = STATE_DIR / f"{name}.done"
    if _is_root():
        if marker.exists():
            marker.unlink()
            log.info("step marker removed: %s", name)
    else:
        if run(f"sudo -n rm -f {marker}", capture=True).ok:
            log.info("step marker removed: %s", name)


def is_step_done(name: str) -> bool:
    return file_exists_sudo(STATE_DIR / f"{name}.done")


def step_data(name: str) -> dict | None:
    """Return stored data for a completed step, or None."""
    marker = STATE_DIR / f"{name}.done"
    content = read_file_sudo(marker)
    if content is None:
        return None
    try:
        return json.loads(content).get("data", {})
    except (json.JSONDecodeError, OSError):
        return None


def all_steps() -> list[dict]:
    """List all completed steps with metadata."""
    results = []
    if not file_exists_sudo(STATE_DIR):
        return results
    for marker in _list_markers():
        content = read_file_sudo(marker)
        if content is None:
            results.append({"step": marker.stem, "completed_at": "unknown", "data": {}})
            continue
        try:
            results.append(json.loads(content))
        except (json.JSONDecodeError, OSError):
            results.append({"step": marker.stem, "completed_at": "unknown", "data": {}})
    return results


def clear_all() -> None:
    """Remove all step markers (used by uninstall)."""
    if _is_root():
        if STATE_DIR.exists():
            for marker in STATE_DIR.glob("*.done"):
                marker.unlink()
            log.info("all step markers cleared")
    else:
        run(f"sudo -n rm -f {STATE_DIR}/*.done", capture=True)
        log.info("all step markers cleared")
