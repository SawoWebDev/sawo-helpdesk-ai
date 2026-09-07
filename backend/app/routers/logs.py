from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_agent_or_admin
from app.db.session import get_db
from app.models.chat_log import ChatLog
from app.schemas.chat_log import ChatLogOut
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/api/logs", tags=["logs"], dependencies=[Depends(require_agent_or_admin)])


@router.get("", response_model=PaginatedResponse)
async def list_all(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    total = (await db.execute(select(func.count(ChatLog.id)))).scalar_one()
    result = await db.execute(
        select(ChatLog).order_by(ChatLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = list(result.scalars().all())
    return PaginatedResponse(
        items=[ChatLogOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
