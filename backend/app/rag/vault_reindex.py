from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_embedding_engine
from app.db.vec_store import VAULT_VEC_TABLE, upsert_embedding
from app.models.vault_entry import VaultEntry
from app.services.ai_usage import FEATURE_VAULT_REINDEX, feature_context


def _embedding_text(entry: VaultEntry) -> str:
    return f"{entry.title}\n{entry.content}"


async def embed_vault_entry(db: AsyncSession, entry: VaultEntry) -> None:
    """Called after create/update of a vault entry when memory_enabled is
    True. No-op if memory_enabled is False, since it plays no role in RAG
    until re-enabled."""
    if not entry.memory_enabled:
        return
    engine = await get_embedding_engine(db)
    with feature_context(FEATURE_VAULT_REINDEX):
        [vector] = await engine.embed([_embedding_text(entry)])
    await upsert_embedding(db, VAULT_VEC_TABLE, entry.id, vector)
    entry.has_embedding = True


async def reindex_all_vault(db: AsyncSession) -> int:
    engine = await get_embedding_engine(db)
    result = await db.execute(select(VaultEntry).where(VaultEntry.memory_enabled.is_(True)))
    entries = list(result.scalars().all())
    if not entries:
        return 0

    texts = [_embedding_text(entry) for entry in entries]
    with feature_context(FEATURE_VAULT_REINDEX):
        vectors = await engine.embed(texts)

    for entry, vector in zip(entries, vectors):
        await upsert_embedding(db, VAULT_VEC_TABLE, entry.id, vector)
        entry.has_embedding = True

    await db.commit()
    return len(entries)
