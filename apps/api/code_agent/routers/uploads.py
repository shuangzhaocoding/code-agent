from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from code_agent.config import settings

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


def _ensure_root() -> Path:
    return settings.uploads_dir


@router.post("")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail={"code": "upload.invalid", "message": "Missing filename"})
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail={"code": "upload.empty", "message": "Empty file"})
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail={"code": "upload.too_large", "message": "File exceeds 20MB"})

    root = _ensure_root()
    ext = Path(file.filename).suffix.lower()
    file_id = uuid.uuid4().hex
    stored = root / f"{file_id}{ext}"
    stored.write_bytes(data)

    mime = file.content_type or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
    return {
        "name": file.filename,
        "url": f"/api/uploads/{file_id}{ext}",
        "size": len(data),
        "type": mime,
    }


@router.get("/{file_name}")
async def get_upload(file_name: str):
    if ".." in file_name or "/" in file_name or "\\" in file_name:
        raise HTTPException(status_code=400, detail={"code": "upload.invalid_path"})
    root = _ensure_root()
    path = root / file_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail={"code": "upload.not_found"})
    mime = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=mime)
