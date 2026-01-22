"""
Gebrauchtwaffen Aggregator - Main FastAPI Application
"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Get project root directory (one level up from backend/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = FastAPI(
    title="Gebrauchtwaffen Aggregator",
    description="Swiss used firearms marketplace aggregator",
    version="0.1.0"
)

# Mount static files with absolute path
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "public")), name="static")

# Templates with absolute path
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))


@app.get("/")
async def index(request: Request):
    """Dashboard home page."""
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "title": "Dashboard"}
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
