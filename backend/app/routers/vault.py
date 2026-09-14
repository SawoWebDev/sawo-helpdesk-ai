from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.ai.factory import get_embedding_engine
from app.core.deps import require_agent_or_admin
from app.crud.vault import (
    bulk_set_memory_enabled,
    create_vault_entry,
    delete_vault_entry,
    get_vault_entry,
    keyword_search_vault,
    list_vault_entries,
    semantic_search_vault,
)
from app.db.session import get_db
from app.rag.vault_reindex import embed_vault_entry
from app.schemas.common import PaginatedResponse
from app.schemas.vault import (
    BulkMemoryToggleRequest,
    VaultEntryCreate,
    VaultEntryOut,
    VaultEntryUpdate,
    VaultSearchResult,
)

router = APIRouter(prefix="/api/vault", tags=["vault"], dependencies=[Depends(require_agent_or_admin)])


@router.get("", response_model=PaginatedResponse)
async def list_all(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_id: int | None = None,
    search: str | None = None,
    memory_enabled: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_vault_entries(db, page, page_size, category_id, search, memory_enabled)
    return PaginatedResponse(
        items=[VaultEntryOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# NOTE: /search and /bulk-memory-toggle are static paths and MUST be declared
# before /{entry_id} below, or FastAPI's dynamic route shadows them (same
# gotcha as imports.router vs faqs.router in main.py).
@router.get("/search", response_model=list[VaultSearchResult])
async def search(q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    keyword_results = await keyword_search_vault(db, q, limit=limit)

    semantic_results: list[tuple] = []
    try:
        embedding_engine = await get_embedding_engine(db)
        [query_vector] = await embedding_engine.embed([q])
        semantic_results = await semantic_search_vault(db, query_vector, limit=limit)
    except AIEngineError:
        # Keyword results alone still populate the UI if embeddings are unreachable.
        pass

    by_id: dict[int, dict] = {}
    for entry, rank, excerpt in keyword_results:
        by_id[entry.id] = {
            "entry": entry,
            "keyword_score": min(rank, 1.0),
            "semantic_score": 0.0,
            "excerpt": excerpt,
            "match_type": "keyword",
        }
    for entry, similarity in semantic_results:
        if entry.id in by_id:
            by_id[entry.id]["semantic_score"] = similarity
            by_id[entry.id]["match_type"] = "both"
        else:
            by_id[entry.id] = {
                "entry": entry,
                "keyword_score": 0.0,
                "semantic_score": similarity,
                "excerpt": entry.content[:200],
                "match_type": "semantic",
            }

    results = []
    for item in by_id.values():
        combined = 0.5 * item["keyword_score"] + 0.5 * item["semantic_score"]
        results.append(
            VaultSearchResult(
                entry=VaultEntryOut.model_validate(item["entry"]),
                score=combined,
                excerpt=item["excerpt"],
                match_type=item["match_type"],
            )
        )
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:limit]


@router.post("/bulk-memory-toggle")
async def bulk_memory_toggle(payload: BulkMemoryToggleRequest, db: AsyncSession = Depends(get_db)):
    entries = await bulk_set_memory_enabled(db, payload.entry_ids, payload.enabled)
    if payload.enabled:
        for entry in entries:
            try:
                await embed_vault_entry(db, entry)
            except AIEngineError as exc:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        await db.commit()
    return {"updated": len(entries)}


@router.get("/{entry_id}", response_model=VaultEntryOut)
async def get_one(entry_id: int, db: AsyncSession = Depends(get_db)):
    entry = await get_vault_entry(db, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vault entry not found")
    return entry


@router.post("", response_model=VaultEntryOut, status_code=status.HTTP_201_CREATED)
async def create(payload: VaultEntryCreate, db: AsyncSession = Depends(get_db)):
    entry = await create_vault_entry(
        db,
        title=payload.title,
        content=payload.content,
        category_id=payload.category_id,
        tags=payload.tags,
        source_type="manual",
    )
    return entry


@router.put("/{entry_id}", response_model=VaultEntryOut)
async def update(entry_id: int, payload: VaultEntryUpdate, db: AsyncSession = Depends(get_db)):
    entry = await get_vault_entry(db, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vault entry not found")

    changed_content = False
    memory_toggled_on = False
    for field_name in ("title", "content", "category_id", "tags"):
        if field_name in payload.model_fields_set:
            setattr(entry, field_name, getattr(payload, field_name))
            if field_name in ("title", "content"):
                changed_content = True

    if "memory_enabled" in payload.model_fields_set and payload.memory_enabled is not None:
        if payload.memory_enabled and not entry.memory_enabled:
            memory_toggled_on = True
        elif not payload.memory_enabled and entry.memory_enabled:
            entry.embedding = None
        entry.memory_enabled = payload.memory_enabled

    if entry.memory_enabled and (changed_content or memory_toggled_on):
        try:
            await embed_vault_entry(db, entry)
        except AIEngineError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(entry_id: int, db: AsyncSession = Depends(get_db)):
    entry = await get_vault_entry(db, entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vault entry not found")
    await delete_vault_entry(db, entry)
