from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.rag.pipeline import answer_question
from app.schemas.chat_log import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: AsyncSession = Depends(get_db)):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Question cannot be empty")

    result = await answer_question(db, question)
    return ChatResponse(
        answer=result.answer,
        is_fallback=result.is_fallback,
        confidence_score=result.confidence_score,
        matched_faq_ids=result.matched_faq_ids,
        matched_vault_ids=result.matched_vault_ids,
        image_urls=result.image_urls,
        reference_urls=result.reference_urls,
    )
