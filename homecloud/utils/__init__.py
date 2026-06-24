"""Utility helpers: shell execution, logging, system checks."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..constants import LOG_DIR

# ── Logging ───────────────────────────────────────────────────────────────────


def setup_logging(name: str = "homecloud", debug: bool = False) -> logging.Logger:
    """Configure and return a logger that writes to LOG_DIR and stderr."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(LOG_DIR / f"{name}.log")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(fh)
    except PermissionError:
        # Log dir not writable (e.g. running as non-root on a dev machine) — fall back to stderr only
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logger.addHandler(sh)
    return logger


log = setup_logging()


# ── Shell execution ───────────────────────────────────────────────────────────


@dataclass
class Result:
    """Result of a shell command execution."""

    cmd: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def __bool__(self) -> bool:
        return self.ok


def run(
    cmd: str | Sequence[str],
    *,
    check: bool = False,
    sudo: bool = False,
    capture: bool = True,
    timeout: int | None = None,
    input_text: str | None = None,
    dry_run: bool = False,
) -> Result:
    """Run a shell command.

    Args:
        cmd: Command string or list of args.
        check: Raise CalledProcessError on non-zero exit.
        sudo: Prefix with sudo (no-op if already root).
        capture: Capture stdout/stderr instead of inheriting.
        timeout: Timeout in seconds.
        input_text: Stdin input.
        dry_run: If True, log the command and return a fake success Result.

    Returns:
        Result with stdout/stderr.
    """
    if isinstance(cmd, (list, tuple)):
        cmd_list = list(cmd)
        cmd_str = " ".join(cmd_list)
    else:
        cmd_str = str(cmd)
        cmd_list = cmd_str

    if sudo and os.geteuid() != 0:
        cmd_list = ["sudo", *cmd_list] if isinstance(cmd_list, list) else f"sudo {cmd_str}"
        cmd_str = f"sudo {cmd_str}"

    log.info("$ %s", cmd_str)

    if dry_run:
        log.info("[dry-run] skipping execution")
        return Result(cmd=cmd_str, returncode=0, stdout="[dry-run]", stderr="")

    try:
        proc = subprocess.run(
            cmd_list if isinstance(cmd_list, list) else cmd_str,
            shell=isinstance(cmd_list, str),
            capture_output=capture,
            text=True,
            timeout=timeout,
            input=input_text,
            check=False,
        )
    except subprocess.TimeoutExpired:
        log.error("command timed out after %ss: %s", timeout, cmd_str)
        raise
    except FileNotFoundError as e:
        log.error("command not found: %s", e)
        return Result(cmd=cmd_str, returncode=127, stdout="", stderr=str(e))

    result = Result(
        cmd=cmd_str,
        returncode=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )
    if not result.ok:
        log.warning("command failed (rc=%d): %s", result.returncode, cmd_str)
        if result.stderr:
            log.debug("stderr: %s", result.stderr.strip())
    if check and not result.ok:
        raise subprocess.CalledProcessError(result.returncode, cmd_str, result.stdout, result.stderr)
    return result


def which(binary: str) -> Path | None:
    """Return path to binary or None."""
    p = shutil.which(binary)
    return Path(p) if p else None


# ── System checks ─────────────────────────────────────────────────────────────


def is_raspberry_pi() -> bool:
    """Detect if running on a Raspberry Pi."""
    try:
        with open("/proc/device-tree/model") as f:
            model = f.read().lower()
        return "raspberry pi" in model
    except FileNotFoundError:
        return False


def is_pi5() -> bool:
    """Detect Raspberry Pi 5 specifically."""
    try:
        with open("/proc/device-tree/model") as f:
            model = f.read().lower()
        return "raspberry pi 5" in model
    except FileNotFoundError:
        return False


def is_arm64() -> bool:
    return platform.machine() in ("aarch64", "arm64")


def os_release() -> dict[str, str]:
    """Parse /etc/os-release into a dict."""
    info: dict[str, str] = {}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    info[k] = v.strip('"')
    except FileNotFoundError:
        pass
    return info


def is_bookworm() -> bool:
    return os_release().get("VERSION_CODENAME", "").lower() == "bookworm"


def is_root() -> bool:
    return os.geteuid() == 0


def has_sudo() -> bool:
    if is_root():
        return True
    return which("sudo") is not None and run("sudo -n true", capture=True).ok


def internet_ok(host: str = "1.1.1.1") -> bool:
    return run(f"ping -c 1 -W 2 {host}", capture=True).ok


def ram_gb() -> float:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / 1024 / 1024, 1)
    except FileNotFoundError:
        pass
    return 0.0
