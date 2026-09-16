from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.ai.factory import get_embedding_engine
from app.core.deps import require_admin, require_agent_or_admin
from app.crud.faq import create_faq, find_duplicate_faq
from app.db.session import get_db
from app.models.chat_log import ChatLog
from app.models.faq import FAQEntry
from app.models.user import User
from app.models.vault_entry import VaultEntry
from app.rag.reindex import embed_entry
from app.schemas.chat_log import ChatLogOut, SessionSummary
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


@router.get("/sessions", response_model=PaginatedResponse)
async def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start_at: datetime | None = Query(None, description="Only sessions active at or after this timestamp"),
    end_at: datetime | None = Query(None, description="Only sessions active at or before this timestamp"),
    db: AsyncSession = Depends(get_db),
):
    """Chat Logs grouped by session — one row per conversation rather than
    per message. Rows with no session_id (pre-dating this feature) are
    excluded here; they're still visible via the flat GET / above."""
    if start_at is not None and end_at is not None and start_at > end_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="start_at must be before end_at"
        )

    filters = [ChatLog.session_id.is_not(None)]
    if start_at is not None:
        filters.append(ChatLog.created_at >= start_at)
    if end_at is not None:
        filters.append(ChatLog.created_at <= end_at)

    total = (
        await db.execute(select(func.count(func.distinct(ChatLog.session_id))).where(*filters))
    ).scalar_one()

    agg_stmt = (
        select(
            ChatLog.session_id,
            func.count(ChatLog.id).label("message_count"),
            func.min(ChatLog.created_at).label("first_at"),
            func.max(ChatLog.created_at).label("last_at"),
        )
        .where(*filters)
        .group_by(ChatLog.session_id)
        .order_by(func.max(ChatLog.created_at).desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    agg_rows = (await db.execute(agg_stmt)).all()
    session_ids = [row.session_id for row in agg_rows]

    # A separate, row-level query just for this page's sessions to get each
    # one's first question and IP — kept apart from the aggregate query above
    # since mixing MIN() and MAX() there makes which row a bare
    # (non-aggregated) column like question_text would come from ambiguous.
    first_rows: dict[str, ChatLog] = {}
    if session_ids:
        detail_result = await db.execute(
            select(ChatLog)
            .where(ChatLog.session_id.in_(session_ids))
            .order_by(ChatLog.session_id, ChatLog.created_at.asc())
        )
        for log in detail_result.scalars():
            first_rows.setdefault(log.session_id, log)

    items = [
        SessionSummary(
            session_id=row.session_id,
            ip_address=first_rows[row.session_id].ip_address if row.session_id in first_rows else None,
            message_count=row.message_count,
            first_question=first_rows[row.session_id].question_text if row.session_id in first_rows else "",
            first_at=row.first_at,
            last_at=row.last_at,
        )
        for row in agg_rows
    ]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/sessions/{session_id}", response_model=list[ChatLogOut])
async def get_session_thread(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ChatLog).where(ChatLog.session_id == session_id).order_by(ChatLog.created_at.asc())
    )
    items = list(result.scalars().all())
    if not items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return items


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
    default for a manually-created FAQ. The source log is then deleted —
    once it's saved as a FAQ there's nothing left to review in Chat Logs."""
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

    question_vector: list[float] | None = None
    try:
        embedding_engine = await get_embedding_engine(db)
        [question_vector] = await embedding_engine.embed([log.question_text])
    except AIEngineError:
        pass  # falls back to the exact-text duplicate check below

    duplicate = await find_duplicate_faq(db, log.question_text, question_vector)
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'A FAQ for this question already exists: "{duplicate.question}"',
        )

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

    await db.delete(log)
    await db.commit()
    await db.refresh(entry)
    return entry
