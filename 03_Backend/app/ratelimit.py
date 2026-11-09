"""WBS 3.4 - rate limiting.

Two different keys for two different problems. An authenticated request is
limited per install, which is the whole point of issuing per-install tokens:
one abusive install trips its own limit and nobody else's. An unauthenticated
request - /register, or /scan in the degraded path - can only be limited by
source IP, which is coarser and easier to evade, so /register's limit is the
strict one. Exceeding a limit returns 429 with Retry-After, not a ban; nothing
is revoked automatically (00_Admin/auth-design-revision.md).

Built directly on the `limits` library as a FastAPI dependency rather than on
slowapi's route decorator: that decorator replaces the handler's signature, so
FastAPI stops seeing the request body as a body. A dependency leaves the
handlers alone and keeps the limit out of their logic.

Storage is in-process. The deployment runs a single API container behind Nginx
(WBS 5.2), so one process sees every request and an in-memory moving window is
accurate. Scaling past one worker means moving this to Redis - recorded here so
the limitation is visible rather than discovered later.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from functools import lru_cache

from fastapi import HTTPException, Request, status
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from .auth import bearer_token, token_hash
from .config import get_settings

_storage = MemoryStorage()
_limiter = MovingWindowRateLimiter(_storage)


@lru_cache(maxsize=32)
def _item(limit: str):
    return parse(limit)


def client_key(request: Request) -> str:
    """Per-install when a token was presented, per-IP otherwise.

    Keyed on the token hash, never the token itself, so the limiter's state does
    not become a second place tokens are held in the clear.
    """
    token = bearer_token(request.headers.get("authorization"))
    if token:
        return "install:" + token_hash(token).hex()
    client = request.client.host if request.client else "unknown"
    return "ip:" + client


def reset() -> None:
    """Clear all counters. Used by the tests; never called by the application."""
    _storage.reset()
    _item.cache_clear()


def limit(which: Callable[[], str], scope: str):
    """Build a dependency enforcing the limit named by `which` under `scope`."""

    def dependency(request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return
        item = _item(which())
        key = client_key(request)
        if not _limiter.hit(item, scope, key):
            reset_at, _remaining = _limiter.get_window_stats(item, scope, key)
            retry_after = max(1, math.ceil(reset_at - time.time()))
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"rate limit exceeded ({item}); retry in {retry_after}s",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency


scan_limit = limit(lambda: get_settings().scan_rate_limit, "scan")
register_limit = limit(lambda: get_settings().register_rate_limit, "register")
feedback_limit = limit(lambda: get_settings().feedback_rate_limit, "feedback")
