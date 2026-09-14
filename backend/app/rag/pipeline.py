from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.ai.factory import get_active_engine, get_embedding_engine
from app.core import setting_keys as keys
from app.crud.category import get_or_create_other_category
from app.crud.settings import get_all_settings
from app.db.vec_store import FAQ_VEC_TABLE, VAULT_VEC_TABLE, knn_search
from app.models.chat_log import ChatLog
from app.models.faq import FAQEntry
from app.models.unanswered import UnansweredQuestion
from app.models.vault_entry import VaultEntry
from app.rag.filler import is_filler

REFUSAL_SENTINEL = "NOT_FOUND"

SYSTEM_PROMPT = (
    "You are a strict helpdesk assistant. You may ONLY answer using the information "
    "in the provided context below, which comes from an internal knowledge base. "
    "Do not use any outside knowledge, do not guess, and do not make anything up. "
    f"If the context does not contain enough information to answer the question, "
    f"respond with exactly: {REFUSAL_SENTINEL}"
)

RELEVANCE_SYSTEM_PROMPT = (
    "You classify whether a user's message is a question or request related to a "
    "company's products, services, or technical/customer support. Respond with "
    "exactly one word: YES if it is such a question, or NO if it is small talk, "
    "a greeting, general knowledge, or anything unrelated to product/technical "
    "support. Respond with nothing except YES or NO."
)


async def _is_on_topic(engine, question: str) -> bool:
    """Ask the LLM whether the question is even in-scope (product/technical
    support) before spending an embedding + vector search on it. Defaults to
    True (let the normal RAG/threshold flow decide) if the classify call fails,
    so an AI engine hiccup never silently blocks a real question."""
    try:
        verdict = await engine.generate(RELEVANCE_SYSTEM_PROMPT, "", question)
    except AIEngineError:
        return True
    first_word = verdict.strip().lower().split()[0] if verdict.strip() else ""
    return first_word != "no"


@dataclass
class RagResult:
    answer: str
    is_fallback: bool
    confidence_score: float | None
    matched_faq_ids: list[int]
    matched_vault_ids: list[int] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    reference_urls: list[str] = field(default_factory=list)
    engine_used: str = "none"


async def answer_question(db: AsyncSession, question: str) -> RagResult:
    settings_values = await get_all_settings(db)
    fallback_message = settings_values[keys.FALLBACK_MESSAGE]
    threshold = float(settings_values[keys.CONFIDENCE_THRESHOLD])
    top_k = int(settings_values[keys.TOP_K])
    off_topic_threshold = float(settings_values[keys.OFF_TOPIC_THRESHOLD])
    off_topic_message = settings_values[keys.OFF_TOPIC_MESSAGE]

    if is_filler(question):
        return await _off_topic(db, question, off_topic_message, None)

    engine = await get_active_engine(db)
    embedding_engine = await get_embedding_engine(db)

    try:
        [query_vector] = await embedding_engine.embed([question])
    except AIEngineError:
        return await _fallback(db, question, fallback_message, None, engine_used="none")

    faq_hits = await knn_search(db, FAQ_VEC_TABLE, query_vector, top_k)
    vault_hits = await knn_search(db, VAULT_VEC_TABLE, query_vector, top_k)

    faq_ids = [entry_id for entry_id, _ in faq_hits]
    faq_by_id = {
        entry.id: entry
        for entry in (await db.execute(select(FAQEntry).where(FAQEntry.id.in_(faq_ids)))).scalars()
    } if faq_ids else {}

    vault_ids = [entry_id for entry_id, _ in vault_hits]
    vault_by_id = {}
    if vault_ids:
        vault_result = await db.execute(
            select(VaultEntry).where(
                VaultEntry.id.in_(vault_ids), VaultEntry.memory_enabled.is_(True)
            )
        )
        vault_by_id = {entry.id: entry for entry in vault_result.scalars()}

    # Merge FAQ + Vault candidates by similarity (higher = closer) and take the
    # combined top_k, so a strong vault match can outrank a weak FAQ match and
    # vice versa. When there are no vault hits, this is exactly today's
    # FAQ-only result (same limit applied).
    rows = sorted(
        [(("faq", faq_by_id[entry_id]), similarity) for entry_id, similarity in faq_hits if entry_id in faq_by_id]
        + [(("vault", vault_by_id[entry_id]), similarity) for entry_id, similarity in vault_hits if entry_id in vault_by_id],
        key=lambda pair: pair[1],
        reverse=True,
    )[:top_k]

    if not rows:
        if not await _is_on_topic(engine, question):
            return await _off_topic(db, question, off_topic_message, None)
        return await _fallback(db, question, fallback_message, None, engine_used="none")

    (_best_kind, _best_entry), best_similarity = rows[0]

    if best_similarity < threshold:
        # Ambiguous zone: similarity alone can't reliably tell a genuine-but-vague
        # support question apart from something entirely off-topic, especially
        # with a small knowledge base. Only here do we pay for an LLM classify
        # call — a clear FAQ match above threshold never hits this path.
        if best_similarity < off_topic_threshold or not await _is_on_topic(engine, question):
            return await _off_topic(db, question, off_topic_message, best_similarity)
        return await _fallback(
            db, question, fallback_message, best_similarity, engine_used="none"
        )

    context_parts = []
    matched_faq_ids: list[int] = []
    matched_vault_ids: list[int] = []
    image_urls: list[str] = []
    reference_urls: list[str] = []
    for (kind, entry), _similarity in rows:
        if kind == "faq":
            context_parts.append(f"Q: {entry.question}\nA: {entry.answer}")
            matched_faq_ids.append(entry.id)
            image_urls.extend(entry.image_urls or [])
            reference_urls.extend(entry.reference_urls or [])
        else:
            context_parts.append(f"Topic: {entry.title}\n{entry.content}")
            matched_vault_ids.append(entry.id)
            if entry.source_url:
                reference_urls.append(entry.source_url)
    context = "\n\n".join(context_parts)

    try:
        generated = await engine.generate(SYSTEM_PROMPT, context, question)
    except AIEngineError:
        return await _fallback(
            db, question, fallback_message, best_similarity, engine_used=engine.name
        )

    if not generated or REFUSAL_SENTINEL in generated:
        return await _fallback(
            db, question, fallback_message, best_similarity, engine_used=engine.name
        )

    chat_log = ChatLog(
        question_text=question,
        answer_text=generated,
        matched_faq_ids=matched_faq_ids,
        matched_vault_ids=matched_vault_ids,
        confidence_score=best_similarity,
        engine_used=engine.name,
    )
    db.add(chat_log)
    await db.commit()

    return RagResult(
        answer=generated,
        is_fallback=False,
        confidence_score=best_similarity,
        matched_faq_ids=matched_faq_ids,
        matched_vault_ids=matched_vault_ids,
        image_urls=list(dict.fromkeys(image_urls)),
        reference_urls=list(dict.fromkeys(reference_urls)),
        engine_used=engine.name,
    )


async def _off_topic(
    db: AsyncSession,
    question: str,
    off_topic_message: str,
    confidence_score: float | None,
) -> RagResult:
    """For chatter/small talk with no meaningful match to any FAQ (below the
    off-topic threshold): redirect to product/technical support without
    logging an UnansweredQuestion, since there's no real support question for
    an agent to review."""
    chat_log = ChatLog(
        question_text=question,
        answer_text=off_topic_message,
        matched_faq_ids=[],
        confidence_score=confidence_score,
        engine_used="none",
    )
    db.add(chat_log)
    await db.commit()

    return RagResult(
        answer=off_topic_message,
        is_fallback=True,
        confidence_score=confidence_score,
        matched_faq_ids=[],
        engine_used="none",
    )


async def _fallback(
    db: AsyncSession,
    question: str,
    fallback_message: str,
    confidence_score: float | None,
    engine_used: str,
) -> RagResult:
    other_category = await get_or_create_other_category(db)
    unanswered = UnansweredQuestion(
        question_text=question,
        status="pending",
        category_id=other_category.id,
        confidence_score=confidence_score,
    )
    db.add(unanswered)

    chat_log = ChatLog(
        question_text=question,
        answer_text=fallback_message,
        matched_faq_ids=[],
        confidence_score=confidence_score,
        engine_used=engine_used,
    )
    db.add(chat_log)
    await db.commit()

    return RagResult(
        answer=fallback_message,
        is_fallback=True,
        confidence_score=confidence_score,
        matched_faq_ids=[],
        engine_used=engine_used,
    )
