from pydantic import BaseModel


class UsageSummary(BaseModel):
    active_model: str
    active_model_is_free: bool
    requests_today: int
    tokens_today: int
    requests_total: int
    tokens_total: int
