from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import setting_keys as keys
from app.core.config import settings as env_settings
from app.models.setting import Setting

DEFAULTS: dict[str, str] = {
    keys.AI_ENGINE: env_settings.default_ai_engine,
    keys.OPENROUTER_API_KEY: env_settings.openrouter_api_key,
    keys.OPENROUTER_MODEL: env_settings.openrouter_model,
    keys.OLLAMA_BASE_URL: env_settings.ollama_base_url,
    keys.OLLAMA_GENERATION_MODEL: env_settings.ollama_generation_model,
    keys.OLLAMA_EMBEDDING_MODEL: env_settings.ollama_embedding_model,
    keys.FALLBACK_MESSAGE: env_settings.default_fallback_message,
    keys.CONFIDENCE_THRESHOLD: str(env_settings.default_confidence_threshold),
    keys.TOP_K: str(env_settings.default_top_k),
    keys.OFF_TOPIC_THRESHOLD: str(env_settings.default_off_topic_threshold),
    keys.OFF_TOPIC_MESSAGE: env_settings.default_off_topic_message,
}


async def get_all_settings(db: AsyncSession) -> dict[str, str]:
    result = await db.execute(select(Setting))
    rows = {row.key: row.value for row in result.scalars().all()}
    merged = dict(DEFAULTS)
    merged.update(rows)
    return merged


async def get_setting(db: AsyncSession, key: str) -> str:
    result = await db.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row is not None:
        return row.value
    return DEFAULTS.get(key, "")


async def set_setting(db: AsyncSession, key: str, value: str) -> Setting:
    result = await db.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        row = Setting(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    await db.commit()
    await db.refresh(row)
    return row


async def set_settings_bulk(db: AsyncSession, values: dict[str, str]) -> None:
    for key, value in values.items():
        result = await db.execute(select(Setting).where(Setting.key == key))
        row = result.scalar_one_or_none()
        if row is None:
            db.add(Setting(key=key, value=value))
        else:
            row.value = value
    await db.commit()


async def seed_default_settings(db: AsyncSession) -> None:
    result = await db.execute(select(Setting))
    present_keys = {row.key for row in result.scalars().all()}
    for key, value in DEFAULTS.items():
        if key not in present_keys:
            db.add(Setting(key=key, value=value))
    await db.commit()
