#!/bin/bash
# Update script for Gilbert's Gun Crawler
# Usage: ./deploy/update.sh

set -e  # Exit on error

APP_DIR="/home/pi/gilberts-gun-crawler"
SERVICE_NAME="gilberts-gun-crawler"

echo "=== Updating Gilbert's Gun Crawler ==="

# Stop service
echo "Stopping service..."
sudo systemctl stop $SERVICE_NAME 2>/dev/null || true

# Pull latest code
echo "Pulling latest code..."
cd $APP_DIR
git pull

# Update service file if changed
echo "Updating service file..."
sudo cp $APP_DIR/deploy/gilberts-gun-crawler.service /etc/systemd/system/
sudo systemctl daemon-reload

# Run migrations (if any)
echo "Running database migrations..."
source $APP_DIR/.venv/bin/activate
python -m alembic upgrade head

# Start service
echo "Starting service..."
sudo systemctl start $SERVICE_NAME

# Show status
echo ""
echo "=== Update complete ==="
sudo systemctl status $SERVICE_NAME --no-pager
