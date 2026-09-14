from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.vec_store import VAULT_VEC_TABLE, delete_embedding, knn_search
from app.models.vault_entry import VaultEntry


async def get_vault_entry(db: AsyncSession, entry_id: int) -> VaultEntry | None:
    result = await db.execute(select(VaultEntry).where(VaultEntry.id == entry_id))
    return result.scalar_one_or_none()


async def list_vault_entries(
    db: AsyncSession,
    page: int,
    page_size: int,
    category_id: int | None = None,
    search: str | None = None,
    memory_enabled: bool | None = None,
) -> tuple[list[VaultEntry], int]:
    stmt = select(VaultEntry)
    count_stmt = select(func.count(VaultEntry.id))

    if category_id is not None:
        stmt = stmt.where(VaultEntry.category_id == category_id)
        count_stmt = count_stmt.where(VaultEntry.category_id == category_id)

    if memory_enabled is not None:
        stmt = stmt.where(VaultEntry.memory_enabled == memory_enabled)
        count_stmt = count_stmt.where(VaultEntry.memory_enabled == memory_enabled)

    if search:
        like = f"%{search}%"
        condition = or_(VaultEntry.title.ilike(like), VaultEntry.content.ilike(like))
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(VaultEntry.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def list_vault_entries_all(db: AsyncSession) -> list[VaultEntry]:
    """Unpaginated, for backup export."""
    result = await db.execute(select(VaultEntry).order_by(VaultEntry.id))
    return list(result.scalars().all())


async def create_vault_entry(
    db: AsyncSession,
    title: str,
    content: str,
    category_id: int | None,
    tags: list[str],
    source_type: str = "manual",
    source_id: int | None = None,
    source_url: str | None = None,
) -> VaultEntry:
    entry = VaultEntry(
        title=title,
        content=content,
        category_id=category_id,
        tags=tags,
        source_type=source_type,
        source_id=source_id,
        source_url=source_url,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def delete_vault_entry(db: AsyncSession, entry: VaultEntry) -> None:
    await delete_embedding(db, VAULT_VEC_TABLE, entry.id)
    await db.delete(entry)
    await db.commit()


async def bulk_set_memory_enabled(db: AsyncSession, entry_ids: list[int], enabled: bool) -> list[VaultEntry]:
    result = await db.execute(select(VaultEntry).where(VaultEntry.id.in_(entry_ids)))
    entries = list(result.scalars().all())
    for entry in entries:
        entry.memory_enabled = enabled
        if not enabled:
            await db.execute(text(f"DELETE FROM {VAULT_VEC_TABLE} WHERE rowid = :id"), {"id": entry.id})
            entry.has_embedding = False
    await db.commit()
    return entries


async def keyword_search_vault(db: AsyncSession, query: str, limit: int = 20) -> list[tuple[VaultEntry, float, str]]:
    """FTS5 full-text search over title+content, ranked by bm25 (more negative
    = better match, so we sort ascending and flip the sign for a 0..1-ish
    score). Works even with zero embeddings. Returns (entry, rank, excerpt)."""
    fts_stmt = text(
        "SELECT rowid, bm25(vault_entries_fts) AS rank, "
        "snippet(vault_entries_fts, -1, '**', '**', '...', 20) AS excerpt "
        "FROM vault_entries_fts WHERE vault_entries_fts MATCH :query "
        "ORDER BY rank LIMIT :limit"
    )
    try:
        rows = (await db.execute(fts_stmt, {"query": query, "limit": limit})).all()
    except Exception:
        # FTS5 raises on malformed MATCH syntax (bare punctuation, dangling
        # operators, etc.) — treat that as "no keyword matches" rather than
        # failing the whole hybrid search.
        return []

    if not rows:
        return []

    ids = [row.rowid for row in rows]
    entries_by_id = {
        entry.id: entry
        for entry in (
            await db.execute(select(VaultEntry).where(VaultEntry.id.in_(ids)))
        ).scalars()
    }

    results = []
    for row in rows:
        entry = entries_by_id.get(row.rowid)
        if entry is None:
            continue
        score = 1.0 / (1.0 + max(-row.rank, 0.0))
        results.append((entry, score, row.excerpt))
    return results


async def semantic_search_vault(
    db: AsyncSession, query_vector: list[float], limit: int = 20
) -> list[tuple[VaultEntry, float]]:
    """sqlite-vec cosine-similarity KNN search, same shape as the FAQ RAG query."""
    hits = await knn_search(db, VAULT_VEC_TABLE, query_vector, limit)
    if not hits:
        return []

    ids = [entry_id for entry_id, _ in hits]
    entries_by_id = {
        entry.id: entry
        for entry in (
            await db.execute(select(VaultEntry).where(VaultEntry.id.in_(ids)))
        ).scalars()
    }
    return [
        (entries_by_id[entry_id], similarity)
        for entry_id, similarity in hits
        if entry_id in entries_by_id
    ]
