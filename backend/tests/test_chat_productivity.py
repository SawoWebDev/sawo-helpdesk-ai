"""Tests for the chat productivity features: feedback reason, report
submission, and popular-questions aggregation. These exercise the CRUD/model
layer directly (same style as the rest of this suite), since the app's
existing tests don't use an HTTP test client."""

from datetime import datetime, timedelta, timezone

import pytest

from app.crud.analytics import get_popular_questions
from app.models.chat_log import ChatLog
from app.models.chat_report import ChatReport


def make_log(
    *,
    question="What is E1?",
    answer="E1 means overheat.",
    session_id="sess-1",
    matched_faq_ids=None,
    matched_vault_ids=None,
    created_at=None,
) -> ChatLog:
    return ChatLog(
        question_text=question,
        answer_text=answer,
        matched_faq_ids=matched_faq_ids or [],
        matched_vault_ids=matched_vault_ids or [],
        engine_used="stub",
        session_id=session_id,
        created_at=created_at or datetime.now(timezone.utc).replace(tzinfo=None),
    )


@pytest.mark.asyncio
async def test_feedback_reason_persists_only_for_down(db):
    log = make_log()
    db.add(log)
    await db.commit()

    log.rating = "down"
    log.feedback_reason = "incorrect_information"
    await db.commit()
    await db.refresh(log)
    assert log.feedback_reason == "incorrect_information"

    # Switching back to "up" clears the reason, mirroring the router's logic
    # (chat_log.feedback_reason = reason if rating == "down" else None).
    log.rating = "up"
    log.feedback_reason = None
    await db.commit()
    await db.refresh(log)
    assert log.feedback_reason is None


@pytest.mark.asyncio
async def test_report_snapshots_are_stored(db):
    log = make_log(session_id="sess-report")
    db.add(log)
    await db.commit()

    report = ChatReport(
        chat_log_id=log.id,
        session_id="sess-report",
        question_text=log.question_text,
        answer_text=log.answer_text,
        reference_urls=["https://example.com/doc"],
        reason="wrong_product_or_model",
        comment="This is about the wrong heater series.",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    assert report.status == "open"
    assert report.reference_urls == ["https://example.com/doc"]
    assert report.reason == "wrong_product_or_model"


@pytest.mark.asyncio
async def test_popular_questions_requires_repeat_demand_across_sessions(db):
    # Same question asked 3 times but all from one session: should NOT
    # qualify as "popular" (one person re-asking isn't demand).
    for _ in range(3):
        db.add(make_log(question="How do I reset my password?", session_id="only-session", matched_faq_ids=[1]))
    await db.commit()

    items, based_on_usage = await get_popular_questions(db, limit=4)
    assert based_on_usage is False


@pytest.mark.asyncio
async def test_popular_questions_uses_usage_when_threshold_met(db):
    for session_id in ("s1", "s2", "s3"):
        db.add(make_log(question="How do I reset my password?", session_id=session_id, matched_faq_ids=[1]))
    await db.commit()

    items, based_on_usage = await get_popular_questions(db, limit=1)
    assert based_on_usage is True
    assert items[0]["question"] == "How do I reset my password?"
    assert items[0]["source"] == "usage"


@pytest.mark.asyncio
async def test_popular_questions_excludes_unanswered_and_old_messages(db):
    # Unanswered (no matches) — must never count as "popular" even if repeated.
    for session_id in ("s1", "s2", "s3"):
        db.add(make_log(question="Unanswered thing", session_id=session_id, matched_faq_ids=[]))
    # Answered but outside the lookback window.
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=60)
    for session_id in ("s4", "s5", "s6"):
        db.add(make_log(question="Old popular thing", session_id=session_id, matched_faq_ids=[1], created_at=old))
    await db.commit()

    items, based_on_usage = await get_popular_questions(db, limit=4)
    assert based_on_usage is False
    questions = [item["question"] for item in items]
    assert "Unanswered thing" not in questions
    assert "Old popular thing" not in questions


@pytest.mark.asyncio
async def test_popular_questions_falls_back_to_published_faqs(db, embedder):
    from tests.conftest import add_faq

    await add_faq(db, "Where is the employee handbook?", "It's on the intranet.")

    items, based_on_usage = await get_popular_questions(db, limit=4)
    assert based_on_usage is False
    assert any(item["source"] == "faq" for item in items)
    assert all(item["source"] == "faq" for item in items)
