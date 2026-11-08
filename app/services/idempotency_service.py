"""Generic idempotency support for money-moving endpoints.

Usage in a router:
    cached = idempotency_service.get_cached(db, key, endpoint, request_hash)
    if cached:
        return JSONResponse(status_code=cached.status_code, content=cached.response_body)
    ... do the operation ...
    idempotency_service.store(db, key, endpoint, request_hash, 201, response_dict)
"""

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import IdempotencyConflictError
from app.models import IdempotencyRecord


def hash_body(body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def get_cached(db: Session, user_id: int, key: str, endpoint: str, request_hash: str) -> IdempotencyRecord | None:
    record = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user_id, IdempotencyRecord.idempotency_key == key, IdempotencyRecord.endpoint == endpoint
        )
    )
    if record is None:
        return None
    if record.request_hash != request_hash:
        raise IdempotencyConflictError()
    return record


def store(db: Session, user_id: int, key: str, endpoint: str, request_hash: str, status_code: int, response_body: dict[str, Any]) -> None:
    db.add(
        IdempotencyRecord(
            user_id=user_id,
            idempotency_key=key,
            endpoint=endpoint,
            request_hash=request_hash,
            status_code=status_code,
            response_body=response_body,
        )
    )


def commit_atomically(db: Session) -> None:
    """Commit the ledger writes and the idempotency record together. If two identical requests
    race past `get_cached` at the same time, the table's UNIQUE(idempotency_key, endpoint)
    constraint lets only one of them commit; the loser gets a clean conflict instead of silently
    double-spending.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise IdempotencyConflictError("A concurrent request with the same idempotency key is already processing") from exc
