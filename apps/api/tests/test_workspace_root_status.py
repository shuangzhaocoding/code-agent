from __future__ import annotations

from pathlib import Path

from code_agent.routers.workspaces import _local_root_ok


def test_local_root_ok_missing(tmp_path: Path):
    assert _local_root_ok(str(tmp_path / "nope")) is False


def test_local_root_ok_exists(tmp_path: Path):
    d = tmp_path / "ws"
    d.mkdir()
    assert _local_root_ok(str(d)) is True


def test_local_root_ok_empty():
    assert _local_root_ok("") is False
    assert _local_root_ok("   ") is False
