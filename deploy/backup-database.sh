#!/bin/bash
# Database backup script for Gilbert's Yoga Helper
# Creates timestamped backups and keeps the last 4 copies
#
# Install: chmod +x deploy/backup-database.sh
# Usage: ./deploy/backup-database.sh

set -e

# Configuration
APP_DIR="/home/pi/gilberts-yoga-helper"
DB_FILE="$APP_DIR/data/app.db"
BACKUP_DIR="$APP_DIR/data/backups"
MAX_BACKUPS=4

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Create timestamped backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/app_${TIMESTAMP}.db"

# Use SQLite backup command for safe backup (handles WAL mode)
sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"

echo "Backup created: $BACKUP_FILE"

# Remove old backups (keep only MAX_BACKUPS)
cd "$BACKUP_DIR"
ls -t app_*.db 2>/dev/null | tail -n +$((MAX_BACKUPS + 1)) | xargs -r rm -f

echo "Backup complete. Current backups:"
ls -la "$BACKUP_DIR"
