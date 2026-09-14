from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.faq import FAQEntry


async def get_category(db: AsyncSession, category_id: int) -> Category | None:
    result = await db.execute(select(Category).where(Category.id == category_id))
    return result.scalar_one_or_none()


async def get_category_by_name(
    db: AsyncSession, name: str, parent_id: int | None
) -> Category | None:
    stmt = select(Category).where(Category.name == name, Category.parent_id == parent_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_categories(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(Category))
    categories = result.scalars().all()

    faq_counts_result = await db.execute(
        select(FAQEntry.category_id, func.count(FAQEntry.id)).group_by(FAQEntry.category_id)
    )
    faq_counts = dict(faq_counts_result.all())

    child_counts_result = await db.execute(
        select(Category.parent_id, func.count(Category.id))
        .where(Category.parent_id.is_not(None))
        .group_by(Category.parent_id)
    )
    child_counts = dict(child_counts_result.all())

    out = []
    for c in categories:
        out.append(
            {
                "id": c.id,
                "name": c.name,
                "parent_id": c.parent_id,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
                "faq_count": faq_counts.get(c.id, 0),
                "child_count": child_counts.get(c.id, 0),
            }
        )
    return out


async def create_category(db: AsyncSession, name: str, parent_id: int | None) -> Category:
    category = Category(name=name, parent_id=parent_id)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


_UNSET = object()


async def update_category(
    db: AsyncSession, category: Category, name: str | None, parent_id=_UNSET
) -> Category:
    if name is not None:
        category.name = name
    if parent_id is not _UNSET:
        category.parent_id = parent_id
    await db.commit()
    await db.refresh(category)
    return category


async def delete_category(db: AsyncSession, category: Category) -> None:
    await db.delete(category)
    await db.commit()


OTHER_CATEGORY_NAME = "Other"


async def get_or_create_other_category(db: AsyncSession) -> Category:
    """Top-level catch-all category for questions the AI can't answer from the
    knowledge base (e.g. company/pricing/product questions outside its scope)."""
    category = await get_category_by_name(db, OTHER_CATEGORY_NAME, None)
    if category is None:
        category = await create_category(db, OTHER_CATEGORY_NAME, None)
    return category


async def build_category_path_map(db: AsyncSession) -> dict[int, str]:
    """Map each category id to its full 'Parent > Child' path string, for export."""
    result = await db.execute(select(Category))
    categories = {c.id: c for c in result.scalars().all()}

    paths: dict[int, str] = {}

    def resolve(category_id: int) -> str:
        if category_id in paths:
            return paths[category_id]
        category = categories[category_id]
        if category.parent_id is None:
            path = category.name
        else:
            path = f"{resolve(category.parent_id)} > {category.name}"
        paths[category_id] = path
        return path

    for cid in categories:
        resolve(cid)
    return paths


async def get_or_create_category_path(db: AsyncSession, path: str) -> Category:
    """Resolve a 'Parent > Child' style path, creating any missing segments."""
    parts = [p.strip() for p in path.split(">") if p.strip()]
    parent_id: int | None = None
    category: Category | None = None
    for part in parts:
        category = await get_category_by_name(db, part, parent_id)
        if category is None:
            category = await create_category(db, part, parent_id)
        parent_id = category.id
    if category is None:
        raise ValueError("Empty category path")
    return category
