from __future__ import annotations

import json
import mimetypes
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from code_agent.config import settings

router = APIRouter(prefix="/api/decor", tags=["decor"])

_SAFE_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_PET_STATUSES = ("idle", "busy", "waiting", "success", "error")
_MAX_BYTES = 20 * 1024 * 1024
_MAX_WALLPAPERS = 12
_MAX_PETS = 12
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".apng", ".bmp"}


def decor_dir() -> Path:
    root = settings.data_dir / "decor"
    (root / "wallpapers").mkdir(parents=True, exist_ok=True)
    (root / "pets").mkdir(parents=True, exist_ok=True)
    return root


def _wallpapers_manifest() -> Path:
    return decor_dir() / "wallpapers.json"


def _pets_manifest() -> Path:
    return decor_dir() / "pets.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_id(value: str, *, label: str = "id") -> str:
    text = (value or "").strip()
    if not _SAFE_ID.match(text):
        raise HTTPException(status_code=400, detail={"code": "decor.invalid_id", "message": f"Invalid {label}"})
    return text


def _ext_for(filename: str | None, content_type: str | None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in _IMAGE_EXTS:
        return ".jpg" if ext == ".jpeg" else ext
    guessed = mimetypes.guess_extension(content_type or "") or ""
    if guessed == ".jpe":
        guessed = ".jpg"
    if guessed in _IMAGE_EXTS:
        return guessed
    return ".jpg"


def _wallpaper_url(file_name: str) -> str:
    path = decor_dir() / "wallpapers" / file_name
    rev = ""
    try:
        if path.is_file():
            rev = str(int(path.stat().st_mtime_ns))
    except OSError:
        rev = ""
    base = f"/api/decor/files/wallpapers/{file_name}"
    return f"{base}?v={rev}" if rev else base


def _pet_image_url(pet_id: str, file_name: str) -> str:
    path = decor_dir() / "pets" / pet_id / file_name
    rev = ""
    try:
        if path.is_file():
            rev = str(int(path.stat().st_mtime_ns))
    except OSError:
        rev = ""
    base = f"/api/decor/files/pets/{pet_id}/{file_name}"
    return f"{base}?v={rev}" if rev else base


def _serialize_wallpaper(row: dict[str, Any]) -> dict[str, Any]:
    file_name = str(row.get("file") or "")
    return {
        "id": row.get("id"),
        "url": _wallpaper_url(file_name) if file_name else "",
        "mime": row.get("mime") or "image/jpeg",
    }


def _serialize_pet(row: dict[str, Any]) -> dict[str, Any]:
    pet_id = str(row.get("id") or "")
    images: dict[str, Any] = {}
    raw_images = row.get("images") or {}
    if isinstance(raw_images, dict):
        for status, meta in raw_images.items():
            if status not in _PET_STATUSES or not isinstance(meta, dict):
                continue
            file_name = str(meta.get("file") or "")
            if not file_name:
                continue
            images[status] = {
                "url": _pet_image_url(pet_id, file_name),
                "mime": meta.get("mime") or "image/jpeg",
            }
    return {
        "id": pet_id,
        "name": row.get("name") or "Pet",
        "images": images,
    }


def _load_wallpapers() -> list[dict[str, Any]]:
    rows = _read_json(_wallpapers_manifest(), [])
    return rows if isinstance(rows, list) else []


def _save_wallpapers(rows: list[dict[str, Any]]) -> None:
    _write_json(_wallpapers_manifest(), rows)


def _load_pets() -> list[dict[str, Any]]:
    rows = _read_json(_pets_manifest(), [])
    return rows if isinstance(rows, list) else []


def _save_pets(rows: list[dict[str, Any]]) -> None:
    _write_json(_pets_manifest(), rows)


async def _read_image(file: UploadFile) -> tuple[bytes, str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail={"code": "decor.invalid", "message": "Missing filename"})
    content_type = (file.content_type or "").lower()
    if content_type and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail={"code": "decor.not_image", "message": "Not an image"})
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail={"code": "decor.empty", "message": "Empty file"})
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=400, detail={"code": "decor.too_large", "message": "File exceeds 20MB"})
    ext = _ext_for(file.filename, content_type)
    mime = content_type or mimetypes.guess_type(f"x{ext}")[0] or "application/octet-stream"
    return data, ext, mime


@router.get("")
async def get_decor_state():
    return {
        "wallpapers": [_serialize_wallpaper(r) for r in _load_wallpapers() if r.get("id") and r.get("file")],
        "pets": [_serialize_pet(r) for r in _load_pets() if r.get("id")],
        "data_dir": str(decor_dir()),
    }


@router.post("/wallpapers")
async def upload_wallpaper(file: UploadFile = File(...)):
    rows = _load_wallpapers()
    if len(rows) >= _MAX_WALLPAPERS:
        raise HTTPException(status_code=400, detail={"code": "decor.limit", "message": "Wallpaper limit reached"})
    data, ext, mime = await _read_image(file)
    wallpaper_id = f"wp_{uuid.uuid4().hex[:12]}"
    file_name = f"{wallpaper_id}{ext}"
    path = decor_dir() / "wallpapers" / file_name
    path.write_bytes(data)
    row = {"id": wallpaper_id, "file": file_name, "mime": mime}
    rows.append(row)
    _save_wallpapers(rows)
    return _serialize_wallpaper(row)


@router.put("/wallpapers/{wallpaper_id}")
async def replace_wallpaper(wallpaper_id: str, file: UploadFile = File(...)):
    wallpaper_id = _safe_id(wallpaper_id, label="wallpaper_id")
    rows = _load_wallpapers()
    idx = next((i for i, r in enumerate(rows) if r.get("id") == wallpaper_id), -1)
    if idx < 0:
        raise HTTPException(status_code=404, detail={"code": "decor.not_found"})
    data, ext, mime = await _read_image(file)
    old_name = str(rows[idx].get("file") or "")
    if old_name:
        old_path = decor_dir() / "wallpapers" / old_name
        if old_path.is_file():
            old_path.unlink()
    file_name = f"{wallpaper_id}{ext}"
    path = decor_dir() / "wallpapers" / file_name
    path.write_bytes(data)
    rows[idx] = {"id": wallpaper_id, "file": file_name, "mime": mime}
    _save_wallpapers(rows)
    return _serialize_wallpaper(rows[idx])


@router.delete("/wallpapers/{wallpaper_id}")
async def delete_wallpaper(wallpaper_id: str):
    wallpaper_id = _safe_id(wallpaper_id, label="wallpaper_id")
    rows = _load_wallpapers()
    hit = next((r for r in rows if r.get("id") == wallpaper_id), None)
    if not hit:
        raise HTTPException(status_code=404, detail={"code": "decor.not_found"})
    file_name = str(hit.get("file") or "")
    if file_name:
        path = decor_dir() / "wallpapers" / file_name
        if path.is_file():
            path.unlink()
    _save_wallpapers([r for r in rows if r.get("id") != wallpaper_id])
    return {"ok": True}


@router.post("/pets")
async def create_pet(name: str | None = Form(default=None)):
    rows = _load_pets()
    if len(rows) >= _MAX_PETS:
        raise HTTPException(status_code=400, detail={"code": "decor.limit", "message": "Pet limit reached"})
    pet_id = f"pet_{uuid.uuid4().hex[:12]}"
    label = (name or "").strip() or f"Pet {len(rows) + 1}"
    (decor_dir() / "pets" / pet_id).mkdir(parents=True, exist_ok=True)
    row = {"id": pet_id, "name": label, "images": {}}
    rows.append(row)
    _save_pets(rows)
    return _serialize_pet(row)


@router.patch("/pets/{pet_id}")
async def rename_pet(pet_id: str, name: str = Form(...)):
    pet_id = _safe_id(pet_id, label="pet_id")
    rows = _load_pets()
    idx = next((i for i, r in enumerate(rows) if r.get("id") == pet_id), -1)
    if idx < 0:
        raise HTTPException(status_code=404, detail={"code": "decor.not_found"})
    label = (name or "").strip() or rows[idx].get("name") or "Pet"
    rows[idx] = {**rows[idx], "name": label}
    _save_pets(rows)
    return _serialize_pet(rows[idx])


@router.delete("/pets/{pet_id}")
async def delete_pet(pet_id: str):
    pet_id = _safe_id(pet_id, label="pet_id")
    rows = _load_pets()
    hit = next((r for r in rows if r.get("id") == pet_id), None)
    if not hit:
        raise HTTPException(status_code=404, detail={"code": "decor.not_found"})
    pet_dir = decor_dir() / "pets" / pet_id
    if pet_dir.is_dir():
        for child in pet_dir.iterdir():
            if child.is_file():
                child.unlink()
        try:
            pet_dir.rmdir()
        except OSError:
            pass
    _save_pets([r for r in rows if r.get("id") != pet_id])
    return {"ok": True}


@router.post("/pets/{pet_id}/images/{status}")
async def upload_pet_image(pet_id: str, status: str, file: UploadFile = File(...)):
    pet_id = _safe_id(pet_id, label="pet_id")
    status = (status or "").strip().lower()
    if status not in _PET_STATUSES:
        raise HTTPException(status_code=400, detail={"code": "decor.invalid_status", "message": "Invalid status"})
    rows = _load_pets()
    idx = next((i for i, r in enumerate(rows) if r.get("id") == pet_id), -1)
    if idx < 0:
        raise HTTPException(status_code=404, detail={"code": "decor.not_found"})
    data, ext, mime = await _read_image(file)
    pet_dir = decor_dir() / "pets" / pet_id
    pet_dir.mkdir(parents=True, exist_ok=True)
    images = dict(rows[idx].get("images") or {})
    old = images.get(status) if isinstance(images.get(status), dict) else None
    if isinstance(old, dict) and old.get("file"):
        old_path = pet_dir / str(old["file"])
        if old_path.is_file():
            old_path.unlink()
    file_name = f"{status}{ext}"
    (pet_dir / file_name).write_bytes(data)
    images[status] = {"file": file_name, "mime": mime}
    rows[idx] = {**rows[idx], "images": images}
    _save_pets(rows)
    return _serialize_pet(rows[idx])


@router.delete("/pets/{pet_id}/images/{status}")
async def delete_pet_image(pet_id: str, status: str):
    pet_id = _safe_id(pet_id, label="pet_id")
    status = (status or "").strip().lower()
    if status not in _PET_STATUSES:
        raise HTTPException(status_code=400, detail={"code": "decor.invalid_status"})
    rows = _load_pets()
    idx = next((i for i, r in enumerate(rows) if r.get("id") == pet_id), -1)
    if idx < 0:
        raise HTTPException(status_code=404, detail={"code": "decor.not_found"})
    images = dict(rows[idx].get("images") or {})
    meta = images.pop(status, None)
    if isinstance(meta, dict) and meta.get("file"):
        path = decor_dir() / "pets" / pet_id / str(meta["file"])
        if path.is_file():
            path.unlink()
    rows[idx] = {**rows[idx], "images": images}
    _save_pets(rows)
    return _serialize_pet(rows[idx])


@router.get("/files/wallpapers/{file_name}")
async def get_wallpaper_file(file_name: str):
    if ".." in file_name or "/" in file_name or "\\" in file_name:
        raise HTTPException(status_code=400, detail={"code": "decor.invalid_path"})
    path = decor_dir() / "wallpapers" / file_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail={"code": "decor.not_found"})
    mime = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=mime)


@router.get("/files/pets/{pet_id}/{file_name}")
async def get_pet_file(pet_id: str, file_name: str):
    pet_id = _safe_id(pet_id, label="pet_id")
    if ".." in file_name or "/" in file_name or "\\" in file_name:
        raise HTTPException(status_code=400, detail={"code": "decor.invalid_path"})
    path = decor_dir() / "pets" / pet_id / file_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail={"code": "decor.not_found"})
    mime = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=mime)
