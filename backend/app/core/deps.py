"""FastAPI dependencies: current user, guest identity, permission gates."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.permissions import Permission, Role
from app.core.security import decode_token
from app.db.session import get_db
from app.models.identity import GuestSession, User
from app.services import auth as auth_service

DbSession = Annotated[Session, Depends(get_db)]


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    return token if scheme.lower() == "bearer" and token else None


def get_current_user_optional(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """Resolve the signed-in user, or None. Never raises for anonymous callers."""
    token = _bearer(authorization)
    if not token:
        return None
    try:
        payload = decode_token(token, expected_type="access")
    except jwt.PyJWTError:
        return None

    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active or user.deactivated_at is not None:
        return None
    return user


def get_current_user(
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User:
    if user is None:
        raise AuthenticationError()
    return user


def get_verified_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.email_verified_at is None:
        raise AuthenticationError(
            "Please verify your email address first.", code="email_not_verified"
        )
    return user


def get_guest_session(
    db: DbSession,
    x_guest_token: Annotated[str | None, Header()] = None,
) -> GuestSession | None:
    if not x_guest_token:
        return None
    return auth_service.resolve_guest_session(db, x_guest_token)


class Shopper:
    """Whoever is shopping: a signed-in user or a guest session.

    Cart, wishlist and checkout all work for both, so they take this rather
    than requiring an account.
    """

    def __init__(self, user: User | None, guest: GuestSession | None) -> None:
        self.user = user
        self.guest = guest

    @property
    def is_authenticated(self) -> bool:
        return self.user is not None

    @property
    def user_id(self) -> uuid.UUID | None:
        return self.user.id if self.user else None

    @property
    def guest_session_id(self) -> uuid.UUID | None:
        # A signed-in user's activity is always attributed to the account, even
        # if a stale guest token is still being sent by the browser.
        if self.user is not None:
            return None
        return self.guest.id if self.guest else None

    @property
    def exists(self) -> bool:
        return self.user is not None or self.guest is not None


def get_shopper(
    user: Annotated[User | None, Depends(get_current_user_optional)],
    guest: Annotated[GuestSession | None, Depends(get_guest_session)],
) -> Shopper:
    return Shopper(user, guest)


def require_staff(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role not in (Role.STAFF, Role.ADMIN):
        raise PermissionDeniedError()
    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role is not Role.ADMIN:
        raise PermissionDeniedError("This action requires an administrator account.")
    return user


def require_permission(permission: Permission) -> Callable[..., User]:
    """Gate an admin route on one granular permission.

    Admins pass everything. Staff pass only what has been granted to them. The
    frontend hides controls a role cannot use, but this is the actual authority.
    """

    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if not user.has_permission(permission):
            raise PermissionDeniedError(
                f"You do not have the '{permission.value}' permission."
            )
        return user

    return dependency


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]
VerifiedUser = Annotated[User, Depends(get_verified_user)]
CurrentShopper = Annotated[Shopper, Depends(get_shopper)]
StaffUser = Annotated[User, Depends(require_staff)]
AdminUser = Annotated[User, Depends(require_admin)]
