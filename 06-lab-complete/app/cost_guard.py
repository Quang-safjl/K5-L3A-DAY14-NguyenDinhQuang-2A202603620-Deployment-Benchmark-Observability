"""Criterion 8: return 402 once spend reaches DAILY_BUDGET_USD / MONTHLY_BUDGET_USD.

Spend is kept in Redis so every worker and instance sees the same total.
"""
from datetime import datetime, timezone

import redis
from fastapi import HTTPException, status

from app.config import settings
from app.redis_client import get_redis

# Rough mock pricing: ~4 characters per token.
PRICE_PER_1K_INPUT_TOKENS = 0.0005
PRICE_PER_1K_OUTPUT_TOKENS = 0.0015


def _keys() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return f"cost:daily:{now:%Y-%m-%d}", f"cost:monthly:{now:%Y-%m}"


def estimate_cost(question: str, answer: str) -> float:
    input_tokens = max(1, len(question) // 4)
    output_tokens = max(1, len(str(answer)) // 4)
    return (
        input_tokens / 1000 * PRICE_PER_1K_INPUT_TOKENS
        + output_tokens / 1000 * PRICE_PER_1K_OUTPUT_TOKENS
    )


def check_budget() -> None:
    daily_key, monthly_key = _keys()
    try:
        daily_spent, monthly_spent = get_redis().mget(daily_key, monthly_key)
    except redis.RedisError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Cost guard unavailable")

    daily_spent = float(daily_spent or 0)
    monthly_spent = float(monthly_spent or 0)

    if settings.daily_budget_usd is not None and daily_spent >= settings.daily_budget_usd:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Daily budget exhausted")
    if settings.monthly_budget_usd is not None and monthly_spent >= settings.monthly_budget_usd:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Monthly budget exhausted")


def record_cost(question: str, answer: str) -> float:
    cost = estimate_cost(question, answer)
    daily_key, monthly_key = _keys()
    try:
        pipe = get_redis().pipeline()
        pipe.incrbyfloat(daily_key, cost)
        pipe.expire(daily_key, 2 * 24 * 3600)
        pipe.incrbyfloat(monthly_key, cost)
        pipe.expire(monthly_key, 32 * 24 * 3600)
        pipe.execute()
    except redis.RedisError:
        # The answer is already produced; don't fail the request over bookkeeping.
        pass
    return cost
