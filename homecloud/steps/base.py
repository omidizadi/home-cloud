"""Base class for all install steps."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..config import Config
from ..utils import log

if TYPE_CHECKING:
    from ..app import HomeCloudApp


@dataclass
class StepResult:
    name: str
    success: bool
    message: str
    details: str = ""


class Step(ABC):
    """Base class for an install step.

    Each step is idempotent: running it twice is safe.
    Each step supports: run, status, repair, undo.
    """

    name: str = "base"
    label: str = "Base Step"
    description: str = ""
    depends_on: list[str] = []

    def __init__(self, app: HomeCloudApp) -> None:
        self.app = app
        self.cfg: Config = app.cfg
        self.dry_run: bool = app.dry_run

    @abstractmethod
    def run(self) -> StepResult:
        """Execute the step."""

    def status(self) -> StepResult:
        """Check current health of this step's components."""
        return StepResult(self.name, True, "OK")

    def repair(self) -> StepResult:
        """Attempt to fix common issues. Default: re-run."""
        log.info("repair: re-running step %s", self.name)
        return self.run()

    def undo(self) -> StepResult:
        """Conservative removal of this step's components (keep data)."""
        return StepResult(self.name, True, f"undo not implemented for {self.name}")

    def is_done(self) -> bool:
        from ..utils.state import is_step_done

        return is_step_done(self.name)

    def mark_done(self, data: dict | None = None) -> None:
        from ..utils.state import step_done

        step_done(self.name, data)

    def mark_undone(self) -> None:
        from ..utils.state import step_undone

        step_undone(self.name)

    def deps_satisfied(self) -> bool:
        from ..utils.state import is_step_done

        return all(is_step_done(d) for d in self.depends_on)

    def log(self, msg: str) -> None:
        log.info("[%s] %s", self.name, msg)
        self.app.notify_step(self.name, msg)
