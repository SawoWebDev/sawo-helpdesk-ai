from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import setting_keys as keys
from app.core.deps import require_admin
from app.crud.settings import get_all_settings
from app.crud.usage import get_usage_totals
from app.db.session import get_db
from app.schemas.usage import UsageSummary

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
