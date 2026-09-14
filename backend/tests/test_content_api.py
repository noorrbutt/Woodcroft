"""Content and account endpoints, focused on the abuse surface."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.deps import get_db
from app.main import app


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestWishlistScoping:
    def test_anonymous_delete_cannot_remove_a_users_row(self, client, db) -> None:
        # A signed-in user's wishlist row: user_id set, guest_session_id NULL.
        user_id = db.execute(
            text(
                'INSERT INTO "user" (email, full_name, password_hash, role) '
                "VALUES ('wish@test.pk', 'Wish', 'x', 'customer') RETURNING id"
            )
        ).scalar_one()
        category = db.execute(
            text("INSERT INTO category (name, slug, path, depth) "
                 "VALUES ('D', 'd', 'd', 0) RETURNING id")
        ).scalar_one()
        product_id = db.execute(
            text("INSERT INTO product (category_id, name, slug, base_price_paisa, status) "
                 "VALUES (:c, 'Chair', 'chair', 500000, 'active') RETURNING id"),
            {"c": category},
        ).scalar_one()
        db.execute(
            text("INSERT INTO wishlist_item (user_id, product_id) VALUES (:u, :p)"),
            {"u": user_id, "p": product_id},
        )
        db.flush()

        # No auth, no guest token: an anonymous caller must not fall into the
        # guest branch and delete this row.
        r = client.delete(f"/api/v1/wishlist/{product_id}")
        assert r.status_code == 200

        survived = db.execute(
            text("SELECT count(*) FROM wishlist_item WHERE user_id = :u"),
            {"u": user_id},
        ).scalar_one()
        assert survived == 1
