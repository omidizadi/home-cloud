"""Home Cloud — plain CLI menu (no TUI framework).

Replaces the previous Textual multi-screen app, which rendered blank with no
errors.  This version uses only print()/input() so it cannot silently fail to
draw — if something goes wrong you see a traceback.
"""

from __future__ import annotations

from pathlib import Path

from . import __version__
from .config import Config, export_recovery_bundle, generate_password, load_config, save_config, validate
from .constants import CONFIG_DIR, INSTALL_DIR, LOG_DIR, STATE_DIR, VENV_DIR
from .services import container_status, unit_status
from .steps import ALL_STEPS
from .utils import has_sudo, is_pi5, is_root, log, run, setup_logging, which
from .utils import file_exists_sudo, read_file_sudo
from .utils.state import clear_all, is_step_done


# ── helpers ───────────────────────────────────────────────────────────────────


def _confirm(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input(prompt + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if not answer:
        return default
    return answer in ("y", "yes")


def _pause() -> None:
    try:
        input("\nPress Enter to return to the menu...")
    except (EOFError, KeyboardInterrupt):
        print()


def _header(title: str) -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _ok(msg: str) -> None:
    print(f"  ✅ {msg}")


def _fail(msg: str) -> None:
    print(f"  ❌ {msg}")


def _info(msg: str) -> None:
    print(f"  ℹ️  {msg}")


# ── the app ───────────────────────────────────────────────────────────────────


class HomeCloudApp:
    """A plain CLI app — holds config & flags, exposes menu actions."""

    def __init__(self, dry_run: bool = False, force: bool = False, debug: bool = False) -> None:
        self.dry_run = dry_run
        self.force = force
        self._debug = debug
        setup_logging(debug=debug)
        self.cfg: Config = load_config()

    # -- step helpers (steps expect an `app` with these attrs) -----------------

    def notify_step(self, step_name: str, msg: str) -> None:
        log.info("[%s] %s", step_name, msg)

    def _step_done(self, name: str) -> bool:
        return is_step_done(name)

    def export_recovery(self) -> None:
        try:
            path = export_recovery_bundle()
            print(f"\n🔐 Recovery bundle written to {path}")
            print("Copy it somewhere safe and offline, then delete from the Pi.")
        except Exception as e:
            _fail(f"Failed: {e}")

    # -- menu actions ----------------------------------------------------------

    def menu_install(self) -> None:
        _header("📥 Install / Configure")
        self.cfg = load_config()

        if not self.cfg.is_complete():
            _fail("Configuration incomplete.")
            missing = self.cfg.missing_fields()
            print(f"  Missing: {', '.join(missing)}")
            print("  Run option 6 (Edit Config) first.")
            _pause()
            return

        print(f"  Dry run: {self.dry_run}")
        print(f"  Steps:   {len(ALL_STEPS)}")
        print()
        if not _confirm("Start installation?"):
            return

        failed: list[str] = []
        for i, StepClass in enumerate(ALL_STEPS, 1):
            step = StepClass(self)
            print(f"\n━━━ Step {i}/{len(ALL_STEPS)}: {step.label} ━━━")

            if step.is_done() and not self.force:
                _ok("already done (skip)")
                continue

            if not step.deps_satisfied():
                missing = [d for d in step.depends_on if not is_step_done(d)]
                _fail(f"dependencies not met: {missing}")
                failed.append(step.name)
                continue

            try:
                result = step.run()
            except Exception as e:
                _fail(f"EXCEPTION: {e}")
                log.exception("step %s failed", step.name)
                failed.append(step.name)
                continue

            if result.success:
                _ok(result.message)
                if result.details:
                    for line in result.details.splitlines():
                        print(f"    {line}")
            else:
                _fail(result.message)
                if result.details:
                    for line in result.details.splitlines():
                        print(f"    {line}")
                failed.append(step.name)

        print()
        print("=" * 60)
        if failed:
            _fail(f"Completed with {len(failed)} failed step(s): {failed}")
            print("  Use Repair (option 4) to retry failed steps.")
        else:
            _ok("All steps completed successfully!")
            print("  Next: open https://<pi-ip>:8080 to finish Nextcloud AIO setup.")
        _pause()

    def menu_status(self) -> None:
        _header("📊 Status Dashboard")

        # System
        print("━━ System ━━")
        uptime = run("uptime -p", capture=True).stdout.strip() or "N/A"
        cpu_temp = run("vcgencmd measure_temp 2>/dev/null | cut -d= -f2", capture=True).stdout.strip() or "N/A"
        mem = run("free -h | awk '/^Mem:/ {print $3\"/\"$2}'", capture=True).stdout.strip() or "N/A"
        print(f"  Uptime:   {uptime}")
        print(f"  CPU temp: {cpu_temp}")
        print(f"  Memory:   {mem}")

        # Disk
        print("\n━━ Disk ━━")
        ssd = run("df -h /mnt/ncdata 2>/dev/null | awk 'NR==2 {print $3\"/\"$2\" (\"$5\")\"}'", capture=True).stdout.strip()
        sd = run("df -h / 2>/dev/null | awk 'NR==2 {print $3\"/\"$2\" (\"$5\")\"}'", capture=True).stdout.strip()
        print(f"  SSD (/mnt/ncdata): {ssd or 'not mounted'}")
        print(f"  SD card (/):       {sd or 'N/A'}")

        # Services
        print("\n━━ Services ━━")
        for svc in ["docker", "smbd", "ncbot", "cron"]:
            st = unit_status(svc)
            print(f"  {'✅' if st == 'active' else '❌'} {svc}: {st}")

        # Containers
        print("\n━━ Containers ━━")
        for c in ["nextcloud-aio-mastercontainer", "nextcloud-aio-nextcloud", "nextcloud-aio-talk"]:
            st = container_status(c)
            print(f"  {'✅' if st == 'running' else '❌'} {c}: {st}")

        # Install steps
        print("\n━━ Install Steps ━━")
        for StepClass in ALL_STEPS:
            step = StepClass(self)
            done = step.is_done()
            try:
                status = step.status()
                health = "OK" if status.success else "ISSUE"
            except Exception:
                health = "?"
            print(f"  {'✅' if done else '⬜'} {step.label}: {health}")

        # Backup
        print("\n━━ Backup ━━")
        backup_log = Path("/var/log/nextcloud-s3-backup.log")
        if file_exists_sudo(backup_log):
            content = read_file_sudo(backup_log) or ""
            if "=== Backup finished" in content.split("=== Backup started")[-1]:
                _ok("Last backup completed")
            else:
                print("  ⚠️  Last backup may be incomplete")
            lines = [ln for ln in content.splitlines() if ln.strip()]
            if lines:
                print(f"  Last log line: {lines[-1]}")
        else:
            _info("No backup log found")

        _pause()

    def menu_update(self) -> None:
        while True:
            _header("🔄 Update")
            print("  1. homecloud (git pull + pip install)")
            print("  2. Nextcloud (AIO)")
            print("  3. Telegram bot deps")
            print("  4. restic")
            print("  5. Samba")
            print("  6. Update all")
            print("  0. Back")
            choice = input("\nChoice: ").strip()
            if choice == "0":
                return
            actions = {
                "1": self._update_self,
                "2": self._update_nextcloud,
                "3": self._update_bot,
                "4": self._update_restic,
                "5": self._update_samba,
                "6": self._update_all,
            }
            action = actions.get(choice)
            if action:
                action()
            else:
                _fail("Invalid choice")

    def menu_repair(self) -> None:
        _header("🔧 Repair")
        print("  1. Check all steps")
        print("  2. Repair all failed")
        print("  0. Back")
        choice = input("\nChoice: ").strip()
        if choice == "1":
            self._check_all()
        elif choice == "2":
            self._repair_all()
        elif choice == "0":
            return
        else:
            _fail("Invalid choice")

    def menu_uninstall(self) -> None:
        _header("🗑️ Uninstall")
        print("⚠️  This removes ALL services, containers, AND the homecloud")
        print("    code itself (repo, venv, CLI wrapper, config, state, logs).")
        print("    Your data on the SSD (/mnt/ncdata) will NOT be touched.")
        if not _confirm("\nProceed with full uninstall?"):
            return

        print()
        for StepClass in reversed(ALL_STEPS):
            step = StepClass(self)
            print(f"Removing: {step.label}...")
            try:
                result = step.undo()
                if result.success:
                    _ok(result.message)
                else:
                    _fail(result.message)
            except Exception as e:
                _fail(f"EXCEPTION: {e}")

        clear_all()
        print()
        self._nuke_self()
        _ok("Uninstall complete. Your data is safe on the SSD at /mnt/ncdata")
        print("homecloud is gone. Reinstall with the install.sh bootstrap script.")
        _pause()

    def _nuke_self(self) -> None:
        """Remove the homecloud installation itself: repo, venv, wrapper, config, logs."""
        _header("🧹 Removing homecloud code")
        targets = [
            ("repo clone", INSTALL_DIR),
            ("virtualenv", VENV_DIR),
            ("CLI wrapper", Path("/usr/local/bin/homecloud")),
            ("config dir", CONFIG_DIR),
            ("state dir", STATE_DIR),
            ("log dir", LOG_DIR),
        ]
        for label, path in targets:
            if not path.exists():
                _info(f"{label}: already gone ({path})")
                continue
            print(f"  Removing {label}: {path}")
            if self.dry_run:
                _info("dry-run: skipped")
                continue
            r = run(f"rm -rf {path}", capture=True, sudo=True)
            if r.ok:
                _ok(f"{label} removed")
            else:
                _fail(f"{label}: {r.stderr.strip()}")

    def menu_config(self) -> None:
        _header("⚙️ Edit Config")
        cfg = self.cfg
        fields_map = [
            ("ssd_device", "SSD device (e.g. /dev/sda)"),
            ("duckdns_domain", "DuckDNS subdomain (e.g. omid)"),
            ("duckdns_token", "DuckDNS token"),
            ("aws_access_key_id", "AWS Access Key ID"),
            ("aws_secret_access_key", "AWS Secret Access Key"),
            ("s3_bucket", "S3 bucket name"),
            ("s3_region", "S3 region (default: eu-central-1)"),
            ("restic_password", "restic password (blank=generate)"),
            ("telegram_bot_token", "Telegram bot token (123:ABC...)"),
            ("telegram_chat_id", "Telegram chat ID"),
            ("nextcloud_admin_password", "Nextcloud admin password (blank=generate)"),
            ("samba_user", "Samba username"),
            ("samba_password", "Samba password (blank=generate)"),
            ("wifi_ssid", "WiFi SSID (blank=Ethernet)"),
            ("wifi_password", "WiFi password"),
            ("timezone", "Timezone (default: Europe/Berlin)"),
        ]

        # Show detected devices to help pick SSD
        print("Detected devices:")
        r = run("lsblk -dln -o NAME,SIZE,TYPE,MODEL", capture=True)
        if r.ok:
            for ln in r.stdout.strip().splitlines()[:10]:
                print(f"  /dev/{ln}")
        else:
            print("  (could not detect)")
        print()

        for attr, label in fields_map:
            current = getattr(cfg, attr, "")
            prompt = f"  {label}"
            if current:
                # mask secrets
                if any(s in attr for s in ("password", "token", "secret")):
                    shown = current[:2] + "***" if len(current) > 2 else "***"
                    prompt += f" [{shown}]"
                else:
                    prompt += f" [{current}]"
            prompt += ": "
            try:
                val = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if val:
                setattr(cfg, attr, val)

        # Generate passwords for blank secret fields
        if not cfg.restic_password:
            cfg.restic_password = generate_password()
            print(f"  Generated restic password: {cfg.restic_password}")
        if not cfg.nextcloud_admin_password:
            cfg.nextcloud_admin_password = generate_password(20)
            print(f"  Generated Nextcloud admin password: {cfg.nextcloud_admin_password}")
        if not cfg.samba_password:
            cfg.samba_password = generate_password(20)
            print(f"  Generated Samba password: {cfg.samba_password}")

        errors = validate(cfg)
        if errors:
            _fail("Validation errors:")
            for e in errors:
                print(f"    - {e}")
            if not _confirm("\nSave anyway?"):
                _pause()
                return
        save_config(cfg, dry_run=self.dry_run)
        self.cfg = cfg
        _ok("Configuration saved")
        _pause()

    # -- repair helpers --------------------------------------------------------

    def _check_all(self) -> None:
        print("\n━━ Step Health Check ━━")
        failed: list[str] = []
        for StepClass in ALL_STEPS:
            step = StepClass(self)
            done = step.is_done()
            try:
                status = step.status()
                ok = status.success
                msg = status.message
            except Exception as e:
                ok = False
                msg = str(e)
            icon = "✅" if ok else "❌"
            done_icon = "✓" if done else "⬜"
            print(f"  {icon} [{done_icon}] {step.label}: {msg}")
            if not ok:
                failed.append(step.name)
        print(f"\nFailed: {len(failed)}")
        _pause()

    def _repair_all(self) -> None:
        print("\n━━ Repairing failed steps ━━")
        for StepClass in ALL_STEPS:
            step = StepClass(self)
            try:
                status = step.status()
                if status.success:
                    continue
            except Exception:
                pass
            print(f"Repairing: {step.label}...")
            try:
                result = step.repair()
                if result.success:
                    _ok(result.message)
                else:
                    _fail(result.message)
            except Exception as e:
                _fail(f"EXCEPTION: {e}")
        print("\nRepair complete.")
        _pause()

    # -- update helpers --------------------------------------------------------

    def _update_self(self) -> None:
        print("\n━━ 📦 homecloud ━━")
        if self.dry_run:
            _info("dry-run: would git pull + pip install")
            return
        if not _confirm("Update homecloud? (git pull + pip install)"):
            return
        r = run(f"git -C {INSTALL_DIR} pull --ff-only", capture=True, sudo=True)
        print(r.stdout.strip() or r.stderr.strip())
        r = run(f"{VENV_DIR}/bin/pip install --quiet -e {INSTALL_DIR}", capture=True, sudo=True)
        if r.ok:
            _ok("homecloud updated. Re-run 'homecloud' to apply.")
        else:
            _fail(r.stderr)

    def _update_nextcloud(self) -> None:
        print("\n━━ ☁️ Nextcloud (AIO) ━━")
        if self.dry_run:
            _info("dry-run: would run occ upgrade + maintenance:mode")
            return
        nc_status = run(
            "docker inspect --format='{{.State.Status}}' nextcloud-aio-nextcloud 2>/dev/null",
            capture=True,
        ).stdout.strip()
        if nc_status != "running":
            _fail("Nextcloud container is not running. Start it via AIO panel first.")
            return
        if not _confirm(
            "Update Nextcloud? This will:\n"
            "  1. Put Nextcloud in maintenance mode\n"
            "  2. Run occ upgrade\n"
            "  3. Take Nextcloud offline briefly"
        ):
            return
        _info("Checking for available updates...")
        r = run(
            "docker exec --user www-data nextcloud-aio-nextcloud php occ update:check",
            capture=True, sudo=True, timeout=60,
        )
        print(r.stdout.strip() or r.stderr.strip())
        if "up to date" in r.stdout.lower():
            _ok("Nextcloud is up to date.")
            return
        if not _confirm("Updates are available. Proceed with upgrade?"):
            return
        _info("Enabling maintenance mode...")
        run("docker exec --user www-data nextcloud-aio-nextcloud php occ maintenance:mode --on", sudo=True, capture=True)
        _info("Running upgrade...")
        r = run(
            "docker exec --user www-data nextcloud-aio-nextcloud php occ upgrade",
            capture=True, sudo=True, timeout=600,
        )
        print(r.stdout.strip() or r.stderr.strip())
        _info("Disabling maintenance mode...")
        run("docker exec --user www-data nextcloud-aio-nextcloud php occ maintenance:mode --off", sudo=True, capture=True)
        if r.ok:
            _ok("Nextcloud upgraded.")
        else:
            _fail("Upgrade may have failed. Check output above.")

    def _update_bot(self) -> None:
        print("\n━━ 🤖 Bot deps ━━")
        if self.dry_run:
            _info("dry-run: would pip upgrade + restart ncbot")
            return
        if not _confirm("Update Telegram bot dependencies? (pip upgrade + restart bot)"):
            return
        from .constants import BOT_VENV
        r = run(
            f"{BOT_VENV}/bin/pip install --upgrade --quiet "
            "python-telegram-bot APScheduler requests",
            capture=True, timeout=180,
        )
        if r.ok:
            _ok("bot deps updated. Restarting bot...")
            run("systemctl restart ncbot", sudo=True)
            _ok("bot restarted")
        else:
            _fail(r.stderr)

    def _update_restic(self) -> None:
        print("\n━━ 🔐 restic ━━")
        if not which("restic"):
            _fail("restic not installed")
            return
        current = run("restic version", capture=True).stdout.strip()
        print(f"Current: {current}")
        if self.dry_run:
            _info("dry-run: would apt update + apt install --only-upgrade restic")
            return
        if not _confirm("Update restic via apt?"):
            return
        _info("Running apt update...")
        run("apt-get update -qq", sudo=True, timeout=120, capture=True)
        _info("Upgrading restic...")
        r = run("apt-get install -y --only-upgrade restic", sudo=True, timeout=120, capture=True)
        if r.ok:
            new = run("restic version", capture=True).stdout.strip()
            _ok(f"restic updated: {new}")
        else:
            _fail(r.stderr)

    def _update_samba(self) -> None:
        print("\n━━ 📁 Samba ━━")
        if not which("smbd"):
            _fail("smbd not installed")
            return
        current = run("smbd --version", capture=True).stdout.strip()
        print(f"Current: {current}")
        if self.dry_run:
            _info("dry-run: would apt update + apt install --only-upgrade samba")
            return
        if not _confirm("Update Samba via apt? (brief share interruption)"):
            return
        _info("Running apt update...")
        run("apt-get update -qq", sudo=True, timeout=120, capture=True)
        _info("Upgrading Samba...")
        r = run("apt-get install -y --only-upgrade samba samba-common-bin", sudo=True, timeout=120, capture=True)
        if r.ok:
            _info("Restarting smbd...")
            run("systemctl restart smbd", sudo=True)
            new = run("smbd --version", capture=True).stdout.strip()
            _ok(f"Samba updated: {new}")
        else:
            _fail(r.stderr)

    def _update_all(self) -> None:
        print("\n━━ ✨ Update All ━━")
        self._update_self()
        self._update_nextcloud()
        self._update_bot()
        self._update_restic()
        self._update_samba()
        print("\n━━ All updates complete ━━")

    # -- main loop -------------------------------------------------------------

    def run(self) -> None:
        """Main menu loop."""
        # Pre-flight warnings
        if not is_pi5() and not self.dry_run:
            print("⚠️  Warning: this doesn't appear to be a Raspberry Pi 5. Proceed at your own risk.")
        if not (is_root() or has_sudo()):
            print("⚠️  Warning: no sudo access. Most install steps will fail.")
        if self.dry_run:
            print("ℹ️  Dry-run mode active — no commands will execute.")

        while True:
            print()
            print("=" * 60)
            print(f"  🏠 Home Cloud  v{__version__}")
            print("=" * 60)
            print("  1. 📥  Install / Configure")
            print("  2. 📊  Status Dashboard")
            print("  3. 🔄  Update")
            print("  4. 🔧  Repair")
            print("  5. 🗑️  Uninstall (full)")
            print("  6. ⚙️  Edit Config")
            print("  7. 🔐  Secrets: Export Recovery Bundle")
            print("  0. ❌  Quit")
            print()
            try:
                choice = input("Choice: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            actions = {
                "1": self.menu_install,
                "2": self.menu_status,
                "3": self.menu_update,
                "4": self.menu_repair,
                "5": self.menu_uninstall,
                "6": self.menu_config,
                "7": self.export_recovery,
            }
            if choice == "0":
                print("Bye 👋")
                break
            action = actions.get(choice)
            if action:
                try:
                    action()
                except Exception as e:
                    _fail(f"Unexpected error: {e}")
                    log.exception("menu action %s failed", choice)
                    _pause()
            else:
                _fail("Invalid choice")


# ── entry points (kept compatible with __main__.py) ─────────────────────────


def run_app(
    dry_run: bool = False,
    force: bool = False,
    debug: bool = False,
) -> None:
    """Launch the CLI app."""
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
