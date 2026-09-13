# Woodcroft

A complete e-commerce platform for a premium handcrafted wood furniture and
woodware retailer in Pakistan. FastAPI and PostgreSQL 18 on the back, React 19
and Vite on the front, with a customer storefront and an admin panel.

Prices are in PKR, addresses and phone validation are Pakistani, GST is handled
both inclusive and exclusive, and Cash on Delivery is the live payment method.

---

## Quick start

You need PostgreSQL 18 running, Python 3.12 or newer, and Node 20.19 or newer.

```powershell
git clone https://github.com/noorrbutt/Woodcroft.git
cd Woodcroft
.\scripts\bootstrap.ps1
.\scripts\run_all.ps1
```

`bootstrap.ps1` creates the database and role, builds the virtual environment,
installs everything, applies migrations and seeds the store. It is safe to run
again.

Seeding generates around 350 product images procedurally, which takes a few
minutes. While you are iterating on data rather than looking at the storefront:

```powershell
.\scripts\bootstrap.ps1 -NoImages
```

| | |
|---|---|
| Storefront | http://localhost:5173 |
| Admin panel | http://localhost:5173/admin |
| API docs | http://localhost:8000/docs |

### Sign in

| Role | Email | Password |
|---|---|---|
| Admin | `admin@woodcroft.pk` | `woodcroft-admin` |
| Staff | `staff@woodcroft.pk` | `woodcroft-staff` |
| Customer | `customer@woodcroft.pk` | `woodcroft-demo` |

Every seeded customer uses `woodcroft-demo`.

---

## What is in the box

**Storefront.** Nested categories, 115 products across 400 variants, faceted
listing, full-text search with autocomplete and did-you-mean, product detail
with a variant matrix and live personalisation pricing, cart, Cash on Delivery
checkout, order tracking, wishlist, compare, reviews, loyalty points,
referrals, a journal, policy pages, FAQ and contact.

**Admin.** Dashboard with a revenue chart and attention queue, order management
with status changes and CSV export, products, an inventory ledger with
adjustments, customers with lifetime value and segments, review moderation, a
notification outbox you can read, an audit log, and store settings including
the tax mode switch.

**Dark mode** across both panels, applied before first paint so there is no
flash.

---

## How it is put together

```
backend/
  app/
    api/v1/        routers: auth, catalog, checkout, content, admin
    core/          config, security, permissions, money, errors, deps
    models/        SQLAlchemy models, 78 tables in 9 domains
    services/      pricing, catalog, auth, notifications, media
    seed/          ordered, idempotent seed modules
    workers/       DB-backed job queue and its handlers
  alembic/         migrations
  tests/
frontend/
  src/
    routes/        storefront pages and the lazy admin tree
    features/      cart, auth, catalog
    components/    layout and UI primitives
    lib/           API client, formatting, types
    styles/        design tokens and base layer
scripts/           PowerShell helpers
```

### Things worth knowing before you change anything

**All money is an integer number of paisa.** 1 PKR = 100 paisa, stored in
`BIGINT`. Never a float, anywhere. `app/core/money.py` owns the arithmetic and
`format_pkr` owns the display.

**One pricing engine.** `app/services/pricing.py` is the only code that
computes money. Cart, checkout, order creation and the seeder all call it, so
they cannot disagree with each other. If the seeder invented its own totals,
the revenue dashboard and the invoices would drift apart while both looked
perfectly plausible.

**The browser never decides prices.** Checkout sends variant ids, quantities
and personalisation text. The server looks up the real prices, reads surcharges
off the option definitions and charges that.

**Order lines are snapshots.** `order_item` stores the product name, SKU, unit
price, tax and discount as they were at purchase. An invoice regenerated in
three years produces the same numbers even if the product has since been
repriced, renamed or deleted.

**Overselling is prevented by the database,** not by application code.
`stock_level` has `CHECK (reserved <= on_hand)` and `available` is a generated
column, so there is exactly one definition of sellable quantity and no way to
contradict it.

**Notifications go to an outbox.** With no SMTP configured, every email and SMS
is rendered and stored, readable in Admin → Notifications. Setting
`EMAIL_DRIVER=smtp` additionally sends over the wire; the row is written either
way, which doubles as an audit trail.

**Background jobs use a database queue,** because there is no Redis. Claims use
`FOR UPDATE SKIP LOCKED`, so a job runs exactly once.

**Design tokens must stay in `@theme inline`.** A plain `@theme` block resolves
`var()` once at `:root` and bakes the light value into every utility, so dark
mode silently stops working with no error.

---

## Common tasks

```powershell
.\scripts\test.ps1                 # run the test suite
.\scripts\seed.ps1 -NoImages       # reseed quickly
.\scripts\run_backend.ps1          # API only
.\scripts\run_frontend.ps1         # storefront only
```

Preview the image generator without a full seed:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.services.media --preview
```

Create a migration after changing a model:

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "what changed"
.\.venv\Scripts\python.exe -m alembic upgrade head
```

---

## Configuration

Everything lives in `backend/.env`, documented in `.env.example`. The settings
you are most likely to touch:

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://woodcroft:woodcroft@localhost:5432/woodcroft_dev` | Must use `+psycopg`. A bare `postgresql://` resolves to psycopg2 and fails. |
| `TAX_MODE` | `inclusive` | Also editable at runtime in Admin → Settings. |
| `EMAIL_DRIVER` | `outbox` | `smtp` to send for real. |
| `SEED_IMAGE_MODE` | `generated` | `curated` fetches photographs, needs `UNSPLASH_ACCESS_KEY`. |
| `ENABLE_BACKGROUND_WORKER` | `true` | Off during tests. |

---

## Payments

Cash on Delivery is fully implemented: availability by shipping zone, a
configurable surcharge, an order-value ceiling per zone, and the cash amount
carried on the shipment.

JazzCash and Easypaisa exist as `payment_method` rows with `is_enabled = false`
and render in checkout as deliberately "coming soon" rather than being hidden.
Enabling them later is a settings change plus a provider implementation, not a
checkout rewrite.

---

## What is deliberately not built

No multi-warehouse or regional stock, no supplier tracking, no multi-currency,
no split payment, no delivery time slots, no store locator, no customer
impersonation. Gift cards are implemented; only splitting payment across a gift
card and another method is not.

Carrier tracking numbers, courier selection and the status timeline are real,
but there is no live integration with TCS or Leopards, because that needs
credentials that do not exist here.

---

## Troubleshooting

**`psql` is not recognised.** The scripts resolve it at
`C:\Program Files\PostgreSQL\18\bin`. If yours is elsewhere, add it to `PATH`.

**`must be owner of schema public`.** The app role needs to own the schema so
the seeder can rebuild it. `scripts\db_create.ps1` does this; re-run it.

**Unicode errors in the console.** The scripts set `PYTHONUTF8=1` because the
Windows console defaults to cp1252 and the seed data contains `Rs` and
Pakistani names. If you run Python directly, set it yourself.

**Dark mode does nothing.** Check that semantic tokens are in `@theme inline`
and not a plain `@theme` block. See `frontend/src/styles/theme.css`.
