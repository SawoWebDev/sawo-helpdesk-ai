from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_usage_log import AIUsageLog


def _today_start_naive_utc() -> datetime:
    # SQLite has no real timezone-aware storage: func.now() writes a naive
    # 'YYYY-MM-DD HH:MM:SS' UTC string regardless of the column's
    # DateTime(timezone=True) type, so the comparison value must be naive
    # UTC too or the two won't compare as intended.
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


async def get_usage_totals(db: AsyncSession) -> dict:
    today_start = _today_start_naive_utc()

    today_row = (
        await db.execute(
            select(func.count(AIUsageLog.id), func.coalesce(func.sum(AIUsageLog.total_tokens), 0)).where(
                AIUsageLog.created_at >= today_start
            )
        )
    ).one()
    total_row = (
        await db.execute(
            select(func.count(AIUsageLog.id), func.coalesce(func.sum(AIUsageLog.total_tokens), 0))
        )
    ).one()

    return {
        "requests_today": today_row[0],
        "tokens_today": int(today_row[1]),
        "requests_total": total_row[0],
        "tokens_total": int(total_row[1]),
    }


async def get_usage_by_model(db: AsyncSession) -> list[dict]:
    """One row per model that has ever logged a request, most-recently-used
    first, with lifetime and today's request/token/cost totals for each."""
    today_start = _today_start_naive_utc()

    rows = (
        await db.execute(
            select(
                AIUsageLog.model,
                AIUsageLog.is_free,
                func.count(AIUsageLog.id),
                func.coalesce(func.sum(AIUsageLog.total_tokens), 0),
                func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0),
                func.max(AIUsageLog.created_at),
            ).group_by(AIUsageLog.model, AIUsageLog.is_free)
        )
    ).all()

    today_rows = (
        await db.execute(
            select(
                AIUsageLog.model,
                func.count(AIUsageLog.id),
                func.coalesce(func.sum(AIUsageLog.total_tokens), 0),
                func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0),
            )
            .where(AIUsageLog.created_at >= today_start)
            .group_by(AIUsageLog.model)
        )
    ).all()
    today_by_model = {row[0]: row for row in today_rows}

    result = []
    for model, is_free, requests, tokens, cost, last_used in rows:
        today = today_by_model.get(model)
        result.append(
            {
                "model": model,
                "is_free": is_free,
                "requests_total": requests,
                "tokens_total": int(tokens),
                "cost_total_usd": float(cost),
                "requests_today": today[1] if today else 0,
                "tokens_today": int(today[2]) if today else 0,
                "cost_today_usd": float(today[3]) if today else 0.0,
                "last_used_at": last_used,
            }
        )
    result.sort(key=lambda r: r["last_used_at"] or "", reverse=True)
    return result


async def get_usage_daily_totals(db: AsyncSession, days: int = 30) -> list[dict]:
    """Per-day request/token/cost totals across all models, oldest first, for
    the last `days` calendar days (UTC) — the Dashboard's "daily AI spend"
    trend, as opposed to get_usage_daily_for_model's single-model drill-down."""
    since = _today_start_naive_utc() - timedelta(days=days - 1)
    day_expr = func.date(AIUsageLog.created_at)
    rows = (
        await db.execute(
            select(
                day_expr.label("day"),
                func.count(AIUsageLog.id),
                func.coalesce(func.sum(AIUsageLog.total_tokens), 0),
                func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0),
            )
            .where(AIUsageLog.created_at >= since)
            .group_by(day_expr)
        )
    ).all()
    by_day = {day: (requests, tokens, cost) for day, requests, tokens, cost in rows}

    result = []
    today = _today_start_naive_utc()
    for offset in range(days):
        day = (today - timedelta(days=days - 1 - offset)).strftime("%Y-%m-%d")
        requests, tokens, cost = by_day.get(day, (0, 0, 0.0))
        result.append({"day": day, "requests": requests, "tokens": int(tokens), "cost_usd": float(cost)})
    return result


async def get_usage_daily_for_model(db: AsyncSession, model: str, days: int = 14) -> list[dict]:
    """Per-day request/token/cost breakdown for one model, most recent first,
    over the last `days` calendar days (UTC)."""
    day_expr = func.date(AIUsageLog.created_at)
    rows = (
        await db.execute(
            select(
                day_expr.label("day"),
                func.count(AIUsageLog.id),
                func.coalesce(func.sum(AIUsageLog.total_tokens), 0),
                func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0),
            )
            .where(AIUsageLog.model == model)
            .group_by(day_expr)
            .order_by(day_expr.desc())
            .limit(days)
        )
    ).all()
    return [
        {"day": day, "requests": requests, "tokens": int(tokens), "cost_usd": float(cost)}
        for day, requests, tokens, cost in rows
    ]
