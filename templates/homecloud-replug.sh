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

# 4. Restart Docker (containers with --restart=always will recover in undefined order)
log "Restarting Docker..."
systemctl restart docker 2>&1 || true

# Wait for Docker daemon to be fully ready
log "Waiting for Docker daemon..."
for i in $(seq 1 30); do
    if docker info >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# 5. Wait for the database container to be running and accepting connections.
#    After a Docker restart, containers come up in undefined order.
#    If Nextcloud starts before the database, it loops on
#    "could not translate host name nextcloud-aio-database to address".
#    So we explicitly wait for the DB to be ready before restarting the master.
log "Waiting for database container to be ready..."
DB_CONTAINER="nextcloud-aio-database"
for i in $(seq 1 60); do
    STATUS=$(docker inspect -f '{{.State.Status}}' "$DB_CONTAINER" 2>/dev/null || echo "missing")
    if [ "$STATUS" = "running" ]; then
        # Container is running — check if PostgreSQL accepts connections
        if docker exec "$DB_CONTAINER" pg_isready -U nextcloud >/dev/null 2>&1; then
            log "Database is ready (took ${i}s)"
            break
        fi
    fi
    if [ "$i" -eq 60 ]; then
        log "WARNING: database not ready after 60s — proceeding anyway"
    fi
    sleep 1
done
# Small extra grace period for DNS propagation inside Docker network
sleep 3

# 6. Restart Nextcloud AIO master container (cascades to all AIO children)
log "Restarting Nextcloud AIO..."
docker restart nextcloud-aio-mastercontainer 2>&1 || true

log "=== SSD hot-replug recovery finished ==="
