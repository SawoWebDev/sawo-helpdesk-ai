"""Reviewed alternate phrasings for canonical FAQs, plus the embedding/LLM call
budget of every saved-answer path. Fixtures (fake engines that count calls,
throwaway DB) are in conftest.py.

The NB-heater answer below is the real approved knowledge-base answer, copied
verbatim — no troubleshooting content is invented here."""

import pytest
from sqlalchemy import select, text

from app.crud.faq import delete_faq, find_duplicate_faq
from app.crud.faq_phrasing import PhrasingError, create_phrasing, delete_phrasing, update_phrasing
from app.db.vec_store import FAQ_PHRASING_VEC_TABLE, FAQ_QUESTION_VEC_TABLE, FAQ_VEC_TABLE, get_embeddings
from app.models.faq_phrasing import FAQPhrasing
from app.rag import pipeline
from app.rag.saved_answers import ENGINE_FAQ_DIRECT, find_exact_answer, find_paraphrase_answer
from tests.conftest import ANGLES, add_faq, angle, vector_for

CANON = (
    "NB heater: Humming sound in a heater. The loud humming appears to come from the NB timer/control area. "
    "What are the causes and how do we fix it?"
)
NB_ANSWER = (
    "- **Cause:** A worn or defective mechanical timer motor or internal timer mechanism  \n"
    "  **Troubleshooting:** Temporarily disconnect the heating elements from the timer/control circuit and then test the timer separately.  \n"
    "  **Solution:** Replace the timer if the humming continues when it is tested separately and the supply voltage is correct.\n\n"
    "- **Cause:** Loose timer mounting, terminals, or metal panels causing vibration  \n"
    "  **Troubleshooting:** Check and tighten the timer, thermostat, terminal connections, and heater mounting  \n"
    "  **Solution:** Secure the timer and panels. Tighten any loose terminals; replace damaged mounting parts or terminals.\n\n"
    "- **Cause:** Incorrect or unstable supply voltage  \n"
    "  **Troubleshooting:** Verify that the supply voltage and wiring match the heater’s rating and wiring diagram. measure actual voltage.  \n"
    "  **Solution:** Correct the supply or wiring to match the heater’s rating and wiring diagram. If the voltage fluctuates, have an electrician investigate the supply.\n\n"
    "- **Cause:** A loose electrical connection creating arcing or vibration  \n"
    "  **Troubleshooting:** Inspect the timer for overheating, discoloration, burning smell, or internal vibration.  \n"
    "  **Solution:** Turn off the power. Repair or replace the affected wire, terminal, or connector, and replace the timer if its contacts show heat or arc damage."
)

P1 = "My NB heater is making a loud humming noise."
P2 = "The timer area of my NB heater is humming loudly. What could cause this?"
P3 = "Why is my NB sauna heater making a humming sound near the controls?"
P4 = "My NB heater is humming loudly. How do I fix it?"
PHRASINGS = [P1, P2, P3, P4]

UNSEEN = "Why does my NB sauna heater hum near the controls"  # never added; close to P3
CLICKING = "My NB heater is making a loud clicking noise."
OTHER_MODEL = "My SW3-45NS heater is humming loudly. How do I fix it?"
WITH_CODE = "My NB heater shows E4 and is humming loudly. How do I fix it?"
WITH_EXTRA = "My NB heater is humming loudly. How do I fix it? Also, what is the warranty?"
UNRELATED = "How many sauna stones does a 9 kW heater need"

OTHER_CANON = "Innova Power Controller Error 1 (E1) - Temperature Sensor 1 (TS1) is not connected"
OTHER_ANSWER = "Test fixture answer for a second canonical FAQ."

# Placed so every phrasing is only 0.74-0.86 similar to the canonical question
# (the real measured range) — an exact phrasing hit therefore cannot be coming
# from similarity. The negatives sit 0.97 from the phrasing they imitate, so
# only the identifier/coverage rules can stop them.
BASE = 3.0
ANGLES.update({
    CANON: BASE,
    P1: BASE + angle(0.77),
    P2: BASE - angle(0.81),
    P3: BASE + angle(0.74) + 0.02,
    P4: BASE - angle(0.86),
    UNSEEN: BASE + angle(0.74) + 0.02 + angle(0.93),  # 0.93 from P3, ~0.42 from CANON
    CLICKING: BASE + angle(0.77) + angle(0.97),
    OTHER_MODEL: BASE - angle(0.86) + angle(0.97),
    WITH_CODE: BASE - angle(0.86) - angle(0.97),
    WITH_EXTRA: BASE - angle(0.86) + angle(0.985),
    OTHER_CANON: 0.5,
})


async def nb_faq_with_phrasings(db, phrasings=PHRASINGS):
    faq = await add_faq(db, CANON, NB_ANSWER)
    added = [await create_phrasing(db, faq, p, created_by_id=None) for p in phrasings]
    return faq, added


async def both_stages(db, question):
    exact = await find_exact_answer(db, question)
    if exact.hit:
        return exact
    return await find_paraphrase_answer(db, question, vector_for(question))


# --- NB humming: reviewed phrasings return the canonical answer --------------------


@pytest.mark.parametrize("phrasing", PHRASINGS)
async def test_each_reviewed_phrasing_returns_the_canonical_answer_with_zero_ai_calls(db, embedder, llm, phrasing):
    faq, _ = await nb_faq_with_phrasings(db)
    embedder.calls.clear()  # ignore the write-time embeddings of the phrasings themselves
    result = await pipeline.answer_question(db, phrasing, session_id="nb")
    assert result.engine_used == ENGINE_FAQ_DIRECT
    assert result.answer == NB_ANSWER  # the canonical answer, verbatim, read by faq id
    assert result.matched_faq_ids == [faq.id]
    assert embedder.calls == [] and llm.generate_calls == 0


async def test_harmless_variants_of_a_phrasing_are_still_exact(db, embedder, llm):
    await nb_faq_with_phrasings(db)
    embedder.calls.clear()
    result = await pipeline.answer_question(db, "my nb heater is making a LOUD humming noise!!", session_id="nb")
    assert result.engine_used == ENGINE_FAQ_DIRECT and embedder.calls == [] and llm.generate_calls == 0


async def test_phrasing_hit_is_recorded_as_a_phrasing_match(db, embedder):
    _, added = await nb_faq_with_phrasings(db)
    d = await find_exact_answer(db, P3)
    assert d.hit and d.stage == "exact" and d.phrasing_id == added[2].id


async def test_unseen_close_rewording_matches_a_phrasing_semantically_without_extra_embedding(db, embedder, llm):
    faq, added = await nb_faq_with_phrasings(db)
    d = await find_paraphrase_answer(db, UNSEEN, vector_for(UNSEEN))
    assert d.hit and d.faq.id == faq.id and d.phrasing_id == added[2].id  # via P3 (0.93), not CANON (0.42)
    embedder.calls.clear()
    result = await pipeline.answer_question(db, UNSEEN, session_id="nb-unseen")
    assert result.answer == NB_ANSWER
    assert len(embedder.calls) == 1 and llm.generate_calls == 0  # the query embedding only


async def test_without_phrasings_the_nb_rewordings_are_not_shortcut(db, embedder):
    # Same question placement, no reviewed phrasings: 0.74-0.86 is below the
    # threshold, so these go to the normal pipeline — phrasings are what
    # widen coverage, not a lower threshold.
    await add_faq(db, CANON, NB_ANSWER)
    for p in PHRASINGS:
        assert not (await both_stages(db, p)).hit


# --- NB humming: negative cases ---------------------------------------------------


async def test_clicking_is_not_answered_with_the_humming_answer(db, embedder, llm):
    await nb_faq_with_phrasings(db)
    d = await both_stages(db, CLICKING)  # 0.97 similar to P1
    assert not d.hit and any("symptoms differ (CLICK vs HUM)" in r for r in d.rejected)
    result = await pipeline.answer_question(db, CLICKING, session_id="nb-click")
    assert result.engine_used != ENGINE_FAQ_DIRECT and llm.generate_calls >= 1  # normal RAG/LLM path


async def test_a_different_heater_model_is_not_answered_with_the_nb_answer(db, embedder):
    await nb_faq_with_phrasings(db)
    d = await both_stages(db, OTHER_MODEL)
    assert not d.hit
    assert any("products differ" in r or "models differ" in r for r in d.rejected)


async def test_a_conflicting_error_code_blocks_reuse(db, embedder):
    await nb_faq_with_phrasings(db)
    d = await both_stages(db, WITH_CODE)
    assert not d.hit and any("codes differ (E4 vs none)" in r for r in d.rejected)


async def test_an_additional_unrelated_question_blocks_reuse(db, embedder, llm):
    await nb_faq_with_phrasings(db)
    d = await both_stages(db, WITH_EXTRA)  # 0.985 similar to P4
    assert not d.hit
    assert any("further request" in r or "several questions" in r for r in d.rejected)


async def test_unpublishing_the_canonical_faq_stops_its_phrasings(db, embedder):
    faq, _ = await nb_faq_with_phrasings(db)
    faq.status = "draft"
    await db.commit()
    assert not (await both_stages(db, P1)).hit


async def test_deleting_the_canonical_faq_removes_its_phrasings_and_vectors(db, embedder):
    faq, added = await nb_faq_with_phrasings(db)
    ids = [p.id for p in added]
    await delete_faq(db, faq)
    assert (await db.execute(select(FAQPhrasing))).scalars().all() == []  # ON DELETE CASCADE
    assert await get_embeddings(db, FAQ_PHRASING_VEC_TABLE, ids) == {}
    assert await get_embeddings(db, FAQ_QUESTION_VEC_TABLE, [faq.id]) == {}
    assert not (await both_stages(db, P1)).hit


async def test_editing_the_canonical_answer_is_served_through_every_phrasing(db, embedder):
    faq, _ = await nb_faq_with_phrasings(db)
    faq.answer = NB_ANSWER + "\n\n(edited by staff)"
    await db.commit()
    for p in PHRASINGS:
        assert (await find_exact_answer(db, p)).faq.answer.endswith("(edited by staff)")


async def test_a_phrasing_that_no_longer_fits_an_edited_canonical_question_is_not_served(db, embedder):
    faq, _ = await nb_faq_with_phrasings(db)
    faq.question = OTHER_CANON  # staff repurpose the FAQ: it is now about Innova E1
    await db.commit()
    d = await find_exact_answer(db, P1)
    assert not d.hit and any("no longer fits" in r for r in d.rejected)


async def test_a_disabled_phrasing_is_not_matched(db, embedder):
    faq, added = await nb_faq_with_phrasings(db)
    await update_phrasing(db, faq, added[0], phrasing=None, enabled=False)
    assert not (await find_exact_answer(db, P1)).hit
    assert await get_embeddings(db, FAQ_PHRASING_VEC_TABLE, [added[0].id]) == {}  # no semantic match either
    await update_phrasing(db, faq, added[0], phrasing=None, enabled=True)
    assert (await find_exact_answer(db, P1)).hit


async def test_a_removed_phrasing_is_not_matched(db, embedder):
    _, added = await nb_faq_with_phrasings(db)
    await delete_phrasing(db, added[0])
    assert not (await find_exact_answer(db, P1)).hit
    assert (await find_exact_answer(db, P2)).hit  # the others are unaffected


async def test_a_downvoted_canonical_faq_is_not_served_through_its_phrasings(db, embedder):
    from app.models.chat_log import ChatLog

    faq, _ = await nb_faq_with_phrasings(db)
    db.add(ChatLog(question_text=P1, answer_text=NB_ANSWER, matched_faq_ids=[faq.id], engine_used=ENGINE_FAQ_DIRECT, rating="down"))
    await db.commit()
    assert not (await find_exact_answer(db, P2)).hit


# --- validation: staff can't create unsafe or conflicting phrasings ----------------------


async def test_one_wording_can_belong_to_only_one_canonical_faq(db, embedder):
    nb, _ = await nb_faq_with_phrasings(db)
    other = await add_faq(db, OTHER_CANON, OTHER_ANSWER)
    with pytest.raises(PhrasingError) as err:
        await create_phrasing(db, other, P1.upper() + "?", created_by_id=None)  # same after normalization
    assert err.value.conflict and f"FAQ #{nb.id}" in str(err.value)


async def test_another_faqs_question_cannot_become_a_phrasing(db, embedder):
    nb = await add_faq(db, CANON, NB_ANSWER)
    other = await add_faq(db, OTHER_CANON, OTHER_ANSWER)
    with pytest.raises(PhrasingError) as err:
        await create_phrasing(db, nb, OTHER_CANON, created_by_id=None)
    assert err.value.conflict and f"#{other.id}" in str(err.value)


@pytest.mark.parametrize(
    "bad, reason",
    [
        (CANON, "FAQ's own question"),
        ("My NB heater is making a loud clicking noise.", "symptoms differ"),
        ("My Innova controller is humming loudly", "products differ"),
        ("My NB heater shows E4 and hums", "codes differ"),
        ("My NB heater is humming, also what is the warranty?", "asks for more"),
        ("   ", "empty"),
    ],
)
async def test_unsafe_phrasings_are_refused_with_the_reason(db, embedder, bad, reason):
    nb = await add_faq(db, CANON, NB_ANSWER)
    with pytest.raises(PhrasingError) as err:
        await create_phrasing(db, nb, bad, created_by_id=None)
    assert reason in str(err.value)
    assert (await db.execute(select(FAQPhrasing))).scalars().all() == []


async def test_a_phrasing_is_never_saved_as_a_new_canonical_faq(db, embedder):
    nb, _ = await nb_faq_with_phrasings(db)
    dup = await find_duplicate_faq(db, P2)  # e.g. staff "Save as FAQ", or auto-promotion
    assert dup is not None and dup.id == nb.id


async def test_phrasings_store_no_answer_text(db, embedder):
    columns = {r[1] for r in (await db.execute(text("PRAGMA table_info(faq_phrasings)"))).all()}
    assert "answer" not in columns


# --- embedding / LLM call budget per path (regression) -------------------------------------


async def test_call_budget_exact_canonical(db, embedder, llm):
    await add_faq(db, CANON, NB_ANSWER)
    await pipeline.answer_question(db, CANON, session_id="b1")
    assert (len(embedder.calls), llm.generate_calls) == (0, 0)


async def test_call_budget_exact_phrasing(db, embedder, llm):
    await nb_faq_with_phrasings(db)
    embedder.calls.clear()
    await pipeline.answer_question(db, P2, session_id="b2")
    assert (len(embedder.calls), llm.generate_calls) == (0, 0)


async def test_call_budget_semantic_paraphrase_hit(db, embedder, llm):
    await nb_faq_with_phrasings(db)
    embedder.calls.clear()
    result = await pipeline.answer_question(db, UNSEEN, session_id="b3")
    assert result.engine_used == ENGINE_FAQ_DIRECT
    assert (len(embedder.calls), llm.generate_calls) == (1, 0)  # was 2 embedding calls before stored question vectors


async def test_call_budget_identifier_mismatch(db, embedder, llm):
    await nb_faq_with_phrasings(db)
    embedder.calls.clear()
    result = await pipeline.answer_question(db, WITH_CODE, session_id="b4")
    assert result.engine_used != ENGINE_FAQ_DIRECT
    assert len(embedder.calls) == 1  # the query embedding only; the rejected candidates cost nothing


async def test_call_budget_unmatched_question(db, embedder, llm):
    await nb_faq_with_phrasings(db)
    embedder.calls.clear()
    result = await pipeline.answer_question(db, UNRELATED, session_id="b5")
    assert result.engine_used != ENGINE_FAQ_DIRECT
    assert len(embedder.calls) == 1 and llm.generate_calls >= 1  # the normal pipeline ran


async def test_call_budget_faq_not_yet_backfilled_falls_back_to_embedding_its_question(db, embedder, llm):
    # An FAQ saved before question-only vectors existed still matches safely,
    # at the old cost of one extra call, until the boot-time repair runs.
    await add_faq(db, CANON, NB_ANSWER, question_vector=False)
    ANGLES["NB heater humming sound near the timer control area, causes and fix"] = BASE + angle(0.95)
    q = "NB heater humming sound near the timer control area, causes and fix"
    result = await pipeline.answer_question(db, q, session_id="b6")
    assert result.engine_used == ENGINE_FAQ_DIRECT
    assert (len(embedder.calls), llm.generate_calls) == (2, 0)


async def test_write_time_embedding_stores_both_faq_vectors_in_one_call(db, embedder):
    from app.models.faq import FAQEntry
    from app.rag.reindex import embed_entry

    faq = FAQEntry(question=CANON, answer=NB_ANSWER)
    db.add(faq)
    await db.commit()
    await embed_entry(db, faq)
    await db.commit()
    assert len(embedder.calls) == 1 and len(embedder.calls[0]) == 2  # question+answer and question, one request
    assert faq.id in await get_embeddings(db, FAQ_VEC_TABLE, [faq.id])
    assert faq.id in await get_embeddings(db, FAQ_QUESTION_VEC_TABLE, [faq.id])


# --- boot-time repair (app/reindex_stale.py) ----------------------------------------------


async def test_boot_repair_backfills_question_vectors_and_phrasings(db, embedder):
    from app.rag.reindex import has_stale_faq_vectors, reindex_stale_faq

    legacy = await add_faq(db, CANON, NB_ANSWER, question_vector=False)  # embedded before this feature
    phrasing = FAQPhrasing(faq_id=legacy.id, phrasing=P1, enabled=True)  # e.g. embedding API was down
    db.add(phrasing)
    await db.commit()
    assert await has_stale_faq_vectors(db)

    await reindex_stale_faq(db)
    assert legacy.id in await get_embeddings(db, FAQ_QUESTION_VEC_TABLE, [legacy.id])
    assert phrasing.id in await get_embeddings(db, FAQ_PHRASING_VEC_TABLE, [phrasing.id])
    assert not await has_stale_faq_vectors(db)  # a second boot does nothing
