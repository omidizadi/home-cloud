"""Main menu screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label

from .. import __version__


class MainMenu(Screen):
    """The main menu of the Home Cloud TUI."""

    DEFAULT_CSS = """
    MainMenu {
        align: center middle;
    }
    MainMenu Container {
        width: 60;
        height: auto;
        padding: 1 2;
        border: round $primary;
    }
    MainMenu .title {
        text-align: center;
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }
    MainMenu .subtitle {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }
    MainMenu Button {
        width: 100%;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()

        with Container():
            yield Label("🏠 Home Cloud", id="title", classes="title")
            yield Label(
                f"v{__version__} — Nextcloud AIO manager for Raspberry Pi 5",
                classes="subtitle",
            )
            yield Button("📥  Install / Configure", id="btn-install", variant="primary")
            yield Button("📊  Status Dashboard", id="btn-status", variant="default")
            yield Button("🔄  Update", id="btn-update", variant="default")
            yield Button("🔧  Repair", id="btn-repair", variant="warning")
            yield Button("🗑️  Uninstall (conservative)", id="btn-uninstall", variant="error")
            yield Button("🔐  Secrets: Export Recovery Bundle", id="btn-export", variant="default")
            yield Button("❌  Quit", id="btn-quit", variant="default")

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app = self.app
        bid = event.button.id
        if bid == "btn-install":
            app.push_screen("install")
        elif bid == "btn-status":
            app.push_screen("status")
        elif bid == "btn-update":
            app.push_screen("update")
        elif bid == "btn-repair":
            app.push_screen("repair")
        elif bid == "btn-uninstall":
            app.push_screen("uninstall")
        elif bid == "btn-export":
            app.export_recovery()
        elif bid == "btn-quit":
            app.exit()
