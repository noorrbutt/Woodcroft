"""Engine, session factory and the FastAPI request-scoped session dependency."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    # Recycle connections before a proxy or Postgres idle timeout can close them
    # out from under the pool, and fail fast rather than hanging 30s when the
    # pool is exhausted so the request returns a clean error under load.
    pool_recycle=1800,
    pool_timeout=10,
    # psycopg3 uses server-side prepared statements once a query repeats, which
    # breaks against a transaction-mode connection pooler (Neon's -pooler /
    # PgBouncer). Disabling them costs almost nothing here and makes the pooled
    # endpoint safe. Harmless on a direct connection too.
    connect_args={"prepare_threshold": None},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """Request-scoped session.

    Commits on clean exit so routers do not each have to remember to; rolls back
    and re-raises on any exception.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
