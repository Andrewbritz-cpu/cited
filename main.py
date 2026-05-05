"""
Cited — main entry point.

Serves the landing page and routes API requests to the appropriate handlers.
Run locally: python main.py
Deployed (Replit Autoscale): uvicorn main:app --host 0.0.0.0 --port $PORT
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.routes import scan, payment, webhook, upgrade, pages
from app.db import init_db
from app.templating import templates

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the database before the app starts taking requests."""
    await init_db()
    yield
    # No teardown work required — SQLite handles connection cleanup itself.


app = FastAPI(
    title="Cited",
    description="ATS scoring for South African job seekers",
    version="0.1.0",
    lifespan=lifespan,
)

# Static assets (CSS, JS, images)
app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static",
)

# API routers — order doesn't matter, FastAPI handles routing.
app.include_router(scan.router, prefix="/api/scan", tags=["scan"])
app.include_router(payment.router, prefix="/api/payment", tags=["payment"])
app.include_router(webhook.router, prefix="/api/webhook", tags=["webhook"])

# Page routers (HTML responses, not JSON APIs)
app.include_router(upgrade.router, tags=["upgrade"])
app.include_router(pages.router, tags=["pages"])


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the landing page."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
    )


@app.get("/healthz")
async def health():
    """Simple health check for uptime monitoring."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )
