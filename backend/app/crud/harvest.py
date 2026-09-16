from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.harvest_job import HarvestJob
from app.models.harvest_source import HarvestSource


async def create_job(db: AsyncSession, job_type: str, config: dict, created_by_id: int | None) -> HarvestJob:
    job = HarvestJob(job_type=job_type, config=config, created_by_id=created_by_id, status="queued")
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_job(db: AsyncSession, job_id: int) -> HarvestJob | None:
    result = await db.execute(select(HarvestJob).where(HarvestJob.id == job_id))
    return result.scalar_one_or_none()


async def rename_job(db: AsyncSession, job: HarvestJob, label: str | None) -> HarvestJob:
    """Sets or clears the batch's display-name override. `label=None` (or
    blank) reverts the row to its auto-derived label on the next listing."""
    job.label = label.strip() if label and label.strip() else None
    await db.commit()
    await db.refresh(job)
    return job


async def create_source(
    db: AsyncSession,
    job_id: int | None,
    source_type: str,
    category_id: int | None,
    origin_url: str | None = None,
    file_path: str | None = None,
    original_filename: str | None = None,
    crawl_depth: int | None = None,
) -> HarvestSource:
    source = HarvestSource(
        job_id=job_id,
        source_type=source_type,
        category_id=category_id,
        origin_url=origin_url,
        file_path=file_path,
        original_filename=original_filename,
        crawl_depth=crawl_depth,
        status="pending",
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


async def create_sources_bulk(
    db: AsyncSession, job_id: int | None, category_id: int | None, origin_urls: list[str]
) -> list[HarvestSource]:
    """Same as create_source (source_type="url", status="pending") for many
    URLs at once, but with a single flush/commit instead of one round-trip
    per row — a batch crawl can be tens of thousands of URLs, and committing
    each individually would mean that many separate DB transactions before
    the request can even return."""
    sources = [
        HarvestSource(job_id=job_id, source_type="url", category_id=category_id, origin_url=url, status="pending")
        for url in origin_urls
    ]
    db.add_all(sources)
    await db.commit()
    return sources


async def get_source(db: AsyncSession, source_id: int) -> HarvestSource | None:
    result = await db.execute(select(HarvestSource).where(HarvestSource.id == source_id))
    return result.scalar_one_or_none()


async def list_sources(
    db: AsyncSession,
    page: int,
    page_size: int,
    category_id: int | None = None,
    status_filter: str | None = None,
    search: str | None = None,
) -> tuple[list[HarvestSource], int]:
    from sqlalchemy import func, or_

    stmt = select(HarvestSource)
    count_stmt = select(func.count(HarvestSource.id))

    if category_id is not None:
        stmt = stmt.where(HarvestSource.category_id == category_id)
        count_stmt = count_stmt.where(HarvestSource.category_id == category_id)

    if status_filter is not None:
        stmt = stmt.where(HarvestSource.status == status_filter)
        count_stmt = count_stmt.where(HarvestSource.status == status_filter)

    if search:
        like = f"%{search}%"
        condition = or_(HarvestSource.original_filename.ilike(like), HarvestSource.origin_url.ilike(like))
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(HarvestSource.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


BATCH_JOB_TYPES = ("web_crawl_batch",)


async def list_sources_grouped(
    db: AsyncSession,
    page: int,
    page_size: int,
    category_id: int | None = None,
    status_filter: str | None = None,
    search: str | None = None,
) -> tuple[list[dict], int]:
    """Top-level listing where a sitemap batch crawl collapses into one
    summary row (keyed by its HarvestJob) instead of one row per page, while
    single-URL crawls and file uploads (job_id either None or a non-batch
    job_type) stay as individual rows, exactly as before.

    Grouping is done in Python rather than SQL: the dataset per admin is
    small (hundreds, not millions, of harvest sources), and a portable
    "is this job a batch" grouping key is awkward to express as a single
    SQL aggregate across SQLite/other backends, so a straightforward Python
    pass over the already-filtered rows is both simpler and fast enough."""
    from sqlalchemy import or_

    base = select(HarvestSource)

    if category_id is not None:
        base = base.where(HarvestSource.category_id == category_id)
    if status_filter is not None:
        base = base.where(HarvestSource.status == status_filter)
    if search:
        like = f"%{search}%"
        base = base.where(or_(HarvestSource.original_filename.ilike(like), HarvestSource.origin_url.ilike(like)))

    rows = (await db.execute(base.order_by(HarvestSource.created_at.desc()))).scalars().all()

    groups: dict[int, dict] = {}
    order: list[int] = []
    job_cache: dict[int, HarvestJob | None] = {}

    for source in rows:
        job = None
        if source.job_id is not None:
            if source.job_id not in job_cache:
                job_cache[source.job_id] = await get_job(db, source.job_id)
            job = job_cache[source.job_id]

        is_batch = job is not None and job.job_type in BATCH_JOB_TYPES
        key = job.id if is_batch else source.id

        if key not in groups:
            order.append(key)
            groups[key] = {
                "is_batch": is_batch,
                "job_id": job.id if job else None,
                "job_type": job.job_type if job else None,
                "label": job.label if job else None,
                "created_at": source.created_at,
                "sources": [],
            }
        groups[key]["sources"].append(source)
        # Keep the group's created_at as the earliest (first-crawled) timestamp.
        if source.created_at < groups[key]["created_at"]:
            groups[key]["created_at"] = source.created_at

    order.sort(key=lambda k: groups[k]["created_at"], reverse=True)

    total = len(order)
    page_keys = order[(page - 1) * page_size : (page - 1) * page_size + page_size]

    results = []
    for key in page_keys:
        group = groups[key]
        sources = group["sources"]
        if group["is_batch"]:
            statuses = [s.status for s in sources]
            results.append(
                {
                    "is_batch": True,
                    "job_id": group["job_id"],
                    "source_count": len(sources),
                    "indexed_count": statuses.count("indexed"),
                    "failed_count": statuses.count("failed"),
                    "pending_count": statuses.count("pending") + statuses.count("processing"),
                    "category_id": sources[0].category_id if sources else None,
                    "created_at": group["created_at"],
                    "origin_label": group["label"] or _common_origin_label(sources),
                }
            )
        else:
            results.append({"is_batch": False, "source": sources[0]})

    return results, total


def _common_origin_label(sources: list[HarvestSource]) -> str:
    """A short label for a batch's parent row: the shared hostname if all
    crawled URLs are on the same domain, else a generic count."""
    hosts = set()
    for s in sources:
        if s.origin_url:
            try:
                import httpx

                hosts.add(httpx.URL(s.origin_url).host)
            except Exception:
                pass
    if len(hosts) == 1:
        return next(iter(hosts))
    return f"{len(sources)} pages"


async def get_sources_by_job(
    db: AsyncSession,
    job_id: int,
    status_filter: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> list[HarvestSource]:
    """`page`/`page_size` omitted (the default) returns every matching source
    — needed by callers that must act on the whole set (retry-all, delete-job
    cleanup). The admin-facing listing endpoint below passes them, since a
    batch can be huge (tens of thousands of pages) and rendering every row
    at once would freeze the browser."""
    stmt = select(HarvestSource).where(HarvestSource.job_id == job_id)
    if status_filter is not None:
        stmt = stmt.where(HarvestSource.status == status_filter)
    # Ordered by id (== insertion order == the order background tasks were
    # queued in, since create_sources_bulk inserts in list order and crawl
    # tasks are queued in that same loop) rather than alphabetically by URL.
    # That way this list's top-to-bottom order matches actual crawl progress
    # — pending flips to indexed moving down the page — instead of an
    # alphabetical slice that may never show any movement, since crawl order
    # has nothing to do with URL alphabetical order.
    stmt = stmt.order_by(HarvestSource.id)
    if page is not None and page_size is not None:
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_sources_by_job(db: AsyncSession, job_id: int, status_filter: str | None = None) -> int:
    from sqlalchemy import func

    stmt = select(func.count(HarvestSource.id)).where(HarvestSource.job_id == job_id)
    if status_filter is not None:
        stmt = stmt.where(HarvestSource.status == status_filter)
    return (await db.execute(stmt)).scalar_one()


async def delete_source(db: AsyncSession, source: HarvestSource) -> None:
    await db.delete(source)
    await db.commit()


async def delete_job_and_sources(db: AsyncSession, job_id: int) -> int:
    """Deletes every source in a batch job (and their vault entries via the
    same per-source cleanup as a single delete), then the job itself.
    Returns how many sources were removed."""
    from app.crud.vault import delete_vault_entry
    from app.models.vault_entry import VaultEntry

    sources = await get_sources_by_job(db, job_id)
    for source in sources:
        vault_result = await db.execute(select(VaultEntry).where(VaultEntry.source_id == source.id))
        for entry in vault_result.scalars().all():
            await delete_vault_entry(db, entry)
        await db.delete(source)

    job = await get_job(db, job_id)
    if job is not None:
        await db.delete(job)

    await db.commit()
    return len(sources)
