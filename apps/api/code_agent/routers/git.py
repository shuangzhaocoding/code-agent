from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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
    safe_rel_paths,
    show_blob,
)
from code_agent.workspace.backend import WorkspaceBackend, get_workspace_backend

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


async def _backend(workspace_id: str) -> WorkspaceBackend:
    return await get_workspace_backend(await _ws(workspace_id))


async def _git(backend: WorkspaceBackend, args: list[str], timeout: int = 60) -> str:
    try:
        return await run_git(backend, args, timeout=timeout)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.missing", "message": "git is not installed"}) from exc
    except GitError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.error", "message": str(exc)}) from exc


@router.get("/{workspace_id}/git/status")
async def git_status(workspace_id: str):
    backend = await _backend(workspace_id)
    return await parse_status(backend)


@router.get("/{workspace_id}/git/log")
async def git_log(workspace_id: str, limit: int = 80):
    backend = await _backend(workspace_id)
    return await parse_log(backend, limit=limit)


@router.get("/{workspace_id}/git/commits/{rev}")
async def git_commit_detail(workspace_id: str, rev: str):
    backend = await _backend(workspace_id)
    data = await parse_commit(backend, rev)
    if not data.get("ok"):
        raise HTTPException(status_code=400, detail={"code": "git.commit", "message": data.get("error") or "commit not found"})
    return data


@router.get("/{workspace_id}/git/diff")
async def git_diff(workspace_id: str, path: str = "", staged: bool = False):
    backend = await _backend(workspace_id)
    if path:
        paths = safe_rel_paths([path])
        if not paths:
            raise HTTPException(status_code=400, detail={"code": "git.paths", "message": "invalid path"})
        path = paths[0]
    try:
        patch = await file_diff(backend, path, staged=staged)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.missing", "message": "git is not installed"}) from exc
    except GitError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.error", "message": str(exc)}) from exc
    return {"path": path, "staged": staged, "diff": patch}


@router.get("/{workspace_id}/git/blob")
async def git_blob(workspace_id: str, path: str, rev: str = "HEAD"):
    backend = await _backend(workspace_id)
    paths = safe_rel_paths([path])
    if not paths:
        raise HTTPException(status_code=400, detail={"code": "git.paths", "message": "invalid path"})
    try:
        return await show_blob(backend, paths[0], rev=rev)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.missing", "message": "git is not installed"}) from exc
    except GitError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.blob", "message": str(exc)}) from exc


@router.post("/{workspace_id}/git/stage")
async def git_stage(workspace_id: str, body: GitPaths):
    backend = await _backend(workspace_id)
    paths = body.paths or ["."]
    await _git(backend, ["add", "--", *paths])
    return await parse_status(backend)


@router.post("/{workspace_id}/git/discard")
async def git_discard(workspace_id: str, body: GitPaths):
    backend = await _backend(workspace_id)
    paths = safe_rel_paths(body.paths)
    if not paths:
        raise HTTPException(status_code=400, detail={"code": "git.paths", "message": "path required"})
    try:
        return await discard_paths(backend, paths)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.missing", "message": "git is not installed"}) from exc
    except GitError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.error", "message": str(exc)}) from exc


@router.post("/{workspace_id}/git/ignore")
async def git_ignore(workspace_id: str, body: GitPaths):
    backend = await _backend(workspace_id)
    paths = safe_rel_paths(body.paths)
    if not paths:
        raise HTTPException(status_code=400, detail={"code": "git.paths", "message": "path required"})
    try:
        return await ignore_paths(backend, paths)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.missing", "message": "git is not installed"}) from exc
    except GitError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.error", "message": str(exc)}) from exc


@router.post("/{workspace_id}/git/unstage")
async def git_unstage(workspace_id: str, body: GitPaths):
    backend = await _backend(workspace_id)
    paths = body.paths or ["."]
    await _git(backend, ["reset", "-q", "HEAD", "--", *paths])
    return await parse_status(backend)


@router.post("/{workspace_id}/git/commit")
async def git_commit(workspace_id: str, body: GitCommitIn):
    backend = await _backend(workspace_id)
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail={"code": "git.message", "message": "commit message required"})
    if body.paths:
        await _git(backend, ["add", "--", *body.paths])
    await _git(backend, ["commit", "-m", message])
    return await parse_status(backend)


@router.post("/{workspace_id}/git/push")
async def git_push(workspace_id: str, body: GitPushIn | None = None):
    backend = await _backend(workspace_id)
    body = body or GitPushIn()
    args = ["push", body.remote]
    if body.branch:
        args.append(body.branch)
    out = await _git(backend, args, timeout=120)
    status = await parse_status(backend)
    status["output"] = out
    return status
