"""Auth flows through the *real* get_db teardown.

Every other test overrides get_db with ``lambda: db`` inside a rolled-back
transaction, which commits nothing and rolls back nothing. That override cannot
see the class of bug where a security control is written and then an exception
unwinds through get_db, whose ``except`` rolls the write back before the request
finishes. These tests rebind SessionLocal to the test engine and let the genuine
get_db generator commit and roll back, so failed-login lockout and refresh-token
reuse detection are exercised for real.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

import app.db.session as db_session
from app.core.config import settings
from app.core.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models.identity import RefreshToken, User

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"


@pytest.fixture
def real_client(engine) -> Generator[TestClient, None, None]:
    """A client whose requests run through the real get_db against the test DB."""
    original = db_session.SessionLocal
    db_session.SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    # Make sure no leftover override shadows the real dependency.
    app.dependency_overrides.pop(get_db, None)
    try:
        with TestClient(app) as c:
            yield c
    finally:
        db_session.SessionLocal = original


@pytest.fixture
def fresh_session(engine):
    """A short-lived session for asserting what actually landed in the DB."""
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    sess = maker()
    try:
        yield sess
    finally:
        sess.close()


def _make_user(fresh_session, email: str, password: str) -> User:
    user = User(
        email=email,
        full_name="Rollback Tester",
        password_hash=hash_password(password),
        email_verified_at=datetime.now(UTC),
    )
    fresh_session.add(user)
    fresh_session.commit()
    fresh_session.refresh(user)
    return user


def _cleanup(fresh_session, user_id) -> None:
    fresh_session.execute(
        text("DELETE FROM refresh_token WHERE user_id = :u"), {"u": user_id}
    )
    fresh_session.execute(text('DELETE FROM "user" WHERE id = :u'), {"u": user_id})
    fresh_session.commit()


class TestLockoutSurvivesTeardown:
    def test_failed_logins_persist_the_lockout(self, real_client, fresh_session) -> None:
        user = _make_user(fresh_session, "lockout@rollback.pk", "correct-horse-9")
        try:
            for _ in range(settings.MAX_FAILED_LOGINS):
                r = real_client.post(
                    LOGIN, json={"email": user.email, "password": "wrong-password"}
                )
                assert r.status_code == 401

            fresh_session.expire_all()
            reloaded = fresh_session.get(User, user.id)
            # Before the fix this is None and the counter is 0: the increment and
            # the lockout were rolled back by get_db on every failed attempt.
            assert reloaded.locked_until is not None
        finally:
            _cleanup(fresh_session, user.id)

    def test_correct_password_after_lockout_is_refused(
        self, real_client, fresh_session
    ) -> None:
        user = _make_user(fresh_session, "lockout2@rollback.pk", "correct-horse-9")
        try:
            for _ in range(settings.MAX_FAILED_LOGINS):
                real_client.post(
                    LOGIN, json={"email": user.email, "password": "nope"}
                )
            # Even the right password is now refused: the account is locked and
            # no token pair comes back.
            r = real_client.post(
                LOGIN, json={"email": user.email, "password": "correct-horse-9"}
            )
            assert r.status_code == 401
            assert "tokens" not in r.json()
        finally:
            _cleanup(fresh_session, user.id)


class TestRefreshReuseSurvivesTeardown:
    def test_replaying_a_rotated_token_kills_the_family(
        self, real_client, fresh_session
    ) -> None:
        user = _make_user(fresh_session, "reuse@rollback.pk", "correct-horse-9")
        try:
            real_client.post(
                LOGIN, json={"email": user.email, "password": "correct-horse-9"}
            )
            r1 = real_client.cookies.get("wc_rt")

            rotated = real_client.post(REFRESH)
            assert rotated.status_code == 200
            r2 = real_client.cookies.get("wc_rt")

            # Replay the already-rotated R1. This must revoke the whole family.
            real_client.cookies.set("wc_rt", r1, path="/api/v1/auth")
            replay = real_client.post(REFRESH)
            assert replay.status_code == 401

            # R2 must now be dead too. Before the fix the revocation was rolled
            # back and R2 kept working.
            real_client.cookies.set("wc_rt", r2, path="/api/v1/auth")
            after = real_client.post(REFRESH)
            assert after.status_code == 401

            fresh_session.expire_all()
            live = fresh_session.scalars(
                select(RefreshToken).where(
                    RefreshToken.user_id == user.id,
                    RefreshToken.revoked_at.is_(None),
                )
            ).all()
            assert live == []
        finally:
            _cleanup(fresh_session, user.id)
