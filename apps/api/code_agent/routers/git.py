from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from code_agent.db.models import Workspace
from code_agent.tools.git_ops import (
    GitError,
    build_commit_draft,
    build_pr_draft,
    default_base_branch,
    discard_paths,
    file_diff,
    ignore_paths,
    init_repo,
    list_branches,
    list_stashes,
    parse_commit,
    parse_log,
    parse_status,
    run_git,
    safe_rel_paths,
    show_blob,
)
from code_agent.tools.git_remote import create_pull_request, remote_info
from code_agent.workspace.backend import WorkspaceBackend, get_workspace_backend

router = APIRouter(prefix="/api/workspaces", tags=["git"])


class GitPaths(BaseModel):
    paths: list[str] = Field(default_factory=list)


class GitCommitIn(BaseModel):
    message: str
    paths: list[str] = Field(default_factory=list)


class GitCommitMsgIn(BaseModel):
    paths: list[str] = Field(default_factory=list)
    model_id: str = ""
    locale: str = "zh"
    hint: str = ""


class GitPushIn(BaseModel):
    remote: str = "origin"
    branch: str = ""


class GitPullIn(BaseModel):
    remote: str = "origin"
    branch: str = ""


class GitBranchIn(BaseModel):
    name: str
    create: bool = False


class GitStashIn(BaseModel):
    action: str = "push"
    message: str = ""
    ref: str = ""
    include_untracked: bool = True


class GitConflictIn(BaseModel):
    path: str
    side: Literal["ours", "theirs"]


class GitPrIn(BaseModel):
    title: str
    body: str = ""
    base: str = ""
    head: str = ""
    remote: str = "origin"
    push: bool = True


def _safe_ref(name: str) -> str:
    value = (name or "").strip()
    if not value or value.startswith("-") or ".." in value or any(ch in value for ch in " \t\n~^:?*[\\"):
        raise HTTPException(status_code=400, detail={"code": "git.ref", "message": "invalid ref"})
    return value


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


@router.post("/{workspace_id}/git/init")
async def git_init(workspace_id: str):
    backend = await _backend(workspace_id)
    return await init_repo(backend)


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


@router.get("/{workspace_id}/git/branches")
async def git_branches(workspace_id: str):
    backend = await _backend(workspace_id)
    return await list_branches(backend)


@router.post("/{workspace_id}/git/checkout")
async def git_checkout(workspace_id: str, body: GitBranchIn):
    backend = await _backend(workspace_id)
    name = _safe_ref(body.name)
    args = ["switch", "-c", name] if body.create else ["switch", name]
    try:
        out = await _git(backend, args)
    except HTTPException as exc:
        if body.create:
            raise
        try:
            out = await _git(backend, ["checkout", name])
        except HTTPException:
            raise exc from None
    status = await parse_status(backend)
    status["output"] = out
    return status


@router.post("/{workspace_id}/git/pull")
async def git_pull(workspace_id: str, body: GitPullIn | None = None):
    backend = await _backend(workspace_id)
    body = body or GitPullIn()
    args = ["pull", body.remote or "origin"]
    if body.branch:
        args.append(_safe_ref(body.branch))
    try:
        out = await _git(backend, args, timeout=120)
    except HTTPException as exc:
        status = await parse_status(backend)
        if status.get("conflicts"):
            status["output"] = str((exc.detail or {}).get("message") if isinstance(exc.detail, dict) else exc.detail)
            return status
        raise
    status = await parse_status(backend)
    status["output"] = out
    return status


@router.get("/{workspace_id}/git/stash")
async def git_stash_list(workspace_id: str):
    backend = await _backend(workspace_id)
    return await list_stashes(backend)


@router.post("/{workspace_id}/git/stash")
async def git_stash(workspace_id: str, body: GitStashIn | None = None):
    backend = await _backend(workspace_id)
    body = body or GitStashIn()
    action = (body.action or "push").strip().lower()
    if action == "push":
        args = ["stash", "push"]
        if body.include_untracked:
            args.append("-u")
        if body.message.strip():
            args.extend(["-m", body.message.strip()])
    elif action in {"pop", "apply", "drop"}:
        args = ["stash", action]
        if body.ref.strip():
            args.append(_safe_ref(body.ref))
    else:
        raise HTTPException(status_code=400, detail={"code": "git.stash", "message": "unsupported stash action"})
    out = await _git(backend, args)
    status = await parse_status(backend)
    status["output"] = out
    status["stashes"] = (await list_stashes(backend)).get("stashes") or []
    return status


@router.post("/{workspace_id}/git/conflict")
async def git_conflict_take(workspace_id: str, body: GitConflictIn):
    backend = await _backend(workspace_id)
    paths = safe_rel_paths([body.path])
    if not paths:
        raise HTTPException(status_code=400, detail={"code": "git.paths", "message": "path required"})
    flag = "--ours" if body.side == "ours" else "--theirs"
    await _git(backend, ["checkout", flag, "--", paths[0]])
    try:
        await _git(backend, ["add", "--", paths[0]])
    except HTTPException:
        pass
    return await parse_status(backend)


@router.post("/{workspace_id}/git/merge/continue")
async def git_merge_continue(workspace_id: str):
    backend = await _backend(workspace_id)
    out = await _git(backend, ["commit", "--no-edit"])
    status = await parse_status(backend)
    status["output"] = out
    return status


@router.get("/{workspace_id}/git/commit-draft")
async def git_commit_draft(workspace_id: str, subject: str = ""):
    backend = await _backend(workspace_id)
    return await build_commit_draft(backend, subject=subject or None)


@router.post("/{workspace_id}/git/commit-message")
async def git_commit_message(workspace_id: str, body: GitCommitMsgIn):
    from langchain_core.messages import HumanMessage, SystemMessage

    from code_agent.editor.inline_edit import message_text
    from code_agent.llm.hub import get_chat_model
    from code_agent.tools.git_commit_msg import (
        COMMIT_SYSTEM,
        build_commit_ai_prompt,
        clean_commit_message,
        collect_commit_context,
    )

    backend = await _backend(workspace_id)
    ctx = await collect_commit_context(backend, body.paths)
    if not ctx.get("ok"):
        raise HTTPException(status_code=400, detail={"code": "git.repo", "message": ctx.get("error") or "not a git repository"})
    if not ctx.get("paths"):
        raise HTTPException(status_code=400, detail={"code": "git.paths", "message": "no changes selected"})

    chat, _row = await get_chat_model(body.model_id or None)
    if not chat:
        raise HTTPException(status_code=400, detail={"code": "llm.no_model", "message": "No chat model configured"})

    prompt = build_commit_ai_prompt(
        branch=str(ctx.get("branch") or ""),
        paths=list(ctx.get("paths") or []),
        diff=str(ctx.get("diff") or ""),
        locale=body.locale or "zh",
        hint=body.hint or "",
    )
    try:
        response = await chat.ainvoke([SystemMessage(content=COMMIT_SYSTEM), HumanMessage(content=prompt)])
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "git.llm_failed", "message": str(exc)[:240]},
        ) from exc
    message = clean_commit_message(message_text(response))
    if not message:
        raise HTTPException(status_code=502, detail={"code": "git.llm_empty", "message": "empty commit message"})
    return {"ok": True, "message": message, "paths": ctx["paths"]}


@router.get("/{workspace_id}/git/remote")
async def git_remote(workspace_id: str, remote: str = "origin"):
    backend = await _backend(workspace_id)
    info = await remote_info(backend, remote or "origin")
    if info.get("ok"):
        try:
            info["base"] = await default_base_branch(backend)
        except Exception:
            info["base"] = "main"
    return info


@router.get("/{workspace_id}/git/pr-draft")
async def git_pr_draft(workspace_id: str):
    backend = await _backend(workspace_id)
    draft = await build_pr_draft(backend)
    info = await remote_info(backend, "origin")
    return {**draft, "remote": info}


@router.post("/{workspace_id}/git/pull-request")
async def git_open_pr(workspace_id: str, body: GitPrIn):
    backend = await _backend(workspace_id)
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail={"code": "git.pr", "message": "title required"})
    status = await parse_status(backend)
    head = _safe_ref(body.head or status.get("branch") or "")
    base = _safe_ref(body.base or await default_base_branch(backend))
    if body.push:
        try:
            await _git(backend, ["push", "-u", body.remote or "origin", head], timeout=120)
        except HTTPException:
            await _git(backend, ["push", body.remote or "origin", head], timeout=120)
    result = await create_pull_request(
        backend,
        title=title,
        body=body.body or "",
        base=base,
        head=head,
        remote=body.remote or "origin",
    )
    if not result.get("ok") and not result.get("compare_url"):
        raise HTTPException(status_code=400, detail={"code": "git.pr", "message": result.get("error") or "pr failed"})
    result["status"] = await parse_status(backend)
    return result

