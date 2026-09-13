"""Seed customers, staff and the demo accounts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.permissions import DEFAULT_STAFF_PERMISSIONS, Role
from app.core.security import hash_password
from app.models.identity import (
    Address,
    NotificationPreference,
    StaffPermissionGrant,
    User,
)
from app.models.promotion import LoyaltyAccount, LoyaltyTransaction

#: Documented in the README and printed by the seeder.
DEMO_ACCOUNTS = [
    ("admin@woodcroft.pk", "Admin User", Role.ADMIN, "woodcroft-admin"),
    ("staff@woodcroft.pk", "Workshop Staff", Role.STAFF, "woodcroft-staff"),
    ("customer@woodcroft.pk", "Ayesha Khan", Role.CUSTOMER, "woodcroft-demo"),
]


def seed_people(s) -> None:
    _demo_accounts(s)
    _customers(s, count=50)
    s.db.flush()
    s.log(f"{len(s.users)} customers, plus admin and staff")


def _demo_accounts(s) -> None:
    for email, name, role, password in DEMO_ACCOUNTS:
        user, created = s.get_or_create(
            User,
            {
                "full_name": name,
                "password_hash": hash_password(password),
                "role": role,
                "phone": s.phone(),
                "email_verified_at": datetime.now(UTC),
                "referral_code": f"WC{role.value[:2].upper()}{s.rng.randint(1000, 9999)}",
            },
            email=email,
        )
        if created:
            s.db.add(NotificationPreference(user_id=user.id))
            s.db.add(LoyaltyAccount(user_id=user.id, points_balance=2400,
                                    lifetime_points_earned=2400, tier="gold"))
            _addresses(s, user, count=2)

        if role is Role.ADMIN:
            s.admin = user
        elif role is Role.STAFF:
            s.staff = user
            for permission in DEFAULT_STAFF_PERMISSIONS:
                s.get_or_create(
                    StaffPermissionGrant, {},
                    user_id=user.id, permission=permission.value,
                )
        else:
            s.users.append(user)


def _customers(s, count: int) -> None:
    for i in range(count):
        name = s.person()
        handle = name.lower().replace(" ", ".")
        email = f"{handle}{i}@example.pk"

        user, created = s.get_or_create(
            User,
            {
                "full_name": name,
                "password_hash": hash_password("woodcroft-demo"),
                "role": Role.CUSTOMER,
                "phone": s.phone(),
                # A few unverified accounts, so that state is visible in admin.
                "email_verified_at": (
                    datetime.now(UTC) if s.rng.random() < 0.85 else None
                ),
                "referral_code": f"WC{s.rng.randint(100000, 999999)}",
                "store_credit_paisa": s.rng.choice([0, 0, 0, 0, 50_000, 100_000]),
                "is_active": s.rng.random() > 0.04,
            },
            email=email,
        )

        if created:
            s.db.add(NotificationPreference(
                user_id=user.id,
                email_marketing=s.rng.random() < 0.75,
                sms_marketing=s.rng.random() < 0.35,
            ))

            points = s.rng.choice([0, 0, 120, 340, 850, 1500, 3200])
            tier = "gold" if points > 1000 else "silver" if points > 300 else "bronze"
            account = LoyaltyAccount(
                user_id=user.id,
                points_balance=points,
                lifetime_points_earned=points + s.rng.randint(0, 800),
                tier=tier,
            )
            s.db.add(account)
            s.db.flush()

            if points:
                s.db.add(LoyaltyTransaction(
                    account_id=account.id, kind="earned",
                    delta_points=points, balance_after=points,
                    note="Earned on earlier orders",
                ))

            _addresses(s, user, count=s.rng.randint(1, 2))

        s.users.append(user)


def _addresses(s, user: User, count: int) -> None:
    from app.seed.runner import AREAS, CITIES, LANDMARKS

    for i in range(count):
        city, province, postal = s.rng.choice(CITIES)
        s.db.add(Address(
            user_id=user.id,
            label="Home" if i == 0 else "Office",
            full_name=user.full_name,
            phone=user.phone or s.phone(),
            line1=f"House {s.rng.randint(1, 400)}, Street {s.rng.randint(1, 60)}",
            area=s.rng.choice(AREAS),
            # Landmarks are how Pakistani addresses actually work, but not
            # everyone supplies one.
            landmark=s.rng.choice(LANDMARKS) if s.rng.random() < 0.6 else None,
            city=city,
            province=province,
            postal_code=postal,
            is_default_shipping=(i == 0),
            is_default_billing=(i == 0),
        ))
