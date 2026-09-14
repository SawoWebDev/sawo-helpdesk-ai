from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.core.deps import require_admin, require_agent_or_admin
from app.crud.faq import create_faq
from app.db.session import get_db
from app.models.chat_log import ChatLog
from app.models.faq import FAQEntry
from app.models.user import User
from app.models.vault_entry import VaultEntry
from app.rag.reindex import embed_entry
from app.schemas.chat_log import ChatLogOut
from app.schemas.common import PaginatedResponse
from app.schemas.faq import FAQOut

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


@router.post("/{log_id}/save-as-faq", response_model=FAQOut, status_code=status.HTTP_201_CREATED)
async def save_log_as_faq(log_id: int, db: AsyncSession = Depends(get_db)):
    """Promotes a real, grounded chat answer into a curated FAQ entry. Only
    logs that actually matched FAQ or Library content are eligible — a
    fallback/off-topic reply always logs empty match lists, so this doubles
    as the "was this a real answer" check. Reference URLs are reconstructed
    from the matched Vault/FAQ entries rather than stored on ChatLog itself,
    since ChatLog only keeps the ids. Published immediately, matching the
    default for a manually-created FAQ."""
    log = await db.get(ChatLog, log_id)
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat log not found")
    if not log.matched_faq_ids and not log.matched_vault_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This log has no matched FAQ/Library content to save from (fallback or off-topic reply).",
        )

    reference_urls: list[str] = []
    if log.matched_vault_ids:
        vault_result = await db.execute(
            select(VaultEntry.source_url).where(VaultEntry.id.in_(log.matched_vault_ids))
        )
        reference_urls.extend(url for url in vault_result.scalars() if url)
    if log.matched_faq_ids:
        faq_result = await db.execute(
            select(FAQEntry.reference_urls).where(FAQEntry.id.in_(log.matched_faq_ids))
        )
        for urls in faq_result.scalars():
            reference_urls.extend(urls or [])
    reference_urls = list(dict.fromkeys(reference_urls))

    entry = await create_faq(
        db,
        question=log.question_text,
        answer=log.answer_text,
        category_id=None,
        image_urls=[],
        reference_urls=reference_urls,
        source="chat_log",
        source_label=f"Chat log #{log.id}",
    )
    try:
        await embed_entry(db, entry)
    except AIEngineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(entry)
    return entry
