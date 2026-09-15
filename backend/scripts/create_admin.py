"""Create (or promote) an admin account securely — no hardcoded passwords.

Use this for production instead of the demo seed accounts. Reads the email and
password from arguments or environment, so a real credential never lives in the
repo.

    # from the backend/ directory
    WOODCROFT_ADMIN_EMAIL=you@store.pk WOODCROFT_ADMIN_PASSWORD='<strong>' \
        python -m scripts.create_admin
    # or
    python -m scripts.create_admin you@store.pk '<strong-password>'

If the user already exists they are promoted to admin and (optionally) their
password reset.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.permissions import Role
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.identity import NotificationPreference, User
from app.models.promotion import LoyaltyAccount


def _referral_code() -> str:
    import secrets

    return "WCAD" + secrets.token_hex(3).upper()


def main() -> int:
    email = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WOODCROFT_ADMIN_EMAIL", "")).strip().lower()
    password = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("WOODCROFT_ADMIN_PASSWORD", "")

    if not email or "@" not in email:
        print("Provide an email (arg 1 or WOODCROFT_ADMIN_EMAIL).")
        return 1
    if len(password) < 10:
        print("Provide a strong password of at least 10 characters "
              "(arg 2 or WOODCROFT_ADMIN_PASSWORD).")
        return 1

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                full_name="Administrator",
                password_hash=hash_password(password),
                role=Role.ADMIN,
                email_verified_at=datetime.now(UTC),
                referral_code=_referral_code(),
            )
            db.add(user)
            db.flush()
            db.add(NotificationPreference(user_id=user.id))
            db.add(LoyaltyAccount(user_id=user.id))
            action = "created"
        else:
            user.role = Role.ADMIN
            user.password_hash = hash_password(password)
            user.email_verified_at = user.email_verified_at or datetime.now(UTC)
            action = "promoted and password reset"
        db.commit()
        print(f"Admin {action}: {email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
