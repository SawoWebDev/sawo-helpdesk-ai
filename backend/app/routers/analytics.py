from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import setting_keys as keys
from app.core.deps import require_agent_or_admin
from app.crud import analytics as crud
from app.crud.settings import get_all_settings
from app.crud.usage import get_usage_daily_totals
from app.db.session import get_db
from app.schemas.analytics import (
    CategoryBreakdown,
    ChatTrendPoint,
    ConfidenceBucket,
    ContentGrowthPoint,
    FeatureUsage,
    HourlyActivity,
    OverviewStats,
    SourceBreakdown,
)
from app.schemas.usage import DailyUsage

router = APIRouter(
    prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(require_agent_or_admin)]
)


@router.get("/overview", response_model=OverviewStats)
async def overview(db: AsyncSession = Depends(get_db)):
    settings_values = await get_all_settings(db)
    active_model = settings_values.get(keys.OPENROUTER_MODEL, "")
    stats = await crud.get_overview(db)
    return OverviewStats(
        active_model=active_model,
        active_model_is_free=active_model.endswith(":free"),
        **stats,
    )


@router.get("/chat-trend", response_model=list[ChatTrendPoint])
async def chat_trend(days: int = Query(30, ge=1, le=90), db: AsyncSession = Depends(get_db)):
    return await crud.get_chat_trend(db, days)


@router.get("/confidence", response_model=list[ConfidenceBucket])
async def confidence(days: int = Query(30, ge=1, le=90), db: AsyncSession = Depends(get_db)):
    settings_values = await get_all_settings(db)
    off_topic_threshold = float(settings_values[keys.OFF_TOPIC_THRESHOLD])
    confidence_threshold = float(settings_values[keys.CONFIDENCE_THRESHOLD])
    return await crud.get_confidence_buckets(db, days, off_topic_threshold, confidence_threshold)


@router.get("/categories", response_model=list[CategoryBreakdown])
async def categories(days: int = Query(90, ge=1, le=365), db: AsyncSession = Depends(get_db)):
    return await crud.get_unanswered_by_category(db, days)


@router.get("/faq-sources", response_model=list[SourceBreakdown])
async def faq_sources(db: AsyncSession = Depends(get_db)):
    return await crud.get_faq_source_breakdown(db)


@router.get("/content-growth", response_model=list[ContentGrowthPoint])
async def content_growth(days: int = Query(30, ge=1, le=90), db: AsyncSession = Depends(get_db)):
    return await crud.get_content_growth(db, days)


@router.get("/hourly-activity", response_model=list[HourlyActivity])
async def hourly_activity(days: int = Query(30, ge=1, le=90), db: AsyncSession = Depends(get_db)):
    return await crud.get_hourly_activity(db, days)


@router.get("/daily-spend", response_model=list[DailyUsage])
async def daily_spend(days: int = Query(30, ge=1, le=90), db: AsyncSession = Depends(get_db)):
    return await get_usage_daily_totals(db, days)


@router.get("/usage-by-feature", response_model=list[FeatureUsage])
async def usage_by_feature(db: AsyncSession = Depends(get_db)):
    return await crud.get_usage_by_feature(db)
