"""Local port discovery and HTTP/WebSocket preview proxy (localhost only)."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin

import httpx
import websockets
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import Response as PlainResponse
from fastapi.responses import StreamingResponse

from code_agent.config import settings
from code_agent.ports.scanner import format_open_url, get_port_entry, kill_port_process, list_listening_ports

router = APIRouter(tags=["ports"])

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

_STRIP_RESPONSE = {
    "content-security-policy",
    "content-security-policy-report-only",
    "x-frame-options",
    "content-encoding",
    "transfer-encoding",
    "content-length",
}

_HTML_LIMIT = 2_000_000
_TEXT_LIMIT = 5_000_000
_ATTR_ABS = re.compile(
    r"""(?P<attr>(?:src|href|action)\s*=\s*["'])/(?!/)""",
    re.IGNORECASE,
)
_VITE_ABS = re.compile(
    r"""(?P<q>["'`])/(?P<p>(?:@vite/|@fs/|@id/|@react-refresh|node_modules/|src/|assets/|\.vite/))"""
)

# Keep frontend assets, /api (via Vite proxy), and direct localhost:backendPort calls inside /api/preview.
_PREVIEW_PATCH = """<script data-ca-preview-ws>
(function () {
  var PREFIX = %PREFIX%;
  var TARGET_PORT = %PORT%;
  var PREFIX_SLASH = PREFIX.replace(/\\/$/, "");

  function isLoopback(hostname) {
    return hostname === "127.0.0.1" || hostname === "localhost" || hostname === "::1";
  }

  function rewriteUrl(raw) {
    if (raw == null) return raw;
    var abs;
    try {
      abs = new URL(String(raw), location.href);
    } catch (e) {
      return raw;
    }
    if (abs.pathname.indexOf("/api/preview/") === 0) return abs.toString();

    // http://127.0.0.1:8001/api/... → /api/preview/8001/api/...
    if (isLoopback(abs.hostname) && abs.port && abs.port !== location.port) {
      var other = abs.port;
      abs.protocol = location.protocol;
      abs.host = location.host;
      if (String(other) === String(TARGET_PORT)) {
        abs.pathname = PREFIX_SLASH + (abs.pathname || "/");
      } else {
        abs.pathname = "/api/preview/" + other + (abs.pathname || "/");
      }
      return abs.toString();
    }

    // same-origin /api/... (Vite proxy to backend) → /api/preview/{frontendPort}/api/...
    if (abs.origin === location.origin && abs.pathname.charAt(0) === "/" && abs.pathname.indexOf(PREFIX_SLASH) !== 0) {
      abs.pathname = PREFIX_SLASH + abs.pathname;
      return abs.toString();
    }
    return abs.toString();
  }

  function rewriteWs(raw) {
    try {
      var u = new URL(String(raw), location.href);
      var sameOriginRoot = u.host === location.host && (u.pathname === "/" || u.pathname === "");
      var port = String(u.port || (u.protocol === "wss:" ? "443" : "80"));
      var toTarget = isLoopback(u.hostname) && port === String(TARGET_PORT);
      var toOther = isLoopback(u.hostname) && u.port && u.port !== location.port && port !== String(TARGET_PORT);
      if (sameOriginRoot || toTarget) {
        u.protocol = location.protocol === "https:" ? "wss:" : "ws:";
        u.host = location.host;
        var rest = u.pathname && u.pathname !== "/" ? u.pathname : "/";
        u.pathname = PREFIX_SLASH + (rest.startsWith("/") ? rest : "/" + rest);
        return u.toString();
      }
      if (toOther) {
        u.protocol = location.protocol === "https:" ? "wss:" : "ws:";
        u.host = location.host;
        u.pathname = "/api/preview/" + u.port + (u.pathname || "/");
        return u.toString();
      }
    } catch (e) {}
    return raw;
  }

  var NativeWS = window.WebSocket;
  function WrappedWS(url, protocols) {
    url = rewriteWs(url);
    return protocols === undefined ? new NativeWS(url) : new NativeWS(url, protocols);
  }
  WrappedWS.prototype = NativeWS.prototype;
  WrappedWS.CONNECTING = NativeWS.CONNECTING;
  WrappedWS.OPEN = NativeWS.OPEN;
  WrappedWS.CLOSING = NativeWS.CLOSING;
  WrappedWS.CLOSED = NativeWS.CLOSED;
  window.WebSocket = WrappedWS;

  var nativeFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    if (typeof input === "string" || (typeof URL !== "undefined" && input instanceof URL)) {
      return nativeFetch(rewriteUrl(input), init);
    }
    if (typeof Request !== "undefined" && input instanceof Request) {
      var next = rewriteUrl(input.url);
      if (next !== input.url) input = new Request(next, input);
    }
    return nativeFetch(input, init);
  };

  var XO = window.XMLHttpRequest;
  if (XO && XO.prototype) {
    var open = XO.prototype.open;
    XO.prototype.open = function (method, url) {
      var args = Array.prototype.slice.call(arguments);
      if (typeof url === "string") args[1] = rewriteUrl(url);
      return open.apply(this, args);
    };
  }

  if (typeof EventSource !== "undefined") {
    var NativeES = window.EventSource;
    window.EventSource = function (url, config) {
      return new NativeES(rewriteUrl(url), config);
    };
    window.EventSource.prototype = NativeES.prototype;
    window.EventSource.CONNECTING = NativeES.CONNECTING;
    window.EventSource.OPEN = NativeES.OPEN;
    window.EventSource.CLOSED = NativeES.CLOSED;
  }
})();
</script>"""


def _own_ports() -> set[int]:
    ports: set[int] = set()
    try:
        ports.add(int(settings.get("server.port") or 8000))
    except (TypeError, ValueError):
        ports.add(8000)
    return ports


@router.get("/api/ports")
async def get_ports():
    own = _own_ports()
    items = list_listening_ports()
    for item in items:
        item["self"] = item["port"] in own
    return {"ports": items, "count": len(items)}


@router.delete("/api/ports/{port}")
async def kill_port(port: int):
    if port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail={"code": "ports.invalid", "message": "无效端口"})
    if port in _own_ports():
        raise HTTPException(status_code=400, detail={"code": "ports.self", "message": "不能结束 Code Agent 自身端口"})
    try:
        result = await asyncio.to_thread(kill_port_process, port)
    except ValueError as exc:
        code = str(exc)
        messages = {
            "port_not_listening": "端口未在监听",
            "pid_unknown": "无法解析监听进程 PID",
            "pid_self": "不能结束当前 API 进程",
            "pid_gone": "进程已退出",
            "permission_denied": "没有权限结束该进程",
            "port_protected": "系统关键端口受保护，不允许结束",
        }
        status = 404 if code in {"port_not_listening", "pid_gone"} else 400
        raise HTTPException(
            status_code=status,
            detail={"code": f"ports.{code}", "message": messages.get(code, code)},
        ) from exc
    return result


def _filter_request_headers(headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        lk = key.lower()
        if lk in _HOP_BY_HOP or lk.startswith("x-forwarded") or lk == "accept-encoding":
            continue
        out[key] = value
    out["Accept-Encoding"] = "identity"
    return out


def _filter_response_headers(headers, *, port: int, prefix: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        lk = key.lower()
        if lk in _STRIP_RESPONSE or lk in _HOP_BY_HOP:
            continue
        if lk == "location":
            if value.startswith("/"):
                value = f"{prefix.rstrip('/')}{value}"
            elif (
                value.startswith(f"http://127.0.0.1:{port}")
                or value.startswith(f"http://localhost:{port}")
                or value.startswith(f"http://[::1]:{port}")
            ):
                path = value.rsplit(f":{port}", 1)[-1] or "/"
                if path.startswith("]"):
                    path = path[1:] or "/"
                value = f"{prefix.rstrip('/')}{path}"
        out[key] = value
    out["X-Frame-Options"] = "SAMEORIGIN"
    return out


def _rewrite_text_paths(text: str, prefix: str) -> str:
    base = prefix.rstrip("/") + "/"
    return _VITE_ABS.sub(lambda m: f"{m.group('q')}{base}{m.group('p')}", text)


def json_dumps_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _rewrite_html(html: str, prefix: str, port: int) -> str:
    base = prefix.rstrip("/") + "/"
    html = _ATTR_ABS.sub(rf"\g<attr>{base}", html)
    html = _rewrite_text_paths(html, prefix)
    patch = _PREVIEW_PATCH.replace("%PREFIX%", json_dumps_str(prefix.rstrip("/"))).replace(
        "%PORT%", str(int(port))
    )
    inject_parts: list[str] = []
    if "data-ca-preview-ws" not in html:
        inject_parts.append(patch)
    if "base href" not in html.lower():
        inject_parts.append(f'<base href="{base}">')
    if inject_parts and re.search(r"(?i)<head[^>]*>", html):
        blob = "".join(inject_parts)
        html = re.sub(r"(?i)<head([^>]*)>", rf"<head\1>{blob}", html, count=1)
    elif inject_parts:
        html = "".join(inject_parts) + html
    return html


def _should_rewrite_text(content_type: str, path: str) -> str | None:
    ct = content_type.lower()
    if "text/html" in ct:
        return "html"
    if any(token in ct for token in ("javascript", "ecmascript", "typescript", "json", "text/css", "text/plain")):
        return "text"
    lower = path.lower()
    if lower.endswith((".js", ".mjs", ".ts", ".tsx", ".jsx", ".css", ".json", ".vue", ".map")):
        return "text"
    return None


async def _open_upstream(method: str, target: str, headers: dict, body: bytes | None):
    client = httpx.AsyncClient(timeout=60.0, follow_redirects=False)
    try:
        upstream = await client.send(
            client.build_request(method, target, headers=headers, content=body if body else None),
            stream=True,
        )
        return client, upstream
    except Exception:
        await client.aclose()
        raise


async def _proxy(port: int, path: str, request: Request) -> Response:
    if port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail={"code": "ports.invalid", "message": "无效端口"})
    entry = get_port_entry(port)
    if not entry:
        raise HTTPException(status_code=404, detail={"code": "ports.not_listening", "message": f"端口 {port} 未在监听"})
    if port in _own_ports():
        raise HTTPException(status_code=400, detail={"code": "ports.self", "message": "不能代理 Code Agent 自身端口"})

    connect_host = entry.get("connect_host") or "127.0.0.1"
    candidates = [connect_host]
    alt = "::1" if connect_host == "127.0.0.1" else "127.0.0.1"
    if alt not in candidates:
        candidates.append(alt)

    prefix = f"/api/preview/{port}"
    body = await request.body()
    headers = _filter_request_headers(request.headers)

    last_error: Exception | None = None
    client = None
    upstream = None
    for host in candidates:
        target_base = format_open_url(host, port).rstrip("/") + "/"
        target = urljoin(target_base, path.lstrip("/"))
        if request.url.query:
            target = f"{target}?{request.url.query}"
        try:
            client, upstream = await _open_upstream(request.method, target, headers, body)
            break
        except httpx.HTTPError as exc:
            last_error = exc
            continue

    if upstream is None or client is None:
        raise HTTPException(
            status_code=502,
            detail={"code": "ports.proxy_error", "message": f"All connection attempts failed: {last_error}"},
        )

    resp_headers = _filter_response_headers(upstream.headers, port=port, prefix=prefix)
    content_type = (upstream.headers.get("content-type") or "").lower()
    kind = _should_rewrite_text(content_type, path) if request.method == "GET" else None

    if kind:
        raw = await upstream.aread()
        await upstream.aclose()
        await client.aclose()
        limit = _HTML_LIMIT if kind == "html" else _TEXT_LIMIT
        if len(raw) <= limit:
            try:
                text = raw.decode(upstream.charset_encoding or "utf-8", errors="replace")
            except LookupError:
                text = raw.decode("utf-8", errors="replace")
            text = _rewrite_html(text, prefix, port) if kind == "html" else _rewrite_text_paths(text, prefix)
            raw = text.encode("utf-8")
            resp_headers.pop("Content-Length", None)
        return PlainResponse(
            content=raw,
            status_code=upstream.status_code,
            headers=resp_headers,
            media_type=upstream.headers.get("content-type"),
        )

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


def _ws_upstream_uri(host: str, port: int, path: str, query: bytes) -> str:
    suffix = "/" + path.lstrip("/") if path else "/"
    if query:
        suffix += "?" + query.decode("utf-8", errors="replace")
    if ":" in host:
        return f"ws://[{host}]:{port}{suffix}"
    return f"ws://{host}:{port}{suffix}"


@router.websocket("/api/preview/{port}")
@router.websocket("/api/preview/{port}/{path:path}")
async def preview_ws(websocket: WebSocket, port: int, path: str = ""):
    entry = get_port_entry(port)
    if not entry or port in _own_ports():
        await websocket.close(code=4404)
        return

    connect_host = entry.get("connect_host") or "127.0.0.1"
    hosts = [connect_host]
    alt = "::1" if connect_host == "127.0.0.1" else "127.0.0.1"
    if alt not in hosts:
        hosts.append(alt)

    await websocket.accept()
    query = websocket.scope.get("query_string") or b""

    upstream = None
    last_error: Exception | None = None
    for host in hosts:
        uri = _ws_upstream_uri(host, port, path, query)
        try:
            upstream = await websockets.connect(uri, open_timeout=5)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    if upstream is None:
        await websocket.close(code=1011, reason=str(last_error or "upstream unavailable")[:100])
        return

    async def client_to_upstream():
        try:
            while True:
                message = await websocket.receive()
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
                    await websocket.send_text(message)
                else:
                    await websocket.send_bytes(message)
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
        await websocket.close()
    except Exception:
        pass


@router.api_route("/api/preview/{port}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
@router.api_route("/api/preview/{port}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
async def preview_proxy(port: int, request: Request, path: str = ""):
    return await _proxy(port, path, request)
