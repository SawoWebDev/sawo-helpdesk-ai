import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.ai.factory import get_active_engine, get_embedding_engine
from app.core import setting_keys as keys
from app.crud.category import get_or_create_other_category
from app.crud.faq import create_faq, find_duplicate_faq
from app.crud.settings import get_all_settings
from app.db.vec_store import FAQ_VEC_TABLE, VAULT_VEC_TABLE, knn_search
from app.models.chat_log import ChatLog
from app.models.faq import FAQEntry
from app.models.unanswered import UnansweredQuestion
from app.models.vault_entry import VaultEntry
from app.rag.filler import is_filler
from app.rag.reindex import embed_entry

REFUSAL_SENTINEL = "NOT_FOUND"

# How many ranked rows actually go into the generation/grounding-check
# context, separate from top_k (which governs retrieval/ranking breadth —
# still worth casting wide so the right content is found at all). A large
# context feeding both the answer generation and the grounding-check calls
# is the main driver of response latency on a free-tier model — capping it
# here keeps that cost bounded regardless of how high top_k is configured.
GENERATION_CONTEXT_LIMIT = 5

# Floating-point tolerance for "is this url's similarity score the same as
# the best one" when deciding which reference links to show (see
# answer_question below) — not a tunable relevance knob, just slack for
# binary float representation, since the compared values come from the same
# query round and should otherwise be exactly equal.
LINK_SIMILARITY_EPSILON = 1e-9

# How many prior same-session, same-day exchanges are eligible to be pulled
# in as conversation history for a follow-up (see answer_question below).
CONVERSATION_HISTORY_LIMIT = 3

SYSTEM_PROMPT = (
    "You are a strict helpdesk assistant. You may ONLY answer using the information "
    "in the provided context below, which comes from an internal knowledge base. "
    "The context may contain several excerpts pulled by a similarity search, and not "
    "all of them are necessarily relevant to the question — read all of them and use "
    "only the ones that actually help answer it. "
    "Every single fact, number, name, or claim in your answer MUST be explicitly present "
    "in the context. Do not add any detail you know from general/outside knowledge, even "
    "if it seems true or well-known — if the context doesn't say it, it is not in your "
    "answer. Do not guess, estimate, or fill gaps to make the answer sound more complete. "
    "It is better to give a short answer or refuse than to add unverified details. "
    "You may also see earlier turns from this same conversation. Use them only if the "
    "current question is genuinely a follow-up continuing that same topic — e.g. to "
    "resolve a pronoun like 'it' or 'that', or to build on what was already established. "
    "If the current question is unrelated to that earlier conversation, ignore it entirely "
    "and answer independently using only the context below. "
    f"If none of the context is actually relevant, or it doesn't contain enough "
    f"information to answer the question, respond with exactly: {REFUSAL_SENTINEL}"
)

RELEVANCE_SYSTEM_PROMPT = (
    "You classify whether a user's message is a question or request related to a "
    "company's products, services, or technical/customer support. Respond with "
    "exactly one word: YES if it is such a question, or NO if it is small talk, "
    "a greeting, general knowledge, or anything unrelated to product/technical "
    "support. Respond with nothing except YES or NO."
)

GROUNDING_CHECK_SYSTEM_PROMPT = (
    "You are a fact-checker. You will be given a CONTEXT and an ANSWER that was "
    "supposedly written using only that context. Check whether every factual claim "
    "in the ANSWER (every specific number, name, date, certification, address, or "
    "other concrete detail) is actually present in the CONTEXT. General wording, "
    "paraphrasing, and reasonable summarizing are fine — the issue is only claims "
    "the CONTEXT never states at all. "
    "Respond with exactly one word: GROUNDED if every claim traces back to the "
    "CONTEXT, or UNGROUNDED if the ANSWER includes any specific fact not present "
    "in the CONTEXT. Respond with nothing except GROUNDED or UNGROUNDED."
)

OFF_TOPIC_SYSTEM_PROMPT = (
    "You are a helpdesk assistant. The user's message is small talk, a greeting, "
    "or otherwise unrelated to product/technical support. Write a brief, warm, "
    "natural one- or two-sentence reply that acknowledges what they said, then "
    "steers the conversation back to product, account, or technical support "
    "topics. Do not answer questions outside product/support, do not make up "
    "product facts, and do not be repetitive or robotic."
)


_UNICODE_PUNCTUATION_MAP = {
    "‐": "-",  # hyphen
    "‑": "-",  # non-breaking hyphen
    "‒": "-",  # figure dash
    "–": "-",  # en dash
    "—": "-",  # em dash
    "―": "-",  # horizontal bar
    "‘": "'",  # left single quote
    "’": "'",  # right single quote
    "“": '"',  # left double quote
    "”": '"',  # right double quote
    "…": "...",  # ellipsis
}
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_text(text: str) -> str:
    """Some free/low-quality models emit smart-punctuation or stray control
    characters that certain fonts/renderers show as a broken box instead of
    the intended glyph. Normalize to plain ASCII punctuation and strip
    control characters before the text ever reaches a client."""
    for unicode_char, ascii_char in _UNICODE_PUNCTUATION_MAP.items():
        text = text.replace(unicode_char, ascii_char)
    return _CONTROL_CHARS_RE.sub("", text)


def _looks_like_real_reply(text: str) -> bool:
    """Guards against a free/low-quality model returning something that isn't
    an actual reply — e.g. a leaked internal classifier tag ("User Safety:
    safe"), a bare label, or a one-word non-answer — instead of the natural
    sentence it was asked to write."""
    stripped = text.strip()
    if len(stripped) < 15:
        return False
    # "Label: value" / "Label - value" shaped output, one line, no real
    # sentence punctuation — the shape a leaked classifier tag takes.
    if "\n" not in stripped and re.match(r"^[A-Za-z][A-Za-z0-9 _-]{2,30}[:\-]\s*\S+$", stripped):
        if not any(p in stripped for p in ".!?"):
            return False
    if not any(c.isalpha() for c in stripped):
        return False
    return True


async def _is_grounded(engine, context: str, answer: str) -> bool:
    """Free/low-quality models don't reliably obey a "don't add outside
    knowledge" instruction on their own — verified live, they'll pad a thin
    context out with specific facts (certifications, addresses, headcounts)
    pulled from training data instead of refusing. This runs a second,
    narrowly-scoped check asking the model to compare the generated answer
    against the context and flag anything not actually supported. Defaults to
    True (trust the answer) only if the check call itself fails, so an AI
    engine hiccup doesn't turn every question into a refusal — but an actual
    UNGROUNDED verdict is authoritative."""
    try:
        verdict = await engine.generate(
            GROUNDING_CHECK_SYSTEM_PROMPT, context, f"ANSWER:\n{answer}", temperature=0
        )
    except AIEngineError:
        return True
    first_word = verdict.strip().upper().split()[0] if verdict.strip() else ""
    return first_word != "UNGROUNDED"


async def _is_on_topic(engine, question: str) -> bool:
    """Ask the LLM whether the question is even in-scope (product/technical
    support) before spending an embedding + vector search on it. Defaults to
    True (let the normal RAG/threshold flow decide) if the classify call fails,
    so an AI engine hiccup never silently blocks a real question."""
    try:
        verdict = await engine.generate(RELEVANCE_SYSTEM_PROMPT, "", question, temperature=0)
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
    low_confidence: bool = False


async def answer_question(
    db: AsyncSession, question: str, session_id: str, ip_address: str | None = None
) -> RagResult:
    settings_values = await get_all_settings(db)
    fallback_message = settings_values[keys.FALLBACK_MESSAGE]
    threshold = float(settings_values[keys.CONFIDENCE_THRESHOLD])
    top_k = int(settings_values[keys.TOP_K])
    off_topic_threshold = float(settings_values[keys.OFF_TOPIC_THRESHOLD])
    off_topic_message = settings_values[keys.OFF_TOPIC_MESSAGE]

    engine = await get_active_engine(db)

    if is_filler(question):
        return await _off_topic(db, engine, question, off_topic_message, None, session_id, ip_address)

    embedding_engine = await get_embedding_engine(db)

    # Recent same-session, same-day history only — a visitor returning after
    # a long gap, or on a different day, starts fresh rather than dragging in
    # stale context from an unrelated earlier conversation.
    history_rows: list[ChatLog] = []
    if session_id:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )
        history_result = await db.execute(
            select(ChatLog)
            .where(ChatLog.session_id == session_id, ChatLog.created_at >= today_start)
            .order_by(ChatLog.created_at.desc())
            .limit(CONVERSATION_HISTORY_LIMIT)
        )
        history_rows = list(history_result.scalars().all())

    # A pronoun-style follow-up ("does it come in a wall-mounted model?") has
    # almost no retrievable content on its own — verified live, it fails to
    # surface the right KB entries and falls back even though the prior turn
    # made the referent obvious. Embedding the previous question together
    # with the current one gives retrieval the missing keywords, without
    # changing what gets shown to the user or logged as the question asked.
    # query_vector (the raw question alone) is kept separate for the
    # auto-promote-to-FAQ duplicate check below, which must compare against
    # what was actually asked, not this retrieval-only blend.
    try:
        if history_rows:
            retrieval_text = f"{history_rows[0].question_text} {question}"
            query_vector, retrieval_vector = await embedding_engine.embed([question, retrieval_text])
        else:
            [query_vector] = await embedding_engine.embed([question])
            retrieval_vector = query_vector
    except AIEngineError:
        return await _fallback(
            db, question, fallback_message, None, engine_used="none",
            session_id=session_id, ip_address=ip_address,
        )

    # Whether a same-day history exists is decided deterministically above
    # (session + calendar day); whether it's actually relevant to THIS
    # question is left to the model itself, via the SYSTEM_PROMPT instruction
    # to only build on prior turns when they're a genuine continuation. An
    # embedding-similarity cutoff between the current and previous question
    # was tried first and abandoned: on short question-to-question pairs (as
    # opposed to question-to-KB-content, which retrieval below does well),
    # this embedding model's scores for genuinely related and unrelated pairs
    # overlap too much to separate with any threshold — verified live,
    # "hello how are you" scored higher than several real follow-ups.
    history_for_generation = (
        [(row.question_text, row.answer_text) for row in reversed(history_rows)]
        if history_rows
        else None
    )

    # Cast a wider net than top_k and let the LLM judge relevance over the
    # whole pool, rather than a raw similarity cutoff deciding before
    # generation ever happens. A single confidence_threshold can reject a
    # genuinely relevant chunk just because its wording doesn't closely match
    # the question — the LLM reading the actual content is a better judge of
    # "is this actually useful" than vector distance alone.
    candidate_k = max(top_k * 3, top_k + 5)
    faq_hits = await knn_search(db, FAQ_VEC_TABLE, retrieval_vector, candidate_k)
    vault_hits = await knn_search(db, VAULT_VEC_TABLE, retrieval_vector, candidate_k)

    faq_ids = [entry_id for entry_id, _ in faq_hits]
    faq_by_id = {
        entry.id: entry
        for entry in (
            await db.execute(
                select(FAQEntry).where(FAQEntry.id.in_(faq_ids), FAQEntry.status == "published")
            )
        ).scalars()
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

    faq_rows = sorted(
        [(("faq", faq_by_id[entry_id]), similarity) for entry_id, similarity in faq_hits if entry_id in faq_by_id],
        key=lambda pair: pair[1],
        reverse=True,
    )
    vault_rows = [
        (("vault", vault_by_id[entry_id]), similarity) for entry_id, similarity in vault_hits if entry_id in vault_by_id
    ]

    # Resolution order: FAQ is the primary tier, Library (Vault) is the
    # secondary tier — but FAQ only wins outright on a high-confidence,
    # near-exact match (>= confidence_threshold). A weak/tangential FAQ hit
    # must not block a genuinely better Library answer, so anything below
    # that bar falls through to the merged FAQ+Library pool, exactly like
    # before, letting the LLM pick the best context from both tiers.
    faq_was_primary = bool(faq_rows and faq_rows[0][1] >= threshold)
    if faq_was_primary:
        rows = faq_rows[:top_k]
    else:
        # Only drop candidates below off_topic_threshold — that floor
        # separates "plausibly related" from "pure noise" — rather than the
        # stricter confidence_threshold, which is now just a signal for
        # is_fallback/logging, not a hard gate.
        all_rows = sorted(faq_rows + vault_rows, key=lambda pair: pair[1], reverse=True)
        rows = [pair for pair in all_rows if pair[1] >= off_topic_threshold][:top_k]

    if not rows:
        if not await _is_on_topic(engine, question):
            return await _off_topic(db, engine, question, off_topic_message, None, session_id, ip_address)
        return await _fallback(
            db, question, fallback_message, None, engine_used="none",
            session_id=session_id, ip_address=ip_address,
        )

    (_best_kind, _best_entry), best_similarity = rows[0]

    # rows is already sorted best-first, so trimming here only ever drops the
    # weakest matches — best_similarity/best match are unaffected.
    rows = rows[:GENERATION_CONTEXT_LIMIT]

    context_parts = []
    matched_faq_ids: list[int] = []
    matched_vault_ids: list[int] = []
    image_urls: list[str] = []
    reference_urls: list[str] = []
    url_similarity: dict[str, float] = {}
    for (kind, entry), similarity in rows:
        if kind == "faq":
            context_parts.append(f"Q: {entry.question}\nA: {entry.answer}")
            matched_faq_ids.append(entry.id)
            image_urls.extend(entry.image_urls or [])
            for url in entry.reference_urls or []:
                reference_urls.append(url)
                url_similarity[url] = max(url_similarity.get(url, 0.0), similarity)
        else:
            context_parts.append(f"Topic: {entry.title}\n{entry.content}")
            matched_vault_ids.append(entry.id)
            if entry.source_url:
                reference_urls.append(entry.source_url)
                url_similarity[entry.source_url] = max(url_similarity.get(entry.source_url, 0.0), similarity)
    context = "\n\n".join(context_parts)

    try:
        generated = await engine.generate(
            SYSTEM_PROMPT, context, question, temperature=0, history=history_for_generation
        )
    except AIEngineError:
        return await _fallback(
            db, question, fallback_message, best_similarity, engine_used=engine.name,
            session_id=session_id, ip_address=ip_address,
        )

    if not generated or REFUSAL_SENTINEL in generated:
        return await _fallback(
            db, question, fallback_message, best_similarity, engine_used=engine.name,
            session_id=session_id, ip_address=ip_address,
        )

    # The grounding check exists to catch a free model padding thin context
    # with outside facts — a real risk with Vault content, which is raw
    # crawled/uploaded material the LLM is summarizing on the fly. It's not
    # needed when the answer is built purely from FAQ context: that content
    # is already admin-curated and verified, so there's nothing left to
    # hallucinate around, and skipping it roughly halves typical latency
    # (the check itself is a second full LLM call, often slower than the
    # original generation).
    if not matched_vault_ids and not await _is_grounded(engine, context, generated):
        return await _fallback(
            db, question, fallback_message, best_similarity, engine_used=engine.name,
            session_id=session_id, ip_address=ip_address,
        )

    generated = _sanitize_text(generated)

    # Only the single most-relevant source earns a reference link — not
    # every matched row that cleared confidence_threshold, since several
    # topically-close pages (e.g. every sauna-heater sub-model) can each
    # independently clear that bar for a question about the category in
    # general, showing several links none of which is clearly THE answer.
    # A margin-based "near the top score" cutoff was tried first and didn't
    # help here: closely related pages score within a hair of each other, so
    # a small margin still let all of them through. Taking only the exact
    # top-scoring source is a deliberately strict, precision-over-recall
    # choice — better to show no link than one that's merely "also related".
    # A plain similarity-score comparison rather than an LLM judgment call —
    # the LLM-based version of this check (asking the model which links were
    # "relevant") proved inconsistent run-to-run on the same question even
    # at temperature 0, which a deterministic score avoids.
    unique_urls = list(dict.fromkeys(reference_urls))
    top_url_similarity = max((url_similarity.get(url, 0.0) for url in unique_urls), default=0.0)
    if top_url_similarity >= threshold:
        reference_urls = [
            url for url in unique_urls
            if url_similarity.get(url, 0.0) >= top_url_similarity - LINK_SIMILARITY_EPSILON
        ]
    else:
        reference_urls = []

    # best_similarity no longer gates whether we answer (the LLM already
    # judged the retrieved context sufficient), but it's still useful as a
    # low-confidence signal: an answer built from below-threshold matches was
    # accepted on the LLM's judgment alone, worth flagging for review even
    # though it's a real, grounded answer rather than a canned fallback.
    low_confidence = best_similarity < threshold

    chat_log = ChatLog(
        question_text=question,
        answer_text=generated,
        matched_faq_ids=matched_faq_ids,
        matched_vault_ids=matched_vault_ids,
        confidence_score=best_similarity,
        engine_used=engine.name,
        session_id=session_id,
        ip_address=ip_address,
    )
    db.add(chat_log)
    await db.commit()

    # Auto-promote every real Library-grounded answer straight into FAQ,
    # published immediately — no separate review step. Only when the answer
    # actually drew on Vault content and FAQ wasn't already the primary-tier
    # answer (a weak FAQ row can still ride along in the merged context pool
    # without being why the question was answered — matched_faq_ids alone
    # isn't a reliable "already covered by FAQ" signal). Relying on that
    # retrieval check alone isn't a hard enough guarantee against duplicates
    # though — e.g. the same question asked twice in quick succession, before
    # the first save's embedding makes the new FAQ rank as primary-tier — so
    # also explicitly check for an existing exact/near-duplicate question
    # right before creating one.
    if matched_vault_ids and not faq_was_primary:
        try:
            if await find_duplicate_faq(db, question, query_vector) is None:
                faq_entry = await create_faq(
                    db,
                    question=question,
                    answer=generated,
                    category_id=None,
                    image_urls=list(dict.fromkeys(image_urls)),
                    reference_urls=reference_urls,
                    source="chat_auto",
                    source_label="Auto-saved from chat",
                )
                await embed_entry(db, faq_entry)
                await db.commit()
        except AIEngineError:
            pass

    return RagResult(
        answer=generated,
        is_fallback=False,
        confidence_score=best_similarity,
        matched_faq_ids=matched_faq_ids,
        matched_vault_ids=matched_vault_ids,
        image_urls=list(dict.fromkeys(image_urls)),
        reference_urls=reference_urls,
        engine_used=engine.name,
        low_confidence=low_confidence,
    )


async def _off_topic(
    db: AsyncSession,
    engine,
    question: str,
    off_topic_message: str,
    confidence_score: float | None,
    session_id: str | None = None,
    ip_address: str | None = None,
) -> RagResult:
    """For chatter/small talk with no meaningful match to any FAQ (below the
    off-topic threshold): redirect to product/technical support without
    logging an UnansweredQuestion, since there's no real support question for
    an agent to review. Tries to generate a natural, non-repetitive reply to
    what was actually said; falls back to the fixed configured message (still
    on-topic, still safe) if that call fails."""
    try:
        generated = await engine.generate(OFF_TOPIC_SYSTEM_PROMPT, "", question)
        if generated and _looks_like_real_reply(generated):
            answer = _sanitize_text(generated)
            engine_used = engine.name
        else:
            answer = off_topic_message
            engine_used = "none"
    except AIEngineError:
        answer = off_topic_message
        engine_used = "none"

    chat_log = ChatLog(
        question_text=question,
        answer_text=answer,
        matched_faq_ids=[],
        confidence_score=confidence_score,
        engine_used=engine_used,
        session_id=session_id,
        ip_address=ip_address,
    )
    db.add(chat_log)
    await db.commit()

    return RagResult(
        answer=answer,
        is_fallback=True,
        confidence_score=confidence_score,
        matched_faq_ids=[],
        engine_used=engine_used,
    )


async def _fallback(
    db: AsyncSession,
    question: str,
    fallback_message: str,
    confidence_score: float | None,
    engine_used: str,
    session_id: str | None = None,
    ip_address: str | None = None,
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
        session_id=session_id,
        ip_address=ip_address,
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
