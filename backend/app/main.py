"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1 import admin as admin_router
from app.api.v1 import admin_content as admin_content_router
from app.api.v1 import auth as auth_router
from app.api.v1 import catalog as catalog_router
from app.api.v1 import checkout as checkout_router
from app.api.v1 import content as content_router
from app.api.v1 import engagement as engagement_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.ratelimit import limiter

logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format="%(levelname)-5s %(name)s: %(message)s",
)
log = logging.getLogger("woodcroft")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start and stop the background worker alongside the app.

    There is no Redis or Celery here, so the worker is an asyncio task in this
    same process, polling the job_queue table. It can be turned off with
    ENABLE_BACKGROUND_WORKER, which is what the test suite does.
    """
    task: asyncio.Task | None = None

    if settings.ENABLE_BACKGROUND_WORKER:
        from app.workers.runner import run_worker

        task = asyncio.create_task(run_worker())
        log.info("background worker started")

    yield

    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        log.info("background worker stopped")


app = FastAPI(
    title="Woodcroft API",
    description=(
        "Handcrafted wood furniture and woodware, built for Pakistan. "
        "All money is an integer number of paisa; 1 PKR = 100 paisa."
    ),
    version="1.0.0",
    lifespan=lifespan,
    # The interactive docs and the OpenAPI schema map every endpoint and its
    # request shape, including admin routes. Keep them out of production.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    # Auth is a Bearer token in the Authorization header, not cookies, so
    # credentialed CORS is unnecessary and needlessly permissive.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Guest-Token"],
)

register_exception_handlers(app)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request id for correlation, and set baseline security headers.

    The request id is echoed back and included in the 500 envelope so a support
    report can be traced to one log line. The headers close off clickjacking,
    MIME sniffing and referrer leakage by default rather than relying on the
    deployment to remember. The API only ever returns JSON, so a strict CSP is
    safe here; the storefront's own CSP is set at nginx.
    """
    request.state.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
    )
    # Strict CSP on API responses only; the docs pages (dev only) load their own
    # assets and would break under default-src 'none'.
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):
        response.headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
        )
    if settings.is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response



@app.exception_handler(RateLimitExceeded)
async def _rate_limited(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "rate_limited",
                "message": "Too many requests. Please slow down and try again.",
            }
        },
    )


# Product images and generated media are served straight off disk in dev. When
# MEDIA_URL is an absolute URL (Cloudinary in production) there is nothing to
# mount - the serverless filesystem is ephemeral and images are delivered from
# the CDN instead, so skip the static mount entirely.
if not settings.media_is_remote:
    app.mount(
        settings.MEDIA_URL,
        StaticFiles(directory=str(settings.media_path), check_dir=False),
        name="media",
    )

app.include_router(auth_router.router, prefix=settings.API_V1_PREFIX)
app.include_router(catalog_router.router, prefix=settings.API_V1_PREFIX)
app.include_router(checkout_router.router, prefix=settings.API_V1_PREFIX)
app.include_router(content_router.router, prefix=settings.API_V1_PREFIX)
app.include_router(engagement_router.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin_router.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin_content_router.router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness: the process is up. Cheap, never touches the database."""
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}


@app.get("/readyz", tags=["meta"])
def readyz():
    """Readiness: can we actually serve? Pings the database and 503s if not, so
    the load balancer stops routing traffic to an instance whose DB is gone."""
    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    from app.db.session import SessionLocal

    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ready"}


@app.get("/api/cron/run-jobs", tags=["meta"], include_in_schema=False)
def run_scheduled_jobs(request: Request):
    """Drain the background job queue once. Triggered by a scheduler.

    On serverless there is no persistent worker, so a scheduler (Vercel Cron or
    an external pinger) calls this to process due jobs: reservation sweeps,
    abandoned-cart and back-in-stock notices, scheduled publishing. Guarded by
    CRON_SECRET, accepted as an ``Authorization: Bearer`` header (Vercel Cron
    sends this automatically) or a ``?key=`` query param. The handlers are
    idempotent, so an occasional double-run is harmless.
    """
    from fastapi.responses import JSONResponse

    secret = settings.CRON_SECRET
    if not secret:
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "not_configured",
                               "message": "CRON_SECRET is not set."}},
        )
    auth = request.headers.get("authorization", "")
    supplied = auth[7:].strip() if auth.lower().startswith("bearer ") \
        else request.query_params.get("key", "")
    if supplied != secret:
        return JSONResponse(
            status_code=401,
            content={"error": {"code": "unauthorized",
                               "message": "Invalid cron secret."}},
        )

    from app.workers import jobs  # noqa: F401  (registers handlers)
    from app.workers.runner import bootstrap_schedule, tick

    bootstrap_schedule()
    processed = 0
    # Bounded drain so the request stays well within the function time limit.
    for _ in range(25):
        n = tick()
        processed += n
        if n == 0:
            break
    return {"status": "ok", "processed": processed}


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {
        "name": "Woodcroft API",
        "docs": "/docs",
        "health": "/health",
    }
