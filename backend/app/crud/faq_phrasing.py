"""Staff-reviewed alternate phrasings of a canonical FAQ (models/faq_phrasing.py).

Validation here uses the same identifier and coverage rules the saved-answer
matcher applies at chat time (rag/saved_answers.py), so a phrasing that could
never be served safely is refused when staff try to add it, with the reason,
instead of being stored and silently ignored later."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.db.vec_store import FAQ_PHRASING_VEC_TABLE, delete_embedding
from app.models.faq import FAQEntry
from app.models.faq_phrasing import FAQPhrasing
from app.rag.question_normalize import normalize_question
from app.rag.reindex import embed_phrasing
from app.rag.saved_answers import _language_request, _reply_conflict, asks_for_more
from app.rag.technical_key import compatible, extract_key

MAX_PHRASING_LENGTH = 500


class PhrasingError(Exception):
    """`conflict` = the wording already belongs somewhere (HTTP 409);
    otherwise the wording itself is unacceptable (HTTP 400)."""

    def __init__(self, message: str, conflict: bool = False):
        super().__init__(message)
        self.conflict = conflict


async def list_phrasings(db: AsyncSession, faq_id: int) -> list[FAQPhrasing]:
    result = await db.execute(select(FAQPhrasing).where(FAQPhrasing.faq_id == faq_id).order_by(FAQPhrasing.id))
    return list(result.scalars().all())


async def get_phrasing(db: AsyncSession, faq_id: int, phrasing_id: int) -> FAQPhrasing | None:
    result = await db.execute(
        select(FAQPhrasing).where(FAQPhrasing.id == phrasing_id, FAQPhrasing.faq_id == faq_id)
    )
    return result.scalar_one_or_none()


async def _validate(db: AsyncSession, faq: FAQEntry, phrasing: str, exclude_id: int | None = None) -> str:
    phrasing = (phrasing or "").strip()
    normalized = normalize_question(phrasing)
    if not normalized:
        raise PhrasingError("The phrasing is empty.")
    if len(phrasing) > MAX_PHRASING_LENGTH:
        raise PhrasingError(f"The phrasing is longer than {MAX_PHRASING_LENGTH} characters.")

    if normalized == faq.question_normalized:
        raise PhrasingError("This is the FAQ's own question, so it is already matched.")

    other_faq = (
        await db.execute(
            select(FAQEntry).where(FAQEntry.question_normalized == normalized, FAQEntry.id != faq.id)
        )
    ).scalars().first()
    if other_faq is not None:
        raise PhrasingError(f'This is the question of another FAQ (#{other_faq.id}: "{other_faq.question}").', conflict=True)

    stmt = select(FAQPhrasing).where(FAQPhrasing.phrasing_normalized == normalized)
    if exclude_id is not None:
        stmt = stmt.where(FAQPhrasing.id != exclude_id)
    existing = (await db.execute(stmt)).scalars().first()
    if existing is not None:
        if existing.faq_id == faq.id:
            raise PhrasingError("This phrasing is already added to this FAQ.", conflict=True)
        raise PhrasingError(f"This phrasing is already mapped to FAQ #{existing.faq_id}.", conflict=True)

    phrasing_key = extract_key(phrasing)
    ok, why = compatible(phrasing_key, extract_key(faq.question))
    if not ok:
        raise PhrasingError(f"The phrasing doesn't match this FAQ's question: {why}.")
    more = asks_for_more(phrasing, phrasing_key, faq)
    if more is not None:
        raise PhrasingError(f"The phrasing asks for more than this FAQ answers: {more}.")
    # Would be stored but never served (saved_answers._reply_conflict /
    # _language_request), so refused here with the reason instead.
    unservable = _language_request(phrasing) or _reply_conflict(phrasing, faq)
    if unservable is not None:
        raise PhrasingError(f"This phrasing can't be answered with this FAQ: {unservable}.")
    return phrasing


async def _try_embed(db: AsyncSession, entry: FAQPhrasing) -> None:
    # Exact-match lookup works without a vector; semantic matching of this
    # phrasing waits for the boot-time repair if the embedding API is down.
    try:
        await embed_phrasing(db, entry)
    except AIEngineError:
        entry.has_embedding = False


async def create_phrasing(
    db: AsyncSession, faq: FAQEntry, phrasing: str, created_by_id: int | None, enabled: bool = True
) -> FAQPhrasing:
    phrasing = await _validate(db, faq, phrasing)
    entry = FAQPhrasing(faq_id=faq.id, phrasing=phrasing, enabled=enabled, created_by_id=created_by_id)
    db.add(entry)
    await db.flush()
    await _try_embed(db, entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def update_phrasing(
    db: AsyncSession, faq: FAQEntry, entry: FAQPhrasing, phrasing: str | None, enabled: bool | None
) -> FAQPhrasing:
    text_changed = phrasing is not None and phrasing.strip() != entry.phrasing
    if text_changed:
        entry.phrasing = await _validate(db, faq, phrasing, exclude_id=entry.id)
    if enabled is not None:
        entry.enabled = enabled
    if text_changed or enabled is not None:
        await db.flush()
        await _try_embed(db, entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def delete_phrasing(db: AsyncSession, entry: FAQPhrasing) -> None:
    await delete_embedding(db, FAQ_PHRASING_VEC_TABLE, entry.id)
    await db.delete(entry)
    await db.commit()
