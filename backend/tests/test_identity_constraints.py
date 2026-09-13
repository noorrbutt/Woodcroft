"""Database-level guarantees on the identity tables.

These assert that the *database* enforces the rules, not just the application.
Anything relying only on application-side validation can be bypassed by a bulk
import, a seed script or a manual fix-up query.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError

INSERT_USER = text(
    'INSERT INTO "user" (email, full_name, role) '
    "VALUES (:email, :name, 'customer') RETURNING id"
)


def _make_user(raw, email: str = "ali@woodcroft.pk", name: str = "Ali Raza"):
    return raw.execute(INSERT_USER, {"email": email, "name": name}).scalar_one()


class TestUserIdentity:
    def test_id_is_uuid_v7(self, raw) -> None:
        """PG18's native uuidv7() gives us time-sortable, non-enumerable ids."""
        uid = _make_user(raw)
        assert uid.version == 7

    def test_uuid_v7_ids_sort_by_creation_time(self, raw) -> None:
        first = _make_user(raw, "a@woodcroft.pk")
        second = _make_user(raw, "b@woodcroft.pk")
        # This orderability is why v7 was chosen over v4: it keeps B-tree
        # inserts local instead of scattering them across the index.
        assert str(first) < str(second)

    def test_email_is_case_insensitive(self, raw) -> None:
        _make_user(raw, "Ali@Woodcroft.pk")
        with pytest.raises(IntegrityError):
            _make_user(raw, "ali@woodcroft.pk", "Impostor")

    def test_email_lookup_ignores_case(self, raw) -> None:
        _make_user(raw, "Ali@Woodcroft.pk")
        found = raw.execute(
            text('SELECT full_name FROM "user" WHERE email = :e'),
            {"e": "ALI@WOODCROFT.PK"},
        ).scalar_one()
        assert found == "Ali Raza"


class TestPhoneConstraint:
    @pytest.mark.parametrize("phone", ["03001234567", "03451234567", "03219876543"])
    def test_accepts_pakistani_mobile(self, raw, phone: str) -> None:
        _make_user(raw)
        raw.execute(text('UPDATE "user" SET phone = :p'), {"p": phone})

    @pytest.mark.parametrize(
        "phone",
        [
            "+923001234567",  # must be normalised before storage
            "0300123456",  # too short
            "030012345678",  # too long
            "02001234567",  # landline prefix
            "abcdefghijk",
            "0300-1234567",  # punctuation must be stripped first
        ],
    )
    def test_rejects_invalid_phone(self, raw, phone: str) -> None:
        _make_user(raw)
        with pytest.raises(IntegrityError):
            raw.execute(text('UPDATE "user" SET phone = :p'), {"p": phone})

    def test_null_phone_allowed(self, raw) -> None:
        _make_user(raw)
        raw.execute(text('UPDATE "user" SET phone = NULL'))


class TestAddressConstraints:
    @staticmethod
    def _insert_address(raw, user_id, *, default_shipping=False, province="punjab",
                        postal="54000"):
        return raw.execute(
            text(
                "INSERT INTO address "
                "(user_id, full_name, phone, line1, city, province, postal_code, "
                " is_default_shipping) "
                "VALUES (:u, 'Ali Raza', '03001234567', 'House 12, Street 4', "
                "        'Lahore', :prov, :postal, :ds) RETURNING id"
            ),
            {"u": user_id, "prov": province, "postal": postal, "ds": default_shipping},
        ).scalar_one()

    def test_only_one_default_shipping_per_user(self, raw) -> None:
        uid = _make_user(raw)
        self._insert_address(raw, uid, default_shipping=True)
        with pytest.raises(IntegrityError):
            self._insert_address(raw, uid, default_shipping=True)

    def test_many_non_default_addresses_allowed(self, raw) -> None:
        uid = _make_user(raw)
        for _ in range(3):
            self._insert_address(raw, uid, default_shipping=False)

    def test_rejects_unknown_province(self, raw) -> None:
        uid = _make_user(raw)
        with pytest.raises((DataError, IntegrityError)):
            self._insert_address(raw, uid, province="texas")

    @pytest.mark.parametrize("postal", ["5400", "540000", "ABCDE"])
    def test_rejects_malformed_postal_code(self, raw, postal: str) -> None:
        uid = _make_user(raw)
        with pytest.raises(IntegrityError):
            self._insert_address(raw, uid, postal=postal)

    def test_postal_code_optional(self, raw) -> None:
        uid = _make_user(raw)
        self._insert_address(raw, uid, postal=None)


class TestStaffPermissions:
    def test_permission_granted_once_per_user(self, raw) -> None:
        uid = _make_user(raw)
        stmt = text(
            "INSERT INTO staff_permission_grant (user_id, permission) "
            "VALUES (:u, 'order:refund')"
        )
        raw.execute(stmt, {"u": uid})
        with pytest.raises(IntegrityError):
            raw.execute(stmt, {"u": uid})
