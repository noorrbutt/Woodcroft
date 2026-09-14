"""Notification delivery.

Every message is rendered and written to ``notification_outbox`` before any
attempt to send it. That gives three things at once: a complete audit trail, a
working notification system with no SMTP or SMS account, and an Admin ->
Notifications screen where you can read exactly what a customer received.

Drivers are selected by ``EMAIL_DRIVER`` / ``SMS_DRIVER``. The default,
``outbox``, stores and stops. Setting ``smtp`` or ``sms_gateway`` makes delivery
additionally go out over the wire; the row is written either way, so switching
drivers never loses history.
"""

from __future__ import annotations

import smtplib
import ssl
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from jinja2 import FileSystemLoader, select_autoescape
from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, settings
from app.core.money import format_pkr
from app.models.enums import NotificationChannel, NotificationStatus
from app.models.identity import NotificationPreference, User
from app.models.ops import NotificationOutbox, NotificationTemplate

TEMPLATE_DIR = BACKEND_DIR / "app" / "templates"

# Sandboxed: some templates come from the notification_template DB rows, which a
# future admin template editor would let staff write. Plain Jinja from a database
# string is remote code execution; the sandbox blocks attribute access to Python
# internals while still rendering normal templates.
_env = SandboxedEnvironment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
# Templates render money through the same function the API and PDFs use.
_env.filters["pkr"] = lambda paisa: format_pkr(paisa or 0)


#: Which notification preference column, if any, gates each template.
PREFERENCE_GATE: dict[str, str] = {
    "order_confirmation": "email_order_updates",
    "order_shipped": "email_order_updates",
    "order_delivered": "email_order_updates",
    "order_cancelled": "email_order_updates",
    "refund_processed": "email_order_updates",
    "back_in_stock": "email_back_in_stock",
    "price_drop": "email_price_drop",
    "review_reminder": "email_review_reminder",
    "abandoned_cart": "email_marketing",
    "newsletter": "email_marketing",
}

#: Transactional messages that must always go out. A password reset cannot be
#: suppressed by a marketing preference, or people get locked out of accounts.
ALWAYS_SEND = {
    "email_verification",
    "password_reset",
    "password_changed",
    "account_locked",
    "data_export_ready",
}


class NotificationDriver(ABC):
    """Delivery transport. The outbox row is written regardless of driver."""

    name: str

    @abstractmethod
    def send(self, message: NotificationOutbox) -> None:
        """Deliver, or raise. Raising marks the row failed and records why."""


class OutboxDriver(NotificationDriver):
    """Stores only. The default, and what makes the app work offline."""

    name = "outbox"

    def send(self, message: NotificationOutbox) -> None:
        return None


class SmtpDriver(NotificationDriver):
    name = "smtp"

    def send(self, message: NotificationOutbox) -> None:
        if not settings.SMTP_HOST:
            raise RuntimeError("SMTP_HOST is not configured")

        email = EmailMessage()
        email["Subject"] = message.subject or "(no subject)"
        email["From"] = settings.SMTP_FROM
        email["To"] = message.recipient
        email.set_content(message.body_text)
        if message.body_html:
            email.add_alternative(message.body_html, subtype="html")

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
            # Verify the relay's certificate. Without a context, smtplib falls
            # back to an unverified TLS session, so a man in the middle could
            # capture the SMTP credentials and every reset/verification token.
            smtp.starttls(context=ssl.create_default_context())
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(email)


class SmsGatewayDriver(NotificationDriver):
    name = "sms_gateway"

    def send(self, message: NotificationOutbox) -> None:
        if not settings.SMS_GATEWAY_URL:
            raise RuntimeError("SMS_GATEWAY_URL is not configured")

        import httpx

        response = httpx.post(
            settings.SMS_GATEWAY_URL,
            json={
                "to": message.recipient,
                "text": message.body_text,
                "key": settings.SMS_GATEWAY_KEY,
            },
            timeout=20,
        )
        response.raise_for_status()


_EMAIL_DRIVERS = {"outbox": OutboxDriver, "smtp": SmtpDriver}
_SMS_DRIVERS = {"outbox": OutboxDriver, "sms_gateway": SmsGatewayDriver}


def driver_for(channel: NotificationChannel) -> NotificationDriver:
    if channel is NotificationChannel.EMAIL:
        return _EMAIL_DRIVERS.get(settings.EMAIL_DRIVER, OutboxDriver)()
    return _SMS_DRIVERS.get(settings.SMS_DRIVER, OutboxDriver)()


def _render(
    db: Session, key: str, channel: NotificationChannel, context: dict[str, Any]
) -> tuple[str | None, str, str]:
    """Render (subject, html, text).

    An admin-edited template in the database wins. Otherwise the file shipped
    with the app is used, so a fresh install has working notifications before
    anyone touches the template editor.
    """
    record = db.scalar(
        select(NotificationTemplate).where(
            NotificationTemplate.key == key,
            NotificationTemplate.channel == channel,
            NotificationTemplate.is_active.is_(True),
        )
    )

    if record is not None:
        subject = (
            _env.from_string(record.subject_template).render(**context)
            if record.subject_template
            else None
        )
        body = _env.from_string(record.body_template).render(**context)
        if channel is NotificationChannel.SMS:
            return subject, "", body
        return subject, body, _html_to_text(body)

    if channel is NotificationChannel.SMS:
        template = _env.get_template(f"sms/{key}.txt")
        return None, "", template.render(**context)

    subject_tpl = TEMPLATE_DIR / "email" / f"{key}.subject.txt"
    subject = (
        _env.get_template(f"email/{key}.subject.txt").render(**context).strip()
        if subject_tpl.exists()
        else context.get("subject", "Woodcroft")
    )
    html = _env.get_template(f"email/{key}.html").render(**context)
    return subject, html, _html_to_text(html)


def _html_to_text(html: str) -> str:
    """A crude but dependency-free plain-text alternative part."""
    import re

    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</div>|</tr>|</h[1-6]>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _is_suppressed(db: Session, user_id: uuid.UUID | None, key: str) -> str | None:
    """Return a reason when the user has opted out of this kind of message."""
    if key in ALWAYS_SEND or user_id is None:
        return None
    column = PREFERENCE_GATE.get(key)
    if column is None:
        return None

    prefs = db.scalar(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    )
    if prefs is None:
        return None
    if getattr(prefs, column, True):
        return None
    return f"user opted out of {column}"


def send(
    db: Session,
    *,
    key: str,
    channel: NotificationChannel,
    recipient: str,
    context: dict[str, Any] | None = None,
    user: User | None = None,
    user_id: uuid.UUID | None = None,
    order_id: uuid.UUID | None = None,
    recipient_name: str | None = None,
) -> NotificationOutbox:
    """Render, store and attempt delivery. Never raises on delivery failure.

    A failed email must not roll back the order that triggered it, so problems
    are recorded on the row and surfaced in admin instead of propagating.
    """
    context = dict(context or {})
    resolved_user_id = user.id if user is not None else user_id

    context.setdefault("store_name", settings.APP_NAME)
    context.setdefault("recipient_name", recipient_name or (user.full_name if user else ""))
    context.setdefault("year", datetime.now(UTC).year)

    suppressed = _is_suppressed(db, resolved_user_id, key)
    if suppressed:
        # Nothing to render: the message is never going anywhere. The row is
        # still written so admin can see the opt-out took effect.
        message = NotificationOutbox(
            channel=channel,
            template_key=key,
            recipient=recipient,
            recipient_name=recipient_name,
            user_id=resolved_user_id,
            order_id=order_id,
            body_text="",
            status=NotificationStatus.SUPPRESSED,
            suppressed_reason=suppressed,
            driver=driver_for(channel).name,
            context=context,
        )
        db.add(message)
        return message

    try:
        subject, html, text = _render(db, key, channel, context)
    except Exception as exc:  # template missing or broken
        message = NotificationOutbox(
            channel=channel,
            template_key=key,
            recipient=recipient,
            recipient_name=recipient_name,
            user_id=resolved_user_id,
            order_id=order_id,
            subject="(render failed)",
            body_text="",
            status=NotificationStatus.FAILED,
            driver=driver_for(channel).name,
            last_error=f"{type(exc).__name__}: {exc}",
            context=context,
        )
        db.add(message)
        return message

    message = NotificationOutbox(
        channel=channel,
        template_key=key,
        recipient=recipient,
        recipient_name=recipient_name,
        user_id=resolved_user_id,
        order_id=order_id,
        subject=subject,
        body_html=html or None,
        body_text=text,
        driver=driver_for(channel).name,
        context=context,
    )

    db.add(message)
    _attempt(message)
    return message


def _attempt(message: NotificationOutbox) -> None:
    driver = driver_for(message.channel)
    # A column default only lands at INSERT, so a row built in memory still
    # has attempts = None here.
    message.attempts = (message.attempts or 0) + 1
    try:
        driver.send(message)
        message.status = NotificationStatus.SENT
        message.sent_at = datetime.now(UTC)
        message.last_error = None
    except Exception as exc:
        message.status = NotificationStatus.FAILED
        message.last_error = f"{type(exc).__name__}: {exc}"


def resend(db: Session, message_id: uuid.UUID) -> NotificationOutbox | None:
    """Retry one message from the admin outbox viewer."""
    message = db.get(NotificationOutbox, message_id)
    if message is None:
        return None
    message.driver = driver_for(message.channel).name
    _attempt(message)
    return message


def email(db: Session, key: str, recipient: str, **kwargs: Any) -> NotificationOutbox:
    return send(db, key=key, channel=NotificationChannel.EMAIL, recipient=recipient, **kwargs)


def sms(db: Session, key: str, recipient: str, **kwargs: Any) -> NotificationOutbox:
    return send(db, key=key, channel=NotificationChannel.SMS, recipient=recipient, **kwargs)
