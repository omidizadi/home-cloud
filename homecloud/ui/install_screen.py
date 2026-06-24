"""Install screen — runs all steps sequentially with live progress."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, RichLog

from ..config import load_config
from ..steps import ALL_STEPS
from ..utils import log


class InstallScreen(Screen):
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
        # NOTE: do not name this `_running` — it collides with Textual's
        # MessagePump._running internal flag, which would make the start
        # button silently do nothing (the guard `not self._running` would
        # always be False once the screen's message pump is active).
        self._installing = False

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
        if bid == "btn-start" and not self._installing:
            # thread=True keeps step.run() (which calls subprocess.run) off the
            # async event loop, so the RichLog repaints live instead of freezing.
            self.run_worker(self._run_install, thread=True)
        elif bid == "btn-config":
            self.app.push_screen("config")
        elif bid == "btn-back":
            self.app.pop_screen()

    def _log(self, log_widget: RichLog, msg: str) -> None:
        """Write a line to the log widget from a worker thread."""
        self.app.call_from_thread(log_widget.write, msg)

    async def _run_install(self) -> None:
        self._installing = True
        try:
            log_widget = self.query_one("#log", RichLog)
            self.app.call_from_thread(log_widget.clear)

            # Reload config in case it was edited
            self.app.cfg = load_config()

            if not self.app.cfg.is_complete():
                self._log(log_widget, "[red]✗ Configuration incomplete. Edit config first.[/]")
                self._log(log_widget, "[yellow]Press ⚙️  Edit Config to set up required values.[/]")
                return

            self._log(log_widget, f"[cyan]Dry run:[/] {self.app.dry_run}")
            self._log(log_widget, f"[cyan]Steps:[/] {len(ALL_STEPS)}\n")

            failed: list[str] = []
            for i, StepClass in enumerate(ALL_STEPS, 1):
                step = StepClass(self.app)
                self._log(log_widget, f"[bold yellow]━━━ Step {i}/{len(ALL_STEPS)}: {step.label} ━━━[/]")

                if step.is_done() and not self.app.force:
                    self._log(log_widget, "  [green]✓ already done (skip)[/]")
                    continue

                if not step.deps_satisfied():
                    missing = [d for d in step.depends_on if not self.app._step_done(d)]
                    self._log(log_widget, f"  [red]✗ dependencies not met: {missing}[/]")
                    failed.append(step.name)
                    continue

                try:
                    result = step.run()
                except Exception as e:
                    self._log(log_widget, f"  [red]✗ EXCEPTION: {e}[/]")
                    log.exception("step %s failed", step.name)
                    failed.append(step.name)
                    continue

                if result.success:
                    self._log(log_widget, f"  [green]✓ {result.message}[/]")
                    if result.details:
                        for line in result.details.splitlines():
                            self._log(log_widget, f"    [dim]{line}[/]")
                else:
                    self._log(log_widget, f"  [red]✗ {result.message}[/]")
                    if result.details:
                        self._log(log_widget, f"    [dim]{result.details}[/]")
                    failed.append(step.name)

                self._log(log_widget, "")

            self._log(log_widget, "=" * 60)
            if failed:
                self._log(log_widget, f"[red]Completed with {len(failed)} failed step(s): {failed}[/]")
                self._log(log_widget, "[yellow]Use Repair screen to retry failed steps.[/]")
            else:
                self._log(log_widget, "[green bold]✅ All steps completed successfully![/]")
                self._log(log_widget, "[cyan]Next: open https://<pi-ip>:8080 to finish Nextcloud AIO setup.[/]")
        except Exception as e:
            # Safety net — never let the worker die silently with _installing=True
            log_widget = self.query_one("#log", RichLog)
            self._log(log_widget, f"[red bold]💥 Install crashed: {e}[/]")
            log.exception("install worker crashed")
        finally:
            self._installing = False
