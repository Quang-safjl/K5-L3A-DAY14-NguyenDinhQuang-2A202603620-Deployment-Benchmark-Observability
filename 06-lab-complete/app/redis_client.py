"""Redis connection from REDIS_URL.

The client is created lazily and never connects at import time, so the
container starts (and /health answers) even when Redis is down.
"""
from typing import Optional

import redis

from app.config import settings

_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _client


def redis_healthy() -> bool:
    try:
        return bool(get_redis().ping())
    except redis.RedisError:
        return False


def close_redis() -> None:
    global _client
    if _client is not None:
        try:
            _client.close()
        except redis.RedisError:
            pass
        _client = None
