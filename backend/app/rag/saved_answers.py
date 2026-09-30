"""Answers a repeat (or near-identical) question straight from a published FAQ,
without the LLM.

There is no separate cache. A published FAQ *is* the staff-approved canonical
answer (staff create one with "Save as FAQ" on a chat log, by hand, or by
import), and it is always read live by id — so editing, deleting,
unpublishing or re-importing an FAQ changes what this serves immediately, and
there is nothing to invalidate. Staff can also attach reviewed alternate
phrasings to an FAQ (models/faq_phrasing.py); a phrasing holds no answer text,
it only points at its canonical FAQ.

Two stages, run at different points of the pipeline:

  1. find_exact_answer — BEFORE any AI call. Indexed equality lookups on
     faq_entries.question_normalized, then on the reviewed phrasings'
     faq_phrasings.phrasing_normalized. Cost: zero embedding calls, zero LLM
     calls.
  2. find_paraphrase_answer — after the question has been embedded (the
     pipeline needs that embedding for normal retrieval anyway). Compares it
     with the STORED question-only vectors of FAQs and of enabled phrasings,
     so it adds no embedding call of its own — except for an FAQ saved before
     those vectors existed and not yet backfilled. Never an LLM call.

A saved answer is only served when ALL of these hold:
  * the FAQ is published, and a matched phrasing is enabled (drafts are never
    embedded or served; unanswered questions and chat history are never
    candidates at all);
  * the technical identifiers (error code, controller, model, component,
    measurement, symptom) are compatible with the question's
    (technical_key.compatible) — this is what stops E1 from answering E4, and
    a "clicking" question from getting the "humming" answer;
  * the FAQ applies to the model/product the question names
    (applicability.applies) and its answer is in the question's language,
    and the question doesn't ask for a particular reply language;
  * a matched phrasing still fits its FAQ's (possibly edited) question;
  * [paraphrase only] the question asks for nothing the saved answer doesn't
    cover (asks_for_more);
  * [paraphrase only] it is at least DIRECT_MATCH_*_THRESHOLD similar to the
    FAQ's question or to one of its reviewed phrasings;
  * nobody rated a previous direct answer from it thumbs-down since it was
    last edited;
  * the Library source it was derived from (if any) hasn't changed since;
  * its answer isn't just the fallback/off-topic message.
Anything else falls through to the normal RAG pipeline unchanged.
"""

import logging
import math
import re
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.ai.factory import get_embedding_engine
from app.core import setting_keys as keys
from app.crud.settings import get_all_settings
from app.db.vec_store import (
    FAQ_PHRASING_VEC_TABLE,
    FAQ_QUESTION_VEC_TABLE,
    FAQ_VEC_TABLE,
    get_embeddings,
    knn_search,
)
from app.models.faq import FAQEntry
from app.models.faq_phrasing import FAQPhrasing
from app.rag import response_language
from app.rag.applicability import applies, scope_of
from app.rag.question_normalize import normalize_question
from app.rag.technical_key import TechnicalKey, compatible, extract_key
from app.services.ai_usage import FEATURE_CHAT_QUERY_EMBEDDING, feature_context

# Child of uvicorn's logger so the decision lines reach the server console
# without any extra logging setup. One line per question.
logger = logging.getLogger("uvicorn.error.saved_answers")

# Measured question-to-question similarities on this knowledge base:
#   genuine rewordings of a staff question        0.87 - 0.94
#   same sentence with a different error code     0.88 - 0.92  (E13 / E4)
#   different wordings of one NB-heater issue     0.74 - 0.90
# The first two overlap, which is why the identifier check is mandatory. With
# it in place, 0.90 accepts close rewordings of coded questions; free-text
# questions (nothing to verify) have no such safety net and need 0.93. Looser
# rewordings are not shortcut by lowering these — staff add them as reviewed
# phrasings instead, which are then matched exactly or at the same thresholds.
DIRECT_MATCH_KEYED_THRESHOLD = 0.90
DIRECT_MATCH_FREE_TEXT_THRESHOLD = 0.93

# Nearest neighbours pulled from each vector table before the (free)
# identifier/coverage checks and the similarity threshold decide.
DIRECT_MATCH_CANDIDATE_POOL = 8

ENGINE_FAQ_DIRECT = "faq_direct"

# Words that only make sense with an earlier turn ("how do I fix it?").
_CONTEXT_REFERENCE_RE = re.compile(r"\b(it|this|that|these|those|they|them|same|above|previous)\b", re.I)

# A second request tacked onto the question ("..., also what's the warranty?").
_ADD_ON_RE = re.compile(
    r"\b(also|additionally|as well as|in addition|another question|what about|how about|plus)\b", re.I
)


@dataclass
class DirectMatchDecision:
    stage: str  # "exact" | "paraphrase"
    hit: bool = False
    faq: FAQEntry | None = None
    phrasing_id: int | None = None  # set when a reviewed alternate phrasing matched
    similarity: float | None = None
    threshold: float | None = None
    query_key: TechnicalKey = field(default_factory=TechnicalKey)
    rejected: list[str] = field(default_factory=list)

    def log(self, question: str) -> None:
        logger.info(
            "saved_answer stage=%s hit=%s faq_id=%s phrasing_id=%s similarity=%s threshold=%s key=[%s] rejected=%s llm_pipeline=%s question=%r",
            self.stage,
            self.hit,
            self.faq.id if self.faq else None,
            self.phrasing_id,
            f"{self.similarity:.3f}" if self.similarity is not None else None,
            self.threshold,
            self.query_key.describe(),
            "; ".join(self.rejected[:6]) or "-",
            "skipped" if self.hit else ("next-stage" if self.stage == "exact" else "invoked"),
            question[:120],
        )


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def asks_for_more(question: str, query_key: TechnicalKey, faq: FAQEntry, also_covered: str = "") -> str | None:
    """Reason the saved answer would only partly answer `question`, or None.
    `also_covered` = extra text known to be answered by this FAQ (a matched
    reviewed phrasing). Also used to validate new phrasings
    (crud/faq_phrasing.py).

    Conservative on purpose: a false positive only costs one normal pipeline
    run, a false negative serves an incomplete answer as if it were complete."""
    if _ADD_ON_RE.search(question):
        return "question adds a further request"
    if question.count("?") >= 2:
        return "question contains several questions"
    covered = extract_key(f"{faq.question}\n{faq.answer}\n{also_covered}")
    missing_parts = query_key.parts - covered.parts
    if missing_parts:
        return f"asks about {','.join(sorted(missing_parts))}, not covered by faq {faq.id}"
    missing_units = query_key.units - covered.units
    if missing_units:
        return f"asks about {','.join(sorted(missing_units))}, not covered by faq {faq.id}"
    missing_symptoms = query_key.symptoms - covered.symptoms
    if missing_symptoms:
        return f"describes {','.join(sorted(missing_symptoms))}, not covered by faq {faq.id}"
    return None


def _phrasing_conflict(query_key: TechnicalKey, phrasing: FAQPhrasing, faq: FAQEntry) -> str | None:
    ok, why = compatible(query_key, extract_key(phrasing.phrasing))
    if not ok:
        return f"phrasing {phrasing.id}: {why}"
    # Validated against the FAQ when it was added, but the FAQ's question may
    # have been edited since — a phrasing that no longer fits is not served.
    ok, why = compatible(extract_key(phrasing.phrasing), extract_key(faq.question))
    if not ok:
        return f"phrasing {phrasing.id} no longer fits faq {faq.id}: {why}"
    return None


def _reply_conflict(question: str, faq: FAQEntry) -> str | None:
    """The checks the generated path applies after generation, applied to a
    stored answer before it is served: the product it covers
    (rag/applicability.py — technical_key alone doesn't read letters-only
    model codes such as HES-45NS, or the NS/Ni2 variants) and the language
    it is written in (rag/response_language.py)."""
    if not applies(scope_of(question), scope_of(f"{faq.question}\n{faq.answer}")):
        return f"faq {faq.id} is about another model or product"
    if not response_language.answer_matches(faq.answer, response_language.detect(question)):
        return f"faq {faq.id}'s answer is not in the question's language"
    return None


def _language_request(question: str) -> str | None:
    # A stored answer can't be re-worded, so a question that asks for a
    # particular reply language always goes to generation.
    language = response_language.detect(question)
    return f"asks for a reply in {language.name}" if language.explicit else None


async def _ineligible_reason(db: AsyncSession, faq: FAQEntry) -> str | None:
    # Defense in depth: "Save as FAQ" already refuses fallback/off-topic
    # replies, but an FAQ created any other way whose answer is just the
    # "we'll follow up" message is not an answer and must never be served.
    settings_values = await get_all_settings(db)
    non_answers = {
        normalize_question(settings_values.get(keys.FALLBACK_MESSAGE, "")),
        normalize_question(settings_values.get(keys.OFF_TOPIC_MESSAGE, "")),
    } - {""}
    if normalize_question(faq.answer) in non_answers:
        return f"faq {faq.id}'s answer is the fallback/off-topic message, not an answer"

    downvoted = await db.execute(
        text(
            "SELECT 1 FROM faq_entries f "
            "JOIN chat_logs c ON c.rating = 'down' AND c.engine_used = :engine AND c.created_at >= f.updated_at "
            "JOIN json_each(c.matched_faq_ids) j ON j.value = f.id "
            "WHERE f.id = :fid LIMIT 1"
        ),
        {"engine": ENGINE_FAQ_DIRECT, "fid": faq.id},
    )
    if downvoted.first() is not None:
        return f"faq {faq.id} was rated thumbs-down since its last edit"

    if faq.source_id is not None:
        stale = await db.execute(
            text(
                "SELECT 1 FROM faq_entries f "
                "JOIN vault_entries v ON v.source_id = f.source_id AND v.updated_at > f.updated_at "
                "WHERE f.id = :fid LIMIT 1"
            ),
            {"fid": faq.id},
        )
        if stale.first() is not None:
            return f"faq {faq.id}'s Library source changed after the FAQ was saved"
    return None


# --- stage 1: exact -------------------------------------------------------------


async def find_exact_answer(db: AsyncSession, question: str, *, has_history: bool = False) -> DirectMatchDecision:
    """Same question as a published FAQ or as one of its enabled reviewed
    phrasings, after normalization. Indexed SELECTs only, no AI calls."""
    decision = DirectMatchDecision(stage="exact", query_key=extract_key(question))
    await _find_exact(db, question, has_history, decision)
    if decision.hit or decision.rejected:
        decision.log(question)  # a plain miss is logged once, by the paraphrase stage
    return decision


async def _find_exact(db: AsyncSession, question: str, has_history: bool, decision: DirectMatchDecision) -> None:
    normalized = normalize_question(question)
    if not normalized:
        return
    if has_history and decision.query_key.is_empty and _CONTEXT_REFERENCE_RE.search(question):
        decision.rejected.append("context-dependent question (session history, no technical identifiers)")
        return
    request = _language_request(question)
    if request is not None:
        decision.rejected.append(request)
        return

    result = await db.execute(
        select(FAQEntry)
        .where(FAQEntry.question_normalized == normalized, FAQEntry.status == "published")
        .order_by(FAQEntry.id)
    )
    for faq in result.scalars().all():
        ok, why = compatible(decision.query_key, extract_key(faq.question))
        if not ok:  # e.g. "oPEn" vs "open": identical once lowercased, not the same question
            decision.rejected.append(f"faq {faq.id}: {why}")
            continue
        conflict = _reply_conflict(question, faq)
        if conflict is not None:
            decision.rejected.append(conflict)
            continue
        reason = await _ineligible_reason(db, faq)
        if reason is not None:
            decision.rejected.append(reason)
            continue
        decision.hit, decision.faq, decision.similarity = True, faq, 1.0
        return

    # Same question as a staff-reviewed alternate phrasing: it was approved as
    # meaning exactly this FAQ, so the canonical answer is served.
    phrasing_result = await db.execute(
        select(FAQPhrasing, FAQEntry)
        .join(FAQEntry, FAQEntry.id == FAQPhrasing.faq_id)
        .where(
            FAQPhrasing.phrasing_normalized == normalized,
            FAQPhrasing.enabled.is_(True),
            FAQEntry.status == "published",
        )
    )
    for phrasing, faq in phrasing_result.all():
        why = _phrasing_conflict(decision.query_key, phrasing, faq) or _reply_conflict(question, faq)
        if why is not None:
            decision.rejected.append(why)
            continue
        reason = await _ineligible_reason(db, faq)
        if reason is not None:
            decision.rejected.append(reason)
            continue
        decision.hit, decision.faq, decision.similarity, decision.phrasing_id = True, faq, 1.0, phrasing.id
        return


# --- stage 2: paraphrase ----------------------------------------------------------


async def find_paraphrase_answer(
    db: AsyncSession,
    question: str,
    query_vector: list[float],
    *,
    has_history: bool = False,
) -> DirectMatchDecision:
    """`query_vector` is the embedding of `question` alone, already computed
    by the pipeline for retrieval. No LLM call, and normally no embedding call
    of its own."""
    decision = DirectMatchDecision(stage="paraphrase", query_key=extract_key(question))
    await _find_paraphrase(db, question, query_vector, has_history, decision)
    decision.log(question)
    return decision


async def _find_paraphrase(
    db: AsyncSession, question: str, query_vector: list[float], has_history: bool, decision: DirectMatchDecision
) -> None:
    query_key = decision.query_key
    # A follow-up like "how do I fix it?" only makes sense with the previous
    # turn, and with no identifiers there is nothing to verify it against.
    if has_history and query_key.is_empty:
        decision.rejected.append("context-dependent question (session history, no technical identifiers)")
        return
    request = _language_request(question)
    if request is not None:
        decision.rejected.append(request)
        return

    # Candidates: canonical questions (question-only index, plus the older
    # question+answer index so an FAQ not yet backfilled is still found), and
    # enabled reviewed phrasings.
    faq_ids: list[int] = []
    for table in (FAQ_QUESTION_VEC_TABLE, FAQ_VEC_TABLE):
        for entry_id, _ in await knn_search(db, table, query_vector, DIRECT_MATCH_CANDIDATE_POOL):
            if entry_id not in faq_ids:
                faq_ids.append(entry_id)
    phrasing_ids = [
        pid for pid, _ in await knn_search(db, FAQ_PHRASING_VEC_TABLE, query_vector, DIRECT_MATCH_CANDIDATE_POOL)
    ]

    faqs: dict[int, FAQEntry] = {}
    if faq_ids:
        rows = await db.execute(select(FAQEntry).where(FAQEntry.id.in_(faq_ids), FAQEntry.status == "published"))
        faqs = {f.id: f for f in rows.scalars().all()}
    phrasing_rows = []
    if phrasing_ids:
        phrasing_rows = (
            await db.execute(
                select(FAQPhrasing, FAQEntry)
                .join(FAQEntry, FAQEntry.id == FAQPhrasing.faq_id)
                .where(FAQPhrasing.id.in_(phrasing_ids), FAQPhrasing.enabled.is_(True), FAQEntry.status == "published")
            )
        ).all()

    # (faq, matched phrasing or None) pairs that pass the free checks.
    survivors: list[tuple[FAQEntry, FAQPhrasing | None]] = []
    for faq_id in faq_ids:
        faq = faqs.get(faq_id)
        if faq is None:
            continue
        ok, why = compatible(query_key, extract_key(faq.question))
        if not ok:
            decision.rejected.append(f"faq {faq.id}: {why}")
            continue
        conflict = _reply_conflict(question, faq)
        if conflict is not None:
            decision.rejected.append(conflict)
            continue
        more = asks_for_more(question, query_key, faq)
        if more is not None:
            decision.rejected.append(more)
            continue
        survivors.append((faq, None))
    for phrasing, faq in phrasing_rows:
        why = _phrasing_conflict(query_key, phrasing, faq) or _reply_conflict(question, faq)
        if why is not None:
            decision.rejected.append(why)
            continue
        more = asks_for_more(question, query_key, faq, also_covered=phrasing.phrasing)
        if more is not None:
            decision.rejected.append(more)
            continue
        survivors.append((faq, phrasing))
    if not survivors:
        return

    # Question-only vectors are stored at save time, so normally no embedding
    # call happens here. Only an FAQ saved before they existed (not yet
    # backfilled by the boot-time repair) is embedded on the fly.
    faq_vectors = await get_embeddings(db, FAQ_QUESTION_VEC_TABLE, [f.id for f, p in survivors if p is None])
    phrasing_vectors = await get_embeddings(db, FAQ_PHRASING_VEC_TABLE, [p.id for _f, p in survivors if p is not None])
    missing = list({f.id: f for f, p in survivors if p is None and f.id not in faq_vectors}.values())
    if missing:
        try:
            engine = await get_embedding_engine(db)
            with feature_context(FEATURE_CHAT_QUERY_EMBEDDING):
                vectors = await engine.embed([f.question for f in missing])
            faq_vectors.update({faq.id: vector for faq, vector in zip(missing, vectors)})
        except AIEngineError:
            decision.rejected.append("candidate embedding unavailable")

    scored = []
    for faq, phrasing in survivors:
        vector = phrasing_vectors.get(phrasing.id) if phrasing is not None else faq_vectors.get(faq.id)
        if vector is not None:
            scored.append((_cosine(query_vector, vector), faq, phrasing))
    scored.sort(key=lambda item: item[0], reverse=True)

    threshold = DIRECT_MATCH_FREE_TEXT_THRESHOLD if query_key.is_empty else DIRECT_MATCH_KEYED_THRESHOLD
    decision.threshold = threshold
    for similarity, faq, phrasing in scored:
        label = f"phrasing {phrasing.id} (faq {faq.id})" if phrasing is not None else f"faq {faq.id}"
        if similarity < threshold:
            decision.rejected.append(f"{label}: similarity {similarity:.3f} < {threshold}")
            if decision.similarity is None:
                decision.similarity = similarity
            break  # sorted: every later candidate is lower still
        reason = await _ineligible_reason(db, faq)
        if reason is not None:
            decision.rejected.append(reason)
            continue
        decision.hit, decision.faq, decision.similarity = True, faq, similarity
        decision.phrasing_id = phrasing.id if phrasing is not None else None
        return
