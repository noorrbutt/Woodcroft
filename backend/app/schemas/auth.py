"""Auth request and response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.permissions import Role
from app.schemas.common import Schema

#: Deliberately modest. Length is what actually protects a password; character
#: class rules mostly push people towards "Password1!" and a sticky note.
MIN_PASSWORD_LENGTH = 8


class PasswordField(BaseModel):
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)

    @field_validator("password")
    @classmethod
    def not_trivial(cls, v: str) -> str:
        if v.lower() in {"password", "12345678", "qwertyui", "woodcroft"}:
            raise ValueError("Please choose a less common password")
        return v


class RegisterRequest(PasswordField):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    phone: str | None = Field(None, max_length=20)
    referral_code: str | None = Field(None, max_length=16)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(Schema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(PasswordField):
    token: str


class ChangePasswordRequest(PasswordField):
    current_password: str


class VerifyEmailRequest(BaseModel):
    token: str


class UserOut(Schema):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    avatar_path: str | None
    role: Role
    is_email_verified: bool
    referral_code: str | None
    store_credit_paisa: int
    created_at: datetime

    @classmethod
    def from_user(cls, user) -> UserOut:
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            avatar_path=user.avatar_path,
            role=user.role,
            is_email_verified=user.email_verified_at is not None,
            referral_code=user.referral_code,
            store_credit_paisa=user.store_credit_paisa,
            created_at=user.created_at,
        )


class AuthResponse(Schema):
    user: UserOut
    tokens: TokenPair


class SessionOut(Schema):
    """One active sign-in, for the "where am I logged in" screen."""

    session_id: uuid.UUID
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    expires_at: datetime
    is_current: bool = False


class GuestTokenOut(Schema):
    guest_token: str
    expires_at: datetime


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=120)
    phone: str | None = Field(None, max_length=20)


class NotificationPreferenceOut(Schema):
    email_order_updates: bool
    email_marketing: bool
    email_back_in_stock: bool
    email_price_drop: bool
    email_review_reminder: bool
    sms_order_updates: bool
    sms_marketing: bool


class NotificationPreferenceUpdate(BaseModel):
    email_order_updates: bool | None = None
    email_marketing: bool | None = None
    email_back_in_stock: bool | None = None
    email_price_drop: bool | None = None
    email_review_reminder: bool | None = None
    sms_order_updates: bool | None = None
    sms_marketing: bool | None = None
