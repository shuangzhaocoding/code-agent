from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from code_agent.db.models import Workspace
from code_agent.tools.git_ops import GitError, parse_status, run_git
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


def _git(root: str, args: list[str], timeout: int = 60) -> str:
    try:
        return run_git(root, args, timeout=timeout)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.missing", "message": "git is not installed"}) from exc
    except GitError as exc:
        raise HTTPException(status_code=400, detail={"code": "git.error", "message": str(exc)}) from exc


@router.get("/{workspace_id}/git/status")
async def git_status(workspace_id: str):
    ws = await _ws(workspace_id)
    return parse_status(ws.root_path)


@router.get("/{workspace_id}/git/diff")
async def git_diff(workspace_id: str, path: str = "", staged: bool = False):
    ws = await _ws(workspace_id)
    args = ["diff"]
    if staged:
        args.append("--cached")
    if path:
        resolve_in_workspace(ws.root_path, path)
        args.extend(["--", path])
    return {"path": path, "staged": staged, "diff": _git(ws.root_path, args)}


@router.post("/{workspace_id}/git/stage")
async def git_stage(workspace_id: str, body: GitPaths):
    ws = await _ws(workspace_id)
    paths = body.paths or ["."]
    _git(ws.root_path, ["add", "--", *paths])
    return parse_status(ws.root_path)


@router.post("/{workspace_id}/git/unstage")
async def git_unstage(workspace_id: str, body: GitPaths):
    ws = await _ws(workspace_id)
    paths = body.paths or ["."]
    _git(ws.root_path, ["reset", "-q", "HEAD", "--", *paths])
    return parse_status(ws.root_path)


@router.post("/{workspace_id}/git/commit")
async def git_commit(workspace_id: str, body: GitCommitIn):
    ws = await _ws(workspace_id)
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail={"code": "git.message", "message": "commit message required"})
    if body.paths:
        _git(ws.root_path, ["add", "--", *body.paths])
    _git(ws.root_path, ["commit", "-m", message])
    return parse_status(ws.root_path)


@router.post("/{workspace_id}/git/push")
async def git_push(workspace_id: str, body: GitPushIn | None = None):
    ws = await _ws(workspace_id)
    body = body or GitPushIn()
    args = ["push", body.remote]
    if body.branch:
        args.append(body.branch)
    out = _git(ws.root_path, args, timeout=120)
    status = parse_status(ws.root_path)
    status["output"] = out
    return status
