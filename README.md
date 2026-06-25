# 🏠 Home Cloud

An interactive installer & manager for a **Raspberry Pi 5** home cloud built on
**Immich** (self-hosted photo/video backup), with nightly **deduplicated S3
Glacier Deep Archive** backups, **Tailscale** (mesh VPN for external access),
and an interactive **Telegram bot** for status reports.

> Designed for a Raspberry Pi 5 (8GB RAM, 128GB SD card) with a 5TB external SSD.
> Conservative uninstall: **never touches your data on the SSD**.

---

## Table of Contents

- [✨ Features](#-features)
- [📋 Architecture](#-architecture)
- [🚀 Quick Start](#-quick-start)
- [🔧 Configuration](#-configuration)
- [📦 Installation Steps](#-installation-steps)
- [🌐 Network & External Access](#-network--external-access)
- [🤖 Telegram Bot](#-telegram-bot)
- [💰 Backups & Costs](#-backups--costs)
- [🔐 Secrets & Recovery](#-secrets--recovery)
- [🔄 Reboot Survival](#-reboot-survival)
- [⬆️ Updating](#⬆️-updating)
- [⚠️ Troubleshooting](#-troubleshooting)
- [🛠️ Development](#-development)
- [🗂️ Project Structure](#-project-structure)
- [📄 License](#-license)

---

## ✨ Features

- **Immich** — self-hosted photo/video backup (like Google Photos) with face
  detection, CLIP smart search, and albums. Full docker-compose stack:
  server + machine-learning + redis + postgres.
- **5TB SSD** as the data directory (SD card stays for OS/Docker only)
- **Tailscale** — WireGuard mesh VPN for external access + automatic TLS certs
  (bypasses DS-Lite/CGNAT, no port forwarding needed). Immich is served at
  `https://<pi>.<tailnet>.ts.net` with a valid cert issued by Tailscale.
- **Nightly restic backup → S3 Glacier Deep Archive** — block-level deduplication
  means you only pay for ~your actual data size, not `200GB × N nights`.
  Includes a `pg_dump` of the Immich postgres database so metadata (faces,
  albums, EXIF) survives a restore.
- **Interactive Telegram bot** — daily reports + on-demand commands
  (`/status`, `/report`, `/jobs`, `/backup`, `/runbackup`, `/logs`)
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
│  │  SD Card    │   │        5TB SSD (/mnt/data)      │  │
│  │  (OS+Docker)│   │  ┌────────────────────────────┐  │  │
│  │             │   │  │ Immich data dir            │  │  │
│  │  compose    │   │  │  uploads/ library/ thumbs/  │  │  │
│  │  files      │   │  │  encoded-video/ profile/    │  │  │
│  │             │   │  │  pgdata/ model-cache/      │  │  │
│  └─────────────┘   └─────────────────────────────────┘  │
│                                                         │
│  Services: Docker · homecloud-bot (Telegram) · Tailscale │
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

The fast path to a running home cloud. Detailed config values are in
[🔧 Configuration](#-configuration); the full step list is in
[📦 Installation Steps](#-installation-steps); external access is in
[🌐 Network & External Access](#-network--external-access).

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
the interactive CLI menu.

### Step 2: Use the menu

| Menu option | What it does |
| :-- | :-- |
| **📥 Install / Configure** | First: edit config (SSD, AWS, Telegram, etc.), then run all install steps |
| **📊 Status Dashboard** | View of containers, disk, services, backup, install steps |
| **🔄 Update** | Update homecloud itself, Immich, bot deps, restic |
| **🔧 Repair** | Re-check and re-run any failed steps |
| **🗑️ Uninstall** | Conservative removal — **keeps data on SSD** |
| **🔐 Secrets: Export** | Save all secrets to a recovery JSON bundle |

### Step 3: Dry-run first (recommended)

```bash
homecloud --dry-run
```

This prints every command without executing — review what will happen before
running for real.

### Step 4: Complete network setup + create admin account

Once the installer finishes, Immich is running but has no admin account yet.
See [🌐 Network & External Access](#-network--external-access) for the full
guide (Tailscale, creating your admin account, and generating an API key for
the Telegram bot).

---

## 🔧 Configuration

The installer asks for a handful of values before it can run. Here's where to
find each one and what format it expects.

### SSD device (`ssd_device`)

The block device path of your external SSD.

```bash
lsblk -d -o NAME,SIZE,MODEL,TRAN | grep -v mmcblk
# NAME   SIZE   MODEL              TRAN
# sda    4.6T   Samsung_T5         usb
```

Use the `/dev/` path, e.g. `/dev/sda`. If the SSD is brand new and unformatted,
the installer will offer to format it (erasing all data). If it already has a
filesystem, the installer mounts it as-is.

> Tip: unplug the SSD, run `lsblk`, plug it back in, run `lsblk` again — the new
> entry is your SSD.

### Tailscale auth key (`tailscale_auth_key`, optional)

Tailscale provides the domain (`<pi>.<tailnet>.ts.net`) and TLS certificate
for Immich. It works on DS-Lite/CGNAT — no port forwarding or public IPv4
needed.

1. Create a Tailscale account at <https://login.tailscale.com/start>.
2. (Optional) Generate an auth key at
   <https://login.tailscale.com/admin/settings/keys> for non-interactive
   setup. If you leave this blank, the installer will print a login URL.
3. Install the Tailscale client on your phone/laptop from
   <https://tailscale.com/download> to access Immich from those devices.

> No port forwarding needed. Tailscale punches through NAT/DS-Lite via its
> WireGuard mesh. The Pi gets a stable `100.x.y.z` IP and a MagicDNS name.

### AWS S3 credentials (`aws_access_key_id`, `aws_secret_access_key`)

1. Sign in to the **AWS Console** → **IAM** → **Users** → your user →
   **Security credentials** → **Create access key**.
2. Choose **Application running outside AWS** (or "Other").
3. Copy the **Access key ID** (starts with `AKIA…`) and **Secret access key**.

> Best practice: create a dedicated IAM user with only `AmazonS3FullAccess`
> (or a scoped-down policy limited to your bucket) rather than using your root
> account keys.

### S3 bucket (`s3_bucket`)

1. **AWS Console** → **S3** → **Create bucket**.
2. Pick a globally-unique name (e.g. `omid-homecloud-backup`).
3. **Region**: pick one close to you (e.g. `eu-central-1` Frankfurt). The
   installer defaults to `eu-central-1` — change `s3_region` if you pick another.
4. Leave **Block all public access** ON (recommended).
5. Versioning: restic manages its own versioning — leave AWS versioning **off**
   to avoid extra costs.

After creating the bucket, add the **Glacier Deep Archive lifecycle rule**
described in [💰 Backups & Costs](#-backups--costs) so backups age into cheap
storage automatically.

### restic password (`restic_password`)

This is the encryption password for your backup repository. **There is no
recovery** — lose it and your backups are gone.

- Must be **at least 12 characters** (the installer enforces this).
- Generate one with: `openssl rand -base64 24`
- Store it in a password manager alongside your recovery bundle.

> The installer can auto-generate one for you if you leave it blank during
> config editing.

### Telegram bot token + chat ID (`telegram_bot_token`, `telegram_chat_id`)

1. In Telegram, message **@BotFather** → `/newbot` → pick a name and username.
2. BotFather replies with a token like `123456789:ABCdefGhi...` — that's your
   `telegram_bot_token`.
3. Start a chat with your new bot and send any message.
4. Visit
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   in a browser — look for `"chat":{"id":123456789}`. That number is your
   `telegram_chat_id`.

> For a private chat (just you), the chat ID is a positive number. For a group,
   it starts with `-` (e.g. `-1001234567890`) — add the bot to the group and
   promote it to admin first.

### Immich secrets (`immich_jwt_secret`, `immich_db_password`)

These are auto-generated by the installer if left blank:
- **`immich_jwt_secret`** — signs JWT auth tokens. 48 chars.
- **`immich_db_password`** — postgres password. 32 chars.

You don't need to touch these unless you want to set your own.

### Immich API key (`immich_api_key`)

> **Manual post-install step.** Unlike Nextcloud's `occ` CLI, Immich has no
> CLI — admin actions go through the REST API with a key generated in the web
> UI. The Telegram bot needs this key to query Immich stats.

1. After install, open Immich in your browser (see
   [🌐 Network & External Access](#-network--external-access)).
2. Create your admin account.
3. Go to **Settings → API Keys → New API key**.
4. Copy the key.
5. Run `homecloud` → **Edit Config** → paste into `immich_api_key`.

The bot won't be able to query Immich stats until this is done. System health
and backup commands still work without it.

### WiFi (optional: `wifi_ssid`, `wifi_password`)

Only needed if the Pi connects over WiFi instead of Ethernet. Use your router's
SSID and WPA2/WPA3 password. Skip entirely if using a cable.

### Timezone (`timezone`)

Your IANA timezone, e.g. `Europe/Berlin`, `America/New_York`, `Asia/Tehran`.
Run `timedatectl list-timezones` on the Pi to see all options. Used for cron
schedules (backup at 3 AM, daily report at 8 AM).

---

## 📦 Installation Steps

What gets installed, in order:

| # | Step | Description |
| :-: | :-- | :-- |
| 1 | **SSD mount** | Format (if needed) + mount 5TB SSD at `/mnt/data`, add to fstab |
| 2 | **Docker** | Install Docker Engine, add user to docker group |
| 3 | **Tailscale** | WireGuard mesh VPN for external access + TLS certs (bypasses DS-Lite/CGNAT) |
| 4 | **Immich** | Launch Immich stack (server + ML + redis + postgres) behind Tailscale Serve |
| 5 | **WiFi** | (Optional) Connect via NetworkManager |
| 6 | **restic + S3** | Init repo, deploy nightly backup script (3 AM cron) with pg_dump |
| 7 | **Telegram bot** | Interactive bot as systemd service, daily 8 AM report |
| 8 | **Hardening** | Docker→SSD dependency, fsck, verify all services auto-start |

Each step is **idempotent** — running it twice is safe. Completed steps are
tracked via marker files in `/etc/homecloud/state/`.

---

## 🌐 Network & External Access

After the installer finishes, Immich is running on port 2283 behind Tailscale
Serve. You need to create your admin account and generate an API key for the bot.

### Step 1: Install Tailscale (external access, bypasses DS-Lite)

Tailscale creates a WireGuard mesh VPN. Every device with the Tailscale client
installed gets a stable `100.x.y.z` IP and can reach the Pi — **no port
forwarding needed**. This is the recommended way to expose Immich when your
ISP uses DS-Lite / CGNAT (no real public IPv4).

**1. Get a Tailscale auth key (optional but recommended for non-interactive setup):**
- Sign up at <https://tailscale.com> (free for personal use, up to 100 devices)
- Go to **Settings → Keys → Generate auth key**
- Copy the key (starts with `tskey-...`)
- Set it in your config: `TAILSCALE_AUTH_KEY=tskey-...`

**2. Run the Tailscale install step** (from the menu or CLI):
```bash
homecloud install  # step 3: Tailscale
```

If you set an auth key, the Pi authenticates automatically. If not, the step
prints a login URL — open it in your browser to authorize the Pi.

**3. Install Tailscale on your devices:**
- Download from <https://tailscale.com/download>
- Available for iOS, Android, macOS, Windows, Linux
- Log in with the same account you used for the Pi

**4. Access Immich over Tailscale:**
```
https://<pi>.<tailnet>.ts.net
```
Find the Pi's Tailscale IP with `tailscale ip -4` on the Pi, or in the
[Tailscale admin console](https://login.tailscale.com/admin/machines).

> **Why Tailscale over port forwarding?**
> - Works with DS-Lite / CGNAT (no real public IPv4)
> - No upload bandwidth limits (unlike Cloudflare Tunnel's 100 MB cap)
> - No request timeout (unlike Cloudflare Tunnel's 100s)
> - Encrypted end-to-end (WireGuard)
> - Free for personal use (up to 100 devices)
>
> **Downside:** every device that accesses Immich needs the Tailscale client
> installed. It's not a public URL you can share with anyone.

### Step 2: Create your Immich admin account

Once the installer finishes, Immich is running but has no admin account yet.

**1. Open Immich in your browser:**
```
https://<pi>.<tailnet>.ts.net
```
Or on your LAN: `http://<pi-ip>:2283`

The cert is valid via Tailscale Serve — no browser warnings over Tailscale.

**2. Create your admin account** — the first user becomes the admin.

**3. (For the Telegram bot) Generate an API key:**
- Go to **Settings → API Keys → New API key**
- Copy the key
- Run `homecloud` → **Edit Config** → paste into `immich_api_key`

The bot can't query Immich stats until you've done this. System health and
backup commands still work without it.

### Step 3: Access Immich (daily use)

Once your admin account is created, access Immich at:

`https://<pi>.<tailnet>.ts.net` (e.g. `https://homecloud.tail665a7d.ts.net`)

This works from any device on your tailnet (phone, laptop, etc. with
Tailscale installed). The cert is valid — no browser warnings.

Install the **Immich mobile app** on your phone (iOS/Android) and point it at
`https://<pi>.<tailnet>.ts.net` for automatic photo backup.

---

## 🤖 Telegram Bot

| Command | What you get |
| :-- | :-- |
| `/status` | CPU, RAM, temp, disk, Immich container, last backup — instant |
| `/report` | Full daily digest: system + Immich stats (photos, videos, usage) |
| `/jobs` | Immich job statuses (library scan, face detection, ML, etc.) |
| `/backup` | Backup status + S3 snapshot list + log tail |
| `/runbackup` | Trigger a backup immediately |
| `/logs` | Last 30 lines of the backup log |
| `/help` | Show command menu |

A daily report is sent automatically at **08:00** (your timezone).

> **Immich API key required:** `/report` and `/jobs` query the Immich REST API,
> which requires an API key. Generate one in the Immich web UI
> (Settings → API Keys) and paste it into `homecloud` config. Without it, those
> commands return "API unavailable" — but `/status`, `/backup`, `/runbackup`,
> and `/logs` still work.

### Sample bot output

**`/status` — Quick health check**
```
⚡ Quick Status
🕐 25 Jun 2026 14:32

🖥 CPU: 3.2% load | 48.1°C temp
🧠 RAM: 1.2G/8.0G
💾 SSD: 214G/4.6T (5%)
📸 Immich: running

📦 Last backup: Wed Jun 25 03:00 2026
   Status: ✅ Success | Uploaded: 312 MiB
```

**`/report` — Full daily digest (sent automatically at 08:00)**
```
📊 Immich Daily Report
📅 Wednesday, 25 Jun 2026 08:00

🏠 System
• Uptime: up 12 days, 4 hours
• CPU: 3.2% | Temp: 48.1°C
• RAM: 1.2G/8.0G
• SSD: 214G/4.6T (5%)
• SD: 7.2G/29G (26%)

📸 Immich
• Photos: 48,392
• Videos: 1,204
• Total usage: 187.4 GB

📦 Backup
• Last: Wed Jun 25 03:00 2026
• Status: ✅ Success
• Uploaded: 312 MiB
```

**`/jobs` — Immich job statuses**
```
🔄 Immich Jobs
📅 25 Jun 2026 14:35

• ✅ library: 0 active, 0 waiting
• 🔄 faceDetection: 1 active, 42 waiting
• ✅ smartSearch: 0 active, 0 waiting
• ⏸ migration: 0 active, 0 waiting
```

**`/backup` — Backup deep dive**
```
📦 Backup Deep Dive
📅 25 Jun 2026 14:40

• Last run: Wed Jun 25 03:00 2026
• Status: ✅ Success
• Uploaded: 312 MiB

🗂 S3 Snapshots
```
ID     Time                 Host        Tags
abc12d 2026-06-25 03:14:22  homecloud   immich,immich-db
def34e 2026-06-24 03:10:15  homecloud   immich,immich-db
ghi56f 2026-06-23 03:12:01  homecloud   immich,immich-db
```

📋 Log tail
```
=== Backup started: Wed Jun 25 03:00:00 2026 ===
Dumping Immich postgres database...
repository ... opened successfully
[0:14] 100.00%  312 MiB/s  ...
snapshot abc12def saved
=== Backup finished: Wed Jun 25 03:14:22 2026 ===
```
```

---

## 💰 Backups & Costs

Nightly restic backups go to **S3 Glacier Deep Archive** (eu-central-1).
Block-level deduplication means you only pay for ~your actual data size, not
`200GB × N nights`.

### What gets backed up

1. **Immich postgres database** — dumped via `pg_dump` and sent to restic
   with tag `immich-db`. This contains all metadata: faces, albums, EXIF,
   user accounts, shared links. Without this, a restore would lose all
   metadata even if the files survived.
2. **Immich data directory** (`/mnt/data/immich/`) — uploads, library,
   encoded-video, profile, thumbs. Sent to restic with tag `immich`.

### Cost estimate

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

This keeps restic's tiny `index/` and `keys/` files in S3 Standard (so restic
can read them without a Glacier restore) while the bulk data moves to Deep
Archive. Without this rule everything stays in S3 Standard and you pay ~10×
more for storage.

In the AWS Console: **S3** → your bucket → **Management** tab →
**Lifecycle rules** → **Create lifecycle rule**, then fill in:

1. **Lifecycle rule name** — e.g. `restic-to-deep-archive`.
2. **Choose a rule scope** — select **Limit the scope of this rule using one or
   more filters**, and in the **Prefix** box enter `data/` (this is where
   restic stores the actual backup chunks; `index/` and `keys/` are left in
   S3 Standard so restic can list/read them instantly).
3. **Lifecycle rule actions** — tick **Transition current versions of objects
   between storage classes**.
4. **Transition** — choose:
   - **Storage class**: `Glacier Deep Archive`
   - **Days after object creation**: `1`
5. Review the rule summary (it should read roughly: *"Transition current
   versions to Glacier Deep Archive after 1 day(s) for objects with prefix
   `data/`"*) and click **Create rule**.

> That's it. New nightly backup chunks land in S3 Standard, then within ~24 h
> AWS moves them to Glacier Deep Archive automatically. No further action
> needed — restic is unaware of the transition and keeps working normally.

---

## 🔐 Secrets & Recovery

All secrets live in `/etc/homecloud/.env` (permissions `0600`, root-owned):

- AWS access key + secret
- S3 bucket name
- restic repository password
- Telegram bot token + chat ID
- Immich JWT secret + DB password
- Immich API key (manual, post-install)

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

## 🔄 Reboot Survival

Everything is wired to survive a reboot:

| Component | Survives? | How |
| :-- | :-- | :-- |
| Immich stack | ✅ | `restart: always` in docker-compose |
| SSD mount | ✅ | `/etc/fstab` with `nofail` |
| Telegram bot | ✅ | systemd service, enabled |
| Cron jobs | ✅ | persist across reboots |
| WiFi | ✅ | NetworkManager persists |

**Hardening applied:**
- Docker waits for the SSD mount before starting (prevents Immich silently
  writing to the SD card if the SSD fails to mount)
- `fsck` auto-repair on the SSD (fstab pass=2)
- The backup script sends a Telegram alert if the Pi just rebooted
- SSD hot-replug support: if you unplug and replug the SSD, a udev rule
  triggers `data-replug.service` which fscks, mounts, restarts Docker, waits
  for postgres, and restarts the Immich stack

For full peace of mind, add a small UPS (~€60, e.g. APC Back-UPS 700) with
`apcupsd` for graceful shutdown on power loss.

---

## ⬆️ Updating

### Update homecloud itself

**From the menu:** Main menu → 🔄 Update → "homecloud"

**From the command line:**

```bash
# Check if updates are available
homecloud update --check

# Apply updates
homecloud update
```

This runs `git pull` in `/opt/homecloud` and reinstalls the package via the
virtualenv's pip. Re-run `homecloud` to use the new version.

### Update all components

The Update screen and CLI can update **all** updatable components, each with a
confirmation prompt:

| Component | What it does |
| :-- | :-- |
| 📦 homecloud | `git pull` + `pip install` |
| 📸 Immich | `docker compose pull` + `docker compose up -d` |
| 🤖 Bot deps | `pip install --upgrade` python-telegram-bot/APScheduler/requests + restart |
| 🔐 restic | `apt-get install --only-upgrade restic` |

**From the menu:** Main menu → 🔄 Update → "Update all"

**From the command line:**

```bash
# Update everything (prompts for each component)
homecloud update --all

# Update everything, skip prompts (unattended)
homecloud update --all -y
```

---

## ⚠️ Troubleshooting

| Problem | Fix |
| :-- | :-- |
| Immich web not reachable on :2283 | `docker compose -f /opt/homecloud/immich/docker-compose.yml logs` |
| Immich not reachable over Tailscale HTTPS | `tailscale serve status` — re-run the Immich step's repair |
| Backup fails with S3 error | Check AWS credentials in `/etc/homecloud/.env` |
| Bot not responding | `systemctl status homecloud-bot` + `journalctl -u homecloud-bot -f` |
| Bot says "Immich API unavailable" | Generate an API key in Immich web UI → Settings → API Keys, paste into config |
| SSD not mounted after reboot | Check `/etc/fstab` + `journalctl -b -u mnt-data.mount` |
| Docker started but Immich on SD card | The hardening step prevents this; re-run Repair |
| ML container too slow on Pi 5 | `docker compose stop immich-machine-learning` — Immich degrades gracefully (smart search won't work) |

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
│   ├── app.py                     # Plain CLI menu app
│   ├── config.py                  # .env schema + secrets + recovery
│   ├── constants.py               # Paths, ports, container names
│   ├── steps/                     # One module per install phase
│   │   ├── base.py                # Step ABC: run/status/repair/undo
│   │   ├── ssd.py
│   │   ├── docker.py
│   │   ├── immich.py
│   │   ├── tailscale.py
│   │   ├── wifi.py
│   │   ├── restic_s3.py
│   │   ├── telegram_bot.py
│   │   └── hardening.py
│   ├── services/                  # systemd, docker, cron managers
│   └── utils/                     # shell, logging, state, checks
└── templates/                     # Reference config files
    ├── immich/
    │   ├── docker-compose.yml.j2
    │   └── env.j2
    ├── 99-data.rules              # udev rule for SSD hot-replug
    ├── data-replug.service         # systemd oneshot for hot-replug
    ├── homecloud-replug.sh        # hot-replug recovery script
    ├── homecloud-bot.service      # Telegram bot systemd unit
    └── docker-wait-for-ssd.conf    # Docker waits for SSD mount
```

---

## 📄 License

MIT
