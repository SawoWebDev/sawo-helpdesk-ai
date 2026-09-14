from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FAQBase(BaseModel):
    question: str
    answer: str
    category_id: int | None = None
    image_urls: list[str] = []
    reference_urls: list[str] = []


class FAQCreate(FAQBase):
    pass


class FAQUpdate(BaseModel):
    question: str | None = None
    answer: str | None = None
    category_id: int | None = None
    image_urls: list[str] | None = None
    reference_urls: list[str] | None = None
    status: str | None = None


class FAQOut(FAQBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    source_label: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
