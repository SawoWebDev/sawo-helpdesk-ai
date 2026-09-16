import os
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.ai.factory import get_active_engine, get_embedding_engine
from app.core import setting_keys
from app.core.config import settings
from app.core.deps import require_admin, require_agent_or_admin
from app.crud.category import create_category, get_category, get_category_by_name
from app.crud.harvest import (
    count_sources_by_job,
    create_job,
    create_source,
    create_sources_bulk,
    delete_job_and_sources,
    delete_source,
    get_job,
    get_sources_by_job,
    get_source,
    list_sources_grouped,
    rename_job,
)
from app.crud.settings import get_setting
from app.crud.vault import keyword_search_vault, semantic_search_vault
from app.db.session import get_db
from app.db.vec_store import VAULT_VEC_TABLE
from app.models.harvest_job import HarvestJob
from app.models.harvest_source import HarvestSource
from app.models.user import User
from app.models.vault_entry import VaultEntry
from app.rag.pipeline import REFUSAL_SENTINEL, SYSTEM_PROMPT, _is_grounded, _sanitize_text
from app.schemas.common import PaginatedResponse
from app.schemas.library import (
    LibraryAnswerSourceOut,
    LibraryBatchSummaryOut,
    LibraryCrawlBatchRequest,
    LibraryCrawlBatchResponse,
    LibraryCrawlRequest,
    LibraryJobRenameRequest,
    LibraryRowOut,
    LibrarySearchRequest,
    LibrarySearchResult,
    LibrarySearchResponse,
    LibrarySourceOut,
    SitemapDiscoverRequest,
    SitemapDiscoverResponse,
)
from app.services.library_ingest import (
    process_file_source,
    process_sources_concurrently,
    process_url_source,
)
from app.services.library_parsers import ParseError, discover_sitemap_urls

# How many top-ranked chunks (by combined keyword+semantic score) get sent to
# the LLM to synthesize an answer from. Kept small since this is a
# synchronous admin-facing search, not the async chat pipeline.
SYNTHESIS_CONTEXT_LIMIT = 5

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
@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_all_library(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    await db.execute(text(f"DELETE FROM {VAULT_VEC_TABLE}"))
    await db.execute(VaultEntry.__table__.delete())
    await db.execute(HarvestSource.__table__.delete())
    await db.execute(HarvestJob.__table__.delete())
    await db.commit()


@router.get("/sources", response_model=PaginatedResponse)
async def list_all_sources(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    rows, total = await list_sources_grouped(db, page, page_size, category_id, status_filter, search)
    items = []
    for row in rows:
        if row["is_batch"]:
            items.append(LibraryRowOut(kind="batch", batch=LibraryBatchSummaryOut(**row)))
        else:
            items.append(LibraryRowOut(kind="source", source=LibrarySourceOut.model_validate(row["source"])))
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/jobs/{job_id}/sources", response_model=PaginatedResponse)
async def list_job_sources(
    job_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    total = await count_sources_by_job(db, job_id, status_filter=status_filter)
    sources = await get_sources_by_job(db, job_id, status_filter=status_filter, page=page, page_size=page_size)
    return PaginatedResponse(
        items=[LibrarySourceOut.model_validate(s) for s in sources], total=total, page=page, page_size=page_size
    )


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_library_job(job_id: int, db: AsyncSession = Depends(get_db)):
    deleted = await delete_job_and_sources(db, job_id)
    if deleted == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch job not found or already empty")


@router.put("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def rename_library_job(job_id: int, payload: LibraryJobRenameRequest, db: AsyncSession = Depends(get_db)):
    """Renames a batch crawl's parent row in the Library Source list. Only
    the batch itself is nameable this way — individual pages within it keep
    showing their real crawled URL, not an editable label."""
    job = await get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch job not found")
    await rename_job(db, job, payload.label)


@router.post("/upload", response_model=LibrarySourceOut, status_code=status.HTTP_201_CREATED)
async def upload(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    category_id: int | None = None,
    new_category_name: str | None = None,
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

    job = await create_job(db, job_type="web_crawl", config={"url": payload.url}, created_by_id=user.id)
    source = await create_source(
        db,
        job_id=job.id,
        source_type="url",
        category_id=resolved_category_id,
        origin_url=payload.url.strip(),
    )

    background_tasks.add_task(process_url_source, source.id)
    return source


@router.post("/discover-sitemap", response_model=SitemapDiscoverResponse)
async def discover_sitemap(payload: SitemapDiscoverRequest, db: AsyncSession = Depends(get_db)):
    if not payload.url.strip().lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="URL must start with http:// or https://")
    max_urls = int(await get_setting(db, setting_keys.MAX_SITEMAP_URLS))
    try:
        urls = await discover_sitemap_urls(payload.url.strip())
    except ParseError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return SitemapDiscoverResponse(urls=urls, max_crawl_urls=max_urls)


@router.post("/crawl-batch", response_model=LibraryCrawlBatchResponse, status_code=status.HTTP_201_CREATED)
async def crawl_batch(
    payload: LibraryCrawlBatchRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_agent_or_admin),
):
    valid_urls = [u.strip() for u in payload.urls if u.strip().lower().startswith(("http://", "https://"))]
    if not valid_urls:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid http(s) URLs provided")

    max_urls = int(await get_setting(db, setting_keys.MAX_SITEMAP_URLS))
    if len(valid_urls) > max_urls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You can crawl at most {max_urls} pages per batch (Settings > General > Max Sitemap URLs). "
            f"{len(valid_urls)} were selected — deselect some or raise the limit.",
        )

    resolved_category_id = await _resolve_category(db, payload.category_id, payload.new_category_name)

    job = await create_job(
        db, job_type="web_crawl_batch", config={"url_count": len(valid_urls)}, created_by_id=user.id
    )

    # One bulk insert/commit for all sources, not one per URL — see
    # create_sources_bulk's docstring. Processed by a single background task
    # that runs a bounded pool of workers concurrently (see
    # process_sources_concurrently) rather than one strictly sequential
    # chain, so a huge batch doesn't take an impractically long time.
    sources = await create_sources_bulk(db, job.id, resolved_category_id, valid_urls)
    background_tasks.add_task(process_sources_concurrently, [(s.id, "url") for s in sources])

    return LibraryCrawlBatchResponse(queued=len(sources), source_ids=[s.id for s in sources])


@router.post("/search", response_model=LibrarySearchResponse)
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
            (
                LibrarySearchResult(
                    entry_id=entry.id,
                    title=entry.title,
                    excerpt=item["excerpt"],
                    score=combined,
                    match_type=item["match_type"],
                    source_id=entry.source_id,
                    category_id=entry.category_id,
                    source_url=entry.source_url,
                ),
                entry,
            )
        )
    results.sort(key=lambda pair: pair[0].score, reverse=True)
    results = results[: payload.limit]

    answer = None
    answer_sources: list[LibraryAnswerSourceOut] = []
    if results:
        synthesis_pool = results[:SYNTHESIS_CONTEXT_LIMIT]
        context = "\n\n".join(f"Topic: {entry.title}\n{entry.content}" for _result, entry in synthesis_pool)
        try:
            engine = await get_active_engine(db)
            generated = await engine.generate(SYSTEM_PROMPT, context, payload.query)
            if generated and REFUSAL_SENTINEL not in generated and await _is_grounded(engine, context, generated):
                answer = _sanitize_text(generated)
                seen_urls: set[str] = set()
                for result, _entry in synthesis_pool:
                    if result.source_url and result.source_url in seen_urls:
                        continue
                    if result.source_url:
                        seen_urls.add(result.source_url)
                    answer_sources.append(
                        LibraryAnswerSourceOut(title=result.title, source_url=result.source_url)
                    )
        except AIEngineError:
            pass

    return LibrarySearchResponse(
        answer=answer, answer_sources=answer_sources, results=[result for result, _entry in results]
    )


@router.get("/sources/{source_id}", response_model=LibrarySourceOut)
async def get_one_source(source_id: int, db: AsyncSession = Depends(get_db)):
    source = await get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library source not found")
    return source


def _queue_retry(background_tasks: BackgroundTasks, source: HarvestSource) -> None:
    if source.source_type == "file":
        background_tasks.add_task(process_file_source, source.id)
    else:
        background_tasks.add_task(process_url_source, source.id)


@router.post("/sources/{source_id}/retry", response_model=LibrarySourceOut)
async def retry_library_source(
    source_id: int, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)
):
    """Re-runs ingestion for a failed source. Safe to re-run from scratch: a
    failed source never got as far as creating any VaultEntry chunks (the
    embed call that would produce them happens before any are stored), so
    there's nothing stale left behind to clean up first."""
    source = await get_source(db, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library source not found")
    if source.status != "failed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only a failed source can be retried")

    source.status = "pending"
    source.error_message = None
    await db.commit()
    await db.refresh(source)

    _queue_retry(background_tasks, source)
    return source


@router.post("/jobs/{job_id}/retry", status_code=status.HTTP_204_NO_CONTENT)
async def retry_library_job(job_id: int, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Retries every failed page in a batch crawl at once."""
    failed = await get_sources_by_job(db, job_id, status_filter="failed")
    if not failed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No failed pages to retry in this batch")

    for source in failed:
        source.status = "pending"
        source.error_message = None
    await db.commit()

    background_tasks.add_task(
        process_sources_concurrently, [(s.id, s.source_type) for s in failed]
    )


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
