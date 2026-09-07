from pydantic import BaseModel


class SettingsOut(BaseModel):
    ai_engine: str
    openrouter_api_key: str
    openrouter_model: str
    ollama_base_url: str
    ollama_generation_model: str
    ollama_embedding_model: str
    fallback_message: str
    confidence_threshold: float
    top_k: int
    off_topic_threshold: float
    off_topic_message: str


class SettingsUpdate(BaseModel):
    ai_engine: str | None = None
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None
    ollama_base_url: str | None = None
    ollama_generation_model: str | None = None
    ollama_embedding_model: str | None = None
    fallback_message: str | None = None
    confidence_threshold: float | None = None
    top_k: int | None = None
    off_topic_threshold: float | None = None
    off_topic_message: str | None = None
