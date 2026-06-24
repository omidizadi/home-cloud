"""Shared UI helpers for Home Cloud screens."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Center, Middle
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class ConfirmScreen(ModalScreen[bool]):
    """A yes/no confirmation modal.

    Replacement for the non-existent `textual.question.Question`.
    Push with `await app.push_screen_wait(ConfirmScreen(prompt))` — returns
    True for "Yes", False for "No" / Escape.
    """

    DEFAULT_CSS = """
    ConfirmScreen {
        align: center middle;
    }
    ConfirmScreen Center {
        width: auto;
        max-width: 70;
        height: auto;
        padding: 1 2;
        border: round $warning;
        background: $surface;
    }
    ConfirmScreen Label {
        width: 100%;
        content-align: center middle;
        margin-bottom: 1;
    }
    ConfirmScreen .buttons {
        align: center middle;
        height: 3;
    }
    ConfirmScreen .buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [("escape", "no", "No")]

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self.prompt = prompt

    def compose(self) -> ComposeResult:
        with Center():
            with Middle():
                yield Label(self.prompt)
                with Container(classes="buttons"):
                    yield Button("✅ Yes", id="btn-yes", variant="success")
                    yield Button("❌ No", id="btn-no", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-yes")

    def action_no(self) -> None:
        self.dismiss(False)


async def confirm(app, prompt: str) -> bool:
    """Show a confirmation modal and await the user's answer."""
    result = await app.push_screen_wait(ConfirmScreen(prompt))
    return bool(result)
