from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_agent_or_admin
from app.db.session import get_db
from app.services.excel_import import generate_template, import_workbook

router = APIRouter(prefix="/api/faqs", tags=["imports"], dependencies=[Depends(require_agent_or_admin)])


@router.get("/template")
async def download_template():
    content = generate_template()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=faq_import_template.xlsx"},
    )


@router.post("/import")
async def import_faqs(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    contents = await file.read()
    summary = await import_workbook(db, contents)
    return {
        "created": summary.created,
        "skipped": summary.skipped,
        "failed": summary.failed,
        "errors": [{"row": e.row_number, "reason": e.reason} for e in summary.errors],
    }
