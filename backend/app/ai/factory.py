from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngine
from app.ai.openrouter_engine import OpenRouterEngine
from app.core import setting_keys as keys
from app.crud.settings import get_all_settings


async def get_active_engine(db: AsyncSession) -> AIEngine:
    values = await get_all_settings(db)
    return OpenRouterEngine(
        api_key=values.get(keys.OPENROUTER_API_KEY, ""),
        model=values.get(keys.OPENROUTER_MODEL, ""),
        embedding_model=values.get(keys.OPENROUTER_EMBEDDING_MODEL, ""),
    )


async def get_embedding_engine(db: AsyncSession) -> AIEngine:
    return await get_active_engine(db)
