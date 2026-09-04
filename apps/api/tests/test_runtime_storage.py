from __future__ import annotations

import pytest

from code_agent.config import merge_user_config, settings
from code_agent.runtime.profile import agent_execution_external, agent_worker_mode, runtime_profile
from code_agent.storage.backends import resolve_database_url, storage_database_backend


@pytest.fixture(autouse=True)
def _reset_runtime(monkeypatch):
    settings.reload()
    settings._cfg.setdefault("runtime", {})["profile"] = "monolith"
    yield


def test_monolith_inline_execution():
    assert runtime_profile() == "monolith"
    assert agent_worker_mode() == "inline"
    assert agent_execution_external() is False


def test_split_external_worker():
    settings._cfg["runtime"]["profile"] = "split"
    assert agent_worker_mode() == "external"
    assert agent_execution_external() is True


def test_sqlite_database_url():
    assert storage_database_backend() == "sqlite"
    assert resolve_database_url().startswith("sqlite://")


def test_postgres_requires_url():
    settings._cfg.setdefault("storage", {})["database"] = "postgres"
    with pytest.raises(RuntimeError):
        resolve_database_url()


def test_merge_user_config_storage(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    monkeypatch.setitem(settings._cfg.setdefault("paths", {}), "user_config", str(cfg_path))
    merge_user_config("storage", {"database": "postgres", "postgres_url": "postgres://u:p@127.0.0.1/db"})
    saved = cfg_path.read_text(encoding="utf-8")
    assert "database: postgres" in saved
    assert "postgres://u:p@127.0.0.1/db" in saved


def test_ensure_user_config_creates(tmp_path):
    from code_agent.config import ensure_user_config

    path = tmp_path / "cfg" / "config.yaml"
    out, created = ensure_user_config(path, quiet=True)
    assert created is True
    assert out == path
    assert path.is_file()
    assert "profile: split" in path.read_text(encoding="utf-8")
    _, again = ensure_user_config(path, quiet=True)
    assert again is False
