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


class LibraryBatchSummaryOut(BaseModel):
    is_batch: bool = True
    job_id: int
    source_count: int
    indexed_count: int
    failed_count: int
    pending_count: int
    category_id: int | None
    created_at: datetime
    generated_faq_count: int
    origin_label: str


class LibraryRowOut(BaseModel):
    """One row in the top-level Library sources table: either a single
    source, or a summary of a batch crawl job. `kind` tells the frontend
    which of `source` / `batch` is populated."""

    kind: str  # "source" | "batch"
    source: LibrarySourceOut | None = None
    batch: LibraryBatchSummaryOut | None = None


class SitemapDiscoverRequest(BaseModel):
    url: str


class SitemapDiscoverResponse(BaseModel):
    urls: list[str]


class LibraryCrawlBatchRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=500)
    category_id: int | None = None
    new_category_name: str | None = None
    auto_generate_faqs: bool = True


class LibraryCrawlBatchResponse(BaseModel):
    queued: int
    source_ids: list[int]


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
    source_url: str | None


class LibraryAnswerSourceOut(BaseModel):
    title: str
    source_url: str | None


class LibrarySearchResponse(BaseModel):
    answer: str | None
    answer_sources: list[LibraryAnswerSourceOut] = []
    results: list[LibrarySearchResult]


class SourceFaqOut(BaseModel):
    id: int
    question: str
    answer: str
    status: str


class JobFaqOut(BaseModel):
    id: int
    question: str
    answer: str
    status: str
    source_id: int
    source_url: str | None
    source_filename: str | None
