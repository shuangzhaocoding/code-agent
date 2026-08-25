"""Unit tests for multimodal image helpers."""

from __future__ import annotations

import base64
from pathlib import Path

from code_agent.llm.capabilities import _looks_vision
from code_agent.llm.vision import (
    IMAGE_TOKEN_ESTIMATE,
    build_user_content,
    collect_image_parts,
    detect_image_mime,
    file_to_image_part,
)


def test_detect_image_mime_magic():
    assert detect_image_mime(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert detect_image_mime(b"\x89PNG\r\n\x1a\nrest") == "image/png"
    assert detect_image_mime(b"GIF89a....") == "image/gif"
    assert detect_image_mime(b"RIFF....WEBP....") == "image/webp"
    assert detect_image_mime(b"not-an-image") is None


def test_looks_vision_deepseek():
    assert _looks_vision("deepseek-v4-flash-vision-exp")
    assert _looks_vision("deepseek-vl2")
    assert not _looks_vision("deepseek-chat")
    assert not _looks_vision("deepseek-reasoner")


def test_build_user_content_multimodal(tmp_path: Path, monkeypatch):
    from code_agent.llm import vision as vision_mod

    monkeypatch.setattr(vision_mod, "upload_root", lambda: tmp_path)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    name = "abcd1234.png"
    (tmp_path / name).write_bytes(png)

    files = [{"name": "shot.png", "url": f"/api/uploads/{name}", "size": len(png), "type": "image/png"}]
    content = build_user_content("这张图里有什么？", files, vision=True)
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "这张图里有什么？"}
    assert content[1]["type"] == "image_url"
    url = content[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    raw = base64.b64decode(url.split(",", 1)[1])
    assert raw.startswith(b"\x89PNG")


def test_build_user_content_rejects_without_vision():
    files = [{"name": "a.png", "url": "/api/uploads/a.png", "type": "image/png", "size": 10}]
    content = build_user_content("hi", files, vision=False)
    assert isinstance(content, str)
    assert "不支持视觉" in content


def test_image_only_message(tmp_path: Path, monkeypatch):
    from code_agent.llm import vision as vision_mod

    monkeypatch.setattr(vision_mod, "upload_root", lambda: tmp_path)
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 16
    name = "img.jpg"
    (tmp_path / name).write_bytes(jpeg)
    files = [{"name": "img.jpg", "url": f"/api/uploads/{name}", "type": "image/jpeg", "size": len(jpeg)}]
    content = build_user_content("", files, vision=True)
    assert isinstance(content, list)
    assert len(content) == 1
    assert content[0]["type"] == "image_url"


def test_external_url_part():
    part = file_to_image_part(
        {"name": "remote.jpg", "url": "https://example.com/a.jpg", "type": "image/jpeg", "size": 1},
    )
    assert part is not None
    assert part["image_url"]["url"] == "https://example.com/a.jpg"


def test_collect_skips_non_images():
    assert collect_image_parts([{"name": "a.txt", "url": "https://x/a.txt", "type": "text/plain"}]) == []


def test_image_token_cap():
    assert IMAGE_TOKEN_ESTIMATE == 384


def test_turn_needs_vision_current_message():
    from code_agent.llm.vision import turn_needs_vision

    files = [{"name": "a.png", "url": "/api/uploads/a.png", "type": "image/png"}]
    assert turn_needs_vision(current_text="你好", current_files=files, history_has_images=False)
    assert not turn_needs_vision(current_text="你好", current_files=[], history_has_images=True)
    assert turn_needs_vision(
        current_text="这张图里有什么？",
        current_files=[],
        history_has_images=True,
    )
    assert not turn_needs_vision(
        current_text="这张图里有什么？",
        current_files=[],
        history_has_images=False,
    )
