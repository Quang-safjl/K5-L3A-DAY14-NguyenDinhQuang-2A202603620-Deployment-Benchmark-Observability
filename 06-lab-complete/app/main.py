"""Production-ready agent (Part 6)."""
import json
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from utils.mock_llm import ask as llm_ask

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import close_redis, redis_healthy


# ---------- Criterion 10: one JSON object per log line ----------
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)
    return logging.getLogger("agent")


logger = setup_logging()


def log(event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"fields": {"event": event, **fields}})


# ---------- Criterion 11: graceful shutdown ----------
# Uvicorn already handles SIGTERM correctly: it stops accepting new
# connections, waits for in-flight requests, runs the lifespan shutdown
# below, then exits with code 0. We do NOT install our own SIGTERM handler.
@asynccontextmanager
async def lifespan(app: FastAPI):
    log("startup", environment=settings.environment, port=settings.port)
    yield
    log("shutdown_started")
    close_redis()
    log("shutdown_complete")


app = FastAPI(title="Day 14 Production Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[str] = None


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log("request_error", logging.ERROR, request_id=request_id, path=request.url.path)
        raise
    response.headers["X-Request-ID"] = request_id
    log(
        "request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        latency_ms=round((time.perf_counter() - start) * 1000, 1),
    )
    return response


# ---------- Criterion 4: liveness ----------
@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.environment}


# ---------- Criterion 5: readiness ----------
@app.get("/ready")
def ready():
    if redis_healthy():
        return {"status": "ready", "redis": "ok"}
    return JSONResponse(status_code=503, content={"status": "not_ready", "redis": "unreachable"})


# ---------- Criteria 6, 7, 8 ----------
@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)   # 429 + Retry-After
    check_budget()              # 402
    answer = llm_ask(body.question)
    cost = record_cost(body.question, answer)
    log("ask_ok", user_id=body.user_id, cost_usd=round(cost, 6))
    return {"question": body.question, "answer": answer}
