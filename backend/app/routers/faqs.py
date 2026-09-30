from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.ai.factory import get_embedding_engine
from app.core.deps import require_admin, require_agent_or_admin, require_dangerous_action_confirmation
from app.crud.faq import create_faq, delete_faq, find_duplicate_faq, get_faq, list_faqs
from app.crud.faq_phrasing import (
    PhrasingError,
    create_phrasing,
    delete_phrasing,
    get_phrasing,
    list_phrasings,
    update_phrasing,
)
from app.db.session import get_db
from app.db.vec_store import FAQ_PHRASING_VEC_TABLE, FAQ_QUESTION_VEC_TABLE, FAQ_VEC_TABLE
from app.models.faq import FAQEntry
from app.models.user import User
from app.rag.reindex import embed_entry
from app.schemas.admin import DangerousActionConfirm
from app.schemas.common import PaginatedResponse
from app.schemas.faq import (
    FAQCreate,
    FAQOut,
    FAQPhrasingCreate,
    FAQPhrasingOut,
    FAQPhrasingUpdate,
    FAQUpdate,
)
from app.services.ai_usage import FEATURE_FAQ_DEDUP, feature_context
from app.services.uploads import delete_unreferenced_uploads

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
    question_vector: list[float] | None = None
    try:
        embedding_engine = await get_embedding_engine(db)
        with feature_context(FEATURE_FAQ_DEDUP):
            [question_vector] = await embedding_engine.embed([payload.question])
    except AIEngineError:
        pass  # falls back to the exact-text duplicate check below

    duplicate = await find_duplicate_faq(db, payload.question, question_vector)
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'A FAQ for this question already exists: "{duplicate.question}"',
        )

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


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_all_faqs(
    payload: DangerousActionConfirm,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_dangerous_action_confirmation),
):
    all_image_urls = [
        url
        for (image_urls,) in (await db.execute(select(FAQEntry.image_urls))).all()
        for url in (image_urls or [])
    ]
    await db.execute(text(f"DELETE FROM {FAQ_VEC_TABLE}"))
    await db.execute(text(f"DELETE FROM {FAQ_QUESTION_VEC_TABLE}"))
    await db.execute(text(f"DELETE FROM {FAQ_PHRASING_VEC_TABLE}"))  # phrasing rows go by ON DELETE CASCADE
    await db.execute(FAQEntry.__table__.delete())
    await db.commit()
    await delete_unreferenced_uploads(db, all_image_urls)


@router.put("/{faq_id}", response_model=FAQOut)
async def update(faq_id: int, payload: FAQUpdate, db: AsyncSession = Depends(get_db)):
    entry = await get_faq(db, faq_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ entry not found")

    if "question" in payload.model_fields_set and payload.question is not None:
        question_vector: list[float] | None = None
        try:
            embedding_engine = await get_embedding_engine(db)
            with feature_context(FEATURE_FAQ_DEDUP):
                [question_vector] = await embedding_engine.embed([payload.question])
        except AIEngineError:
            pass  # falls back to the exact-text duplicate check below

        duplicate = await find_duplicate_faq(db, payload.question, question_vector, exclude_id=faq_id)
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'A FAQ for this question already exists: "{duplicate.question}"',
            )

    old_image_urls = list(entry.image_urls or [])
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

    if "image_urls" in payload.model_fields_set:
        removed = set(old_image_urls) - set(entry.image_urls or [])
        await delete_unreferenced_uploads(db, removed)

    return entry


@router.delete("/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(faq_id: int, db: AsyncSession = Depends(get_db)):
    entry = await get_faq(db, faq_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ entry not found")
    await delete_faq(db, entry)


# --- reviewed alternate phrasings -------------------------------------------------
# Same access rule as editing the FAQ itself (router-level require_agent_or_admin).
# Only staff create these: nothing in chat or AI output adds a phrasing on its own.


async def _faq_or_404(db: AsyncSession, faq_id: int) -> FAQEntry:
    entry = await get_faq(db, faq_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ entry not found")
    return entry


def _phrasing_http_error(exc: PhrasingError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT if exc.conflict else status.HTTP_400_BAD_REQUEST, detail=str(exc)
    )


@router.get("/{faq_id}/phrasings", response_model=list[FAQPhrasingOut])
async def list_faq_phrasings(faq_id: int, db: AsyncSession = Depends(get_db)):
    await _faq_or_404(db, faq_id)
    return await list_phrasings(db, faq_id)


@router.post("/{faq_id}/phrasings", response_model=FAQPhrasingOut, status_code=status.HTTP_201_CREATED)
async def add_faq_phrasing(
    faq_id: int,
    payload: FAQPhrasingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_agent_or_admin),
):
    faq = await _faq_or_404(db, faq_id)
    try:
        return await create_phrasing(db, faq, payload.phrasing, created_by_id=user.id)
    except PhrasingError as exc:
        raise _phrasing_http_error(exc) from exc


@router.patch("/{faq_id}/phrasings/{phrasing_id}", response_model=FAQPhrasingOut)
async def edit_faq_phrasing(
    faq_id: int, phrasing_id: int, payload: FAQPhrasingUpdate, db: AsyncSession = Depends(get_db)
):
    faq = await _faq_or_404(db, faq_id)
    entry = await get_phrasing(db, faq_id, phrasing_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phrasing not found")
    try:
        return await update_phrasing(db, faq, entry, payload.phrasing, payload.enabled)
    except PhrasingError as exc:
        raise _phrasing_http_error(exc) from exc


@router.delete("/{faq_id}/phrasings/{phrasing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_faq_phrasing(faq_id: int, phrasing_id: int, db: AsyncSession = Depends(get_db)):
    await _faq_or_404(db, faq_id)
    entry = await get_phrasing(db, faq_id, phrasing_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phrasing not found")
    await delete_phrasing(db, entry)
