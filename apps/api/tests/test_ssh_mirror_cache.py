from __future__ import annotations

import asyncio
from pathlib import Path

from code_agent.workspace import mirror as mirror_mod


class _Ws:
    id = "ws-mirror-1"
    kind = "ssh"
    root_path = "/remote/proj"


def test_ensure_local_assets_root_ttl_skips_resync(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(mirror_mod.settings, "data_dir", tmp_path)
    monkeypatch.setattr(mirror_mod, "_ttl_sec", lambda: 60.0)
    mirror_mod._synced_at.clear()

    calls = {"n": 0}

    async def _fake_sync(ws):
        calls["n"] += 1
        root = mirror_mod.mirror_root(str(ws.id))
        root.mkdir(parents=True, exist_ok=True)
        (root / "marker").write_text("ok", encoding="utf-8")
        return root

    monkeypatch.setattr(mirror_mod, "sync_ssh_workspace_assets", _fake_sync)

    async def _run():
        a = await mirror_mod.ensure_local_assets_root(_Ws())  # type: ignore[arg-type]
        b = await mirror_mod.ensure_local_assets_root(_Ws())  # type: ignore[arg-type]
        assert a == b
        assert calls["n"] == 1
        # concurrent callers share one sync when cold
        mirror_mod._synced_at.clear()
        mirror_mod.clear_mirror("ws-mirror-1")
        calls["n"] = 0

        async def _one():
            return await mirror_mod.ensure_local_assets_root(_Ws())  # type: ignore[arg-type]

        await asyncio.gather(_one(), _one(), _one())
        assert calls["n"] == 1

    asyncio.run(_run())
