from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.chat_log import ChatLog
from app.rag.pipeline import answer_question
from app.schemas.chat_log import ChatFeedbackRequest, ChatRequest, ChatResponse
from app.services.faq_promotion import promote_answer_to_draft

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _get_client_ip(request: Request) -> str | None:
    """Best-effort visitor IP. This app's /api/* traffic is proxied through
    the Next.js frontend (browser -> Next route handler -> FastAPI) with no
    reverse proxy of its own, so request.client.host here would just be the
    frontend container's address — not the visitor's. The frontend proxy
    forwards X-Forwarded-For when it can determine it; fall back to
    request.client.host for any direct (non-proxied) caller."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty")

    result = await answer_question(
        db, question, session_id=payload.session_id, ip_address=_get_client_ip(request)
    )

    if result.promotion is not None:
        background_tasks.add_task(
            promote_answer_to_draft,
            question=result.promotion.question,
            answer=result.promotion.answer,
            image_urls=result.promotion.image_urls,
            reference_urls=result.promotion.reference_urls,
            source_id=result.promotion.source_id,
            query_vector=result.promotion.query_vector,
        )

    return ChatResponse(
        answer=result.answer,
        is_fallback=result.is_fallback,
        confidence_score=result.confidence_score,
        matched_faq_ids=result.matched_faq_ids,
        matched_vault_ids=result.matched_vault_ids,
        image_urls=result.image_urls,
        reference_urls=result.reference_urls,
        chat_log_id=result.chat_log_id,
        low_confidence=result.low_confidence,
    )


@router.post("/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def feedback(payload: ChatFeedbackRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ChatLog).where(ChatLog.id == payload.chat_log_id))
    chat_log = result.scalar_one_or_none()
    # 404 rather than 403 on a session mismatch, so a chat_log_id can't be
    # probed to learn whether it exists — this endpoint has no auth (the
    # chat itself doesn't either), so the session check is the only thing
    # stopping one visitor from rating another's conversation.
    if chat_log is None or chat_log.session_id != payload.session_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat log not found")

    chat_log.rating = payload.rating
    chat_log.rated_at = datetime.now(timezone.utc)
    await db.commit()
