"""Saved-answer reuse, exercised through the real pipeline against a throwaway
SQLite+sqlite-vec database. Embeddings are hand-built: every text is a point
on a circle, so the cosine between two questions is exactly the number the
scenario needs (the values below are the ones measured on the real knowledge
base — see technical_key.py)."""

import pytest
from sqlalchemy import select, text

from app.crud.faq import find_duplicate_faq
from app.models.chat_log import ChatLog
from app.models.harvest_source import HarvestSource
from app.models.unanswered import UnansweredQuestion
from app.models.vault_entry import VaultEntry
from app.rag import pipeline
from app.rag.saved_answers import ENGINE_FAQ_DIRECT, find_exact_answer, find_paraphrase_answer
from tests.conftest import ANGLES, add_faq, vec, vector_for
from tests.conftest import angle as _angle


E1 = "my sauna screen says E1 and it wont heat up"
E1_REWORDED = "what happens my sauna screen says E1 and it wont heat up what could be the reason of this"
E4 = "my sauna screen says E4 and it wont heat up"
E13 = "my sauna screen says E13 and it wont heat up"
OPEN = "sauna display says oPEn and heater won't start"
E1_TERSE = "E1 sauna heating problem"
E1_ANSWER = "E1 means Temperature Sensor 1 (TS1) is not connected. Check the TS1 wiring."
E1_PLUS_WARRANTY = "my sauna screen says E1 and it wont heat up, also what is the warranty on the heater"
E1_TS2 = "my sauna screen says E1 and it wont heat up, what should TS2 read"
INNOVA_E1 = "Innova controller shows E1 and it wont heat up"
OPEN_LOWER = "sauna display says open and heater won't start"

SAUNOVA_E7 = "Saunova E7 communication error, how to troubleshoot?"
SAUNOVA_E7_REWORDED = "how do I troubleshoot the communication error E7 on Saunova"
INNOVA_E7 = "Innova E7 communication error, how to troubleshoot?"

WHAT_IS_SAWO = "What is SAWO?"
SAWO_CLOSE = "tell me what SAWO is"
SAWO_LOOSE = "tell me about sawo"

# text -> angle on the circle. E1 sits at 0, so sim(E1, x) == cos(angle(x)).
ANGLES.update({
    E1: 0.0,
    E1_REWORDED: _angle(0.938),
    E4: -_angle(0.916),
    E13: -_angle(0.881),
    OPEN: _angle(0.707),
    E1_TERSE: _angle(0.85),
    E1_PLUS_WARRANTY: _angle(0.95),  # very similar, but asks for more than the saved answer covers
    E1_TS2: _angle(0.95),
    INNOVA_E1: _angle(0.95),
    SAUNOVA_E7: 1.0,
    SAUNOVA_E7_REWORDED: 1.0 + _angle(0.93),
    INNOVA_E7: 1.0 - _angle(0.95),  # extremely close in meaning, different controller
    WHAT_IS_SAWO: 2.0,
    SAWO_CLOSE: 2.0 + _angle(0.95),
    SAWO_LOOSE: 2.0 + _angle(0.91),
})


async def direct(db, question, has_history=False):
    """Both stages, in the same order the pipeline runs them."""
    exact = await find_exact_answer(db, question, has_history=has_history)
    if exact.hit:
        return exact
    return await find_paraphrase_answer(db, question, vector_for(question), has_history=has_history)


# --- matching -------------------------------------------------------------


async def test_exact_repeat_reuses_the_saved_answer(db, embedder):
    faq = await add_faq(db, E1, E1_ANSWER)
    d = await direct(db, "  " + E1.upper() + "  ")  # case/whitespace-insensitive
    assert d.hit and d.stage == "exact" and d.faq.id == faq.id and d.similarity == 1.0
    assert embedder.calls == []  # an exact repeat needs no embedding comparison at all


async def test_close_rewording_reuses_the_same_saved_answer(db, embedder):
    faq = await add_faq(db, E1, E1_ANSWER)
    d = await direct(db, E1_REWORDED)  # 0.938, same identifiers
    assert d.hit and d.faq.id == faq.id and d.stage == "paraphrase"
    assert d.similarity == pytest.approx(0.938, abs=1e-6)


async def test_e4_never_gets_the_e1_answer_even_at_0_916_similarity(db, embedder):
    await add_faq(db, E1, E1_ANSWER)
    d = await direct(db, E4)  # 0.916 >= both thresholds; only the identifier check stops it
    assert not d.hit
    assert any("codes differ (E4 vs E1)" in r for r in d.rejected)
    assert embedder.calls == []  # blocked before any candidate embedding is spent


async def test_e13_and_open_never_get_the_e1_answer(db, embedder):
    await add_faq(db, E1, E1_ANSWER)
    assert not (await direct(db, E13)).hit  # 0.881: "E1" must not match inside "E13"
    assert not (await direct(db, OPEN)).hit


async def test_same_error_on_a_different_controller_is_not_reused(db, embedder):
    await add_faq(db, SAUNOVA_E7, "Saunova E7: check the RJ cable.")
    d = await direct(db, INNOVA_E7)  # 0.95 similar, but Innova != Saunova
    assert not d.hit
    assert any("products differ" in r for r in d.rejected)


async def test_same_controller_rewording_is_reused(db, embedder):
    faq = await add_faq(db, SAUNOVA_E7, "Saunova E7: check the RJ cable.")
    d = await direct(db, SAUNOVA_E7_REWORDED)
    assert d.hit and d.faq.id == faq.id


async def test_low_similarity_with_matching_identifiers_goes_to_the_normal_pipeline(db, embedder):
    await add_faq(db, E1, E1_ANSWER)
    d = await direct(db, E1_TERSE)  # 0.85 < 0.90
    assert not d.hit
    assert any("< 0.9" in r for r in d.rejected)


async def test_free_text_needs_the_stricter_threshold(db, embedder):
    faq = await add_faq(db, WHAT_IS_SAWO, "SAWO is a sauna company.")
    assert not (await direct(db, SAWO_LOOSE)).hit  # 0.91: fine for a coded question, not for free text
    assert (await direct(db, SAWO_CLOSE)).faq.id == faq.id  # 0.95


async def test_history_dependent_question_without_identifiers_is_not_shortcut(db, embedder):
    await add_faq(db, WHAT_IS_SAWO, "SAWO is a sauna company.")
    assert not (await direct(db, SAWO_CLOSE, has_history=True)).hit


# --- trust rules ----------------------------------------------------------


async def test_drafts_are_never_served(db, embedder):
    await add_faq(db, E1, E1_ANSWER, status="draft")
    assert not (await direct(db, E1)).hit  # exact text, but not published


async def test_thumbs_down_on_a_direct_answer_stops_reuse_until_the_faq_is_edited(db, embedder):
    faq = await add_faq(db, E1, E1_ANSWER)
    db.add(ChatLog(
        question_text=E1, answer_text=E1_ANSWER, matched_faq_ids=[faq.id],
        engine_used=ENGINE_FAQ_DIRECT, rating="down",
    ))
    await db.commit()
    d = await direct(db, E1)
    assert not d.hit and any("thumbs-down" in r for r in d.rejected)

    # A staff edit puts the FAQ back in play: the rating was about the old text.
    await db.execute(
        text("UPDATE faq_entries SET answer = 'Fixed answer', updated_at = datetime('now', '+1 minute') WHERE id = :i"),
        {"i": faq.id},
    )
    await db.commit()
    db.expire_all()  # raw SQL bypassed the session cache; the app uses a fresh session per request
    d = await direct(db, E1)
    assert d.hit and d.faq.answer == "Fixed answer"


async def test_thumbs_down_on_a_generated_answer_does_not_ban_the_faq(db, embedder):
    faq = await add_faq(db, E1, E1_ANSWER)
    db.add(ChatLog(
        question_text=E1, answer_text="whatever", matched_faq_ids=[faq.id], engine_used="stub", rating="down",
    ))
    await db.commit()
    assert (await direct(db, E1)).hit


async def test_faq_whose_library_source_changed_afterwards_is_not_reused(db, embedder):
    source = HarvestSource(source_type="url")
    db.add(source)
    await db.commit()
    # Real order: the Library page exists first, the FAQ is derived from it later.
    vault = VaultEntry(title="page", content="old content", source_id=source.id)
    db.add(vault)
    await db.commit()
    await db.execute(
        text("UPDATE vault_entries SET updated_at = datetime('now', '-1 hour') WHERE id = :i"), {"i": vault.id}
    )
    await db.commit()
    await add_faq(db, E1, E1_ANSWER, source_id=source.id)
    assert (await direct(db, E1)).hit  # source not newer than the FAQ

    await db.execute(
        text("UPDATE vault_entries SET updated_at = datetime('now', '+1 minute') WHERE id = :i"), {"i": vault.id}
    )
    await db.commit()
    d = await direct(db, E1)
    assert not d.hit and any("source changed" in r for r in d.rejected)


async def test_editing_or_deleting_an_faq_takes_effect_immediately(db, embedder):
    faq = await add_faq(db, E1, E1_ANSWER)
    assert (await direct(db, E1)).faq.answer == E1_ANSWER
    faq.answer = "Updated wording"
    await db.commit()
    assert (await direct(db, E1)).faq.answer == "Updated wording"  # nothing cached to go stale
    await db.delete(faq)
    await db.commit()
    assert not (await direct(db, E1)).hit


# --- duplicate prevention (no "E1 question #2, #3, #4") -----------------------


async def test_rewordings_of_a_saved_question_resolve_to_the_one_existing_faq(db, embedder):
    faq = await add_faq(db, E1, E1_ANSWER)
    dup = await find_duplicate_faq(db, E1_REWORDED, vec(ANGLES[E1_REWORDED]))
    assert dup is not None and dup.id == faq.id


async def test_a_different_error_is_not_a_duplicate_of_an_existing_faq(db, embedder):
    await add_faq(db, E1, E1_ANSWER)
    # Previously refused as a "duplicate" (0.916 and 0.881 are both >= 0.88).
    assert await find_duplicate_faq(db, E4, vec(ANGLES[E4])) is None
    assert await find_duplicate_faq(db, E13, vec(ANGLES[E13])) is None


# --- through the real pipeline -------------------------------------------------


async def test_pipeline_answers_a_repeat_without_any_ai_generation(db, embedder, llm):
    faq = await add_faq(db, E1, E1_ANSWER)
    # exact repeat: zero AI calls of any kind; rewording: only the query embedding
    # (candidate question vectors are stored, not re-embedded), still no LLM
    for question, expected_embed_calls in ((E1, 0), (E1_REWORDED, 1)):
        embedder.calls.clear()
        result = await pipeline.answer_question(db, question, session_id="s-" + str(expected_embed_calls))
        assert result.answer == E1_ANSWER  # as stored, not rewritten
        assert not result.is_fallback and result.engine_used == ENGINE_FAQ_DIRECT
        assert result.matched_faq_ids == [faq.id] and result.chat_log_id is not None
        assert len(embedder.calls) == expected_embed_calls
    assert llm.generate_calls == 0  # no generation, no relevance check, no grounding check

    log = (await db.execute(select(ChatLog).where(ChatLog.engine_used == ENGINE_FAQ_DIRECT))).scalars().first()
    assert log.matched_faq_ids == [faq.id]  # ratable, visible in the Logs page


async def test_pipeline_still_generates_for_a_different_error_code(db, embedder, llm):
    await add_faq(db, E1, E1_ANSWER)
    result = await pipeline.answer_question(db, E4, session_id="s-e4")
    assert result.answer == "Generated answer" and result.answer != E1_ANSWER
    assert result.engine_used == "stub" and llm.generate_calls == 2  # the untouched RAG flow: answer + fact-check
    assert len(embedder.calls) == 1  # no extra embedding spent on the blocked candidate


async def test_pipeline_fallback_path_is_unchanged_when_nothing_matches(db, embedder, llm):
    llm.reply = "NOT_FOUND"
    result = await pipeline.answer_question(db, "something nobody has documented", session_id="s-none")
    assert result.is_fallback and result.engine_used != ENGINE_FAQ_DIRECT
    pending = (await db.execute(select(UnansweredQuestion))).scalars().all()
    assert len(pending) == 1  # still logged for staff exactly as before


# --- exact stage: normalization + index, zero AI -------------------------------


@pytest.mark.parametrize(
    "variant",
    [
        "My sauna screen says E1 and it won't heat up??",
        "my  sauna screen   says e1 and it wont heat up.",
        "“my sauna screen says E1 and it wont heat up”",
    ],
)
async def test_harmless_wording_differences_are_an_exact_hit_with_zero_ai_calls(db, embedder, llm, variant):
    faq = await add_faq(db, E1, E1_ANSWER)
    result = await pipeline.answer_question(db, variant, session_id="s-norm")
    assert result.engine_used == ENGINE_FAQ_DIRECT and result.matched_faq_ids == [faq.id]
    assert embedder.calls == [] and llm.generate_calls == 0


async def test_exact_lookup_uses_the_index(db):
    plan = (await db.execute(text(
        "EXPLAIN QUERY PLAN SELECT id FROM faq_entries WHERE question_normalized = 'x' AND status = 'published'"
    ))).all()
    assert any("ix_faq_entries_question_normalized" in str(row) for row in plan)


async def test_normalized_key_follows_every_edit(db, embedder):
    faq = await add_faq(db, E1, E1_ANSWER)
    assert faq.question_normalized == "my sauna screen says e1 and it wont heat up"
    faq.question = "What does E13 mean?"
    await db.commit()
    assert faq.question_normalized == "what does e13 mean"
    assert not (await find_exact_answer(db, E1)).hit


async def test_case_only_difference_that_changes_a_code_is_not_an_exact_hit(db, embedder):
    await add_faq(db, OPEN, "oPEn means the door sensor is open.")
    d = await find_exact_answer(db, OPEN_LOWER)  # same text once lowercased, but "open" is not the oPEn code
    assert not d.hit and any("codes differ" in r for r in d.rejected)


# --- conservative policies -------------------------------------------------------


async def test_missing_controller_is_not_filled_in_from_the_candidate(db, embedder):
    await add_faq(db, INNOVA_E1, "Innova E1: check TS1.")
    d = await direct(db, E1)  # 0.95 similar, but the asker never said Innova
    assert not d.hit and any("products differ" in r for r in d.rejected)


async def test_extra_request_is_not_answered_with_the_partial_saved_answer(db, embedder, llm):
    await add_faq(db, E1, E1_ANSWER)
    d = await direct(db, E1_PLUS_WARRANTY)  # 0.95 similar
    assert not d.hit and any("further request" in r for r in d.rejected)
    result = await pipeline.answer_question(db, E1_PLUS_WARRANTY, session_id="s-more")
    assert result.engine_used != ENGINE_FAQ_DIRECT and llm.generate_calls == 2  # answer + fact-check


async def test_component_the_saved_answer_does_not_cover_is_not_shortcut(db, embedder):
    await add_faq(db, E1, E1_ANSWER)  # answer covers TS1 only
    d = await direct(db, E1_TS2)
    assert not d.hit and any("TS2, not covered" in r for r in d.rejected)


async def test_unpublishing_an_faq_stops_reuse(db, embedder):
    faq = await add_faq(db, E1, E1_ANSWER)
    faq.status = "draft"
    await db.commit()
    assert not (await direct(db, E1)).hit


async def test_repeats_never_create_faqs_or_promotions(db, embedder, llm):
    await add_faq(db, E1, E1_ANSWER)
    for i in range(3):
        result = await pipeline.answer_question(db, E1, session_id=f"s-rep-{i}")
        assert result.promotion is None  # nothing queued for auto-save
    count = (await db.execute(text("SELECT count(*) FROM faq_entries"))).scalar_one()
    assert count == 1


async def test_duplicate_check_uses_the_same_normalization(db, embedder):
    faq = await add_faq(db, E1, E1_ANSWER)
    dup = await find_duplicate_faq(db, "My sauna screen says E1 and it won't heat up??")
    assert dup is not None and dup.id == faq.id


async def test_an_faq_whose_answer_is_the_fallback_message_is_never_served(db, embedder, llm):
    from app.crud.settings import get_all_settings
    from app.core import setting_keys as keys

    fallback = (await get_all_settings(db))[keys.FALLBACK_MESSAGE]
    await add_faq(db, E1, fallback)  # e.g. created by hand or a script, bypassing "Save as FAQ"'s guard
    d = await find_exact_answer(db, E1)
    assert not d.hit and any("fallback/off-topic message" in r for r in d.rejected)
    result = await pipeline.answer_question(db, E1, session_id="s-fb")
    assert result.engine_used != ENGINE_FAQ_DIRECT
