"""
Simple in-process rate limiter middleware.

For a single-instance deployment this needs no external service. For a
multi-instance production deployment behind a load balancer, swap the
in-memory `_buckets` dict for Redis (INCR + EXPIRE) using REDIS_URL from
settings -- the interface below is intentionally small so that swap is a
one-function change.
"""
import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings

_buckets: dict[str, deque] = defaultdict(deque)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        key = f"{client_ip}:{request.url.path}"
        now = time.time()
        window = 60.0
        limit = settings.RATE_LIMIT_PER_MINUTE

        bucket = _buckets[key]
        while bucket and now - bucket[0] > window:
            bucket.popleft()

        if len(bucket) >= limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
            )

        bucket.append(now)
        return await call_next(request)
