# 🏠 Home Cloud

An interactive installer & manager for a **Raspberry Pi 5** home cloud built on
**Nextcloud AIO**, with nightly **deduplicated S3 Glacier Deep Archive** backups,
a **Samba** share, **DuckDNS**, **Nextcloud Talk** (video calls), and an
interactive **Telegram bot** for status reports.

> Designed for a Raspberry Pi 5 (8GB RAM, 128GB SD card) with a 5TB external SSD.
> Conservative uninstall: **never touches your data on the SSD**.

---

## ✨ Features

- **Nextcloud AIO** — photos (Memories), files, and Talk (1-1 video calls)
- **5TB SSD** as the data directory (SD card stays for OS/Docker only)
- **Samba share** — access the SSD for non-Nextcloud files without detaching it
- **DuckDNS** — free dynamic DNS + automatic Let's Encrypt TLS
- **Nextcloud Talk** — 1-1 video calls via AIO's built-in Coturn TURN server
- **Nightly restic backup → S3 Glacier Deep Archive** — block-level deduplication
  means you only pay for ~your actual data size, not `200GB × N nights`
- **Interactive Telegram bot** — daily reports + on-demand commands
  (`/status`, `/report`, `/backup`, `/runbackup`, `/logs`)
- **Reboot survival** — all services auto-start; Docker waits for SSD mount
- **Dry-run mode** — preview every command before executing
- **Recovery bundle** — export all secrets to a JSON file for offline safekeeping
- **Conservative uninstall** — removes apps/services, **keeps your data**

---

## 📋 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Raspberry Pi 5 (8GB)                   │
│                                                         │
│  ┌─────────────┐   ┌─────────────────────────────────┐  │
│  │  SD Card    │   │        5TB SSD (/mnt/ncdata)    │  │
│  │  (OS+Docker)│   │  ┌────────────┐ ┌────────────┐  │  │
│  │             │   │  │ Nextcloud  │ │ Samba share│  │  │
│  │             │   │  │ data dir   │ │ /files     │  │  │
│  │             │   │  └────────────┘ └────────────┘  │  │
│  │             │   │  ┌────────────────────────────┐ │  │
│  │             │   │  │ Borg backup (local)        │ │  │
│  │             │   │  └────────────────────────────┘ │  │
│  └─────────────┘   └─────────────────────────────────┘  │
│                                                         │
│  Services: Docker · Samba · ncbot (Telegram) · DuckDNS  │
└───────────────────────┬─────────────────────────────────┘
                        │
                        │ nightly restic (deduplicated)
                        ▼
              ┌───────────────────┐
              │  AWS S3 Glacier   │
              │  Deep Archive     │
              │  (~€0.20/mo for   │
              │   200GB)          │
              └───────────────────┘
```

---

## 🚀 Quick Start

### Step 0: Flash the OS (manual)

1. Download **Raspberry Pi Imager**
2. Choose **Raspberry Pi OS Lite (64-bit)** (Bookworm)
3. Click the gear icon ⚙️ to configure:
   - Enable SSH (use password auth)
   - Set hostname (e.g. `homecloud`)
   - Set username/password
   - Optionally configure WiFi
4. Flash to the 128GB SD card
5. Boot the Pi, SSH in

### Step 1: Run the installer

```bash
curl -fsSL https://raw.githubusercontent.com/omidizadi/home-cloud/main/install.sh | sudo bash
```

This clones the repo to `/opt/homecloud`, creates a virtualenv, and launches
the interactive TUI.

### Step 2: Use the TUI

| Menu option | What it does |
| :-- | :-- |
| **📥 Install / Configure** | First: edit config (SSD, DuckDNS, AWS, Telegram, etc.), then run all install steps |
| **📊 Status Dashboard** | Live view of containers, disk, services, backup, install steps |
| **🔄 Update** | Update homecloud itself, Nextcloud, bot deps, restic |
| **🔧 Repair** | Re-check and re-run any failed steps |
| **🗑️ Uninstall** | Conservative removal — **keeps data on SSD** |
| **🔐 Secrets: Export** | Save all secrets to a recovery JSON bundle |

### Step 3: Dry-run first (recommended)

```bash
homecloud --dry-run
```

This prints every command without executing — review what will happen before
running for real.

### Updating homecloud itself

There are two ways to update the homecloud app:

**From the TUI:** Main menu → 🔄 Update → "Update homecloud"

**From the command line (no TUI needed):**

```bash
# Check if updates are available
homecloud update --check

# Apply updates
homecloud update
```

This runs `git pull` in `/opt/homecloud` and reinstalls the package via the
virtualenv's pip. Re-run `homecloud` to use the new version.

### Updating all components

The Update screen and CLI can update **all** updatable components, each with a
confirmation prompt:

| Component | What it does |
| :-- | :-- |
| 📦 homecloud | `git pull` + `pip install` |
| ☁️ Nextcloud | `occ update:check` → maintenance mode → `occ upgrade` → maintenance mode off |
| 🤖 Bot deps | `pip install --upgrade` python-telegram-bot/APScheduler/requests + restart |
| 🔐 restic | `apt-get install --only-upgrade restic` |
| 📁 Samba | `apt-get install --only-upgrade samba` + restart smbd |

**From the TUI:** Main menu → 🔄 Update → "✨ Update all"

**From the command line:**

```bash
# Update everything (prompts for each component)
homecloud update --all

# Update everything, skip prompts (unattended)
homecloud update --all -y
```

---

## 📦 What gets installed (in order)

| # | Step | Description |
| :-: | :-- | :-- |
| 1 | **SSD mount** | Format (if needed) + mount 5TB SSD at `/mnt/ncdata`, add to fstab |
| 2 | **Docker** | Install Docker Engine, add user to docker group |
| 3 | **Nextcloud AIO** | Launch master container with `NEXTCLOUD_DATADIR` on SSD |
| 4 | **DuckDNS** | Dynamic DNS updater (5-min cron) for free domain + TLS |
| 5 | **Talk (Coturn)** | Guide enabling AIO's built-in TURN server for video calls |
| 6 | **Samba** | Network share at `/mnt/ncdata/files` for non-Nextcloud files |
| 7 | **WiFi** | (Optional) Connect via NetworkManager |
| 8 | **restic + S3** | Init repo, deploy nightly backup script (3 AM cron) |
| 9 | **Telegram bot** | Interactive bot as systemd service, daily 8 AM report |
| 10 | **Hardening** | Docker→SSD dependency, fsck, verify all services auto-start |

Each step is **idempotent** — running it twice is safe. Completed steps are
tracked via marker files in `/etc/homecloud/state/`.

---

## 🤖 Telegram Bot Commands

| Command | What you get |
| :-- | :-- |
| `/status` | CPU, RAM, temp, disk, NC container, last backup — instant |
| `/report` | Full daily digest: system + Nextcloud aggregate stats |
| `/users` | **Per-user** storage usage (quota, used space, last login) |
| `/backup` | Backup status + S3 snapshot list + log tail |
| `/runbackup` | Trigger a backup immediately |
| `/logs` | Last 30 lines of the backup log |
| `/help` | Show command menu |

A daily report is sent automatically at **08:00** (your timezone).

> **Per-user reports:** `/report` shows *aggregate* Nextcloud stats (total files,
> total users, free space). For a **per-user breakdown** (each user's storage
> consumption, quota, and last login), use `/users`. This requires the
> `usage_report` app to be enabled in Nextcloud (install it via
> **Apps → Tools → User usage report**). If the app isn't installed, `/users`
> falls back to listing usernames.

### Sample bot output

**`/status` — Quick health check**
```
⚡ Quick Status
🕐 24 Jun 2026 14:32

🖥 CPU: 3.2% load | 48.1°C temp
🧠 RAM: 1.2G/8.0G
💾 SSD: 214G/4.6T (5%)
☁️ Nextcloud: running

📦 Last backup: Tue Jun 24 03:00 2026
   Status: ✅ Success | Uploaded: 312 MiB
```

**`/report` — Full daily digest (sent automatically at 08:00)**
```
📊 Nextcloud Daily Report
📅 Tuesday, 24 Jun 2026 08:00

🏠 System
• Uptime: up 12 days, 4 hours
• CPU: 3.2% | Temp: 48.1°C
• RAM: 1.2G/8.0G
• SSD: 214G/4.6T (5%)
• SD: 7.2G/29G (26%)

☁️ Nextcloud
• Files: 48,392
• Free: 4.3 TB
• DB: 156 MB

📦 Backup
• Last: Tue Jun 24 03:00 2026
• Status: ✅ Success
• Uploaded: 312 MiB
```

**`/users` — Per-user storage usage**
```
👥 Per-User Usage
📅 24 Jun 2026 14:35

• omid: 187.4 GB / unlimited (last login: 2026-06-24)
• sarah: 12.1 GB / 50.0 GB (last login: 2026-06-23)
• guest: 4.2 GB / 10.0 GB (last login: 2026-06-15)
```

**`/backup` — Backup deep dive**
```
📦 Backup Deep Dive
📅 24 Jun 2026 14:40

• Last run: Tue Jun 24 03:00 2026
• Status: ✅ Success
• Uploaded: 312 MiB

🗂 S3 Snapshots
```
ID     Time                 Host        Tags
abc12d 2026-06-24 03:14:22  homecloud   nextcloud
def34e 2026-06-23 03:10:15  homecloud   nextcloud
ghi56f 2026-06-22 03:12:01  homecloud   nextcloud
```

📋 Log tail
```
=== Backup started: Tue Jun 24 03:00:00 2026 ===
repository ... opened successfully
[0:14] 100.00%  312 MiB/s  ...
snapshot abc12def saved
=== Backup finished: Tue Jun 24 03:14:22 2026 ===
```
```

**`/runbackup` — Trigger backup now**
```
🚀 Triggering backup now...
✅ Backup started! Check /backup in ~5 min.
```

---

## 🔐 Secrets & Recovery

All secrets live in `/etc/homecloud/.env` (permissions `0600`, root-owned):

- DuckDNS token
- AWS access key + secret
- S3 bucket name
- restic repository password
- Telegram bot token + chat ID
- Nextcloud admin password
- Samba password

### Export a recovery bundle

```bash
homecloud secrets export -o ~/homecloud-recovery-bundle.json
```

This writes a JSON file with **all** secrets + config + install state. Copy it
to a USB stick or password manager, then delete it from the Pi.

### Import on a fresh Pi

If your SD card dies and you re-flash:

```bash
curl -fsSL https://raw.githubusercontent.com/omidizadi/home-cloud/main/install.sh | sudo bash
# ...then:
homecloud secrets import /path/to/homecloud-recovery-bundle.json
homecloud
```

Your SSD data is untouched — just re-run install and it picks up where you left off.

---

## 💰 Cost Estimate (S3 Glacier Deep Archive, eu-central-1)

| Item | Cost |
| :-- | :-- |
| Storage (200 GB) | ~€0.20/month |
| Upload (first time, 200 GB) | ~€1.80 one-time |
| Nightly delta uploads (~500 MB/night) | ~€0.10/month |
| Retrieval (restore, if needed) | ~€0.01/GB + 12–48h wait |

**Why you won't pay for 200GB × N nights:** restic uses content-defined
chunking — only *changed* chunks are uploaded. Add 500MB of new photos → only
~500MB goes to S3 that night.

### S3 Lifecycle rule (manual, one-time)

In the AWS Console → your bucket → **Management** → **Lifecycle rules**:

- Transition objects in the `data/` prefix to **Glacier Deep Archive** after 1 day

This keeps restic's tiny `index/` and `keys/` files in S3 Standard (so restic
can read them without a Glacier restore) while the bulk data moves to Deep Archive.

---

## 🔄 Reboot Survival

Everything is wired to survive a reboot:

| Component | Survives? | How |
| :-- | :-- | :-- |
| Nextcloud AIO | ✅ | `--restart always` |
| Samba | ✅ | systemd service, enabled |
| SSD mount | ✅ | `/etc/fstab` with `nofail` |
| Telegram bot | ✅ | systemd service, enabled |
| Cron jobs | ✅ | persist across reboots |
| WiFi | ✅ | NetworkManager persists |

**Hardening applied:**
- Docker waits for the SSD mount before starting (prevents Nextcloud silently
  writing to the SD card if the SSD fails to mount)
- `fsck` auto-repair on the SSD (fstab pass=2)
- The backup script sends a Telegram alert if the Pi just rebooted

For full peace of mind, add a small UPS (~€60, e.g. APC Back-UPS 700) with
`apcupsd` for graceful shutdown on power loss.

---

## 🛠️ Development

```bash
git clone https://github.com/omidizadi/home-cloud.git
cd home-cloud
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Lint
ruff check homecloud

# Compile check
python -m compileall homecloud

# Dry-run on your Mac (no commands execute)
python -m homecloud --dry-run
```

---

## 🗂️ Project Structure

```
home-cloud/
├── README.md
├── install.sh                     # Bootstrap one-liner
├── pyproject.toml
├── homecloud/
│   ├── __main__.py                # CLI entry point
│   ├── app.py                     # Textual TUI app
│   ├── config.py                  # .env schema + secrets + recovery
│   ├── constants.py               # Paths, ports, container names
│   ├── steps/                     # One module per install phase
│   │   ├── base.py                # Step ABC: run/status/repair/undo
│   │   ├── ssd.py
│   │   ├── docker.py
│   │   ├── nextcloud_aio.py
│   │   ├── duckdns.py
│   │   ├── coturn.py
│   │   ├── samba.py
│   │   ├── wifi.py
│   │   ├── restic_s3.py
│   │   ├── telegram_bot.py
│   │   └── hardening.py
│   ├── services/                  # systemd, docker, cron managers
│   ├── ui/                        # Textual screens
│   └── utils/                     # shell, logging, state, checks
└── templates/                     # Reference config files
```

---

## ⚠️ Troubleshooting

| Problem | Fix |
| :-- | :-- |
| AIO admin panel not reachable on :8080 | `docker logs nextcloud-aio-mastercontainer` |
| Nextcloud Talk calls fail across networks | Verify port 3478 TCP+UDP is forwarded on your router |
| Backup fails with S3 error | Check AWS credentials in `/etc/homecloud/.env` |
| Bot not responding | `systemctl status ncbot` + `journalctl -u ncbot -f` |
| SSD not mounted after reboot | Check `/etc/fstab` + `journalctl -b -u mnt-ncdata.mount` |
| Docker started but Nextcloud on SD card | The hardening step prevents this; re-run Repair |

---

## 📄 License

MIT
