import os
import uuid
from typing import Iterable

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.faq import FAQEntry

UPLOAD_URL_PREFIX = "/uploads/"


def _ext(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


async def save_upload(file: UploadFile) -> str:
    ext = _ext(file.filename or "")
    if ext not in settings.allowed_image_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(settings.allowed_image_extensions)}",
        )

    contents = await file.read()
    if len(contents) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds max size of {settings.max_upload_size_bytes} bytes",
        )

    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(settings.upload_dir, safe_name)

    with open(dest_path, "wb") as f:
        f.write(contents)

    return f"{UPLOAD_URL_PREFIX}{safe_name}"


async def delete_unreferenced_uploads(db: AsyncSession, urls: Iterable[str]) -> None:
    """Deletes files under uploads/ that no FAQ entry's image_urls points to
    any more. Only ever touches our own /uploads/... URLs — anything else
    (an admin-pasted external image URL) isn't a file we own, so it's left
    alone. Called after a FAQ's images are removed/replaced or the FAQ
    itself is deleted, since save_upload() otherwise leaves the file behind
    on disk forever with nothing left pointing to it."""
    candidates = {url for url in urls if url.startswith(UPLOAD_URL_PREFIX)}
    if not candidates:
        return

    rows = (await db.execute(select(FAQEntry.image_urls))).scalars().all()
    still_referenced: set[str] = set()
    for image_urls in rows:
        still_referenced.update(image_urls or [])

    for url in candidates - still_referenced:
        filename = url[len(UPLOAD_URL_PREFIX):]
        # Belt-and-suspenders against a URL smuggling a path (e.g.
        # "../../something") past the intended uploads directory.
        if not filename or os.path.basename(filename) != filename:
            continue
        path = os.path.join(settings.upload_dir, filename)
        try:
            os.remove(path)
        except OSError:
            pass
