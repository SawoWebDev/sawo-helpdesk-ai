from fastapi import APIRouter, Depends, File, UploadFile

from app.core.deps import require_agent_or_admin
from app.services.uploads import save_upload

router = APIRouter(prefix="/api/uploads", tags=["uploads"], dependencies=[Depends(require_agent_or_admin)])


@router.post("")
async def upload_file(file: UploadFile = File(...)):
    url = await save_upload(file)
    return {"url": url}
