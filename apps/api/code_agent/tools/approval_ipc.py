"""Cross-process HITL approval decisions (API gateway ↔ agent worker).

In split mode the worker owns in-memory waiters while the API process receives
``POST /approvals``. Decisions are written under ``data_dir/approvals/`` and
polled by the worker.
"""

from __future__ import annotations

import json
from pathlib import Path

from code_agent.config import settings


def _run_dir(run_id: str) -> Path:
    path = Path(settings.data_dir) / "approvals" / str(run_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def register_pending(run_id: str, approval_ids: list[str]) -> None:
    path = _run_dir(run_id) / "pending.json"
    path.write_text(json.dumps({"approval_ids": list(approval_ids)}, ensure_ascii=False), encoding="utf-8")


def list_pending(run_id: str) -> list[str]:
    path = _run_dir(run_id) / "pending.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    ids = data.get("approval_ids") if isinstance(data, dict) else None
    if not isinstance(ids, list):
        return []
    return [str(x) for x in ids if x]


def put_decision(run_id: str, approval_id: str, allowed: bool) -> None:
    path = _run_dir(run_id) / f"{approval_id}.json"
    path.write_text(json.dumps({"allowed": bool(allowed)}, ensure_ascii=False), encoding="utf-8")


def take_decision(run_id: str, approval_id: str) -> bool | None:
    path = _run_dir(run_id) / f"{approval_id}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        allowed = bool(data.get("allowed")) if isinstance(data, dict) else False
    except (OSError, json.JSONDecodeError):
        allowed = False
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return allowed


def clear_run(run_id: str) -> None:
    root = Path(settings.data_dir) / "approvals" / str(run_id)
    if not root.is_dir():
        return
    for child in root.iterdir():
        try:
            child.unlink()
        except OSError:
            pass
    try:
        root.rmdir()
    except OSError:
        pass
