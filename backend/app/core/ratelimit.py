"""Rate limiting.

slowapi with in-memory storage, which is the right call here: there is no Redis
in this environment, and a single uvicorn process shares one limiter anyway.
If this is ever scaled to multiple workers, point ``storage_uri`` at Redis and
nothing else has to change.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings


def _identify(request) -> str:
    """Rate limit per user when signed in, per IP otherwise.

    Keying auth endpoints purely on IP would let one office network lock itself
    out, and would let an attacker rotating IPs through a proxy pool bypass it.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return f"token:{auth[7:][:32]}"
    return get_remote_address(request)


limiter = Limiter(
    key_func=_identify,
    default_limits=[],
    enabled=settings.APP_ENV != "test",
)
