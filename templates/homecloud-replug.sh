#!/usr/bin/env bash
# homecloud: hot-replug recovery script.
# Installed to /usr/local/bin/homecloud-replug.sh
#
# Called by ncdata-replug.service when the SSD reappears after being unplugged.
# Logs everything to syslog (visible via: journalctl -u ncdata-replug.service).
set -euo pipefail

MOUNT_POINT="/mnt/ncdata"
LOG_TAG="homecloud-replug"

log() {
    logger -t "$LOG_TAG" -- "$*"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [replug] $*"
}

log "=== SSD hot-replug recovery started ==="

# 1. Filesystem check (safe: read-only unless corruption found)
DEVICE=$(findmnt -n -o SOURCE "$MOUNT_POINT" 2>/dev/null || true)
if [ -z "$DEVICE" ]; then
    # Mount is gone — try to resolve from fstab LABEL
    LABEL=$(grep "$MOUNT_POINT" /etc/fstab 2>/dev/null | head -1 | grep -oP 'LABEL=\K\S+' || echo "ncdata")
    DEVICE=$(blkid -L "$LABEL" 2>/dev/null || true)
    if [ -z "$DEVICE" ]; then
        log "ERROR: could not find SSD device by label $LABEL"
        exit 1
    fi
fi
log "SSD device: $DEVICE"

log "Running fsck (safe check)..."
if fsck -n "$DEVICE" 2>&1; then
    log "fsck: filesystem clean"
else
    log "WARNING: fsck found issues — attempting repair..."
    fsck -y "$DEVICE" 2>&1 || true
fi

# 2. Mount
log "Mounting $MOUNT_POINT..."
if mount "$MOUNT_POINT" 2>&1; then
    log "Mount succeeded"
else
    log "ERROR: mount failed"
    exit 1
fi

# 3. Brief settle — let the kernel flush device nodes
sleep 2

# 4. Restart Docker (containers with --restart=always will auto-recover)
log "Restarting Docker..."
systemctl restart docker 2>&1 || true

# Give Docker a moment to initialize
sleep 3

# 5. Restart Nextcloud AIO master container (cascades to all AIO children)
log "Restarting Nextcloud AIO..."
docker restart nextcloud-aio-mastercontainer 2>&1 || true

log "=== SSD hot-replug recovery finished ==="
