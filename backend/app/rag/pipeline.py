import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.ai.factory import get_active_engine, get_embedding_engine
from app.core import setting_keys as keys
from app.crud.category import get_chatbot_kb_category_ids, get_or_create_other_category
from app.crud.settings import get_all_settings
from app.db.vec_store import FAQ_VEC_TABLE, VAULT_VEC_TABLE, knn_search
from app.models.chat_log import ChatLog
from app.models.faq import FAQEntry
from app.models.faq_phrasing import FAQPhrasing
from app.models.unanswered import UnansweredQuestion
from app.models.vault_entry import VaultEntry
from app.rag import response_language
from app.rag.answer_style import strip_source_talk
from app.rag.applicability import (
    Scope,
    applies,
    linked_controller_pages,
    linked_controllers,
    other_labels,
    scope_of,
    vault_scope,
)
from app.rag.filler import is_filler
from app.rag.saved_answers import (
    _CONTEXT_REFERENCE_RE,
    ENGINE_FAQ_DIRECT,
    DirectMatchDecision,
    find_exact_answer,
    find_paraphrase_answer,
)
from app.rag.technical_key import TechnicalKey, extract_key
from app.services.ai_usage import (
    FEATURE_CHAT_ANSWER_GENERATION,
    FEATURE_CHAT_OFF_TOPIC_REPLY,
    FEATURE_CHAT_QUERY_EMBEDDING,
    FEATURE_GROUNDING_CHECK,
    FEATURE_RELEVANCE_CHECK,
    feature_context,
    session_context,
)

REFUSAL_SENTINEL = "NOT_FOUND"

# How many ranked rows actually go into the generation/grounding-check
# context, separate from top_k (which governs retrieval/ranking breadth —
# still worth casting wide so the right content is found at all). A large
# context feeding both the answer generation and the grounding-check calls
# is the main driver of response latency on a free-tier model — capping it
# here keeps that cost bounded regardless of how high top_k is configured.
GENERATION_CONTEXT_LIMIT = 5

# An "list every model in this range" question is the one case where the cap
# above is actively wrong: answering it *completely* needs every matching
# variant in context at once, and five chunks covers only two or three of
# them, so the model silently answers about a fraction of the family and
# sounds confident doing it. These questions get the full retrieved set (up
# to top_k, bounded here) instead.
ENUMERATION_CONTEXT_LIMIT = 12

# Cues that the question wants a complete set rather than one fact. Kept
# deliberately narrow: widening the context costs tokens and latency on
# every question that trips it.
_ENUMERATION_RE = re.compile(
    r"\b("
    r"list(?:\s+(?:them|these|those|all|out))?"
    r"|all (?:the |of the |their |your )?[a-z]+"
    r"|every (?:model|variant|option|version|type|product|one)"
    r"|(?:full|complete|entire|whole) (?:range|lineup|list|series|set)"
    r"|how many (?:model|variant|option|version|type|product)"
    r"|(?:what|which)[^.?!]{0,40}?(?:models|variants|options|versions|types|products|sizes)"
    r")\b",
    re.IGNORECASE,
)

# Overview/hub pages ("…/tower-series/") name every member of a product
# family. That is exactly what an enumeration question needs and exactly
# what similarity search buries: each individual product page answers the
# query just as closely and there are a dozen of them, so the one page that
# lists the whole family never makes the cut. When the question names a
# family, its overview page is pinned into the context rather than left to
# win a ranking contest it cannot win.
HUB_URL_SUFFIXES = ("-series", "-range", "-collection")
MAX_PINNED_HUB_CHUNKS = 2

# Most product families have no overview page at all — their variants simply
# sit at sibling URLs ("/aries-corner-nb/", "/aries-round-ns/"). Retrieval
# returns a handful of them and the model then answers as though that
# handful were the whole family. Pinning siblings by URL slug makes the set
# complete rather than whatever scored best.
MAX_PINNED_FAMILY_CHUNKS = 6

# At most this many source links are shown under an answer.
MAX_REFERENCE_URLS = 3

# Question words that would match a hub URL by accident.
_HUB_TOKEN_STOPWORDS = {
    "what", "which", "where", "when", "does", "have", "with", "from", "they",
    "them", "this", "that", "these", "those", "your", "list", "every", "about",
    "there", "their", "tell", "show", "give", "spec", "specs", "please", "would",
    "could", "many", "much", "also", "into", "over", "under", "between",
}
_HUB_TOKEN_RE = re.compile(r"[a-z0-9]{4,}")


def _is_enumeration_question(question: str) -> bool:
    return bool(_ENUMERATION_RE.search(question))


def _hub_tokens(question: str) -> list[str]:
    seen: list[str] = []
    for word in _HUB_TOKEN_RE.findall(question.lower()):
        if word not in _HUB_TOKEN_STOPWORDS and word not in seen:
            seen.append(word)
    return seen


# Matches a "flat" product-style URL -- a single root-level slug, no nested
# path ("https://www.sawo.com/aries-round-nb/") -- as opposed to an overview
# page ("/finnish-sauna/sauna-heaters/tower-series/") or a manual PDF under
# /wp-content/. Every product family in this KB uses this same flat shape,
# and their pages are templated closely enough (near-identical feature-bullet
# wording) that similarity search regularly ranks one family's product page
# almost as well as another's for a question naming only one of them.
_FLAT_PRODUCT_URL_RE = re.compile(r"^https?://[^/]+/([a-z0-9]+)-[a-z0-9-]*/?$")


def _is_off_family_product_page(source_url: str | None, family_tokens: list[str]) -> bool:
    """True when `source_url` looks like another product's own page and
    doesn't belong to any of `family_tokens` -- see _FLAT_PRODUCT_URL_RE.

    Used only once a question has been pinned to a specific family (hub
    pinning found a match): at that point, a same-shaped page for a
    different family reaching the context via ordinary similarity search
    is a known failure mode (confirmed live -- Aries product pages in a
    Tower-only enumeration's context, crowding out real Tower variants and
    the answer's own completeness), not a second family the question
    actually asked about.
    """
    if not source_url or not family_tokens:
        return False
    match = _FLAT_PRODUCT_URL_RE.match(source_url.lower())
    if not match:
        return False
    return match.group(1) not in family_tokens

# Floating-point tolerance for "is this image's similarity score the same as
# the best one" when deciding which images to show (see answer_question
# below; reference links no longer use this rule) — not a tunable relevance knob, just slack for
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
    "When the question asks for ALL of something — every model in a series, the "
    "full range, a complete list — first point to the overview page for that family "
    "if one appears in the context, then list every matching item the context "
    "actually contains. Group them clearly and keep each item's details with it. "
    "If the context only covers part of the family, say so plainly and point to the "
    "overview page for the rest, rather than presenting a partial list as complete. "
    "Never state where a product is documented, or which page or manual covers it, "
    "unless the context explicitly ties that product to that page. If you cannot "
    "tell from the context where something is documented, say you don't know rather "
    "than naming a page that merely appears nearby in the context. "
    "Whenever you mention a URL from the context, never write the raw URL out in the "
    "sentence (e.g. not 'the Dragonfire Series page (https://example.com/dragonfire/)'). "
    "Instead format it as a Markdown inline link with short, descriptive text as the "
    "label, e.g. 'the [Dragonfire Series page](https://example.com/dragonfire/)'. "
    "Answer directly, the way a colleague would: start with the answer itself. Never "
    "mention 'the context', 'the knowledge base', 'the documentation' or 'the provided "
    "information', never say where the information comes from, and never begin with "
    "'Based on...' or 'According to...'. Do not add a closing remark, conclusion or "
    "explanation that the context does not itself state. "
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


def _generation_prompt(
    scope: Scope, language: response_language.ResponseLanguage, linked: frozenset[str] = frozenset()
) -> str:
    """SYSTEM_PROMPT plus this question's two hard constraints: the product it
    names (applicability.py already removed other products' content; this
    covers what is left, e.g. a page that mentions several) and the reply
    language (response_language.py). `linked` = controllers the model's own
    product page lists, whose content applicability.py kept for that reason."""
    parts = [SYSTEM_PROMPT]
    if not scope.is_empty:
        target = scope.describe()
        covered = f"explicitly covers {target}"
        if linked:
            controllers = " or ".join(sorted(label.capitalize() for label in linked))
            covered += (
                f", or it is about the {controllers} control, which the documentation lists for "
                f"{target} (then say which control the answer is for)"
            )
        parts.append(
            f"The question is specifically about: {target}. Treat that as a hard constraint. Use an "
            f"excerpt only if it is general (not tied to a particular product) or it {covered}. "
            f"Never apply troubleshooting steps, specifications or instructions that an excerpt "
            f"gives for a different model, heater type or controller, and never assume two models behave "
            f"the same unless an excerpt says so. If no excerpt establishes the answer for {target}, "
            f"respond with exactly: {REFUSAL_SENTINEL}"
        )
    parts.append(language.instruction())
    return " ".join(parts)


# How many of the removed, other-product matches the limitation reply names.
MAX_NAMED_EXCLUSIONS = 3


def _limitation_message(
    scope: Scope,
    excluded: list[tuple[Scope, float]],
    best_kept: float,
    linked: frozenset[str],
    fallback_message: str,
    language: response_language.ResponseLanguage,
) -> str:
    """Reply for a question about a specific product that the knowledge base
    doesn't cover: says so, instead of the generic fallback or an answer
    borrowed from another product. Names only the removed matches that
    outranked everything that was kept — the content that would otherwise
    have been used — not every weak match that shares a word. The lead-in and
    the appended fallback text are both localized to `language` (see
    response_language.limitation_message/localize_fallback_message);
    `target`/`others` are technical identifiers and are never translated."""
    target = scope.describe()
    notable = sorted((pair for pair in excluded if pair[1] > best_kept), key=lambda pair: pair[1], reverse=True)
    others = other_labels(scope, [s for s, _sim in notable[:MAX_NAMED_EXCLUSIONS]], linked)
    message = response_language.limitation_message(target, others, language)
    localized_fallback = response_language.localize_fallback_message(fallback_message, language)
    return f"{message} {localized_fallback}"


def _conversation_scope(history_rows: list[ChatLog]) -> Scope:
    """The product the conversation is about, for a follow-up that names none.
    Walks back from the newest earlier turn, past turns that were themselves
    bare follow-ups ("why is it humming?"), to the last one that named a
    product; a turn that was a new, product-less question ends the search, so
    "what stones does SAWO recommend?" resets it."""
    for row in history_rows:  # newest first
        scope = scope_of(row.question_text)
        if not scope.is_empty:
            return scope
        if not _CONTEXT_REFERENCE_RE.search(row.question_text):
            break
    return Scope()


async def _has_documented_identifier(db: AsyncSession, key: TechnicalKey) -> bool:
    """True if one of `key`'s codes or parts (e.g. "E1", "TS1") is the exact
    identifier of something the knowledge base actually documents — a
    published FAQ's question/answer, an enabled reviewed phrasing, or
    memory-enabled Library content — rather than merely a string that happens
    to match technical_key's E<digits>-style patterns.

    Used only to keep filler.is_filler's short-message heuristic (a bare
    "E1?" is otherwise indistinguishable from "meh" or "abc" by length alone)
    from swallowing a real technical question: "E1?" reaches the normal
    pipeline exactly when E1 is something this KB documents, while an
    undocumented short string like "Q9" is left as filler. A coarse SQL
    `.contains()` narrows candidates (same approach as
    applicability.linked_controllers), then extract_key on each candidate's
    own text confirms an exact identifier match rather than a substring one
    ("E1" must not match because a row happens to contain "E10")."""
    identifiers = key.codes | key.parts
    if not identifiers:
        return False

    def _mentions(text: str) -> bool:
        found = extract_key(text)
        return bool(identifiers & (found.codes | found.parts))

    faq_like = or_(
        *(FAQEntry.question.contains(i) for i in identifiers),
        *(FAQEntry.answer.contains(i) for i in identifiers),
    )
    faq_rows = (
        await db.execute(select(FAQEntry.question, FAQEntry.answer).where(FAQEntry.status == "published", faq_like))
    ).all()
    if any(_mentions(f"{q}\n{a}") for q, a in faq_rows):
        return True

    phrasing_like = or_(*(FAQPhrasing.phrasing.contains(i) for i in identifiers))
    phrasings = (
        await db.execute(select(FAQPhrasing.phrasing).where(FAQPhrasing.enabled.is_(True), phrasing_like))
    ).scalars().all()
    if any(_mentions(p) for p in phrasings):
        return True

    vault_like = or_(*(VaultEntry.content.contains(i) for i in identifiers))
    contents = (
        await db.execute(
            select(VaultEntry.content).where(VaultEntry.memory_enabled.is_(True), vault_like).limit(50)
        )
    ).scalars().all()
    return any(_mentions(c) for c in contents)


def _entry_scope(kind: str, entry) -> Scope:
    if kind == "faq":
        return scope_of(f"{entry.question}\n{entry.answer}")
    return vault_scope(entry.title, entry.source_url, entry.content, entry.source_type)


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
        with feature_context(FEATURE_GROUNDING_CHECK):
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
        with feature_context(FEATURE_RELEVANCE_CHECK):
            verdict = await engine.generate(RELEVANCE_SYSTEM_PROMPT, "", question, temperature=0)
    except AIEngineError:
        return True
    first_word = verdict.strip().lower().split()[0] if verdict.strip() else ""
    return first_word != "no"


@dataclass
class PromotionPayload:
    """Everything a background task needs to promote a Library-grounded chat
    answer into a draft FAQ, without handing it the request's AsyncSession
    (see faq_promotion.promote_answer_to_draft)."""

    question: str
    answer: str
    image_urls: list[str]
    reference_urls: list[str]
    source_id: int | None
    query_vector: list[float]


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
    chat_log_id: int | None = None
    promotion: PromotionPayload | None = None


async def _find_hub_entries(
    db: AsyncSession, question: str, excluded_category_ids: set[int] | None = None
) -> list[VaultEntry]:
    """Library chunks for a product-family overview page named by the question.

    Matched on the URL rather than on content similarity: a family's overview
    page is identifiable by its slug ("/tower-series/") and is precisely the
    page that similarity search cannot surface, because every individual
    product page in that family scores at least as well against the question.
    """
    tokens = _hub_tokens(question)
    if not tokens:
        return []

    clauses = []
    for token in tokens:
        for suffix in HUB_URL_SUFFIXES:
            clauses.append(VaultEntry.source_url.like(f"%/{token}{suffix}/%"))
            clauses.append(VaultEntry.source_url.like(f"%/{token}{suffix}"))

    result = await db.execute(
        select(VaultEntry)
        .where(VaultEntry.memory_enabled.is_(True), or_(*clauses))
        .order_by(VaultEntry.id)
        .limit(MAX_PINNED_HUB_CHUNKS)
    )
    entries = list(result.scalars())
    if excluded_category_ids:
        entries = [e for e in entries if e.category_id not in excluded_category_ids]
    return entries


async def _find_family_entries(
    db: AsyncSession,
    question: str,
    excluded_category_ids: set[int] | None = None,
    exclude_ids: set[int] | None = None,
    limit: int = MAX_PINNED_FAMILY_CHUNKS,
    only_tokens: list[str] | None = None,
) -> list[VaultEntry]:
    """Library chunks for sibling product pages of a family named in the question.

    Matched on the URL slug ("/aries-...") for the same reason as
    _find_hub_entries: the variants of one family are near-identical pages
    that all score alike, so similarity ranking returns an arbitrary few of
    them rather than the set.
    """
    tokens = list(only_tokens) if only_tokens else _hub_tokens(question)
    if not tokens:
        return []

    clauses = [VaultEntry.source_url.like(f"%/{token}-%") for token in tokens]
    query = select(VaultEntry).where(VaultEntry.memory_enabled.is_(True), or_(*clauses))
    if exclude_ids:
        query = query.where(VaultEntry.id.notin_(exclude_ids))

    result = await db.execute(query.order_by(VaultEntry.source_url, VaultEntry.id).limit(limit))
    entries = list(result.scalars())
    if excluded_category_ids:
        entries = [e for e in entries if e.category_id not in excluded_category_ids]
    return entries


async def answer_question(
    db: AsyncSession, question: str, session_id: str, ip_address: str | None = None
) -> RagResult:
    # Lets every AI call this question triggers (relevance check, embedding,
    # generation, grounding check) record which conversation it belongs to
    # without threading session_id through AIEngine.generate()/embed() and
    # every helper below that calls them — see services/ai_usage.py.
    with session_context(session_id):
        return await _answer_question_impl(db, question, session_id, ip_address)


async def _answer_question_impl(
    db: AsyncSession, question: str, session_id: str, ip_address: str | None = None
) -> RagResult:
    settings_values = await get_all_settings(db)
    fallback_message = settings_values[keys.FALLBACK_MESSAGE]
    threshold = float(settings_values[keys.CONFIDENCE_THRESHOLD])
    top_k = int(settings_values[keys.TOP_K])
    off_topic_threshold = float(settings_values[keys.OFF_TOPIC_THRESHOLD])
    off_topic_message = settings_values[keys.OFF_TOPIC_MESSAGE]
    general_knowledge_enabled = settings_values[keys.GENERAL_KNOWLEDGE_ENABLED] == "true"
    chatbot_kb_enabled = settings_values[keys.CHATBOT_KB_ENABLED] == "true"

    engine = await get_active_engine(db)
    # Computed this early (pure text function, no I/O) so every fallback below
    # — including one from an embedding failure, before question_scope even
    # exists — can localize its message; see response_language.py's
    # localize_fallback_message/localize_off_topic_message/limitation_message.
    language = response_language.detect(question)

    # is_filler's short-message heuristic can't tell "E1?" from "meh" by
    # length alone, so a short message it flags gets one more chance: if it
    # carries a technical identifier (error/status code, component
    # designator) that this KB actually documents, it is a real technical
    # question, not small talk — see _has_documented_identifier. An
    # undocumented short string is still treated as filler.
    if is_filler(question):
        key = extract_key(question)
        if key.is_empty or not await _has_documented_identifier(db, key):
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
            # id breaks ties: created_at has one-second resolution, and which
            # turn counts as "previous" decides what a follow-up refers to.
            .order_by(ChatLog.created_at.desc(), ChatLog.id.desc())
            .limit(CONVERSATION_HISTORY_LIMIT)
        )
        history_rows = list(history_result.scalars().all())

    # Stage 1 of saved-answer reuse (rag/saved_answers.py): the same question
    # as a staff-approved, published FAQ is answered by one indexed lookup,
    # before any AI call — no embedding, no generation, no fact-check, and the
    # identical approved wording every time.
    exact = await find_exact_answer(db, question, has_history=bool(history_rows))
    if exact.hit:
        return await _direct_answer_result(db, exact, question, session_id, ip_address)

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
        with feature_context(FEATURE_CHAT_QUERY_EMBEDDING):
            if history_rows:
                retrieval_text = f"{history_rows[0].question_text} {question}"
                query_vector, retrieval_vector = await embedding_engine.embed([question, retrieval_text])
            else:
                [query_vector] = await embedding_engine.embed([question])
                retrieval_vector = query_vector
    except AIEngineError:
        return await _fallback(
            db, question, fallback_message, None, engine_used="none",
            language=language, session_id=session_id, ip_address=ip_address,
        )

    # Stage 2: a close rewording of a published FAQ with the same error
    # code/product/model, asking for nothing more than that FAQ covers, is
    # returned as stored — no LLM call. Anything not provably the same question
    # falls through to the normal flow below, untouched.
    paraphrase = await find_paraphrase_answer(db, question, query_vector, has_history=bool(history_rows))
    if paraphrase.hit:
        return await _direct_answer_result(db, paraphrase, question, session_id, ip_address)

    # Both decided from the question text alone — no AI call. A follow-up that
    # only says "it" is about the product the conversation last named — and so
    # is one that names no product but does carry a technical identifier of
    # its own ("E1?" after "SW3-45NS"): it has nothing to name a product with
    # either, and reads the same way to a person continuing the conversation.
    question_scope = scope_of(question)
    if question_scope.is_empty and (_CONTEXT_REFERENCE_RE.search(question) or not extract_key(question).is_empty):
        question_scope = _conversation_scope(history_rows)

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
    # Skipping the vault query entirely (rather than filtering its results
    # after the fact) when General Knowledge is turned off, since there's no
    # reason to pay for the search at all when its results would be discarded.
    vault_hits = await knn_search(db, VAULT_VEC_TABLE, retrieval_vector, candidate_k) if general_knowledge_enabled else []

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
    # Shared by the hub-page pinning below, so a pinned overview page can
    # never smuggle in content the Chatbot-KB opt-out excludes.
    excluded_category_ids: set[int] = set()
    if vault_ids:
        vault_result = await db.execute(
            select(VaultEntry).where(
                VaultEntry.id.in_(vault_ids), VaultEntry.memory_enabled.is_(True)
            )
        )
        vault_by_id = {entry.id: entry for entry in vault_result.scalars()}
        if not chatbot_kb_enabled and vault_by_id:
            # Separate opt-out from General Knowledge as a whole: drop only
            # entries under the sawochatbot import's category tree, leaving
            # crawler- and manually-added Library content untouched.
            excluded_category_ids = set(await get_chatbot_kb_category_ids(db))
            if excluded_category_ids:
                vault_by_id = {
                    entry_id: entry
                    for entry_id, entry in vault_by_id.items()
                    if entry.category_id not in excluded_category_ids
                }

    faq_rows = sorted(
        [(("faq", faq_by_id[entry_id]), similarity) for entry_id, similarity in faq_hits if entry_id in faq_by_id],
        key=lambda pair: pair[1],
        reverse=True,
    )
    vault_rows = [
        (("vault", vault_by_id[entry_id]), similarity) for entry_id, similarity in vault_hits if entry_id in vault_by_id
    ]

    # A named model or controller is a hard constraint (see applicability.py):
    # content scoped only to other products is removed here, before ranking,
    # so it can neither win the FAQ-primary tier nor reach the prompt.
    # `excluded` remembers what was removed and would otherwise have been
    # eligible, to explain the gap if nothing applicable is left.
    linked: frozenset[str] = frozenset()
    excluded: list[tuple[Scope, float]] = []
    if not question_scope.is_empty:
        linked = await linked_controllers(db, question_scope)

        def _applicable(pair) -> bool:
            (kind, entry), similarity = pair
            scope = _entry_scope(kind, entry)
            if applies(question_scope, scope, linked):
                return True
            if similarity >= off_topic_threshold:
                excluded.append((scope, similarity))
            return False

        faq_rows = [pair for pair in faq_rows if _applicable(pair)]
        vault_rows = [pair for pair in vault_rows if _applicable(pair)]

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
        if excluded:
            # Only other products' documentation matched: say so, with no LLM call.
            return await _fallback(
                db, question, _limitation_message(question_scope, excluded, 0.0, linked, fallback_message, language),
                None, engine_used="none", language=language, session_id=session_id, ip_address=ip_address,
            )
        if not await _is_on_topic(engine, question):
            return await _off_topic(db, engine, question, off_topic_message, None, session_id, ip_address)
        return await _fallback(
            db, question, fallback_message, None, engine_used="none",
            language=language, session_id=session_id, ip_address=ip_address,
        )

    (_best_kind, _best_entry), best_similarity = rows[0]

    # rows is already sorted best-first, so trimming here only ever drops the
    # weakest matches — best_similarity/best match are unaffected. A question
    # asking for a whole product family gets a bigger slice: answering it
    # completely means having every variant in context at once.
    wants_enumeration = _is_enumeration_question(question)
    context_limit = ENUMERATION_CONTEXT_LIMIT if wants_enumeration else GENERATION_CONTEXT_LIMIT
    rows = rows[:context_limit]

    # For an enumeration question, put the family's overview page and its
    # sibling product pages in front of the ranked results, then fill the
    # remaining budget from retrieval. Pinned rows spend the same budget
    # rather than extending it, so context size stays bounded at
    # context_limit however many siblings a family turns out to have.
    #
    # Restricted to enumeration questions: a single-fact question ("what kW
    # is the SW3-45NS") is better served by the specific page retrieval
    # already ranked first, and pinning would only crowd it out.
    if wants_enumeration and general_knowledge_enabled:
        vault_similarity = dict(vault_hits)
        present_ids = {entry.id for (kind, entry), _ in rows if kind == "vault"}

        pinned_entries = await _find_hub_entries(db, question, excluded_category_ids)
        pinned_ids = {entry.id for entry in pinned_entries}
        # A hub page's own slug names the family precisely ("tower-series" ->
        # "tower"), so the sibling search is narrowed to it. Without that, a
        # broad token from the question — a brand name like "sawo" — matches
        # unrelated pages and spends the pinned budget on them.
        hub_tokens = [
            token for token in _hub_tokens(question)
            if any(f"/{token}-" in (entry.source_url or "") for entry in pinned_entries)
        ]
        pinned_entries += await _find_family_entries(
            db, question, excluded_category_ids, exclude_ids=pinned_ids,
            only_tokens=hub_tokens or None,
        )
        pinned_entries = [
            entry for entry in pinned_entries
            if applies(question_scope, _entry_scope("vault", entry), linked)
        ]

        # A pinned chunk keeps its real retrieval score when it was in the
        # candidate pool at all; otherwise it takes the floor that makes it
        # eligible to be cited as a source without claiming it out-ranked
        # anything it did not.
        pinned_rows = [
            (("vault", entry), vault_similarity.get(entry.id, off_topic_threshold))
            for entry in pinned_entries
            if entry.id not in present_ids
        ]
        if pinned_rows:
            pinned_ids = {entry.id for (_kind, entry), _ in pinned_rows}
            # A family with no overview page (e.g. Aries) never populates
            # hub_tokens above, but _find_family_entries still resolved the
            # same fallback token set internally to find its siblings --
            # reusing that here keeps "which family is this" consistent
            # between pinning siblings in and filtering other families out.
            filter_tokens = hub_tokens or _hub_tokens(question)
            kept = [
                pair
                for pair in rows
                if not (
                    pair[0][0] == "vault"
                    and (
                        pair[0][1].id in pinned_ids
                        or _is_off_family_product_page(pair[0][1].source_url, filter_tokens)
                    )
                )
            ]
            rows = (pinned_rows + kept)[:context_limit]

    context_parts = []
    matched_faq_ids: list[int] = []
    matched_vault_ids: list[int] = []
    image_urls: list[str] = []
    image_similarity: dict[str, float] = {}
    reference_urls: list[str] = []
    url_similarity: dict[str, float] = {}
    # rows is sorted best-first, so the first vault entry encountered here is
    # the top-ranked one — used below to link an auto-promoted FAQ back to
    # the Library source it was actually drawn from.
    top_vault_source_id: int | None = None
    for (kind, entry), similarity in rows:
        if kind == "faq":
            context_parts.append(f"Q: {entry.question}\nA: {entry.answer}")
            matched_faq_ids.append(entry.id)
            for img in entry.image_urls or []:
                image_urls.append(img)
                image_similarity[img] = max(image_similarity.get(img, 0.0), similarity)
            for url in entry.reference_urls or []:
                reference_urls.append(url)
                url_similarity[url] = max(url_similarity.get(url, 0.0), similarity)
        else:
            context_parts.append(f"Topic: {entry.title}\n{entry.content}")
            matched_vault_ids.append(entry.id)
            if top_vault_source_id is None:
                top_vault_source_id = entry.source_id
            if entry.source_url:
                reference_urls.append(entry.source_url)
                url_similarity[entry.source_url] = max(url_similarity.get(entry.source_url, 0.0), similarity)

    # Relationship evidence: some row above was only admitted past the
    # applicability filter because it's scoped to a controller the question's
    # model links (applicability.linked_controllers) rather than to the model
    # itself — an Innova E1 FAQ never mentions "SW3-45NS". Without the page
    # that actually documents "Available controls: Saunova/Innova" for that
    # model, nothing in context ties the two together: the model has to take
    # it purely on the system prompt's word, and a real answer naming the
    # model has no CONTEXT support for that name at all. That page is added
    # here, deliberately, as evidence for the relationship rather than as
    # ranked answer content (it does not affect matched_vault_ids, promotion,
    # or best_similarity/low_confidence, and does not need to out-rank the
    # controller FAQ it's supporting) — added only when a row actually needed
    # the link, never speculatively, and never in place of the off_topic
    # floor other retrieval still has to clear.
    if linked and any(
        not applies(question_scope, _entry_scope(kind, entry), frozenset()) for (kind, entry), _sim in rows
    ):
        present_vault_ids = {entry.id for (kind, entry), _sim in rows if kind == "vault"}
        for entry in await linked_controller_pages(db, question_scope):
            if entry.id in present_vault_ids:
                continue
            context_parts.append(f"Topic: {entry.title}\n{entry.content}")
            if entry.source_url:
                reference_urls.append(entry.source_url)
                url_similarity[entry.source_url] = max(url_similarity.get(entry.source_url, 0.0), off_topic_threshold)

    context = "\n\n".join(context_parts)

    try:
        with feature_context(FEATURE_CHAT_ANSWER_GENERATION):
            generated = await engine.generate(
                _generation_prompt(question_scope, language, linked), context, question,
                temperature=0, history=history_for_generation,
            )
    except AIEngineError:
        return await _fallback(
            db, question, fallback_message, best_similarity, engine_used=engine.name,
            language=language, session_id=session_id, ip_address=ip_address,
        )

    if not generated or REFUSAL_SENTINEL in generated:
        message = (
            fallback_message if question_scope.is_empty
            else _limitation_message(question_scope, excluded, best_similarity, linked, fallback_message, language)
        )
        return await _fallback(
            db, question, message, best_similarity, engine_used=engine.name,
            language=language, session_id=session_id, ip_address=ip_address,
        )

    # The language instruction is only a prompt, and a prompt is what failed
    # (response_language.py). A reply in the wrong writing system — typically
    # a refusal the model wrote as a Chinese apology instead of the sentinel —
    # is not shown.
    if not response_language.answer_matches(generated, language):
        return await _fallback(
            db, question, fallback_message, best_similarity, engine_used=engine.name,
            language=language, session_id=session_id, ip_address=ip_address,
        )

    # The grounding check runs only on answers built purely from FAQ
    # context, and is skipped as soon as any Library (Vault) chunk is used.
    #
    # That is the opposite of what the check was designed for — Vault content
    # is the raw crawled material most at risk of being padded with outside
    # facts — and it is deliberate, because the check is not affordable on a
    # Vault-sized context. Measured on this KB with a 12-chunk Library
    # context (~19k characters), a single check call took 377 seconds and
    # still returned UNGROUNDED for a hand-verified correct answer. Enabling
    # it there costs minutes per question and discards good answers; FAQ
    # contexts are small enough for it to be both fast and accurate.
    #
    # The gap this leaves — an unverified claim inside a Library answer — is
    # handled in SYSTEM_PROMPT instead, which forbids asserting where a
    # product is documented unless the context ties it to that page.
    if not matched_vault_ids and not await _is_grounded(engine, context, generated):
        return await _fallback(
            db, question, fallback_message, best_similarity, engine_used=engine.name,
            language=language, session_id=session_id, ip_address=ip_address,
        )

    generated = strip_source_talk(_sanitize_text(generated))

    # Links are the sources the answer was actually written from: every URL
    # attached to a chunk that went into the context, best-ranked first and
    # capped.
    #
    # The previous rule kept only URLs whose score tied the single best one,
    # which decided the link by ranking accident rather than by what the
    # answer used — a question about one product family could be captioned
    # with a different family's page purely because that page happened to
    # rank first. It also showed nothing at all unless the top score cleared
    # confidence_threshold, so the common case of a good multi-source answer
    # cited none of its sources.
    #
    # Still a plain score comparison rather than an LLM judgment call: the
    # LLM-based version of this check (asking the model which links were
    # "relevant") proved inconsistent run-to-run on the same question even
    # at temperature 0, which a deterministic score avoids.
    reference_urls = [
        url for url in dict.fromkeys(reference_urls)
        if url_similarity.get(url, 0.0) >= off_topic_threshold
    ][:MAX_REFERENCE_URLS]

    # Same "only the exact top-scoring source" rule as reference_urls above,
    # applied to images: an image attached to one FAQ entry shouldn't ride
    # along on an answer that only used a different, lower-ranked entry from
    # the same context pool just because both cleared the retrieval bar.
    unique_images = list(dict.fromkeys(image_urls))
    top_image_similarity = max((image_similarity.get(img, 0.0) for img in unique_images), default=0.0)
    if top_image_similarity >= threshold:
        image_urls = [
            img for img in unique_images
            if image_similarity.get(img, 0.0) >= top_image_similarity - LINK_SIMILARITY_EPSILON
        ]
    else:
        image_urls = []

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

    # Flag every real Library-grounded answer for promotion into a draft FAQ
    # — not published outright, an admin reviews it (see faq_promotion.py).
    # Only when the answer actually drew on Vault content and FAQ wasn't
    # already the primary-tier answer (a weak FAQ row can still ride along in
    # the merged context pool without being why the question was answered —
    # matched_faq_ids alone isn't a reliable "already covered by FAQ"
    # signal). The actual duplicate check and DB write happen in the
    # background task, off the request path — they cost an extra embeddings
    # call for candidate questions and give the asker nothing.
    promotion = (
        PromotionPayload(
            question=question,
            answer=generated,
            image_urls=list(dict.fromkeys(image_urls)),
            reference_urls=reference_urls,
            source_id=top_vault_source_id,
            query_vector=query_vector,
        )
        if matched_vault_ids and not faq_was_primary
        else None
    )

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
        chat_log_id=chat_log.id,
        promotion=promotion,
    )


async def _direct_answer_result(
    db: AsyncSession,
    direct: DirectMatchDecision,
    question: str,
    session_id: str | None,
    ip_address: str | None,
) -> RagResult:
    faq = direct.faq
    image_urls = list(faq.image_urls or [])
    reference_urls = list(faq.reference_urls or [])
    chat_log = ChatLog(
        question_text=question,
        answer_text=faq.answer,
        matched_faq_ids=[faq.id],
        confidence_score=direct.similarity,
        engine_used=ENGINE_FAQ_DIRECT,
        session_id=session_id,
        ip_address=ip_address,
    )
    db.add(chat_log)
    await db.commit()

    return RagResult(
        answer=faq.answer,
        is_fallback=False,
        confidence_score=direct.similarity,
        matched_faq_ids=[faq.id],
        image_urls=image_urls,
        reference_urls=reference_urls,
        engine_used=ENGINE_FAQ_DIRECT,
        low_confidence=False,
        chat_log_id=chat_log.id,
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
    on-topic, still safe) if that call fails — localized the same way
    pipeline._fallback localizes its own default message."""
    language = response_language.detect(question)
    off_topic_message = response_language.localize_off_topic_message(off_topic_message, language)
    try:
        with feature_context(FEATURE_CHAT_OFF_TOPIC_REPLY):
            generated = await engine.generate(f"{OFF_TOPIC_SYSTEM_PROMPT} {language.reply_rule()}", "", question)
        if generated and _looks_like_real_reply(generated) and response_language.answer_matches(generated, language):
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
        chat_log_id=chat_log.id,
    )


async def _fallback(
    db: AsyncSession,
    question: str,
    fallback_message: str,
    confidence_score: float | None,
    engine_used: str,
    language: response_language.ResponseLanguage | None = None,
    session_id: str | None = None,
    ip_address: str | None = None,
) -> RagResult:
    # A message built by _limitation_message is already localized (and won't
    # match the plain default below, so this is a no-op for it); a plain
    # fallback_message setting value is localized here, once, for every
    # caller. language=None (only the "message doesn't matter, already have
    # every field it needs" internal callers, if any were ever added) skips
    # it and shows the message exactly as passed in.
    if language is not None:
        fallback_message = response_language.localize_fallback_message(fallback_message, language)

    # Collapse repeat askings of the same question into one pending row with
    # a counter, rather than a fresh row per occurrence — otherwise a
    # question asked 50 times is 50 rows and the admin can't see what to fix
    # first. Scoped to status == "pending" so a question that regresses after
    # being resolved correctly opens a new row instead of reviving the old
    # (already-answered) one.
    normalized = question.strip().lower()
    now = datetime.now(timezone.utc)
    existing_result = await db.execute(
        select(UnansweredQuestion).where(
            UnansweredQuestion.status == "pending",
            func.lower(func.trim(UnansweredQuestion.question_text)) == normalized,
        )
    )
    existing = existing_result.scalars().first()
    if existing is not None:
        existing.occurrence_count += 1
        existing.last_asked_at = now
    else:
        other_category = await get_or_create_other_category(db)
        unanswered = UnansweredQuestion(
            question_text=question,
            status="pending",
            category_id=other_category.id,
            confidence_score=confidence_score,
            occurrence_count=1,
            last_asked_at=now,
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
        chat_log_id=chat_log.id,
    )
