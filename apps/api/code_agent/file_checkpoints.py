"""File checkpoints derived from file.diff / file.delete blocks (per run)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from code_agent.conversation_rollback import FileChange, _collect_file_changes, _revert_file_changes
from code_agent.db.models import Conversation, Message, Run, Workspace


def _file_ops_from_messages(messages: list[Message]) -> list[FileChange]:
    return _collect_file_changes(messages)


def _unique_paths_summary(ops: list[FileChange]) -> list[dict[str, Any]]:
    """Latest op per path (ops are newest-first from collector)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for op in ops:
        if op.path in seen:
            continue
        seen.add(op.path)
        out.append(
            {
                "path": op.path,
                "action": op.action,
                "block_type": op.block_type,
                "before_chars": len(op.before or ""),
                "after_chars": len(op.after or ""),
            }
        )
    return out


async def list_conversation_checkpoints(conversation_id: str) -> dict[str, Any]:
    conv = await Conversation.get_or_none(id=conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail={"code": "conversation.not_found"})

    runs = await Run.filter(conversation_id=conversation_id).order_by("-started_at")
    messages = await Message.filter(conversation_id=conversation_id, role="assistant").order_by("sort_key")
    by_run: dict[str, list[Message]] = {}
    for msg in messages:
        if not msg.run_id:
            continue
        by_run.setdefault(str(msg.run_id), []).append(msg)

    checkpoints: list[dict[str, Any]] = []
    for run in runs:
        rid = str(run.id)
        msgs = by_run.get(rid) or []
        ops = _file_ops_from_messages(msgs)
        if not ops:
            continue
        files = _unique_paths_summary(ops)
        checkpoints.append(
            {
                "run_id": rid,
                "status": run.status,
                "mode": run.mode,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "ended_at": run.ended_at.isoformat() if run.ended_at else None,
                "file_count": len(files),
                "files": files,
                "skill_name": (run.model_snapshot or {}).get("skill_name"),
            }
        )

    return {
        "conversation_id": conversation_id,
        "checkpoints": checkpoints,
    }


async def get_run_checkpoint(run_id: str) -> dict[str, Any]:
    run = await Run.get_or_none(id=run_id)
    if not run:
        raise HTTPException(status_code=404, detail={"code": "run.not_found"})
    messages = await Message.filter(run_id=run_id, role="assistant").order_by("sort_key")
    ops = _file_ops_from_messages(messages)
    files = []
    seen: set[str] = set()
    for op in ops:
        if op.path in seen:
            continue
        seen.add(op.path)
        files.append(
            {
                "path": op.path,
                "action": op.action,
                "block_type": op.block_type,
                "before": op.before,
                "after": op.after,
                "before_chars": len(op.before or ""),
                "after_chars": len(op.after or ""),
            }
        )
    return {
        "run_id": run_id,
        "conversation_id": str(run.conversation_id),
        "status": run.status,
        "mode": run.mode,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "file_count": len(files),
        "files": files,
    }


async def restore_run_files(
    run_id: str,
    *,
    mode: str = "run",
    paths: list[str] | None = None,
) -> dict[str, Any]:
    """
    Restore workspace files from checkpoint data.

    mode=run: revert file changes made in this run only.
    mode=to_before: revert this run and all later runs' file changes (keep chat).
    """
    if mode not in {"run", "to_before"}:
        raise HTTPException(status_code=400, detail={"code": "checkpoint.invalid_mode"})

    run = await Run.get_or_none(id=run_id)
    if not run:
        raise HTTPException(status_code=404, detail={"code": "run.not_found"})
    if run.status in {"queued", "running"}:
        raise HTTPException(
            status_code=400,
            detail={"code": "checkpoint.run_active", "message": "Cannot restore while the run is still active"},
        )

    conv = await Conversation.get_or_none(id=run.conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail={"code": "conversation.not_found"})
    ws = await Workspace.get_or_none(id=conv.workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})

    if mode == "run":
        messages = await Message.filter(run_id=run_id, role="assistant").order_by("sort_key")
    else:
        all_msgs = await Message.filter(conversation_id=conv.id, role="assistant").order_by("sort_key")
        # Include this run and any assistant messages that belong to later runs
        # (by started_at of run, or by message sort_key after this run's messages)
        run_msgs = [m for m in all_msgs if str(m.run_id) == run_id]
        if not run_msgs:
            raise HTTPException(status_code=400, detail={"code": "checkpoint.no_files", "message": "No file changes in this run"})
        min_sk = min(m.sort_key for m in run_msgs)
        later_run_ids = {
            str(r.id)
            for r in await Run.filter(conversation_id=conv.id)
            if r.started_at and run.started_at and r.started_at >= run.started_at
        }
        messages = [
            m
            for m in all_msgs
            if (m.run_id and str(m.run_id) in later_run_ids) or m.sort_key >= min_sk
        ]

    ops = _file_ops_from_messages(messages)
    if paths:
        want = {p.strip() for p in paths if p and p.strip()}
        ops = [op for op in ops if op.path in want]
    if not ops:
        raise HTTPException(status_code=400, detail={"code": "checkpoint.no_files", "message": "No file changes to restore"})

    reverted, warnings = await _revert_file_changes(ws, ops)
    return {
        "ok": True,
        "mode": mode,
        "run_id": run_id,
        "files_reverted": len(reverted),
        "reverted_paths": reverted,
        "warnings": warnings,
    }
