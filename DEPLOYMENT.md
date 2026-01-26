# Deployment Guide - Gebrauchtwaffen Aggregator

This guide covers deploying the Gebrauchtwaffen Aggregator on a Raspberry Pi for 24/7 operation.

## Prerequisites

### Hardware
- Raspberry Pi 3B+ or newer (4 recommended)
- 16GB+ SD card
- Stable network connection

### Software
- Raspberry Pi OS (Debian-based, 64-bit recommended)
- Python 3.11 or 3.12
- SQLite 3 (included in Pi OS)

## Installation

### 1. System Preparation

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y python3 python3-pip python3-venv git sqlite3

# Install Poetry (Python dependency manager)
curl -sSL https://install.python-poetry.org | python3 -
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### 2. Clone and Setup Application

```bash
# Clone repository
cd ~
git clone https://github.com/your-repo/gebrauchtwaffen-aggregator.git gebrauchtwaffen_aggregator
cd gebrauchtwaffen_aggregator

# Create virtual environment and install dependencies
poetry install --no-dev

# Create required directories
mkdir -p data logs data/backups

# Initialize database
poetry run alembic upgrade head
```

### 3. Verify Installation

```bash
# Test the application starts
poetry run uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Open browser to http://<pi-ip>:8000
# Press Ctrl+C to stop
```

## Production Setup

### 4. Configure Systemd Service

The systemd service ensures the application:
- Starts automatically on boot
- Restarts if it crashes
- Integrates with system logging

```bash
# Copy service file
sudo cp deploy/gebrauchtwaffen.service /etc/systemd/system/

# Adjust paths if needed (default assumes /home/pi/gebrauchtwaffen_aggregator)
sudo nano /etc/systemd/system/gebrauchtwaffen.service

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable gebrauchtwaffen
sudo systemctl start gebrauchtwaffen

# Check status
sudo systemctl status gebrauchtwaffen
```

#### Service Management Commands

```bash
# View status
sudo systemctl status gebrauchtwaffen

# Stop service
sudo systemctl stop gebrauchtwaffen

# Start service
sudo systemctl start gebrauchtwaffen

# Restart service
sudo systemctl restart gebrauchtwaffen

# View logs
sudo journalctl -u gebrauchtwaffen -f

# View last 100 log lines
sudo journalctl -u gebrauchtwaffen -n 100
```

### 5. Configure Daily Crawl (Cron)

Set up automatic daily crawling at 06:00:

```bash
# Option 1: Use the provided cron file
sudo cp deploy/cron-daily-crawl /etc/cron.d/gebrauchtwaffen-crawl
sudo chmod 644 /etc/cron.d/gebrauchtwaffen-crawl

# Option 2: Edit user crontab manually
crontab -e
# Add line:
0 6 * * * cd /home/pi/gebrauchtwaffen_aggregator && /home/pi/gebrauchtwaffen_aggregator/.venv/bin/python -m backend.cli crawl >> /var/log/gebrauchtwaffen-crawl.log 2>&1
```

#### Manual Crawl

```bash
# Run crawl manually
cd ~/gebrauchtwaffen_aggregator
poetry run python -m backend.cli crawl
```

### 6. Configure Database Backups

Weekly backups with 4-backup rotation:

```bash
# Make backup script executable
chmod +x deploy/backup-database.sh

# Option 1: Use provided cron file
sudo cp deploy/cron-weekly-backup /etc/cron.d/gebrauchtwaffen-backup
sudo chmod 644 /etc/cron.d/gebrauchtwaffen-backup

# Option 2: Add to root crontab
sudo crontab -e
# Add line (runs Sunday 02:00):
0 2 * * 0 /home/pi/gebrauchtwaffen_aggregator/deploy/backup-database.sh >> /var/log/gebrauchtwaffen-backup.log 2>&1
```

#### Manual Backup

```bash
# Run backup manually
~/gebrauchtwaffen_aggregator/deploy/backup-database.sh

# List backups
ls -la ~/gebrauchtwaffen_aggregator/data/backups/
```

#### Restore from Backup

```bash
# Stop service first
sudo systemctl stop gebrauchtwaffen

# Copy backup to database location
cp data/backups/gebrauchtwaffen_20240115_020000.db data/gebrauchtwaffen.db

# Restart service
sudo systemctl start gebrauchtwaffen
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | INFO | Log level: DEBUG, INFO, WARNING, ERROR |
| `LOG_FILE` | logs/app.log | Log file path |
| `LOG_MAX_SIZE` | 5242880 | Max log size before rotation (5MB) |
| `LOG_BACKUP_COUNT` | 3 | Number of backup log files to keep |
| `USE_JOURNALD` | false | Enable journald logging (for systemd) |
| `DEBUG` | false | Enable debug mode |

### Adjusting Configuration

Edit the systemd service file to change environment variables:

```bash
sudo systemctl edit gebrauchtwaffen
```

Add overrides:
```ini
[Service]
Environment=LOG_LEVEL=DEBUG
```

Then reload:
```bash
sudo systemctl daemon-reload
sudo systemctl restart gebrauchtwaffen
```

## Monitoring

### Check Application Status

```bash
# Service status
sudo systemctl status gebrauchtwaffen

# Recent logs
sudo journalctl -u gebrauchtwaffen -n 50

# Follow logs in real-time
sudo journalctl -u gebrauchtwaffen -f

# Check crawl logs
tail -f /var/log/gebrauchtwaffen-crawl.log
```

### Check Resource Usage

```bash
# Memory and CPU
htop

# Disk space
df -h

# Database size
ls -lh ~/gebrauchtwaffen_aggregator/data/gebrauchtwaffen.db
```

## Troubleshooting

### Service Won't Start

1. Check logs:
   ```bash
   sudo journalctl -u gebrauchtwaffen -n 100 --no-pager
   ```

2. Verify paths in service file:
   ```bash
   cat /etc/systemd/system/gebrauchtwaffen.service
   ```

3. Test manually:
   ```bash
   cd ~/gebrauchtwaffen_aggregator
   poetry run uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```

### Database Issues

1. Check database exists:
   ```bash
   ls -la ~/gebrauchtwaffen_aggregator/data/
   ```

2. Run migrations:
   ```bash
   cd ~/gebrauchtwaffen_aggregator
   poetry run alembic upgrade head
   ```

3. Check database integrity:
   ```bash
   sqlite3 data/gebrauchtwaffen.db "PRAGMA integrity_check;"
   ```

### Crawl Not Running

1. Check cron is installed:
   ```bash
   cat /etc/cron.d/gebrauchtwaffen-crawl
   ```

2. Check cron logs:
   ```bash
   grep gebrauchtwaffen /var/log/syslog
   ```

3. Test crawl manually:
   ```bash
   cd ~/gebrauchtwaffen_aggregator
   poetry run python -m backend.cli crawl
   ```

### Permission Errors

1. Check ownership:
   ```bash
   ls -la ~/gebrauchtwaffen_aggregator/
   ls -la ~/gebrauchtwaffen_aggregator/data/
   ```

2. Fix permissions:
   ```bash
   sudo chown -R pi:pi ~/gebrauchtwaffen_aggregator
   chmod 755 ~/gebrauchtwaffen_aggregator/data
   chmod 644 ~/gebrauchtwaffen_aggregator/data/gebrauchtwaffen.db
   ```

### Network/Scraper Issues

1. Check network:
   ```bash
   ping -c 3 waffenboerse.ch
   ```

2. Test scraper manually:
   ```bash
   cd ~/gebrauchtwaffen_aggregator
   poetry run python -c "from backend.scrapers import scrape_waffenboerse; import asyncio; print(asyncio.run(scrape_waffenboerse())[:2])"
   ```

## Updating

### Update Application

```bash
# Stop service
sudo systemctl stop gebrauchtwaffen

# Pull latest code
cd ~/gebrauchtwaffen_aggregator
git pull

# Update dependencies
poetry install --no-dev

# Run migrations
poetry run alembic upgrade head

# Restart service
sudo systemctl start gebrauchtwaffen
```

## Security Notes

- The application is designed for local network use only
- No authentication is implemented (single-user, trusted network)
- Do not expose port 8000 to the internet
- Consider using a firewall (ufw) to restrict access

```bash
# Basic firewall setup (optional)
sudo apt install ufw
sudo ufw allow ssh
sudo ufw allow from 192.168.0.0/16 to any port 8000
sudo ufw enable
```

## File Locations

| Path | Description |
|------|-------------|
| `/home/pi/gebrauchtwaffen_aggregator/` | Application root |
| `/home/pi/gebrauchtwaffen_aggregator/data/gebrauchtwaffen.db` | SQLite database |
| `/home/pi/gebrauchtwaffen_aggregator/data/backups/` | Database backups |
| `/home/pi/gebrauchtwaffen_aggregator/logs/app.log` | Application logs |
| `/etc/systemd/system/gebrauchtwaffen.service` | Systemd service |
| `/etc/cron.d/gebrauchtwaffen-crawl` | Daily crawl cron |
| `/etc/cron.d/gebrauchtwaffen-backup` | Weekly backup cron |
| `/var/log/gebrauchtwaffen-crawl.log` | Crawl command logs |
| `/var/log/gebrauchtwaffen-backup.log` | Backup script logs |
