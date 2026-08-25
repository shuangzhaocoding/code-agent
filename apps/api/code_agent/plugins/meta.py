from __future__ import annotations

from typing import Any

from code_agent.plugins.base import PluginInfo

META_FIELDS = (
    "author",
    "homepage",
    "repository",
    "license",
    "icon",
    "icon_url",
    "accent",
)

_MODULE_ALIASES = {
    "author": "PLUGIN_AUTHOR",
    "homepage": "PLUGIN_HOMEPAGE",
    "repository": "PLUGIN_REPOSITORY",
    "license": "PLUGIN_LICENSE",
    "icon": "PLUGIN_ICON",
    "icon_url": "PLUGIN_ICON_URL",
    "accent": "PLUGIN_ACCENT",
    "keywords": "PLUGIN_KEYWORDS",
}


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_keywords(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace(";", ",").split(",")]
        return tuple(part for part in parts if part)
    if isinstance(value, (list, tuple)):
        return tuple(str(part).strip() for part in value if str(part).strip())
    return ()


def meta_from_mapping(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {}
    out: dict[str, Any] = {}
    for key in META_FIELDS:
        value = _clean_str(data.get(key))
        if value is not None:
            out[key] = value
    keywords = _clean_keywords(data.get("keywords"))
    if keywords:
        out["keywords"] = keywords
    return out


def meta_from_module(module: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, attr in _MODULE_ALIASES.items():
        if hasattr(module, attr):
            data[key] = getattr(module, attr)
    return meta_from_mapping(data)


def apply_plugin_meta(
    info: PluginInfo,
    *,
    meta: dict[str, Any] | None = None,
    module: Any | None = None,
) -> None:
    merged = meta_from_mapping(meta)
    if module is not None:
        merged = {**meta_from_module(module), **merged}
    for key, value in merged.items():
        setattr(info, key, value)


def plugin_meta_public(info: PluginInfo) -> dict[str, Any]:
    from code_agent.plugins.icon_assets import resolve_app_icon_name, resolve_icon_url

    return {
        "author": info.author or None,
        "homepage": info.homepage or None,
        "repository": info.repository or None,
        "license": info.license or None,
        "icon": resolve_app_icon_name(info),
        "icon_url": resolve_icon_url(info),
        "accent": info.accent or None,
        "keywords": list(info.keywords),
    }
