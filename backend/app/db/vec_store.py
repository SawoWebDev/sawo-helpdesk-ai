"""Embedding storage via sqlite-vec, kept in separate vec0 virtual tables
(vec0 doesn't support NULL vectors or living alongside ordinary columns on
the same table). Each vec table is keyed by rowid = the owning row's id, and
a row only exists here once that entry actually has an embedding — presence
is tracked on the owning table via `has_embedding`."""

from array import array

import sqlite_vec
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

FAQ_VEC_TABLE = "faq_entries_vec"
VAULT_VEC_TABLE = "vault_entries_vec"
# Question-only embeddings, for "is this the same question?" (saved-answer
# reuse). FAQ_VEC_TABLE holds question+answer embeddings, which is the right
# shape for RAG retrieval but not for question-to-question similarity.
# rowid = faq_entries.id / faq_phrasings.id respectively.
FAQ_QUESTION_VEC_TABLE = "faq_questions_vec"
FAQ_PHRASING_VEC_TABLE = "faq_phrasings_vec"


async def upsert_embedding(db: AsyncSession, table: str, entry_id: int, vector: list[float]) -> None:
    blob = sqlite_vec.serialize_float32(vector)
    await db.execute(text(f"DELETE FROM {table} WHERE rowid = :id"), {"id": entry_id})
    await db.execute(
        text(f"INSERT INTO {table}(rowid, embedding) VALUES (:id, :embedding)"),
        {"id": entry_id, "embedding": blob},
    )


async def delete_embedding(db: AsyncSession, table: str, entry_id: int) -> None:
    await db.execute(text(f"DELETE FROM {table} WHERE rowid = :id"), {"id": entry_id})


async def knn_search(
    db: AsyncSession, table: str, query_vector: list[float], limit: int
) -> list[tuple[int, float]]:
    """Returns (rowid, cosine_similarity) pairs, best match first."""
    blob = sqlite_vec.serialize_float32(query_vector)
    result = await db.execute(
        text(
            f"SELECT rowid, distance FROM {table} "
            f"WHERE embedding MATCH :embedding AND k = :k "
            f"ORDER BY distance"
        ),
        {"embedding": blob, "k": limit},
    )
    return [(row.rowid, 1.0 - float(row.distance)) for row in result.all()]


async def get_embeddings(db: AsyncSession, table: str, entry_ids: list[int]) -> dict[int, list[float]]:
    """Stored vectors for the given rowids; ids with no stored vector are
    simply absent from the result."""
    if not entry_ids:
        return {}
    placeholders = ", ".join(f":id{i}" for i in range(len(entry_ids)))
    result = await db.execute(
        text(f"SELECT rowid, embedding FROM {table} WHERE rowid IN ({placeholders})"),
        {f"id{i}": entry_id for i, entry_id in enumerate(entry_ids)},
    )
    vectors = {}
    for row in result.all():
        floats = array("f")
        floats.frombytes(row.embedding)
        vectors[row.rowid] = floats.tolist()
    return vectors


def create_vec_table_sql(table: str) -> str:
    return (
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING vec0("
        f"embedding float[{settings.embedding_dimensions}] distance_metric=cosine"
        f")"
    )
