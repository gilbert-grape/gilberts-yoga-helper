# Gebrauchtwaffen Aggregator Schweiz

Personal web aggregator for Swiss used firearms marketplaces. Monitors multiple sources and notifies you of new listings matching your search terms.

## Features

- Aggregates listings from multiple Swiss firearms marketplaces
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

- Python 3.11 or 3.12
- Poetry (`pip install poetry` or `curl -sSL https://install.python-poetry.org | python3 -`)

### Installation

```bash
# Clone the repository
git clone https://github.com/gilbert-grape/gilberts-gun-crawler.git
cd gilberts-gun-crawler

# Install dependencies
poetry install

# Create required directories
mkdir -p data logs
```

### Initialize Database

```bash
# Run database migrations
poetry run alembic upgrade head
```

### Start the Application

```bash
# Development mode (with auto-reload)
poetry run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
poetry run uvicorn backend.main:app --host 0.0.0.0 --port 8000
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
poetry run python -m backend.cli crawl

# Show help
poetry run python -m backend.cli --help
```

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=backend

# Run specific test file
poetry run pytest tests/test_scrapers.py
```

## Project Structure

```
gebrauchtwaffen_aggregator/
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
| `DATABASE_URL` | sqlite:///data/gebrauchtwaffen.db | Database connection |

## Production Deployment

For deploying to a Raspberry Pi with systemd, cron jobs, and backups, see [DEPLOYMENT.md](DEPLOYMENT.md).
