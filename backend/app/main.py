"""NanoScribe – FastAPI application factory."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, HTMLResponse

from app.api.system import router as system_router

DATA_DIR = Path(os.environ.get("NANOSCRIBE_DATA_DIR", "/app/data"))
STATIC_DIR = Path(os.environ.get("NANOSCRIBE_STATIC_DIR", "/app/static"))


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="NanoScribe", version="0.1.0")

    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "memos").mkdir(parents=True, exist_ok=True)

    # Register API routes under /api prefix
    app.include_router(system_router, prefix="/api/system")

    # Serve built SPA static files in production
    if STATIC_DIR.is_dir() and any(STATIC_DIR.iterdir()):
        # Mount static assets (JS, CSS, etc.)
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

        # Serve index.html for the SPA catch-all (root and non-/api routes)
        @app.get("/")
        async def serve_index() -> FileResponse:
            """Serve the SPA index page."""
            return FileResponse(STATIC_DIR / "index.html")

    else:
        # Placeholder HTML when no SPA is built yet
        @app.get("/")
        async def serve_placeholder() -> HTMLResponse:
            """Serve a placeholder page when the SPA is not built."""
            html = "<!DOCTYPE html><html><head><title>NanoScribe</title></head>"
            html += "<body><h1>NanoScribe</h1><p>Frontend not built. Running in dev mode.</p></body></html>"
            return HTMLResponse(content=html)

    return app


app = create_app()
