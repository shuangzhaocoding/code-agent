from __future__ import annotations

from code_agent.workspace.watcher import _should_ignore_rel


def test_watch_ignore_git_and_venv():
    assert _should_ignore_rel(".git/HEAD")
    assert _should_ignore_rel(".git/objects/xx")
    assert _should_ignore_rel("node_modules/foo")
    assert _should_ignore_rel(".venv/bin/python")
    assert not _should_ignore_rel("src/main.py")
    assert not _should_ignore_rel("README.md")
