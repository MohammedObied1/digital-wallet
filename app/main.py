from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.router import api_router
from app.api.v1 import health
from app.core.config import settings
from app.core.database import init_db
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import register_middleware

DESCRIPTION = """
**Digital Wallet API** is a production-style financial transaction backend.

## Features (built incrementally — see ARCHITECTURE.md for the roadmap)
* Double-entry ledger with rebuildable, verifiable balances
* PostgreSQL row-level locking for safe concurrent transfers
* Idempotent money-moving endpoints
* Configurable transfer limits and a fraud/risk rules engine
* Immutable audit log of every sensitive action
* Transactional outbox for asynchronous notifications
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_middleware(app)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    # In the Docker image the frontend is pre-built into frontend/dist; mounting it here
    # lets a single container serve both the API and the UI (same pattern as TaskFlow API).
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


app = create_app()
