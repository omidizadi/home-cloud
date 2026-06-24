"""The main Textual application."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult

from .config import Config, export_recovery_bundle, load_config
from .ui import (
    ConfigScreen,
    InstallScreen,
    MainMenu,
    RepairScreen,
    StatusScreen,
    UninstallScreen,
    UpdateScreen,
)
from .utils import has_sudo, is_pi5, is_root, log, setup_logging
from .utils.state import is_step_done


class HomeCloudApp(App):
    """Home Cloud — interactive installer & manager TUI."""

    TITLE = "🏠 Home Cloud"
    CSS = """
    Screen {
        background: $surface;
    }
    """

    BINDINGS = [("q", "quit", "Quit"), ("d", "toggle_dry_run", "Dry-run")]

    def __init__(self, dry_run: bool = False, force: bool = False, debug: bool = False) -> None:
        super().__init__()
        self.dry_run = dry_run
        self.force = force
        self._debug = debug
        setup_logging(debug=debug)
        self.cfg: Config = load_config()

    def compose(self) -> ComposeResult:
        # Screens are pushed via on_mount; each screen yields its own Header/Footer.
        yield from ()

    def on_mount(self) -> None:
        self.install_screen(MainMenu(), "main")
        self.install_screen(InstallScreen(), "install")
        self.install_screen(StatusScreen(), "status")
        self.install_screen(UpdateScreen(), "update")
        self.install_screen(RepairScreen(), "repair")
        self.install_screen(UninstallScreen(), "uninstall")
        self.install_screen(ConfigScreen(), "config")
        self.push_screen("main")

        # Pre-flight checks (non-blocking warnings)
        if not is_pi5() and not self.dry_run:
            self.notify(
                "Warning: this doesn't appear to be a Raspberry Pi 5. "
                "Proceed at your own risk.",
                severity="warning",
                timeout=10,
            )
        if not (is_root() or has_sudo()):
            self.notify(
                "Warning: no sudo access. Most install steps will fail.",
                severity="error",
                timeout=10,
            )
        if self.dry_run:
            self.notify("Dry-run mode active — no commands will execute.", severity="information")

    def action_toggle_dry_run(self) -> None:
        self.dry_run = not self.dry_run
        self.notify(f"Dry-run: {'ON' if self.dry_run else 'OFF'}", severity="information")

    def notify_step(self, step_name: str, msg: str) -> None:
        """Called by steps to report progress (logged, not always notified)."""
        log.info("[%s] %s", step_name, msg)

    def _step_done(self, name: str) -> bool:
        return is_step_done(name)

    def export_recovery(self) -> None:
        """Export secrets to a recovery bundle."""
        try:
            path = export_recovery_bundle()
            self.notify(
                f"Recovery bundle written to {path}\n"
                "Copy it somewhere safe and offline, then delete from the Pi.",
                title="🔐 Recovery bundle",
                severity="information",
                timeout=15,
            )
        except Exception as e:
            self.notify(f"Failed: {e}", severity="error")


def run_app(
    dry_run: bool = False,
    force: bool = False,
    debug: bool = False,
) -> None:
    """Launch the TUI app."""
    app = HomeCloudApp(dry_run=dry_run, force=force, debug=debug)
    app.run()


def export_secrets(output: str | None = None) -> None:
    """CLI subcommand: export recovery bundle."""
    path = Path(output) if output else None
    result = export_recovery_bundle(path)
    print(f"Recovery bundle written to: {result}")
    print("Store it somewhere safe and offline. Delete it from the Pi after saving.")


def import_secrets(path: str) -> None:
    """CLI subcommand: import recovery bundle."""
    from .config import import_recovery_bundle
    cfg = import_recovery_bundle(Path(path))
    print(f"Imported config. Nextcloud domain: {cfg.nextcloud_domain or '(not set)'}")
    print("Run 'homecloud' to continue installation.")
