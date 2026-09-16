from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.rag.pipeline import answer_question
from app.schemas.chat_log import ChatRequest, ChatResponse

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
async def chat(payload: ChatRequest, request: Request, db: AsyncSession = Depends(get_db)):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty")

    result = await answer_question(
        db, question, session_id=payload.session_id, ip_address=_get_client_ip(request)
    )
    return ChatResponse(
        answer=result.answer,
        is_fallback=result.is_fallback,
        confidence_score=result.confidence_score,
        matched_faq_ids=result.matched_faq_ids,
        matched_vault_ids=result.matched_vault_ids,
        image_urls=result.image_urls,
        reference_urls=result.reference_urls,
    )
