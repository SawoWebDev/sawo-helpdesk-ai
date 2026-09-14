import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.ai.factory import get_embedding_engine
from app.core.config import settings
from app.core.deps import require_agent_or_admin
from app.crud.category import create_category, get_category, get_category_by_name
from app.crud.faq import list_faqs_by_source
from app.crud.harvest import create_job, create_source, delete_source, get_source, list_sources
from app.crud.vault import keyword_search_vault, semantic_search_vault
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.library import (
    LibraryCrawlRequest,
    LibrarySearchRequest,
    LibrarySearchResult,
    LibrarySourceOut,
)
from app.services.library_ingest import process_file_source, process_url_source, regenerate_faqs_for_source

router = APIRouter(prefix="/api/library", tags=["library"], dependencies=[Depends(require_agent_or_admin)])

ALLOWED_LIBRARY_EXTENSIONS = (".pdf", ".docx", ".xlsx")


async def _resolve_category(db: AsyncSession, category_id: int | None, new_category_name: str | None) -> int | None:
    if new_category_name and new_category_name.strip():
        name = new_category_name.strip()
        category = await get_category_by_name(db, name, None)
        if category is None:
            category = await create_category(db, name, None)
        return category.id
    if category_id is not None:
        category = await get_category(db, category_id)
        if category is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found")
        return category.id
    return None


# NOTE: /sources, /upload, /crawl, /search are static paths and MUST be
# declared before /sources/{source_id} below (same gotcha as
# imports.router vs faqs.router in main.py).
@router.get("/sources", response_model=PaginatedResponse)
async def list_all_sources(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_sources(db, page, page_size, category_id, status_filter, search)
    return PaginatedResponse(
        items=[LibrarySourceOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/upload", response_model=LibrarySourceOut, status_code=status.HTTP_201_CREATED)
async def upload(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    category_id: int | None = None,
    new_category_name: str | None = None,
    auto_generate_faqs: bool = True,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_agent_or_admin),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_LIBRARY_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_LIBRARY_EXTENSIONS)}",
        )

    contents = await file.read()
    if len(contents) > settings.max_harvest_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds max size of {settings.max_harvest_upload_size_bytes} bytes",
        )

    resolved_category_id = await _resolve_category(db, category_id, new_category_name)

    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(settings.upload_dir, safe_name)
    with open(dest_path, "wb") as f:
        f.write(contents)

    job = await create_job(db, job_type="file_upload", config={"filename": file.filename}, created_by_id=user.id)
    source = await create_source(
        db,
        job_id=job.id,
        source_type="file",
        category_id=resolved_category_id,
        file_path=dest_path,
        original_filename=file.filename,
        auto_generate_faqs=auto_generate_faqs,
    )

    background_tasks.add_task(process_file_source, source.id)
    return source


@router.post("/crawl", response_model=LibrarySourceOut, status_code=status.HTTP_201_CREATED)
async def crawl(
    payload: LibraryCrawlRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_agent_or_admin),
):
    if not payload.url.strip().lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL must start with http:// or https://")

    resolved_category_id = await _resolve_category(db, payload.category_id, payload.new_category_name)

    job = await create_job(db, job_type="web_crawl", config={"url": payload.url, "depth": payload.crawl_depth}, created_by_id=user.id)
    source = await create_source(
        db,
        job_id=job.id,
        source_type="url",
        category_id=resolved_category_id,
        origin_url=payload.url.strip(),
        crawl_depth=payload.crawl_depth,
        auto_generate_faqs=payload.auto_generate_faqs,
    )

    background_tasks.add_task(process_url_source, source.id)
    return source


@router.post("/search", response_model=list[LibrarySearchResult])
async def search(payload: LibrarySearchRequest, db: AsyncSession = Depends(get_db)):
    keyword_results = await keyword_search_vault(db, payload.query, limit=payload.limit)

    semantic_results: list[tuple] = []
    try:
        embedding_engine = await get_embedding_engine(db)
        [query_vector] = await embedding_engine.embed([payload.query])
        semantic_results = await semantic_search_vault(db, query_vector, limit=payload.limit)
    except AIEngineError:
        pass

    by_id: dict[int, dict] = {}
    for entry, rank, excerpt in keyword_results:
        by_id[entry.id] = {"entry": entry, "keyword": min(rank, 1.0), "semantic": 0.0, "excerpt": excerpt, "match_type": "keyword"}
    for entry, similarity in semantic_results:
        if entry.id in by_id:
            by_id[entry.id]["semantic"] = similarity
            by_id[entry.id]["match_type"] = "both"
        else:
            by_id[entry.id] = {
                "entry": entry,
                "keyword": 0.0,
                "semantic": similarity,
                "excerpt": entry.content[:200],
                "match_type": "semantic",
            }

    results = []
    for item in by_id.values():
        entry = item["entry"]
        combined = 0.5 * item["keyword"] + 0.5 * item["semantic"]
        results.append(
            LibrarySearchResult(
                entry_id=entry.id,
                title=entry.title,
                excerpt=item["excerpt"],
                score=combined,
                match_type=item["match_type"],
                source_id=entry.source_id,
                category_id=entry.category_id,
            )
        )
    results.sort(key=lambda r: r.score, reverse=True)
    return results[: payload.limit]


@router.post("/sources/{source_id}/generate-faqs", status_code=status.HTTP_202_ACCEPTED)
async def trigger_faq_generation(
    source_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    source = await get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library source not found")
    if source.status != "indexed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Source must be indexed before generating FAQs")

    background_tasks.add_task(regenerate_faqs_for_source, source.id)
    return {"status": "queued"}


@router.get("/sources/{source_id}/faqs")
async def get_source_faqs(source_id: int, db: AsyncSession = Depends(get_db)):
    faqs = await list_faqs_by_source(db, source_id)
    return [
        {"id": f.id, "question": f.question, "answer": f.answer, "status": f.status}
        for f in faqs
    ]


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_library_source(source_id: int, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select

    from app.crud.vault import delete_vault_entry
    from app.models.vault_entry import VaultEntry

    source = await get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library source not found")

    result = await db.execute(select(VaultEntry).where(VaultEntry.source_id == source_id))
    for entry in result.scalars().all():
        await delete_vault_entry(db, entry)

    await delete_source(db, source)
