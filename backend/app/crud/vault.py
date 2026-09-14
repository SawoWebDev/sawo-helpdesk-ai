from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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
    await db.delete(entry)
    await db.commit()


async def bulk_set_memory_enabled(db: AsyncSession, entry_ids: list[int], enabled: bool) -> list[VaultEntry]:
    result = await db.execute(select(VaultEntry).where(VaultEntry.id.in_(entry_ids)))
    entries = list(result.scalars().all())
    for entry in entries:
        entry.memory_enabled = enabled
        if not enabled:
            entry.embedding = None
    await db.commit()
    return entries


async def keyword_search_vault(db: AsyncSession, query: str, limit: int = 20) -> list[tuple[VaultEntry, float, str]]:
    """Full-text search via search_vector, ranked by ts_rank. Works even with
    zero embeddings. Returns (entry, rank, excerpt) tuples."""
    tsquery = func.plainto_tsquery("english", query)
    rank = func.ts_rank(VaultEntry.search_vector, tsquery)
    excerpt = func.ts_headline(
        "english", VaultEntry.content, tsquery, "MaxWords=35, MinWords=15, StartSel=**, StopSel=**"
    )
    stmt = (
        select(VaultEntry, rank.label("rank"), excerpt.label("excerpt"))
        .where(VaultEntry.search_vector.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [(entry, float(rank_val), excerpt_val) for entry, rank_val, excerpt_val in result.all()]


async def semantic_search_vault(
    db: AsyncSession, query_vector: list[float], limit: int = 20
) -> list[tuple[VaultEntry, float]]:
    """pgvector cosine-distance search, same shape as the FAQ RAG query."""
    distance_expr = VaultEntry.embedding.cosine_distance(query_vector)
    stmt = (
        select(VaultEntry, distance_expr.label("distance"))
        .where(VaultEntry.embedding.is_not(None))
        .order_by(distance_expr)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [(entry, 1.0 - float(distance)) for entry, distance in result.all()]
