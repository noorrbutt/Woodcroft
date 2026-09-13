"""FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1 import admin as admin_router
from app.api.v1 import auth as auth_router
from app.api.v1 import catalog as catalog_router
from app.api.v1 import checkout as checkout_router
from app.api.v1 import content as content_router
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
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Guest-Token"],
)

register_exception_handlers(app)


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


# Product images and generated media are served straight off disk. There is no
# object store in this deployment, and for a catalogue this size a static mount
# is both faster and simpler than proxying through the app.
app.mount(
    settings.MEDIA_URL,
    StaticFiles(directory=str(settings.media_path), check_dir=False),
    name="media",
)

app.include_router(auth_router.router, prefix=settings.API_V1_PREFIX)
app.include_router(catalog_router.router, prefix=settings.API_V1_PREFIX)
app.include_router(checkout_router.router, prefix=settings.API_V1_PREFIX)
app.include_router(content_router.router, prefix=settings.API_V1_PREFIX)
app.include_router(admin_router.router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {
        "name": "Woodcroft API",
        "docs": "/docs",
        "health": "/health",
    }
