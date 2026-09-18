import math

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.ai.factory import get_embedding_engine
from app.db.vec_store import FAQ_VEC_TABLE, delete_embedding, knn_search
from app.models.faq import FAQEntry
from app.services.ai_usage import FEATURE_FAQ_DEDUP, feature_context

# How close two questions need to be, by their own question-only embeddings,
# to treat them as the same underlying question (a rephrasing, not just a
# topically related one) for duplicate-prevention purposes. Deliberately
# stricter than the RAG confidence_threshold (which judges "close enough to
# answer from"), since here a false positive silently discards a FAQ the
# admin/auto-save wanted to create.
DUPLICATE_SIMILARITY_THRESHOLD = 0.88

# How many nearest neighbors to pull from the FAQ vector index as candidates
# before re-scoring them precisely. The index itself is keyed on
# question+answer text (see reindex._embedding_text), which is the right
# representation for RAG retrieval but not for judging "is this the same
# question" — a candidate can rank lower there than its true question-only
# similarity, so the net is cast wider than the final decision needs.
DUPLICATE_CANDIDATE_POOL = 5


async def get_faq(db: AsyncSession, faq_id: int) -> FAQEntry | None:
    result = await db.execute(select(FAQEntry).where(FAQEntry.id == faq_id))
    return result.scalar_one_or_none()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def find_duplicate_faq(
    db: AsyncSession,
    question: str,
    question_vector: list[float] | None = None,
    exclude_id: int | None = None,
) -> FAQEntry | None:
    """Finds an existing FAQ that's either an exact (case/whitespace
    insensitive) match for `question`, or — if `question_vector` is given —
    semantically near-identical to it. Only considers published FAQs, since
    a draft isn't live yet and re-saving over it is fine. Used to keep FAQ
    unique per question, whether saved manually or auto-saved from chat.
    `exclude_id` skips a given FAQ's own row, for checking an edit against
    every *other* FAQ."""
    normalized = question.strip().lower()
    exact_stmt = select(FAQEntry).where(
        FAQEntry.status == "published", func.lower(func.trim(FAQEntry.question)) == normalized
    )
    if exclude_id is not None:
        exact_stmt = exact_stmt.where(FAQEntry.id != exclude_id)
    exact = await db.execute(exact_stmt)
    match = exact.scalars().first()
    if match is not None:
        return match

    if question_vector is None:
        return None

    pool_size = DUPLICATE_CANDIDATE_POOL + (1 if exclude_id is not None else 0)
    hits = await knn_search(db, FAQ_VEC_TABLE, question_vector, limit=pool_size)
    candidate_ids = [entry_id for entry_id, _similarity in hits if entry_id != exclude_id]
    if not candidate_ids:
        return None

    result = await db.execute(
        select(FAQEntry).where(FAQEntry.id.in_(candidate_ids), FAQEntry.status == "published")
    )
    candidates = list(result.scalars().all())
    if not candidates:
        return None

    try:
        embedding_engine = await get_embedding_engine(db)
        with feature_context(FEATURE_FAQ_DEDUP):
            candidate_vectors = await embedding_engine.embed([c.question for c in candidates])
    except AIEngineError:
        return None

    best_match: FAQEntry | None = None
    best_similarity = 0.0
    for candidate, candidate_vector in zip(candidates, candidate_vectors):
        similarity = _cosine_similarity(question_vector, candidate_vector)
        if similarity >= DUPLICATE_SIMILARITY_THRESHOLD and similarity > best_similarity:
            best_match = candidate
            best_similarity = similarity
    return best_match


async def list_faqs(
    db: AsyncSession,
    page: int,
    page_size: int,
    category_id: int | None = None,
    search: str | None = None,
    status_filter: str | None = None,
) -> tuple[list[FAQEntry], int]:
    stmt = select(FAQEntry)
    count_stmt = select(func.count(FAQEntry.id))

    if category_id is not None:
        stmt = stmt.where(FAQEntry.category_id == category_id)
        count_stmt = count_stmt.where(FAQEntry.category_id == category_id)

    if status_filter is not None:
        stmt = stmt.where(FAQEntry.status == status_filter)
        count_stmt = count_stmt.where(FAQEntry.status == status_filter)

    if search:
        like = f"%{search}%"
        condition = or_(FAQEntry.question.ilike(like), FAQEntry.answer.ilike(like))
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(FAQEntry.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def list_faqs_all(
    db: AsyncSession,
    category_id: int | None = None,
    search: str | None = None,
) -> list[FAQEntry]:
    """Unpaginated variant of list_faqs, for export."""
    stmt = select(FAQEntry)

    if category_id is not None:
        stmt = stmt.where(FAQEntry.category_id == category_id)

    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(FAQEntry.question.ilike(like), FAQEntry.answer.ilike(like)))

    stmt = stmt.order_by(FAQEntry.updated_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_faq(
    db: AsyncSession,
    question: str,
    answer: str,
    category_id: int | None,
    image_urls: list[str],
    reference_urls: list[str],
    source: str = "manual",
    source_label: str | None = None,
    source_id: int | None = None,
    status: str = "published",
) -> FAQEntry:
    entry = FAQEntry(
        question=question,
        answer=answer,
        category_id=category_id,
        image_urls=image_urls,
        reference_urls=reference_urls,
        source=source,
        source_label=source_label,
        source_id=source_id,
        status=status,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def delete_faq(db: AsyncSession, entry: FAQEntry) -> None:
    await delete_embedding(db, FAQ_VEC_TABLE, entry.id)
    await db.delete(entry)
    await db.commit()
