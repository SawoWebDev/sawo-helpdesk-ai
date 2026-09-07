from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIEngineError
from app.core.deps import require_admin
from app.db.session import get_db
from app.rag.reindex import reindex_all

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/reindex")
async def reindex(db: AsyncSession = Depends(get_db)):
    try:
        count = await reindex_all(db)
    except AIEngineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return {"reindexed": count}
