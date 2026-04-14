"""NanoScribe – FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, HTMLResponse

from app.api.jobs import router as jobs_router
from app.api.library import router as library_router
from app.api.memos import router as memos_router
from app.api.search import router as search_router
from app.api.system import router as system_router
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
DATA_DIR = _settings.data_dir
STATIC_DIR = _settings.static_dir


def _resolve_path(base: str, path: str) -> str | None:
    """Resolve *path* relative to *base* and return it only if contained within *base*.

    Prevents path-traversal attacks (e.g. ``/../../../etc/passwd``).
    Returns the resolved absolute path string on success, or ``None`` if the
    candidate escapes *base*.
    """
    # pathlib handles platform-specific separators; resolve() collapses ".."
    from pathlib import Path

    resolved = (Path(base) / path).resolve()
    base_resolved = Path(base).resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        return None
    return str(resolved)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="NanoScribe", version="0.1.0")

    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "memos").mkdir(parents=True, exist_ok=True)

    # Register API routes under /api prefix
    app.include_router(system_router, prefix="/api/system")
    app.include_router(library_router, prefix="/api")
    app.include_router(memos_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(search_router, prefix="/api")

    # Startup: recover stale jobs and start worker
    @app.on_event("startup")
    async def _on_startup() -> None:
        from app.services import jobs as job_service
        from app.services.worker import start_worker

        db_path = DATA_DIR / "nanoscribe.db"
        recovered = job_service.recover_stale_jobs(db_path)
        if recovered > 0:
            logger.info("Recovered %d stale jobs on startup", recovered)

        await start_worker(db_path)

    # Serve built SPA static files in production
    # SvelteKit adapter-static produces: 200.html (fallback), _app/ (immutable assets), favicon.png
    if STATIC_DIR.is_dir() and (STATIC_DIR / "200.html").exists():
        # Mount immutable assets at /_app — these have content-hashed filenames
        app.mount("/_app", StaticFiles(directory=STATIC_DIR / "_app"), name="spa-assets")

        # Serve static files from the build output (favicon, etc.)
        app.mount("/static-assets", StaticFiles(directory=STATIC_DIR), name="static-root")

        # SPA fallback: serve 200.html for root and all non-/api routes
        @app.get("/", response_model=None)
        @app.get("/{path:path}", response_model=None)
        async def serve_spa(request: Request, path: str = "") -> Response:
            """Serve the SPA. API routes are handled before this catch-all."""
            # Check if a static file matches the path — but guard against traversal
            if path:
                resolved = _resolve_path(str(STATIC_DIR), path)
                if resolved is not None:
                    from pathlib import Path as _P

                    if _P(resolved).is_file():
                        return FileResponse(resolved)

            # Otherwise serve the SPA fallback for client-side routing
            return FileResponse(STATIC_DIR / "200.html")

    else:
        # Placeholder HTML when no SPA is built yet (dev mode)
        @app.get("/")
        @app.get("/{path:path}", response_model=None)
        async def serve_placeholder(path: str = "") -> HTMLResponse:
            """Serve a placeholder page when the SPA is not built."""
            html = "<!DOCTYPE html><html><head><title>NanoScribe</title></head>"
            html += "<body><h1>NanoScribe</h1><p>Frontend not built. Running in dev mode.</p></body></html>"
            return HTMLResponse(content=html)

    return app


app = create_app()
