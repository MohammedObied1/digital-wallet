import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.api.deps import DBSession

logger = logging.getLogger("wallet.health")

router = APIRouter(tags=["Health"])
versioned_router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/health", summary="Combined liveness & readiness probe (used by Docker HEALTHCHECK)")
def health(db: DBSession) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "version": __version__, "database": "connected"}


@versioned_router.get("", summary="Liveness probe — process is up, no dependency checks")
def liveness() -> dict:
    return {"status": "ok"}


@versioned_router.get("/ready", summary="Readiness probe — verifies PostgreSQL is reachable")
def readiness(db: DBSession):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("readiness check failed: database unreachable")
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "disconnected"})
    return {"status": "ready", "database": "connected"}
