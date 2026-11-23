import asyncio
import logging
import time
import uuid

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.models import ChatRequest, ChatResponse, MetaInfo, UsageInfo
from app.services import guardrails
from app.services.api_keys import resolve_key
from app.services.cache import check_cache
from app.services.circuit_breaker import registry as cb
from app.services.cost import calculate_cost
from app.services.providers import call_gemini, call_groq
from app.services.rate_limiter import limiter
from app.services.redaction import restore

# Import Celery tasks (fire-and-forget post-processing)
from app.tasks import post_process_task, touch_api_key_task

logger = logging.getLogger(__name__)
router = APIRouter()


def _truncate(s: str | None, n: int = 280) -> str | None:
    if not s:
        return None
    s = s.strip()
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _prompt_preview(messages: list[dict]) -> str | None:
    # Prefer the last user message (what engineers usually want to inspect).
    for m in reversed(messages):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            return _truncate(m.get("content"))
    # Fallback: last message content.
    if messages and isinstance(messages[-1].get("content"), str):
        return _truncate(messages[-1].get("content"))
    return None


def _queue(task, **kwargs) -> int:
    """
    Enqueue a fire-and-forget Celery task without ever failing the request.

    A broker outage must not turn an otherwise-successful response into a
    500 — the same degrade-don't-block philosophy services/rate_limiter.py
    and services/circuit_breaker.py already follow for Redis. Losing a log
    row or a cache write is an acceptable cost; losing a response the
    caller already paid a provider for is not. Returns queue time in ms.
    """
    start = time.monotonic()
    try:
        task.delay(**kwargs)
    except Exception as e:
        logger.error("failed to queue %s — continuing without it: %s", task.name, e)
    return int((time.monotonic() - start) * 1000)


async def verify_api_key(
    response: Response,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> str:
    """
    Resolves the bearer token and enforces its rate limit.

    Two accepted forms:
      - The master admin key (settings.api_key) — always valid, never
        rate-limited. Kept for backward compatibility and bootstrapping.
      - A per-tenant key (see app/services/api_keys.py) — looked up via a
        Redis-cached hash lookup against the api_keys table, then checked
        against its own requests-per-minute limit.

    Returns an identity string ("master" or the key's id) for callers that
    want to know who made the request.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth format")
    token = authorization.replace("Bearer ", "")

    if token == settings.api_key:
        return "master"

    key_data = await resolve_key(db=db, raw_key=token)
    if key_data is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    limit_result = await limiter.check(key_hash=key_data["key_hash"], limit=key_data["rate_limit"])
    response.headers["X-RateLimit-Limit"] = str(limit_result.limit)
    response.headers["X-RateLimit-Remaining"] = str(limit_result.remaining)

    if not limit_result.allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(limit_result.limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(limit_result.reset_seconds),
                "Retry-After": str(limit_result.reset_seconds),
            },
        )

    # Fire-and-forget — never block (or fail) the request on a last_used write.
    _queue(touch_api_key_task, key_hash=key_data["key_hash"])
    return key_data["id"]


def verify_master_key(authorization: str = Header(...)) -> str:
    """
    Admin-only auth for API key management endpoints (routers/keys.py).
    Accepts only the master key from settings — never a per-tenant key,
    so a leaked tenant key can't be used to mint or revoke other keys.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth format")
    token = authorization.replace("Bearer ", "")
    if token != settings.api_key:
        raise HTTPException(status_code=401, detail="Admin key required")
    return token


async def _try_provider(name: str, fn) -> dict | None:
    """
    Attempt a provider call with circuit breaker protection.
    Returns result dict on success, None on any failure.
    """
    if not await cb.is_available(name):
        logger.info("%s circuit is OPEN — skipping immediately", name)
        return None

    try:
        result = await fn()
        await cb.record_success(name)
        return result

    except httpx.TimeoutException:
        logger.warning("%s TIMEOUT — recording circuit breaker failure", name)
        await cb.record_failure(name)
        return None

    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        logger.warning("%s returned HTTP %d — recording circuit breaker failure", name, status_code)
        await cb.record_failure(name)   # ← record ALL HTTP errors now, not just some
        return None                     # ← always return None, never re-raise

    except Exception as e:
        logger.error("%s unexpected error: %s", name, e)
        await cb.record_failure(name)
        return None


def _log_timing(request_id: str, wall_start: float, stage: dict, **extra) -> None:
    if settings.log_stage_timings:
        logger.info("chat request timing", extra={
            "request_id": request_id, "total_ms": int((time.monotonic() - wall_start) * 1000), **stage, **extra,
        })


@router.post("/v1/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(verify_api_key),
):
    raw_messages = [m.model_dump() for m in request.messages]
    request_id = str(uuid.uuid4())
    wall_start = time.monotonic()
    stage: dict[str, int] = {}

    # ── 1. Guardrails: redact PII, score injection, pick a model tier ─
    # Everything after this point — cache, providers, logs — only ever
    # sees the redacted messages.
    t_guard = time.monotonic()
    guard = await asyncio.to_thread(guardrails.inspect, raw_messages, request.model)
    stage["guard_ms"] = int((time.monotonic() - t_guard) * 1000)
    messages = guard.messages
    mapping = guard.redaction.mapping
    prompt_prev = _prompt_preview(messages)
    log_common = {"messages": messages, "prompt_preview": prompt_prev, **guard.log_fields()}

    if guard.blocked:
        stage["task_queue_ms"] = _queue(
            post_process_task,
            request_id=request_id, provider="none", model=request.model or "none",
            input_tokens=0, output_tokens=0, cost_usd=0.0,
            latency_ms=int((time.monotonic() - wall_start) * 1000),
            cache_hit=False, status="blocked", error_type="prompt_injection", fallback_from=None,
            response=None, response_preview=None, **log_common,
        )
        _log_timing(request_id, wall_start, stage, status="blocked")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "prompt_injection_detected",
                "message": "This request was blocked because it looks like a prompt-injection attempt.",
                "score": round(guard.injection_score or 0.0, 3),
                "request_id": request_id,
            },
        )

    meta_extra = {"route": guard.route, "redactions": guard.redaction.total}

    # ── 2. Semantic cache (keyed on the redacted prompt) ──────────────
    if not request.bypass_cache:
        t_cache = time.monotonic()
        cached = await check_cache(db=db, messages=messages)
        stage["cache_check_ms"] = int((time.monotonic() - t_cache) * 1000)

        if cached:
            wall_latency = int((time.monotonic() - wall_start) * 1000)
            stage["task_queue_ms"] = _queue(
                post_process_task,
                request_id=request_id, provider=cached["provider"], model=cached["model"],
                input_tokens=cached["input_tokens"], output_tokens=cached["output_tokens"],
                cost_usd=0.0, latency_ms=wall_latency, cache_hit=True,
                status="success", error_type=None, fallback_from=None,
                response=None,  # nothing to cache — already cached
                response_preview=_truncate(cached.get("content")),
                **log_common,
            )
            _log_timing(request_id, wall_start, stage, cache_hit=True)
            return ChatResponse(
                id=request_id, content=restore(cached["content"], mapping),
                provider=cached["provider"], model=cached["model"],
                usage=UsageInfo(input_tokens=cached["input_tokens"],
                                output_tokens=cached["output_tokens"],
                                cost_usd=0.0),
                meta=MetaInfo(cache_hit=True, latency_ms=wall_latency,
                              provider=cached["provider"], fallback=None, **meta_extra),
            )

    # ── 3. Groq on the routed (or pinned) model, circuit-breaker guarded
    fallback_from: str | None = None
    status = "success"
    groq_model = guardrails.groq_model(guard, request.model)

    t_groq = time.monotonic()
    result = await _try_provider(
        "groq",
        lambda: call_groq(
            messages=messages, model=groq_model,
            max_tokens=request.max_tokens, temperature=request.temperature,
        ),
    )
    stage["groq_ms"] = int((time.monotonic() - t_groq) * 1000)

    # ── 4. Gemini, same tier, if Groq failed or its circuit is open ───
    if result is None:
        fallback_from = "groq"
        t_gemini = time.monotonic()
        result = await _try_provider(
            "gemini",
            lambda: call_gemini(
                messages=messages, max_tokens=request.max_tokens,
                temperature=request.temperature, model=guardrails.gemini_model(guard),
            ),
        )
        stage["gemini_ms"] = int((time.monotonic() - t_gemini) * 1000)
        if result:
            status = "fallback"

    # ── 5. All providers failed ───────────────────────────────────────
    if result is None:
        stage["task_queue_ms"] = _queue(
            post_process_task,
            request_id=request_id, provider="none", model=groq_model,
            input_tokens=0, output_tokens=0, cost_usd=0.0,
            latency_ms=int((time.monotonic() - wall_start) * 1000),
            cache_hit=False, status="error", error_type="all_providers_failed",
            fallback_from=fallback_from, response=None, response_preview=None,
            **log_common,
        )
        _log_timing(request_id, wall_start, stage, status="error")
        circuit_states = await cb.get_all_states()
        raise HTTPException(
            status_code=503,
            detail={"error": "All providers unavailable", "circuit_states": circuit_states},
        )

    wall_latency = int((time.monotonic() - wall_start) * 1000)

    # What this request would have cost on the large model — the basis
    # for "saved by routing" in /v1/metrics.
    cost_if_large = None
    if guard.route == "small":
        large = guardrails.large_model_for(result["provider"])
        if large:
            cost_if_large = calculate_cost(result["provider"], large, result["input_tokens"], result["output_tokens"])

    # ── 6. Respond first; log + cache in the background ───────────────
    # The cache stores the provider's placeholder text (no PII); only this
    # caller's response gets the original values put back.
    response_obj = ChatResponse(
        id=request_id, content=restore(result["content"], mapping),
        provider=result["provider"], model=result["model"],
        usage=UsageInfo(input_tokens=result["input_tokens"],
                        output_tokens=result["output_tokens"],
                        cost_usd=result["cost_usd"]),
        meta=MetaInfo(cache_hit=False, latency_ms=wall_latency,
                      provider=result["provider"], fallback=fallback_from, **meta_extra),
    )
    stage["task_queue_ms"] = _queue(
        post_process_task,
        request_id=request_id, provider=result["provider"], model=result["model"],
        input_tokens=result["input_tokens"], output_tokens=result["output_tokens"],
        cost_usd=result["cost_usd"], latency_ms=wall_latency, cache_hit=False,
        status=status, error_type=None, fallback_from=fallback_from,
        response=result, response_preview=_truncate(result.get("content")),
        cost_if_large_usd=cost_if_large, **log_common,
    )
    _log_timing(request_id, wall_start, stage, status=status)
    return response_obj
