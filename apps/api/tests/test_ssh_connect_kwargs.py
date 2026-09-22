from __future__ import annotations

from pathlib import Path

from code_agent.workspace.ssh_pool import SshAuth, connect_kwargs


def test_password_connect_skips_openssh_config_and_default_keys(monkeypatch):
    monkeypatch.setattr(
        "code_agent.workspace.ssh_pool.settings.get",
        lambda key, default=None: 20 if key == "ssh.login_timeout" else None,
    )
    kw = connect_kwargs(SshAuth(host="10.0.0.1", port=22, username="root", password="secret"))
    assert kw["config"] is None
    assert kw["known_hosts"] is None
    assert kw["encoding"] == "utf-8"
    assert kw["errors"] == "replace"
    assert kw["client_keys"] is None
    assert kw["agent_path"] is None
    assert kw["password"] == "secret"
    assert kw["host"] == "10.0.0.1"
    assert kw["username"] == "root"
    assert kw["tcp_keepalive"] is True
    assert kw["keepalive_interval"] == 30
    assert kw["keepalive_count_max"] == 10


def test_keepalive_overrides(monkeypatch):
    def get(key, default=None):
        if key == "ssh.keepalive_interval":
            return 60
        if key == "ssh.keepalive_count_max":
            return 5
        if key == "ssh.login_timeout":
            return 20
        return None

    monkeypatch.setattr("code_agent.workspace.ssh_pool.settings.get", get)
    kw = connect_kwargs(SshAuth(host="h", port=22, username="u", password="p"))
    assert kw["keepalive_interval"] == 60
    assert kw["keepalive_count_max"] == 5


def test_known_hosts_file_is_read_as_utf8_bytes(tmp_path: Path, monkeypatch):
    hosts = tmp_path / "known_hosts"
    # UTF-8 continuation 0xac would raise under GBK if opened with locale encoding.
    hosts.write_bytes(b"example.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIComment\xc2\xac\n")
    monkeypatch.setattr(
        "code_agent.workspace.ssh_pool.settings.get",
        lambda key, default=None: str(hosts) if key == "ssh.known_hosts" else None,
    )
    kw = connect_kwargs(SshAuth(host="example.com", port=22, username="u", password="p"))
    assert isinstance(kw["known_hosts"], bytes)
    assert b"example.com" in kw["known_hosts"]
    assert b"\xc2\xac" in kw["known_hosts"]


def test_private_key_sets_client_keys(monkeypatch):
    monkeypatch.setattr(
        "code_agent.workspace.ssh_pool.settings.get",
        lambda key, default=None: None,
    )
    monkeypatch.setattr(
        "code_agent.workspace.ssh_pool.asyncssh.import_private_key",
        lambda data, passphrase=None: "IMPORTED",
    )
    kw = connect_kwargs(
        SshAuth(host="h", port=22, username="u", private_key="-----BEGIN OPENSSH PRIVATE KEY-----")
    )
    assert kw["client_keys"] == ["IMPORTED"]
    assert kw["agent_path"] is None
    assert "password" not in kw
