from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.ai.factory import get_embedding_engine
from app.core.deps import require_admin, require_agent_or_admin
from app.crud.faq import create_faq, find_duplicate_faq
from app.db.session import get_db
from app.models.ai_usage_log import AIUsageLog
from app.models.chat_log import ChatLog
from app.models.faq import FAQEntry
from app.models.user import User
from app.models.vault_entry import VaultEntry
from app.rag.reindex import embed_entry
from app.schemas.chat_log import ChatLogOut, DeleteSessionsRequest, SessionSummary, SessionUsageOut
from app.schemas.common import PaginatedResponse
from app.schemas.faq import FAQOut
from app.services.ai_usage import FEATURE_FAQ_DEDUP, feature_context

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
    search: str | None = Query(None, description="Matches question or answer text (case-insensitive)"),
    start_at: datetime | None = Query(None, description="Only sessions with activity at or after this timestamp"),
    end_at: datetime | None = Query(None, description="Only sessions with activity at or before this timestamp"),
    db: AsyncSession = Depends(get_db),
):
    """Chat Logs grouped by session — one row per conversation rather than
    per message. Rows with no session_id (pre-dating this feature) are
    excluded here; they're still visible via the flat GET / above.

    Search and date range each independently narrow which SESSIONS qualify
    (a session qualifies if ANY of its messages matches), but the returned
    message_count/first_at/last_at/cost are always computed over that
    session's full history — not just the matching rows. A session with one
    match from a month ago still reports its true, current message count."""
    if start_at is not None and end_at is not None and start_at > end_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="start_at must be before end_at"
        )

    qualifying = select(ChatLog.session_id).where(ChatLog.session_id.is_not(None)).distinct()
    if search:
        like = f"%{search}%"
        qualifying = qualifying.where(or_(ChatLog.question_text.ilike(like), ChatLog.answer_text.ilike(like)))
    if start_at is not None:
        qualifying = qualifying.where(ChatLog.created_at >= start_at)
    if end_at is not None:
        qualifying = qualifying.where(ChatLog.created_at <= end_at)
    qualifying_subq = qualifying.subquery()

    total = (await db.execute(select(func.count()).select_from(qualifying_subq))).scalar_one()

    agg_stmt = (
        select(
            ChatLog.session_id,
            func.count(ChatLog.id).label("message_count"),
            func.min(ChatLog.created_at).label("first_at"),
            func.max(ChatLog.created_at).label("last_at"),
        )
        .where(ChatLog.session_id.in_(select(qualifying_subq.c.session_id)))
        .group_by(ChatLog.session_id)
        .order_by(func.max(ChatLog.created_at).desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    agg_rows = (await db.execute(agg_stmt)).all()
    session_ids = [row.session_id for row in agg_rows]

    first_rows: dict[str, ChatLog] = {}
    match_counts: dict[str, int] = {}
    preview_texts: dict[str, str] = {}
    cost_by_session: dict[str, float] = {}
    if session_ids:
        # All messages for this page's sessions in one query — used both for
        # first_question/IP (existing behavior) and, when searching, to
        # count matches and pick a preview excerpt per session in Python
        # rather than a second round trip.
        detail_result = await db.execute(
            select(ChatLog)
            .where(ChatLog.session_id.in_(session_ids))
            .order_by(ChatLog.session_id, ChatLog.created_at.asc())
        )
        for log in detail_result.scalars():
            first_rows.setdefault(log.session_id, log)
            if search:
                matched_question = search.lower() in log.question_text.lower()
                matched_answer = search.lower() in log.answer_text.lower()
                if matched_question or matched_answer:
                    match_counts[log.session_id] = match_counts.get(log.session_id, 0) + 1
                    preview_texts.setdefault(
                        log.session_id, log.question_text if matched_question else log.answer_text
                    )

        cost_rows = await db.execute(
            select(AIUsageLog.session_id, func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0))
            .where(AIUsageLog.session_id.in_(session_ids))
            .group_by(AIUsageLog.session_id)
        )
        cost_by_session = {sid: float(cost) for sid, cost in cost_rows.all()}

    items = [
        SessionSummary(
            session_id=row.session_id,
            ip_address=first_rows[row.session_id].ip_address if row.session_id in first_rows else None,
            message_count=row.message_count,
            first_question=first_rows[row.session_id].question_text if row.session_id in first_rows else "",
            first_at=row.first_at,
            last_at=row.last_at,
            session_cost_usd=cost_by_session.get(row.session_id, 0.0),
            match_count=match_counts.get(row.session_id) if search else None,
            preview_text=preview_texts.get(row.session_id) if search else None,
        )
        for row in agg_rows
    ]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sessions(
    payload: DeleteSessionsRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Bulk-delete selected conversations. AIUsageLog rows for these sessions
    are left in place — they're a cost ledger of AI spend that already
    happened, not conversation content, so deleting the transcript doesn't
    retroactively erase what it cost."""
    if not payload.session_ids:
        return
    await db.execute(ChatLog.__table__.delete().where(ChatLog.session_id.in_(payload.session_ids)))
    await db.commit()


@router.get("/sessions/{session_id}/usage", response_model=list[SessionUsageOut])
async def get_session_usage(session_id: str, db: AsyncSession = Depends(get_db)):
    """Every AI call (embedding + generation) made while answering questions
    in this session — the raw data behind the Chat Logs consumption view.
    Empty for sessions logged before session-linked usage tracking existed,
    or where every AI call in the conversation failed before a reply came
    back (record_usage only ever writes on a successful response)."""
    result = await db.execute(
        select(AIUsageLog).where(AIUsageLog.session_id == session_id).order_by(AIUsageLog.created_at.asc())
    )
    return result.scalars().all()


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
        with feature_context(FEATURE_FAQ_DEDUP):
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
