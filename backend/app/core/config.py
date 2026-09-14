from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "sqlite+aiosqlite:///./helpdesk.db"

    # Auth
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 12

    # Initial admin seed
    initial_admin_username: str = "admin"
    initial_admin_password: str = "changeme123"
    initial_admin_email: str | None = "admin@example.com"

    # Uploads
    upload_dir: str = "uploads"
    max_upload_size_bytes: int = 5 * 1024 * 1024
    allowed_image_extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".gif", ".webp")

    # Harvester uploads (separate limits from FAQ image uploads above)
    max_harvest_upload_size_bytes: int = 25 * 1024 * 1024
    allowed_pdf_extensions: tuple[str, ...] = (".pdf",)
    max_vault_entry_chars: int = 50_000

    # AI engine defaults (used only for first-boot Settings seed; live config is in DB)
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3-70b-instruct"
    openrouter_embedding_model: str = "openai/text-embedding-3-small"

    default_fallback_message: str = (
        "Thanks for your question — we've taken note of it and will follow up "
        "once we have an answer."
    )
    default_confidence_threshold: float = 0.75
    default_top_k: int = 5
    # Below this similarity, a question is treated as off-topic chatter (greetings,
    # small talk) rather than a genuine unanswered support question: it gets the
    # off-topic redirect message and is not logged for agent review.
    default_off_topic_threshold: float = 0.35
    default_off_topic_message: str = (
        "I'm here to help with product and technical support questions — "
        "what can I help you with?"
    )

    embedding_dimensions: int = 1536

    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
