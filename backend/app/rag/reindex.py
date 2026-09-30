from sqlalchemy import exists, literal_column, select, table, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_embedding_engine
from app.db.vec_store import (
    FAQ_PHRASING_VEC_TABLE,
    FAQ_QUESTION_VEC_TABLE,
    FAQ_VEC_TABLE,
    delete_embedding,
    upsert_embedding,
)
from app.models.faq import FAQEntry
from app.models.faq_phrasing import FAQPhrasing
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
    """Writes both vectors per FAQ — question+answer (RAG retrieval) and
    question-only (saved-answer matching, see rag/saved_answers.py) — from one
    embeddings call per batch."""
    if not entries:
        return 0
    engine = await get_embedding_engine(db)
    for start in range(0, len(entries), REINDEX_BATCH_SIZE):
        batch = entries[start : start + REINDEX_BATCH_SIZE]
        texts = [_embedding_text(entry) for entry in batch] + [entry.question for entry in batch]
        with feature_context(FEATURE_FAQ_REINDEX):
            vectors = await engine.embed(texts)
        for i, entry in enumerate(batch):
            await upsert_embedding(db, FAQ_VEC_TABLE, entry.id, vectors[i])
            await upsert_embedding(db, FAQ_QUESTION_VEC_TABLE, entry.id, vectors[len(batch) + i])
            entry.has_embedding = True
        await db.commit()
    return len(entries)


async def reindex_all(db: AsyncSession) -> int:
    """Force re-embed every published FAQ entry regardless of its current
    has_embedding state — the manual "Reindex All" admin action, e.g. after
    switching embedding models. Phrasings follow, since their vectors must
    come from the same model to be comparable."""
    result = await db.execute(select(FAQEntry).where(FAQEntry.status == "published"))
    count = await _embed_entries(db, list(result.scalars().all()))
    phrasings = (await db.execute(select(FAQPhrasing).where(FAQPhrasing.enabled.is_(True)))).scalars().all()
    await _embed_phrasings(db, list(phrasings))
    return count


async def reindex_stale_faq(db: AsyncSession) -> int:
    """Re-embed only published FAQ entries still missing an embedding — the
    boot-time repair path (see reindex_stale.py). Re-running reindex_all
    there would re-embed the whole KB just because one entry is stale. Also
    covers entries embedded before question-only vectors existed."""
    result = await db.execute(
        select(FAQEntry).where(
            FAQEntry.status == "published",
            (FAQEntry.has_embedding.is_(False)) | (FAQEntry.id.not_in(_question_vec_rowids())),
        )
    )
    count = await _embed_entries(db, list(result.scalars().all()))
    stale_phrasings = (
        await db.execute(
            select(FAQPhrasing).where(FAQPhrasing.enabled.is_(True), FAQPhrasing.has_embedding.is_(False))
        )
    ).scalars().all()
    await _embed_phrasings(db, list(stale_phrasings))
    return count


def _question_vec_rowids():
    return select(literal_column("rowid")).select_from(table(FAQ_QUESTION_VEC_TABLE))


async def has_stale_faq_vectors(db: AsyncSession) -> bool:
    """Whether reindex_stale_faq has anything to do: a published FAQ missing
    either vector, or an enabled phrasing missing its vector."""
    faq_stale = (
        await db.execute(
            select(exists().where(
                FAQEntry.status == "published",
                (FAQEntry.has_embedding.is_(False)) | (FAQEntry.id.not_in(_question_vec_rowids())),
            ))
        )
    ).scalar()
    phrasing_stale = (
        await db.execute(
            select(exists().where(FAQPhrasing.enabled.is_(True), FAQPhrasing.has_embedding.is_(False)))
        )
    ).scalar()
    return bool(faq_stale or phrasing_stale)


async def embed_entry(db: AsyncSession, entry: FAQEntry) -> None:
    """No-op (and removes any existing vec rows) while the entry is a Draft —
    drafts must never be retrievable by RAG until an admin publishes them."""
    if entry.status != "published":
        if entry.has_embedding:
            await delete_embedding(db, FAQ_VEC_TABLE, entry.id)
            entry.has_embedding = False
        await delete_embedding(db, FAQ_QUESTION_VEC_TABLE, entry.id)
        return
    engine = await get_embedding_engine(db)
    with feature_context(FEATURE_FAQ_REINDEX):
        qa_vector, question_vector = await engine.embed([_embedding_text(entry), entry.question])
    await upsert_embedding(db, FAQ_VEC_TABLE, entry.id, qa_vector)
    await upsert_embedding(db, FAQ_QUESTION_VEC_TABLE, entry.id, question_vector)
    entry.has_embedding = True


async def _embed_phrasings(db: AsyncSession, phrasings: list[FAQPhrasing]) -> None:
    if not phrasings:
        return
    engine = await get_embedding_engine(db)
    for start in range(0, len(phrasings), REINDEX_BATCH_SIZE):
        batch = phrasings[start : start + REINDEX_BATCH_SIZE]
        with feature_context(FEATURE_FAQ_REINDEX):
            vectors = await engine.embed([p.phrasing for p in batch])
        for phrasing, vector in zip(batch, vectors):
            await upsert_embedding(db, FAQ_PHRASING_VEC_TABLE, phrasing.id, vector)
            phrasing.has_embedding = True
        await db.commit()


async def embed_phrasing(db: AsyncSession, phrasing: FAQPhrasing) -> None:
    """Disabled phrasings keep no vector, so they can't be matched semantically."""
    if not phrasing.enabled:
        await delete_embedding(db, FAQ_PHRASING_VEC_TABLE, phrasing.id)
        phrasing.has_embedding = False
        return
    engine = await get_embedding_engine(db)
    with feature_context(FEATURE_FAQ_REINDEX):
        [vector] = await engine.embed([phrasing.phrasing])
    await upsert_embedding(db, FAQ_PHRASING_VEC_TABLE, phrasing.id, vector)
    phrasing.has_embedding = True


async def delete_faq_vectors(db: AsyncSession, faq_id: int) -> None:
    """Every vector owned by one FAQ, including its phrasings' — call before
    deleting the FAQ (the phrasing rows themselves go by ON DELETE CASCADE)."""
    await delete_embedding(db, FAQ_VEC_TABLE, faq_id)
    await delete_embedding(db, FAQ_QUESTION_VEC_TABLE, faq_id)
    await db.execute(
        text(f"DELETE FROM {FAQ_PHRASING_VEC_TABLE} WHERE rowid IN (SELECT id FROM faq_phrasings WHERE faq_id = :f)"),
        {"f": faq_id},
    )
