"""Image helpers for multimodal (vision) LLM requests.

DeepSeek vision (and OpenAI-compatible providers) accept user-message content as a
list of text / image_url blocks. Format is detected from file bytes, not the
declared MIME type.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from code_agent.config import settings

# DeepSeek: JPEG / PNG / GIF / WebP only for vision inputs.
_SUPPORTED_IMAGE_MIMES = frozenset({"image/jpeg", "image/png", "image/gif", "image/webp"})
# Inline base64 / external URL limit (DeepSeek docs); Files API allows more.
_MAX_INLINE_IMAGE_BYTES = 32 * 1024 * 1024
# DeepSeek caps image tokens ~384 after resize; use for context estimates.
IMAGE_TOKEN_ESTIMATE = 384


def detect_image_mime(data: bytes) -> str | None:
    """Detect image MIME from magic bytes (authoritative over filename/headers)."""
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def is_image_file_meta(item: dict[str, Any] | None) -> bool:
    if not item:
        return False
    mime = str(item.get("type") or "").lower().split(";")[0].strip()
    if mime in _SUPPORTED_IMAGE_MIMES or mime.startswith("image/"):
        return True
    name = str(item.get("name") or item.get("url") or "")
    ext = Path(name).suffix.lower()
    return ext in {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def upload_root() -> Path:
    root = Path(settings.get("uploads.dir") or ".code-agent-uploads")
    if not root.is_absolute():
        root = Path.cwd() / root
    return root


def resolve_upload_path(url: str) -> Path | None:
    """Map `/api/uploads/{file}` (or bare filename) to a local path."""
    raw = (url or "").strip()
    if not raw:
        return None
    path = urlparse(raw).path if "://" in raw or raw.startswith("/") else raw
    name = Path(unquote(path)).name
    if not name or name in {".", ".."} or "/" in name or "\\" in name or ".." in name:
        return None
    candidate = upload_root() / name
    if candidate.is_file():
        return candidate
    return None


def _data_url(mime: str, data: bytes) -> str:
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def image_url_part(
    url: str,
    *,
    detail: str = "auto",
) -> dict[str, Any]:
    part: dict[str, Any] = {"type": "image_url", "image_url": {"url": url}}
    if detail:
        part["image_url"]["detail"] = detail
    return part


def file_to_image_part(
    item: dict[str, Any],
    *,
    detail: str = "auto",
) -> dict[str, Any] | None:
    """Build an OpenAI-compatible image_url content part from upload metadata.

    Prefers local upload bytes as base64 data URLs. Falls back to http(s) URLs.
    Returns None if the item is not a supported image or cannot be loaded.
    """
    url = str(item.get("url") or "").strip()
    declared = str(item.get("type") or "").lower().split(";")[0].strip()

    local = resolve_upload_path(url)
    if local is not None:
        data = local.read_bytes()
        if not data or len(data) > _MAX_INLINE_IMAGE_BYTES:
            return None
        mime = detect_image_mime(data) or declared
        if mime not in _SUPPORTED_IMAGE_MIMES:
            # Try guess from filename as last resort
            guessed = mimetypes.guess_type(str(item.get("name") or local.name))[0]
            mime = guessed if guessed in _SUPPORTED_IMAGE_MIMES else None
        if mime not in _SUPPORTED_IMAGE_MIMES:
            return None
        return image_url_part(_data_url(mime, data), detail=detail)

    if url.startswith(("http://", "https://")):
        if len(url) > 8192:
            return None
        # External URL — provider downloads it. Prefer a known image type.
        if declared and declared not in _SUPPORTED_IMAGE_MIMES and not declared.startswith("image/"):
            if not is_image_file_meta(item):
                return None
        return image_url_part(url, detail=detail)

    return None


def collect_image_parts(
    files: list[dict[str, Any]] | None,
    *,
    detail: str = "auto",
    max_images: int = 600,
) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    for item in files or []:
        if len(parts) >= max_images:
            break
        if not is_image_file_meta(item):
            continue
        part = file_to_image_part(item, detail=detail)
        if part:
            parts.append(part)
    return parts


def message_files(row_blocks: list | None) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for block in row_blocks or []:
        meta = block.get("meta") or {}
        for item in meta.get("files") or []:
            if isinstance(item, dict):
                files.append(item)
    return files


def message_text(row_blocks: list | None) -> str:
    parts: list[str] = []
    for block in row_blocks or []:
        if block.get("type") in {"user.text", "assistant.markdown"} and block.get("text"):
            parts.append(str(block["text"]))
    return "\n".join(parts).strip()


# Phrases that suggest the user is referring to an image already in the thread.
_IMAGE_INTENT_PATTERNS = (
    "这张图",
    "这张图片",
    "图片里",
    "图片中",
    "图里",
    "图中",
    "截图",
    "看图",
    "识图",
    "上面的图",
    "刚才的图",
    "那张图",
    "该图",
    "附图",
    "照片里",
    "描述一下图",
    "图是什么",
    "这个图",
    "此图",
    "ocr",
    "this image",
    "the image",
    "the picture",
    "the screenshot",
    "in the image",
    "in the picture",
    "look at the image",
    "describe the image",
    "what.*in.*(image|picture|screenshot)",
)


def text_refers_to_image(text: str | None) -> bool:
    """Heuristic: does this text ask about / refer to an image?"""
    raw = (text or "").strip().lower()
    if not raw:
        return False
    for token in _IMAGE_INTENT_PATTERNS:
        if token.startswith("what.*") or ".*" in token:
            import re

            if re.search(token, raw, re.IGNORECASE):
                return True
        elif token.lower() in raw:
            return True
    return False


def turn_needs_vision(
    *,
    current_text: str,
    current_files: list[dict[str, Any]] | None,
    history_has_images: bool,
) -> bool:
    """Decide whether this turn should use a vision model.

    Priority:
    1. Current message attaches images → yes
    2. Current text refers to images AND context has prior images → yes
    3. Otherwise (e.g. plain「你好」) → no, even if history once had images
    """
    if any(is_image_file_meta(item) for item in (current_files or [])):
        return True
    if history_has_images and text_refers_to_image(current_text):
        return True
    return False


def build_user_content(
    text: str,
    files: list[dict[str, Any]] | None,
    *,
    vision: bool,
    detail: str = "auto",
) -> str | list[dict[str, Any]] | None:
    """Return LangChain HumanMessage content: str or multimodal list.

    When vision is False and images are attached, returns plain text with a note
    (caller should prefer failing the run instead).
    """
    text = (text or "").strip()
    image_files = [f for f in (files or []) if is_image_file_meta(f)]
    if not vision or not image_files:
        if not text and not image_files:
            return None
        if image_files and not vision:
            names = ", ".join(str(f.get("name") or "image") for f in image_files[:8])
            note = f"[此前消息附带图片：{names}]"
            return f"{text}\n\n{note}".strip() if text else note
        return text or None

    parts: list[dict[str, Any]] = []
    if text:
        parts.append({"type": "text", "text": text})
    parts.extend(collect_image_parts(image_files, detail=detail))
    if not parts:
        return text or None
    # If we had images but none loaded, fall back to text + note
    loaded = sum(1 for p in parts if p.get("type") == "image_url")
    if image_files and loaded == 0:
        names = ", ".join(str(f.get("name") or "image") for f in image_files[:8])
        note = f"[图片加载失败：{names}]"
        if text:
            return f"{text}\n\n{note}"
        return note
    return parts
