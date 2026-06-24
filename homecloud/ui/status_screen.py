"""Status screen — live dashboard of all components."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, RichLog

from ..services import container_status, unit_status
from ..steps import ALL_STEPS
from ..utils import run


class StatusScreen(Screen):
    DEFAULT_CSS = """
    StatusScreen {
        align: center middle;
    }
    StatusScreen Container {
        width: 90;
        height: 85%;
        padding: 1;
        border: round $primary;
    }
    StatusScreen RichLog {
        height: 1fr;
        border: solid $surface;
    }
    StatusScreen .actions {
        height: 3;
        align: center middle;
    }
    """

    BINDINGS = [("escape", "app.pop_screen", "Back"), ("r", "refresh", "Refresh")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Label("📊 Status Dashboard", id="title")
            yield RichLog(id="log", markup=True)
            with Container(classes="actions"):
                yield Button("🔄 Refresh", id="btn-refresh", variant="primary")
                yield Button("↩️ Back", id="btn-back", variant="default")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh":
            self._refresh()
        elif event.button.id == "btn-back":
            self.app.pop_screen()

    def action_refresh(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        log_widget = self.query_one("#log", RichLog)
        log_widget.clear()

        if self.app.dry_run:
            log_widget.write("[dim]dry-run mode — showing simulated status[/]\n")

        # System
        log_widget.write("[bold cyan]━━ System ━━[/]")
        uptime = run("uptime -p", capture=True).stdout.strip() or "N/A"
        cpu_temp = run("vcgencmd measure_temp 2>/dev/null | cut -d= -f2", capture=True).stdout.strip() or "N/A"
        mem = run("free -h | awk '/^Mem:/ {print $3\"/\"$2}'", capture=True).stdout.strip() or "N/A"
        log_widget.write(f"  Uptime:   {uptime}")
        log_widget.write(f"  CPU temp: {cpu_temp}")
        log_widget.write(f"  Memory:   {mem}")

        # Disk
        log_widget.write("\n[bold cyan]━━ Disk ━━[/]")
        ssd = run("df -h /mnt/ncdata 2>/dev/null | awk 'NR==2 {print $3\"/\"$2\" (\"$5\")\"}'", capture=True).stdout.strip()
        sd = run("df -h / 2>/dev/null | awk 'NR==2 {print $3\"/\"$2\" (\"$5\")\"}'", capture=True).stdout.strip()
        log_widget.write(f"  SSD (/mnt/ncdata): {ssd or 'not mounted'}")
        log_widget.write(f"  SD card (/):       {sd or 'N/A'}")

        # Services
        log_widget.write("\n[bold cyan]━━ Services ━━[/]")
        for svc in ["docker", "smbd", "ncbot", "cron"]:
            st = unit_status(svc)
            icon = "✅" if st == "active" else "❌"
            log_widget.write(f"  {icon} {svc}: {st}")

        # Containers
        log_widget.write("\n[bold cyan]━━ Containers ━━[/]")
        for c in ["nextcloud-aio-mastercontainer", "nextcloud-aio-nextcloud", "nextcloud-aio-talk"]:
            st = container_status(c)
            icon = "✅" if st == "running" else "❌"
            log_widget.write(f"  {icon} {c}: {st}")

        # Install steps
        log_widget.write("\n[bold cyan]━━ Install Steps ━━[/]")
        for StepClass in ALL_STEPS:
            step = StepClass(self.app)
            done = step.is_done()
            icon = "✅" if done else "⬜"
            try:
                status = step.status()
                health = "OK" if status.success else "ISSUE"
            except Exception:
                health = "?"
            log_widget.write(f"  {icon} {step.label}: {health}")

        # Backup
        log_widget.write("\n[bold cyan]━━ Backup ━━[/]")
        from pathlib import Path
        backup_log = Path("/var/log/nextcloud-s3-backup.log")
        if backup_log.exists():
            content = backup_log.read_text()
            if "=== Backup finished" in content.split("=== Backup started")[-1]:
                log_widget.write("  ✅ Last backup completed")
            else:
                log_widget.write("  ⚠️  Last backup may be incomplete")
            # Last line
            lines = [ln for ln in content.splitlines() if ln.strip()]
            if lines:
                log_widget.write(f"  Last log: {lines[-1][:80]}")
        else:
            log_widget.write("  ⬜ No backup run yet")
