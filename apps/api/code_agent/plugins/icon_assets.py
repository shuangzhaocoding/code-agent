from __future__ import annotations

import mimetypes
from pathlib import Path

from code_agent.plugins.base import PluginInfo

ICON_EXTENSIONS = {".png", ".svg", ".jpg", ".jpeg", ".webp", ".ico", ".gif"}
DEFAULT_ICON_NAMES = ("icon.png", "icon.svg", "icon.webp", "icon.jpg", "icon.jpeg", "icon.ico")


def plugin_root(info: PluginInfo) -> Path:
    source = Path(info.source)
    if source.is_dir():
        return source
    return source.parent


def _looks_like_image_ref(value: str) -> bool:
    lower = value.lower()
    if "/" in value or "\\" in value:
        return True
    return any(lower.endswith(ext) for ext in ICON_EXTENSIONS)


def resolve_icon_file(info: PluginInfo) -> Path | None:
    """Resolve a local icon file under the plugin directory."""
    root = plugin_root(info).resolve()
    raw = (info.icon or "").strip()
    candidates: list[Path] = []
    if raw and not raw.startswith(("http://", "https://")) and _looks_like_image_ref(raw):
        candidates.append(root / raw)
    elif not raw:
        for name in DEFAULT_ICON_NAMES:
            candidates.append(root / name)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved == root or not str(resolved).startswith(str(root)):
            continue
        if resolved.is_file():
            return resolved
    return None


def resolve_icon_url(info: PluginInfo) -> str | None:
    explicit = (info.icon_url or "").strip()
    if explicit:
        return explicit
    icon = (info.icon or "").strip()
    if icon.startswith(("http://", "https://")):
        return icon
    if resolve_icon_file(info) is not None:
        from urllib.parse import quote

        return f"/api/plugins/{quote(info.plugin_id, safe='')}/icon"
    return None


def resolve_app_icon_name(info: PluginInfo) -> str | None:
    if resolve_icon_url(info):
        return None
    icon = (info.icon or "").strip()
    return icon or None


def icon_media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"
