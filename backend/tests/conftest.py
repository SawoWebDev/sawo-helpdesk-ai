"""Shared fixtures for the saved-answer tests: a throwaway SQLite+sqlite-vec
database, and fake AI engines that record every call so tests can assert
exactly how many embedding / LLM calls a request made.

Embeddings are hand-built: every text is a point on a circle, so the cosine
between two texts is exactly the similarity a scenario needs. Test modules
register their texts in ANGLES; any unregistered text is orthogonal to all
of them (similarity 0)."""

import math

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import settings
from app.crud import faq as crud_faq
from app.db.base import Base, _setup_connection
from app.db.vec_store import (
    FAQ_PHRASING_VEC_TABLE,
    FAQ_QUESTION_VEC_TABLE,
    FAQ_VEC_TABLE,
    VAULT_VEC_TABLE,
    create_vec_table_sql,
    upsert_embedding,
)
from app.models.faq import FAQEntry
from app.rag import pipeline, reindex, saved_answers

DIM = settings.embedding_dimensions

ANGLES: dict[str, float] = {}


def vec(theta: float) -> list[float]:
    v = [0.0] * DIM
    v[0], v[1] = math.cos(theta), math.sin(theta)
    return v


def angle(sim: float) -> float:
    return math.acos(sim)


def vector_for(text_: str) -> list[float]:
    if text_ in ANGLES:
        return vec(ANGLES[text_])
    v = [0.0] * DIM
    v[2] = 1.0
    return v


class FakeEmbedder:
    def __init__(self):
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [vector_for(t) for t in texts]


class StubLLM:
    name = "stub"

    def __init__(self, reply: str = "Generated answer"):
        self.reply = reply
        self.generate_calls = 0  # every LLM call, including relevance and fact-check
        self.calls: list[tuple[str, str, str]] = []  # (system prompt, context, question)

    async def generate(self, system, context, question, temperature=0, history=None):
        self.generate_calls += 1
        self.calls.append((system, context, question))
        if system.startswith("You are a fact-checker"):
            return "GROUNDED"
        return self.reply


@pytest_asyncio.fixture
async def db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    event.listen(engine.sync_engine, "connect", lambda conn, _rec: conn.run_async(_setup_connection))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for table in (FAQ_VEC_TABLE, VAULT_VEC_TABLE, FAQ_QUESTION_VEC_TABLE, FAQ_PHRASING_VEC_TABLE):
            await conn.execute(text(create_vec_table_sql(table)))
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def embedder(monkeypatch):
    fake = FakeEmbedder()

    async def _get(_db):
        return fake

    for module in (saved_answers, pipeline, crud_faq, reindex):
        monkeypatch.setattr(module, "get_embedding_engine", _get)
    return fake


@pytest.fixture
def llm(monkeypatch):
    stub = StubLLM()

    async def _get(_db):
        return stub

    monkeypatch.setattr(pipeline, "get_active_engine", _get)
    return stub


async def add_faq(db, question, answer, *, status="published", source_id=None, question_vector=True) -> FAQEntry:
    """A published FAQ with its vectors stored directly (no embedder call), the
    way embed_entry leaves it. question_vector=False mimics an FAQ saved
    before question-only vectors existed."""
    faq = FAQEntry(question=question, answer=answer, status=status, source_id=source_id)
    db.add(faq)
    await db.commit()
    if status == "published":
        await upsert_embedding(db, FAQ_VEC_TABLE, faq.id, vector_for(question))
        if question_vector:
            await upsert_embedding(db, FAQ_QUESTION_VEC_TABLE, faq.id, vector_for(question))
        faq.has_embedding = True
        await db.commit()
    return faq
