"""Install screen — runs all steps sequentially with live progress."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Button, Footer, Header, Label, RichLog, Static

from ..config import load_config
from ..steps import ALL_STEPS
from ..utils import log


class InstallScreen(Static):
    DEFAULT_CSS = """
    InstallScreen {
        align: center middle;
    }
    InstallScreen Container {
        width: 90;
        height: 85%;
        padding: 1;
        border: round $primary;
    }
    InstallScreen RichLog {
        height: 1fr;
        border: solid $surface;
    }
    InstallScreen .actions {
        height: 3;
        align: center middle;
    }
    """

    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._running = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Label("📥 Installation", id="title")
            yield RichLog(id="log", markup=True)
            with Container(classes="actions"):
                yield Button("▶️  Start Install", id="btn-start", variant="primary")
                yield Button("⚙️  Edit Config", id="btn-config", variant="default")
                yield Button("↩️  Back", id="btn-back", variant="default")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-start" and not self._running:
            self.run_worker(self._run_install)
        elif bid == "btn-config":
            self.app.push_screen("config")
        elif bid == "btn-back":
            self.app.pop_screen()

    async def _run_install(self) -> None:
        self._running = True
        log_widget = self.query_one("#log", RichLog)
        log_widget.clear()

        # Reload config in case it was edited
        self.app.cfg = load_config()

        if not self.app.cfg.is_complete():
            log_widget.write("[red]✗ Configuration incomplete. Edit config first.[/]")
            self._running = False
            return

        log_widget.write(f"[cyan]Dry run:[/] {self.app.dry_run}")
        log_widget.write(f"[cyan]Steps:[/] {len(ALL_STEPS)}\n")

        failed: list[str] = []
        for i, StepClass in enumerate(ALL_STEPS, 1):
            step = StepClass(self.app)
            log_widget.write(f"[bold yellow]━━━ Step {i}/{len(ALL_STEPS)}: {step.label} ━━━[/]")

            if step.is_done() and not self.app.force:
                log_widget.write("  [green]✓ already done (skip)[/]")
                continue

            if not step.deps_satisfied():
                missing = [d for d in step.depends_on if not self.app._step_done(d)]
                log_widget.write(f"  [red]✗ dependencies not met: {missing}[/]")
                failed.append(step.name)
                continue

            try:
                result = step.run()
            except Exception as e:
                log_widget.write(f"  [red]✗ EXCEPTION: {e}[/]")
                log.exception("step %s failed", step.name)
                failed.append(step.name)
                continue

            if result.success:
                log_widget.write(f"  [green]✓ {result.message}[/]")
                if result.details:
                    for line in result.details.splitlines():
                        log_widget.write(f"    [dim]{line}[/]")
            else:
                log_widget.write(f"  [red]✗ {result.message}[/]")
                if result.details:
                    log_widget.write(f"    [dim]{result.details}[/]")
                failed.append(step.name)

            log_widget.write("")

        log_widget.write("=" * 60)
        if failed:
            log_widget.write(f"[red]Completed with {len(failed)} failed step(s): {failed}[/]")
            log_widget.write("[yellow]Use Repair screen to retry failed steps.[/]")
        else:
            log_widget.write("[green bold]✅ All steps completed successfully![/]")
            log_widget.write("[cyan]Next: open https://<pi-ip>:8080 to finish Nextcloud AIO setup.[/]")

        self._running = False
