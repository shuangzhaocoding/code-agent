from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_YAML = REPO_ROOT / "config" / "default.yaml"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config {path} must be a mapping")
    return data


def _apply_env(cfg: dict[str, Any]) -> dict[str, Any]:
    host = os.environ.get("CODE_AGENT_HOST")
    port = os.environ.get("CODE_AGENT_PORT")
    if host:
        cfg.setdefault("server", {})["host"] = host
    if port:
        cfg.setdefault("server", {})["port"] = int(port)
    data_dir = os.environ.get("CODE_AGENT_DATA_DIR")
    if data_dir:
        cfg.setdefault("paths", {})["data_dir"] = data_dir
    extra = os.environ.get("CODE_AGENT_SYSTEM_PROMPT")
    if extra:
        cfg.setdefault("agent", {})["system_prompt_extra"] = extra
    shell = os.environ.get("CODE_AGENT_SHELL")
    if shell:
        cfg.setdefault("terminal", {})["shell"] = shell
    dev_ui = os.environ.get("CODE_AGENT_DEV_UI_PORT")
    if dev_ui:
        cfg.setdefault("server", {})["dev_ui_port"] = int(dev_ui)
    uploads_dir = os.environ.get("CODE_AGENT_UPLOADS_DIR")
    if uploads_dir:
        cfg.setdefault("uploads", {})["dir"] = uploads_dir
    profile = os.environ.get("CODE_AGENT_RUNTIME_PROFILE")
    if profile:
        cfg.setdefault("runtime", {})["profile"] = profile
    pg = os.environ.get("CODE_AGENT_POSTGRES_URL")
    if pg:
        cfg.setdefault("storage", {})["postgres_url"] = pg
        cfg.setdefault("storage", {})["database"] = "postgres"
    redis = os.environ.get("CODE_AGENT_REDIS_URL")
    if redis:
        cfg.setdefault("storage", {})["redis_url"] = redis
        cfg.setdefault("storage", {})["events"] = "redis"
    return cfg


def _resolve_uploads_dir(cfg: dict[str, Any]) -> Path:
    raw = cfg.get("uploads", {}).get("dir", "uploads")
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def default_user_config_path() -> Path:
    cfg = _load_yaml(DEFAULT_YAML)
    return Path(cfg.get("paths", {}).get("user_config", "~/.code-agent/config.yaml")).expanduser()


def user_config_template() -> str:
    template = REPO_ROOT / "config" / "user.yaml.example"
    if template.is_file():
        return template.read_text(encoding="utf-8")
    return (
        "runtime:\n  profile: split\n  terminal:\n    mode: standalone\n  preview:\n    mode: standalone\n"
        "storage:\n  database: sqlite\n  events: sqlite\n  checkpoint: sqlite\n"
    )


def describe_user_config(path: Path | None = None) -> dict[str, Any]:
    target = path or default_user_config_path()
    if not target.is_file():
        return {"path": str(target), "exists": False}
    cfg = _load_yaml(target)
    runtime = cfg.get("runtime") if isinstance(cfg.get("runtime"), dict) else {}
    storage = cfg.get("storage") if isinstance(cfg.get("storage"), dict) else {}
    return {
        "path": str(target),
        "exists": True,
        "profile": runtime.get("profile", "split"),
        "terminal_mode": (runtime.get("terminal") or {}).get("mode", "standalone")
        if isinstance(runtime.get("terminal"), dict)
        else "standalone",
        "preview_mode": (runtime.get("preview") or {}).get("mode", "standalone")
        if isinstance(runtime.get("preview"), dict)
        else "standalone",
        "storage_database": storage.get("database", "sqlite"),
        "storage_events": storage.get("events", "sqlite"),
    }


def ensure_user_config(
    path: Path | None = None,
    *,
    quiet: bool = False,
    force: bool = False,
) -> tuple[Path, bool]:
    """Create ~/.code-agent/config.yaml from template on first run. Returns (path, created)."""
    target = path or default_user_config_path()
    if target.is_file() and not force:
        return target, False
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and force:
        backup = target.with_suffix(".yaml.bak")
        backup.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        if not quiet:
            print(f"Backed up existing config: {backup}")
    target.write_text(user_config_template(), encoding="utf-8")
    if not quiet:
        print(f"{'Reset' if force else 'Created'} user config: {target}")
    return target, True


class Settings:
    def __init__(self) -> None:
        self.reload()

    def reload(self, workspace_root: str | None = None) -> None:
        cfg = _load_yaml(DEFAULT_YAML)
        user_path = Path(cfg.get("paths", {}).get("user_config", "~/.code-agent/config.yaml")).expanduser()
        ensure_user_config(user_path, quiet=True)
        cfg = _deep_merge(cfg, _load_yaml(user_path))
        if workspace_root:
            ws = Path(workspace_root) / ".code-agent" / "config.yaml"
            cfg = _deep_merge(cfg, _load_yaml(ws))
        cfg = _apply_env(cfg)
        self._cfg = cfg
        self.data_dir = Path(cfg["paths"]["data_dir"]).expanduser()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir = _resolve_uploads_dir(cfg)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir.parent / "plugins").mkdir(parents=True, exist_ok=True)
        (self.data_dir.parent / "skills").mkdir(parents=True, exist_ok=True)

    def get(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self._cfg
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def raw(self) -> dict[str, Any]:
        return deepcopy(self._cfg)

    @property
    def db_url(self) -> str:
        from code_agent.storage.backends import resolve_database_url

        return resolve_database_url()

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT

    def resolve_static_dir(self) -> Path | None:
        raw = self.get("server.static_dir", "auto")
        token = "auto" if raw is None else str(raw).strip().lower()
        if token in {"false", "off", "none", "0"}:
            return None
        if token in {"auto", "true", "on", "1", ""}:
            dist = REPO_ROOT / "apps" / "web" / "dist"
            return dist if dist.is_dir() else None
        path = Path(str(raw)).expanduser()
        if not path.is_absolute():
            path = REPO_ROOT / path
        return path if path.is_dir() else None


def user_config_path(cfg: dict[str, Any] | None = None) -> Path:
    base = cfg if cfg is not None else settings._cfg
    return Path(base.get("paths", {}).get("user_config", "~/.code-agent/config.yaml")).expanduser()


def merge_user_config(section: str, values: dict[str, Any], *, cfg: dict[str, Any] | None = None) -> Path:
    """Merge a config section into ~/.code-agent/config.yaml (creates file if missing)."""
    path = user_config_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_yaml(path)
    bucket = existing.setdefault(section, {})
    if not isinstance(bucket, dict):
        bucket = {}
        existing[section] = bucket
    for key, value in values.items():
        if value is None or value == "":
            bucket.pop(key, None)
        else:
            bucket[key] = value
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(existing, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return path


STORAGE_SETTING_KEYS = frozenset(
    {
        "storage.database",
        "storage.events",
        "storage.checkpoint",
        "storage.postgres_url",
        "storage.redis_url",
        "storage.checkpoint_postgres_url",
    }
)

SETTINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent.max_steps": {
            "type": "integer",
            "title": "Agent 最大步数",
            "minimum": 1,
            "maximum": 200,
            "default": 80,
        },
        "agent.tool_timeout_sec": {
            "type": "integer",
            "title": "单工具超时（秒）",
            "default": 90,
        },
        "agent.run_timeout_sec": {
            "type": "integer",
            "title": "单次 Run 超时（秒）",
            "default": 900,
        },
        "agent.system_prompt_extra": {
            "type": "string",
            "title": "附加系统提示",
            "format": "textarea",
            "default": "",
        },
        "agent.default_mode": {
            "type": "string",
            "title": "默认模式",
            "enum": ["ask", "agent", "plan"],
            "default": "agent",
        },
        "policy.auto_run": {
            "type": "string",
            "title": "自动运行级别",
            "enum": ["manual", "sandbox", "full"],
            "default": "sandbox",
        },
        "terminal.shell": {
            "type": "string",
            "title": "终端 Shell",
            "default": "/bin/bash",
        },
        "llm.default_temperature": {
            "type": "number",
            "title": "默认 temperature",
            "minimum": 0,
            "maximum": 2,
            "default": 0.2,
        },
        "ui.theme": {
            "type": "string",
            "title": "主题",
            "enum": ["dark", "light"],
            "default": "dark",
        },
        "ui.font_size": {
            "type": "integer",
            "title": "界面字号",
            "default": 13,
        },
        "ui.send_on_enter": {
            "type": "boolean",
            "title": "Enter 发送",
            "default": True,
        },
        "storage.database": {
            "type": "string",
            "title": "主数据库",
            "enum": ["sqlite", "postgres"],
            "default": "sqlite",
            "requires_restart": True,
        },
        "storage.events": {
            "type": "string",
            "title": "事件总线",
            "enum": ["sqlite", "redis"],
            "default": "sqlite",
            "requires_restart": True,
        },
        "storage.checkpoint": {
            "type": "string",
            "title": "Checkpoint 存储",
            "enum": ["sqlite", "postgres"],
            "default": "sqlite",
            "requires_restart": True,
        },
        "storage.postgres_url": {
            "type": "string",
            "title": "PostgreSQL 连接 URL",
            "format": "password",
            "default": "",
            "example": "postgres://user:pass@127.0.0.1:5432/code_agent",
            "requires_restart": True,
        },
        "storage.redis_url": {
            "type": "string",
            "title": "Redis 连接 URL",
            "format": "password",
            "default": "",
            "example": "redis://127.0.0.1:6379/0",
            "requires_restart": True,
        },
        "storage.checkpoint_postgres_url": {
            "type": "string",
            "title": "Checkpoint PostgreSQL URL（可选）",
            "format": "password",
            "default": "",
            "example": "postgres://user:pass@127.0.0.1:5432/code_agent_checkpoints",
            "requires_restart": True,
        },
    },
}


settings = Settings()
