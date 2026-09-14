from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_embedding_engine
from app.models.vault_entry import VaultEntry


def _embedding_text(entry: VaultEntry) -> str:
    return f"{entry.title}\n{entry.content}"


async def embed_vault_entry(db: AsyncSession, entry: VaultEntry) -> None:
    """Called after create/update of a vault entry when memory_enabled is
    True. No-op if memory_enabled is False, since it plays no role in RAG
    until re-enabled."""
    if not entry.memory_enabled:
        return
    engine = await get_embedding_engine(db)
    [vector] = await engine.embed([_embedding_text(entry)])
    entry.embedding = vector


async def reindex_all_vault(db: AsyncSession) -> int:
    engine = await get_embedding_engine(db)
    result = await db.execute(select(VaultEntry).where(VaultEntry.memory_enabled.is_(True)))
    entries = list(result.scalars().all())
    if not entries:
        return 0

    texts = [_embedding_text(entry) for entry in entries]
    vectors = await engine.embed(texts)

    for entry, vector in zip(entries, vectors):
        entry.embedding = vector

    await db.commit()
    return len(entries)
