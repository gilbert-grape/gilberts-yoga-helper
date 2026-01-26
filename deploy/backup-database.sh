#!/bin/bash
#
# Database Backup Script for Gebrauchtwaffen Aggregator
#
# Creates timestamped SQLite backups and maintains rotation (keeps last 4).
# Designed for weekly cron execution.
#
# Installation:
#   chmod +x deploy/backup-database.sh
#   sudo cp deploy/backup-database.sh /usr/local/bin/gebrauchtwaffen-backup
#
# Cron setup (weekly on Sunday at 02:00):
#   sudo crontab -e
#   0 2 * * 0 /usr/local/bin/gebrauchtwaffen-backup
#
# Or add to /etc/cron.d/:
#   sudo cp deploy/cron-weekly-backup /etc/cron.d/gebrauchtwaffen-backup
#
# Configuration: Adjust paths below as needed

set -e

# Configuration
APP_DIR="${APP_DIR:-/home/pi/gebrauchtwaffen_aggregator}"
DB_FILE="${APP_DIR}/data/gebrauchtwaffen.db"
BACKUP_DIR="${APP_DIR}/data/backups"
MAX_BACKUPS=4
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/gebrauchtwaffen_${TIMESTAMP}.db"

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Check if database exists
if [ ! -f "$DB_FILE" ]; then
    log "ERROR: Database file not found: $DB_FILE"
    exit 1
fi

# Create backup directory if it doesn't exist
if [ ! -d "$BACKUP_DIR" ]; then
    log "Creating backup directory: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
fi

# Create backup using SQLite's backup command (safer for WAL mode)
log "Starting backup of $DB_FILE"
sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"

if [ $? -eq 0 ]; then
    log "Backup created successfully: $BACKUP_FILE"

    # Get backup size
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log "Backup size: $BACKUP_SIZE"
else
    log "ERROR: Backup failed!"
    exit 1
fi

# Rotate old backups (keep only MAX_BACKUPS most recent)
log "Checking for old backups to rotate..."
BACKUP_COUNT=$(ls -1 "${BACKUP_DIR}"/gebrauchtwaffen_*.db 2>/dev/null | wc -l)

if [ "$BACKUP_COUNT" -gt "$MAX_BACKUPS" ]; then
    # Calculate how many to delete
    DELETE_COUNT=$((BACKUP_COUNT - MAX_BACKUPS))
    log "Removing $DELETE_COUNT old backup(s)..."

    # Delete oldest backups (sorted by name = sorted by date due to timestamp format)
    ls -1 "${BACKUP_DIR}"/gebrauchtwaffen_*.db | head -n "$DELETE_COUNT" | while read OLD_BACKUP; do
        log "Deleting: $OLD_BACKUP"
        rm -f "$OLD_BACKUP"
    done
fi

# List current backups
log "Current backups:"
ls -lh "${BACKUP_DIR}"/gebrauchtwaffen_*.db 2>/dev/null || log "  (none)"

log "Backup completed successfully"
exit 0
