from __future__ import annotations

import asyncio
from types import SimpleNamespace

from code_agent.tools.git_ops import build_commit_message, init_repo, is_conflict_code, is_repo, parse_status
from code_agent.tools.git_remote import compare_url, parse_remote_url
from code_agent.workspace.local import LocalWorkspaceBackend


class TestGitConflict:
    def test_unmerged_codes(self):
        assert is_conflict_code("UU")
        assert is_conflict_code("AA")
        assert is_conflict_code("DU")
        assert not is_conflict_code(" M")
        assert not is_conflict_code("??")


class TestCommitMessage:
    def test_single_file(self):
        msg = build_commit_message(["apps/web/src/a.ts"], subject="Apply agent changes")
        assert msg.startswith("Apply agent changes")
        assert "- apps/web/src/a.ts" in msg

    def test_many_files_truncated(self):
        paths = [f"f{i}.py" for i in range(30)]
        msg = build_commit_message(paths)
        assert "Update 30 files" in msg
        assert "+6 files" in msg


class TestRemoteUrl:
    def test_github_ssh(self):
        info = parse_remote_url("git@github.com:acme/app.git")
        assert info["kind"] == "github"
        assert info["owner"] == "acme"
        assert info["repo"] == "app"
        assert info["web_url"] == "https://github.com/acme/app"
        assert "compare/main...feat" in compare_url(info, base="main", head="feat")

    def test_github_https(self):
        info = parse_remote_url("https://github.com/acme/app.git")
        assert info["kind"] == "github"
        assert info["owner"] == "acme"

    def test_gitlab_nested(self):
        info = parse_remote_url("https://gitlab.example.com/group/sub/app.git")
        assert info["kind"] == "gitlab"
        assert info["owner"] == "group/sub"
        assert info["repo"] == "app"
        url = compare_url(info, base="main", head="feat")
        assert "/-/merge_requests/new" in url
        assert "feat" in url and "main" in url


class TestInitRepo:
    def test_init_creates_repo(self, tmp_path):
        ws = SimpleNamespace(root_path=str(tmp_path), ignore_globs=[], kind="local")
        backend = LocalWorkspaceBackend(ws)  # type: ignore[arg-type]
        assert not asyncio.run(is_repo(backend))
        status = asyncio.run(init_repo(backend))
        assert status["ok"]
        assert asyncio.run(is_repo(backend))
        again = asyncio.run(init_repo(backend))
        assert again["ok"]
        assert asyncio.run(parse_status(backend))["ok"]


class TestCommitAiMessage:
    def test_clean_strips_fences_and_period(self):
        from code_agent.tools.git_commit_msg import clean_commit_message

        raw = "```\nFix(login): Retry expired sessions.\n\nKeep users signed in.\n```"
        msg = clean_commit_message(raw)
        assert msg.startswith("fix(login): Retry expired sessions")
        assert not msg.splitlines()[0].endswith(".")
        assert "Keep users signed in" in msg

    def test_clean_normalizes_conventional_type(self):
        from code_agent.tools.git_commit_msg import clean_commit_message

        msg = clean_commit_message("Feat: add git diff layout")
        assert msg == "feat: add git diff layout"

    def test_prompt_includes_diff_and_locale(self):
        from code_agent.tools.git_commit_msg import COMMIT_SYSTEM, build_commit_ai_prompt

        prompt = build_commit_ai_prompt(
            branch="feat/login",
            paths=["apps/web/src/a.ts"],
            diff="@@ -1 +1 @@\n-foo\n+bar",
            locale="zh",
            hint="登录",
        )
        assert "Simplified Chinese" in prompt
        assert "<type>" in prompt
        assert "feat/login" in prompt
        assert "apps/web/src/a.ts" in prompt
        assert "+bar" in prompt
        assert "登录" in prompt
        assert "feat" in COMMIT_SYSTEM and "fix" in COMMIT_SYSTEM
