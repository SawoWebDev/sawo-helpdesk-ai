"""Tests for the chat productivity features: feedback reason, report
submission, and popular-questions aggregation. Most of these exercise the
CRUD/model layer directly (same style as the rest of this suite); the
/api/chat/report and /api/logs/reports endpoints are gated by session
matching and by JWT role respectively, both enforced in the router/dependency
layer, so those are exercised through the real HTTP layer instead (same
reasoning as test_conversations.py's client fixture)."""

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_agent_or_admin
from app.crud.analytics import get_popular_questions
from app.db.session import get_db
from app.main import app
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


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Unauthenticated client — only `get_db` is overridden, so the real
    require_agent_or_admin/get_current_user chain still runs. Used to prove
    the /api/logs/reports endpoints actually reject an unauthenticated
    caller, rather than only exercising the happy path."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def staff_client(db: AsyncSession) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Same as `client`, but also bypasses the JWT check — the agent/admin
    role gate itself is covered separately by `client` (no override), so
    this fixture only needs to get past it, not exercise it."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    # resolve/reopen read `user.username` for the audit fields — a bare
    # object() would AttributeError there, so stub just enough of User.
    app.dependency_overrides[require_agent_or_admin] = lambda: SimpleNamespace(id=1, username="staff-tester")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(require_agent_or_admin, None)


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


async def post_report(client: httpx.AsyncClient, chat_log_id: int, session_id: str, **overrides):
    payload = {
        "chat_log_id": chat_log_id,
        "session_id": session_id,
        "question_text": "What is E1?",
        "answer_text": "E1 means overheat.",
        "reason": "wrong_product_or_model",
        **overrides,
    }
    return await client.post("/api/chat/report", json=payload)


@pytest.mark.asyncio
async def test_report_endpoint_rejects_session_mismatch(client, db):
    # No auth on /api/chat/report (the chat widget itself has none) — the
    # session_id pairing is the only thing stopping one visitor from
    # reporting on another's chat_log_id, so a mismatch must 404 rather
    # than silently attach to the wrong session.
    log = make_log(session_id="real-session")
    db.add(log)
    await db.commit()

    res = await post_report(client, log.id, "someone-elses-session")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_report_endpoint_creates_report_via_http(client, staff_client, db):
    log = make_log(session_id="sess-http-report")
    db.add(log)
    await db.commit()

    res = await post_report(client, log.id, "sess-http-report", comment="Totally wrong heater.")
    assert res.status_code == 204

    listing = await staff_client.get("/api/logs/reports")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["items"][0]["comment"] == "Totally wrong heater."
    assert body["items"][0]["status"] == "open"


@pytest.mark.asyncio
async def test_reports_endpoints_require_agent_or_admin(client):
    # `client` has no auth override — a caller with no token at all must be
    # rejected before ever reaching the ChatReport query.
    assert (await client.get("/api/logs/reports")).status_code == 401
    assert (await client.post("/api/logs/reports/1/resolve")).status_code == 401
    assert (await client.post("/api/logs/reports/1/reopen")).status_code == 401
    assert (await client.delete("/api/logs/reports/1")).status_code == 401


async def make_report(db, *, session_id="sess-1", status="open") -> ChatReport:
    log = make_log(session_id=session_id)
    db.add(log)
    await db.commit()
    report = ChatReport(
        chat_log_id=log.id,
        session_id=session_id,
        question_text=log.question_text,
        answer_text=log.answer_text,
        reason="outdated_information",
        status=status,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


@pytest.mark.asyncio
async def test_list_reports_filters_by_status(staff_client, db):
    open_report = await make_report(db, session_id="sess-open", status="open")
    resolved_report = await make_report(db, session_id="sess-resolved", status="resolved")

    only_open = await staff_client.get("/api/logs/reports?status=open")
    assert [item["id"] for item in only_open.json()["items"]] == [open_report.id]

    only_resolved = await staff_client.get("/api/logs/reports?status=resolved")
    assert [item["id"] for item in only_resolved.json()["items"]] == [resolved_report.id]

    everything = await staff_client.get("/api/logs/reports")
    assert everything.json()["total"] == 2


@pytest.mark.asyncio
async def test_resolve_then_reopen_report(staff_client, db):
    report = await make_report(db, status="open")

    resolved = await staff_client.post(f"/api/logs/reports/{report.id}/resolve")
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["status"] == "resolved"
    # Audit trail: who resolved it and when, from the staff_client's
    # stubbed user (see the fixture) rather than a users.id FK — so this
    # still reads correctly even if that account is deleted later.
    assert body["resolved_by"] == "staff-tester"
    assert body["resolved_at"] is not None

    reopened = await staff_client.post(f"/api/logs/reports/{report.id}/reopen")
    assert reopened.status_code == 200
    reopened_body = reopened.json()
    assert reopened_body["status"] == "open"
    # Reopening means nobody currently has it resolved — stale audit data
    # from the previous resolution must not linger.
    assert reopened_body["resolved_by"] is None
    assert reopened_body["resolved_at"] is None


@pytest.mark.asyncio
async def test_resolve_and_reopen_404_for_missing_report(staff_client):
    assert (await staff_client.post("/api/logs/reports/999999/resolve")).status_code == 404
    assert (await staff_client.post("/api/logs/reports/999999/reopen")).status_code == 404


@pytest.mark.asyncio
async def test_delete_report_removes_it_and_404s_after(staff_client, db):
    report = await make_report(db)

    deleted = await staff_client.delete(f"/api/logs/reports/{report.id}")
    assert deleted.status_code == 204

    listing = await staff_client.get("/api/logs/reports")
    assert listing.json()["total"] == 0

    # Deleting again (or resolving the now-gone row) must 404, not 500.
    assert (await staff_client.delete(f"/api/logs/reports/{report.id}")).status_code == 404
    assert (await staff_client.post(f"/api/logs/reports/{report.id}/resolve")).status_code == 404
