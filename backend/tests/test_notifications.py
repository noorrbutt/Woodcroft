from __future__ import annotations

import uuid
from unittest.mock import Mock

from app.models.enums import NotificationChannel, NotificationStatus
from app.services import notifications
from app.workers import jobs


class _NotificationSession:
    def __init__(self) -> None:
        self.added = None
        self.scalar_results = []

    def scalar(self, statement):
        return self.scalar_results.pop(0)

    def add(self, instance) -> None:
        self.added = instance

    def flush(self) -> None:
        self.added.id = uuid.uuid4()


def test_queued_email_is_delivered_once_by_worker(monkeypatch) -> None:
    db = _NotificationSession()
    driver = Mock()
    driver.name = "smtp"
    db.scalar_results = [None]
    enqueue = Mock()
    monkeypatch.setattr(notifications, "_render", lambda *args: ("Subject", "", "Body"))
    monkeypatch.setattr(notifications, "driver_for", lambda channel: driver)
    monkeypatch.setattr("app.workers.runner.enqueue", enqueue)

    message = notifications.send(
        db,
        key="order_confirmation",
        channel=NotificationChannel.EMAIL,
        recipient="guest@example.pk",
    )

    assert message.status is NotificationStatus.QUEUED
    driver.send.assert_not_called()
    enqueue.assert_called_once_with(
        db,
        "send_notification",
        {"notification_id": str(message.id)},
        dedupe_key=f"notif:{message.id}",
    )

    db.scalar_results = [message, message]
    payload = {"notification_id": str(message.id)}
    jobs.send_notification(db, payload)

    assert message.status is NotificationStatus.SENT
    driver.send.assert_called_once_with(message)

    jobs.send_notification(db, payload)
    driver.send.assert_called_once_with(message)
