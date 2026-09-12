from __future__ import annotations

import json
import os
import shlex
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import quote, urlparse

from code_agent.tools.git_ops import GitError, run_git
from code_agent.workspace.backend import WorkspaceBackend

_GITHUB_HOSTS = {"github.com"}


def parse_remote_url(url: str) -> dict[str, str]:
    raw = (url or "").strip()
    if raw.endswith(".git"):
        raw = raw[:-4]
    host = ""
    path = ""
    if "://" in raw:
        parsed = urlparse(raw)
        host = parsed.hostname or ""
        path = (parsed.path or "").lstrip("/")
    elif "@" in raw and ":" in raw.split("@", 1)[-1] and "/" not in raw.split(":", 1)[0]:
        left, _, path = raw.partition(":")
        host = left.split("@")[-1]
    else:
        host, _, path = raw.partition(":")
        if "/" in host and not path:
            path = host
            host = ""
    host = host.strip().lower()
    parts = [p for p in path.split("/") if p]
    kind = "other"
    if host in _GITHUB_HOSTS or host.endswith(".github.com"):
        kind = "github"
    elif "gitlab" in host:
        kind = "gitlab"
    owner = repo = ""
    if kind == "github" and len(parts) >= 2:
        owner, repo = parts[0], parts[1]
    elif len(parts) >= 2:
        repo = parts[-1]
        owner = "/".join(parts[:-1])
        if kind == "other" and owner:
            kind = "gitlab" if "gitlab" in host else kind
    web = ""
    if kind == "github" and owner and repo:
        web = f"https://github.com/{owner}/{repo}"
    elif host and owner and repo:
        web = f"https://{host}/{owner}/{repo}"
    return {
        "kind": kind,
        "host": host,
        "owner": owner,
        "repo": repo,
        "url": (url or "").strip(),
        "web_url": web,
    }


def compare_url(info: dict[str, str], *, base: str, head: str) -> str:
    web = info.get("web_url") or ""
    if not web:
        return ""
    kind = info.get("kind")
    if kind == "github":
        return f"{web}/compare/{quote(base)}...{quote(head)}?expand=1"
    if kind == "gitlab":
        return (
            f"{web}/-/merge_requests/new?merge_request[source_branch]={quote(head)}"
            f"&merge_request[target_branch]={quote(base)}"
        )
    return web


async def remote_info(backend: WorkspaceBackend, remote: str = "origin") -> dict[str, Any]:
    try:
        url = await run_git(backend, ["remote", "get-url", remote], include_stderr=False)
    except GitError as exc:
        return {"ok": False, "error": str(exc), "remote": remote}
    info = parse_remote_url(url)
    which = await _which(backend, "gh" if info["kind"] == "github" else "glab" if info["kind"] == "gitlab" else "")
    return {
        "ok": True,
        "remote": remote,
        **info,
        "cli": which,
        "has_token": bool(_token_for(info["kind"])),
    }


async def _which(backend: WorkspaceBackend, name: str) -> str:
    if not name:
        return ""
    code, out, _ = await backend.run_command(f"command -v {shlex.quote(name)}", cwd=".", timeout=10)
    if code == 0:
        return (out or "").strip() or name
    return ""


def _token_for(kind: str) -> str:
    if kind == "github":
        return (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if kind == "gitlab":
        return (os.environ.get("GITLAB_TOKEN") or os.environ.get("GL_TOKEN") or "").strip()
    return ""


def _http_json(url: str, *, token: str, payload: dict, host_kind: str) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    if host_kind == "github":
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "code-agent")
    else:
        req.add_header("PRIVATE-TOKEN", token)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            return parsed if isinstance(parsed, dict) else {"raw": parsed}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise GitError(f"HTTP {exc.code}: {detail}") from exc


async def create_pull_request(
    backend: WorkspaceBackend,
    *,
    title: str,
    body: str,
    base: str,
    head: str,
    remote: str = "origin",
) -> dict[str, Any]:
    info = await remote_info(backend, remote)
    if not info.get("ok"):
        return info
    kind = str(info.get("kind") or "other")
    cmp = compare_url(info, base=base, head=head)
    cli = str(info.get("cli") or "")
    if cli and kind == "github":
        cmd = (
            f"gh pr create --title {shlex.quote(title)} --body {shlex.quote(body)} "
            f"--base {shlex.quote(base)} --head {shlex.quote(head)}"
        )
        code, out, err = await backend.run_command(cmd, cwd=".", timeout=60)
        text = ((out or "") + "\n" + (err or "")).strip()
        if code == 0:
            url = next((ln.strip() for ln in text.splitlines() if ln.strip().startswith("http")), cmp)
            return {"ok": True, "method": "gh", "url": url, "compare_url": cmp, "output": text}
        return {"ok": False, "method": "gh", "error": text or "gh pr create failed", "compare_url": cmp}
    if cli and kind == "gitlab":
        cmd = (
            f"glab mr create --title {shlex.quote(title)} --description {shlex.quote(body)} "
            f"--target-branch {shlex.quote(base)} --source-branch {shlex.quote(head)} --yes"
        )
        code, out, err = await backend.run_command(cmd, cwd=".", timeout=60)
        text = ((out or "") + "\n" + (err or "")).strip()
        if code == 0:
            url = next((ln.strip() for ln in text.splitlines() if ln.strip().startswith("http")), cmp)
            return {"ok": True, "method": "glab", "url": url, "compare_url": cmp, "output": text}
        return {"ok": False, "method": "glab", "error": text or "glab mr create failed", "compare_url": cmp}

    token = _token_for(kind)
    owner, repo, host = info.get("owner") or "", info.get("repo") or "", info.get("host") or ""
    if token and kind == "github" and owner and repo:
        api = f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}/pulls"
        data = _http_json(api, token=token, payload={"title": title, "body": body, "head": head, "base": base}, host_kind="github")
        url = str(data.get("html_url") or cmp)
        return {"ok": True, "method": "api", "url": url, "compare_url": cmp, "number": data.get("number")}
    if token and kind == "gitlab" and owner and repo:
        project = quote(f"{owner}/{repo}", safe="")
        origin = f"https://{host}" if host else "https://gitlab.com"
        api = f"{origin}/api/v4/projects/{project}/merge_requests"
        data = _http_json(
            api,
            token=token,
            payload={"title": title, "description": body, "source_branch": head, "target_branch": base},
            host_kind="gitlab",
        )
        url = str(data.get("web_url") or cmp)
        return {"ok": True, "method": "api", "url": url, "compare_url": cmp, "iid": data.get("iid")}
    if cmp:
        return {"ok": True, "method": "url", "url": cmp, "compare_url": cmp}
    return {"ok": False, "error": "cannot detect GitHub/GitLab remote", "compare_url": ""}
