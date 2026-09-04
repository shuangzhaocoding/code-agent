"""Reverse-proxy terminal/preview routes on the API gateway in split mode."""

from __future__ import annotations

import asyncio

import httpx
import websockets
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from starlette.responses import StreamingResponse

from code_agent.runtime.profile import service_endpoint

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _filter_request_headers(headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in _HOP_BY_HOP:
            continue
        out[key] = value
    return out


def _filter_response_headers(headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in _HOP_BY_HOP:
            continue
        out[key] = value
    return out


async def _forward_http(request: Request, upstream_base: str) -> Response:
    path = request.url.path
    url = upstream_base.rstrip("/") + path
    if request.url.query:
        url = f"{url}?{request.url.query}"

    body = await request.body()
    headers = _filter_request_headers(request.headers)
    client = httpx.AsyncClient(timeout=60.0, follow_redirects=False)
    try:
        upstream = await client.send(
            client.build_request(request.method, url, headers=headers, content=body if body else None),
            stream=True,
        )
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(status_code=502, detail={"code": "gateway.proxy_error", "message": str(exc)}) from exc

    resp_headers = _filter_response_headers(upstream.headers)

    async def stream():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        stream(),
        status_code=upstream.status_code,
        headers=resp_headers,
        media_type=upstream.headers.get("content-type"),
    )


async def _relay_websocket(client_ws: WebSocket, upstream_ws_url: str) -> None:
    await client_ws.accept()
    upstream = None
    try:
        upstream = await websockets.connect(upstream_ws_url, open_timeout=5)
    except Exception as exc:  # noqa: BLE001
        await client_ws.close(code=1011, reason=str(exc)[:100])
        return

    async def client_to_upstream():
        try:
            while True:
                message = await client_ws.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if "text" in message and message["text"] is not None:
                    await upstream.send(message["text"])
                elif "bytes" in message and message["bytes"] is not None:
                    await upstream.send(message["bytes"])
        except WebSocketDisconnect:
            pass

    async def upstream_to_client():
        try:
            async for message in upstream:
                if isinstance(message, str):
                    await client_ws.send_text(message)
                else:
                    await client_ws.send_bytes(message)
        except Exception:
            pass

    tasks = [
        asyncio.create_task(client_to_upstream()),
        asyncio.create_task(upstream_to_client()),
    ]
    _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    await upstream.close()
    try:
        await client_ws.close()
    except Exception:
        pass


def _ws_url(upstream_base: str, path: str, query: bytes) -> str:
    ws_base = upstream_base.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
    suffix = path if path.startswith("/") else f"/{path}"
    if query:
        suffix += "?" + query.decode("utf-8", errors="replace")
    return ws_base.rstrip("/") + suffix


def create_gateway_proxy_router(*, terminal: bool, preview: bool) -> APIRouter:
    router = APIRouter(tags=["gateway-proxy"])
    terminal_base = service_endpoint("terminal")["url"] if terminal else ""
    preview_base = service_endpoint("preview")["url"] if preview else ""

    if terminal:

        @router.api_route("/api/terminals", methods=["GET", "POST", "PATCH", "DELETE", "HEAD", "OPTIONS"])
        async def proxy_terminal_root(request: Request):
            return await _forward_http(request, terminal_base)

        @router.api_route(
            "/api/terminals/{path:path}",
            methods=["GET", "POST", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        )
        async def proxy_terminal_http(request: Request, path: str):
            return await _forward_http(request, terminal_base)

        @router.websocket("/api/terminals/{path:path}")
        async def proxy_terminal_ws(websocket: WebSocket, path: str):
            query = websocket.scope.get("query_string") or b""
            url = _ws_url(terminal_base, f"/api/terminals/{path}", query)
            await _relay_websocket(websocket, url)

    if preview:

        @router.get("/api/ports")
        async def proxy_ports_list(request: Request):
            return await _forward_http(request, preview_base)

        @router.delete("/api/ports/{port}")
        async def proxy_ports_delete(request: Request, port: int):
            return await _forward_http(request, preview_base)

        @router.api_route(
            "/api/preview/{port}",
            methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        )
        @router.api_route(
            "/api/preview/{port}/{path:path}",
            methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        )
        async def proxy_preview_http(request: Request, port: int, path: str = ""):
            return await _forward_http(request, preview_base)

        @router.websocket("/api/preview/{port}")
        @router.websocket("/api/preview/{port}/{path:path}")
        async def proxy_preview_ws(websocket: WebSocket, port: int, path: str = ""):
            query = websocket.scope.get("query_string") or b""
            suffix = f"/api/preview/{port}"
            if path:
                suffix += f"/{path.lstrip('/')}"
            url = _ws_url(preview_base, suffix, query)
            await _relay_websocket(websocket, url)

    return router
