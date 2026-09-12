from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx


class McpError(RuntimeError):
    pass


class McpSession:
    async def start(self) -> None: ...
    async def list_tools(self) -> list[dict[str, Any]]: ...
    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str: ...
    async def close(self) -> None: ...


class StdioMcpSession(McpSession):
    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self.proc: asyncio.subprocess.Process | None = None
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def start(self) -> None:
        command = str(self.spec.get("command") or "").strip()
        if not command:
            raise McpError("stdio MCP server missing command")
        args = self.spec.get("args") or []
        if not isinstance(args, list):
            args = [str(args)]
        env = os.environ.copy()
        extra = self.spec.get("env") or {}
        if isinstance(extra, dict):
            env.update({str(k): str(v) for k, v in extra.items() if v is not None})
        self.proc = await asyncio.create_subprocess_exec(
            command,
            *[str(a) for a in args],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        await self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "code-agent", "version": "0.1.0"},
            },
        )
        await self._notify("notifications/initialized", {})

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        req_id = self._next_id()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut
        await self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})
        try:
            return await asyncio.wait_for(fut, timeout=30)
        except TimeoutError as exc:
            self._pending.pop(req_id, None)
            raise McpError(f"MCP timeout: {method}") from exc

    async def _send(self, msg: dict[str, Any]) -> None:
        if not self.proc or not self.proc.stdin:
            raise McpError("MCP process is not running")
        raw = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
        self.proc.stdin.write(header + raw)
        await self.proc.stdin.drain()

    async def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        buf = b""
        try:
            while True:
                chunk = await self.proc.stdout.read(4096)
                if not chunk:
                    break
                buf += chunk
                while True:
                    header_end = buf.find(b"\r\n\r\n")
                    if header_end < 0:
                        break
                    headers = buf[:header_end].decode("ascii", errors="replace")
                    length = 0
                    for line in headers.split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            length = int(line.split(":", 1)[1].strip())
                    body_start = header_end + 4
                    if len(buf) < body_start + length:
                        break
                    raw = buf[body_start : body_start + length]
                    buf = buf[body_start + length :]
                    try:
                        msg = json.loads(raw.decode("utf-8"))
                    except Exception:
                        continue
                    req_id = msg.get("id")
                    fut = self._pending.pop(req_id, None) if req_id is not None else None
                    if fut and not fut.done():
                        if msg.get("error"):
                            fut.set_exception(McpError(str(msg["error"])))
                        else:
                            fut.set_result(msg.get("result"))
        except Exception:
            pass

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._rpc("tools/list", {})
        tools = (result or {}).get("tools") if isinstance(result, dict) else None
        return tools if isinstance(tools, list) else []

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        return _format_tool_result(result)

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        if self.proc:
            try:
                if self.proc.stdin:
                    self.proc.stdin.close()
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=2)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None


class HttpMcpSession(McpSession):
    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self._id = 0
        self._client: httpx.AsyncClient | None = None

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def start(self) -> None:
        url = str(self.spec.get("url") or "").strip()
        if not url:
            raise McpError("http MCP server missing url")
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        extra = self.spec.get("headers") or {}
        if isinstance(extra, dict):
            headers.update({str(k): str(v) for k, v in extra.items() if v is not None})
        self._client = httpx.AsyncClient(timeout=30.0, headers=headers)
        await self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "code-agent", "version": "0.1.0"},
            },
        )
        await self._rpc("notifications/initialized", {}, notify=True)

    async def _rpc(self, method: str, params: dict[str, Any] | None = None, *, notify: bool = False) -> Any:
        if not self._client:
            raise McpError("HTTP MCP client is not started")
        url = str(self.spec.get("url") or "")
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            payload["id"] = self._next_id()
        response = await self._client.post(url, json=payload)
        if notify:
            return None
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise McpError("invalid MCP HTTP response")
        if data.get("error"):
            raise McpError(str(data["error"]))
        return data.get("result")

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._rpc("tools/list", {})
        tools = (result or {}).get("tools") if isinstance(result, dict) else None
        return tools if isinstance(tools, list) else []

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        return _format_tool_result(result)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


def open_session(spec: dict[str, Any]) -> McpSession:
    transport = str(spec.get("transport") or ("http" if spec.get("url") else "stdio")).lower()
    if transport == "http":
        return HttpMcpSession(spec)
    return StdioMcpSession(spec)


def _format_tool_result(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        if result.get("isError"):
            return f"ERROR: {result}"
        content = result.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(str(item.get("text") or ""))
                    else:
                        parts.append(json.dumps(item, ensure_ascii=False))
                else:
                    parts.append(str(item))
            return "\n".join(p for p in parts if p)
        return json.dumps(result, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)
