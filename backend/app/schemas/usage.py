from datetime import datetime

from pydantic import BaseModel


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
