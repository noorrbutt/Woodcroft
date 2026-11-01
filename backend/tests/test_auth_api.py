"""End to end auth flows through the real HTTP app."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import get_db
from app.main import app
from app.models.enums import NotificationStatus
from app.models.identity import User
from app.models.ops import NotificationOutbox

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"


@pytest.fixture
def client(db):
    """A TestClient whose requests run inside the test's rolled back session."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _register(client, email="ayesha@woodcroft.pk", password="walnut-table-8"):
    return client.post(
        REGISTER,
        json={"email": email, "password": password, "full_name": "Ayesha Khan"},
    )


class TestRegistration:
    def test_creates_account_and_returns_tokens(self, client) -> None:
        r = _register(client)
        assert r.status_code == 201
        body = r.json()
        assert body["user"]["email"] == "ayesha@woodcroft.pk"
        assert body["user"]["role"] == "customer"
        assert body["user"]["is_email_verified"] is False
        assert body["tokens"]["access_token"]
        assert "refresh_token" not in body["tokens"]

    def test_issues_a_referral_code(self, client) -> None:
        code = _register(client).json()["user"]["referral_code"]
        assert code.startswith("WC")
        assert len(code) == 8

    def test_duplicate_email_rejected(self, client) -> None:
        _register(client)
        r = _register(client)
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "email_already_registered"

    def test_duplicate_email_is_case_insensitive(self, client) -> None:
        _register(client, email="Ayesha@Woodcroft.pk")
        r = _register(client, email="ayesha@woodcroft.pk")
        assert r.status_code == 409

    def test_short_password_rejected(self, client) -> None:
        r = _register(client, password="short")
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"

    def test_common_password_rejected(self, client) -> None:
        r = _register(client, password="password")
        assert r.status_code == 422

    def test_verification_email_lands_in_the_outbox(self, client, db) -> None:
        """With no SMTP configured the message still exists and is readable."""
        _register(client)
        message = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.template_key == "email_verification"
            )
        )
        assert message is not None
        assert message.recipient == "ayesha@woodcroft.pk"
        assert message.status is NotificationStatus.SENT
        assert message.driver == "outbox"
        assert "Confirm email" in (message.body_html or "")

    @pytest.mark.parametrize(
        "phone,stored",
        [
            ("03001234567", "03001234567"),
            ("+923001234567", "03001234567"),
            ("0300-1234567", "03001234567"),
            ("3001234567", "03001234567"),
        ],
    )
    def test_phone_is_normalised(self, client, db, phone, stored) -> None:
        r = client.post(
            REGISTER,
            json={
                "email": "p@woodcroft.pk",
                "password": "walnut-table-8",
                "full_name": "Test User",
                "phone": phone,
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["user"]["phone"] == stored

    def test_invalid_phone_rejected(self, client) -> None:
        r = client.post(
            REGISTER,
            json={
                "email": "p@woodcroft.pk",
                "password": "walnut-table-8",
                "full_name": "Test User",
                "phone": "12345",
            },
        )
        assert r.status_code == 422


class TestLogin:
    def test_login_succeeds(self, client) -> None:
        _register(client)
        r = client.post(
            LOGIN, json={"email": "ayesha@woodcroft.pk", "password": "walnut-table-8"}
        )
        assert r.status_code == 200
        assert r.json()["tokens"]["access_token"]
        cookie = r.headers["set-cookie"]
        assert "wc_rt=" in cookie
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie
        assert "Path=/api/v1/auth" in cookie
        assert f"Max-Age={settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60}" in cookie

    def test_wrong_password_rejected(self, client) -> None:
        _register(client)
        r = client.post(
            LOGIN, json={"email": "ayesha@woodcroft.pk", "password": "wrong-password"}
        )
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "invalid_credentials"

    def test_unknown_email_gives_the_same_error(self, client) -> None:
        """Login must not reveal which addresses have accounts."""
        _register(client)
        wrong_pw = client.post(
            LOGIN, json={"email": "ayesha@woodcroft.pk", "password": "wrong-password"}
        )
        no_user = client.post(
            LOGIN, json={"email": "nobody@woodcroft.pk", "password": "wrong-password"}
        )
        assert wrong_pw.status_code == no_user.status_code == 401
        assert wrong_pw.json() == no_user.json()

    def test_lockout_after_repeated_failures(self, client, db) -> None:
        _register(client)
        for _ in range(settings.MAX_FAILED_LOGINS):
            client.post(
                LOGIN, json={"email": "ayesha@woodcroft.pk", "password": "nope-nope-1"}
            )

        # Even the correct password is refused while the account is locked, and
        # the response is the same invalid_credentials as any wrong password, so
        # login cannot be used to discover that an account exists and is locked.
        r = client.post(
            LOGIN, json={"email": "ayesha@woodcroft.pk", "password": "walnut-table-8"}
        )
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "invalid_credentials"
        db_user = db.scalar(select(User).where(User.email == "ayesha@woodcroft.pk"))
        assert db_user.is_locked

    def test_successful_login_clears_failure_count(self, client, db) -> None:
        _register(client)
        client.post(LOGIN, json={"email": "ayesha@woodcroft.pk", "password": "nope-nope-1"})
        client.post(LOGIN, json={"email": "ayesha@woodcroft.pk", "password": "walnut-table-8"})
        user = db.scalar(select(User).where(User.email == "ayesha@woodcroft.pk"))
        assert user.failed_login_count == 0
        assert user.last_login_at is not None


class TestTokenRotation:
    def test_refresh_returns_a_new_pair(self, client) -> None:
        _register(client)
        original = client.cookies.get("wc_rt")
        r = client.post("/api/v1/auth/refresh")
        assert r.status_code == 200
        assert "refresh_token" not in r.json()
        assert client.cookies.get("wc_rt") != original

    def test_refresh_without_cookie_is_rejected(self, client) -> None:
        r = client.post("/api/v1/auth/refresh")
        assert r.status_code == 401

    def test_reusing_a_rotated_token_kills_the_session(self, client) -> None:
        """The reuse detection that makes a stolen refresh token near useless."""
        _register(client)
        original = client.cookies.get("wc_rt")

        rotated = client.post("/api/v1/auth/refresh")
        assert rotated.status_code == 200
        new_token = client.cookies.get("wc_rt")

        # Replaying the old token is treated as theft.
        client.cookies.set("wc_rt", original, path="/api/v1/auth")
        replay = client.post("/api/v1/auth/refresh")
        assert replay.status_code == 401

        # And the replacement is revoked too, because we cannot tell which
        # party is the attacker.
        client.cookies.set("wc_rt", new_token, path="/api/v1/auth")
        after = client.post("/api/v1/auth/refresh")
        assert after.status_code == 401

    def test_garbage_token_rejected(self, client) -> None:
        client.cookies.set("wc_rt", "not-a-token", path="/api/v1/auth")
        r = client.post("/api/v1/auth/refresh")
        assert r.status_code == 401


class TestProtectedRoutes:
    def test_me_requires_a_token(self, client) -> None:
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_me_returns_the_user(self, client) -> None:
        access = _register(client).json()["tokens"]["access_token"]
        r = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}
        )
        assert r.status_code == 200
        assert r.json()["email"] == "ayesha@woodcroft.pk"

    def test_profile_update(self, client) -> None:
        access = _register(client).json()["tokens"]["access_token"]
        r = client.patch(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access}"},
            json={"full_name": "Ayesha K. Khan", "phone": "+923451234567"},
        )
        assert r.status_code == 200
        assert r.json()["full_name"] == "Ayesha K. Khan"
        assert r.json()["phone"] == "03451234567"


class TestPasswordReset:
    def test_forgot_password_does_not_leak_registration(self, client) -> None:
        _register(client)
        known = client.post(
            "/api/v1/auth/forgot-password", json={"email": "ayesha@woodcroft.pk"}
        )
        unknown = client.post(
            "/api/v1/auth/forgot-password", json={"email": "nobody@woodcroft.pk"}
        )
        assert known.status_code == unknown.status_code == 200
        assert known.json() == unknown.json()

    def test_reset_flow_end_to_end(self, client, db) -> None:
        _register(client)
        client.post(
            "/api/v1/auth/forgot-password", json={"email": "ayesha@woodcroft.pk"}
        )

        message = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.template_key == "password_reset"
            )
        )
        assert message is not None
        token = message.context["reset_url"].split("token=")[1]

        r = client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "password": "new-oak-shelf-9"},
        )
        assert r.status_code == 200

        assert client.post(
            LOGIN, json={"email": "ayesha@woodcroft.pk", "password": "new-oak-shelf-9"}
        ).status_code == 200
        assert client.post(
            LOGIN, json={"email": "ayesha@woodcroft.pk", "password": "walnut-table-8"}
        ).status_code == 401

    def test_reset_token_is_single_use(self, client, db) -> None:
        _register(client)
        client.post("/api/v1/auth/forgot-password", json={"email": "ayesha@woodcroft.pk"})
        message = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.template_key == "password_reset"
            )
        )
        token = message.context["reset_url"].split("token=")[1]

        client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "password": "new-oak-shelf-9"},
        )
        second = client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "password": "another-one-11"},
        )
        assert second.status_code == 422


class TestEmailVerification:
    def test_verification_marks_the_account(self, client, db) -> None:
        _register(client)
        message = db.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.template_key == "email_verification"
            )
        )
        token = message.context["verify_url"].split("token=")[1]

        r = client.post("/api/v1/auth/verify-email", json={"token": token})
        assert r.status_code == 200

        user = db.scalar(select(User).where(User.email == "ayesha@woodcroft.pk"))
        assert user.email_verified_at is not None


class TestSessions:
    def test_sessions_listed_and_revocable(self, client) -> None:
        tokens = _register(client).json()["tokens"]
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        listed = client.get("/api/v1/auth/sessions", headers=headers)
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        session_id = listed.json()[0]["session_id"]
        revoked = client.delete(f"/api/v1/auth/sessions/{session_id}", headers=headers)
        assert revoked.status_code == 200

        # The refresh cookie from that session no longer works.
        assert client.post("/api/v1/auth/refresh").status_code == 401


class TestGuestSession:
    def test_guest_token_issued(self, client) -> None:
        r = client.post("/api/v1/auth/guest")
        assert r.status_code == 201
        assert r.json()["guest_token"]


class TestNotificationPreferences:
    def test_defaults_then_update(self, client) -> None:
        access = _register(client).json()["tokens"]["access_token"]
        headers = {"Authorization": f"Bearer {access}"}

        prefs = client.get("/api/v1/auth/me/notifications", headers=headers).json()
        assert prefs["email_order_updates"] is True
        assert prefs["sms_marketing"] is False

        updated = client.patch(
            "/api/v1/auth/me/notifications",
            headers=headers,
            json={"email_marketing": False},
        )
        assert updated.json()["email_marketing"] is False
        assert updated.json()["email_order_updates"] is True


class TestSuppression:
    def test_marketing_optout_suppresses_but_transactional_still_sends(
        self, client, db
    ) -> None:
        """Opting out of marketing must never block a password reset."""
        access = _register(client).json()["tokens"]["access_token"]
        headers = {"Authorization": f"Bearer {access}"}
        client.patch(
            "/api/v1/auth/me/notifications",
            headers=headers,
            json={"email_marketing": False},
        )

        from app.services import notifications

        user = db.scalar(select(User).where(User.email == "ayesha@woodcroft.pk"))
        marketing = notifications.email(
            db, "abandoned_cart", user.email, user=user,
            context={"cart_url": "x", "item_count": 1, "cart_value_paisa": 100},
        )
        assert marketing.status is NotificationStatus.SUPPRESSED

        transactional = notifications.email(
            db, "password_changed", user.email, user=user
        )
        assert transactional.status is NotificationStatus.SENT
