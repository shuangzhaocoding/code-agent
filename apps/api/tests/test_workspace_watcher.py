from __future__ import annotations

from code_agent.workspace.watcher import _SSH_INSTALL_INOTIFY_SCRIPT, _should_ignore_rel


def test_watch_ignore_git_and_venv():
    assert _should_ignore_rel(".git/HEAD")
    assert _should_ignore_rel(".git/objects/xx")
    assert _should_ignore_rel("node_modules/foo")
    assert _should_ignore_rel(".venv/bin/python")
    assert not _should_ignore_rel("src/main.py")
    assert not _should_ignore_rel("README.md")


def test_ssh_install_inotify_script_covers_common_managers():
    script = _SSH_INSTALL_INOTIFY_SCRIPT
    assert "inotifywait" in script
    assert "inotify-tools" in script
    assert "apt-get" in script
    assert "dnf" in script
    assert "apk" in script
    assert "sudo -n" in script
    assert "UNSUPPORTED_OS" in script
    assert "TRY:" in script
    from code_agent.workspace.watcher import _SSH_INSTALL_FALLBACK_CMDS

    assert len(_SSH_INSTALL_FALLBACK_CMDS) >= 8
    assert any("apt-get" in c for c in _SSH_INSTALL_FALLBACK_CMDS)
    assert any("dnf" in c for c in _SSH_INSTALL_FALLBACK_CMDS)
