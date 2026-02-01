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

# Install build dependencies for lxml (required for HTML parsing)
sudo apt install -y libxml2-dev libxslt-dev

# Install Poetry (Python dependency manager)
curl -sSL https://install.python-poetry.org | python3 -
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### 2. Clone and Setup Application

```bash
# Clone repository
cd ~
git clone https://github.com/gilbert-grape/gilberts-gun-crawler.git gilberts-gun-crawler
cd gilberts-gun-crawler

# Create virtual environment and install dependencies
poetry install --only main

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
sudo cp deploy/gilberts-gun-crawler.service /etc/systemd/system/

# Adjust paths if needed (default assumes /home/pi/gilberts-gun-crawler)
sudo nano /etc/systemd/system/gilberts-gun-crawler.service

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable gilberts-gun-crawler
sudo systemctl start gilberts-gun-crawler

# Check status
sudo systemctl status gilberts-gun-crawler
```

#### Service Management Commands

```bash
# View status
sudo systemctl status gilberts-gun-crawler

# Stop service
sudo systemctl stop gilberts-gun-crawler

# Start service
sudo systemctl start gilberts-gun-crawler

# Restart service
sudo systemctl restart gilberts-gun-crawler

# View logs
sudo journalctl -u gilberts-gun-crawler -f

# View last 100 log lines
sudo journalctl -u gilberts-gun-crawler -n 100
```

### 5. Configure Daily Crawl (Cron)

Set up automatic daily crawling at 06:00:

```bash
# Option 1: Use the provided cron file
sudo cp deploy/cron-daily-crawl /etc/cron.d/gilberts-gun-crawler-crawl
sudo chmod 644 /etc/cron.d/gilberts-gun-crawler-crawl

# Option 2: Edit user crontab manually
crontab -e
# Add line:
0 6 * * * cd /home/pi/gilberts-gun-crawler && /home/pi/gilberts-gun-crawler/.venv/bin/python -m backend.cli crawl >> /var/log/gilberts-gun-crawler-crawl.log 2>&1
```

#### Manual Crawl

```bash
# Run crawl manually
cd ~/gilberts-gun-crawler
poetry run python -m backend.cli crawl
```

### 6. Configure Database Backups

Weekly backups with 4-backup rotation:

```bash
# Make backup script executable
chmod +x deploy/backup-database.sh

# Option 1: Use provided cron file
sudo cp deploy/cron-weekly-backup /etc/cron.d/gilberts-gun-crawler-backup
sudo chmod 644 /etc/cron.d/gilberts-gun-crawler-backup

# Option 2: Add to root crontab
sudo crontab -e
# Add line (runs Sunday 02:00):
0 2 * * 0 /home/pi/gilberts-gun-crawler/deploy/backup-database.sh >> /var/log/gilberts-gun-crawler-backup.log 2>&1
```

#### Manual Backup

```bash
# Run backup manually
~/gilberts-gun-crawler/deploy/backup-database.sh

# List backups
ls -la ~/gilberts-gun-crawler/data/backups/
```

#### Restore from Backup

```bash
# Stop service first
sudo systemctl stop gilberts-gun-crawler

# Copy backup to database location
cp data/backups/gilberts-gun-crawler_20240115_020000.db data/gilberts-gun-crawler.db

# Restart service
sudo systemctl start gilberts-gun-crawler
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
sudo systemctl edit gilberts-gun-crawler
```

Add overrides:
```ini
[Service]
Environment=LOG_LEVEL=DEBUG
```

Then reload:
```bash
sudo systemctl daemon-reload
sudo systemctl restart gilberts-gun-crawler
```

## Monitoring

### Check Application Status

```bash
# Service status
sudo systemctl status gilberts-gun-crawler

# Recent logs
sudo journalctl -u gilberts-gun-crawler -n 50

# Follow logs in real-time
sudo journalctl -u gilberts-gun-crawler -f

# Check crawl logs
tail -f /var/log/gilberts-gun-crawler-crawl.log
```

### Check Resource Usage

```bash
# Memory and CPU
htop

# Disk space
df -h

# Database size
ls -lh ~/gilberts-gun-crawler/data/gilberts-gun-crawler.db
```

## Troubleshooting

### Service Won't Start

1. Check logs:
   ```bash
   sudo journalctl -u gilberts-gun-crawler -n 100 --no-pager
   ```

2. Verify paths in service file:
   ```bash
   cat /etc/systemd/system/gilberts-gun-crawler.service
   ```

3. Test manually:
   ```bash
   cd ~/gilberts-gun-crawler
   poetry run uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```

### Database Issues

1. Check database exists:
   ```bash
   ls -la ~/gilberts-gun-crawler/data/
   ```

2. Run migrations:
   ```bash
   cd ~/gilberts-gun-crawler
   poetry run alembic upgrade head
   ```

3. Check database integrity:
   ```bash
   sqlite3 data/gilberts-gun-crawler.db "PRAGMA integrity_check;"
   ```

### Poetry/lxml Installation Fails

If `poetry install` fails with "Please make sure the libxml2 and libxslt development packages are installed":

1. Install system dependencies:
   ```bash
   sudo apt-get update && sudo apt-get install -y libxml2-dev libxslt-dev
   ```

2. Clear the broken virtualenv cache:
   ```bash
   rm -rf ~/.cache/pypoetry/virtualenvs/gilberts-*
   ```

3. Retry installation:
   ```bash
   poetry install --only main
   ```

### Crawl Not Running

1. Check cron is installed:
   ```bash
   cat /etc/cron.d/gilberts-gun-crawler-crawl
   ```

2. Check cron logs:
   ```bash
   grep gilberts-gun-crawler /var/log/syslog
   ```

3. Test crawl manually:
   ```bash
   cd ~/gilberts-gun-crawler
   poetry run python -m backend.cli crawl
   ```

### Permission Errors

1. Check ownership:
   ```bash
   ls -la ~/gilberts-gun-crawler/
   ls -la ~/gilberts-gun-crawler/data/
   ```

2. Fix permissions:
   ```bash
   sudo chown -R pi:pi ~/gilberts-gun-crawler
   chmod 755 ~/gilberts-gun-crawler/data
   chmod 644 ~/gilberts-gun-crawler/data/gilberts-gun-crawler.db
   ```

### Network/Scraper Issues

1. Check network:
   ```bash
   ping -c 3 waffenboerse.ch
   ```

2. Test scraper manually:
   ```bash
   cd ~/gilberts-gun-crawler
   poetry run python -c "from backend.scrapers import scrape_waffenboerse; import asyncio; print(asyncio.run(scrape_waffenboerse())[:2])"
   ```

## Updating

### Update Application

```bash
# Stop service
sudo systemctl stop gilberts-gun-crawler

# Pull latest code
cd ~/gilberts-gun-crawler
git pull

# Activate virtual environment
source .venv/bin/activate

# Update dependencies
pip install -r requirements.txt

# Run migrations
python -m alembic upgrade head

# Restart service
sudo systemctl start gilberts-gun-crawler
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

## Remote Access with Tailscale

Tailscale provides secure remote access to your Pi without exposing any ports to the internet. It creates a private VPN mesh network between your devices.

### Why Tailscale?

- **No port forwarding needed** - Works behind NAT/firewalls
- **No DuckDNS needed** - Direct device-to-device connection
- **Zero configuration** - Just install and login
- **Secure by default** - WireGuard-based encryption
- **Free for personal use** - Up to 100 devices

### Installation on Raspberry Pi

```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh

# Start Tailscale and authenticate
sudo tailscale up

# A URL will be displayed - open it in your browser to authorize the Pi
```

### Installation on Your Devices

- **iPhone/Android:** Install "Tailscale" from App Store / Play Store
- **Windows/Mac/Linux:** Download from https://tailscale.com/download
- Login with the same account used on the Pi

### Accessing the Application

After setup, your Pi gets a Tailscale IP (100.x.x.x). Find it with:

```bash
tailscale ip -4
```

Access the application from anywhere:
```
http://100.x.x.x:8000
```

### Enable MagicDNS (Recommended)

MagicDNS lets you use hostnames instead of IPs:

1. Go to https://login.tailscale.com/admin/dns
2. Enable "MagicDNS"
3. Access your Pi using its hostname:
   ```
   http://pi3:8000
   ```

### Tailscale Service Management

```bash
# Check Tailscale status
tailscale status

# View your Tailscale IP
tailscale ip -4

# Disconnect temporarily
sudo tailscale down

# Reconnect
sudo tailscale up

# View connected devices
tailscale status
```

### Tailscale on Boot

Tailscale installs as a systemd service and starts automatically:

```bash
# Check service status
sudo systemctl status tailscaled

# Enable on boot (usually already enabled)
sudo systemctl enable tailscaled
```

### Firewall Adjustment for Tailscale

If you're using ufw, allow Tailscale traffic:

```bash
sudo ufw allow in on tailscale0
```

## File Locations

| Path | Description |
|------|-------------|
| `~/gilberts-gun-crawler/` | Application root |
| `~/gilberts-gun-crawler/data/app.db` | SQLite database |
| `~/gilberts-gun-crawler/data/backups/` | Database backups |
| `~/gilberts-gun-crawler/logs/app.log` | Application logs |
| `/etc/systemd/system/gilberts-gun-crawler.service` | Systemd service |
| `/etc/cron.d/gilberts-gun-crawler-crawl` | Daily crawl cron |
| `/etc/cron.d/gilberts-gun-crawler-backup` | Weekly backup cron |
