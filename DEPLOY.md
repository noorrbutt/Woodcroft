# Deploying Woodcroft

Woodcroft ships as a Docker Compose stack: **db** (PostgreSQL 18), **api**
(FastAPI), **worker** (background jobs), and **web** (the built React app served
by nginx, which also reverse-proxies `/api` and `/media` to the api). The SPA
calls the API on the same origin, so **everything must sit behind one host**.

## Prerequisites
- A Linux host with Docker + Docker Compose.
- A domain pointed at the host, and TLS (see step 6). COD name/address/phone and
  login tokens travel in the clear without HTTPS - do not skip it.

## 1. Configure secrets
From the repo root, create `./.env` (copy from `.env.example`) with **at least**:

```
SECRET_KEY=<48+ random chars>      # python -c "import secrets;print(secrets.token_urlsafe(48))"
DB_PASSWORD=<strong password>      # not 'woodcroft'
PUBLIC_URL=https://your-domain.pk  # https, no trailing slash, NOT localhost
EMAIL_DRIVER=outbox                # emails are written to the DB outbox until real SMTP is set
```

Compose refuses to start without `SECRET_KEY`, `DB_PASSWORD` and `PUBLIC_URL`.
The api boots in `APP_ENV=production` (set by compose), which **fail-closes**:
it will not start with a placeholder `SECRET_KEY`, `DEBUG=true`, or a localhost
CORS origin, and it turns `/docs`, `/redoc` and `/openapi.json` off.

## 2. Build and start
```
docker compose up -d --build
```

## 3. Apply migrations
```
docker compose exec api python -m alembic upgrade head
docker compose exec api python -m alembic current   # expect the latest head
```
(The db container auto-installs the required Postgres extensions on first boot.)

## 4. Seed the essential store data (NO demo data in production)
```
docker compose exec api python -m app.seed --append
```
In production this seeds only store settings, categories, products, promotions,
the **legal pages** and FAQ. It **skips** all demo accounts, fabricated orders,
reviews, testimonials and the known-password admin - those exist in dev only.

## 5. Create the real admin (securely - no hardcoded password)
```
docker compose exec \
  -e WOODCROFT_ADMIN_EMAIL=you@your-domain.pk \
  -e WOODCROFT_ADMIN_PASSWORD='<strong 10+ char password>' \
  api python -m scripts.create_admin
```

## 6. Put TLS in front
Terminate HTTPS with Caddy, nginx+certbot, a cloud load balancer, or Cloudflare,
forwarding `443 -> web:80`. Keep it single-origin so `/api` and `/media` still
proxy correctly. **Never publish the api's port 8000 directly.** Set
`PUBLIC_URL`/`CORS_ORIGINS` to the https origin.

## 7. Verify
```
curl -f https://your-domain.pk/          # storefront loads
curl -f https://your-domain.pk/api/v1/health   # or /readyz on the api
```
- Confirm `/docs` and `/openapi.json` return 404 (docs are off in production).
- Sign in as the admin, place a test COD order, confirm it appears in Admin →
  Orders and the activity bell.

## Before you go live - checklist
- [ ] `./.env` has strong, unique `SECRET_KEY` and `DB_PASSWORD`; `PUBLIC_URL` is https.
- [ ] TLS terminating in front; api port 8000 not exposed.
- [ ] Admin created via `create_admin` (no demo logins exist in prod).
- [ ] Image licences: product photos, category images and the hero are from
      Pexels (free for commercial use); the logo is owner-supplied - confirm you
      own it. See `NOTICES.md`. (No unlicensed images ship.)
- [ ] Fill every `[PLACEHOLDER]` in the legal pages (Admin → Content) and have a
      lawyer review them; add real business name, address, NTN.
- [ ] Reconcile the tax label with your sales-tax (STRN) status.
- [ ] Back up the `db-data` volume regularly.

## Notes
- **Email/SMS**: default `EMAIL_DRIVER=outbox` writes rendered messages to the DB
  (Admin → Notifications) - nothing is actually sent until real SMTP/SMS creds are
  configured. Set `EMAIL_DRIVER=smtp` + `SMTP_*` when ready.
- **Background worker**: runs as its own service (abandoned-cart, back-in-stock,
  scheduled publish). Keep it to one replica.
- **Scaling**: the rate limiter is in-process; keep `uvicorn --workers 1` per api
  container (scale by adding a shared Redis `storage_uri`, not more workers).
