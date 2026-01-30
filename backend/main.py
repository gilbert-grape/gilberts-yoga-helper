"""
Gebrauchtwaffen Aggregator - Main FastAPI Application

Database Migrations:
    This application uses Alembic for database migrations.
    Before starting the application, ensure migrations are applied:

        # Apply all pending migrations
        alembic upgrade head

        # Or check current migration status
        alembic current

    The application verifies database connectivity on startup but does NOT
    auto-run migrations to prevent accidental schema changes in production.

Logging:
    Logging is automatically configured on backend package import.
    Logs are written to logs/app.log with rotation (5MB max, 3 backups).
    Console logging is enabled in DEBUG mode.

    Configuration via environment variables:
        - LOG_LEVEL: DEBUG, INFO, WARNING, ERROR (default: INFO)
        - LOG_FILE: Log file path (default: logs/app.log)
        - LOG_MAX_SIZE: Max file size before rotation (default: 5MB)
        - LOG_BACKUP_COUNT: Number of backup files (default: 3)
"""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

# Import from backend package ensures logging is initialized (via backend/__init__.py)
from backend.database import (
    engine,
    get_db,
    get_all_matches,
    get_all_search_terms,
    get_all_search_terms_sorted,
    get_active_search_terms,
    get_search_term_by_id,
    get_search_term_by_term,
    create_search_term,
    delete_search_term,
    update_search_term_match_type,
    toggle_search_term_hide_seen,
    move_search_term_up,
    move_search_term_down,
    get_all_sources_sorted,
    get_source_by_id,
    toggle_source_active,
    clear_source_error,
    move_source_up,
    move_source_down,
    get_matches_by_search_term,
    get_new_match_count,
    mark_matches_as_seen,
    get_all_exclude_terms_sorted,
    get_active_exclude_terms,
    get_exclude_term_by_id,
    get_exclude_term_by_term,
    create_exclude_term,
    delete_exclude_term,
    toggle_exclude_term_active,
    DATABASE_PATH,
)
from backend.services.crawler import (
    run_crawl_async,
    is_crawl_running,
    get_crawl_state,
    get_last_crawl_result,
    get_crawl_log,
    request_crawl_cancel,
    prepare_crawl_state,
    ensure_sources_exist,
)
from backend.utils.logging import get_logger

logger = get_logger(__name__)

# Get project root directory (one level up from backend/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def verify_database() -> None:
    """
    Verify database connectivity and migration status on startup.

    This function checks that:
    1. The database file exists (or can be created)
    2. The database is accessible
    3. Expected tables exist (warns if not)

    Note: This does NOT run migrations automatically. Use 'alembic upgrade head'
    to apply migrations before starting the application.
    """
    # Check if database file exists
    if not DATABASE_PATH.exists():
        logger.error(
            f"Database file not found at {DATABASE_PATH}. "
            "Run 'alembic upgrade head' to create the database. "
            "Application may not function correctly without a database."
        )
        return

    # Verify database connectivity and check for expected tables
    try:
        with engine.connect() as conn:
            # Check for alembic_version table (indicates migrations have been run)
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
            )
            if result.fetchone() is None:
                logger.warning(
                    "Alembic version table not found. "
                    "Run 'alembic upgrade head' to apply migrations."
                )
                return

            # Check for expected application tables
            expected_tables = ['search_terms', 'sources', 'matches']
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
            existing_tables = {row[0] for row in result.fetchall()}

            missing_tables = set(expected_tables) - existing_tables
            if missing_tables:
                logger.warning(
                    f"Missing tables: {missing_tables}. "
                    "Run 'alembic upgrade head' to apply pending migrations."
                )
            else:
                logger.info("Database verification successful. All expected tables exist.")

    except Exception as e:
        logger.error(f"Database verification failed: {e}")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler for startup and shutdown events.

    Startup:
        - Verifies database connectivity and migration status
        - Creates all registered sources if they don't exist
        - Does NOT auto-run migrations (use 'alembic upgrade head' manually)

    Shutdown:
        - Currently no cleanup required
    """
    # Startup: Verify database (but don't auto-migrate)
    verify_database()

    # Create all registered sources and default terms at startup
    from backend.database import (
        SessionLocal,
        ensure_default_search_terms,
        ensure_default_exclude_terms,
    )
    db = SessionLocal()
    try:
        ensure_sources_exist(db)
        logger.info("All registered sources initialized")
        ensure_default_search_terms(db)
        logger.info("Default search terms initialized")
        ensure_default_exclude_terms(db)
        logger.info("Default exclude terms initialized")
    except Exception as e:
        logger.error(f"Failed to initialize startup data: {e}")
    finally:
        db.close()

    yield
    # Shutdown: cleanup if needed (none currently)


app = FastAPI(
    title="Gebrauchtwaffen Aggregator",
    description="Swiss used firearms marketplace aggregator",
    version="0.1.0",
    lifespan=lifespan,
)

# Ensure static files directory exists
STATIC_DIR = FRONTEND_DIR / "public"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files with absolute path
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Templates with absolute path
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))


@app.get("/")
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    filter: Optional[bool] = None,
):
    """
    Dashboard home page showing all matches grouped by search term.

    Displays:
    - Matches grouped by search term with collapsible sections
    - Count of new (unseen) matches per group and total
    - Empty state for search terms with no matches
    - Duplicate filtering based on hide_seen_matches setting
    - Exclude term filtering (matches containing exclude terms are hidden)

    Args:
        filter: If True, hide matches containing exclude terms.
                If False, show all matches including those with exclude terms.
                If None, read from cookie (default: True).

    After displaying, marks all matches as seen so they won't
    appear as "new" on the next visit.
    """
    # Determine filter state: URL param > cookie > default (True)
    if filter is None:
        filter_cookie = request.cookies.get("filter_mode", "true")
        filter = filter_cookie.lower() != "false"

    # Get all search terms (including those with no matches), sorted by sort_order
    search_terms = get_all_search_terms(db)

    # Get active exclude terms for filtering
    exclude_terms = get_active_exclude_terms(db)
    exclude_patterns = [et.term.lower() for et in exclude_terms]

    def matches_exclude_term(title: str) -> bool:
        """Check if a title contains any exclude term (case-insensitive)."""
        title_lower = title.lower()
        return any(pattern in title_lower for pattern in exclude_patterns)

    # Build groups with matches, filtering duplicates and optionally exclude terms
    groups = []
    total_count = 0
    total_new_count = 0
    seen_urls = set()  # Track URLs already shown by earlier search terms

    for term in search_terms:
        all_matches = get_matches_by_search_term(db, term.id)

        # Filter out matches containing exclude terms (only if filter is enabled)
        if filter:
            filtered_matches = [m for m in all_matches if not matches_exclude_term(m.title)]
        else:
            filtered_matches = list(all_matches)

        # Filter out duplicates if hide_seen_matches is enabled
        if term.hide_seen_matches:
            matches = [m for m in filtered_matches if m.url not in seen_urls]
        else:
            matches = filtered_matches

        # Add all match URLs from this term to the seen set (for filtering later terms)
        for m in filtered_matches:
            seen_urls.add(m.url)

        new_count = sum(1 for m in matches if m.is_new)
        groups.append({
            "term": term,
            "matches": matches,
            "total_count": len(matches),
            "new_count": new_count,
        })
        total_count += len(matches)
        total_new_count += new_count

    # Build response first (so matches still show as "new" in this render)
    response = templates.TemplateResponse("dashboard.html", {"request": request, 
            "title": "Dashboard",
            "groups": groups,
            "total_count": total_count,
            "new_count": total_new_count,
            "filter_enabled": filter,
        },
    )

    # Mark matches as seen after building response
    # This ensures the current view shows NEW badges, but next view won't
    mark_matches_as_seen(db)

    return response


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/admin/search-terms")
async def admin_search_terms(request: Request, db: Session = Depends(get_db)):
    """
    Admin page for managing search terms.

    Displays all search terms sorted by sort_order with options to:
    - Add new search terms
    - Delete existing search terms
    - Toggle match type (exact/similar)
    - Reorder search terms (move up/down)
    """
    search_terms = get_all_search_terms(db)
    return templates.TemplateResponse("admin/search_terms.html", {"request": request, 
            "title": "Suchbegriffe",
            "search_terms": search_terms,
        }
    )


@app.post("/admin/search-terms")
async def add_search_term(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Add a new search term via HTMX form submission.

    Returns the updated search terms list partial for HTMX swap.
    """
    form = await request.form()
    term_text = form.get("term", "").strip()
    match_type = form.get("match_type", "exact")

    error = None

    # Validation
    if not term_text:
        error = "Suchbegriff darf nicht leer sein."
    elif get_search_term_by_term(db, term_text):
        error = f"Suchbegriff '{term_text}' existiert bereits."
    elif match_type not in ("exact", "similar"):
        error = "Ungültiger Matching-Typ."

    if error:
        search_terms = get_all_search_terms(db)
        return templates.TemplateResponse("admin/_partials/_search_terms_list.html", {"request": request, 
                "search_terms": search_terms,
                "error": error,
            }
        )

    # Create the new search term
    create_search_term(db, term_text, match_type)
    search_terms = get_all_search_terms(db)

    return templates.TemplateResponse("admin/_partials/_search_terms_list.html", {"request": request, 
            "search_terms": search_terms,
            "success": f"Suchbegriff '{term_text}' hinzugefügt.",
        }
    )


@app.delete("/admin/search-terms/{term_id}")
async def remove_search_term(
    request: Request,
    term_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a search term via HTMX request.

    Returns the updated search terms list partial for HTMX swap.
    """
    term = get_search_term_by_id(db, term_id)
    term_text = term.term if term else "Unbekannt"

    success = delete_search_term(db, term_id)
    search_terms = get_all_search_terms(db)

    message = None
    if success:
        message = f"Suchbegriff '{term_text}' gelöscht."

    return templates.TemplateResponse("admin/_partials/_search_terms_list.html", {"request": request, 
            "search_terms": search_terms,
            "success": message,
        }
    )


@app.patch("/admin/search-terms/{term_id}/match-type")
async def toggle_match_type(
    request: Request,
    term_id: int,
    db: Session = Depends(get_db)
):
    """
    Toggle a search term's match type between exact and similar.

    Returns the updated search term row partial for HTMX swap.
    """
    term = get_search_term_by_id(db, term_id)
    if not term:
        return templates.TemplateResponse("admin/_partials/_search_term_row.html", {"request": request, "term": None, "error": "Suchbegriff nicht gefunden."}
        )

    # Toggle the match type
    new_type = "similar" if term.match_type == "exact" else "exact"
    updated_term = update_search_term_match_type(db, term_id, new_type)

    return templates.TemplateResponse("admin/_partials/_search_term_row.html", {"request": request, "term": updated_term}
    )


@app.patch("/admin/search-terms/{term_id}/hide-seen")
async def toggle_hide_seen(
    request: Request,
    term_id: int,
    db: Session = Depends(get_db)
):
    """
    Toggle a search term's hide_seen_matches setting.

    Returns the updated search term row partial for HTMX swap.
    """
    updated_term = toggle_search_term_hide_seen(db, term_id)
    if not updated_term:
        return templates.TemplateResponse("admin/_partials/_search_term_row.html", {"request": request, "term": None, "error": "Suchbegriff nicht gefunden."}
        )

    return templates.TemplateResponse("admin/_partials/_search_term_row.html", {"request": request, "term": updated_term}
    )


@app.post("/admin/search-terms/{term_id}/move-up")
async def move_term_up(
    request: Request,
    term_id: int,
    db: Session = Depends(get_db)
):
    """
    Move a search term up in sort order.

    Returns the updated search terms list partial for HTMX swap.
    """
    move_search_term_up(db, term_id)
    search_terms = get_all_search_terms(db)

    return templates.TemplateResponse("admin/_partials/_search_terms_list.html", {"request": request, "search_terms": search_terms}
    )


@app.post("/admin/search-terms/{term_id}/move-down")
async def move_term_down(
    request: Request,
    term_id: int,
    db: Session = Depends(get_db)
):
    """
    Move a search term down in sort order.

    Returns the updated search terms list partial for HTMX swap.
    """
    move_search_term_down(db, term_id)
    search_terms = get_all_search_terms(db)

    return templates.TemplateResponse("admin/_partials/_search_terms_list.html", {"request": request, "search_terms": search_terms}
    )


# =============================================================================
# Exclude Terms Admin Routes
# =============================================================================


@app.get("/admin/exclude-terms")
async def admin_exclude_terms(request: Request, db: Session = Depends(get_db)):
    """
    Admin page for managing exclude terms (negative keywords).

    Displays all exclude terms sorted alphabetically with options to:
    - Add new exclude terms
    - Delete existing exclude terms
    - Toggle active state
    """
    exclude_terms = get_all_exclude_terms_sorted(db)
    return templates.TemplateResponse("admin/exclude_terms.html", {"request": request, 
            "title": "Ausschlüsse",
            "exclude_terms": exclude_terms,
        }
    )


@app.post("/admin/exclude-terms")
async def add_exclude_term(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Add a new exclude term via HTMX form submission.

    Returns the updated exclude terms list partial for HTMX swap.
    """
    form = await request.form()
    term_text = form.get("term", "").strip()

    error = None

    # Validation
    if not term_text:
        error = "Ausschlussbegriff darf nicht leer sein."
    elif get_exclude_term_by_term(db, term_text):
        error = f"Ausschlussbegriff '{term_text}' existiert bereits."

    if error:
        exclude_terms = get_all_exclude_terms_sorted(db)
        return templates.TemplateResponse("admin/_partials/_exclude_terms_list.html", {"request": request, 
                "exclude_terms": exclude_terms,
                "error": error,
            }
        )

    # Create the new exclude term
    create_exclude_term(db, term_text)
    exclude_terms = get_all_exclude_terms_sorted(db)

    return templates.TemplateResponse("admin/_partials/_exclude_terms_list.html", {"request": request, 
            "exclude_terms": exclude_terms,
            "success": f"Ausschlussbegriff '{term_text}' hinzugefügt.",
        }
    )


@app.delete("/admin/exclude-terms/{term_id}")
async def remove_exclude_term(
    request: Request,
    term_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete an exclude term via HTMX request.

    Returns the updated exclude terms list partial for HTMX swap.
    """
    term = get_exclude_term_by_id(db, term_id)
    term_text = term.term if term else "Unbekannt"

    success = delete_exclude_term(db, term_id)
    exclude_terms = get_all_exclude_terms_sorted(db)

    message = None
    if success:
        message = f"Ausschlussbegriff '{term_text}' gelöscht."

    return templates.TemplateResponse("admin/_partials/_exclude_terms_list.html", {"request": request, 
            "exclude_terms": exclude_terms,
            "success": message,
        }
    )


@app.patch("/admin/exclude-terms/{term_id}/toggle")
async def toggle_exclude_term(
    request: Request,
    term_id: int,
    db: Session = Depends(get_db)
):
    """
    Toggle an exclude term's active state via HTMX request.

    Returns the updated exclude term row partial for HTMX swap.
    """
    term = toggle_exclude_term_active(db, term_id)
    if not term:
        return templates.TemplateResponse("admin/_partials/_exclude_term_row.html", {"request": request, "term": None, "error": "Ausschlussbegriff nicht gefunden."}
        )

    return templates.TemplateResponse("admin/_partials/_exclude_term_row.html", {"request": request, "term": term}
    )


@app.get("/admin/sources")
async def admin_sources(request: Request, db: Session = Depends(get_db)):
    """
    Admin page for managing sources.

    Displays all sources sorted alphabetically with:
    - Active/inactive status toggle
    - Last crawl timestamp
    - Error status if any
    """
    sources = get_all_sources_sorted(db)
    return templates.TemplateResponse("admin/sources.html", {"request": request, 
            "title": "Quellen",
            "sources": sources,
        }
    )


@app.patch("/admin/sources/{source_id}/toggle")
async def toggle_source(
    request: Request,
    source_id: int,
    db: Session = Depends(get_db)
):
    """
    Toggle a source's active state via HTMX request.

    Returns the updated source row partial for HTMX swap.
    """
    source = toggle_source_active(db, source_id)
    if not source:
        return templates.TemplateResponse("admin/_partials/_source_row.html", {"request": request, "source": None, "error": "Quelle nicht gefunden."}
        )

    return templates.TemplateResponse("admin/_partials/_source_row.html", {"request": request, "source": source}
    )


@app.delete("/admin/sources/{source_id}/error")
async def clear_source_error_route(
    request: Request,
    source_id: int,
    db: Session = Depends(get_db)
):
    """
    Clear a source's error state via HTMX request.

    Returns the updated source row partial for HTMX swap.
    """
    source = clear_source_error(db, source_id)
    if not source:
        return templates.TemplateResponse("admin/_partials/_source_row.html", {"request": request, "source": None, "error": "Quelle nicht gefunden."}
        )

    return templates.TemplateResponse("admin/_partials/_source_row.html", {"request": request, "source": source}
    )


@app.patch("/admin/sources/{source_id}/move-up")
async def move_source_up_route(
    request: Request,
    source_id: int,
    db: Session = Depends(get_db)
):
    """
    Move a source up in the crawl order via HTMX request.

    Returns the updated sources list partial for HTMX swap.
    """
    sources = move_source_up(db, source_id)
    return templates.TemplateResponse("admin/_partials/_sources_list.html", {"request": request, "sources": sources}
    )


@app.patch("/admin/sources/{source_id}/move-down")
async def move_source_down_route(
    request: Request,
    source_id: int,
    db: Session = Depends(get_db)
):
    """
    Move a source down in the crawl order via HTMX request.

    Returns the updated sources list partial for HTMX swap.
    """
    sources = move_source_down(db, source_id)
    return templates.TemplateResponse("admin/_partials/_sources_list.html", {"request": request, "sources": sources}
    )


@app.get("/admin/crawl")
async def admin_crawl_status(request: Request):
    """
    Admin page for crawl control and status.

    Displays:
    - Current crawl status (running/idle)
    - Last crawl result (if any)
    - Manual crawl trigger button
    """
    crawl_state = get_crawl_state()
    return templates.TemplateResponse("admin/crawl_status.html", {"request": request, 
            "title": "Crawl-Status",
            "is_running": crawl_state.is_running,
            "current_source": crawl_state.current_source,
            "last_result": crawl_state.last_result,
            "log_messages": get_crawl_log(),
        }
    )


@app.post("/admin/crawl/start")
async def start_crawl(request: Request, db: Session = Depends(get_db)):
    """
    Start a manual crawl via HTMX request.

    Starts the crawl in the background and returns immediately so the UI
    can show the running state with cancel button.
    """
    import asyncio

    # Check if already running
    if is_crawl_running():
        crawl_state = get_crawl_state()
        return templates.TemplateResponse("admin/_partials/_crawl_status.html", {"request": request, 
                "is_running": True,
                "current_source": crawl_state.current_source,
                "last_result": crawl_state.last_result,
                "log_messages": get_crawl_log(),
                "error": "Ein Crawl läuft bereits.",
            }
        )

    # Check if there are active search terms
    active_terms = get_active_search_terms(db)
    if not active_terms:
        crawl_state = get_crawl_state()
        return templates.TemplateResponse("admin/_partials/_crawl_status.html", {"request": request, 
                "is_running": False,
                "current_source": None,
                "last_result": crawl_state.last_result,
                "log_messages": get_crawl_log(),
                "error": "Kein Crawl möglich: Bitte zuerst Suchbegriffe erfassen.",
            }
        )

    # Prepare crawl state BEFORE creating background task to avoid race conditions
    # This ensures polling sees is_running=True immediately
    prepare_crawl_state()

    # Start crawl in background task
    async def run_crawl_background():
        # Create a new database session for the background task
        from backend.database import SessionLocal
        background_db = SessionLocal()
        try:
            # Pass state_prepared=True since we already set up the state
            await run_crawl_async(background_db, state_prepared=True)
        except Exception as e:
            logger.error(f"Background crawl failed: {e}")
        finally:
            background_db.close()

    asyncio.create_task(run_crawl_background())

    # Return immediately with running state
    crawl_state = get_crawl_state()
    return templates.TemplateResponse("admin/_partials/_crawl_status.html", {"request": request, 
            "is_running": crawl_state.is_running,
            "current_source": crawl_state.current_source,
            "last_result": crawl_state.last_result,
            "log_messages": get_crawl_log(),
        }
    )


@app.get("/admin/crawl/status")
async def get_crawl_status_partial(request: Request):
    """
    Get current crawl status partial for HTMX polling.

    Used for real-time status updates during crawl.
    """
    crawl_state = get_crawl_state()
    return templates.TemplateResponse("admin/_partials/_crawl_status.html", {"request": request, 
            "is_running": crawl_state.is_running,
            "current_source": crawl_state.current_source,
            "last_result": crawl_state.last_result,
            "log_messages": get_crawl_log(),
        }
    )


@app.post("/admin/crawl/cancel")
async def cancel_crawl(request: Request):
    """
    Cancel a running crawl via HTMX request.

    Returns the updated status partial for HTMX swap.
    """
    if not is_crawl_running():
        crawl_state = get_crawl_state()
        return templates.TemplateResponse("admin/_partials/_crawl_status.html", {"request": request, 
                "is_running": False,
                "current_source": None,
                "last_result": crawl_state.last_result,
                "error": "Kein Crawl läuft.",
            }
        )

    # Request cancellation
    request_crawl_cancel()

    crawl_state = get_crawl_state()
    return templates.TemplateResponse("admin/_partials/_crawl_status.html", {"request": request, 
            "is_running": crawl_state.is_running,
            "current_source": crawl_state.current_source,
            "last_result": crawl_state.last_result,
            "success": "Abbruch angefordert...",
        }
    )
