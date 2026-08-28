from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from code_agent.db.models import Conversation, Message, Run, RunEvent, Workspace
from code_agent.policy.engine import is_protected
from code_agent.routers.workspaces import _delete_entry_fs, _write_text_file
from code_agent.streaming.run_manager import cancel_run
from code_agent.tools.paths import resolve_in_workspace
from code_agent.async_io import run_sync


@dataclass
class FileChange:
    path: str
    action: str
    before: str
    after: str
    block_type: str
    sort_key: int


async def rollback_conversation_to_message(conversation_id: str, message_id: str, *, mode: str = "to") -> dict:
    conv = await Conversation.get_or_none(id=conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail={"code": "conversation.not_found"})

    anchor = await Message.get_or_none(id=message_id, conversation_id=conversation_id)
    if not anchor:
        raise HTTPException(status_code=404, detail={"code": "message.not_found"})
    if anchor.role != "user":
        raise HTTPException(status_code=400, detail={"code": "rollback.invalid_message", "message": "只能回退到用户消息"})

    ws = await Workspace.get_or_none(id=conv.workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})

    if mode not in {"to", "before"}:
        raise HTTPException(status_code=400, detail={"code": "rollback.invalid_mode", "message": "无效的回退模式"})

    all_messages = await Message.filter(conversation_id=conversation_id).order_by("sort_key")
    cutoff_sort_key = _cutoff_sort_key(anchor, all_messages, mode)
    trailing = [m for m in all_messages if m.sort_key > cutoff_sort_key]
    if not trailing:
        raise HTTPException(
            status_code=400,
            detail={"code": "rollback.nothing_after", "message": "没有可回退的内容"},
        )

    trailing_run_ids = {str(m.run_id) for m in trailing if m.run_id}
    if conv.active_run_id and conv.active_run_id in trailing_run_ids:
        active = await Run.get_or_none(id=conv.active_run_id)
        if active and active.status in {"queued", "running"}:
            await cancel_run(conv.active_run_id)
        conv.active_run_id = None

    for run_id in trailing_run_ids:
        run = await Run.get_or_none(id=run_id)
        if run and run.status in {"queued", "running"}:
            await cancel_run(str(run.id))

    file_ops = _collect_file_changes(trailing)
    reverted_paths, warnings = await _revert_file_changes(ws.root_path, file_ops)

    trailing_ids = [m.id for m in trailing]
    if trailing_run_ids:
        await RunEvent.filter(run_id__in=list(trailing_run_ids)).delete()
        await Run.filter(id__in=list(trailing_run_ids)).delete()
    await Message.filter(id__in=trailing_ids).delete()

    if int(conv.summary_covers_sort_key or 0) > cutoff_sort_key:
        conv.summary = None
        conv.summary_covers_sort_key = 0
        conv.summary_updated_at = None

    conv.active_run_id = None
    await conv.save()

    return {
        "ok": True,
        "mode": mode,
        "cutoff_sort_key": cutoff_sort_key,
        "messages_removed": len(trailing),
        "files_reverted": len(reverted_paths),
        "reverted_paths": reverted_paths,
        "warnings": warnings,
    }


def _cutoff_sort_key(anchor: Message, all_messages: list[Message], mode: str = "to") -> int:
    if mode == "before":
        prev = [m for m in all_messages if m.sort_key < anchor.sort_key]
        if not prev:
            return -1
        return max(m.sort_key for m in prev)
    reply_sk = _assistant_reply_sort_key(anchor, all_messages)
    if reply_sk is not None:
        return reply_sk
    return anchor.sort_key


def _assistant_reply_sort_key(anchor: Message, all_messages: list[Message]) -> int | None:
    """User messages are not linked to run_id; find the assistant reply for this turn."""
    seen_anchor = False
    for msg in all_messages:
        if str(msg.id) == str(anchor.id):
            seen_anchor = True
            continue
        if not seen_anchor:
            continue
        if msg.role == "user":
            return None
        if msg.role == "assistant":
            return msg.sort_key
    return None


def _collect_file_changes(messages: list[Message]) -> list[FileChange]:
    ops: list[FileChange] = []
    for msg in sorted(messages, key=lambda m: m.sort_key, reverse=True):
        blocks = msg.blocks or []
        for block in reversed(blocks):
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "")
            if block_type not in {"file.diff", "file.delete"}:
                continue
            meta = block.get("meta") or {}
            if not isinstance(meta, dict):
                continue
            path = str(meta.get("path") or "").strip()
            if not path:
                continue
            before = meta.get("before")
            after = meta.get("after")
            if before is None and after is None:
                continue
            action = str(meta.get("action") or ("delete" if block_type == "file.delete" else "edit"))
            ops.append(
                FileChange(
                    path=path,
                    action=action,
                    before=str(before) if before is not None else "",
                    after=str(after) if after is not None else "",
                    block_type=block_type,
                    sort_key=msg.sort_key,
                )
            )
    return ops


async def _revert_file_changes(root_path: str, ops: list[FileChange]) -> tuple[list[str], list[str]]:
    reverted: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for op in ops:
        if op.path in seen:
            continue
        seen.add(op.path)

        if is_protected(op.path):
            warnings.append(f"跳过受保护文件: {op.path}")
            continue

        try:
            file_path = resolve_in_workspace(root_path, op.path)
        except Exception:
            warnings.append(f"无法解析路径: {op.path}")
            continue

        created = op.action == "create" or (op.block_type == "file.diff" and not op.before and bool(op.after))
        try:
            if op.block_type == "file.delete" or op.action == "delete":
                await run_sync(_write_text_file, file_path, op.before)
                reverted.append(op.path)
            elif created:
                if file_path.exists():
                    await run_sync(_delete_entry_fs, file_path)
                reverted.append(op.path)
            else:
                await run_sync(_write_text_file, file_path, op.before)
                reverted.append(op.path)
        except Exception as exc:
            warnings.append(f"恢复失败 {op.path}: {exc}")

    return reverted, warnings
