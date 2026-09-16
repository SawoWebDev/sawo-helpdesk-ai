from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_text: str
    answer_text: str
    matched_faq_ids: list[int]
    matched_vault_ids: list[int]
    confidence_score: float | None
    engine_used: str
    session_id: str | None
    ip_address: str | None
    created_at: datetime


class ChatRequest(BaseModel):
    question: str
    session_id: str


class ChatResponse(BaseModel):
    answer: str
    is_fallback: bool
    confidence_score: float | None
    matched_faq_ids: list[int]
    matched_vault_ids: list[int]
    image_urls: list[str]
    reference_urls: list[str]


class SessionSummary(BaseModel):
    session_id: str
    ip_address: str | None
    message_count: int
    first_question: str
    first_at: datetime
    last_at: datetime
