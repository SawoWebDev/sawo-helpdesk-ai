from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UnansweredOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_text: str
    status: str
    category_id: int | None
    confidence_score: float | None
    created_at: datetime
    resolved_at: datetime | None
    resulting_faq_id: int | None


class UnansweredResolveRequest(BaseModel):
    answer: str
    category_id: int | None = None
    image_urls: list[str] = []
    reference_urls: list[str] = []


class UnansweredAssignCategoryRequest(BaseModel):
    category_id: int | None = None
