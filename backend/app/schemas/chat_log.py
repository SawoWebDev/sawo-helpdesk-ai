from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Reasons offered when a staff member marks a reply "not helpful" or files a
# report. Kept as a plain str field (not a strict Literal) on the wire so an
# older/newer client sending an unrecognized value never 422s the request —
# reason is supplementary context, not something worth failing feedback over.
FEEDBACK_REASONS = (
    "incorrect_information",
    "outdated_information",
    "did_not_answer",
    "wrong_product_or_model",
    "other",
)


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
    rating: str | None
    rated_at: datetime | None
    feedback_reason: str | None = None
    created_at: datetime


class ChatRequest(BaseModel):
    question: str
    session_id: str
    # Private conversation this message belongs to; omitted/None for the
    # first message of a new conversation (the server creates one and
    # reports its id back once the turn is actually logged).
    conversation_id: int | None = None


class ChatResponse(BaseModel):
    answer: str
    is_fallback: bool
    confidence_score: float | None
    matched_faq_ids: list[int]
    matched_vault_ids: list[int]
    image_urls: list[str]
    reference_urls: list[str]
    chat_log_id: int | None = None
    low_confidence: bool = False
    # None when this turn wasn't logged (e.g. off-topic chatter) and no
    # conversation exists yet to attach it to.
    conversation_id: int | None = None
    conversation_title: str | None = None


class ChatFeedbackRequest(BaseModel):
    chat_log_id: int
    session_id: str
    rating: Literal["up", "down"]
    # Only meaningful for rating == "down"; ignored (stored as None) otherwise.
    reason: str | None = Field(default=None, max_length=40)


class ChatReportRequest(BaseModel):
    chat_log_id: int
    session_id: str
    # Snapshotted from what the client actually rendered for this reply,
    # rather than re-derived server-side, so a report always reflects exactly
    # what the staff member saw.
    question_text: str
    answer_text: str
    reference_urls: list[str] = []
    reason: str | None = Field(default=None, max_length=40)
    comment: str | None = Field(default=None, max_length=2000)


class ChatReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_log_id: int
    session_id: str
    question_text: str
    answer_text: str
    reference_urls: list[str]
    reason: str | None
    comment: str | None
    status: str
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None


class PopularQuestion(BaseModel):
    question: str
    source: Literal["usage", "faq"]


class PopularQuestionsOut(BaseModel):
    items: list[PopularQuestion]
    based_on_usage: bool


class SessionSummary(BaseModel):
    session_id: str
    ip_address: str | None
    message_count: int
    first_question: str
    first_at: datetime
    last_at: datetime
    session_cost_usd: float
    # Only populated when a search term is active: how many messages in this
    # session matched, and the matching row's text (question or answer,
    # whichever matched) to build a highlighted excerpt from client-side.
    match_count: int | None = None
    preview_text: str | None = None


class MessageUsage(BaseModel):
    """AI spend for one side of one message: `question` = embedding the staff
    question (and matching it against saved answers), `answer` = every LLM
    call made to produce the reply (relevance check, generation, fact-check).
    Input/output cost are OpenRouter's own split; None for calls logged
    before that split was recorded."""

    calls: int = 0
    llm_calls: int = 0
    embedding_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    input_cost_usd: float | None = None
    output_cost_usd: float | None = None
    total_cost_usd: float = 0.0
    models: list[str] = []


class ChatLogWithUsageOut(ChatLogOut):
    question_usage: MessageUsage
    answer_usage: MessageUsage


class DeleteSessionsRequest(BaseModel):
    session_ids: list[str]


class SessionUsageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model: str
    is_free: bool
    request_type: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    provider: str | None
    finish_reason: str | None
    latency_ms: int | None
    created_at: datetime
