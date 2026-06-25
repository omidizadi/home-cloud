#!/usr/bin/env bash
# homecloud: hot-replug recovery script.
# Installed to /usr/local/bin/homecloud-replug.sh
#
# Called by data-replug.service when the SSD reappears after being unplugged.
# Logs everything to syslog (visible via: journalctl -u data-replug.service).
set -euo pipefail

MOUNT_POINT="/mnt/data"
COMPOSE_FILE="/opt/homecloud/immich/docker-compose.yml"
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
    LABEL=$(grep "$MOUNT_POINT" /etc/fstab 2>/dev/null | head -1 | grep -oP 'LABEL=\K\S+' || echo "data")
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

# 4. Restart Docker (containers with restart: always will recover)
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

# 5. Wait for the Immich postgres container to be running and accepting
#    connections. After a Docker restart, containers come up in undefined
#    order. If immich-server starts before the database, it will crash-loop.
log "Waiting for Immich postgres to be ready..."
DB_CONTAINER="immich-postgres"
for i in $(seq 1 60); do
    STATUS=$(docker inspect -f '{{.State.Status}}' "$DB_CONTAINER" 2>/dev/null || echo "missing")
    if [ "$STATUS" = "running" ]; then
        if docker exec "$DB_CONTAINER" pg_isready -U postgres >/dev/null 2>&1; then
            log "Immich postgres is ready (took ${i}s)"
            break
        fi
    fi
    if [ "$i" -eq 60 ]; then
        log "WARNING: Immich postgres not ready after 60s — proceeding anyway"
    fi
    sleep 1
done
# Small extra grace period for DNS propagation inside Docker network
sleep 3

# 6. Restart the Immich stack via docker compose
log "Restarting Immich stack..."
if [ -f "$COMPOSE_FILE" ]; then
    docker compose -f "$COMPOSE_FILE" up -d 2>&1 || true
else
    log "WARNING: compose file not found at $COMPOSE_FILE — skipping stack restart"
fi

log "=== SSD hot-replug recovery finished ==="
