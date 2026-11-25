"""Criterion 9: every setting comes from environment variables."""
import os
from dataclasses import dataclass
from typing import Optional


def _optional_float(name: str) -> Optional[float]:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    return float(raw)


@dataclass(frozen=True)
class Settings:
    agent_api_key: str = os.getenv("AGENT_API_KEY", "")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
    daily_budget_usd: Optional[float] = _optional_float("DAILY_BUDGET_USD")
    monthly_budget_usd: Optional[float] = _optional_float("MONTHLY_BUDGET_USD")
    port: int = int(os.getenv("PORT", "8000"))
    environment: str = os.getenv("ENVIRONMENT", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()


settings = Settings()
