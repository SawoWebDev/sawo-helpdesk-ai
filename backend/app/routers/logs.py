from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin, require_agent_or_admin
from app.db.session import get_db
from app.models.chat_log import ChatLog
from app.models.user import User
from app.schemas.chat_log import ChatLogOut
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/api/logs", tags=["logs"], dependencies=[Depends(require_agent_or_admin)])


@router.get("", response_model=PaginatedResponse)
async def list_all(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start_at: datetime | None = Query(None, description="Only logs at or after this timestamp"),
    end_at: datetime | None = Query(None, description="Only logs at or before this timestamp"),
    db: AsyncSession = Depends(get_db),
):
    if start_at is not None and end_at is not None and start_at > end_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="start_at must be before end_at"
        )

    stmt = select(ChatLog)
    count_stmt = select(func.count(ChatLog.id))

    if start_at is not None:
        stmt = stmt.where(ChatLog.created_at >= start_at)
        count_stmt = count_stmt.where(ChatLog.created_at >= start_at)
    if end_at is not None:
        stmt = stmt.where(ChatLog.created_at <= end_at)
        count_stmt = count_stmt.where(ChatLog.created_at <= end_at)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(ChatLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = list(result.scalars().all())
    return PaginatedResponse(
        items=[ChatLogOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_all_logs(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    await db.execute(ChatLog.__table__.delete())
    await db.commit()
