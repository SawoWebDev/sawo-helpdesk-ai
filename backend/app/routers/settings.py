from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import setting_keys as keys
from app.core.deps import require_admin
from app.crud.settings import get_all_settings, set_settings_bulk
from app.db.session import get_db
from app.schemas.settings import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_admin)])

MASK = "********"


def _to_out(values: dict[str, str]) -> SettingsOut:
    api_key = values.get(keys.OPENROUTER_API_KEY, "")
    return SettingsOut(
        ai_engine=values.get(keys.AI_ENGINE, "ollama"),
        openrouter_api_key=MASK if api_key else "",
        openrouter_model=values.get(keys.OPENROUTER_MODEL, ""),
        ollama_base_url=values.get(keys.OLLAMA_BASE_URL, ""),
        ollama_generation_model=values.get(keys.OLLAMA_GENERATION_MODEL, ""),
        ollama_embedding_model=values.get(keys.OLLAMA_EMBEDDING_MODEL, ""),
        ollama_vision_model=values.get(keys.OLLAMA_VISION_MODEL, ""),
        fallback_message=values.get(keys.FALLBACK_MESSAGE, ""),
        confidence_threshold=float(values.get(keys.CONFIDENCE_THRESHOLD, "0.75")),
        top_k=int(values.get(keys.TOP_K, "5")),
        off_topic_threshold=float(values.get(keys.OFF_TOPIC_THRESHOLD, "0.4")),
        off_topic_message=values.get(keys.OFF_TOPIC_MESSAGE, ""),
    )


@router.get("", response_model=SettingsOut)
async def get_settings(db: AsyncSession = Depends(get_db)):
    values = await get_all_settings(db)
    return _to_out(values)


@router.post("", response_model=SettingsOut)
async def update_settings(payload: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    updates: dict[str, str] = {}

    field_to_key = {
        "ai_engine": keys.AI_ENGINE,
        "openrouter_model": keys.OPENROUTER_MODEL,
        "ollama_base_url": keys.OLLAMA_BASE_URL,
        "ollama_generation_model": keys.OLLAMA_GENERATION_MODEL,
        "ollama_embedding_model": keys.OLLAMA_EMBEDDING_MODEL,
        "ollama_vision_model": keys.OLLAMA_VISION_MODEL,
        "fallback_message": keys.FALLBACK_MESSAGE,
        "confidence_threshold": keys.CONFIDENCE_THRESHOLD,
        "top_k": keys.TOP_K,
        "off_topic_threshold": keys.OFF_TOPIC_THRESHOLD,
        "off_topic_message": keys.OFF_TOPIC_MESSAGE,
    }

    for field_name, key in field_to_key.items():
        if field_name in payload.model_fields_set:
            value = getattr(payload, field_name)
            if value is not None:
                updates[key] = str(value)

    # Only overwrite the API key if the admin actually typed a new (unmasked) value.
    if "openrouter_api_key" in payload.model_fields_set:
        value = payload.openrouter_api_key
        if value and value != MASK:
            updates[keys.OPENROUTER_API_KEY] = value

    if updates:
        await set_settings_bulk(db, updates)

    values = await get_all_settings(db)
    return _to_out(values)
