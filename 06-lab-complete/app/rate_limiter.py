"""Criterion 7: sliding-window rate limit per API key, stored in Redis.

State lives in Redis (not process memory), so it is shared between the
2 uvicorn workers and survives an agent restart. A Lua script makes the
check-and-add atomic, so concurrent requests cannot overshoot the limit.
"""
import hashlib
import math
import time
import uuid

import redis
from fastapi import HTTPException, status

from app.config import settings
from app.redis_client import get_redis

WINDOW_SECONDS = 60

_LUA = """
local key    = KEYS[1]
local now    = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit  = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  return {0, tostring(oldest[2])}
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window)
return {1, ''}
"""


def _key_for(api_key: str) -> str:
    # Never store the raw key in Redis.
    digest = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    return f"ratelimit:{digest}"


def check_rate_limit(api_key: str) -> None:
    now = time.time()
    try:
        allowed, oldest = get_redis().eval(
            _LUA,
            1,
            _key_for(api_key),
            now,
            WINDOW_SECONDS,
            settings.rate_limit_per_minute,
            f"{now}-{uuid.uuid4().hex}",
        )
    except redis.RedisError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Rate limiter unavailable")

    if int(allowed) == 0:
        retry_after = WINDOW_SECONDS
        if oldest:
            retry_after = max(1, math.ceil(float(oldest) + WINDOW_SECONDS - now))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
