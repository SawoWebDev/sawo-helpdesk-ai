"""Streamed chat answers: the OpenRouter stream parser, the pipeline's
preview rules (what may be shown before the post-generation checks run),
and POST /api/chat/stream end to end over a real HTTP client."""

import asyncio
import json
from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai import openrouter_engine
from app.ai.base import AIEngineError
from app.ai.openrouter_engine import STREAM_DONE, OpenRouterEngine, parse_stream_line
from app.db.session import get_db, get_session_factory
from app.db.vec_store import VAULT_VEC_TABLE, upsert_embedding
from app.main import app
from app.models.conversation import Conversation
from app.models.vault_entry import VaultEntry
from app.rag import pipeline
from app.routers import chat as chat_router
from tests.conftest import ANGLES, add_faq, vector_for

LIBRARY_Q = "how many stones does the tower heater hold"
LIBRARY_TITLE = "Tower heater stone capacity"
ANGLES.update({LIBRARY_Q: 0.0, LIBRARY_TITLE: 0.0})


class StreamingStub:
    """Engine whose generate_stream yields fixed pieces; generate() returns
    them joined, so both paths agree on the final text."""

    name = "stub"

    def __init__(self, pieces: list[str]):
        self.pieces = pieces

    async def generate(self, *args, **kwargs) -> str:
        return "".join(self.pieces).strip()

    async def generate_stream(self, *args, **kwargs):
        for piece in self.pieces:
            yield piece


async def collect(pieces: list[str]) -> tuple[list[str], str]:
    shown: list[str] = []

    async def on_delta(text: str) -> None:
        shown.append(text)

    final = await pipeline._generate_answer(StreamingStub(pieces), "sys", "ctx", "q", None, on_delta)
    return shown, final


# --- pipeline preview rules ---------------------------------------------------------


@pytest.mark.asyncio
async def test_pieces_are_previewed_and_joined_into_the_final_answer():
    shown, final = await collect(["The tower ", "holds ", "20 kg."])
    assert "".join(shown) == "The tower holds 20 kg."
    assert final == "The tower holds 20 kg."


@pytest.mark.asyncio
async def test_refusal_sentinel_is_never_previewed():
    # The model's "I can't answer" reply must not flash on screen before the
    # fallback message replaces it, even when it arrives split in pieces.
    shown, final = await collect(["NOT_", "FOU", "ND"])
    assert shown == []
    assert final == pipeline.REFUSAL_SENTINEL


@pytest.mark.asyncio
async def test_opening_is_held_only_while_it_could_still_be_the_sentinel():
    shown, _final = await collect(["  N", "ice to ", "meet you"])
    assert shown == ["Nice to ", "meet you"]


@pytest.mark.asyncio
async def test_previewed_pieces_are_sanitized_like_the_final_answer():
    shown, _final = await collect(["Use the 9—", "11 kW model…"])
    assert "".join(shown) == "Use the 9-11 kW model..."


@pytest.mark.asyncio
async def test_no_callback_means_a_plain_generate_call():
    final = await pipeline._generate_answer(StreamingStub(["whole answer"]), "s", "c", "q", None, None)
    assert final == "whole answer"


# --- OpenRouter stream parsing ------------------------------------------------------


def test_parse_stream_line_skips_keepalives_and_detects_the_end():
    assert parse_stream_line(": OPENROUTER PROCESSING") is None
    assert parse_stream_line("") is None
    assert parse_stream_line("data: [DONE]") is STREAM_DONE
    assert parse_stream_line('data: {"choices": []}') == {"choices": []}


def _sse_body(*chunks: dict) -> str:
    lines = [": OPENROUTER PROCESSING", ""]
    for chunk in chunks:
        lines += [f"data: {json.dumps(chunk)}", ""]
    lines += ["data: [DONE]", ""]
    return "\n".join(lines)


def _patch_transport(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        openrouter_engine.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.asyncio
async def test_openrouter_generate_stream_yields_content_and_logs_usage(db, monkeypatch):
    usage = {"prompt_tokens": 10, "completion_tokens": 4, "cost": 0.0001}
    body = _sse_body(
        {"provider": "Prov", "choices": [{"delta": {"content": "Hello "}}]},
        {"choices": [{"delta": {"content": "there"}, "finish_reason": "stop"}]},
        {"choices": [], "usage": usage},
    )
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    _patch_transport(monkeypatch, handler)
    recorded: list[tuple] = []

    async def fake_record_usage(model, request_type, usage_arg, _db, **kwargs):
        recorded.append((request_type, usage_arg, kwargs))

    monkeypatch.setattr(openrouter_engine, "record_usage", fake_record_usage)

    engine = OpenRouterEngine(api_key="key", model="m", embedding_model="e", db=db)
    pieces = [piece async for piece in engine.generate_stream("sys", "ctx", "q", temperature=0)]

    assert pieces == ["Hello ", "there"]
    assert requests[0]["stream"] is True
    await asyncio.sleep(0)  # let the fire-and-forget usage task run
    [(request_type, logged_usage, extra)] = recorded
    assert request_type == "chat" and logged_usage == usage
    assert extra["provider"] == "Prov" and extra["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_openrouter_generate_stream_raises_engine_error_on_http_error(db, monkeypatch):
    _patch_transport(monkeypatch, lambda request: httpx.Response(500, text="boom"))
    engine = OpenRouterEngine(api_key="key", model="m", embedding_model="e", db=db)
    with pytest.raises(AIEngineError):
        [piece async for piece in engine.generate_stream("sys", "ctx", "q")]


# --- POST /api/chat/stream ----------------------------------------------------------


@pytest_asyncio.fixture
async def client(db: AsyncSession, embedder, llm, monkeypatch) -> AsyncGenerator[httpx.AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    # Promotion writes through the app's real session factory, not the test DB.
    promoted: list[dict] = []

    async def fake_promote(**kwargs):
        promoted.append(kwargs)

    monkeypatch.setattr(chat_router, "promote_answer_to_draft", fake_promote)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_session_factory] = lambda: async_sessionmaker(db.bind, expire_on_commit=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.promoted = promoted
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_session_factory, None)


def parse_events(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


async def add_library_page(db, title: str, content: str) -> VaultEntry:
    entry = VaultEntry(title=title, content=content, source_url="https://www.sawo.com/tower/", memory_enabled=True)
    db.add(entry)
    await db.commit()
    await upsert_embedding(db, VAULT_VEC_TABLE, entry.id, vector_for(title))
    # The stream writes through its own session; an uncommitted write here
    # would hold SQLite's lock and block it.
    await db.commit()
    return entry


@pytest.mark.asyncio
async def test_library_answer_streams_then_finishes_with_the_logged_turn(client, db, llm):
    await add_library_page(db, LIBRARY_TITLE, "The tower heater holds 20 kg of stones.")

    async def stream_reply(*args, **kwargs):
        for piece in ["The tower heater ", "holds 20 kg ", "of stones."]:
            yield piece

    llm.generate_stream = stream_reply

    res = await client.post("/api/chat/stream", json={"question": LIBRARY_Q, "session_id": "sess-stream"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")

    events = parse_events(res.text)
    deltas = [data["text"] for kind, data in events if kind == "delta"]
    (done_kind, done), = [e for e in events if e[0] != "delta"]
    assert done_kind == "done"
    assert "".join(deltas) == done["answer"] == "The tower heater holds 20 kg of stones."
    assert done["chat_log_id"] is not None and done["is_fallback"] is False

    # The turn is saved into a new conversation, same as POST /api/chat.
    conversation = await db.get(Conversation, done["conversation_id"])
    assert conversation is not None and conversation.title
    # And the Library answer is still queued for FAQ promotion afterwards.
    assert [p["question"] for p in client.promoted] == [LIBRARY_Q]


@pytest.mark.asyncio
async def test_unanswerable_question_sends_no_preview_only_the_fallback(client):
    res = await client.post(
        "/api/chat/stream", json={"question": "what is the warranty on the door handles", "session_id": "sess-fb"}
    )
    events = parse_events(res.text)
    assert [kind for kind, _ in events] == ["done"]
    assert events[0][1]["is_fallback"] is True


@pytest.mark.asyncio
async def test_faq_answer_arrives_whole(client, db):
    await add_faq(db, LIBRARY_Q, "It holds 20 kg of stones.")
    res = await client.post("/api/chat/stream", json={"question": LIBRARY_Q, "session_id": "sess-faq"})
    events = parse_events(res.text)
    assert [kind for kind, _ in events] == ["done"]
    assert events[0][1]["answer"] == "It holds 20 kg of stones."


@pytest.mark.asyncio
async def test_someone_elses_conversation_is_rejected_before_streaming(client, db):
    other = Conversation(owner_hash="someone-else", title="Not yours")
    db.add(other)
    await db.commit()
    res = await client.post(
        "/api/chat/stream", json={"question": LIBRARY_Q, "session_id": "s", "conversation_id": other.id}
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_pipeline_crash_becomes_an_error_event(client, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr(chat_router, "answer_question", boom)
    res = await client.post("/api/chat/stream", json={"question": LIBRARY_Q, "session_id": "s"})
    events = parse_events(res.text)
    assert [kind for kind, _ in events] == ["error"]


@pytest.mark.asyncio
async def test_first_visit_still_gets_the_owner_cookie(client):
    res = await client.post(
        "/api/chat/stream", json={"question": "what is the warranty on the door handles", "session_id": "s"}
    )
    assert "helpdesk_owner" in res.headers.get("set-cookie", "")
