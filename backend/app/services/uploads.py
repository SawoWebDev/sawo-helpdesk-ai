import os
import uuid

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings


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

    return f"/uploads/{safe_name}"
