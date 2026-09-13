"""Authentication: registration, login, token rotation, verification, reset.

Refresh token rotation
----------------------
Every refresh issues a new token and revokes the one used. If a token that was
already revoked comes back, that is a replay: either the user's token was
stolen and the thief is now using it, or the thief used it and the real user is.
We cannot tell which, so the whole session family is revoked and both parties
have to sign in again. That makes a stolen refresh token useful for one request
at most.
"""

from __future__ import annotations

import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import (
    AccountLockedError,
    AuthenticationError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    NotFoundError,
    ValidationError,
)
from app.core.permissions import Role
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from app.models.identity import (
    EmailVerification,
    GuestSession,
    NotificationPreference,
    PasswordReset,
    RefreshToken,
    User,
)
from app.models.promotion import LoyaltyAccount

REFERRAL_ALPHABET = string.ascii_uppercase + string.digits


def _now() -> datetime:
    return datetime.now(UTC)


def generate_referral_code(db: Session) -> str:
    """A short human-readable code. Retries on the very rare collision."""
    for _ in range(10):
        code = "WC" + "".join(secrets.choice(REFERRAL_ALPHABET) for _ in range(6))
        exists = db.scalar(select(User.id).where(User.referral_code == code))
        if not exists:
            return code
    raise RuntimeError("Could not allocate a unique referral code")


def normalise_phone(raw: str | None) -> str | None:
    """Reduce any Pakistani mobile format to the stored 03XXXXXXXXX form.

    Accepts +923001234567, 923001234567, 0300-1234567 and so on. The database
    CHECK only permits the normalised form, so this must run before any write.
    """
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("92"):
        digits = "0" + digits[2:]
    if len(digits) == 10 and digits.startswith("3"):
        digits = "0" + digits
    if len(digits) != 11 or not digits.startswith("03"):
        raise ValidationError(
            "Enter a valid Pakistani mobile number, for example 0300 1234567.",
            details={"fields": {"phone": "Invalid format"}},
        )
    return digits


# ── Registration ─────────────────────────────────────────────────────────────
def register_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    phone: str | None = None,
    referred_by_code: str | None = None,
) -> tuple[User, str]:
    """Create an account. Returns the user and the raw verification token."""
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise EmailAlreadyRegisteredError()

    referrer = None
    if referred_by_code:
        referrer = db.scalar(
            select(User).where(User.referral_code == referred_by_code.upper())
        )

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        phone=normalise_phone(phone),
        role=Role.CUSTOMER,
        referral_code=generate_referral_code(db),
        referred_by_id=referrer.id if referrer else None,
    )
    db.add(user)
    db.flush()

    # Every customer gets a loyalty account and default notification settings
    # up front, so nothing downstream has to handle their absence.
    db.add(LoyaltyAccount(user_id=user.id))
    db.add(NotificationPreference(user_id=user.id))

    raw_token = issue_email_verification(db, user)
    db.flush()
    return user, raw_token


def issue_email_verification(db: Session, user: User, new_email: str | None = None) -> str:
    """Create a verification token. The raw value is returned once, then gone."""
    raw = generate_token()
    db.add(
        EmailVerification(
            user_id=user.id,
            token_hash=hash_token(raw),
            new_email=new_email,
            expires_at=_now() + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS),
        )
    )
    return raw


def verify_email(db: Session, raw_token: str) -> User:
    record = db.scalar(
        select(EmailVerification).where(
            EmailVerification.token_hash == hash_token(raw_token)
        )
    )
    if record is None or record.consumed_at is not None:
        raise ValidationError("This verification link is invalid or already used.")
    if record.expires_at < _now():
        raise ValidationError("This verification link has expired.")

    user = db.get(User, record.user_id)
    if user is None:
        raise NotFoundError("Account not found.")

    if record.new_email:
        user.email = record.new_email
    user.email_verified_at = _now()
    record.consumed_at = _now()
    return user


# ── Login ────────────────────────────────────────────────────────────────────
def authenticate(db: Session, *, email: str, password: str) -> User:
    """Check credentials, applying lockout.

    A wrong email and a wrong password produce the same error on purpose, so the
    response cannot be used to discover which addresses have accounts.
    """
    user = db.scalar(select(User).where(User.email == email))

    if user is None:
        # Spend roughly the same time as a real verify would, so the timing does
        # not reveal whether the address exists.
        hash_password(password)
        raise InvalidCredentialsError()

    if user.is_locked:
        raise AccountLockedError(
            "Too many failed attempts. Try again in a few minutes."
        )
    if not user.is_active or user.deactivated_at is not None:
        raise AuthenticationError("This account has been deactivated.")
    if user.password_hash is None or not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.MAX_FAILED_LOGINS:
            user.locked_until = _now() + timedelta(
                minutes=settings.ACCOUNT_LOCKOUT_MINUTES
            )
            user.failed_login_count = 0
        raise InvalidCredentialsError()

    # Transparently upgrade the hash if the cost parameters have moved on.
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = _now()
    return user


def issue_tokens(
    db: Session,
    user: User,
    *,
    remember_me: bool = False,
    user_agent: str | None = None,
    ip_address: str | None = None,
    session_id: uuid.UUID | None = None,
) -> tuple[str, str]:
    """Mint an access and refresh token pair. Returns (access, refresh)."""
    session_id = session_id or uuid.uuid4()
    access = create_access_token(user.id, role=user.role.value)
    refresh, expires_at = create_refresh_token(
        user.id, session_id=session_id, remember_me=remember_me
    )

    db.add(
        RefreshToken(
            user_id=user.id,
            session_id=session_id,
            token_hash=hash_token(refresh),
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
            remember_me=remember_me,
        )
    )
    return access, refresh


def rotate_refresh_token(
    db: Session,
    raw_refresh: str,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[User, str, str]:
    """Exchange a refresh token for a new pair, with reuse detection."""
    import jwt

    try:
        payload = decode_token(raw_refresh, expected_type="refresh")
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Your session has expired. Please sign in again.") from exc

    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh))
    )
    if stored is None:
        raise AuthenticationError("Your session has expired. Please sign in again.")

    if stored.revoked_at is not None:
        # Replay. We cannot tell the thief from the victim, so end the whole
        # family and make both sign in again.
        revoke_session(db, stored.user_id, stored.session_id)
        raise AuthenticationError(
            "Your session was ended for security reasons. Please sign in again."
        )

    if stored.expires_at < _now():
        raise AuthenticationError("Your session has expired. Please sign in again.")

    user = db.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("This account is no longer active.")

    access, refresh = issue_tokens(
        db,
        user,
        remember_me=stored.remember_me,
        user_agent=user_agent or stored.user_agent,
        ip_address=ip_address,
        session_id=stored.session_id,
    )
    db.flush()

    new_record = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh))
    )
    stored.revoked_at = _now()
    stored.replaced_by_id = new_record.id if new_record else None

    return user, access, refresh


def revoke_session(db: Session, user_id: uuid.UUID, session_id: uuid.UUID) -> int:
    """Revoke every token in one session family. Returns how many were live."""
    result = db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.session_id == session_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )
    return result.rowcount or 0


def revoke_all_sessions(
    db: Session, user_id: uuid.UUID, *, except_session_id: uuid.UUID | None = None
) -> int:
    """Sign out everywhere, optionally keeping the current device signed in."""
    stmt = update(RefreshToken).where(
        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
    )
    if except_session_id is not None:
        stmt = stmt.where(RefreshToken.session_id != except_session_id)
    return db.execute(stmt.values(revoked_at=_now())).rowcount or 0


def list_active_sessions(db: Session, user_id: uuid.UUID) -> list[RefreshToken]:
    """One row per live session family, newest first."""
    rows = db.scalars(
        select(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > _now(),
        )
        .order_by(RefreshToken.created_at.desc())
    ).all()

    seen: set[uuid.UUID] = set()
    unique: list[RefreshToken] = []
    for row in rows:
        if row.session_id not in seen:
            seen.add(row.session_id)
            unique.append(row)
    return unique


# ── Password reset ───────────────────────────────────────────────────────────
def request_password_reset(db: Session, email: str, ip: str | None = None) -> tuple[User, str] | None:
    """Start a reset. Returns None when the address is unknown.

    The caller must respond identically either way, so the endpoint cannot be
    used to enumerate registered addresses.
    """
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        return None

    raw = generate_token()
    db.add(
        PasswordReset(
            user_id=user.id,
            token_hash=hash_token(raw),
            requested_ip=ip,
            expires_at=_now() + timedelta(hours=settings.PASSWORD_RESET_EXPIRE_HOURS),
        )
    )
    return user, raw


def reset_password(db: Session, raw_token: str, new_password: str) -> User:
    record = db.scalar(
        select(PasswordReset).where(PasswordReset.token_hash == hash_token(raw_token))
    )
    if record is None or record.consumed_at is not None:
        raise ValidationError("This reset link is invalid or already used.")
    if record.expires_at < _now():
        raise ValidationError("This reset link has expired.")

    user = db.get(User, record.user_id)
    if user is None:
        raise NotFoundError("Account not found.")

    user.password_hash = hash_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    record.consumed_at = _now()

    # Changing the password signs every other device out. Anyone who reset a
    # password because they suspect compromise expects exactly this.
    revoke_all_sessions(db, user.id)
    return user


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if user.password_hash is None or not verify_password(current, user.password_hash):
        raise ValidationError(
            "Your current password is incorrect.",
            details={"fields": {"current_password": "Incorrect"}},
        )
    user.password_hash = hash_password(new)


# ── Guest identity ───────────────────────────────────────────────────────────
def create_guest_session(
    db: Session, *, user_agent: str | None = None, ip_address: str | None = None
) -> tuple[GuestSession, str]:
    raw = generate_token()
    guest = GuestSession(
        token_hash=hash_token(raw),
        expires_at=_now() + timedelta(days=30),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(guest)
    db.flush()
    return guest, raw


def resolve_guest_session(db: Session, raw_token: str) -> GuestSession | None:
    if not raw_token:
        return None
    guest = db.scalar(
        select(GuestSession).where(GuestSession.token_hash == hash_token(raw_token))
    )
    if guest is None or guest.expires_at < _now() or guest.merged_at is not None:
        return None
    return guest
