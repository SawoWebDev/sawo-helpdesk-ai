"""Phase 6 — controller relationship evidence, exercised through the real pipeline.

Reproduces the live failure: "SW3-45NS shows E1" is documented — the SW3-45NS
product page says "Available controls: Saunova/Innova (NS)", and the KB has
an Innova/Saunova E1 FAQ — but the product page itself scores too low on
semantic similarity to the question (it describes specs, not the error) to
clear the retrieval floor. applicability.linked_controllers() already reads
that page directly from the DB (no similarity involved) to let the E1 FAQ
past the model/controller filter, so the FAQ reaches the model — but the page
that actually ties "SW3-45NS" to "Innova/Saunova" never did, leaving nothing
in CONTEXT for a real answer (or a real fact-checker) to point to when the
model name appears in the reply.

app.rag.applicability.linked_controller_pages() and the injection in
app.rag.pipeline._answer_question_impl fix that by adding that specific page
to context as relationship evidence — deliberately, only when something in
the final context needed the controller link to be considered applicable —
without lowering off_topic_threshold and without any SW3-45NS/E1-specific
logic."""

from app.rag import pipeline
from app.rag.applicability import linked_controller_pages, scope_of
from tests.conftest import ANGLES, add_faq, vector_for
from tests.conftest import angle as _angle
from tests.test_applicability import add_page
from tests.test_response_language import DriftingLLM

SW_PAGE_TITLE = "SW3-45NS Product Page"
SW_PAGE_URL = "https://www.sawo.com/sw3-45ns/"
SW_PAGE = (
    "SW3-45NS Product Page\nFeatures:\n- Available controls: Saunova/Innova (NS)\n"
    "Heater Model | kW\nSW3-45NS-P-C | 4.5"
)
MULTI_PAGE_TITLE = "SW5-90NS Product Page"
MULTI_PAGE_URL = "https://www.sawo.com/sw5-90ns/"
MULTI_PAGE = (
    "SW5-90NS Product Page\nFeatures:\n- Available controls: Saunova/Innova (NS) or STE\n"
    "Heater Model | kW\nSW5-90NS-P-C | 9.0"
)
NO_LINK_PAGE_TITLE = "CUB3-45NB Product Page"
NO_LINK_PAGE_URL = "https://www.sawo.com/cub3-45nb/"
NO_LINK_PAGE = "CUB3-45NB Product Page\nHeater Model | kW\nCUB3-45NB-P-C | 4.5\nStones: 20 kg"

INNOVA_E1_Q = "Innova Power Controller Error 1 (E1) explanation"
INNOVA_E1_A = "E1 means Temperature Sensor 1 (TS1) is not connected. Check the TS1 wiring on the Innova/Saunova control."
STE_E1_Q = "STE Board Error 1 (E1) explanation"
STE_E1_A = "On the STE board, E1 means TS1 is not connected. Reseat the TS1 connector."
GENERAL_WARRANTY_Q = "What is the general warranty policy for SAWO heaters?"
GENERAL_WARRANTY_A = "SAWO heaters carry a 2-year warranty from the date of purchase."

SW_E1_QUESTION = "SW3-45NS shows E1, what does it mean?"
MULTI_E1_QUESTION = "SW5-90NS shows E1, what does it mean?"
FOLLOW_UP = "why does it show E1?"

NB_HUM_Q = "NB heater: humming sound from the timer/control area — causes and fix?"
NB_HUM_A = "A worn timer motor. Disconnect the elements from the timer and test it separately; replace if needed."
NB_HUM_QUESTION = "My NB sauna heater is making a loud humming noise near the timer area, how do I fix it?"
SW_HUM_QUESTION = "My SW3-45NS heater is making a loud humming noise near the control panel, how do I fix it?"

NAV = (
    "Heater Accessories Infrared Sauna Controls Innova Series Interface Holders Latest News "
    "Nordex Mini Ni2 Sauna Accessories Sauna Controls Sauna Rooms Saunova Series"
)
GENERAL_PAGE_TITLE = "https://www.sawo.com/general-care-tips/ (phase-6 relationship-evidence fixture)"
GENERAL_PAGE = f"{NAV}\nNever use the heater without stones. Use only SAWO-recommended stones."
GENERAL_STONES_QUESTION = "How often should I change the stones in my heater, generally speaking?"

SHARED_HUM_Q = "NB and NS heaters (relationship-evidence fixture): contactor humming — applies to both. How do we fix it?"
SHARED_HUM_A = "Tighten the contactor terminals and check the supply voltage matches the rating plate."

NS_SAVED_STYLE = "SW3-45NS heater (relationship-evidence fixture): Humming Sound — loud humming from the timer/control area."

# A fresh angle range (200s), independent of other test modules' registrations
# — ANGLES is shared process-wide, but each test's data lives in its own
# per-test temporary database, so only the *shapes* below (which texts are
# close/far to which) matter, not overlap with other files' numbers.
INNOVA_E1_ANGLE = 204.0  # kept well apart (4.0 rad) from SW_PAGE_TITLE's 200.0, below

ANGLES.update({
    SW_PAGE_TITLE: 200.0,
    MULTI_PAGE_TITLE: 200.0,  # never both present in the same test
    NO_LINK_PAGE_TITLE: 200.0,
    INNOVA_E1_Q: INNOVA_E1_ANGLE,
    STE_E1_Q: INNOVA_E1_ANGLE + _angle(0.9),
    # 0.6 similarity to the E1 FAQ (between off_topic_threshold and
    # confidence_threshold, so the FAQ ranks but isn't the primary tier —
    # exercising the merged FAQ+Library pool the off_topic floor applies to)
    # and, since SW_PAGE_TITLE sits 4.0 rad away in the opposite direction,
    # a strongly negative (nowhere near 0.35) similarity to the product page.
    SW_E1_QUESTION: INNOVA_E1_ANGLE - _angle(0.6),
    MULTI_E1_QUESTION: INNOVA_E1_ANGLE - _angle(0.85),
    # GENERAL_WARRANTY_Q is deliberately left unregistered: an unregistered
    # text defaults to a vector orthogonal to every registered one (see
    # conftest.vector_for), giving it ~0 similarity to SW_E1_QUESTION —
    # unambiguously below off_topic_threshold, with no risk of an
    # accidental near-multiple-of-2*pi collision the way two arbitrary
    # registered angles could have.
    NB_HUM_Q: 230.0,
    NB_HUM_QUESTION: 230.0 + _angle(0.86),
    SW_HUM_QUESTION: 230.0 - _angle(0.86),
    GENERAL_PAGE_TITLE: 240.0,
    GENERAL_STONES_QUESTION: 240.0 + _angle(0.8),
    SHARED_HUM_Q: 230.0 - _angle(0.97),
    NS_SAVED_STYLE: 230.0 + _angle(0.97),
    f"{SW_E1_QUESTION} {FOLLOW_UP}": INNOVA_E1_ANGLE - _angle(0.6),
})


def contexts(llm) -> list[str]:
    return [context for system, context, _q in llm.calls if not system.startswith("You are a fact-checker")]


# --- Test 1: SW3-45NS -> E1 ------------------------------------------------------------


async def test_low_scoring_product_page_is_included_as_relationship_evidence(db, embedder, llm):
    await add_page(db, SW_PAGE_TITLE, SW_PAGE, SW_PAGE_URL)
    await add_faq(db, INNOVA_E1_Q, INNOVA_E1_A)
    result = await pipeline.answer_question(db, SW_E1_QUESTION, session_id="s-e1-evidence")

    assert not result.is_fallback
    [context] = contexts(llm)
    assert INNOVA_E1_A in context  # the controller FAQ itself
    assert "Available controls: Saunova/Innova (NS)" in context  # the evidence tying it to SW3-45NS
    assert "SW3-45NS" in context


# --- Test 2: the global retrieval floor is unchanged ------------------------------------


async def test_unrelated_low_scoring_content_is_still_excluded(db, embedder, llm):
    await add_page(db, SW_PAGE_TITLE, SW_PAGE, SW_PAGE_URL)
    await add_faq(db, INNOVA_E1_Q, INNOVA_E1_A)
    await add_faq(db, GENERAL_WARRANTY_Q, GENERAL_WARRANTY_A)  # general, but far below the floor for this question
    result = await pipeline.answer_question(db, SW_E1_QUESTION, session_id="s-floor")

    assert not result.is_fallback
    [context] = contexts(llm)
    assert GENERAL_WARRANTY_A not in context  # never rescued by the evidence mechanism


# --- Test 3: NB humming regression, with relationship evidence in the same KB -----------


async def test_nb_humming_regression_alongside_relationship_evidence(db, embedder, llm):
    await add_page(db, SW_PAGE_TITLE, SW_PAGE, SW_PAGE_URL)  # establishes an unrelated SW3-45NS/controller link
    await add_faq(db, NB_HUM_Q, NB_HUM_A)

    nb_result = await pipeline.answer_question(db, NB_HUM_QUESTION, session_id="s-nb-hum")
    assert not nb_result.is_fallback
    assert any(NB_HUM_A in c for c in contexts(llm))

    sw_result = await pipeline.answer_question(db, SW_HUM_QUESTION, session_id="s-sw-hum")
    assert sw_result.is_fallback  # the humming FAQ is NB-only; the link is to a controller, not to NB troubleshooting
    assert not any(NB_HUM_A in c for c in contexts(llm)[1:])


# --- Test 4: general crawled page stays general -----------------------------------------


async def test_general_page_with_nav_menu_stays_general(db, embedder, llm):
    await add_page(db, SW_PAGE_TITLE, SW_PAGE, SW_PAGE_URL)
    page = await add_page(db, GENERAL_PAGE_TITLE, GENERAL_PAGE, "https://www.sawo.com/frequently-asked-questions/")
    page.source_type = "library"
    await db.commit()

    result = await pipeline.answer_question(db, GENERAL_STONES_QUESTION, session_id="s-general")
    assert not result.is_fallback
    assert any("SAWO-recommended stones" in c for c in contexts(llm))
    # The nav menu's Innova/Saunova mentions must not pull in the (unrelated) SW3-45NS page as "evidence".
    assert not any("Available controls" in c for c in contexts(llm))

    # And the function itself must not treat a harvested page's nav-menu text as a
    # controller link, mirroring applicability.linked_controllers' own guarantee.
    assert await linked_controller_pages(db, scope_of("SW3-45NB")) == []


# --- Test 5: shared documentation remains usable ----------------------------------------


async def test_shared_documentation_remains_usable(db, embedder, llm):
    await add_page(db, SW_PAGE_TITLE, SW_PAGE, SW_PAGE_URL)
    await add_faq(db, NB_HUM_Q, NB_HUM_A)
    await add_faq(db, SHARED_HUM_Q, SHARED_HUM_A)
    result = await pipeline.answer_question(db, SW_HUM_QUESTION, session_id="s-shared")
    assert not result.is_fallback
    assert any(SHARED_HUM_A in c for c in contexts(llm))
    assert not any(NB_HUM_A in c for c in contexts(llm))


# --- Test 6: missing relationship is never fabricated -----------------------------------


async def test_model_without_documented_controller_gets_no_evidence(db, embedder, llm):
    await add_page(db, NO_LINK_PAGE_TITLE, NO_LINK_PAGE, NO_LINK_PAGE_URL)  # no "Available controls" line
    await add_faq(db, INNOVA_E1_Q, INNOVA_E1_A)
    result = await pipeline.answer_question(db, "CUB3-45NB shows E1, what does it mean?", session_id="s-nolink")
    assert result.is_fallback  # no documented link -> the E1 FAQ never becomes applicable
    assert not any(INNOVA_E1_A in c for c in contexts(llm))
    assert await linked_controller_pages(db, scope_of("CUB3-45NB")) == []


# --- Test 7: follow-up retains the relationship -----------------------------------------


async def test_followup_question_keeps_relationship_evidence(db, embedder, llm):
    await add_page(db, SW_PAGE_TITLE, SW_PAGE, SW_PAGE_URL)
    await add_faq(db, INNOVA_E1_Q, INNOVA_E1_A)
    await pipeline.answer_question(db, SW_E1_QUESTION, session_id="s-followup")
    await pipeline.answer_question(db, FOLLOW_UP, session_id="s-followup")
    assert "Available controls: Saunova/Innova (NS)" in contexts(llm)[-1]


# --- Test 8: multiple documented controllers --------------------------------------------


async def test_multiple_controller_relationship_is_not_assumed_to_be_singular(db, embedder, llm):
    await add_page(db, MULTI_PAGE_TITLE, MULTI_PAGE, MULTI_PAGE_URL)
    await add_faq(db, INNOVA_E1_Q, INNOVA_E1_A)
    await add_faq(db, STE_E1_Q, STE_E1_A)
    result = await pipeline.answer_question(db, MULTI_E1_QUESTION, session_id="s-multi")
    assert not result.is_fallback
    [context] = contexts(llm)
    # Both controllers the page documents are usable...
    assert INNOVA_E1_A in context and STE_E1_A in context
    # ...and the evidence page itself is only included once.
    assert context.count("Available controls: Saunova/Innova (NS) or STE") == 1


# --- Test 9: saved-answer applicability is unaffected -----------------------------------


async def test_relationship_evidence_does_not_bypass_saved_answer_applicability(db, embedder, llm):
    from app.rag.saved_answers import find_paraphrase_answer

    await add_page(db, SW_PAGE_TITLE, SW_PAGE, SW_PAGE_URL)
    await add_faq(db, NB_HUM_Q, NB_HUM_A)
    decision = await find_paraphrase_answer(db, NS_SAVED_STYLE, vector_for(NS_SAVED_STYLE))
    assert not decision.hit
    result = await pipeline.answer_question(db, NS_SAVED_STYLE, session_id="s-saved-evidence")
    assert result.engine_used != "faq_direct" and NB_HUM_A not in result.answer


# --- Test 10: response-language protection is unaffected --------------------------------


async def test_relationship_evidence_does_not_bypass_language_protection(db, embedder, monkeypatch):
    drifting = DriftingLLM(stubborn="E1 表示 TS1 未连接。")  # ignores the English instruction

    async def _get(_db):
        return drifting

    monkeypatch.setattr(pipeline, "get_active_engine", _get)

    await add_page(db, SW_PAGE_TITLE, SW_PAGE, SW_PAGE_URL)
    await add_faq(db, INNOVA_E1_Q, INNOVA_E1_A)
    result = await pipeline.answer_question(db, SW_E1_QUESTION, session_id="s-lang-evidence")
    assert result.is_fallback  # the extra evidence context must not let a wrong-language reply through
    assert "TS1" not in result.answer
