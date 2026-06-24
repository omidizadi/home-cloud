"""Uninstall screen — conservative removal (never touches data on SSD)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, RichLog

from ..steps import ALL_STEPS
from ..utils import log


class UninstallScreen(Screen):
    DEFAULT_CSS = """
    UninstallScreen {
        align: center middle;
    }
    UninstallScreen Container {
        width: 90;
        height: 85%;
        padding: 1;
        border: round $error;
    }
    UninstallScreen RichLog {
        height: 1fr;
        border: solid $surface;
    }
    UninstallScreen .actions {
        height: 3;
        align: center middle;
    }
    UninstallScreen .warning {
        color: $warning;
        text-style: bold;
        margin-bottom: 1;
    }
    """

    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Label("🗑️ Uninstall (Conservative)", id="title")
            yield Label(
                "⚠️  This will remove all services and containers, but will NOT "
                "touch your data on the SSD (/mnt/ncdata). Your photos and files "
                "will remain intact on the disk.",
                classes="warning",
            )
            yield RichLog(id="log", markup=True)
            with Container(classes="actions"):
                yield Button("🗑️ Uninstall (keep data)", id="btn-uninstall", variant="error")
                yield Button("↩️ Back", id="btn-back", variant="default")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-uninstall":
            # thread=True keeps step.undo() (which calls subprocess.run) off the
            # event loop so the RichLog repaints live instead of freezing.
            self.run_worker(self._uninstall, thread=True)
        elif event.button.id == "btn-back":
            self.app.pop_screen()

    def _log(self, msg: str) -> None:
        """Thread-safe write to the log widget."""
        try:
            log_widget = self.query_one("#log", RichLog)
            self.app.call_from_thread(log_widget.write, msg)
        except Exception:
            pass

    async def _uninstall(self) -> None:
        try:
            log_widget = self.query_one("#log", RichLog)
            self.app.call_from_thread(log_widget.clear)
            self._log("[bold red]━━ Conservative Uninstall ━━[/]\n")
            self._log("[dim]Data on /mnt/ncdata will be PRESERVED.[/]\n")

            # Run undo() on each step in reverse order
            for StepClass in reversed(ALL_STEPS):
                step = StepClass(self.app)
                self._log(f"[yellow]Removing: {step.label}...[/]")
                try:
                    result = step.undo()
                    if result.success:
                        self._log(f"  [green]✓ {result.message}[/]")
                    else:
                        self._log(f"  [red]✗ {result.message}[/]")
                except Exception as e:
                    self._log(f"  [red]✗ EXCEPTION: {e}[/]")

            # Clear state markers
            from ..utils.state import clear_all
            clear_all()

            # Remove config (optional — ask? for now keep it so user can reinstall)
            self._log("\n[cyan]Config (.env) kept at /etc/homecloud/.env[/]")
            self._log("[cyan]Use 'homecloud secrets export' to back up, then delete manually if desired.[/]")

            self._log("\n[bold green]✅ Uninstall complete.[/]")
            self._log("[bold]Your data is safe on the SSD at /mnt/ncdata[/]")
        except Exception as e:
            self._log(f"[red bold]💥 Uninstall crashed: {e}[/]")
            log.exception("uninstall worker crashed")
