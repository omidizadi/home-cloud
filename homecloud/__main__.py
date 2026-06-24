"""Entry point for the homecloud CLI."""

from __future__ import annotations

import argparse

from .app import export_secrets, import_secrets, run_app
from .constants import INSTALL_DIR, VENV_DIR
from .utils import run


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="homecloud",
        description="Interactive installer & manager for a Raspberry Pi 5 home cloud.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing (safe preview).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run steps even if already completed.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging.",
    )

    sub = parser.add_subparsers(dest="command")

    # secrets export
    p_export = sub.add_parser("secrets", help="Manage secrets recovery bundle.")
    p_export_sub = p_export.add_subparsers(dest="secrets_command", required=True)
    p_exp = p_export_sub.add_parser("export", help="Export recovery bundle.")
    p_exp.add_argument("-o", "--output", default=None, help="Output path (default: ./homecloud-recovery-bundle.json)")
    p_imp = p_export_sub.add_parser("import", help="Import recovery bundle.")
    p_imp.add_argument("path", help="Path to recovery bundle JSON.")

    # update
    p_update = sub.add_parser("update", help="Update the homecloud app itself (git pull + pip install).")
    p_update.add_argument("--check", action="store_true", help="Only check for updates, don't apply them.")
    p_update.add_argument("--all", action="store_true", help="Update all components (homecloud, Nextcloud, bot, restic, Samba).")
    p_update.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompts (use with --all).")

    args = parser.parse_args()

    if args.command == "secrets":
        if args.secrets_command == "export":
            export_secrets(args.output)
        elif args.secrets_command == "import":
            import_secrets(args.path)
        return

    if args.command == "update":
        if getattr(args, "all", False):
            _run_update_all(yes=getattr(args, "yes", False))
        else:
            _run_self_update(check_only=getattr(args, "check", False))
        return

    run_app(dry_run=args.dry_run, force=args.force, debug=args.debug)


def _run_self_update(check_only: bool = False) -> None:
    """Pull latest from GitHub and reinstall the package."""
    print("📦 Updating homecloud...\n")

    # Check for updates
    r = run(f"git -C {INSTALL_DIR} fetch --quiet", capture=True, sudo=True)
    if not r.ok:
        print(f"❌ git fetch failed: {r.stderr}")
        return

    r = run(f"git -C {INSTALL_DIR} status -uno --porcelain", capture=True)
    local_changes = bool(r.stdout.strip())

    r = run(f"git -C {INSTALL_DIR} log HEAD..origin/main --oneline", capture=True)
    new_commits = r.stdout.strip()

    if not new_commits:
        print("✅ Already up to date.")
        return

    print(f"📥 {len(new_commits.splitlines())} new commit(s):\n{new_commits}\n")

    if check_only:
        print("Run 'homecloud update' to apply.")
        return

    if local_changes:
        print("⚠️  Local changes detected in install dir. Stashing...")
        run(f"git -C {INSTALL_DIR} stash", capture=True, sudo=True)

    # Pull
    r = run(f"git -C {INSTALL_DIR} pull --ff-only", capture=True, sudo=True)
    print(r.stdout or r.stderr)

    # Reinstall
    r = run(f"{VENV_DIR}/bin/pip install --quiet -e {INSTALL_DIR}", capture=True, sudo=True)
    if r.ok:
        print("\n✅ homecloud updated. Re-run 'homecloud' to use the new version.")
    else:
        print(f"\n❌ pip install failed: {r.stderr}")


def _confirm(prompt: str, yes: bool = False) -> bool:
    """Yes/no confirmation prompt for CLI use."""
    if yes:
        print(f"{prompt} [y/N] y (auto)")
        return True
    try:
        answer = input(f"{prompt} [y/N] ").strip().lower()
        return answer in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def _run_update_all(yes: bool = False) -> None:
    """Update all components from the CLI (homecloud, Nextcloud, bot, restic, Samba)."""
    from .constants import BOT_VENV
    from .utils import which

    # ── 1. homecloud ──
    print("\n" + "=" * 50)
    print("📦 homecloud")
    print("=" * 50)
    if _confirm("Update homecloud? (git pull + pip install)", yes):
        _run_self_update()
    else:
        print("⏭️  skipped")

    # ── 2. Nextcloud ──
    print("\n" + "=" * 50)
    print("☁️  Nextcloud")
    print("=" * 50)
    nc_status = run(
        "docker inspect --format='{{.State.Status}}' nextcloud-aio-nextcloud 2>/dev/null",
        capture=True,
    ).stdout.strip()
    if nc_status != "running":
        print("❌ Nextcloud container is not running. Start it via AIO panel first.")
    elif _confirm("Update Nextcloud? (maintenance mode + occ upgrade)", yes):
        print("Checking for updates...")
        r = run(
            "docker exec --user www-data nextcloud-aio-nextcloud php occ update:check",
            capture=True, sudo=True, timeout=60,
        )
        print(r.stdout.strip() or r.stderr.strip())
        if "up to date" in r.stdout.lower():
            print("✅ Nextcloud is up to date.")
        elif _confirm("Updates available. Proceed with upgrade?", yes):
            print("Enabling maintenance mode...")
            run(
                "docker exec --user www-data nextcloud-aio-nextcloud php occ maintenance:mode --on",
                sudo=True, capture=True,
            )
            print("Running upgrade...")
            r = run(
                "docker exec --user www-data nextcloud-aio-nextcloud php occ upgrade",
                capture=True, sudo=True, timeout=600,
            )
            print(r.stdout.strip() or r.stderr.strip())
            run(
                "docker exec --user www-data nextcloud-aio-nextcloud php occ maintenance:mode --off",
                sudo=True, capture=True,
            )
            print("✅ Nextcloud upgraded." if r.ok else "❌ Upgrade may have failed.")
    else:
        print("⏭️  skipped")

    # ── 3. Bot deps ──
    print("\n" + "=" * 50)
    print("🤖 Bot deps")
    print("=" * 50)
    if _confirm("Update Telegram bot deps? (pip upgrade + restart)", yes):
        r = run(
            f"{BOT_VENV}/bin/pip install --upgrade --quiet "
            "python-telegram-bot APScheduler requests",
            capture=True, timeout=180,
        )
        if r.ok:
            run("systemctl restart ncbot", sudo=True)
            print("✅ Bot deps updated + restarted.")
        else:
            print(f"❌ {r.stderr}")
    else:
        print("⏭️  skipped")

    # ── 4. restic ──
    print("\n" + "=" * 50)
    print("🔐 restic")
    print("=" * 50)
    if not which("restic"):
        print("❌ restic not installed")
    elif _confirm("Update restic via apt?", yes):
        run("apt-get update -qq", sudo=True, timeout=120, capture=True)
        r = run(
            "apt-get install -y --only-upgrade restic",
            sudo=True, timeout=120, capture=True,
        )
        if r.ok:
            new = run("restic version", capture=True).stdout.strip()
            print(f"✅ restic updated: {new}")
        else:
            print(f"❌ {r.stderr}")
    else:
        print("⏭️  skipped")

    # ── 5. Samba ──
    print("\n" + "=" * 50)
    print("📁 Samba")
    print("=" * 50)
    if not which("smbd"):
        print("❌ smbd not installed")
    elif _confirm("Update Samba via apt? (brief share interruption)", yes):
        run("apt-get update -qq", sudo=True, timeout=120, capture=True)
        r = run(
            "apt-get install -y --only-upgrade samba samba-common-bin",
            sudo=True, timeout=120, capture=True,
        )
        if r.ok:
            run("systemctl restart smbd", sudo=True)
            new = run("smbd --version", capture=True).stdout.strip()
            print(f"✅ Samba updated: {new}")
        else:
            print(f"❌ {r.stderr}")
    else:
        print("⏭️  skipped")

    print("\n" + "=" * 50)
    print("✨ All updates complete.")
    print("=" * 50)


if __name__ == "__main__":
    main()
