from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_embedding_engine
from app.db.vec_store import VAULT_VEC_TABLE, upsert_embedding
from app.models.vault_entry import VaultEntry
from app.services.ai_usage import FEATURE_VAULT_REINDEX, feature_context

# See reindex.py's REINDEX_BATCH_SIZE for why this exists — same reasoning,
# applied here too since Vault entries can be much larger (up to
# max_vault_entry_chars) than a typical FAQ answer.
REINDEX_BATCH_SIZE = 50


def _embedding_text(entry: VaultEntry) -> str:
    return f"{entry.title}\n{entry.content}"


async def _embed_entries(db: AsyncSession, entries: list[VaultEntry]) -> int:
    if not entries:
        return 0
    engine = await get_embedding_engine(db)
    for start in range(0, len(entries), REINDEX_BATCH_SIZE):
        batch = entries[start : start + REINDEX_BATCH_SIZE]
        texts = [_embedding_text(entry) for entry in batch]
        with feature_context(FEATURE_VAULT_REINDEX):
            vectors = await engine.embed(texts)
        for entry, vector in zip(batch, vectors):
            await upsert_embedding(db, VAULT_VEC_TABLE, entry.id, vector)
            entry.has_embedding = True
        await db.commit()
    return len(entries)


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
    """Force re-embed every memory-enabled vault entry regardless of its
    current has_embedding state — the manual "Reindex All" admin action."""
    result = await db.execute(select(VaultEntry).where(VaultEntry.memory_enabled.is_(True)))
    return await _embed_entries(db, list(result.scalars().all()))


async def reindex_stale_vault(db: AsyncSession) -> int:
    """Re-embed only memory-enabled vault entries still missing an
    embedding — the boot-time repair path (see reindex_stale.py)."""
    result = await db.execute(
        select(VaultEntry).where(VaultEntry.memory_enabled.is_(True), VaultEntry.has_embedding.is_(False))
    )
    return await _embed_entries(db, list(result.scalars().all()))
