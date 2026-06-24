"""State tracking for install steps (idempotency + repair)."""

from __future__ import annotations

import json
from datetime import datetime

from ..constants import STATE_DIR
from ..utils import log


def step_done(name: str, data: dict | None = None) -> None:
    """Mark a step as completed by writing a marker file."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "step": name,
        "completed_at": datetime.now().isoformat(),
        "data": data or {},
    }
    marker = STATE_DIR / f"{name}.done"
    marker.write_text(json.dumps(payload, indent=2))
    log.info("step marked done: %s", name)


def step_undone(name: str) -> None:
    """Remove a step's marker file."""
    marker = STATE_DIR / f"{name}.done"
    if marker.exists():
        marker.unlink()
        log.info("step marker removed: %s", name)


def is_step_done(name: str) -> bool:
    return (STATE_DIR / f"{name}.done").exists()


def step_data(name: str) -> dict | None:
    """Return stored data for a completed step, or None."""
    marker = STATE_DIR / f"{name}.done"
    if not marker.exists():
        return None
    try:
        return json.loads(marker.read_text()).get("data", {})
    except (json.JSONDecodeError, OSError):
        return None


def all_steps() -> list[dict]:
    """List all completed steps with metadata."""
    results = []
    if not STATE_DIR.exists():
        return results
    for marker in sorted(STATE_DIR.glob("*.done")):
        try:
            results.append(json.loads(marker.read_text()))
        except (json.JSONDecodeError, OSError):
            results.append({"step": marker.stem, "completed_at": "unknown", "data": {}})
    return results


def clear_all() -> None:
    """Remove all step markers (used by uninstall)."""
    if STATE_DIR.exists():
        for marker in STATE_DIR.glob("*.done"):
            marker.unlink()
        log.info("all step markers cleared")
