"""NanoScribe – FastAPI application factory."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request, Response
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
            # Check if a static file matches the path (e.g. favicon.png)
            candidate = STATIC_DIR / path
            if path and candidate.is_file():
                return FileResponse(candidate)

            # Otherwise serve the SPA fallback for client-side routing
            return FileResponse(STATIC_DIR / "200.html")

    else:
        # Placeholder HTML when no SPA is built yet (dev mode)
        @app.get("/")
        async def serve_placeholder() -> HTMLResponse:
            """Serve a placeholder page when the SPA is not built."""
            html = "<!DOCTYPE html><html><head><title>NanoScribe</title></head>"
            html += "<body><h1>NanoScribe</h1><p>Frontend not built. Running in dev mode.</p></body></html>"
            return HTMLResponse(content=html)

    return app


app = create_app()
