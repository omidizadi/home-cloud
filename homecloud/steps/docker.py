"""Step 2: Install Docker."""

from __future__ import annotations

import os

from ..utils import run, which
from .base import Step, StepResult


class DockerStep(Step):
    name = "docker"
    label = "Install Docker"
    description = "Install Docker Engine and add the current user to the docker group"
    depends_on = ["ssd"]

    def run(self) -> StepResult:
        if which("docker") and not self.dry_run:
            self.log("Docker already installed")
        else:
            self.log("Installing Docker via get.docker.com...")
            r = run("curl -fsSL https://get.docker.com | sh", sudo=True, dry_run=self.dry_run, timeout=300)
            if not r.ok and not self.dry_run:
                return StepResult(self.name, False, f"Docker install failed: {r.stderr}", r.stderr)

        # Enable service
        run("systemctl enable docker", sudo=True, dry_run=self.dry_run)
        run("systemctl start docker", sudo=True, dry_run=self.dry_run)

        # Add user to docker group
        user = os.environ.get("USER", "pi")
        run(f"usermod -aG docker {user}", sudo=True, dry_run=self.dry_run)
        self.log(f"Added {user} to docker group (re-login to take effect)")

        self.mark_done({"user": user})
        return StepResult(self.name, True, "Docker installed and enabled")

    def status(self) -> StepResult:
        if self.dry_run:
            return StepResult(self.name, True, "[dry-run]")
        if not which("docker"):
            return StepResult(self.name, False, "docker binary not found")
        r = run("docker info", sudo=True, capture=True)
        if r.ok:
            return StepResult(self.name, True, "Docker daemon running")
        return StepResult(self.name, False, "Docker daemon not responding")

    def undo(self) -> StepResult:
        self.log("Conservative undo: disabling Docker service (not uninstalling)")
        run("systemctl stop docker", sudo=True, dry_run=self.dry_run)
        run("systemctl disable docker", sudo=True, dry_run=self.dry_run)
        self.mark_undone()
        return StepResult(self.name, True, "Docker service disabled (binary kept)")
