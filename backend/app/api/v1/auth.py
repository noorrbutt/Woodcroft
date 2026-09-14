"""Authentication endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Request, status

from app.core.config import settings
from app.core.deps import (
    CurrentUser,
    DbSession,
    client_ip,
    get_current_user,
    user_agent,
)
from app.core.errors import AuthenticationError, NotFoundError
from app.core.ratelimit import limiter
from app.core.security import decode_token
from app.models.identity import NotificationPreference
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    GuestTokenOut,
    LoginRequest,
    NotificationPreferenceOut,
    NotificationPreferenceUpdate,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SessionOut,
    TokenPair,
    UpdateProfileRequest,
    UserOut,
    VerifyEmailRequest,
)
from app.schemas.common import Message
from app.services import auth as auth_service
from app.services import notifications

router = APIRouter(prefix="/auth", tags=["auth"])

FRONTEND = settings.PUBLIC_URL


def _tokens(access: str, refresh: str) -> TokenPair:
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_REGISTER)
def register(request: Request, payload: RegisterRequest, db: DbSession) -> AuthResponse:
    user, raw_token = auth_service.register_user(
        db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        phone=payload.phone,
        referred_by_code=payload.referral_code,
    )

    notifications.email(
        db,
        "email_verification",
        user.email,
        user=user,
        context={
            "verify_url": f"{FRONTEND}/verify-email?token={raw_token}",
            "expires_hours": settings.EMAIL_VERIFICATION_EXPIRE_HOURS,
        },
    )

    access, refresh = auth_service.issue_tokens(
        db, user, user_agent=user_agent(request), ip_address=client_ip(request)
    )
    return AuthResponse(user=UserOut.from_user(user), tokens=_tokens(access, refresh))


@router.post("/login", response_model=AuthResponse)
@limiter.limit(settings.RATE_LIMIT_LOGIN)
def login(request: Request, payload: LoginRequest, db: DbSession) -> AuthResponse:
    user = auth_service.authenticate(
        db, email=payload.email, password=payload.password
    )
    access, refresh = auth_service.issue_tokens(
        db,
        user,
        remember_me=payload.remember_me,
        user_agent=user_agent(request),
        ip_address=client_ip(request),
    )
    return AuthResponse(user=UserOut.from_user(user), tokens=_tokens(access, refresh))


@router.post("/refresh", response_model=TokenPair)
@limiter.limit("30/minute")
def refresh_tokens(request: Request, payload: RefreshRequest, db: DbSession) -> TokenPair:
    _, access, refresh = auth_service.rotate_refresh_token(
        db,
        payload.refresh_token,
        user_agent=user_agent(request),
        ip_address=client_ip(request),
    )
    return _tokens(access, refresh)


@router.post("/logout", response_model=Message)
def logout(payload: RefreshRequest, db: DbSession) -> Message:
    """End the current session only. Other devices stay signed in."""
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except jwt.PyJWTError:
        # An expired or malformed token is already unusable, so report success
        # rather than making the user look at an error while signing out.
        return Message(message="Signed out.")

    auth_service.revoke_session(
        db, uuid.UUID(claims["sub"]), uuid.UUID(claims["sid"])
    )
    return Message(message="Signed out.")


@router.post("/logout-all", response_model=Message)
def logout_all(user: CurrentUser, db: DbSession) -> Message:
    count = auth_service.revoke_all_sessions(db, user.id)
    return Message(message=f"Signed out of {count} session(s).")


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(user: CurrentUser, db: DbSession) -> list[SessionOut]:
    return [
        SessionOut(
            session_id=row.session_id,
            user_agent=row.user_agent,
            ip_address=row.ip_address,
            created_at=row.created_at,
            expires_at=row.expires_at,
        )
        for row in auth_service.list_active_sessions(db, user.id)
    ]


@router.delete("/sessions/{session_id}", response_model=Message)
def revoke_session(session_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Message:
    revoked = auth_service.revoke_session(db, user.id, session_id)
    if not revoked:
        raise NotFoundError("That session is no longer active.")
    return Message(message="Session ended.")


@router.post("/verify-email", response_model=Message)
@limiter.limit(settings.RATE_LIMIT_PASSWORD_RESET)
def verify_email(request: Request, payload: VerifyEmailRequest, db: DbSession) -> Message:
    auth_service.verify_email(db, payload.token)
    return Message(message="Your email address is confirmed.")


@router.post("/resend-verification", response_model=Message)
@limiter.limit(settings.RATE_LIMIT_PASSWORD_RESET)
def resend_verification(request: Request, user: CurrentUser, db: DbSession) -> Message:
    if user.email_verified_at is not None:
        return Message(message="Your email is already confirmed.")

    raw = auth_service.issue_email_verification(db, user)
    notifications.email(
        db,
        "email_verification",
        user.email,
        user=user,
        context={
            "verify_url": f"{FRONTEND}/verify-email?token={raw}",
            "expires_hours": settings.EMAIL_VERIFICATION_EXPIRE_HOURS,
        },
    )
    return Message(message="Confirmation email sent.")


@router.post("/forgot-password", response_model=Message)
@limiter.limit(settings.RATE_LIMIT_PASSWORD_RESET)
def forgot_password(
    request: Request, payload: ForgotPasswordRequest, db: DbSession
) -> Message:
    result = auth_service.request_password_reset(
        db, payload.email, ip=client_ip(request)
    )
    if result is not None:
        user, raw = result
        notifications.email(
            db,
            "password_reset",
            user.email,
            user=user,
            context={
                "reset_url": f"{FRONTEND}/reset-password?token={raw}",
                "expires_hours": settings.PASSWORD_RESET_EXPIRE_HOURS,
            },
        )

    # Same response whether or not the address exists, so this endpoint cannot
    # be used to find out who has an account.
    return Message(
        message="If that email is registered, a reset link is on its way."
    )


@router.post("/reset-password", response_model=Message)
@limiter.limit(settings.RATE_LIMIT_PASSWORD_RESET)
def reset_password(
    request: Request, payload: ResetPasswordRequest, db: DbSession
) -> Message:
    user = auth_service.reset_password(db, payload.token, payload.password)
    notifications.email(db, "password_changed", user.email, user=user)
    return Message(message="Your password has been reset. Please sign in.")


@router.post("/change-password", response_model=Message)
def change_password(
    payload: ChangePasswordRequest, user: CurrentUser, db: DbSession
) -> Message:
    auth_service.change_password(db, user, payload.current_password, payload.password)
    notifications.email(db, "password_changed", user.email, user=user)
    return Message(message="Password updated.")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.from_user(user)


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: UpdateProfileRequest, user: CurrentUser, db: DbSession
) -> UserOut:
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.phone is not None:
        user.phone = auth_service.normalise_phone(payload.phone)
    db.flush()
    return UserOut.from_user(user)


@router.get("/me/notifications", response_model=NotificationPreferenceOut)
def get_notification_preferences(
    user: CurrentUser, db: DbSession
) -> NotificationPreferenceOut:
    prefs = user.notification_preference
    if prefs is None:
        prefs = NotificationPreference(user_id=user.id)
        db.add(prefs)
        db.flush()
    return NotificationPreferenceOut.model_validate(prefs)


@router.patch("/me/notifications", response_model=NotificationPreferenceOut)
def update_notification_preferences(
    payload: NotificationPreferenceUpdate, user: CurrentUser, db: DbSession
) -> NotificationPreferenceOut:
    prefs = user.notification_preference
    if prefs is None:
        prefs = NotificationPreference(user_id=user.id)
        db.add(prefs)
        db.flush()

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(prefs, field, value)
    db.flush()
    return NotificationPreferenceOut.model_validate(prefs)


@router.post("/guest", response_model=GuestTokenOut, status_code=status.HTTP_201_CREATED)
def create_guest(request: Request, db: DbSession) -> GuestTokenOut:
    """Issue a guest identity so an anonymous visitor can use a cart."""
    guest, raw = auth_service.create_guest_session(
        db, user_agent=user_agent(request), ip_address=client_ip(request)
    )
    return GuestTokenOut(guest_token=raw, expires_at=guest.expires_at)


@router.delete("/me", response_model=Message)
def deactivate_account(user: CurrentUser, db: DbSession) -> Message:
    """Deactivate rather than delete.

    Orders reference the account, so a hard delete would tear holes in history.
    A full erasure goes through the data-request flow instead.
    """
    user.is_active = False
    user.deactivated_at = datetime.now(UTC)
    auth_service.revoke_all_sessions(db, user.id)
    return Message(message="Your account has been deactivated.")
