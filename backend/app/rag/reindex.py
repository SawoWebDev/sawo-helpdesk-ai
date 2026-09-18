from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_embedding_engine
from app.db.vec_store import FAQ_VEC_TABLE, delete_embedding, upsert_embedding
from app.models.faq import FAQEntry
from app.services.ai_usage import FEATURE_FAQ_REINDEX, feature_context


def _embedding_text(entry: FAQEntry) -> str:
    return f"{entry.question}\n{entry.answer}"


async def reindex_all(db: AsyncSession) -> int:
    engine = await get_embedding_engine(db)
    result = await db.execute(select(FAQEntry).where(FAQEntry.status == "published"))
    entries = list(result.scalars().all())
    if not entries:
        return 0

    texts = [_embedding_text(entry) for entry in entries]
    with feature_context(FEATURE_FAQ_REINDEX):
        vectors = await engine.embed(texts)

    for entry, vector in zip(entries, vectors):
        await upsert_embedding(db, FAQ_VEC_TABLE, entry.id, vector)
        entry.has_embedding = True

    await db.commit()
    return len(entries)


async def embed_entry(db: AsyncSession, entry: FAQEntry) -> None:
    """No-op (and removes any existing vec row) while the entry is a Draft —
    drafts must never be retrievable by RAG until an admin publishes them."""
    if entry.status != "published":
        if entry.has_embedding:
            await delete_embedding(db, FAQ_VEC_TABLE, entry.id)
            entry.has_embedding = False
        return
    engine = await get_embedding_engine(db)
    with feature_context(FEATURE_FAQ_REINDEX):
        [vector] = await engine.embed([_embedding_text(entry)])
    await upsert_embedding(db, FAQ_VEC_TABLE, entry.id, vector)
    entry.has_embedding = True
