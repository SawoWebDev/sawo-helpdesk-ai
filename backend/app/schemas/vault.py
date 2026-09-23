from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VaultEntryBase(BaseModel):
    title: str
    content: str
    category_id: int | None = None
    tags: list[str] = []


class VaultEntryCreate(VaultEntryBase):
    pass


class VaultEntryUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    category_id: int | None = None
    tags: list[str] | None = None
    memory_enabled: bool | None = None
    source_url: str | None = None


class VaultEntryOut(VaultEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    source_id: int | None
    source_url: str | None
    memory_enabled: bool
    created_at: datetime
    updated_at: datetime


class VaultSearchResult(BaseModel):
    entry: VaultEntryOut
    score: float
    excerpt: str
    match_type: str  # "keyword" | "semantic" | "both"


class BulkMemoryToggleRequest(BaseModel):
    entry_ids: list[int]
    enabled: bool


class ChatbotKbEntryOut(BaseModel):
    id: int
    title: str
    content: str
    category_path: str
    memory_enabled: bool
    source_url: str | None
