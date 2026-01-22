"""
Gebrauchtwaffen Aggregator - Main FastAPI Application
"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(
    title="Gebrauchtwaffen Aggregator",
    description="Swiss used firearms marketplace aggregator",
    version="0.1.0"
)

# Mount static files
app.mount("/static", StaticFiles(directory="frontend/public"), name="static")

# Templates
templates = Jinja2Templates(directory="frontend/templates")


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
