from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UsageSummary(BaseModel):
    active_model: str
    active_model_is_free: bool
    requests_today: int
    tokens_today: int
    requests_total: int
    tokens_total: int


class ModelUsageSummary(BaseModel):
    model: str
    is_free: bool
    requests_total: int
    tokens_total: int
    prompt_tokens_total: int
    completion_tokens_total: int
    cost_total_usd: float
    requests_today: int
    tokens_today: int
    cost_today_usd: float
    last_used_at: datetime | None


class DailyUsage(BaseModel):
    day: str
    requests: int
    tokens: int
    cost_usd: float


class UsageCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model: str
    is_free: bool
    request_type: str
    feature: str | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    provider: str | None
    finish_reason: str | None
    latency_ms: int | None
    session_id: str | None
    created_at: datetime


class OpenRouterBalance(BaseModel):
    configured: bool
    total_credits: float
    total_usage: float
    balance: float
    error: str | None
