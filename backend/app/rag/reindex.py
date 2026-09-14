from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_embedding_engine
from app.db.vec_store import FAQ_VEC_TABLE, upsert_embedding
from app.models.faq import FAQEntry


def _embedding_text(entry: FAQEntry) -> str:
    return f"{entry.question}\n{entry.answer}"


async def reindex_all(db: AsyncSession) -> int:
    engine = await get_embedding_engine(db)
    result = await db.execute(select(FAQEntry))
    entries = list(result.scalars().all())
    if not entries:
        return 0

    texts = [_embedding_text(entry) for entry in entries]
    vectors = await engine.embed(texts)

    for entry, vector in zip(entries, vectors):
        await upsert_embedding(db, FAQ_VEC_TABLE, entry.id, vector)
        entry.has_embedding = True

    await db.commit()
    return len(entries)


async def embed_entry(db: AsyncSession, entry: FAQEntry) -> None:
    engine = await get_embedding_engine(db)
    [vector] = await engine.embed([_embedding_text(entry)])
    await upsert_embedding(db, FAQ_VEC_TABLE, entry.id, vector)
    entry.has_embedding = True
