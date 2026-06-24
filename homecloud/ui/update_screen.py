"""Update screen — update homecloud, Nextcloud, bot deps, restic, Samba."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, RichLog

from ..constants import BOT_VENV, INSTALL_DIR, VENV_DIR
from ..utils import run, which


class UpdateScreen(Screen):
    DEFAULT_CSS = """
    UpdateScreen {
        align: center middle;
    }
    UpdateScreen Container {
        width: 90;
        height: 85%;
        padding: 1;
        border: round $primary;
    }
    UpdateScreen RichLog {
        height: 1fr;
        border: solid $surface;
    }
    UpdateScreen .actions {
        height: auto;
        align: center middle;
        padding: 1;
    }
    UpdateScreen .actions Button {
        margin: 0 1;
    }
    """

    BINDINGS = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container():
            yield Label("🔄 Update", id="title")
            yield RichLog(id="log", markup=True)
            with Container(classes="actions"):
                yield Button("📦 homecloud", id="btn-self", variant="primary")
                yield Button("☁️ Nextcloud", id="btn-nc", variant="default")
                yield Button("🤖 Bot deps", id="btn-bot", variant="default")
                yield Button("🔐 restic", id="btn-restic", variant="default")
                yield Button("📁 Samba", id="btn-samba", variant="default")
                yield Button("✨ Update all", id="btn-all", variant="success")
                yield Button("↩️ Back", id="btn-back", variant="default")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-self":
            self.run_worker(self._update_self)
        elif bid == "btn-nc":
            self.run_worker(self._update_nextcloud)
        elif bid == "btn-bot":
            self.run_worker(self._update_bot)
        elif bid == "btn-restic":
            self.run_worker(self._update_restic)
        elif bid == "btn-samba":
            self.run_worker(self._update_samba)
        elif bid == "btn-all":
            self.run_worker(self._update_all)
        elif bid == "btn-back":
            self.app.pop_screen()

    def _log(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(msg)

    async def _confirm(self, prompt: str) -> bool:
        """Ask the user for confirmation via a modal dialog."""
        from textual.question import Question

        result = await self.app.push_screen_wait(Question(prompt))
        return bool(result)

    # ── Individual updaters ───────────────────────────────────────────────────

    async def _update_self(self) -> None:
        self._log("\n[bold cyan]━━ 📦 homecloud ━━[/]")
        if self.app.dry_run:
            self._log("[dim]dry-run: would git pull + pip install[/]")
            return
        if not await self._confirm("Update homecloud? (git pull + pip install)"):
            self._log("[dim]skipped[/]")
            return
        r = run(f"git -C {INSTALL_DIR} pull --ff-only", capture=True, sudo=True)
        if r.stdout:
            self._log(r.stdout.strip())
        if r.stderr:
            self._log(r.stderr.strip())
        r = run(f"{VENV_DIR}/bin/pip install --quiet -e {INSTALL_DIR}", capture=True, sudo=True)
        if r.ok:
            self._log("[green]✓ homecloud updated. Re-run 'homecloud' to apply.[/]")
        else:
            self._log(f"[red]✗ {r.stderr}[/]")

    async def _update_nextcloud(self) -> None:
        self._log("\n[bold cyan]━━ ☁️ Nextcloud (AIO) ━━[/]")
        if self.app.dry_run:
            self._log("[dim]dry-run: would run occ upgrade + maintenance:mode[/]")
            return
        # Check if Nextcloud container is running
        nc_status = run(
            "docker inspect --format='{{.State.Status}}' nextcloud-aio-nextcloud 2>/dev/null",
            capture=True,
        ).stdout.strip()
        if nc_status != "running":
            self._log("[red]✗ Nextcloud container is not running. Start it via AIO panel first.[/]")
            return

        if not await self._confirm(
            "Update Nextcloud? This will:\n"
            "  1. Put Nextcloud in maintenance mode\n"
            "  2. Run occ upgrade\n"
            "  3. Take Nextcloud offline briefly"
        ):
            self._log("[dim]skipped[/]")
            return

        self._log("[cyan]Checking for available updates...[/]")
        r = run(
            "docker exec --user www-data nextcloud-aio-nextcloud php occ update:check",
            capture=True, sudo=True, timeout=60,
        )
        self._log(r.stdout.strip() or r.stderr.strip())

        if "up to date" in r.stdout.lower():
            self._log("[green]✓ Nextcloud is up to date.[/]")
            return

        if not await self._confirm("Updates are available. Proceed with upgrade?"):
            self._log("[dim]skipped[/]")
            return

        self._log("[cyan]Enabling maintenance mode...[/]")
        run(
            "docker exec --user www-data nextcloud-aio-nextcloud php occ maintenance:mode --on",
            sudo=True, dry_run=self.app.dry_run, capture=True,
        )

        self._log("[cyan]Running upgrade...[/]")
        r = run(
            "docker exec --user www-data nextcloud-aio-nextcloud php occ upgrade",
            capture=True, sudo=True, timeout=600,
        )
        self._log(r.stdout.strip() or r.stderr.strip())

        self._log("[cyan]Disabling maintenance mode...[/]")
        run(
            "docker exec --user www-data nextcloud-aio-nextcloud php occ maintenance:mode --off",
            sudo=True, dry_run=self.app.dry_run, capture=True,
        )

        if r.ok:
            self._log("[green]✓ Nextcloud upgraded.[/]")
        else:
            self._log("[red]✗ Upgrade may have failed. Check output above.[/]")

    async def _update_bot(self) -> None:
        self._log("\n[bold cyan]━━ 🤖 Bot deps ━━[/]")
        if self.app.dry_run:
            self._log("[dim]dry-run: would pip upgrade + restart ncbot[/]")
            return
        if not await self._confirm(
            "Update Telegram bot dependencies? (pip upgrade + restart bot)"
        ):
            self._log("[dim]skipped[/]")
            return
        r = run(
            f"{BOT_VENV}/bin/pip install --upgrade --quiet "
            "python-telegram-bot APScheduler requests",
            dry_run=self.app.dry_run, capture=True, timeout=180,
        )
        if r.ok or self.app.dry_run:
            self._log("[green]✓ bot deps updated. Restarting bot...[/]")
            run("systemctl restart ncbot", sudo=True, dry_run=self.app.dry_run)
            self._log("[green]✓ bot restarted[/]")
        else:
            self._log(f"[red]✗ {r.stderr}[/]")

    async def _update_restic(self) -> None:
        self._log("\n[bold cyan]━━ 🔐 restic ━━[/]")
        if not which("restic"):
            self._log("[red]✗ restic not installed[/]")
            return
        current = run("restic version", capture=True).stdout.strip()
        self._log(f"Current: {current}")

        if self.app.dry_run:
            self._log("[dim]dry-run: would apt update + apt install --only-upgrade restic[/]")
            return

        if not await self._confirm("Update restic via apt?"):
            self._log("[dim]skipped[/]")
            return

        self._log("[cyan]Running apt update...[/]")
        run("apt-get update -qq", sudo=True, dry_run=self.app.dry_run, timeout=120, capture=True)

        self._log("[cyan]Upgrading restic...[/]")
        r = run(
            "apt-get install -y --only-upgrade restic",
            sudo=True, dry_run=self.app.dry_run, timeout=120, capture=True,
        )
        if r.ok:
            new = run("restic version", capture=True).stdout.strip()
            self._log(f"[green]✓ restic updated: {new}[/]")
        else:
            self._log(f"[red]✗ {r.stderr}[/]")

    async def _update_samba(self) -> None:
        self._log("\n[bold cyan]━━ 📁 Samba ━━[/]")
        if not which("smbd"):
            self._log("[red]✗ smbd not installed[/]")
            return
        current = run("smbd --version", capture=True).stdout.strip()
        self._log(f"Current: {current}")

        if self.app.dry_run:
            self._log("[dim]dry-run: would apt update + apt install --only-upgrade samba[/]")
            return

        if not await self._confirm("Update Samba via apt? (brief share interruption)"):
            self._log("[dim]skipped[/]")
            return

        self._log("[cyan]Running apt update...[/]")
        run("apt-get update -qq", sudo=True, dry_run=self.app.dry_run, timeout=120, capture=True)

        self._log("[cyan]Upgrading Samba...[/]")
        r = run(
            "apt-get install -y --only-upgrade samba samba-common-bin",
            sudo=True, dry_run=self.app.dry_run, timeout=120, capture=True,
        )
        if r.ok:
            self._log("[cyan]Restarting smbd...[/]")
            run("systemctl restart smbd", sudo=True, dry_run=self.app.dry_run)
            new = run("smbd --version", capture=True).stdout.strip()
            self._log(f"[green]✓ Samba updated: {new}[/]")
        else:
            self._log(f"[red]✗ {r.stderr}[/]")

    async def _update_all(self) -> None:
        """Run all updaters in sequence, each with its own confirmation."""
        self._log("\n[bold magenta]━━ ✨ Update All ━━[/]")
        self._log("[dim]Each component will ask for confirmation before updating.[/]\n")
        await self._update_self()
        await self._update_nextcloud()
        await self._update_bot()
        await self._update_restic()
        await self._update_samba()
        self._log("\n[bold green]━━ All updates complete ━━[/]")
