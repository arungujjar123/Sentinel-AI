import statistics
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RequestLog


# ── Helper: convert window string to a datetime cutoff ──────────────
def window_to_cutoff(window: str) -> datetime:
    now = datetime.now(timezone.utc)
    mapping = {
        "1h":  timedelta(hours=1),
        "6h":  timedelta(hours=6),
        "24h": timedelta(hours=24),
        "7d":  timedelta(days=7),
    }
    delta = mapping.get(window, timedelta(hours=24))
    return now - delta


# ── Fetch paginated logs with optional filters ───────────────────────
async def get_logs(
    db: AsyncSession,
    page: int = 1,
    limit: int = 50,
    status: Optional[str] = None,       # "success" | "error" | "fallback"
    provider: Optional[str] = None,     # "groq" | "gemini"
) -> dict:

    offset = (page - 1) * limit

    # Build filter conditions dynamically
    conditions = []
    if status:
        conditions.append(RequestLog.status == status)
    if provider:
        conditions.append(RequestLog.provider == provider)

    # Count query (for pagination total)
    count_stmt = select(func.count()).select_from(RequestLog)
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total = (await db.execute(count_stmt)).scalar_one()

    # Data query
    data_stmt = (
        select(RequestLog)
        .order_by(desc(RequestLog.created_at))
        .offset(offset)
        .limit(limit)
    )
    if conditions:
        data_stmt = data_stmt.where(and_(*conditions))

    rows = (await db.execute(data_stmt)).scalars().all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "logs": rows,
    }


# ── Compute metrics for a given time window ──────────────────────────
async def get_metrics(db: AsyncSession, window: str = "24h") -> dict:
    cutoff = window_to_cutoff(window)

    # Fetch all rows in the window (we need raw data for percentile math)
    stmt = select(RequestLog).where(RequestLog.created_at >= cutoff)
    rows = (await db.execute(stmt)).scalars().all()

    if not rows:
        return _empty_metrics(window)

    total = len(rows)
    blocked     = [r for r in rows if r.status == "blocked"]
    successful  = [r for r in rows if r.status == "success"]
    failed      = [r for r in rows if r.status == "error"]
    fallbacks   = [r for r in rows if r.status == "fallback"]
    cache_hits  = [r for r in rows if r.cache_hit is True]

    # Latency percentiles — only from successful + fallback (errors have bad latency)
    good_rows = successful + fallbacks
    latencies = sorted([r.latency_ms for r in good_rows]) if good_rows else [0]

    def percentile(data: list, pct: float) -> float:
        if not data:
            return 0.0
        idx = int(len(data) * pct / 100)
        idx = min(idx, len(data) - 1)
        return float(data[idx])

    # Per-provider breakdown
    provider_names = set(r.provider for r in rows if r.provider != "none")
    providers = {}
    for name in provider_names:
        p_rows   = [r for r in rows if r.provider == name]
        p_errors = [r for r in p_rows if r.status == "error"]
        p_lat    = [r.latency_ms for r in p_rows]
        providers[name] = {
            "requests":       len(p_rows),
            "errors":         len(p_errors),
            "avg_latency_ms": round(statistics.mean(p_lat), 1) if p_lat else 0.0,
            "error_rate":     round(len(p_errors) / len(p_rows), 4) if p_rows else 0.0,
        }

    return {
        "window":               window,
        "total_requests":       total,
        "successful_requests":  len(successful),
        "failed_requests":      len(failed),
        "fallback_requests":    len(fallbacks),
        # Blocked requests never reach the cache, so they're left out of the denominator.
        "cache_hit_rate":       round(len(cache_hits) / (total - len(blocked)), 4) if total > len(blocked) else 0.0,
        "total_cost_usd":       round(sum(r.cost_usd for r in rows), 6),
        "latency": {
            "p50_ms":  percentile(latencies, 50),
            "p95_ms":  percentile(latencies, 95),
            "p99_ms":  percentile(latencies, 99),
            "avg_ms":  round(statistics.mean(latencies), 1),
        },
        "providers": providers,
        "guardrails": _guardrail_stats(rows, blocked),
        "routing": _routing_stats(rows),
    }


def _guardrail_stats(rows: list, blocked: list) -> dict:
    redacted = [r for r in rows if (r.redaction_count or 0) > 0]
    by_type: dict[str, int] = {}
    for r in redacted:
        for kind in (r.redaction_types or "").split(","):
            if kind:
                by_type[kind] = by_type.get(kind, 0) + 1
    return {
        "blocked_requests":   len(blocked),
        "redacted_requests":  len(redacted),
        "redactions_total":   sum(r.redaction_count for r in redacted),
        "redacted_requests_by_type": by_type,
    }


def _routing_stats(rows: list) -> dict:
    """
    Tier split over requests that actually called a provider (cache hits,
    blocked and failed requests never used the routed model), plus what
    sending small-routed requests to the small model saved versus the
    large one.
    """
    served = [r for r in rows if not r.cache_hit and r.status in ("success", "fallback")]
    counts = {tier: 0 for tier in ("small", "large", "pinned", "default")}
    for r in served:
        counts[r.route if r.route in counts else "default"] += 1
    saved = sum(
        r.cost_if_large_usd - r.cost_usd
        for r in served
        if r.route == "small" and r.cost_if_large_usd is not None
    )
    return {**counts, "saved_usd": round(max(saved, 0.0), 6)}


def _empty_metrics(window: str) -> dict:
    return {
        "window": window,
        "total_requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "fallback_requests": 0,
        "cache_hit_rate": 0.0,
        "total_cost_usd": 0.0,
        "latency": {"p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "avg_ms": 0.0},
        "providers": {},
        "guardrails": {"blocked_requests": 0, "redacted_requests": 0, "redactions_total": 0,
                       "redacted_requests_by_type": {}},
        "routing": {"small": 0, "large": 0, "pinned": 0, "default": 0, "saved_usd": 0.0},
    }
