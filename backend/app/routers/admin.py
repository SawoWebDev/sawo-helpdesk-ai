from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.core.deps import require_admin, require_dangerous_action_confirmation
from app.db.session import get_db
from app.db.vec_store import FAQ_PHRASING_VEC_TABLE, FAQ_QUESTION_VEC_TABLE, FAQ_VEC_TABLE, VAULT_VEC_TABLE
from app.models.category import Category
from app.models.chat_log import ChatLog
from app.models.faq import FAQEntry
from app.models.harvest_job import HarvestJob
from app.models.harvest_source import HarvestSource
from app.models.unanswered import UnansweredQuestion
from app.models.user import User
from app.models.vault_entry import VaultEntry
from app.rag.reindex import reindex_all
from app.rag.vault_reindex import reindex_all_vault
from app.schemas.admin import DangerousActionConfirm
from app.services.uploads import delete_unreferenced_uploads

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/reindex")
async def reindex(db: AsyncSession = Depends(get_db)):
    try:
        faq_count = await reindex_all(db)
        vault_count = await reindex_all_vault(db)
    except AIEngineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"reindexed": faq_count, "reindexed_vault": vault_count}


@router.post("/purge-all", status_code=status.HTTP_204_NO_CONTENT)
async def purge_all_data(
    payload: DangerousActionConfirm,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_dangerous_action_confirmation),
):
    """One confirmation instead of five: wipes every FAQ, Library/Vault
    entry, harvest source/job, category, chat log, and unanswered question —
    the same tables the individual "Reset" actions on the Data Management
    tab each clear on their own. Settings (including the OpenRouter keys),
    user accounts, and AI usage/billing history are left untouched."""
    all_image_urls = [
        url
        for (image_urls,) in (await db.execute(select(FAQEntry.image_urls))).all()
        for url in (image_urls or [])
    ]

    await db.execute(text(f"DELETE FROM {VAULT_VEC_TABLE}"))
    await db.execute(VaultEntry.__table__.delete())
    await db.execute(HarvestSource.__table__.delete())
    await db.execute(HarvestJob.__table__.delete())

    await db.execute(text(f"DELETE FROM {FAQ_VEC_TABLE}"))
    await db.execute(text(f"DELETE FROM {FAQ_QUESTION_VEC_TABLE}"))
    await db.execute(text(f"DELETE FROM {FAQ_PHRASING_VEC_TABLE}"))  # phrasing rows go by ON DELETE CASCADE
    await db.execute(FAQEntry.__table__.delete())

    await db.execute(Category.__table__.delete())
    await db.execute(ChatLog.__table__.delete())
    await db.execute(UnansweredQuestion.__table__.delete())

    await db.commit()
    await delete_unreferenced_uploads(db, all_image_urls)
