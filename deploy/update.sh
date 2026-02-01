#!/bin/bash
# Update script for Gilbert's Yoga Helper
# Usage: ./deploy/update.sh

set -e  # Exit on error

APP_DIR="/home/pi/gilberts-yoga-helper"
SERVICE_NAME="gilberts-yoga-helper"

echo "=== Updating Gilbert's Yoga Helper ==="

# Stop service
echo "Stopping service..."
sudo systemctl stop $SERVICE_NAME 2>/dev/null || true

# Pull latest code
echo "Pulling latest code..."
cd $APP_DIR
git pull

# Update service file if changed
echo "Updating service file..."
sudo cp $APP_DIR/deploy/gilberts-yoga-helper.service /etc/systemd/system/
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
