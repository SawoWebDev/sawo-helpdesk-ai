import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.deps import get_owner_hash
from app.crud.analytics import get_popular_questions
from app.db.session import get_db, get_session_factory
from app.models.chat_log import ChatLog
from app.models.chat_report import ChatReport
from app.models.conversation import Conversation
from app.rag.pipeline import RagResult, answer_question
from app.schemas.chat_log import (
    ChatFeedbackRequest,
    ChatReportRequest,
    ChatRequest,
    ChatResponse,
    PopularQuestion,
    PopularQuestionsOut,
)
from app.services.conversation_title import make_conversation_title
from app.services.faq_promotion import promote_answer_to_draft

logger = logging.getLogger(__name__)

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


def _question_or_400(payload: ChatRequest) -> str:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty")
    return question


async def _owned_conversation(db: AsyncSession, conversation_id: int | None, owner_hash: str) -> Conversation | None:
    if conversation_id is None:
        return None
    conv_result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = conv_result.scalar_one_or_none()
    # Same 404 whether the conversation doesn't exist or belongs to
    # someone else, so a conversation_id can't be probed to learn which.
    if conversation is None or conversation.owner_hash != owner_hash:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    owner_hash: str = Depends(get_owner_hash),
):
    question = _question_or_400(payload)
    conversation = await _owned_conversation(db, payload.conversation_id, owner_hash)

    result = await answer_question(
        db, question, session_id=payload.session_id, ip_address=_get_client_ip(request)
    )
    return await _finish_turn(db, result, question, conversation, owner_hash, background_tasks)


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
    owner_hash: str = Depends(get_owner_hash),
):
    """Same turn as POST /api/chat, sent as server-sent events: `delta`
    events carry answer text while it is being written, then exactly one
    `done` event carries the full ChatResponse (whose `answer` is the final
    text and replaces the preview), or one `error` event. Requests that are
    invalid outright (empty question, someone else's conversation) still get
    a plain 400/404 before any stream starts."""
    question = _question_or_400(payload)
    await _owned_conversation(db, payload.conversation_id, owner_hash)
    ip_address = _get_client_ip(request)

    queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

    async def on_delta(text: str) -> None:
        queue.put_nowait(("delta", text))

    async def run_turn() -> None:
        try:
            async with session_factory() as stream_db:
                conversation = await _owned_conversation(stream_db, payload.conversation_id, owner_hash)
                result = await answer_question(
                    stream_db, question, session_id=payload.session_id, ip_address=ip_address, on_delta=on_delta
                )
                body = await _finish_turn(stream_db, result, question, conversation, owner_hash, background_tasks)
            queue.put_nowait(("done", body))
        except Exception:
            logger.exception("Streamed chat turn failed")
            queue.put_nowait(("error", None))

    async def events():
        task = asyncio.create_task(run_turn())
        try:
            while True:
                kind, value = await queue.get()
                if kind == "delta":
                    yield _sse("delta", {"text": value})
                elif kind == "done":
                    yield _sse("done", value.model_dump(mode="json"))
                    return
                else:
                    yield _sse("error", {"detail": "Something went wrong answering this question."})
                    return
        finally:
            # The client went away mid-answer: stop paying for generation.
            task.cancel()

    stream = StreamingResponse(
        events(),
        media_type="text/event-stream",
        # no-transform stops gzip in the Next.js proxy from holding pieces
        # back to compress them; X-Accel-Buffering does the same for nginx.
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
    # Returning a Response directly skips FastAPI's copying of headers set on
    # the injected `response` — including get_owner_hash's first-visit cookie.
    for cookie in response.headers.getlist("set-cookie"):
        stream.headers.append("set-cookie", cookie)
    return stream


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _finish_turn(
    db: AsyncSession,
    result: RagResult,
    question: str,
    conversation: Conversation | None,
    owner_hash: str,
    background_tasks: BackgroundTasks,
) -> ChatResponse:
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

    # Only attach/create a conversation once this turn is actually logged
    # (off-topic chatter isn't) — otherwise a brand-new, never-answered
    # conversation would show up as an empty entry in the sidebar.
    if result.chat_log_id is not None:
        if conversation is None:
            conversation = Conversation(owner_hash=owner_hash, title=make_conversation_title(question))
            db.add(conversation)
            await db.flush()
        conversation.updated_at = datetime.now(timezone.utc)
        await db.execute(
            update(ChatLog).where(ChatLog.id == result.chat_log_id).values(conversation_id=conversation.id)
        )
        await db.commit()

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
        conversation_id=conversation.id if conversation is not None else None,
        conversation_title=conversation.title if conversation is not None else None,
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
    chat_log.feedback_reason = payload.reason if payload.rating == "down" else None
    await db.commit()


@router.post("/report", status_code=status.HTTP_204_NO_CONTENT)
async def report_answer(payload: ChatReportRequest, db: AsyncSession = Depends(get_db)):
    """Staff-submitted "report a problem" for one reply. Same no-probing
    rationale as /feedback: a chat_log_id must be paired with the session_id
    that produced it, since this endpoint has no auth of its own."""
    result = await db.execute(select(ChatLog).where(ChatLog.id == payload.chat_log_id))
    chat_log = result.scalar_one_or_none()
    if chat_log is None or chat_log.session_id != payload.session_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat log not found")

    db.add(
        ChatReport(
            chat_log_id=payload.chat_log_id,
            session_id=payload.session_id,
            question_text=payload.question_text,
            answer_text=payload.answer_text,
            reference_urls=payload.reference_urls,
            reason=payload.reason,
            comment=payload.comment,
        )
    )
    await db.commit()


@router.get("/popular-questions", response_model=PopularQuestionsOut)
async def popular_questions(limit: int = Query(4, ge=1, le=10), db: AsyncSession = Depends(get_db)):
    items, based_on_usage = await get_popular_questions(db, limit)
    return PopularQuestionsOut(
        items=[PopularQuestion(**item) for item in items], based_on_usage=based_on_usage
    )
