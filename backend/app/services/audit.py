"""The admin audit trail.

Every staff or admin action that changes data writes one row here, with the
actor's email copied in alongside the id so the trail survives the account
being deleted. Lives in services rather than in a router because both admin
routers write to it and neither owns it.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.identity import User
from app.models.ops import AuditLog


def audit(
    db: Session,
    actor: User,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    summary: str,
    changes: dict[str, Any] | None = None,
) -> None:
    """Record one administrative action."""
    db.add(
        AuditLog(
            actor_id=actor.id,
            actor_email=actor.email,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            summary=summary,
            changes=changes or {},
        )
    )
