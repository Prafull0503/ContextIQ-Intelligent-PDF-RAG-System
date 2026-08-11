"""Database engine and session management.

Single ``engine`` for the process, built from ``DATABASE_URL``. Works with
either PostgreSQL (production) or SQLite (local/dev fallback) based on the
configured URL scheme.
"""

from __future__ import annotations

import logging
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")

# SQLite needs this because a single connection is otherwise pinned to the
# thread that created it, which breaks under FastAPI's threadpool.
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

# Pooling only makes sense for a real server (Postgres); SQLite ignores these.
_pool_kwargs = (
    {}
    if _is_sqlite
    else {
        "pool_pre_ping": True,  # discard dead connections before use (fixes
                                  # "server closed the connection unexpectedly")
        "pool_size": 5,
        "max_overflow": 10,
    }
)

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    echo=settings.log_level == "DEBUG",
    **_pool_kwargs,
)


def init_db() -> None:
    """Create all tables that don't already exist.

    Call once at application startup (e.g. from the lifespan handler in
    ``application.py``). Safe to call repeatedly — existing tables are left
    untouched.
    """
    SQLModel.metadata.create_all(engine)
    logger.info("Database tables verified/created.")


def get_db() -> Generator[Session, None, None]:
    """Yield a database session (FastAPI dependency).

    Commits are the caller's responsibility (routes call ``db.commit()``
    explicitly). On an unhandled exception the session is rolled back so a
    failed request never leaves a half-written transaction behind.
    """
    session = Session(engine)
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()