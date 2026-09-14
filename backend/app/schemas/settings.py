from pydantic import BaseModel


class SettingsOut(BaseModel):
    openrouter_api_key: str
    openrouter_model: str
    openrouter_embedding_model: str
    fallback_message: str
    confidence_threshold: float
    top_k: int
    off_topic_threshold: float
    off_topic_message: str


class SettingsUpdate(BaseModel):
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None
    openrouter_embedding_model: str | None = None
    fallback_message: str | None = None
    confidence_threshold: float | None = None
    top_k: int | None = None
    off_topic_threshold: float | None = None
    off_topic_message: str | None = None
