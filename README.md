# Gebrauchtwaffen Aggregator Schweiz

Personal web aggregator for Swiss used firearms marketplaces. Runs on Raspberry Pi.

## Technology Stack

- Python 3.11+
- FastAPI + Uvicorn
- Jinja2 Templates + HTMX
- TailwindCSS + Flowbite
- SQLAlchemy + SQLite
- Poetry for dependency management

## Setup

```bash
# Install dependencies
poetry install

# Run development server
poetry run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

## Project Structure

```
gebrauchtwaffen_aggregator/
├── backend/           # FastAPI application
│   ├── database/      # SQLAlchemy models and CRUD
│   ├── scrapers/      # Web scrapers per source
│   ├── services/      # Business logic
│   ├── routes/        # API endpoints
│   └── utils/         # Utilities and logging
├── frontend/
│   ├── templates/     # Jinja2 templates
│   └── public/        # Static files (CSS, JS)
├── tests/             # Pytest tests
├── data/              # SQLite database (gitignored)
└── logs/              # Application logs (gitignored)
```
