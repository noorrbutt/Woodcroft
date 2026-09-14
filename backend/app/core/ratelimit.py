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
from app.core.security import decode_token


def _identify(request) -> str:
    """Rate limit per user when signed in, per IP otherwise.

    The token is decoded and keyed on its subject. The old code keyed on the
    first 32 characters of the bearer string, which for every HS256 token this
    app issues are the identical header segment, so every signed-in request
    shared one bucket, and an attacker could send a random bearer per request to
    land in a fresh bucket and defeat the login limiter entirely. An invalid or
    absent token falls back to the peer address.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            payload = decode_token(auth[7:].strip(), expected_type="access")
            return f"user:{payload['sub']}"
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(
    key_func=_identify,
    default_limits=[],
    enabled=settings.APP_ENV != "test",
)
