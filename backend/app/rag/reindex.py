from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_embedding_engine
from app.db.vec_store import FAQ_VEC_TABLE, delete_embedding, upsert_embedding
from app.models.faq import FAQEntry
from app.services.ai_usage import FEATURE_FAQ_REINDEX, feature_context

# Caps how many entries go into a single embeddings API call. Without this, a
# full reindex sends the entire KB's text as one HTTP request and commits
# once at the end — the request grows unbounded with KB size, and a
# timeout/failure minutes in loses all progress, not just the current batch.
# Chunking bounds both, and per-batch commits mean a failure partway through
# only costs that batch — a re-run only has the remaining stale rows to redo.
REINDEX_BATCH_SIZE = 50


def _embedding_text(entry: FAQEntry) -> str:
    return f"{entry.question}\n{entry.answer}"


async def _embed_entries(db: AsyncSession, entries: list[FAQEntry]) -> int:
    if not entries:
        return 0
    engine = await get_embedding_engine(db)
    for start in range(0, len(entries), REINDEX_BATCH_SIZE):
        batch = entries[start : start + REINDEX_BATCH_SIZE]
        texts = [_embedding_text(entry) for entry in batch]
        with feature_context(FEATURE_FAQ_REINDEX):
            vectors = await engine.embed(texts)
        for entry, vector in zip(batch, vectors):
            await upsert_embedding(db, FAQ_VEC_TABLE, entry.id, vector)
            entry.has_embedding = True
        await db.commit()
    return len(entries)


async def reindex_all(db: AsyncSession) -> int:
    """Force re-embed every published FAQ entry regardless of its current
    has_embedding state — the manual "Reindex All" admin action, e.g. after
    switching embedding models."""
    result = await db.execute(select(FAQEntry).where(FAQEntry.status == "published"))
    return await _embed_entries(db, list(result.scalars().all()))


async def reindex_stale_faq(db: AsyncSession) -> int:
    """Re-embed only published FAQ entries still missing an embedding — the
    boot-time repair path (see reindex_stale.py). Re-running reindex_all
    there would re-embed the whole KB just because one entry is stale."""
    result = await db.execute(
        select(FAQEntry).where(FAQEntry.status == "published", FAQEntry.has_embedding.is_(False))
    )
    return await _embed_entries(db, list(result.scalars().all()))


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
