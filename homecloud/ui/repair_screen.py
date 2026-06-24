"""Repair screen — re-run failed steps or fix common issues."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, RichLog

from ..steps import ALL_STEPS


class RepairScreen(Screen):
    DEFAULT_CSS = """
    RepairScreen {
        align: center middle;
    }
    RepairScreen Container {
        width: 90;
        height: 85%;
        padding: 1;
        border: round $primary;
    }
    RepairScreen RichLog {
        height: 1fr;
        border: solid $surface;
    }
    RepairScreen .actions {
        height: 3;
        align: center middle;
    }
    """

    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Label("🔧 Repair", id="title")
            yield RichLog(id="log", markup=True)
            with Container(classes="actions"):
                yield Button("🔍 Check all steps", id="btn-check", variant="primary")
                yield Button("🔧 Repair all failed", id="btn-repair-all", variant="warning")
                yield Button("↩️ Back", id="btn-back", variant="default")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-check":
            self.run_worker(self._check_all)
        elif bid == "btn-repair-all":
            self.run_worker(self._repair_all)
        elif bid == "btn-back":
            self.app.pop_screen()

    def _log(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(msg)

    async def _check_all(self) -> None:
        log_widget = self.query_one("#log", RichLog)
        log_widget.clear()
        self._log("[bold cyan]━━ Step Health Check ━━[/]\n")
        failed: list[str] = []
        for StepClass in ALL_STEPS:
            step = StepClass(self.app)
            done = step.is_done()
            try:
                status = step.status()
                ok = status.success
            except Exception as e:
                ok = False
                status = type("S", (), {"message": str(e)})()
            icon = "✅" if ok else "❌"
            done_icon = "✓" if done else "⬜"
            self._log(f"  {icon} [{done_icon}] {step.label}: {status.message}")
            if not ok:
                failed.append(step.name)
        self._log(f"\n[bold]Failed: {len(failed)}[/]")

    async def _repair_all(self) -> None:
        log_widget = self.query_one("#log", RichLog)
        log_widget.clear()
        self._log("[bold cyan]━━ Repairing failed steps ━━[/]\n")
        for StepClass in ALL_STEPS:
            step = StepClass(self.app)
            try:
                status = step.status()
                if status.success:
                    continue
            except Exception:
                pass
            self._log(f"[yellow]Repairing: {step.label}...[/]")
            try:
                result = step.repair()
                if result.success:
                    self._log(f"  [green]✓ {result.message}[/]")
                else:
                    self._log(f"  [red]✗ {result.message}[/]")
            except Exception as e:
                self._log(f"  [red]✗ EXCEPTION: {e}[/]")
        self._log("\n[bold]Repair complete.[/]")
