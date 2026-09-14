"""Embedding storage via sqlite-vec, kept in separate vec0 virtual tables
(vec0 doesn't support NULL vectors or living alongside ordinary columns on
the same table). Each vec table is keyed by rowid = the owning row's id, and
a row only exists here once that entry actually has an embedding — presence
is tracked on the owning table via `has_embedding`."""

import sqlite_vec
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

FAQ_VEC_TABLE = "faq_entries_vec"
VAULT_VEC_TABLE = "vault_entries_vec"


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


def create_vec_table_sql(table: str) -> str:
    return (
        f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING vec0("
        f"embedding float[{settings.embedding_dimensions}] distance_metric=cosine"
        f")"
    )
