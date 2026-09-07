from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngine
from app.ai.ollama_engine import OllamaEngine
from app.ai.openrouter_engine import OpenRouterEngine
from app.core import setting_keys as keys
from app.crud.settings import get_all_settings


async def get_active_engine(db: AsyncSession) -> AIEngine:
    values = await get_all_settings(db)

    ollama_engine = OllamaEngine(
        base_url=values[keys.OLLAMA_BASE_URL],
        embedding_model=values[keys.OLLAMA_EMBEDDING_MODEL],
        generation_model=values[keys.OLLAMA_GENERATION_MODEL],
    )

    engine_choice = values.get(keys.AI_ENGINE, "ollama")
    if engine_choice == "openrouter":
        return OpenRouterEngine(
            api_key=values.get(keys.OPENROUTER_API_KEY, ""),
            model=values.get(keys.OPENROUTER_MODEL, ""),
            ollama_engine=ollama_engine,
        )
    return ollama_engine


async def get_embedding_engine(db: AsyncSession) -> AIEngine:
    """Embeddings always use the Ollama-backed engine regardless of the active
    generation engine, to keep vector dimensions consistent."""
    values = await get_all_settings(db)
    return OllamaEngine(
        base_url=values[keys.OLLAMA_BASE_URL],
        embedding_model=values[keys.OLLAMA_EMBEDDING_MODEL],
        generation_model=values[keys.OLLAMA_GENERATION_MODEL],
    )
