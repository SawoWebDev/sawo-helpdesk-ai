from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin
from app.db.session import get_db
from app.services.kb_export import ImportSummary, export_knowledge_base, import_knowledge_base

router = APIRouter(prefix="/api/knowledge-base", tags=["knowledge-base"], dependencies=[Depends(require_admin)])


def _summary_dict(summary: ImportSummary) -> dict:
    return {
        "created": summary.created,
        "skipped": summary.skipped,
        "failed": summary.failed,
        "errors": [{"row": e.row_number, "reason": e.reason} for e in summary.errors],
    }


@router.get("/export")
async def export_knowledge_base_endpoint(db: AsyncSession = Depends(get_db)):
    content = await export_knowledge_base(db)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=knowledge_base_export.xlsx"},
    )


@router.post("/import")
async def import_knowledge_base_endpoint(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    contents = await file.read()
    summary = await import_knowledge_base(db, contents)
    return {"faqs": _summary_dict(summary.faqs), "library": _summary_dict(summary.library)}
