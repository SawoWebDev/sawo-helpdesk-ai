from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import setting_keys as keys
from app.core.deps import require_admin
from app.crud.settings import get_all_settings
from app.crud.usage import get_usage_by_model, get_usage_daily_for_model, get_usage_totals
from app.db.session import get_db
from app.schemas.usage import DailyUsage, ModelUsageSummary, UsageSummary

router = APIRouter(prefix="/api/usage", tags=["usage"], dependencies=[Depends(require_admin)])


@router.get("/summary", response_model=UsageSummary)
async def summary(db: AsyncSession = Depends(get_db)):
    settings_values = await get_all_settings(db)
    active_model = settings_values.get(keys.OPENROUTER_MODEL, "")
    totals = await get_usage_totals(db)
    return UsageSummary(
        active_model=active_model,
        active_model_is_free=active_model.endswith(":free"),
        **totals,
    )


# NOTE: /models is a static path and must be declared before any dynamic
# /models/{model} route would be added later (same gotcha as elsewhere in
# this app's routers).
@router.get("/models", response_model=list[ModelUsageSummary])
async def models(db: AsyncSession = Depends(get_db)):
    return await get_usage_by_model(db)


@router.get("/models/daily", response_model=list[DailyUsage])
async def model_daily(model: str = Query(...), days: int = Query(14, ge=1, le=90), db: AsyncSession = Depends(get_db)):
    return await get_usage_daily_for_model(db, model, days)
