from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.core.deps import require_admin, require_agent_or_admin
from app.crud.faq import create_faq
from app.db.session import get_db
from app.models.unanswered import UnansweredQuestion
from app.models.user import User
from app.rag.reindex import embed_entry
from app.schemas.common import PaginatedResponse
from app.schemas.unanswered import (
    UnansweredAssignCategoryRequest,
    UnansweredOut,
    UnansweredResolveRequest,
)

router = APIRouter(
    prefix="/api/unanswered", tags=["unanswered"], dependencies=[Depends(require_agent_or_admin)]
)


async def _get_or_404(db: AsyncSession, question_id: int) -> UnansweredQuestion:
    result = await db.execute(select(UnansweredQuestion).where(UnansweredQuestion.id == question_id))
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unanswered question not found")
    return obj


@router.get("", response_model=PaginatedResponse)
async def list_all(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    category_id: int | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(UnansweredQuestion)
    count_stmt = select(func.count(UnansweredQuestion.id))

    if status_filter:
        stmt = stmt.where(UnansweredQuestion.status == status_filter)
        count_stmt = count_stmt.where(UnansweredQuestion.status == status_filter)
    if category_id is not None:
        stmt = stmt.where(UnansweredQuestion.category_id == category_id)
        count_stmt = count_stmt.where(UnansweredQuestion.category_id == category_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(UnansweredQuestion.question_text.ilike(like))
        count_stmt = count_stmt.where(UnansweredQuestion.question_text.ilike(like))

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = (
        stmt.order_by(UnansweredQuestion.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return PaginatedResponse(
        items=[UnansweredOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_all_unanswered(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    await db.execute(UnansweredQuestion.__table__.delete())
    await db.commit()


@router.put("/{question_id}/category", response_model=UnansweredOut)
async def assign_category(
    question_id: int, payload: UnansweredAssignCategoryRequest, db: AsyncSession = Depends(get_db)
):
    obj = await _get_or_404(db, question_id)
    obj.category_id = payload.category_id
    await db.commit()
    await db.refresh(obj)
    return obj


@router.post("/{question_id}/resolve", response_model=UnansweredOut)
async def resolve(question_id: int, payload: UnansweredResolveRequest, db: AsyncSession = Depends(get_db)):
    obj = await _get_or_404(db, question_id)

    category_id = payload.category_id if payload.category_id is not None else obj.category_id
    faq = await create_faq(
        db,
        question=obj.question_text,
        answer=payload.answer,
        category_id=category_id,
        image_urls=payload.image_urls,
        reference_urls=payload.reference_urls,
        source="manual",
    )
    try:
        await embed_entry(db, faq)
    except AIEngineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(faq)

    obj.status = "answered"
    obj.resolved_at = datetime.now(timezone.utc)
    obj.resulting_faq_id = faq.id
    if payload.category_id is not None:
        obj.category_id = payload.category_id
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(question_id: int, db: AsyncSession = Depends(get_db)):
    obj = await _get_or_404(db, question_id)
    await db.delete(obj)
    await db.commit()
