"""Exception hierarchy and the single JSON error envelope the API returns.

Every error response has the same shape, so the frontend needs exactly one
error-handling path:

    {"error": {"code": "out_of_stock", "message": "...", "details": {...}}}
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError


class AppError(Exception):
    """Base class for every error the application raises deliberately."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "Request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)

    def to_response(self) -> JSONResponse:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return JSONResponse(status_code=self.status_code, content={"error": payload})


# ── 4xx ──────────────────────────────────────────────────────────────────────
class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_error"
    message = "The submitted data is invalid."


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "authentication_required"
    message = "Authentication is required."


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"
    message = "Email or password is incorrect."


class AccountLockedError(AuthenticationError):
    code = "account_locked"
    message = "Too many failed attempts. Try again shortly."


class EmailNotVerifiedError(AuthenticationError):
    code = "email_not_verified"
    message = "Please verify your email address first."


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"
    message = "You do not have permission to perform this action."


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "The request conflicts with the current state."


class EmailAlreadyRegisteredError(ConflictError):
    code = "email_already_registered"
    message = "An account with this email already exists."


# ── Domain-specific ──────────────────────────────────────────────────────────
class OutOfStockError(ConflictError):
    code = "out_of_stock"
    message = "This item is no longer available in the requested quantity."


class InsufficientStockError(ConflictError):
    code = "insufficient_stock"
    message = "Not enough stock remaining."


class ReservationExpiredError(ConflictError):
    code = "reservation_expired"
    message = "Your checkout reservation expired. Please review your cart."


class CartEmptyError(AppError):
    code = "cart_empty"
    message = "Your cart is empty."


class CouponInvalidError(AppError):
    code = "coupon_invalid"
    message = "This coupon code is not valid."


class PaymentMethodUnavailableError(AppError):
    code = "payment_method_unavailable"
    message = "This payment method is not currently available."


class CodNotAvailableError(PaymentMethodUnavailableError):
    code = "cod_not_available"
    message = "Cash on Delivery is not available for this order."


class OrderNotCancellableError(ConflictError):
    code = "order_not_cancellable"
    message = "This order can no longer be cancelled."


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "Too many requests. Please slow down."


def register_exception_handlers(app: FastAPI) -> None:
    """Wire every handler so responses share one envelope."""

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return exc.to_response()

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, str] = {}
        for err in exc.errors():
            # loc looks like ("body", "email"); drop the source segment.
            location = ".".join(str(p) for p in err["loc"][1:]) or "body"
            fields[location] = err["msg"]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "The submitted data is invalid.",
                    "details": {"fields": fields},
                }
            },
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        # Surface a clean conflict rather than leaking the SQL constraint text.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": {
                    "code": "conflict",
                    "message": "That operation conflicts with existing data.",
                }
            },
        )
