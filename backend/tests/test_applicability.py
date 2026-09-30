"""Model/controller applicability, exercised through the real pipeline.

Reproduces the live failure: a humming question naming the SW3-45NS received
the NB heater's timer troubleshooting, because the NB FAQ is worded almost
identically and nothing downstream of similarity search knew the question
named a different product."""

from sqlalchemy import select

from app.db.vec_store import VAULT_VEC_TABLE, upsert_embedding
from app.models.unanswered import UnansweredQuestion
from app.models.vault_entry import VaultEntry
from app.rag import pipeline
from app.rag.applicability import applies, linked_controllers, scope_of
from app.rag.saved_answers import find_paraphrase_answer
from tests.conftest import ANGLES, add_faq, vector_for
from tests.conftest import angle as _angle

NB_HUM_Q = (
    "NB heater: Humming Sound in a heater — the loud humming appears to come from the NB timer/control "
    "area. What are the causes and how do we fix it?"
)
NB_HUM_A = (
    "- **Cause:** A worn or defective mechanical timer motor.\n"
    "  **Troubleshooting:** Temporarily disconnect the heating elements from the timer and test the timer separately.\n"
    "  **Solution:** Replace the timer if the humming continues."
)
SHARED_HUM_Q = "NB and NS heaters: contactor humming — applies to both NB and NS heaters. How do we fix it?"
SHARED_HUM_A = "Tighten the contactor terminals and check the supply voltage matches the rating plate."
INNOVA_E1_Q = "Innova Power Controller Error 1 (E1) — Temperature Sensor 1 (TS1) is not connected"
INNOVA_E1_A = "E1 means Temperature Sensor 1 (TS1) is not connected. Check the TS1 wiring on the Innova."
STE_E1_Q = "STE Board Error 1 (E1) — Temperature Sensor 1 (TS1) is not connected"
STE_E1_A = "On the STE board, E1 means TS1 is not connected. Reseat the TS1 connector on the STE board."

NS_PAGE_TITLE = "SAWO30 Round NS"
NS_PAGE = (
    "SAWO30 Round NS\nFeatures:\n- Available controls: Saunova/Innova (NS)\n"
    "Heater Model | kW\nSW3-45NS-P-C | 4.5\nSW3-60NS-P-C | 6.0\n"
    "Manual: https://www.sawo.com/wp-content/uploads/2025/10/SAWO30-Round-NS-NB_FiEn-3P-1P.pdf"
)
CUBE_PAGE_TITLE = "Cubos NB"
CUBE_PAGE = "Cubos NB\nHeater Model | kW\nCUB3-45NB-P-C | 4.5\nStones: 20 kg"

GENERIC_Q = "Heater: Heating elements not working — some elements glow while others stay dark"
GENERIC_A = "Check each element's resistance and replace any element that reads open circuit."
WEAK_STE_Q = "STE Board: steam generator fill valve clicks"

NB_QUESTION = "My NB sauna heater is making a loud humming noise from the timer, how do I fix it?"
NS_QUESTION = "My SW3-45NS heater is making a loud humming noise from the control area, how do I fix it?"
NS_E1_QUESTION = "The SW3-45NS shows E1, what does it mean?"
CUBE_NS_QUESTION = "How many kg of stones does the CUB3-45NS take?"
NS_KW_QUESTION = "what kW is the SW3-45NS"
NS_WARRANTY_QUESTION = "what is the warranty period of the SW3-45NS"
NS_SAVED_STYLE = "SW3-45NS heater: Humming Sound — loud humming from the timer/control area. Causes and fix?"
FOLLOW_UP = "why is it humming so loudly?"

ANGLES.update({
    NB_HUM_Q: 10.0,
    NB_QUESTION: 10.0 + _angle(0.86),
    NS_QUESTION: 10.0 - _angle(0.86),  # as close to the NB FAQ as the NB question is
    SHARED_HUM_Q: 10.0 - _angle(0.97),
    GENERIC_Q: 10.0 - _angle(0.86) - _angle(0.60),
    WEAK_STE_Q: 10.0 - _angle(0.86) + _angle(0.50),
    INNOVA_E1_Q: 12.0,
    STE_E1_Q: 12.0 + _angle(0.95),
    NS_E1_QUESTION: 12.0 - _angle(0.85),
    CUBE_PAGE_TITLE: 14.0,
    CUBE_NS_QUESTION: 14.0 + _angle(0.85),
    NS_PAGE_TITLE: 16.0,
    NS_KW_QUESTION: 16.0 + _angle(0.8),
    NS_WARRANTY_QUESTION: 16.0 - _angle(0.8),
    NS_SAVED_STYLE: 10.0 + _angle(0.97),
    f"{NS_KW_QUESTION} {FOLLOW_UP}": 10.0 + _angle(0.86),
})


async def add_page(db, title, content, url):
    entry = VaultEntry(title=title, content=content, source_url=url, memory_enabled=True)
    db.add(entry)
    await db.commit()
    await upsert_embedding(db, VAULT_VEC_TABLE, entry.id, vector_for(title))
    return entry


def contexts(llm) -> list[str]:
    return [context for system, context, _q in llm.calls if not system.startswith("You are a fact-checker")]


# --- scope rules -------------------------------------------------------------------


def test_scope_reads_models_variants_and_controllers():
    s = scope_of(NS_QUESTION)
    assert s.models == {"SW3-45NS"} and s.labels == {"NS"}
    assert scope_of(NB_HUM_Q).labels == {"NB"} and not scope_of(NB_HUM_Q).models
    assert scope_of("Innova shows E1").labels == {"INNOVA"}
    assert scope_of("what is the warranty on heaters").is_empty
    assert scope_of("the 15-minute timer on 392-D").is_empty  # article numbers and noise never scope


def test_model_codes_match_their_option_variants_only():
    ns = scope_of("SW3-45NS")
    assert applies(ns, scope_of("SW3-45NS-P-C | 4.5"))
    assert not applies(ns, scope_of("SW3-45NB-P-C | 4.5"))
    assert not applies(ns, scope_of("SW3-450NS-P | 45"))
    assert applies(scope_of("SW3-45"), scope_of("SW3-45NB-P-C"))
    assert applies(ns, scope_of("the SW3-45NS-based sauna"))


def test_letter_only_family_codes_are_models_too():
    # Other NS heaters' pages: sharing the NS variant does not make them the SW3-45NS.
    ns = scope_of("SW3-45NS")
    for page in ("HES-45NS-G-P-C | 4.5", "SCAC-60NS-Z-C | 6.0", "TRDC-90/120NS-G-P | 9.0/12.0"):
        page_scope = scope_of(page)
        assert page_scope.models and "NS" in page_scope.labels
        assert not applies(ns, page_scope)
    assert scope_of("hes-45ns-g-p-c").is_empty  # letters-only codes must be written as the docs do
    assert scope_of("in the mid-60s").is_empty


# --- pipeline ------------------------------------------------------------------------


async def test_nb_question_uses_the_nb_documentation(db, embedder, llm):
    await add_faq(db, NB_HUM_Q, NB_HUM_A)
    result = await pipeline.answer_question(db, NB_QUESTION, session_id="s-nb")
    assert not result.is_fallback and result.answer == "Generated answer"
    assert any(NB_HUM_A in c for c in contexts(llm))


async def test_sw3_45ns_question_never_receives_nb_troubleshooting(db, embedder, llm):
    await add_faq(db, NB_HUM_Q, NB_HUM_A)
    result = await pipeline.answer_question(db, NS_QUESTION, session_id="s-ns")

    assert not any(NB_HUM_A in c for c in contexts(llm))  # never even shown to the model
    assert "timer" not in result.answer.lower()
    assert result.is_fallback
    assert "SW3-45NS" in result.answer and "NB" in result.answer
    assert "doesn't establish" in result.answer
    assert llm.generate_calls == 0  # the limitation needs no AI call
    pending = (await db.execute(select(UnansweredQuestion))).scalars().all()
    assert [u.question_text for u in pending] == [NS_QUESTION]  # staff see the gap


async def test_limitation_names_only_what_outranked_the_usable_content(db, embedder, llm):
    await add_faq(db, NB_HUM_Q, NB_HUM_A)  # 0.86 — removed, and would have been the answer
    await add_faq(db, GENERIC_Q, GENERIC_A)  # 0.60 — general, kept
    await add_faq(db, WEAK_STE_Q, STE_E1_A)  # 0.50 — removed, but ranked below what was kept
    llm.reply = pipeline.REFUSAL_SENTINEL
    result = await pipeline.answer_question(db, NS_QUESTION, session_id="s-named")
    assert result.is_fallback
    assert "found is for NB," in result.answer and "STE" not in result.answer


async def test_model_without_matching_documentation_gets_a_limitation_reply(db, embedder, llm):
    await add_page(db, CUBE_PAGE_TITLE, CUBE_PAGE, "https://www.sawo.com/cubos-nb/")
    result = await pipeline.answer_question(db, CUBE_NS_QUESTION, session_id="s-cube")
    assert result.is_fallback
    assert "CUB3-45NS" in result.answer and "doesn't establish" in result.answer
    assert "20 kg" not in result.answer
    assert contexts(llm) == []


async def test_model_question_the_llm_cannot_answer_gets_the_limitation_not_a_guess(db, embedder, llm):
    await add_page(db, NS_PAGE_TITLE, NS_PAGE, "https://www.sawo.com/sawo30-round-ns/")
    llm.reply = pipeline.REFUSAL_SENTINEL
    result = await pipeline.answer_question(db, NS_WARRANTY_QUESTION, session_id="s-ref")
    assert result.is_fallback and "doesn't establish an answer to this for SW3-45NS" in result.answer


async def test_documentation_that_explicitly_covers_both_models_stays_usable(db, embedder, llm):
    await add_faq(db, NB_HUM_Q, NB_HUM_A)
    await add_faq(db, SHARED_HUM_Q, SHARED_HUM_A)
    result = await pipeline.answer_question(db, NS_QUESTION, session_id="s-shared")
    assert not result.is_fallback
    [context] = contexts(llm)
    assert SHARED_HUM_A in context and NB_HUM_A not in context


async def test_controllers_listed_on_the_models_own_page_apply_to_it(db, embedder, llm):
    await add_page(db, NS_PAGE_TITLE, NS_PAGE, "https://www.sawo.com/sawo30-round-ns/")
    await add_faq(db, INNOVA_E1_Q, INNOVA_E1_A)
    await add_faq(db, STE_E1_Q, STE_E1_A)
    result = await pipeline.answer_question(db, NS_E1_QUESTION, session_id="s-e1")
    assert not result.is_fallback
    [context] = contexts(llm)
    assert INNOVA_E1_A in context  # the SW3-45NS page lists Innova as its control
    assert STE_E1_A not in context  # a steam-generator board the page never mentions


async def test_the_prompt_carries_the_model_constraint(db, embedder, llm):
    await add_page(db, NS_PAGE_TITLE, NS_PAGE, "https://www.sawo.com/sawo30-round-ns/")
    await pipeline.answer_question(db, NS_KW_QUESTION, session_id="s-kw")
    system = llm.calls[-1][0]
    assert "specifically about: SW3-45NS" in system and "hard constraint" in system


async def test_a_follow_up_keeps_the_previous_questions_model(db, embedder, llm):
    await add_page(db, NS_PAGE_TITLE, NS_PAGE, "https://www.sawo.com/sawo30-round-ns/")
    await add_faq(db, NB_HUM_Q, NB_HUM_A)
    await pipeline.answer_question(db, NS_KW_QUESTION, session_id="s-follow")
    await pipeline.answer_question(db, FOLLOW_UP, session_id="s-follow")
    assert not any(NB_HUM_A in c for c in contexts(llm))
    assert "specifically about: SW3-45NS" in llm.calls[-1][0]


async def test_saved_answer_matching_still_rejects_an_incompatible_model(db, embedder, llm):
    await add_faq(db, NB_HUM_Q, NB_HUM_A)
    question = NS_SAVED_STYLE
    decision = await find_paraphrase_answer(db, question, vector_for(question))
    assert not decision.hit and any("differ" in r for r in decision.rejected)
    result = await pipeline.answer_question(db, question, session_id="s-saved")
    assert result.engine_used != "faq_direct" and NB_HUM_A not in result.answer


# --- audit regressions ---------------------------------------------------------------

NAV = (
    "Heater Accessories Infrared Sauana Controls Innova Series Interface Holders Latest News "
    "Nordex Mini Nordex Mini Ni2 Sauna Accessories Sauna Controls Sauna Rooms Saunova Series"
)
STONES_PAGE_TITLE = "https://www.sawo.com/frequently-asked-questions/ (part 4/4)"
STONES_PAGE = f"{NAV}\nNever use the heater without stones. Use only SAWO-recommended stones."
NB_STONES_QUESTION = "How often should I change the stones in my NB heater?"
HES_FAQ_Q = "HES-45NS heater: the glass front fogs up, what should we do?"
HES_FAQ_A = "Wipe the HES-45NS glass front and check the room ventilation."
SCAC_QUESTION = "SCAC-60NS heater: the glass front fogs up, what should we do?"
NI2_FAQ_Q = "Ni2 heater: display dims after an hour, what should we do?"
NI2_FAQ_A = "On Ni2 heaters the display dims by design after 60 minutes."
NS_DIM_QUESTION = "NS heater: display dims after an hour, what should we do?"
FOLLOW_UP_2 = "and how do I fix it?"

ANGLES.update({
    STONES_PAGE_TITLE: 18.0,
    NB_STONES_QUESTION: 18.0 + _angle(0.8),
    HES_FAQ_Q: 20.0,
    SCAC_QUESTION: 20.0 + _angle(0.97),
    NI2_FAQ_Q: 22.0,
    NS_DIM_QUESTION: 22.0 + _angle(0.97),
    f"{FOLLOW_UP} {FOLLOW_UP_2}": 10.0 + _angle(0.86),
})


async def test_navigation_menus_on_crawled_pages_do_not_scope_them(db, embedder, llm):
    # Every crawled page repeats the site menu ("Innova Series ... Saunova Series");
    # that must not make a general FAQ page "Innova documentation" hidden from NB questions.
    page = await add_page(db, STONES_PAGE_TITLE, STONES_PAGE, "https://www.sawo.com/frequently-asked-questions/")
    page.source_type = "library"
    await db.commit()
    result = await pipeline.answer_question(db, NB_STONES_QUESTION, session_id="s-nav")
    assert not result.is_fallback
    assert any("SAWO-recommended stones" in c for c in contexts(llm))


async def test_navigation_menus_do_not_link_controllers_to_a_model(db, embedder):
    page = await add_page(db, "https://www.sawo.com/sawo30-round-nb/ (part 1/2)", f"{NAV}\nSW3-45NB-P-C | 4.5", "https://www.sawo.com/sawo30-round-nb/")
    page.source_type = "library"
    await db.commit()
    assert await linked_controllers(db, scope_of("SW3-45NB")) == frozenset()


async def test_saved_answers_cannot_serve_another_models_faq(db, embedder, llm):
    # technical_key doesn't read letters-only codes or the NS/Ni2 variants, so
    # applicability has to veto these shortcuts itself.
    await add_faq(db, HES_FAQ_Q, HES_FAQ_A)
    await add_faq(db, NI2_FAQ_Q, NI2_FAQ_A)
    for question in (SCAC_QUESTION, NS_DIM_QUESTION):
        result = await pipeline.answer_question(db, question, session_id=f"s-veto-{question[:4]}")
        assert result.engine_used != "faq_direct"
        assert HES_FAQ_A not in result.answer and NI2_FAQ_A not in result.answer


async def test_model_context_survives_several_follow_ups(db, embedder, llm):
    await add_page(db, NS_PAGE_TITLE, NS_PAGE, "https://www.sawo.com/sawo30-round-ns/")
    await add_faq(db, NB_HUM_Q, NB_HUM_A)
    await pipeline.answer_question(db, NS_KW_QUESTION, session_id="s-chain")
    await pipeline.answer_question(db, FOLLOW_UP, session_id="s-chain")
    await pipeline.answer_question(db, FOLLOW_UP_2, session_id="s-chain")
    assert not any(NB_HUM_A in c for c in contexts(llm))
    assert "specifically about: SW3-45NS" in llm.calls[-1][0]


async def test_a_new_unrelated_question_does_not_inherit_an_old_model(db, embedder, llm):
    await add_page(db, NS_PAGE_TITLE, NS_PAGE, "https://www.sawo.com/sawo30-round-ns/")
    await pipeline.answer_question(db, NS_KW_QUESTION, session_id="s-reset")
    await pipeline.answer_question(db, "What sauna stones does SAWO recommend in general?", session_id="s-reset")
    await pipeline.answer_question(db, FOLLOW_UP_2, session_id="s-reset")
    assert all("specifically about" not in system for system, _c, _q in llm.calls[1:])
