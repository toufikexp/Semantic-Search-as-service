import time

from fastapi import Depends, HTTPException, Request, Response

from app.core.auth import AuthenticatedKey, get_api_key
from app.core.config import settings
from app.core.redis import get_redis


async def check_rate_limit(
    request: Request,
    response: Response,
    auth: AuthenticatedKey = Depends(get_api_key),
):
    """Sliding-window rate limiter backed by Redis."""
    if not settings.RATE_LIMIT_ENABLED:
        return auth

    redis = await get_redis()
    key = f"ratelimit:{auth.key_id}"
    now = int(time.time())
    window = 60  # 1 minute window

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, now - window)
    pipe.zadd(key, {str(now * 1000 + id(request) % 1000): now})
    pipe.zcard(key)
    pipe.expire(key, window)
    results = await pipe.execute()

    current_count = results[2]
    limit = auth.rate_limit

    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current_count))
    response.headers["X-RateLimit-Reset"] = str(now + window)

    if current_count > limit:
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Too many requests. Please retry later.",
                }
            },
            headers={"Retry-After": str(window)},
        )

    return auth
