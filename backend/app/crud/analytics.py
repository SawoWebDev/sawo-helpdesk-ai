from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_usage_log import AIUsageLog
from app.models.category import Category
from app.models.chat_log import ChatLog
from app.models.faq import FAQEntry
from app.models.unanswered import UnansweredQuestion


def _now_naive_utc() -> datetime:
    # SQLite stores func.now() as a naive 'YYYY-MM-DD HH:MM:SS' UTC string
    # regardless of the column's DateTime(timezone=True) type, so comparison
    # values must be naive UTC too (see crud/usage.py for the same pattern).
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _days_ago_naive_utc(days: int) -> datetime:
    return _now_naive_utc() - timedelta(days=days)


def _today_start_naive_utc() -> datetime:
    now = _now_naive_utc()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def get_overview(db: AsyncSession) -> dict:
    today_start = _today_start_naive_utc()
    since_7d = _days_ago_naive_utc(7)
    since_30d = _days_ago_naive_utc(30)

    chats_today = (
        await db.execute(select(func.count(ChatLog.id)).where(ChatLog.created_at >= today_start))
    ).scalar_one()
    chats_30d = (
        await db.execute(select(func.count(ChatLog.id)).where(ChatLog.created_at >= since_30d))
    ).scalar_one()

    week_rows = (
        await db.execute(
            select(ChatLog.session_id, ChatLog.matched_faq_ids, ChatLog.matched_vault_ids).where(
                ChatLog.created_at >= since_7d
            )
        )
    ).all()
    chats_7d = len(week_rows)
    unique_sessions_7d = len({row.session_id for row in week_rows if row.session_id})
    answered_7d = sum(1 for row in week_rows if row.matched_faq_ids or row.matched_vault_ids)
    answered_rate_7d = round((answered_7d / chats_7d) * 100, 1) if chats_7d else 0.0

    unanswered_pending = (
        await db.execute(
            select(func.count(UnansweredQuestion.id)).where(UnansweredQuestion.status == "pending")
        )
    ).scalar_one()

    faq_total = (await db.execute(select(func.count(FAQEntry.id)))).scalar_one()
    faq_published = (
        await db.execute(select(func.count(FAQEntry.id)).where(FAQEntry.status == "published"))
    ).scalar_one()

    ai_cost_today = (
        await db.execute(
            select(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0)).where(
                AIUsageLog.created_at >= today_start
            )
        )
    ).scalar_one()
    ai_cost_30d = (
        await db.execute(
            select(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0)).where(
                AIUsageLog.created_at >= since_30d
            )
        )
    ).scalar_one()

    return {
        "chats_today": chats_today,
        "chats_7d": chats_7d,
        "chats_30d": chats_30d,
        "unique_sessions_7d": unique_sessions_7d,
        "answered_rate_7d": answered_rate_7d,
        "unanswered_pending": unanswered_pending,
        "faq_total": faq_total,
        "faq_published": faq_published,
        "ai_cost_today_usd": float(ai_cost_today),
        "ai_cost_30d_usd": float(ai_cost_30d),
    }


async def get_chat_trend(db: AsyncSession, days: int) -> list[dict]:
    """Daily message/session/answered-vs-unanswered counts over the last
    `days` calendar days (UTC), oldest first. Computed in Python from one
    fetch rather than SQL JSON functions, since matched_faq_ids/matched_vault_ids
    are JSON columns and this app's chat volume is small enough that isn't a
    concern."""
    since = _days_ago_naive_utc(days - 1)
    since_day_start = since.replace(hour=0, minute=0, second=0, microsecond=0)

    rows = (
        await db.execute(
            select(
                ChatLog.created_at,
                ChatLog.session_id,
                ChatLog.matched_faq_ids,
                ChatLog.matched_vault_ids,
            ).where(ChatLog.created_at >= since_day_start)
        )
    ).all()

    by_day: dict[str, dict] = {}
    today = _today_start_naive_utc()
    for offset in range(days):
        day = (today - timedelta(days=days - 1 - offset)).strftime("%Y-%m-%d")
        by_day[day] = {"messages": 0, "sessions": set(), "answered": 0, "unanswered": 0}

    for row in rows:
        day = row.created_at.strftime("%Y-%m-%d")
        bucket = by_day.get(day)
        if bucket is None:
            continue
        bucket["messages"] += 1
        if row.session_id:
            bucket["sessions"].add(row.session_id)
        if row.matched_faq_ids or row.matched_vault_ids:
            bucket["answered"] += 1
        else:
            bucket["unanswered"] += 1

    return [
        {
            "day": day,
            "messages": data["messages"],
            "sessions": len(data["sessions"]),
            "answered": data["answered"],
            "unanswered": data["unanswered"],
        }
        for day, data in sorted(by_day.items())
    ]


async def get_hourly_activity(db: AsyncSession, days: int) -> list[dict]:
    """Message volume and AI spend bucketed by hour of day (UTC, 00-23),
    summed across the last `days` calendar days — "what time of day is this
    thing busiest," not a per-day series. Messages and cost come from two
    separate tables (ChatLog / AIUsageLog) so they're aggregated independently
    and merged by hour, the same two-source-by-hour approach as
    sawo-chatbot's admin analytics endpoint."""
    since = _days_ago_naive_utc(days)

    message_rows = (
        await db.execute(
            select(ChatLog.created_at).where(ChatLog.created_at >= since)
        )
    ).scalars().all()
    cost_rows = (
        await db.execute(
            select(AIUsageLog.created_at, AIUsageLog.cost_usd).where(AIUsageLog.created_at >= since)
        )
    ).all()

    messages_by_hour: dict[str, int] = defaultdict(int)
    for created_at in message_rows:
        messages_by_hour[created_at.strftime("%H")] += 1

    cost_by_hour: dict[str, float] = defaultdict(float)
    for created_at, cost_usd in cost_rows:
        cost_by_hour[created_at.strftime("%H")] += float(cost_usd or 0.0)

    return [
        {"hour": hour, "messages": messages_by_hour.get(hour, 0), "cost_usd": round(cost_by_hour.get(hour, 0.0), 6)}
        for hour in (f"{h:02d}" for h in range(24))
    ]


async def get_confidence_buckets(
    db: AsyncSession, days: int, off_topic_threshold: float, confidence_threshold: float
) -> list[dict]:
    since = _days_ago_naive_utc(days)
    rows = (
        await db.execute(
            select(ChatLog.confidence_score).where(
                ChatLog.created_at >= since, ChatLog.confidence_score.is_not(None)
            )
        )
    ).scalars().all()

    low_label = f"Low (< {off_topic_threshold:g})"
    medium_label = f"Medium ({off_topic_threshold:g}–{confidence_threshold:g})"
    high_label = f"High (≥ {confidence_threshold:g})"
    counts = {low_label: 0, medium_label: 0, high_label: 0}

    for score in rows:
        if score < off_topic_threshold:
            counts[low_label] += 1
        elif score < confidence_threshold:
            counts[medium_label] += 1
        else:
            counts[high_label] += 1

    return [{"bucket": label, "count": counts[label]} for label in (high_label, medium_label, low_label)]


async def get_unanswered_by_category(db: AsyncSession, days: int) -> list[dict]:
    since = _days_ago_naive_utc(days)
    rows = (
        await db.execute(
            select(
                Category.id,
                func.coalesce(Category.name, "Uncategorized"),
                func.count(UnansweredQuestion.id),
            )
            .select_from(UnansweredQuestion)
            .outerjoin(Category, Category.id == UnansweredQuestion.category_id)
            .where(UnansweredQuestion.created_at >= since)
            .group_by(Category.id, Category.name)
            .order_by(func.count(UnansweredQuestion.id).desc())
        )
    ).all()
    return [{"category_id": cid, "category_name": name, "count": count} for cid, name, count in rows]


async def get_faq_source_breakdown(db: AsyncSession) -> list[dict]:
    rows = (
        await db.execute(
            select(FAQEntry.source, func.count(FAQEntry.id))
            .group_by(FAQEntry.source)
            .order_by(func.count(FAQEntry.id).desc())
        )
    ).all()
    return [{"source": source, "count": count} for source, count in rows]


async def get_usage_by_feature(db: AsyncSession) -> list[dict]:
    """One row per distinct AI process (feature) that has ever logged a
    request — e.g. "library_ingest", "chat_answer_generation", "faq_dedup" —
    most-costly first. NULL/legacy rows predating the feature column are
    grouped under "other", same coalesce pattern as get_faq_source_breakdown."""
    feature_expr = func.coalesce(AIUsageLog.feature, "other")
    rows = (
        await db.execute(
            select(
                feature_expr.label("feature"),
                func.count(AIUsageLog.id),
                func.coalesce(func.sum(AIUsageLog.total_tokens), 0),
                func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0),
            )
            .group_by(feature_expr)
            .order_by(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0).desc())
        )
    ).all()
    return [
        {
            "feature": feature,
            "requests_total": requests,
            "tokens_total": int(tokens),
            "cost_total_usd": float(cost),
        }
        for feature, requests, tokens, cost in rows
    ]


async def get_content_growth(db: AsyncSession, days: int) -> list[dict]:
    since = _days_ago_naive_utc(days - 1)
    since_day_start = since.replace(hour=0, minute=0, second=0, microsecond=0)

    day_expr = func.date(FAQEntry.created_at)
    rows = (
        await db.execute(
            select(day_expr.label("day"), FAQEntry.source, func.count(FAQEntry.id))
            .where(FAQEntry.created_at >= since_day_start)
            .group_by(day_expr, FAQEntry.source)
        )
    ).all()

    by_day: dict[str, dict[str, int]] = defaultdict(dict)
    today = _today_start_naive_utc()
    for offset in range(days):
        day = (today - timedelta(days=days - 1 - offset)).strftime("%Y-%m-%d")
        by_day[day] = {}

    for day, source, count in rows:
        by_day.setdefault(day, {})[source] = count

    return [
        {"day": day, "by_source": sources, "total": sum(sources.values())}
        for day, sources in sorted(by_day.items())
    ]
