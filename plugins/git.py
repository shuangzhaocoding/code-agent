PLUGIN_TITLE = "Git"
PLUGIN_DESCRIPTION = "Workspace Git tools: status, diff, log, branch, add, commit, push, pull, checkout, reset."
PLUGIN_KIND = "tools"
PLUGIN_VERSION = "1.0.0"
PLUGIN_AUTHOR = "Code Agent"
PLUGIN_HOMEPAGE = "https://git-scm.com/"
PLUGIN_REPOSITORY = "https://github.com/git/git"
PLUGIN_LICENSE = "GPL-2.0"
PLUGIN_ICON = "git"
PLUGIN_ACCENT = "#f97316"
PLUGIN_KEYWORDS = ("git", "version-control", "scm")


def register(registry) -> None:
    from langchain_core.tools import tool

    from code_agent.tools.approval import request_approval
    from code_agent.tools.context import get_workspace
    from code_agent.tools.git_ops import GitError, parse_status, run_git

    def _root() -> str:
        return get_workspace()["root_path"]

    def _run(args: list[str], timeout: int = 60) -> str:
        try:
            return run_git(_root(), args, timeout=timeout) or "(ok)"
        except GitError as exc:
            return f"ERROR: {exc}"
        except FileNotFoundError:
            return "ERROR: git is not installed"
        except Exception as exc:
            return f"ERROR: {exc}"

    @tool
    async def git_status() -> str:
        """Show git branch and changed files in the workspace repository."""
        data = parse_status(_root())
        if not data.get("ok"):
            return f"ERROR: {data.get('error') or 'not a git repository'}"
        lines = [f"branch {data['branch']} ahead={data['ahead']} behind={data['behind']}"]
        for item in data["files"]:
            mark = item["code"].ljust(2)
            lines.append(f"{mark} {item['path']}")
        return "\n".join(lines) if len(lines) > 1 else f"{lines[0]}\n(clean)"

    @tool
    async def git_diff(path: str = "") -> str:
        """Show git diff. Optional path limits the diff to one file."""
        args = ["diff"]
        if path:
            args.extend(["--", path])
        return _run(args)

    @tool
    async def git_log(limit: int = 12) -> str:
        """Show recent git commits (oneline)."""
        n = max(1, min(int(limit or 12), 50))
        return _run(["log", f"-{n}", "--oneline", "--decorate"])

    @tool
    async def git_branch() -> str:
        """List local git branches."""
        return _run(["branch", "-vv"])

    @tool
    async def git_add(paths: str) -> str:
        """Stage files. `paths` is a space-separated list, or `.` for all."""
        items = [p for p in paths.split() if p]
        if not items:
            return "ERROR: no paths"
        return _run(["add", "--", *items])

    @tool
    async def git_commit(message: str) -> str:
        """Create a git commit from currently staged files. Requires user confirmation."""
        if not await request_approval("git_commit", f"提交：{message}", {"message": message}, kind="git"):
            return "ERROR: user denied this operation"
        return _run(["commit", "-m", message])

    @tool
    async def git_push(remote: str = "origin", branch: str = "") -> str:
        """Push the current (or named) branch. Requires user confirmation."""
        args = ["push", remote]
        if branch:
            args.append(branch)
        summary = f"推送到 {remote}" + (f" {branch}" if branch else "")
        if not await request_approval("git_push", summary, {"remote": remote, "branch": branch}, kind="git"):
            return "ERROR: user denied this operation"
        return _run(args, timeout=120)

    @tool
    async def git_pull(remote: str = "origin", branch: str = "") -> str:
        """Pull from remote. Requires user confirmation."""
        args = ["pull", remote]
        if branch:
            args.append(branch)
        if not await request_approval("git_pull", f"拉取 {remote} {branch}".strip(), {"remote": remote, "branch": branch}, kind="git"):
            return "ERROR: user denied this operation"
        return _run(args, timeout=120)

    @tool
    async def git_checkout(ref: str) -> str:
        """Switch branch or restore files (`git checkout <ref>`). Requires user confirmation."""
        if not await request_approval("git_checkout", f"切换/恢复：{ref}", {"ref": ref}, kind="git"):
            return "ERROR: user denied this operation"
        return _run(["checkout", ref])

    @tool
    async def git_reset(mode: str = "mixed", ref: str = "HEAD") -> str:
        """Reset HEAD. mode is soft|mixed|hard. Requires user confirmation."""
        flag = {"soft": "--soft", "mixed": "--mixed", "hard": "--hard"}.get(mode, "--mixed")
        if not await request_approval(
            "git_reset",
            f"git reset {flag} {ref}",
            {"mode": mode, "ref": ref},
            kind="git",
        ):
            return "ERROR: user denied this operation"
        return _run(["reset", flag, ref])

    for t, modes in [
        (git_status, ("ask", "agent", "plan")),
        (git_diff, ("ask", "agent", "plan")),
        (git_log, ("ask", "agent", "plan")),
        (git_branch, ("ask", "agent", "plan")),
        (git_add, ("agent",)),
        (git_commit, ("agent",)),
        (git_push, ("agent",)),
        (git_pull, ("agent",)),
        (git_checkout, ("agent",)),
        (git_reset, ("agent",)),
    ]:
        registry.register_tool(t, source="plugin:git", modes=modes)
