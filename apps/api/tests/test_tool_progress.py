from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from code_agent.tools import progress as tool_progress
from code_agent.tools.long_lived import is_long_lived_command
from code_agent.workspace.local import LocalWorkspaceBackend


class _Ws:
    root_path = ""
    ignore_globs: list = []
    kind = "local"


def test_progress_bind_and_current_block():
    tool_progress.clear_run("r1")
    tool_progress.bind("r1", "c1", "b1", "run_command")
    assert tool_progress.current_block("r1") == "b1"
    assert tool_progress.current_block("r1", name="run_command") == "b1"
    assert tool_progress.current_block("r1", name="other") is None
    tool_progress.bind("r1", "c2", "b2", "read_file")
    assert tool_progress.current_block("r1") == "b2"
    tool_progress.unbind("r1", call_id="c2")
    assert tool_progress.current_block("r1") == "b1"
    tool_progress.clear_run("r1")
    assert tool_progress.current_block("r1") is None


def test_emit_delta_publishes_to_bound_block():
    tool_progress.clear_run("r2")
    tool_progress.bind("r2", "c1", "block-x", "run_command")
    published: list[tuple] = []

    async def fake_publish(run_id, etype, payload):
        published.append((run_id, etype, payload))

    async def _run():
        with patch("code_agent.streaming.broker.broker.publish", new=AsyncMock(side_effect=fake_publish)):
            await tool_progress.emit_delta("r2", "hello", name="run_command")
            await tool_progress.emit_meta("r2", {"elapsed_sec": 3}, name="run_command")

    asyncio.run(_run())
    tool_progress.clear_run("r2")
    assert published[0][1] == "block.delta"
    assert published[0][2]["block_id"] == "block-x"
    assert published[0][2]["text"] == "hello"
    assert published[1][1] == "block.updated"
    assert published[1][2]["meta"]["elapsed_sec"] == 3


def test_local_run_command_streams_and_cancels(tmp_path: Path):
    ws = _Ws()
    ws.root_path = str(tmp_path)
    backend = LocalWorkspaceBackend(ws)  # type: ignore[arg-type]
    chunks: list[str] = []

    async def on_output(text: str) -> None:
        chunks.append(text)

    async def _run():
        code, out, _err = await backend.run_command(
            "printf 'hi\\n'; sleep 0.05; printf 'bye\\n'",
            cwd=".",
            timeout=10,
            on_output=on_output,
        )
        assert code == 0
        assert "hi" in out and "bye" in out
        assert any("hi" in c or "bye" in c for c in chunks)

        cancel = asyncio.Event()

        async def cancel_soon():
            await asyncio.sleep(0.15)
            cancel.set()

        task = asyncio.create_task(cancel_soon())
        code2, _out2, err2 = await backend.run_command(
            "sleep 5",
            cwd=".",
            timeout=10,
            cancel_event=cancel,
        )
        await task
        assert code2 == 130
        assert "cancelled" in err2

    asyncio.run(_run())


def test_long_lived_watch_and_tail():
    assert is_long_lived_command("tail -f /var/log/syslog")
    assert is_long_lived_command("watch -n 1 date")
    assert is_long_lived_command("npm run build --watch")
    assert is_long_lived_command("webpack --watch")
    assert not is_long_lived_command("tail /var/log/syslog")
    assert not is_long_lived_command("npm run build")
