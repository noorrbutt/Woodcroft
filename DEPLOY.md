# Deploying Woodcroft

Woodcroft runs on managed, serverless infrastructure: the API and the storefront
are separate deployments, Postgres and Redis are managed services, and images are
served from a CDN. The live deployment uses Vercel, Neon, Upstash and Cloudinary,
but nothing in the application is tied to those vendors — the whole adaptation is
driven by the environment variables listed below.

| Piece | What it is | Source |
|---|---|---|
| API | FastAPI as a serverless function | `backend/`, `backend/vercel.json` |
| Storefront | The built React bundle, static | `frontend/`, `frontend/vercel.json` |
| Database | Managed PostgreSQL 18, pooled endpoint | `DATABASE_URL` |
| Rate-limit store | Managed Redis | `RATELIMIT_STORAGE_URI` |
| Media | CDN delivery prefix, Cloudinary uploads | `MEDIA_URL`, `CLOUDINARY_*` |
| Job queue | `job_queue` table, drained on a schedule | `GET /api/cron/run-jobs` |

## What serverless changes

There is no long-lived process and the filesystem is read-only, so three parts of
the design adapt. All three are configuration, not code paths:

| Concern | Single long-running process | Serverless |
|---|---|---|
| Background worker | asyncio task polling the queue (`ENABLE_BACKGROUND_WORKER=true`) | `false`, and a scheduler calls `/api/cron/run-jobs` |
| Rate limiting | in-process memory | `RATELIMIT_STORAGE_URI` at Redis, so limits are shared across instances |
| Media | local disk under `MEDIA_ROOT` | `MEDIA_URL` at the CDN; admin uploads go to Cloudinary |

---

## 1. Provision the database

Create a PostgreSQL 18 database and install the extensions the schema needs:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS btree_gin;
```

Two things to get right:

- **Use the pooled connection endpoint.** The engine already disables psycopg's
  server-side prepared statements (`prepare_threshold=None`), which is what makes
  a transaction-mode pooler safe.
- **PostgreSQL 18 or newer.** Primary keys default to the native `uuidv7()`. On an
  older server, install an RFC 9562 pl/pgSQL `uuidv7()` shim before migrating; it
  is behaviourally identical.

## 2. Configure the API

Set these on the API deployment. Everything else has a working default; see
[`.env.example`](.env.example) for the full list.

```
APP_ENV=production
DEBUG=false
SECRET_KEY=<48+ random chars>        # python -c "import secrets;print(secrets.token_urlsafe(48))"
DATABASE_URL=postgresql+psycopg://...   # pooled endpoint, +psycopg driver
PUBLIC_URL=https://your-domain.pk    # https, no trailing slash, NOT localhost
CORS_ORIGINS=https://your-domain.pk
ENABLE_BACKGROUND_WORKER=false
RATELIMIT_STORAGE_URI=rediss://default:<token>@<host>:6379
MEDIA_URL=https://res.cloudinary.com/<cloud>/image/upload
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
CRON_SECRET=<random string>
EMAIL_DRIVER=outbox                  # 'smtp' once real SMTP_* credentials exist
```

With `APP_ENV=production` the app **fail-closes** at startup: it refuses to boot
with a placeholder or short `SECRET_KEY`, with `DEBUG=true`, or with a localhost
CORS origin, and it serves `/docs`, `/redoc` and `/openapi.json` as 404.

## 3. Migrate and seed, from your machine

Run these against the production database from somewhere that can reach it — not
from the serverless function, which would time out.

```powershell
cd backend
$env:DATABASE_URL = "postgresql+psycopg://...";  $env:APP_ENV = "production"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.seed --append
```

In `APP_ENV=production` the seeder lays down only store settings, categories,
products, promotions, legal pages and FAQ. It **skips** every demo account,
fabricated order, review and testimonial — those exist in development only.

## 4. Create the real admin

There are no default logins in production.

```powershell
$env:WOODCROFT_ADMIN_EMAIL = "you@your-domain.pk"
$env:WOODCROFT_ADMIN_PASSWORD = "<strong 10+ char password>"
.\.venv\Scripts\python.exe -m scripts.create_admin
```

## 5. Deploy the storefront

The frontend is a static bundle (`npm run build`) plus two pieces of host
configuration, both in [`frontend/vercel.json`](frontend/vercel.json):

Set `VITE_WHATSAPP_NUMBER` in the storefront build environment to enable the
product inquiry, product share, and cart WhatsApp buttons. Use digits only,
including the country code (for example `923001234567`), with no leading `+`.
Leave it unset or empty to hide the buttons.

- **Rewrites.** `/api/*` proxies to the API deployment, and everything else falls
  back to `index.html` so client routing survives a hard refresh of
  `/product/...` or `/admin/...`. Keeping the API on the same origin is what lets
  the client work with no base URL and no credentialed CORS.
- **Security headers,** including the storefront CSP. The API sets its own strict
  CSP on JSON responses; this one covers the HTML shell that runs the bundle.

If you change the inline theme script in `frontend/index.html`, its `sha256-`
hash in the `script-src` directive must be updated to match, or the script is
blocked and the page loads with a flash of the wrong theme.

## 6. Schedule the job queue

With no persistent worker, a scheduler drains the queue: reservation sweeps,
abandoned-cart and back-in-stock notices, scheduled publishing, flash sales.

```
GET https://<api-host>/api/cron/run-jobs
Authorization: Bearer <CRON_SECRET>
```

`backend/vercel.json` declares this as a daily cron. Any scheduler works — the
secret is also accepted as `?key=`. Handlers are idempotent, so an occasional
double-run is harmless. Without `CRON_SECRET` set, the endpoint returns 503 and
the queue never drains.

## 7. Verify

```
curl -f https://your-domain.pk/                       # storefront loads
curl -f https://<api-host>/health                     # {"status":"ok"}
curl -f https://<api-host>/readyz                     # {"status":"ready"} — proves the DB is reachable
curl -i https://<api-host>/docs                       # expect 404 in production
```

Then sign in as the admin, place a test COD order, and confirm it appears under
Admin → Orders and in the activity bell.

---

## Before you go live

- [ ] `SECRET_KEY` is strong and unique; `PUBLIC_URL` and `CORS_ORIGINS` are the
      real https origin.
- [ ] `RATELIMIT_STORAGE_URI` points at Redis. Without it every function instance
      keeps its own buckets and the limits multiply.
- [ ] `CRON_SECRET` is set and the schedule is firing.
- [ ] Admin created via `create_admin`; no demo logins exist.
- [ ] Every `[PLACEHOLDER]` in the legal pages (Admin → Content) is filled in,
      with a real business name, address and NTN, and reviewed by a lawyer.
- [ ] The tax label matches your sales-tax (STRN) status.
- [ ] Image licences confirmed — see [`NOTICES.md`](NOTICES.md).
- [ ] Database backups are on.

## Notes

- **Email and SMS.** The default `outbox` driver renders every message and stores
  it (Admin → Notifications) without sending. Nothing goes out until
  `EMAIL_DRIVER=smtp` and the `SMTP_*` credentials are set. The row is written
  either way, so the outbox doubles as an audit trail.
- **Running it as a long-lived process instead.** If you deploy the API to a VM or
  a container platform rather than a function, leave
  `ENABLE_BACKGROUND_WORKER=true` and the worker runs in the app's lifespan. Run
  exactly one process in that case: the worker would otherwise fire each job once
  per process, and the in-memory rate limiter would multiply its limits. Scale out
  by setting `RATELIMIT_STORAGE_URI` first.
