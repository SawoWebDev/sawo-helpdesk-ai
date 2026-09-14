from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.vec_store import FAQ_VEC_TABLE, delete_embedding
from app.models.faq import FAQEntry


async def get_faq(db: AsyncSession, faq_id: int) -> FAQEntry | None:
    result = await db.execute(select(FAQEntry).where(FAQEntry.id == faq_id))
    return result.scalar_one_or_none()


async def list_faqs(
    db: AsyncSession,
    page: int,
    page_size: int,
    category_id: int | None = None,
    search: str | None = None,
) -> tuple[list[FAQEntry], int]:
    stmt = select(FAQEntry)
    count_stmt = select(func.count(FAQEntry.id))

    if category_id is not None:
        stmt = stmt.where(FAQEntry.category_id == category_id)
        count_stmt = count_stmt.where(FAQEntry.category_id == category_id)

    if search:
        like = f"%{search}%"
        condition = or_(FAQEntry.question.ilike(like), FAQEntry.answer.ilike(like))
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(FAQEntry.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def list_faqs_all(
    db: AsyncSession,
    category_id: int | None = None,
    search: str | None = None,
) -> list[FAQEntry]:
    """Unpaginated variant of list_faqs, for export."""
    stmt = select(FAQEntry)

    if category_id is not None:
        stmt = stmt.where(FAQEntry.category_id == category_id)

    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(FAQEntry.question.ilike(like), FAQEntry.answer.ilike(like)))

    stmt = stmt.order_by(FAQEntry.updated_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_faq(
    db: AsyncSession,
    question: str,
    answer: str,
    category_id: int | None,
    image_urls: list[str],
    reference_urls: list[str],
    source: str = "manual",
) -> FAQEntry:
    entry = FAQEntry(
        question=question,
        answer=answer,
        category_id=category_id,
        image_urls=image_urls,
        reference_urls=reference_urls,
        source=source,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def delete_faq(db: AsyncSession, entry: FAQEntry) -> None:
    await delete_embedding(db, FAQ_VEC_TABLE, entry.id)
    await db.delete(entry)
    await db.commit()
