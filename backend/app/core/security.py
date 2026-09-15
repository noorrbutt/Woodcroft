"""Password hashing, JWT issue/verify, and opaque token generation.

Password hashing uses argon2id directly via argon2-cffi rather than through
passlib: passlib is unmaintained and its bcrypt backend detection is broken on
recent releases, while argon2-cffi is the algorithm we actually want anyway.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

# Tuned for an interactive login on modest hardware: ~50-100ms per verify.
_hasher = PasswordHasher(time_cost=2, memory_cost=64 * 1024, parallelism=2)

TokenType = Literal["access", "refresh"]


# ── Passwords ────────────────────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        _hasher.verify(hashed, plain)
        return True
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def password_needs_rehash(hashed: str) -> bool:
    """True when the stored hash uses outdated parameters."""
    try:
        return _hasher.check_needs_rehash(hashed)
    except (InvalidHashError, ValueError):
        return True


# ── JWT ──────────────────────────────────────────────────────────────────────
def create_access_token(
    subject: str | uuid.UUID,
    *,
    role: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": secrets.token_urlsafe(16),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(
    subject: str | uuid.UUID,
    *,
    session_id: str | uuid.UUID,
    remember_me: bool = False,
) -> tuple[str, datetime]:
    """Return ``(token, expires_at)``.

    The refresh token carries the session id so a rotation can invalidate the
    whole family on reuse detection.
    """
    now = datetime.now(UTC)
    days = (
        settings.REFRESH_TOKEN_REMEMBER_ME_DAYS
        if remember_me
        else settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    expires_at = now + timedelta(days=days)
    payload = {
        "sub": str(subject),
        "sid": str(session_id),
        "type": "refresh",
        "iat": now,
        "exp": expires_at,
        "jti": secrets.token_urlsafe(16),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expires_at


def decode_token(token: str, *, expected_type: TokenType | None = None) -> dict[str, Any]:
    """Decode and validate a JWT.

    Raises ``jwt.PyJWTError`` subclasses on any failure; callers translate that
    into the appropriate AppError.
    """
    payload: dict[str, Any] = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    if expected_type is not None and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(
            f"Expected a {expected_type} token, got {payload.get('type')!r}"
        )
    return payload


# ── Opaque tokens (email verification, password reset, guest sessions) ───────
def generate_token(nbytes: int = 32) -> str:
    """A URL-safe random token to hand to the user."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """SHA-256 of an opaque token.

    Verification and reset tokens are stored hashed so a database leak cannot be
    replayed. These are high-entropy random values, not passwords, so a fast
    hash is correct here - argon2 would add latency for no security gain.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
