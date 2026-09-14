"""Shared pytest fixtures.

Each test runs inside a transaction that is rolled back afterwards, so tests
share one schema build and never see each other's data. That is dramatically
faster than recreating the schema per test, and it keeps tests order-independent.
"""

from __future__ import annotations

import os

# Force the test profile before any application module (and therefore the
# settings singleton) is imported. Environment variables win over the .env
# file in pydantic-settings, so this overrides APP_ENV=development from .env.
# It disables the rate limiter (otherwise its in-memory bucket bleeds across
# tests and later logins 429) and keeps the production guard dormant.
os.environ.setdefault("APP_ENV", "test")

from collections.abc import Generator

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.base import Base

# Import for the side effect of registering every model on Base.metadata.
import app.models  # noqa: F401  isort:skip

REQUIRED_EXTENSIONS = ("pg_trgm", "citext", "unaccent", "btree_gin")


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    """Build the schema once for the whole session against the test database."""
    eng = create_engine(settings.TEST_DATABASE_URL, poolclass=None)

    with eng.begin() as conn:
        # A clean slate, so a stale column from an earlier run cannot mask a bug.
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        for ext in REQUIRED_EXTENSIONS:
            conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Generator[Session, None, None]:
    """A session bound to a transaction that is always rolled back.

    The nested SAVEPOINT means application code may call ``commit()`` normally;
    only the outer transaction matters, and it never lands.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, expire_on_commit=False)()
    session.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def raw(engine: Engine) -> Generator[object, None, None]:
    """A raw connection in a rolled-back transaction, for DDL/constraint tests."""
    connection = engine.connect()
    transaction = connection.begin()
    try:
        yield connection
    finally:
        transaction.rollback()
        connection.close()
