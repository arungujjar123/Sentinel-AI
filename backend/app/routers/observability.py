import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models import LogsResponse, MetricsResponse
from app.routers.gateway import verify_api_key  # reuse the same auth
from app.services.cache import get_cache_stats
from app.services.circuit_breaker import registry as cb
from app.services.cost import get_pricing_table
from app.services.queries import get_logs, get_metrics
from app.services.redis_client import get_redis
from app.services.webhook import send_webhook
from app.worker import celery_app

router = APIRouter()


@router.get("/v1/logs", response_model=LogsResponse)
async def logs(
    page:     int            = Query(default=1,  ge=1),
    limit:    int            = Query(default=50, ge=1, le=200),
    status:   Optional[str] = Query(default=None, description="success | error | fallback"),
    provider: Optional[str] = Query(default=None, description="groq | gemini"),
    db:       AsyncSession   = Depends(get_db),
    _:        str            = Depends(verify_api_key),
):
    result = await get_logs(db=db, page=page, limit=limit, status=status, provider=provider)
    return LogsResponse(**result)


@router.get("/v1/metrics", response_model=MetricsResponse)
async def metrics(
    window: str          = Query(default="24h", description="1h | 6h | 24h | 7d"),
    db:     AsyncSession = Depends(get_db),
    _:      str          = Depends(verify_api_key),
):
    result = await get_metrics(db=db, window=window)
    return MetricsResponse(**result)


@router.get("/v1/pricing")
async def pricing(_: str = Depends(verify_api_key)):
    """Returns current provider pricing per 1M tokens."""
    return {
        "unit": "USD per 1M tokens",
        "note": "Cost is calculated on every request using real token counts × these rates",
        "providers": get_pricing_table()
    }


@router.get("/v1/cache/stats")
async def cache_stats(
    db: AsyncSession = Depends(get_db),
    _:  str          = Depends(verify_api_key),
):
    return await get_cache_stats(db=db)


@router.delete("/v1/cache/invalidate")
async def invalidate_cache(
    db: AsyncSession = Depends(get_db),
    _:  str          = Depends(verify_api_key),
):
    """Mark all cache entries as stale. Useful for testing."""
    from sqlalchemy import update as sql_update

    from app.db.models import CacheEntry
    await db.execute(sql_update(CacheEntry).values(is_stale=True))
    await db.commit()
    return {"message": "All cache entries invalidated"}


@router.post("/v1/circuit/{provider}/reset")
async def reset_circuit(
    provider: str,
    _: str = Depends(verify_api_key),
):
    """Manually reset a circuit breaker — useful for testing and demos."""
    await cb.reset(provider)
    return {"message": f"{provider} circuit reset to CLOSED"}

@router.get("/v1/circuit/states")
async def circuit_states(_: str = Depends(verify_api_key)):
    """Current state of all circuit breakers."""
    return await cb.get_all_states()


def _ping_celery_workers() -> dict:
    """
    Blocking Celery control broadcast — must be called via asyncio.to_thread,
    never directly from an async handler. inspect().ping() waits out its full
    timeout when no worker replies, which would stall the event loop (and
    every other in-flight request) on each dashboard poll.
    """
    inspector = celery_app.control.inspect(timeout=1)
    if not inspector:
        return {}
    return inspector.ping() or {}


@router.get("/v1/worker/stats")
async def worker_stats(_: str = Depends(verify_api_key)):
    """
    Returns Celery queue depth and worker status from Redis.
    Used by dashboard to show async processing health.

    Uses the shared async client (settings.redis_url) rather than its own
    sync connection to localhost — the old hardcoded host meant this
    endpoint always reported "down" under docker-compose, where Redis is
    reachable as `redis`, not `localhost`.
    """
    try:
        r = get_redis()
        await asyncio.wait_for(r.ping(), timeout=settings.health_redis_timeout_seconds)

        ping = await asyncio.to_thread(_ping_celery_workers)
        if len(ping) == 0:
            return {"status": "down", "queue_depth": 0}

        queue_depth = await asyncio.wait_for(
            r.llen("celery"), timeout=settings.health_redis_timeout_seconds
        )
        return {"status": "connected", "queue_depth": queue_depth}
    except Exception:
        return {"status": "down", "queue_depth": 0}


@router.get("/v1/webhook/config")
async def webhook_config(_: str = Depends(verify_api_key)):
    """Returns whether a webhook URL/secret are configured. Never exposes the secret itself."""
    return {
        "url_configured": bool(settings.webhook_url),
        "secret_configured": bool(settings.webhook_secret),
    }


@router.post("/v1/webhook/test")
async def webhook_test(_: str = Depends(verify_api_key)):
    """Fires a test payload at the configured webhook URL synchronously and reports the delivery outcome."""
    if not settings.webhook_url:
        raise HTTPException(status_code=400, detail="No webhook_url configured")

    payload = {
        "event": "webhook.test",
        "message": "SentinelAI webhook test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    result = await send_webhook(payload)
    return {
        "status": "sent" if result["sent"] else "failed",
        "response_code": result["status_code"],
    }
