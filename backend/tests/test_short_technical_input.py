"""Phase 8 — short technical input handling, exercised through the real
pipeline.

Reproduces the live failure: a bare "E1?" is exactly as short as "meh" or
"abc" (filler.is_filler's <=4-char heuristic can't tell them apart from
length alone), so it was redirected to the off-topic small-talk reply before
the technical pipeline — saved-answer matching, retrieval, applicability —
ever saw it.

The fix (app.rag.pipeline._has_documented_identifier) gives a short message
is_filler flags one more chance: if technical_key.extract_key finds a code or
part identifier in it (E1, TS1, oPEn, ...) AND that exact identifier is
documented somewhere in the KB (a published FAQ, an enabled phrasing, or
memory-enabled Library content), it is treated as a real technical question
instead of small talk. An undocumented short string (e.g. "Q9") is still
filler — the mechanism is general, not hardcoded to E1, and does not lower
any similarity threshold.

Product-less fixtures (GENERIC_*) are used for the saved-answer/phrasing
tests below deliberately: a bare "E1?" names no controller, and
faq_phrasing's own existing validation (technical_key.compatible) already
refuses to attach a product-less phrasing to a product-specific FAQ ("Innova
E1" is not the same question as "Saunova E1") — Phase 8 must not weaken that,
so these tests exercise it against an FAQ that is itself product-less."""

from app.crud.faq_phrasing import create_phrasing
from app.rag import pipeline
from app.rag.applicability import scope_of
from app.rag.filler import is_filler
from app.rag.response_language import detect
from app.rag.saved_answers import find_exact_answer
from app.rag.technical_key import extract_key
from tests.conftest import ANGLES, add_faq
from tests.conftest import angle as _angle
from tests.test_applicability import add_page

GENERIC_E1_Q = "Error 1 (E1) — Temperature Sensor 1 (TS1) is not connected: what causes it and how do we fix it?"
GENERIC_E1_A = "E1 means Temperature Sensor 1 (TS1) is not connected. Check the TS1 wiring."
GENERIC_E7_Q = "Error 7 (E7) — Heating Element Failure: what causes it and how do we fix it?"
GENERIC_E7_A = "E7 means a heating element circuit has failed. Check the element wiring and resistance."
GENERIC_OPEN_Q = "Display shows oPEn (Open Circuit): what causes it and how do we fix it?"
GENERIC_OPEN_A = "oPEn means an open circuit was detected in the heating element. Check the element wiring."

INNOVA_E1_Q = "Innova Power Controller Error 1 (E1) — Temperature Sensor 1 (TS1) is not connected: what causes it and how do we fix it?"
INNOVA_E1_A = "E1 means Temperature Sensor 1 (TS1) is not connected. Check the TS1 wiring on the Innova."
STE_E1_Q = "STE Board Error 1 (E1) — Temperature Sensor 1 (TS1) is not connected: what causes it and how do we fix it?"
STE_E1_A = "On the STE board, E1 means TS1 is not connected. Reseat the TS1 connector on the STE board."

NS_PAGE_TITLE = "SAWO30 Round NS (short-input fixture)"
NS_PAGE_URL = "https://www.sawo.com/sawo30-round-ns-short-input/"
NS_PAGE = (
    "SAWO30 Round NS\nFeatures:\n- Available controls: Saunova/Innova (NS)\n"
    "Heater Model | kW\nSW3-45NS-P-C | 4.5"
)
NS_MODEL_QUESTION = "I'm asking about SW3-45NS."

ANGLES.update({
    NS_PAGE_TITLE: 300.0,
    NS_MODEL_QUESTION: 300.0 + _angle(0.8),
})


def contexts(llm) -> list[str]:
    return [context for system, context, _q in llm.calls if not system.startswith("You are a fact-checker")]


def last_generation_system(llm) -> str:
    """The system prompt of the last real generation call, skipping any
    fact-checker (grounding-check) call that may have followed it."""
    return [system for system, _c, _q in llm.calls if not system.startswith("You are a fact-checker")][-1]


# --- unit: extract_key / detect are unaffected (no DB, sanity checks) --------------------


def test_extract_key_reads_short_codes_without_a_database():
    assert extract_key("E1?").codes == {"E1"}
    assert extract_key("E1").codes == {"E1"}
    assert extract_key("oPEn?").codes == {"OPEN"}
    assert extract_key("Hi").is_empty
    assert extract_key("Help").is_empty


def test_short_technical_identifiers_carry_no_language_signal():
    for text in ("E1?", "E1", "oPEn?", "Er1"):
        language = detect(text)
        assert language.explicit is False and language.name is None


# --- Test 1 & 2: E1 with and without punctuation -----------------------------------------


async def test_e1_with_question_mark_is_recognized_as_technical(db, embedder, llm):
    faq = await add_faq(db, GENERIC_E1_Q, GENERIC_E1_A)
    await create_phrasing(db, faq, "E1?", created_by_id=None, enabled=True)

    assert is_filler("E1?")  # still true: this is exactly what the fix must see past
    result = await pipeline.answer_question(db, "E1?", session_id="s-e1-qmark")
    assert not result.is_fallback
    assert result.engine_used == "faq_direct" and result.answer == GENERIC_E1_A
    assert llm.generate_calls == 0  # no LLM call needed — matched via saved answer


async def test_e1_without_punctuation_is_recognized_as_technical(db, embedder, llm):
    faq = await add_faq(db, GENERIC_E1_Q, GENERIC_E1_A)
    await create_phrasing(db, faq, "E1?", created_by_id=None, enabled=True)

    assert is_filler("E1")
    result = await pipeline.answer_question(db, "E1", session_id="s-e1-bare")
    assert not result.is_fallback
    assert result.engine_used == "faq_direct" and result.answer == GENERIC_E1_A


# --- Test 3: another documented error code, not hardcoded --------------------------------


async def test_another_documented_error_code_is_recognized_generically(db, embedder, llm):
    faq = await add_faq(db, GENERIC_E7_Q, GENERIC_E7_A)
    await create_phrasing(db, faq, "E7?", created_by_id=None, enabled=True)

    assert is_filler("E7?")
    result = await pipeline.answer_question(db, "E7?", session_id="s-e7")
    assert not result.is_fallback
    assert result.engine_used == "faq_direct" and result.answer == GENERIC_E7_A


# --- Test 4: a documented non-E-series status code ----------------------------------------


async def test_documented_open_status_code_is_recognized(db, embedder, llm):
    faq = await add_faq(db, GENERIC_OPEN_Q, GENERIC_OPEN_A)
    await create_phrasing(db, faq, "oPEn?", created_by_id=None, enabled=True)

    assert is_filler("oPEn?")
    result = await pipeline.answer_question(db, "oPEn?", session_id="s-open")
    assert not result.is_fallback
    assert result.engine_used == "faq_direct" and result.answer == GENERIC_OPEN_A


# --- Test 5 & 6: ordinary short messages stay small talk ----------------------------------


async def test_ordinary_greeting_stays_small_talk(db, embedder, llm):
    await add_faq(db, GENERIC_E1_Q, GENERIC_E1_A)  # documented content present, but irrelevant here
    result = await pipeline.answer_question(db, "Hi", session_id="s-hi")
    assert result.is_fallback
    assert result.matched_faq_ids == [] and result.engine_used != "faq_direct"


async def test_ordinary_short_word_does_not_become_technical(db, embedder, llm):
    await add_faq(db, GENERIC_E1_Q, GENERIC_E1_A)
    result = await pipeline.answer_question(db, "Help", session_id="s-help")
    assert result.is_fallback
    assert result.matched_faq_ids == [] and result.engine_used != "faq_direct"


# --- Test 7: an undocumented short identifier is not assumed technical -------------------


async def test_undocumented_short_identifier_stays_filler(db, embedder, llm):
    await add_faq(db, GENERIC_E1_Q, GENERIC_E1_A)  # KB has content, but nothing mentions "Q9"
    assert extract_key("Q9?").parts == {"Q9"}  # matches technical_key's pattern...
    result = await pipeline.answer_question(db, "Q9?", session_id="s-q9")
    assert result.is_fallback  # ...but isn't documented anywhere, so it's still small talk
    assert result.matched_faq_ids == [] and result.engine_used != "faq_direct"


# --- Test 8: saved-answer / phrasing compatibility, no unnecessary LLM call ---------------


async def test_short_phrasing_reuses_the_approved_answer_with_no_llm_call(db, embedder, llm):
    faq = await add_faq(db, GENERIC_E1_Q, GENERIC_E1_A)
    await create_phrasing(db, faq, "E1?", created_by_id=None, enabled=True)

    decision = await find_exact_answer(db, "E1?")
    assert decision.hit and decision.faq.id == faq.id and decision.phrasing_id is not None

    result = await pipeline.answer_question(db, "E1?", session_id="s-saved-e1")
    assert result.engine_used == "faq_direct" and result.answer == GENERIC_E1_A
    assert llm.generate_calls == 0


# --- Test 9: model applicability still filters short-code follow-ups ---------------------


async def test_short_error_code_follow_up_still_respects_model_applicability(db, embedder, llm):
    await add_page(db, NS_PAGE_TITLE, NS_PAGE, NS_PAGE_URL)  # SW3-45NS -> Saunova/Innova link
    await add_faq(db, INNOVA_E1_Q, INNOVA_E1_A)
    await add_faq(db, STE_E1_Q, STE_E1_A)  # a different, unlinked controller's E1

    await pipeline.answer_question(db, NS_MODEL_QUESTION, session_id="s-applic-followup")
    await pipeline.answer_question(db, "E1?", session_id="s-applic-followup")

    assert not any(STE_E1_A in c for c in contexts(llm))  # never even shown to the model


# --- Test 10: follow-up model context is retained for a bare code ------------------------


async def test_follow_up_bare_error_code_keeps_the_previous_models_scope(db, embedder, llm):
    await add_page(db, NS_PAGE_TITLE, NS_PAGE, NS_PAGE_URL)
    await add_faq(db, INNOVA_E1_Q, INNOVA_E1_A)

    await pipeline.answer_question(db, NS_MODEL_QUESTION, session_id="s-context-followup")
    await pipeline.answer_question(db, "E1?", session_id="s-context-followup")

    assert scope_of(NS_MODEL_QUESTION).models == {"SW3-45NS"}
    assert scope_of("E1?").is_empty  # the bare code names no product of its own
    assert "specifically about: SW3-45NS" in last_generation_system(llm)  # scope carried over


# --- Test 11: language protection is unaffected -------------------------------------------


async def test_language_protection_unaffected_by_short_technical_input(db, embedder, llm):
    faq = await add_faq(db, GENERIC_E1_Q, GENERIC_E1_A)
    await create_phrasing(db, faq, "E1?", created_by_id=None, enabled=True)

    result = await pipeline.answer_question(db, "E1?", session_id="s-lang")
    assert not result.is_fallback and result.answer == GENERIC_E1_A  # English answer, unchanged


# --- Test 12: existing (long-form) technical questions are unaffected ---------------------


async def test_normal_length_technical_question_behaves_as_before(db, embedder, llm):
    faq = await add_faq(db, GENERIC_E1_Q, GENERIC_E1_A)
    assert not is_filler(GENERIC_E1_Q)  # long enough to never have hit the filler gate

    result = await pipeline.answer_question(db, GENERIC_E1_Q, session_id="s-normal")
    assert result.engine_used == "faq_direct" and result.matched_faq_ids == [faq.id]
