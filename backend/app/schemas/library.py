from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LibrarySourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    origin_url: str | None
    original_filename: str | None
    category_id: int | None
    status: str
    error_message: str | None
    extracted_char_count: int | None
    chunk_count: int
    auto_generate_faqs: bool
    faq_generation_status: str | None
    generated_faq_count: int
    created_at: datetime
    processed_at: datetime | None


class LibraryCrawlRequest(BaseModel):
    url: str
    category_id: int | None = None
    new_category_name: str | None = None
    auto_generate_faqs: bool = True


class LibrarySearchRequest(BaseModel):
    query: str
    limit: int = Field(default=20, ge=1, le=100)


class LibrarySearchResult(BaseModel):
    entry_id: int
    title: str
    excerpt: str
    score: float
    match_type: str
    source_id: int | None
    category_id: int | None


class LibrarySearchResponse(BaseModel):
    answer: str | None
    results: list[LibrarySearchResult]
