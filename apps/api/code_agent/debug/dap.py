"""DAP (Debug Adapter Protocol) TCP client — Content-Length framing."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any


EventHandler = Callable[[str, dict[str, Any]], Awaitable[None] | None]


class DapClient:
    def __init__(self) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._seq = 1
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._on_event: EventHandler | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = False
        self._initialized = asyncio.Event()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._closed

    def set_event_handler(self, handler: EventHandler | None) -> None:
        self._on_event = handler

    async def wait_initialized(self, timeout: float = 15.0) -> None:
        await asyncio.wait_for(self._initialized.wait(), timeout=timeout)

    async def connect(self, host: str, port: int, *, timeout: float = 30.0) -> None:
        last_err: Exception | None = None
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=2.0,
                )
                # Tunnel may accept then reset if remote wasn't ready yet.
                await asyncio.sleep(0.05)
                if reader.at_eof():
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
                    last_err = ConnectionError("DAP peer closed immediately")
                    await asyncio.sleep(0.15)
                    continue
                self._reader, self._writer = reader, writer
                self._closed = False
                self._initialized.clear()
                self._reader_task = asyncio.create_task(self._read_loop())
                return
            except Exception as exc:  # noqa: BLE001 — retry until timeout
                last_err = exc
                await asyncio.sleep(0.15)
        raise ConnectionError(f"DAP connect failed on {host}:{port}: {last_err}")

    async def close(self) -> None:
        self._closed = True
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
        self._reader = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("DAP closed"))
        self._pending.clear()

    async def request(
        self,
        command: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        fut = await self.request_start(command, arguments)
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as exc:
            # best-effort cleanup if still pending
            for seq, pending in list(self._pending.items()):
                if pending is fut:
                    self._pending.pop(seq, None)
                    break
            raise TimeoutError(f"DAP request timed out: {command}") from exc

    async def request_start(
        self,
        command: str,
        arguments: dict[str, Any] | None = None,
    ) -> asyncio.Future[dict[str, Any]]:
        """Send a request and return its future without waiting (for attach-before-configDone)."""
        if not self._writer:
            raise ConnectionError("DAP not connected")
        seq = self._seq
        self._seq += 1
        msg: dict[str, Any] = {
            "seq": seq,
            "type": "request",
            "command": command,
        }
        if arguments is not None:
            msg["arguments"] = arguments
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[seq] = fut
        await self._send(msg)
        return fut

    async def _send(self, msg: dict[str, Any]) -> None:
        assert self._writer is not None
        body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._writer.write(header + body)
        await self._writer.drain()

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while not self._closed:
                headers = await self._read_headers()
                if headers is None:
                    break
                length = int(headers.get("Content-Length") or 0)
                if length <= 0:
                    continue
                raw = await self._reader.readexactly(length)
                try:
                    msg = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                await self._dispatch(msg)
        except (asyncio.CancelledError, asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        finally:
            self._closed = True
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(ConnectionError("DAP disconnected"))
            self._pending.clear()

    async def _read_headers(self) -> dict[str, str] | None:
        assert self._reader is not None
        headers: dict[str, str] = {}
        while True:
            line = await self._reader.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                return headers
            try:
                text = line.decode("ascii").strip()
            except UnicodeDecodeError:
                continue
            if ":" in text:
                key, value = text.split(":", 1)
                headers[key.strip()] = value.strip()

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        if kind == "response":
            req_seq = int(msg.get("request_seq") or 0)
            fut = self._pending.pop(req_seq, None)
            if fut and not fut.done():
                if msg.get("success", True):
                    fut.set_result(msg)
                else:
                    fut.set_exception(RuntimeError(str(msg.get("message") or "DAP error")))
            return
        if kind == "event":
            event = str(msg.get("event") or "")
            body = msg.get("body") if isinstance(msg.get("body"), dict) else {}
            if event == "initialized":
                self._initialized.set()
            if self._on_event:
                # Never await handlers on the read loop — nested DAP requests would deadlock.
                result = self._on_event(event, body)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
