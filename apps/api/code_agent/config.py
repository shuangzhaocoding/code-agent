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
    return cfg


class Settings:
    def __init__(self) -> None:
        self.reload()

    def reload(self, workspace_root: str | None = None) -> None:
        cfg = _load_yaml(DEFAULT_YAML)
        user_path = Path(cfg.get("paths", {}).get("user_config", "~/.code-agent/config.yaml")).expanduser()
        cfg = _deep_merge(cfg, _load_yaml(user_path))
        if workspace_root:
            ws = Path(workspace_root) / ".code-agent" / "config.yaml"
            cfg = _deep_merge(cfg, _load_yaml(ws))
        cfg = _apply_env(cfg)
        self._cfg = cfg
        self.data_dir = Path(cfg["paths"]["data_dir"]).expanduser()
        self.data_dir.mkdir(parents=True, exist_ok=True)
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
        return f"sqlite://{self.data_dir / 'code_agent.sqlite3'}"

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT


settings = Settings()

SETTINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "agent.max_steps": {
            "type": "integer",
            "title": "Agent 最大步数",
            "minimum": 1,
            "maximum": 200,
            "default": 40,
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
    },
}
