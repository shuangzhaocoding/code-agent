"""HTTP + WebSocket API for Python debugging."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from code_agent.db.models import Workspace
from code_agent.debug.manager import debug_manager

router = APIRouter(prefix="/api/debug", tags=["debug"])


class BreakpointIn(BaseModel):
    line: int
    condition: str | None = None
    hitCondition: str | None = None
    logMessage: str | None = None


class StartDebugIn(BaseModel):
    workspace_id: str
    program: str | None = None
    module: str | None = None
    cwd: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    python: str | None = None
    stopOnEntry: bool = True
    justMyCode: bool = True
    configName: str | None = None
    config: dict[str, Any] | None = None
    currentFile: str | None = None
    breakpoints: dict[str, list[BreakpointIn]] = Field(default_factory=dict)
    exceptionFilters: list[str] = Field(default_factory=lambda: ["uncaught"])


class SetBreakpointsIn(BaseModel):
    path: str
    breakpoints: list[BreakpointIn] = Field(default_factory=list)


class ExceptionBreakpointsIn(BaseModel):
    filters: list[str] = Field(default_factory=list)


class EvaluateIn(BaseModel):
    expression: str
    frameId: int | None = None
    context: str = "repl"


class SetVariableIn(BaseModel):
    variablesReference: int
    name: str
    value: str


def _session_or_404(session_id: str):
    session = debug_manager.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"code": "debug.not_found"})
    return session


def _bp_dicts(bps: list[BreakpointIn]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for bp in bps:
        row: dict[str, Any] = {"line": bp.line}
        if bp.condition:
            row["condition"] = bp.condition
        if bp.hitCondition:
            row["hitCondition"] = bp.hitCondition
        if bp.logMessage:
            row["logMessage"] = bp.logMessage
        out.append(row)
    return out


@router.get("/configs")
async def list_configs(workspace_id: str):
    ws = await Workspace.get_or_none(id=workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})
    return {"configurations": await debug_manager.load_configs(ws)}


@router.get("/sessions")
async def list_sessions(workspace_id: str):
    rows = debug_manager.list_for_workspace(workspace_id)
    return {
        "sessions": [
            {
                "id": s.id,
                "state": s.state,
                "program": s.config.program,
                "module": s.config.module,
                "cwd": s.config.cwd,
                "name": s.config.name,
            }
            for s in rows
        ]
    }


@router.post("/sessions")
async def start_session(body: StartDebugIn):
    ws = await Workspace.get_or_none(id=body.workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail={"code": "workspace.not_found"})
    bps = {path: _bp_dicts(items) for path, items in body.breakpoints.items()}
    try:
        session = await debug_manager.start(
            ws,
            program=body.program,
            module=body.module,
            cwd=body.cwd,
            args=body.args,
            env=body.env,
            python=body.python,
            stop_on_entry=body.stopOnEntry,
            just_my_code=body.justMyCode,
            config_name=body.configName,
            config=body.config,
            breakpoints=bps,
            exception_filters=body.exceptionFilters,
            current_file=body.currentFile,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "debug.invalid", "message": str(exc)}) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail={"code": "debug.start_failed", "message": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "debug.start_failed", "message": str(exc)}) from exc
    return {
        "id": session.id,
        "state": session.state,
        "program": session.config.program,
        "module": session.config.module,
        "cwd": session.config.cwd,
        "name": session.config.name,
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    session = _session_or_404(session_id)
    return await session.snapshot()


@router.post("/sessions/{session_id}/continue")
async def continue_session(session_id: str):
    session = _session_or_404(session_id)
    await session.continue_()
    return {"ok": True}


@router.post("/sessions/{session_id}/next")
async def next_step(session_id: str):
    session = _session_or_404(session_id)
    await session.next()
    return {"ok": True}


@router.post("/sessions/{session_id}/stepIn")
async def step_in(session_id: str):
    session = _session_or_404(session_id)
    await session.step_in()
    return {"ok": True}


@router.post("/sessions/{session_id}/stepOut")
async def step_out(session_id: str):
    session = _session_or_404(session_id)
    await session.step_out()
    return {"ok": True}


@router.post("/sessions/{session_id}/pause")
async def pause_session(session_id: str):
    session = _session_or_404(session_id)
    await session.pause()
    return {"ok": True}


@router.post("/sessions/{session_id}/stop")
async def stop_session(session_id: str):
    await debug_manager.stop(session_id)
    return {"ok": True}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    await debug_manager.stop(session_id)
    return {"ok": True}


@router.post("/sessions/{session_id}/breakpoints")
async def set_breakpoints(session_id: str, body: SetBreakpointsIn):
    session = _session_or_404(session_id)
    result = await session.set_breakpoints(body.path, _bp_dicts(body.breakpoints))
    return result


@router.post("/sessions/{session_id}/exceptionBreakpoints")
async def set_exception_breakpoints(session_id: str, body: ExceptionBreakpointsIn):
    session = _session_or_404(session_id)
    await session.set_exception_breakpoints(body.filters)
    return {"ok": True}


@router.get("/sessions/{session_id}/stackTrace")
async def stack_trace(session_id: str, threadId: int | None = None):
    session = _session_or_404(session_id)
    frames = await session.stack_trace(threadId)
    return {"stackFrames": frames}


@router.get("/sessions/{session_id}/scopes")
async def scopes(session_id: str, frameId: int):
    session = _session_or_404(session_id)
    return {"scopes": await session.scopes(frameId)}


@router.get("/sessions/{session_id}/variables")
async def variables(session_id: str, variablesReference: int):
    session = _session_or_404(session_id)
    return {"variables": await session.variables(variablesReference)}


@router.post("/sessions/{session_id}/evaluate")
async def evaluate(session_id: str, body: EvaluateIn):
    session = _session_or_404(session_id)
    try:
        result = await session.evaluate(body.expression, body.frameId, body.context)
    except Exception as exc:
        session.record_repl(body.expression, error=str(exc))
        raise HTTPException(status_code=400, detail={"code": "debug.evaluate_failed", "message": str(exc)}) from exc
    session.record_repl(body.expression, result=str(result.get("result") if isinstance(result, dict) else result))
    return result


@router.post("/sessions/{session_id}/setVariable")
async def set_variable(session_id: str, body: SetVariableIn):
    session = _session_or_404(session_id)
    try:
        result = await session.set_variable(body.variablesReference, body.name, body.value)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "debug.set_variable_failed", "message": str(exc)}) from exc
    return result


@router.websocket("/sessions/{session_id}/ws")
async def debug_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()
    session = debug_manager.get(session_id)
    if not session:
        await websocket.close(code=4404)
        return
    await debug_manager.subscribe(session_id, websocket)
    snap = await session.snapshot()
    await websocket.send_json(
        {
            "type": "session",
            "session_id": session_id,
            "payload": {"state": session.state},
        }
    )
    # Replay console history (stdout + REPL) so refresh keeps prior logs.
    history = session.console_history()
    if history:
        await websocket.send_json(
            {
                "type": "console_history",
                "session_id": session_id,
                "payload": {"lines": history},
            }
        )
    if session.state == "paused":
        await websocket.send_json(
            {
                "type": "stopped",
                "session_id": session_id,
                "payload": {
                    "reason": "sync",
                    "threadId": snap.get("threadId"),
                    "frames": snap.get("frames") or [],
                },
            }
        )
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            # Client may send ping/control JSON; ignore for now.
            _ = message.get("text") or message.get("bytes")
    except WebSocketDisconnect:
        pass
    finally:
        await debug_manager.unsubscribe(session_id, websocket)
