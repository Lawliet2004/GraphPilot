"""Durable non-secret log policy with a short per-process override cache."""

import threading
import time

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from api.config import settings
from api.db import SessionLocal
from api.models import RuntimeSetting


class LogPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_retention_days: int = Field(ge=1, le=3650, strict=True)
    max_log_downloads: int = Field(ge=0, le=30, strict=True)
    max_log_bytes: int = Field(ge=1000, le=10_000_000, strict=True)


_lock = threading.Lock()
_cached = None
_cached_at = 0


def defaults():
    cfg = settings()
    return {key: getattr(cfg, key) for key in LogPolicy.model_fields}


def clear_cache():
    global _cached
    with _lock:
        _cached = None


def read_policy(db):
    rows = db.scalars(select(RuntimeSetting).where(RuntimeSetting.key.in_(LogPolicy.model_fields)))
    return LogPolicy(**(defaults() | {row.key: row.value for row in rows})).model_dump()


def log_policy():
    global _cached, _cached_at
    with _lock:
        if _cached is None or time.monotonic() - _cached_at >= 5:
            with SessionLocal() as db:
                _cached = {
                    row.key: row.value
                    for row in db.scalars(
                        select(RuntimeSetting).where(RuntimeSetting.key.in_(LogPolicy.model_fields))
                    )
                }
            _cached_at = time.monotonic()
        # Defaults are read afresh; only durable overrides are cached.
        return LogPolicy(**(defaults() | _cached)).model_dump()
