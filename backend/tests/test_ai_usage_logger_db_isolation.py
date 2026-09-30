"""Regression tests for the AI usage logger's database isolation.

record_usage() used to always open the app's default AsyncSessionLocal
(bound to whatever DATABASE_URL/./helpdesk.db resolves to), ignoring which
database the caller (the RAG pipeline, reindexing, etc.) was actually using.
That meant tests or scratch/live verification against a temporary database
could silently write usage telemetry into the real database.

The fix threads the caller's AsyncSession into OpenRouterEngine and from
there into record_usage(), which now opens its own short-lived session bound
to that SAME underlying engine rather than the global default one.
"""

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.db.base as db_base
from app.db.base import Base, _setup_connection
from app.models.ai_usage_log import AIUsageLog
from app.services import ai_usage

USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.001}


async def _make_temp_session(tmp_path, name: str) -> AsyncSession:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    event.listen(engine.sync_engine, "connect", lambda conn, _rec: conn.run_async(_setup_connection))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)()


@pytest_asyncio.fixture
async def temp_session(tmp_path):
    session = await _make_temp_session(tmp_path, "isolation_a.db")
    yield session
    await session.close()


@pytest.fixture
def guard_default_engine(monkeypatch):
    """Fails the test immediately if anything tries to open a session via the
    app's default/global sessionmaker (bound to ./helpdesk.db) — proving the
    isolated operation below never touches it."""

    def _forbidden_session(*args, **kwargs):
        raise AssertionError("record_usage opened a session on the default ./helpdesk.db sessionmaker")

    monkeypatch.setattr(db_base, "AsyncSessionLocal", _forbidden_session)


async def test_usage_written_to_temporary_database(temp_session, guard_default_engine):
    """Test A: a temp-database operation's usage row lands in that temp
    database, and the real/default database is never opened."""
    await ai_usage.record_usage("test-model", "chat", USAGE, temp_session, provider="test-provider")

    result = await temp_session.execute(select(AIUsageLog))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].model == "test-model"


async def test_explicit_session_determines_target_database(tmp_path):
    """Test B: two calls with two different explicit sessions land in their
    own respective databases, proving the explicit db/session always wins
    rather than any shared/default target."""
    session_a = await _make_temp_session(tmp_path, "isolation_b_a.db")
    session_b = await _make_temp_session(tmp_path, "isolation_b_b.db")
    try:
        await ai_usage.record_usage("model-a", "chat", USAGE, session_a)
        await ai_usage.record_usage("model-b", "chat", USAGE, session_b)

        rows_a = (await session_a.execute(select(AIUsageLog))).scalars().all()
        rows_b = (await session_b.execute(select(AIUsageLog))).scalars().all()

        assert [r.model for r in rows_a] == ["model-a"]
        assert [r.model for r in rows_b] == ["model-b"]
    finally:
        await session_a.close()
        await session_b.close()


async def test_usage_fields_recorded_as_before(temp_session):
    """Test C: existing logging semantics (fields, session_id, feature,
    cost split, provider/finish_reason/latency) are unchanged."""
    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 40,
        "total_tokens": 140,
        "cost": 0.0025,
        "cost_details": {
            "upstream_inference_prompt_cost": 0.0015,
            "upstream_inference_completions_cost": 0.0010,
        },
    }
    with ai_usage.session_context("chat-session-123"), ai_usage.feature_context(
        ai_usage.FEATURE_CHAT_ANSWER_GENERATION
    ):
        await ai_usage.record_usage(
            "mistralai/mistral-nemo",
            "chat",
            usage,
            temp_session,
            provider="SomeProvider",
            finish_reason="stop",
            latency_ms=456,
        )

    row = (await temp_session.execute(select(AIUsageLog))).scalars().one()
    assert row.model == "mistralai/mistral-nemo"
    assert row.is_free is False
    assert row.request_type == "chat"
    assert row.prompt_tokens == 100
    assert row.completion_tokens == 40
    assert row.total_tokens == 140
    assert row.cost_usd == 0.0025
    assert row.input_cost_usd == 0.0015
    assert row.output_cost_usd == 0.0010
    assert row.session_id == "chat-session-123"
    assert row.feature == ai_usage.FEATURE_CHAT_ANSWER_GENERATION
    assert row.provider == "SomeProvider"
    assert row.finish_reason == "stop"
    assert row.latency_ms == 456


async def test_no_usage_recorded_when_usage_missing(temp_session, guard_default_engine):
    """record_usage is a no-op (and never touches any database) when the
    caller has no usage payload to log."""
    await ai_usage.record_usage("test-model", "chat", None, temp_session)
    rows = (await temp_session.execute(select(AIUsageLog))).scalars().all()
    assert rows == []
