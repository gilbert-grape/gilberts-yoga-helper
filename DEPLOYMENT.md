# Deployment Guide - Gilbert's Yoga Helper

This guide covers deploying Gilbert's Yoga Helper on a Raspberry Pi for 24/7 operation.

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

```

### 2. Clone and Setup Application

```bash
# Clone repository
cd ~
git clone https://github.com/gilbert-grape/gilberts-yoga-helper.git gilberts-yoga-helper
cd gilberts-yoga-helper

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install fastapi uvicorn jinja2 httpx beautifulsoup4 sqlalchemy alembic python-dotenv python-multipart typing_extensions

# Create required directories
mkdir -p data logs data/backups

# Initialize database
python -m alembic upgrade head
```

### 3. Verify Installation

```bash
# Test the application starts (ensure venv is activated)
source .venv/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

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
sudo cp deploy/gilberts-yoga-helper.service /etc/systemd/system/

# Adjust paths if needed (default assumes /home/pi/gilberts-yoga-helper)
sudo nano /etc/systemd/system/gilberts-yoga-helper.service

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable gilberts-yoga-helper
sudo systemctl start gilberts-yoga-helper

# Check status
sudo systemctl status gilberts-yoga-helper
```

#### Service Management Commands

```bash
# View status
sudo systemctl status gilberts-yoga-helper

# Stop service
sudo systemctl stop gilberts-yoga-helper

# Start service
sudo systemctl start gilberts-yoga-helper

# Restart service
sudo systemctl restart gilberts-yoga-helper

# View logs
sudo journalctl -u gilberts-yoga-helper -f

# View last 100 log lines
sudo journalctl -u gilberts-yoga-helper -n 100
```

### 5. Configure Daily Crawl (Cron)

Set up automatic daily crawling at 06:00:

```bash
# Option 1: Use the provided cron file
sudo cp deploy/cron-daily-crawl /etc/cron.d/gilberts-yoga-helper-crawl
sudo chmod 644 /etc/cron.d/gilberts-yoga-helper-crawl

# Option 2: Edit user crontab manually
crontab -e
# Add line:
0 6 * * * cd /home/pi/gilberts-yoga-helper && /home/pi/gilberts-yoga-helper/.venv/bin/python -m backend.cli crawl >> /var/log/gilberts-yoga-helper-crawl.log 2>&1
```

#### Manual Crawl

```bash
# Run crawl manually
cd ~/gilberts-yoga-helper
source .venv/bin/activate
python -m backend.cli crawl
```

### 6. Configure Database Backups

Weekly backups with 4-backup rotation:

```bash
# Make backup script executable
chmod +x deploy/backup-database.sh

# Option 1: Use provided cron file
sudo cp deploy/cron-weekly-backup /etc/cron.d/gilberts-yoga-helper-backup
sudo chmod 644 /etc/cron.d/gilberts-yoga-helper-backup

# Option 2: Add to root crontab
sudo crontab -e
# Add line (runs Sunday 02:00):
0 2 * * 0 /home/pi/gilberts-yoga-helper/deploy/backup-database.sh >> /var/log/gilberts-yoga-helper-backup.log 2>&1
```

#### Manual Backup

```bash
# Run backup manually
~/gilberts-yoga-helper/deploy/backup-database.sh

# List backups
ls -la ~/gilberts-yoga-helper/data/backups/
```

#### Restore from Backup

```bash
# Stop service first
sudo systemctl stop gilberts-yoga-helper

# Copy backup to database location
cp data/backups/gilberts-yoga-helper_20240115_020000.db data/gilberts-yoga-helper.db

# Restart service
sudo systemctl start gilberts-yoga-helper
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
sudo systemctl edit gilberts-yoga-helper
```

Add overrides:
```ini
[Service]
Environment=LOG_LEVEL=DEBUG
```

Then reload:
```bash
sudo systemctl daemon-reload
sudo systemctl restart gilberts-yoga-helper
```

## Monitoring

### Check Application Status

```bash
# Service status
sudo systemctl status gilberts-yoga-helper

# Recent logs
sudo journalctl -u gilberts-yoga-helper -n 50

# Follow logs in real-time
sudo journalctl -u gilberts-yoga-helper -f

# Check crawl logs
tail -f /var/log/gilberts-yoga-helper-crawl.log
```

### Check Resource Usage

```bash
# Memory and CPU
htop

# Disk space
df -h

# Database size
ls -lh ~/gilberts-yoga-helper/data/gilberts-yoga-helper.db
```

## Troubleshooting

### Service Won't Start

1. Check logs:
   ```bash
   sudo journalctl -u gilberts-yoga-helper -n 100 --no-pager
   ```

2. Verify paths in service file:
   ```bash
   cat /etc/systemd/system/gilberts-yoga-helper.service
   ```

3. Test manually:
   ```bash
   cd ~/gilberts-yoga-helper
   source .venv/bin/activate
   python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```

### Database Issues

1. Check database exists:
   ```bash
   ls -la ~/gilberts-yoga-helper/data/
   ```

2. Run migrations:
   ```bash
   cd ~/gilberts-yoga-helper
   source .venv/bin/activate
   python -m alembic upgrade head
   ```

3. Check database integrity:
   ```bash
   sqlite3 data/gilberts-yoga-helper.db "PRAGMA integrity_check;"
   ```

### Pip Installation Fails

If `pip install` fails with dependency errors:

1. Ensure venv is activated:
   ```bash
   source .venv/bin/activate
   ```

2. Update pip:
   ```bash
   pip install --upgrade pip
   ```

3. Retry installation:
   ```bash
   pip install fastapi uvicorn jinja2 httpx beautifulsoup4 sqlalchemy alembic python-dotenv python-multipart typing_extensions
   ```

### Crawl Not Running

1. Check cron is installed:
   ```bash
   cat /etc/cron.d/gilberts-yoga-helper-crawl
   ```

2. Check cron logs:
   ```bash
   grep gilberts-yoga-helper /var/log/syslog
   ```

3. Test crawl manually:
   ```bash
   cd ~/gilberts-yoga-helper
   source .venv/bin/activate
   python -m backend.cli crawl
   ```

### Permission Errors

1. Check ownership:
   ```bash
   ls -la ~/gilberts-yoga-helper/
   ls -la ~/gilberts-yoga-helper/data/
   ```

2. Fix permissions:
   ```bash
   sudo chown -R pi:pi ~/gilberts-yoga-helper
   chmod 755 ~/gilberts-yoga-helper/data
   chmod 644 ~/gilberts-yoga-helper/data/gilberts-yoga-helper.db
   ```

### Network/Scraper Issues

1. Check network:
   ```bash
   ping -c 3 waffenboerse.ch
   ```

2. Test scraper manually:
   ```bash
   cd ~/gilberts-yoga-helper
   source .venv/bin/activate
   python -c "from backend.scrapers import scrape_waffenboerse; import asyncio; print(asyncio.run(scrape_waffenboerse())[:2])"
   ```

## Updating

### Quick Update (Recommended)

Use the update script for one-command updates:

```bash
# First time only: make script executable
chmod +x ~/gilberts-yoga-helper/deploy/update.sh

# Run update
~/gilberts-yoga-helper/deploy/update.sh
```

The script automatically:
1. Stops the service
2. Pulls latest code
3. Updates the systemd service file
4. Runs database migrations
5. Starts the service
6. Shows status

### Manual Update

If you prefer manual steps:

```bash
sudo systemctl stop gilberts-yoga-helper
cd ~/gilberts-yoga-helper
git pull
sudo cp deploy/gilberts-yoga-helper.service /etc/systemd/system/
sudo systemctl daemon-reload
source .venv/bin/activate
python -m alembic upgrade head
sudo systemctl start gilberts-yoga-helper
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
| `~/gilberts-yoga-helper/` | Application root |
| `~/gilberts-yoga-helper/data/app.db` | SQLite database |
| `~/gilberts-yoga-helper/data/backups/` | Database backups |
| `~/gilberts-yoga-helper/logs/app.log` | Application logs |
| `/etc/systemd/system/gilberts-yoga-helper.service` | Systemd service |
| `/etc/cron.d/gilberts-yoga-helper-crawl` | Daily crawl cron |
| `/etc/cron.d/gilberts-yoga-helper-backup` | Weekly backup cron |
