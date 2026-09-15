"""Seed CLI.

    python -m app.seed --fresh            wipe and rebuild everything
    python -m app.seed --append           add anything missing, touch nothing else
    python -m app.seed --fresh --no-images   skip plate generation, much faster

Image generation is the slow part by a wide margin, so --no-images exists for
when you are iterating on data rather than looking at the storefront.
"""

from __future__ import annotations

import argparse
import sys
import time

from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.seed.engagement import seed_engagement
from app.seed.orders import seed_orders
from app.seed.people import DEMO_ACCOUNTS, seed_people
from app.seed.promotions import seed_promotions
from app.seed.runner import Seeder


def _guard_destructive() -> None:
    """Refuse to drop a production database, or an unexpected one.

    reset_schema runs DROP SCHEMA public CASCADE against whatever DATABASE_URL
    points at. That is unrecoverable, so require an explicit opt-in and never
    allow it in production.
    """
    import os

    from sqlalchemy.engine import make_url

    if settings.is_production:
        raise SystemExit(
            "Refusing to reset the schema: APP_ENV is production. A destructive "
            "seed must never run against production data."
        )
    if os.environ.get("WOODCROFT_ALLOW_DESTRUCTIVE_SEED") == "yes":
        return
    db_name = make_url(settings.DATABASE_URL).database or "?"
    print(f"\nThis will DROP and rebuild the schema of database '{db_name}'.")
    print("Everything in it will be permanently deleted.")
    answer = input(f"Type the database name ('{db_name}') to continue: ").strip()
    if answer != db_name:
        raise SystemExit("Cancelled: the name did not match.")


def reset_schema() -> None:
    """Drop and rebuild the schema, then re-stamp Alembic.

    Faster and more reliable than deleting rows in dependency order, and it
    guarantees the result matches the models exactly.
    """
    import app.models  # noqa: F401
    from app.db.base import Base

    _guard_destructive()

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        for extension in ("pg_trgm", "citext", "unaccent", "btree_gin"):
            conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS {extension}"))

    Base.metadata.create_all(engine)

    # Stamp the migration head so `alembic upgrade` is a no-op afterwards
    # rather than trying to recreate tables that already exist. Anchored on the
    # backend directory, not the media path, which may be an unrelated mounted
    # volume in production.
    from alembic.config import Config

    from alembic import command
    from app.core.config import BACKEND_DIR

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.stamp(cfg, "head")


def _advance_number_sequences(db) -> None:
    """Set each reference-number sequence past the highest seeded value.

    Order numbers are WC-YYYY-NNNNNN and ticket numbers WC-TKT-NNNN. Real
    checkouts and contact requests mint from these sequences, so they must start
    above the seeded rows or the UNIQUE constraint would reject the first one.
    """
    db.execute(
        text(
            "SELECT setval('order_number_seq', COALESCE((SELECT MAX("
            "CAST(split_part(order_number, '-', 3) AS INTEGER)) FROM \"order\"), 1))"
        )
    )
    db.execute(
        text(
            "SELECT setval('ticket_number_seq', COALESCE((SELECT MAX("
            "CAST(split_part(ticket_number, '-', 3) AS INTEGER)) "
            "FROM support_ticket WHERE ticket_number ~ '^WC-TKT-[0-9]+$'), 999))"
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="app.seed")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fresh", action="store_true",
                      help="drop everything and rebuild")
    mode.add_argument("--append", action="store_true",
                      help="add what is missing, leave the rest alone")
    parser.add_argument("--no-images", action="store_true",
                        help="skip plate generation")
    parser.add_argument("--orders", type=int, default=260,
                        help="how many orders to create")
    args = parser.parse_args()

    if not args.fresh and not args.append:
        parser.error("choose --fresh or --append")

    started = time.perf_counter()
    print(f"\nSeeding Woodcroft ({'fresh' if args.fresh else 'append'})")
    print(f"Database: {settings.DATABASE_URL.split('@')[-1]}")
    if args.no_images:
        print("Images:   skipped")
    print()

    if args.fresh:
        print("Resetting schema")
        reset_schema()

    db = SessionLocal()
    try:
        seeder = Seeder(db, with_images=not args.no_images)

        print("Store configuration")
        seeder.seed_settings()

        print("Catalogue")
        seeder.seed_categories()
        seeder.seed_products()

        # Demo accounts (incl. the known-password admin) and fabricated orders
        # must never seed into production. Use scripts.create_admin for the real
        # admin instead.
        if not settings.is_production:
            print("People")
            seed_people(seeder)

        print("Promotions")
        seed_promotions(seeder)

        if not settings.is_production:
            print("Orders")
            seed_orders(seeder, count=args.orders)

        print("Content and pages")
        seed_engagement(seeder)

        # Advance the reference-number sequences past the seeded rows so the
        # first real order or ticket does not mint a number that already exists.
        _advance_number_sequences(db)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    elapsed = time.perf_counter() - started
    print(f"\nDone in {elapsed:.1f}s\n")
    if not settings.is_production:
        print("Sign in with:")
        for email, _name, role, password in DEMO_ACCOUNTS:
            print(f"  {role.value:9} {email:26} {password}")
        print()
        print("  Storefront  http://localhost:5173")
        print("  Admin       http://localhost:5173/admin")
        print("  API docs    http://localhost:8000/docs")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
