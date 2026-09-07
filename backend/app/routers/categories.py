from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_agent_or_admin
from app.crud.category import (
    create_category,
    delete_category,
    get_category,
    list_categories,
    update_category,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(
    prefix="/api/categories", tags=["categories"], dependencies=[Depends(require_agent_or_admin)]
)


@router.get("", response_model=list[CategoryOut])
async def list_all(db: AsyncSession = Depends(get_db)):
    return await list_categories(db)


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create(payload: CategoryCreate, db: AsyncSession = Depends(get_db)):
    if payload.parent_id is not None:
        parent = await get_category(db, payload.parent_id)
        if parent is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent category not found")
    category = await create_category(db, payload.name, payload.parent_id)
    return CategoryOut(
        id=category.id,
        name=category.name,
        parent_id=category.parent_id,
        created_at=category.created_at,
        updated_at=category.updated_at,
        faq_count=0,
        child_count=0,
    )


@router.put("/{category_id}", response_model=CategoryOut)
async def update(category_id: int, payload: CategoryUpdate, db: AsyncSession = Depends(get_db)):
    category = await get_category(db, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    if payload.parent_id is not None and payload.parent_id == category_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A category cannot be its own parent")

    kwargs = {}
    if "parent_id" in payload.model_fields_set:
        kwargs["parent_id"] = payload.parent_id
    category = await update_category(db, category, payload.name, **kwargs)
    return CategoryOut(
        id=category.id,
        name=category.name,
        parent_id=category.parent_id,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(category_id: int, force: bool = False, db: AsyncSession = Depends(get_db)):
    category = await get_category(db, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    categories = await list_categories(db)
    info = next((c for c in categories if c["id"] == category_id), None)
    if info and (info["faq_count"] > 0 or info["child_count"] > 0) and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category has attached FAQs or child categories. Pass force=true to delete anyway "
            "(children are reassigned to no parent, FAQs are reassigned to no category).",
        )

    await delete_category(db, category)
