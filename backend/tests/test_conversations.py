"""Private per-owner conversation history, exercised through the real HTTP
layer (not just CRUD) since ownership is enforced by the `helpdesk_owner`
cookie dependency living in the router/dependency layer, not in a function
that could be unit-tested directly. Two httpx AsyncClient instances (each
with its own cookie jar) simulate two separate browsers/owners.

Note on "off-topic chatter isn't logged": every path through
`answer_question` (direct FAQ match, off-topic reply, fallback) constructs
and commits a ChatLog row today, so `result.chat_log_id` is never actually
None in practice. The "don't create an empty conversation" guarantee is
still verified below (nothing exists in `conversations` until the first real
`/api/chat` call), just not via a code path that logs nothing — none exists
right now. The `chat_log_id is not None` guard in chat.py is kept anyway as
defensive code matching RagResult's own `int | None` contract."""

from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.main import app
from app.models.chat_log import ChatLog
from tests.conftest import ANGLES, add_faq
from tests.conftest import angle as _angle

RESET_Q1 = "how do I reset the sauna controller to factory settings"
RESET_Q2 = "what is the factory reset procedure for the controller"
RESET_ANSWER = "Press and hold the reset button for 10 seconds."

WARRANTY_Q = "what is the warranty period for the heater"
WARRANTY_ANSWER = "The heater warranty is 2 years."

ANGLES.update(
    {
        RESET_Q1: 0.0,
        RESET_Q2: _angle(0.95),
        WARRANTY_Q: 2.0,
    }
)


@pytest_asyncio.fixture
async def client(db: AsyncSession, embedder, llm) -> AsyncGenerator[httpx.AsyncClient, None]:
    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


async def send(client: httpx.AsyncClient, question: str, session_id: str, conversation_id: int | None = None):
    payload = {"question": question, "session_id": session_id}
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    res = await client.post("/api/chat", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.asyncio
async def test_no_conversations_before_first_message(client, db):
    """Nothing is persisted until a real message is sent — opening the chat
    for the first time must not create any empty conversation rows."""
    res = await client.get("/api/conversations")
    assert res.status_code == 200
    assert res.json() == []


@pytest.mark.asyncio
async def test_ownership_isolation_and_listing(db):
    await add_faq(db, RESET_Q1, RESET_ANSWER)
    await add_faq(db, WARRANTY_Q, WARRANTY_ANSWER)

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as owner_a, httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as owner_b:
            # Owner A opens a conversation, then starts a second one.
            res1 = await send(owner_a, RESET_Q1, "sess-a-1")
            conv_a1 = res1["conversation_id"]
            assert conv_a1 is not None

            res2 = await send(owner_a, WARRANTY_Q, "sess-a-2")
            conv_a2 = res2["conversation_id"]
            assert conv_a2 is not None
            assert conv_a2 != conv_a1

            # Owner B asks the same question as A's second conversation —
            # must land in B's own, separate conversation, not A's.
            res3 = await send(owner_b, WARRANTY_Q, "sess-b-1")
            conv_b = res3["conversation_id"]
            assert conv_b is not None

            # A's list currently [conv_a2, conv_a1] (a2 is newer).
            listing_a = (await owner_a.get("/api/conversations")).json()
            assert [c["id"] for c in listing_a] == [conv_a2, conv_a1]

            # A follows up on the *first* conversation -> it must jump back
            # to the top of A's list (ordering by updated_at, not creation).
            res4 = await send(owner_a, RESET_Q2, "sess-a-1", conversation_id=conv_a1)
            assert res4["conversation_id"] == conv_a1

            listing_a = (await owner_a.get("/api/conversations")).json()
            assert [c["id"] for c in listing_a] == [conv_a1, conv_a2]

            # B only ever sees its own conversation.
            listing_b = (await owner_b.get("/api/conversations")).json()
            assert [c["id"] for c in listing_b] == [conv_b]

            # Detail: A's first conversation now has both turns, in order.
            detail = (await owner_a.get(f"/api/conversations/{conv_a1}")).json()
            assert [m["question_text"] for m in detail["messages"]] == [RESET_Q1, RESET_Q2]

            # Cross-owner access is refused...
            assert (await owner_b.get(f"/api/conversations/{conv_a1}")).status_code == 404
            assert (await owner_a.get(f"/api/conversations/{conv_b}")).status_code == 404
            # ...identically to a conversation that doesn't exist at all, so
            # existence can't be probed.
            missing = await owner_a.get("/api/conversations/999999")
            cross_owner = await owner_a.get(f"/api/conversations/{conv_b}")
            assert missing.status_code == cross_owner.status_code == 404
            assert missing.json()["detail"] == cross_owner.json()["detail"]

            # A fresh client (no prior cookie) can't use someone else's
            # conversation_id either — it mints its own new, empty identity.
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as stranger:
                res = await stranger.get(f"/api/conversations/{conv_a1}")
                assert res.status_code == 404
                assert (await stranger.get("/api/conversations")).json() == []

            # Supplying another owner's conversation_id in a /api/chat body
            # never grants access — ownership comes from B's own cookie only.
            res = await owner_b.post(
                "/api/chat", json={"question": "irrelevant", "session_id": "sess-b-2", "conversation_id": conv_a1}
            )
            assert res.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_cookie_tampering_yields_a_different_empty_owner(db):
    await add_faq(db, RESET_Q1, RESET_ANSWER)

    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as owner_a:
            res1 = await send(owner_a, RESET_Q1, "sess-a-1")
            conv_a1 = res1["conversation_id"]

            # Same client, but with the owner cookie swapped for an arbitrary
            # value: this must behave as an entirely different (new, empty)
            # owner, not as a forged way back into A's history.
            owner_a.cookies.set("helpdesk_owner", "forged-token-value")
            res = await owner_a.get("/api/conversations")
            assert res.status_code == 200
            assert res.json() == []
            assert (await owner_a.get(f"/api/conversations/{conv_a1}")).status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_legacy_chat_logs_without_conversation_are_not_surfaced(client, db):
    """A ChatLog row from before this feature (conversation_id stays NULL)
    must never appear in anyone's private conversation list or detail view."""
    legacy = ChatLog(
        question_text="an old question from before this feature existed",
        answer_text="an old answer",
        matched_faq_ids=[],
        matched_vault_ids=[],
        engine_used="none",
        session_id="legacy-session",
    )
    db.add(legacy)
    await db.commit()

    res = await client.get("/api/conversations")
    assert res.status_code == 200
    assert res.json() == []
