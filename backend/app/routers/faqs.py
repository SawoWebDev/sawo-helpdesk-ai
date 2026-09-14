from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.core.deps import require_agent_or_admin
from app.crud.faq import create_faq, delete_faq, get_faq, list_faqs
from app.db.session import get_db
from app.rag.reindex import embed_entry
from app.schemas.common import PaginatedResponse
from app.schemas.faq import FAQCreate, FAQOut, FAQUpdate

router = APIRouter(prefix="/api/faqs", tags=["faqs"], dependencies=[Depends(require_agent_or_admin)])


@router.get("", response_model=PaginatedResponse)
async def list_all(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_id: int | None = None,
    search: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_faqs(db, page, page_size, category_id, search, status_filter)
    return PaginatedResponse(
        items=[FAQOut.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{faq_id}", response_model=FAQOut)
async def get_one(faq_id: int, db: AsyncSession = Depends(get_db)):
    entry = await get_faq(db, faq_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ entry not found")
    return entry


@router.post("", response_model=FAQOut, status_code=status.HTTP_201_CREATED)
async def create(payload: FAQCreate, db: AsyncSession = Depends(get_db)):
    entry = await create_faq(
        db,
        question=payload.question,
        answer=payload.answer,
        category_id=payload.category_id,
        image_urls=payload.image_urls,
        reference_urls=payload.reference_urls,
        source="manual",
    )
    try:
        await embed_entry(db, entry)
    except AIEngineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(entry)
    return entry


@router.put("/{faq_id}", response_model=FAQOut)
async def update(faq_id: int, payload: FAQUpdate, db: AsyncSession = Depends(get_db)):
    entry = await get_faq(db, faq_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ entry not found")

    changed_content = False
    status_changed = False
    for field_name in ("question", "answer", "category_id", "image_urls", "reference_urls", "status"):
        if field_name in payload.model_fields_set:
            value = getattr(payload, field_name)
            setattr(entry, field_name, value)
            if field_name in ("question", "answer"):
                changed_content = True
            if field_name == "status":
                status_changed = True

    if changed_content or status_changed:
        try:
            await embed_entry(db, entry)
        except AIEngineError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(faq_id: int, db: AsyncSession = Depends(get_db)):
    entry = await get_faq(db, faq_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ entry not found")
    await delete_faq(db, entry)
