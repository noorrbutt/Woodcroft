# Woodcroft

[![CI](https://github.com/noorrbutt/Woodcroft/actions/workflows/ci.yml/badge.svg)](https://github.com/noorrbutt/Woodcroft/actions/workflows/ci.yml)

A production e-commerce platform for a premium handcrafted wood furniture and
woodware retailer in Pakistan. FastAPI and PostgreSQL on the back, React 19 and
Vite on the front, with a customer storefront and a full admin panel served by a
single API.

Prices are in PKR, addresses and phone validation are Pakistani, GST works both
inclusive and exclusive, and Cash on Delivery is the live payment method.

| | |
|---|---|
| Storefront | https://woodcroft.vercel.app |
| Admin panel | https://woodcroft.vercel.app/admin |

---
## sneak peek to the admin panel
<img width="2548" height="1191" alt="image" src="https://github.com/user-attachments/assets/ee4e6a6c-626d-4478-a12c-f49eaee652e8" />
<img width="2548" height="1191" alt="image" src="https://github.com/user-attachments/assets/1756f34c-00f0-4de5-8793-fb8dfd3c5d43" />

---


## What is in the box

**Storefront.** Nested categories, 115 products across 403 variants, faceted
listing, full-text search with autocomplete and did-you-mean, product detail with
a variant matrix and live personalisation pricing, cart, Cash on Delivery
checkout, order tracking, wishlist, compare, reviews, loyalty points, referrals, a
journal, policy pages, FAQ and contact.

**Admin.** A dashboard with a revenue chart and an attention queue, order
management with status changes, partial shipments, refunds and CSV export, product
and inventory management with an append-only stock ledger, customers with lifetime
value and segments, coupons, gift cards, a live flash sale, review moderation, a
CMS for pages, blog, banners and FAQ, a readable notification outbox, an audit log,
and store settings including the tax-mode switch.

**Dark mode** across both panels, applied before first paint so there is no flash.

---

## Tech stack

| Layer | Choices |
|---|---|
| Backend | FastAPI, SQLAlchemy 2.0 (typed models), Alembic, Pydantic v2, psycopg 3, PyJWT, argon2-cffi, slowapi, Jinja2, Pillow, bleach |
| Frontend | React 19, Vite 7, TypeScript, Tailwind CSS v4, TanStack Query, Zustand, react-router 7, Recharts, DOMPurify |
| Data and services | PostgreSQL 18, Redis (rate limiting), a media CDN, and a DB-backed job queue (no Celery, no broker) |

The backend is layered strictly: routers validate, services hold the business
logic, and typed models own the data. A single pricing engine is the only code
that computes money, so cart, checkout, order creation and the seeder cannot
disagree.

---

## Quick start (local)

You need PostgreSQL 18 running, Python 3.12 or newer, and Node 20.19 or newer.
PostgreSQL 18 matters locally because the schema uses the native `uuidv7()`
function for primary keys.

```powershell
git clone https://github.com/noorrbutt/Woodcroft.git
cd Woodcroft
.\scripts\bootstrap.ps1
.\scripts\run_all.ps1
```

`bootstrap.ps1` creates the database and role, builds the virtual environment,
installs dependencies, applies migrations and seeds the store. It is safe to run
again.

Seeding generates around 350 product images procedurally, which takes a few
minutes. While you are iterating on data rather than looking at the storefront,
skip them:

```powershell
.\scripts\bootstrap.ps1 -NoImages
```

| | |
|---|---|
| Storefront | http://localhost:5173 |
| Admin panel | http://localhost:5173/admin |
| API docs | http://localhost:8000/docs |

### Sign in (development seed only)

The seed creates demo accounts for local work. These never ship to production,
where the admin is created separately (see Deployment).

| Role | Email | Password |
|---|---|---|
| Admin | `admin@woodcroft.pk` | `woodcroft-admin` |
| Staff | `staff@woodcroft.pk` | `woodcroft-staff` |
| Customer | `customer@woodcroft.pk` | `woodcroft-demo` |

Every seeded customer uses `woodcroft-demo`.

---

## How it is put together

```
backend/
  app/
    api/v1/        routers: auth, catalog, checkout, content, admin
    core/          config, security, permissions, money, errors, deps
    models/        SQLAlchemy models, 78 tables across 11 domains
    services/      pricing, catalog, auth, notifications, media
    seed/          ordered, idempotent seed modules
    workers/       DB-backed job queue and its handlers
  alembic/         migrations
  tests/
frontend/
  src/
    routes/        storefront pages and the lazy-loaded admin tree
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

**One pricing engine.** `app/services/pricing.py` is the only code that computes
money. Cart, checkout, order creation and the seeder all call it, so they cannot
disagree. If the seeder invented its own totals, the revenue dashboard and the
invoices would drift apart while both looked perfectly plausible.

**The browser never decides prices.** Checkout sends variant ids, quantities and
personalisation text. The server looks up the real prices, reads surcharges off
the option definitions, and charges that.

**Order lines are snapshots.** `order_item` stores the product name, SKU, unit
price, tax and discount as they were at purchase. An invoice regenerated in three
years produces the same numbers even if the product has since been repriced,
renamed or deleted.

**Overselling is prevented by the database,** not by application code.
`stock_level` carries its own constraints and sellable quantity has exactly one
definition, and contended rows are taken with `SELECT ... FOR UPDATE` during
checkout so two people cannot both buy the last unit.

**Order locks avoid the joined-user trap.** The `Order.user` relationship loads
with `selectin`, not a join. A joined outer-join to the nullable user table makes
Postgres refuse `SELECT ... FOR UPDATE` on the order, which is the kind of thing
that only shows up the first time someone issues a refund.

**Notifications go to an outbox.** With no SMTP configured, every email and SMS is
rendered and stored, readable in Admin then Notifications. Setting
`EMAIL_DRIVER=smtp` also sends over the wire; the row is written either way, which
doubles as an audit trail.

**Background jobs use a database queue,** because there is no broker. Claims use
`FOR UPDATE SKIP LOCKED`, so a job runs exactly once even across several workers.

**Design tokens must stay in `@theme inline`.** A plain `@theme` block resolves
`var()` once at `:root` and bakes the light value into every utility, so dark mode
silently stops working with no error.

---

## Deployment

The live deployment is serverless: the API and the storefront are separate
deployments on Vercel, Postgres is Neon, Redis is Upstash, and images come off a
CDN. None of that is baked in — the whole adaptation is environment variables.

Serverless has no long-lived process and a read-only filesystem, so three parts of
the design adapt:

| Concern | Long-running process | Serverless |
|---|---|---|
| Background worker | asyncio task polling the job queue | `ENABLE_BACKGROUND_WORKER=false`; a secret-guarded `GET /api/cron/run-jobs` drains the queue on a schedule |
| Rate limiting | in-process memory | `RATELIMIT_STORAGE_URI` points at Redis, so limits are shared across instances |
| Media | local disk under `MEDIA_ROOT` | `MEDIA_URL` points at the CDN; admin uploads push to Cloudinary |

In `APP_ENV=production` the app fail-closes on a weak `SECRET_KEY`, `DEBUG=true`,
or a localhost CORS origin, and it turns the API docs off. The seed lays down only
store settings, categories, products, promotions, legal pages and FAQ — never demo
accounts or fabricated orders — and the real admin is created separately with
`python -m scripts.create_admin`.

See [`DEPLOY.md`](DEPLOY.md) for the full runbook.

---

## Configuration

Everything lives in `backend/.env`, documented in `.env.example`. The settings you
are most likely to touch:

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | local dev URL | Must use `+psycopg`. A bare `postgresql://` resolves to psycopg2 and fails. |
| `TAX_MODE` | `inclusive` | Also editable at runtime in Admin then Settings. |
| `EMAIL_DRIVER` | `outbox` | `smtp` to send for real. |
| `MEDIA_URL` | `/media` | An absolute CDN URL in production; the local static mount is skipped when it is remote. |
| `RATELIMIT_STORAGE_URI` | empty | Empty is in-memory. Point at Redis on serverless. |
| `SEED_IMAGE_MODE` | `generated` | `curated` fetches photographs and needs `PEXELS_API_KEY`. |
| `ENABLE_BACKGROUND_WORKER` | `true` | Off during tests and on serverless. |
| `VITE_WHATSAPP_NUMBER` | empty | Storefront build-time setting; digits only with country code, no `+`. Empty hides WhatsApp buttons. |

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

## Testing

`scripts\test.ps1` runs the pytest suite, with the pricing engine and stock
reservation logic covered most heavily since everything downstream depends on
them. The live deployment was also verified end to end: every endpoint exercised,
the full Cash on Delivery purchase flow, admin CRUD across every content type,
coupon and gift-card validation, rate limiting, and the security headers.

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

No multi-warehouse or regional stock, no supplier tracking, no multi-currency, no
split payment, no delivery time slots, no store locator, no customer
impersonation. Gift cards are implemented; only splitting a single payment across a
gift card and another method is not.

Carrier tracking numbers, courier selection and the status timeline are real, but
there is no live integration with TCS or Leopards, because that needs credentials
that do not exist here.

---

## Troubleshooting

**`psql` is not recognised.** The scripts resolve it at
`C:\Program Files\PostgreSQL\18\bin`. If yours is elsewhere, add it to `PATH`.

**`must be owner of schema public`.** The app role needs to own the schema so the
seeder can rebuild it. `scripts\db_create.ps1` does this; re-run it.

**Unicode errors in the console.** The scripts set `PYTHONUTF8=1` because the
Windows console defaults to cp1252 and the seed data contains `Rs` and Pakistani
names. If you run Python directly, set it yourself.

**Dark mode does nothing.** Check that semantic tokens are in `@theme inline` and
not a plain `@theme` block. See `frontend/src/styles/theme.css`.

**A refund or other admin action returns a 500 about `FOR UPDATE`.** An order
relationship has reverted to joined loading. Order queries that lock rows must not
outer-join the nullable user table. See `app/models/order.py`.
