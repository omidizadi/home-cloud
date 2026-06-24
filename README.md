# 🏠 Home Cloud

An interactive installer & manager for a **Raspberry Pi 5** home cloud built on
**Nextcloud AIO**, with nightly **deduplicated S3 Glacier Deep Archive** backups,
a **Samba** share, **DuckDNS**, **Nextcloud Talk** (video calls), and an
interactive **Telegram bot** for status reports.

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
- [💾 Accessing Your Files](#-accessing-your-files)
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

- **Nextcloud AIO** — photos (Memories), files, and Talk (1-1 video calls)
- **5TB SSD** as the data directory (SD card stays for OS/Docker only)
- **Samba share** — access the SSD for non-Nextcloud files without detaching it
- **DuckDNS** — free dynamic DNS + automatic Let's Encrypt TLS
- **Tailscale** — WireGuard mesh VPN for external access (bypasses DS-Lite/CGNAT,
  no port forwarding needed, no bandwidth/timeout limits like Cloudflare Tunnel)
- **Nextcloud Talk** — 1-1 video calls via AIO's built-in Coturn TURN server
  (works over Tailscale — no port forwarding required)
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

The fast path to a running home cloud. Detailed config values are in
[🔧 Configuration](#-configuration); the full step list is in
[📦 Installation Steps](#-installation-steps); external access and the one-time
AIO browser setup are in [🌐 Network & External Access](#-network--external-access).

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
| **📥 Install / Configure** | First: edit config (SSD, DuckDNS, AWS, Telegram, etc.), then run all install steps |
| **📊 Status Dashboard** | View of containers, disk, services, backup, install steps |
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

### Step 4: Complete network & AIO setup

Once the installer finishes, Nextcloud isn't running yet — you need to set up
external access and click through the AIO panel. See
[🌐 Network & External Access](#-network--external-access) for the full guide
(port forwarding, Tailscale, and the one-time AIO browser setup).

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

### DuckDNS domain + token (`duckdns_domain`, `duckdns_token`)

1. Go to <https://www.duckdns.org> and sign in with GitHub/Google/Reddit.
2. Add a subdomain (e.g. `omid`) — this becomes `omid.duckdns.org`.
   Enter just the subdomain part (`omid`), not the full URL.
3. Copy the long **token** shown at the top of the page — it's a UUID like
   `a1b2c3d4-e5f6-7890-abcd-ef1234567890`.

The installer uses this for:
- Dynamic DNS updates (so `omid.duckdns.org` always points to your home IP)
- Let's Encrypt TLS certificates for Nextcloud

> Make sure your router forwards ports **80** and **443** to the Pi's local IP.
> For Talk video calls, also forward **3478** and **5349** (TCP+UDP). See
> [Port forwarding](#step-1-port-forwarding-on-your-router) for the full table.

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

### Nextcloud admin password (`nextcloud_admin_password`)

The master password for the Nextcloud AIO admin panel (port 8080). Pick
something strong — the installer can auto-generate one if left blank. Store it
in a password manager; you'll need it to log in to the AIO management UI.

### Tailscale auth key (optional: `tailscale_auth_key`)

Used for non-interactive authentication of the Pi to your Tailscale tailnet.
If set, the Tailscale step authenticates automatically. If left blank, the
step prints a login URL you must open in your browser.

1. Sign up at <https://tailscale.com> (free for personal use, up to 100 devices)
2. Go to **Settings → Keys → Generate auth key**
3. Copy the key (starts with `tskey-...`)

> **Without an auth key**, the Tailscale step still works — it just requires
> you to open a URL in your browser to authorize the Pi. The auth key makes
> it fully automated (useful for headless installs).

### Samba user + password (`samba_user`, `samba_password`)

The username and password for the network file share. This is a local Linux
account used only by Samba — pick any username (e.g. your first name) and a
strong password. The installer can auto-generate the password if left blank.

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
| 1 | **SSD mount** | Format (if needed) + mount 5TB SSD at `/mnt/ncdata`, add to fstab |
| 2 | **Docker** | Install Docker Engine, add user to docker group |
| 3 | **Nextcloud AIO** | Launch master container with `NEXTCLOUD_DATADIR` on SSD |
| 4 | **DuckDNS** | Dynamic DNS updater (5-min cron) for free domain + TLS |
| 5 | **Tailscale** | WireGuard mesh VPN for external access (bypasses DS-Lite/CGNAT) |
| 6 | **Talk (Coturn)** | Guide enabling AIO's built-in TURN server for video calls |
| 7 | **Samba** | Network share at `/mnt/ncdata/files` for non-Nextcloud files |
| 8 | **WiFi** | (Optional) Connect via NetworkManager |
| 9 | **restic + S3** | Init repo, deploy nightly backup script (3 AM cron) |
| 10 | **Telegram bot** | Interactive bot as systemd service, daily 8 AM report |
| 11 | **Hardening** | Docker→SSD dependency, fsck, verify all services auto-start |

Each step is **idempotent** — running it twice is safe. Completed steps are
tracked via marker files in `/etc/homecloud/state/`.

---

## 🌐 Network & External Access

After the installer finishes, you need to expose Nextcloud so you can reach it
from outside your LAN, then complete the one-time AIO setup in your browser.

### Step 1: Port forwarding (on your router)

> **⚠️ DS-Lite / CGNAT check first!** Many ISPs (Telekom, Vodafone, 1&1 in
> Germany) assign a shared IPv4 via DS-Lite — you have **no real public IPv4**
> and port forwarding **will not work**. Test from a phone on mobile data:
> ```
> curl -s https://api.ipify.org  # your public IPv4
> nc -z -w5 <that-ip> 443 && echo OPEN || echo BLOCKED
> ```
> If blocked, skip port forwarding and use **Tailscale** (Step 2) instead.

**If you have a real public IPv4**, forward these ports to your Pi's local IP
(find it with `hostname -I` on the Pi):

| Port | Protocol | Purpose |
| :--: | :------: | :------ |
| **80** | TCP | Let's Encrypt HTTP challenge (for TLS certs) |
| **443** | TCP | Nextcloud HTTPS (daily use) |
| **443** | UDP | HTTP/3 (optional, faster connections) |
| **3478** | TCP + UDP | Talk TURN server (video calls) |
| **5349** | TCP + UDP | Talk TURN over TLS (video calls) |

### Step 2: Install Tailscale (external access, bypasses DS-Lite)

Tailscale creates a WireGuard mesh VPN. Every device with the Tailscale client
installed gets a stable `100.x.y.z` IP and can reach the Pi — **no port
forwarding needed**. This is the recommended way to expose Nextcloud when your
ISP uses DS-Lite / CGNAT (no real public IPv4).

**1. Get a Tailscale auth key (optional but recommended for non-interactive setup):**
- Sign up at <https://tailscale.com> (free for personal use, up to 100 devices)
- Go to **Settings → Keys → Generate auth key**
- Copy the key (starts with `tskey-...`)
- Set it in your config: `TAILSCALE_AUTH_KEY=tskey-...`

**2. Run the Tailscale install step** (from the menu or CLI):
```bash
homecloud install  # step 5: Tailscale
```

If you set an auth key, the Pi authenticates automatically. If not, the step
prints a login URL — open it in your browser to authorize the Pi.

**3. Install Tailscale on your devices:**
- Download from <https://tailscale.com/download>
- Available for iOS, Android, macOS, Windows, Linux
- Log in with the same account you used for the Pi

**4. Access Nextcloud over Tailscale:**
```
https://<pi-tailscale-ip>       # Nextcloud
https://<pi-tailscale-ip>:8080   # AIO admin panel
```
Find the Pi's Tailscale IP with `tailscale ip -4` on the Pi, or in the
[Tailscale admin console](https://login.tailscale.com/admin/machines).

> **Why Tailscale over port forwarding?**
> - Works with DS-Lite / CGNAT (no real public IPv4)
> - No upload bandwidth limits (unlike Cloudflare Tunnel's 100 MB cap)
> - No request timeout (unlike Cloudflare Tunnel's 100s) — Talk video calls work
> - Encrypted end-to-end (WireGuard)
> - Free for personal use (up to 100 devices)
>
> **Downside:** every device that accesses Nextcloud needs the Tailscale client
> installed. It's not a public URL you can share with anyone.

### Step 3: Complete AIO setup (one-time, in your browser)

After the installer finishes, Nextcloud isn't running yet — you need to open
the AIO panel and click through a few screens.

**1. Open the AIO panel:**
```
https://<pi-tailscale-ip>:8080
```
Or on your LAN: `https://<pi-ip>:8080`

Accept the self-signed certificate warning in your browser.

**2. Enter your domain — validation is auto-skipped:**

AIO requires a domain to be entered, but it also tries to validate that your
Pi is reachable from the internet on port 443. The installer launches AIO
with `SKIP_DOMAIN_VALIDATION=true`, so **validation is skipped automatically**
— no manual steps needed. This works even on DS-Lite/CGNAT (no real public IPv4).

The domain is just used internally by AIO for config (TLS cert generation,
Coturn, etc.). You don't actually access Nextcloud through it — you use the
Tailscale IP.

Just enter your DuckDNS domain (e.g. `omid.duckdns.org`) and submit.

**3. Pick optional containers:**
| Container | Recommended? | Why |
| :-- | :--: | :-- |
| Nextcloud (core) | ✅ always | The actual cloud |
| Nextcloud Talk | ✅ yes | Video/audio calls (works over Tailscale) |
| Collabora | optional | Online document editing (LibreOffice) |
| ClamAV | ❌ no | Antivirus — heavy, eats RAM on a Pi |
| Fulltextsearch | ❌ no | Elasticsearch — heavy on Pi |
| Imaginary | optional | Image processing/thumbnailing |

**4. Set an admin password** — this is your Nextcloud `admin` login.
Use something strong and store it in a password manager.

**5. Click "Start containers"** — AIO pulls Docker images and boots everything.
This takes 5–10 minutes on a Pi. You'll see progress in the panel.

**6. When all containers show ✅**, your Nextcloud is live. Access it via:

| Where you are | URL |
| :-- | :-- |
| Over Tailscale | `https://<pi-tailscale-ip>` |
| Same LAN | `https://<pi-ip>` |
| Public internet | `https://<your-subdomain>.duckdns.org` (needs real public IPv4) |

Log in with username `admin` and the password you set in step 4.

> **⚠️ You must open the AIO panel and complete these steps before
> Nextcloud is usable.** The installer only launches the master container —
> the actual Nextcloud instance, database, Redis, etc. are started from
> inside the AIO panel.

### Step 4: Access Nextcloud (daily use)

Once AIO containers are running, pick the URL that matches where you are:

| Where | URL |
| :-- | :-- |
| Same LAN | `https://<pi-ip>` |
| Over Tailscale | `https://<pi-tailscale-ip>` |
| Public internet | `https://<your-subdomain>.duckdns.org` (needs real public IPv4) |

Log in with the admin username (`admin`) and the Nextcloud admin password from
your config.

---

## 💾 Accessing Your Files

Your SSD is mounted at `/mnt/ncdata` with this layout:

| Path | Purpose | Owner |
| :-- | :-- | :-- |
| `/mnt/ncdata/nextcloud/` | Nextcloud's internal data (managed by NC — don't edit directly) | www-data (uid 33) |
| `/mnt/ncdata/files/` | **Samba share** — your "drop any file here" folder | your user (uid 1000) |
| `/mnt/ncdata/borg-backup/` | Local borg backup snapshots | root |

### Samba (recommended)

Already installed if you ran the Samba step. This gives you read/write access to `/mnt/ncdata/files/` from any device on your LAN.

**macOS:** Finder → Go → Connect to Server (⌘K) → `smb://<pi-ip>/NAS Files`

**Linux:** `smbclient //<pi-ip>/"NAS Files" -U <samba-user>`

**Windows:** File Explorer → `\\<pi-ip>\NAS Files`

### SSH / SCP

```bash
# Browse the SSD
ssh pi@<pi-ip>
ls -la /mnt/ncdata/files/

# Copy a file off the SSD
scp pi@<pi-ip>:/mnt/ncdata/files/somefile.pdf ./

# Copy a file onto the SSD
scp ./photo.jpg pi@<pi-ip>:/mnt/ncdata/files/
```

> You need `sudo` to access `/mnt/ncdata/nextcloud/` since it's owned by www-data.

### SFTP (GUI clients)

Use FileZilla, Cyberduck, WinSCP, etc. — connect to `<pi-ip>` with your SSH credentials, then navigate to `/mnt/ncdata/`.

### ⚠️ Don't manually edit `/mnt/ncdata/nextcloud/`

That folder is Nextcloud's internal database-tracked storage. Adding or removing files there directly will confuse Nextcloud. Instead:

- **To make files visible in Nextcloud:** put them in `/mnt/ncdata/files/` (the Samba share), then in the Nextcloud web UI go to **Admin → External Storage → Add storage → Local** and set the path to `/mnt/ncdata/files`. That folder will then appear alongside your other Nextcloud folders.
- **Or** upload via Nextcloud's web UI or desktop sync client as usual.

---

## 🤖 Telegram Bot

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

## 💰 Backups & Costs

Nightly restic backups go to **S3 Glacier Deep Archive** (eu-central-1).
Block-level deduplication means you only pay for ~your actual data size, not
`200GB × N nights`.

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
| ☁️ Nextcloud | `occ update:check` → maintenance mode → `occ upgrade` → maintenance mode off |
| 🤖 Bot deps | `pip install --upgrade` python-telegram-bot/APScheduler/requests + restart |
| 🔐 restic | `apt-get install --only-upgrade restic` |
| 📁 Samba | `apt-get install --only-upgrade samba` + restart smbd |

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
| AIO admin panel not reachable on :8080 | `docker logs nextcloud-aio-mastercontainer` |
| Nextcloud Talk calls fail across networks | Verify port 3478 TCP+UDP is forwarded on your router |
| Backup fails with S3 error | Check AWS credentials in `/etc/homecloud/.env` |
| Bot not responding | `systemctl status ncbot` + `journalctl -u ncbot -f` |
| SSD not mounted after reboot | Check `/etc/fstab` + `journalctl -b -u mnt-ncdata.mount` |
| Docker started but Nextcloud on SD card | The hardening step prevents this; re-run Repair |

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
│   │   ├── nextcloud_aio.py
│   │   ├── duckdns.py
│   │   ├── coturn.py
│   │   ├── samba.py
│   │   ├── wifi.py
│   │   ├── restic_s3.py
│   │   ├── telegram_bot.py
│   │   └── hardening.py
│   ├── services/                  # systemd, docker, cron managers
│   └── utils/                     # shell, logging, state, checks
└── templates/                     # Reference config files
```

---

## 📄 License

MIT
