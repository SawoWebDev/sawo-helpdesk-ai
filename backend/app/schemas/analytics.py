from pydantic import BaseModel


class OverviewStats(BaseModel):
    chats_today: int
    chats_7d: int
    chats_30d: int
    unique_sessions_7d: int
    answered_rate_7d: float  # 0-100, share of chat_7d messages that matched real content
    unanswered_pending: int
    faq_total: int
    faq_published: int
    ai_cost_today_usd: float
    ai_cost_30d_usd: float
    active_model: str
    active_model_is_free: bool


class ChatTrendPoint(BaseModel):
    day: str
    messages: int
    sessions: int
    answered: int
    unanswered: int


class ConfidenceBucket(BaseModel):
    bucket: str
    count: int


class CategoryBreakdown(BaseModel):
    category_id: int | None
    category_name: str
    count: int


class SourceBreakdown(BaseModel):
    source: str
    count: int


class ContentGrowthPoint(BaseModel):
    day: str
    by_source: dict[str, int]
    total: int
