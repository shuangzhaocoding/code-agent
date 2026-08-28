from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from code_agent.async_io import run_sync
from code_agent.db.models import Workspace
from code_agent.tools.git_ops import (
    GitError,
    discard_paths,
    file_diff,
    ignore_paths,
    parse_commit,
    parse_log,
    parse_status,
    run_git,
    show_blob,
)
from code_agent.tools.paths import resolve_in_workspace

router = APIRouter(prefix="/api/workspaces", tags=["git"])


class GitPaths(BaseModel):
    paths: list[str] = Field(default_factory=list)


class GitCommitIn(BaseModel):
    message: str
    paths: list[str] = Field(default_factory=list)


class GitPushIn(BaseModel):
    remote: str = "origin"
    branch: str = ""


async def _ws(workspace_id: str) -> Workspace:
    row = await Workspace.get_or_none(id=workspace_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})
    return row


async def _git(root: str, args: list[str], timeout: int = 60) -> str:
    try:
        return await run_sync(run_git, root, args, timeout=timeout)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.missing", "message": "git is not installed"}) from exc
    except GitError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.error", "message": str(exc)}) from exc


def _safe_paths(root: str, paths: list[str]) -> list[str]:
    out: list[str] = []
    for raw in paths:
        rel = (raw or "").replace("\\", "/").strip().lstrip("/")
        if not rel or rel in {".", ".."} or rel.startswith("../"):
            continue
        resolve_in_workspace(root, rel)
        out.append(rel)
    return out


@router.get("/{workspace_id}/git/status")
async def git_status(workspace_id: str):
    ws = await _ws(workspace_id)
    return await run_sync(parse_status, ws.root_path)


@router.get("/{workspace_id}/git/log")
async def git_log(workspace_id: str, limit: int = 80):
    ws = await _ws(workspace_id)
    return await run_sync(parse_log, ws.root_path, limit=limit)


@router.get("/{workspace_id}/git/commits/{rev}")
async def git_commit_detail(workspace_id: str, rev: str):
    ws = await _ws(workspace_id)
    data = await run_sync(parse_commit, ws.root_path, rev)
    if not data.get("ok"):
        raise HTTPException(status_code=400, detail={"code": "git.commit", "message": data.get("error") or "commit not found"})
    return data


@router.get("/{workspace_id}/git/diff")
async def git_diff(workspace_id: str, path: str = "", staged: bool = False):
    ws = await _ws(workspace_id)
    if path:
        resolve_in_workspace(ws.root_path, path)
    try:
        patch = await run_sync(file_diff, ws.root_path, path, staged=staged)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.missing", "message": "git is not installed"}) from exc
    except GitError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.error", "message": str(exc)}) from exc
    return {"path": path, "staged": staged, "diff": patch}


@router.get("/{workspace_id}/git/blob")
async def git_blob(workspace_id: str, path: str, rev: str = "HEAD"):
    ws = await _ws(workspace_id)
    resolve_in_workspace(ws.root_path, path)
    try:
        return await run_sync(show_blob, ws.root_path, path, rev=rev)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.missing", "message": "git is not installed"}) from exc
    except GitError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.blob", "message": str(exc)}) from exc


@router.post("/{workspace_id}/git/stage")
async def git_stage(workspace_id: str, body: GitPaths):
    ws = await _ws(workspace_id)
    paths = body.paths or ["."]
    await _git(ws.root_path, ["add", "--", *paths])
    return await run_sync(parse_status, ws.root_path)


@router.post("/{workspace_id}/git/discard")
async def git_discard(workspace_id: str, body: GitPaths):
    ws = await _ws(workspace_id)
    paths = _safe_paths(ws.root_path, body.paths)
    if not paths:
        raise HTTPException(status_code=400, detail={"code": "git.paths", "message": "path required"})
    try:
        return await run_sync(discard_paths, ws.root_path, paths)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.missing", "message": "git is not installed"}) from exc
    except GitError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.error", "message": str(exc)}) from exc


@router.post("/{workspace_id}/git/ignore")
async def git_ignore(workspace_id: str, body: GitPaths):
    ws = await _ws(workspace_id)
    paths = _safe_paths(ws.root_path, body.paths)
    if not paths:
        raise HTTPException(status_code=400, detail={"code": "git.paths", "message": "path required"})
    try:
        return await run_sync(ignore_paths, ws.root_path, paths)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.missing", "message": "git is not installed"}) from exc
    except GitError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.error", "message": str(exc)}) from exc


@router.post("/{workspace_id}/git/unstage")
async def git_unstage(workspace_id: str, body: GitPaths):
    ws = await _ws(workspace_id)
    paths = body.paths or ["."]
    await _git(ws.root_path, ["reset", "-q", "HEAD", "--", *paths])
    return await run_sync(parse_status, ws.root_path)


@router.post("/{workspace_id}/git/commit")
async def git_commit(workspace_id: str, body: GitCommitIn):
    ws = await _ws(workspace_id)
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail={"code": "git.message", "message": "commit message required"})
    if body.paths:
        await _git(ws.root_path, ["add", "--", *body.paths])
    await _git(ws.root_path, ["commit", "-m", message])
    return await run_sync(parse_status, ws.root_path)


@router.post("/{workspace_id}/git/push")
async def git_push(workspace_id: str, body: GitPushIn | None = None):
    ws = await _ws(workspace_id)
    body = body or GitPushIn()
    args = ["push", body.remote]
    if body.branch:
        args.append(body.branch)
    out = await _git(ws.root_path, args, timeout=120)
    status = await run_sync(parse_status, ws.root_path)
    status["output"] = out
    return status
