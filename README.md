# Gilbert's Yoga Helper

Personal web aggregator that monitors multiple sources and notifies you of new listings matching your search terms.

## Features

- Aggregates listings from multiple sources
- Configurable search terms with exact or partial matching
- Highlights new matches since last visit
- Manual and automated (cron) crawling
- Admin interface for managing sources and search terms
- Designed for 24/7 operation on Raspberry Pi

## Technology Stack

- Python 3.11+
- FastAPI + Uvicorn
- Jinja2 Templates + HTMX
- TailwindCSS + Flowbite
- SQLAlchemy + SQLite (WAL mode)
- Poetry for dependency management

## Quick Start

### Prerequisites

- Python 3.7+ (3.7, 3.8, 3.9, 3.10, 3.11, or 3.12)
- Poetry (dependency manager)

**Install Poetry:**

- **Windows (PowerShell):**
  ```powershell
  (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
  ```
  Then add `%APPDATA%\Python\Scripts` to your PATH.

- **Linux/macOS:**
  ```bash
  curl -sSL https://install.python-poetry.org | python3 -
  ```

### Installation

#### Windows (PowerShell or Command Prompt)

```powershell
# Clone the repository
git clone https://github.com/gilbert-grape/gilberts-yoga-helper.git
cd gilberts-yoga-helper

# Install dependencies
poetry install

# Create required directories
mkdir data
mkdir logs
```

#### Linux/macOS

```bash
# Clone the repository
git clone https://github.com/gilbert-grape/gilberts-yoga-helper.git
cd gilberts-yoga-helper

# Install dependencies
poetry install

# Create required directories
mkdir -p data logs
```

#### Raspberry Pi

z.B. installieren in `/home/pi/gilberts-yoga-helper` (oder `/opt/` für system-weite Installation)

Das Projekt unterstützt **Python 3.7+**, sodass auch ältere Raspberry Pi OS Versionen (Buster, Bullseye) funktionieren.

```bash
# Update system and install dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git sqlite3 libxml2-dev libxslt1-dev

# Install Poetry (1.5.1 for Python 3.7, or latest for Python 3.8+)
curl -sSL https://install.python-poetry.org | python3 - --version 1.5.1
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Clone repository
cd ~
git clone https://github.com/gilbert-grape/gilberts-yoga-helper.git
cd gilberts-yoga-helper

# Install dependencies (without dev dependencies for production)
poetry install --no-dev

# Create required directories
mkdir -p data logs data/backups
```

For full Raspberry Pi production setup with systemd service, automatic daily crawls, and database backups, see [DEPLOYMENT.md](DEPLOYMENT.md).

### Initialize Database

```bash
python -m alembic upgrade head
```

### Start the Application

```bash
# Development mode (with auto-reload)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

**Note:** Make sure the virtual environment is activated first:
```bash
# Linux/macOS/Raspberry Pi
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Open your browser to **http://localhost:8000**

## Usage

### Dashboard

The main page shows all matches grouped by search term. New matches (since your last visit) are highlighted in yellow.

### Admin Pages

- **Search Terms** (`/admin/search-terms`) - Add, delete, and configure search terms
- **Sources** (`/admin/sources`) - View and toggle scraper sources
- **Crawl Control** (`/admin/crawl`) - Trigger manual crawls and view status

### CLI Commands

```bash
# Run a crawl from command line (useful for cron)
python -m backend.cli crawl

# Show help
python -m backend.cli --help
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=backend

# Run specific test file
pytest tests/test_scrapers.py
```

## Project Structure

```
gilberts-yoga-helper/
├── backend/           # FastAPI application
│   ├── database/      # SQLAlchemy models and CRUD
│   ├── scrapers/      # Web scrapers per source
│   ├── services/      # Business logic (crawler, matcher)
│   ├── utils/         # Utilities and logging
│   ├── main.py        # FastAPI app and routes
│   ├── cli.py         # Command-line interface
│   └── config.py      # Configuration settings
├── frontend/
│   ├── templates/     # Jinja2 templates
│   └── public/        # Static files (CSS, JS)
├── tests/             # Pytest tests
├── deploy/            # Deployment configs (systemd, cron, backup)
├── data/              # SQLite database (gitignored)
└── logs/              # Application logs (gitignored)
```

## Configuration

Environment variables (can be set in `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | false | Enable debug mode |
| `LOG_LEVEL` | INFO | Log level: DEBUG, INFO, WARNING, ERROR |
| `LOG_FILE` | logs/app.log | Log file path |
| `DATABASE_URL` | sqlite:///data/yoga_helper.db | Database connection |

## Upgrading

When a new version is released, follow these steps to upgrade:

### Quick Upgrade (Raspberry Pi / Linux)

```bash
cd ~/gilberts-yoga-helper

# 1. Backup database (recommended)
cp data/yoga_helper.db data/yoga_helper_backup_$(date +%Y%m%d).db

# 2. Stop service (if running as systemd service)
sudo systemctl stop gilberts-yoga-helper

# 3. Pull latest code
git pull

# 4. Activate virtual environment and update dependencies
source .venv/bin/activate
pip install -r requirements.txt

# 5. Run database migrations
python -m alembic upgrade head

# 6. Restart service
sudo systemctl start gilberts-yoga-helper
```

### Windows / Development

```powershell
cd gilberts-yoga-helper

# 1. Pull latest code
git pull

# 2. Activate virtual environment
.venv\Scripts\Activate.ps1

# 3. Update dependencies
pip install -r requirements.txt

# 4. Run database migrations
python -m alembic upgrade head

# 5. Restart application
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Troubleshooting Upgrades

**Git pull fails (poetry.lock conflict):**
```bash
git checkout -- poetry.lock
git pull
pip install -r requirements.txt
```

**Migration fails:**
```bash
# Check current migration status
python -m alembic current

# View pending migrations
python -m alembic history

# Force upgrade to latest
python -m alembic upgrade head
```

**Rollback to previous version:**
```bash
# Restore database backup
cp data/yoga_helper_backup_YYYYMMDD.db data/yoga_helper.db

# Checkout previous version
git log --oneline -5  # find previous commit
git checkout <commit-hash>
pip install -r requirements.txt
```

## Production Deployment

For deploying to a Raspberry Pi with systemd, cron jobs, and backups, see [DEPLOYMENT.md](DEPLOYMENT.md).
