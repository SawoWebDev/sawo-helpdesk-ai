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


async def create_source(
    db: AsyncSession,
    job_id: int | None,
    source_type: str,
    category_id: int | None,
    origin_url: str | None = None,
    file_path: str | None = None,
    original_filename: str | None = None,
    crawl_depth: int | None = None,
    auto_generate_faqs: bool = True,
) -> HarvestSource:
    source = HarvestSource(
        job_id=job_id,
        source_type=source_type,
        category_id=category_id,
        origin_url=origin_url,
        file_path=file_path,
        original_filename=original_filename,
        crawl_depth=crawl_depth,
        auto_generate_faqs=auto_generate_faqs,
        status="pending",
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


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


async def delete_source(db: AsyncSession, source: HarvestSource) -> None:
    await db.delete(source)
    await db.commit()
