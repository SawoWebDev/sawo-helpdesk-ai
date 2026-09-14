from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_usage_log import AIUsageLog


async def get_usage_totals(db: AsyncSession) -> dict:
    # SQLite has no real timezone-aware storage: func.now() writes a naive
    # 'YYYY-MM-DD HH:MM:SS' UTC string regardless of the column's
    # DateTime(timezone=True) type, so the comparison value must be naive
    # UTC too or the two won't compare as intended.
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )

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
