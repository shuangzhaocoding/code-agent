from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from code_agent.middleware.access_password import (
    access_password_enabled,
    clear_access_cookie,
    make_access_token,
    request_unlocked,
    set_access_cookie,
    verify_password_attempt,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class UnlockIn(BaseModel):
    password: str = ""


@router.get("/status")
async def auth_status(request: Request):
    required = access_password_enabled()
    return {
        "required": required,
        "unlocked": (not required) or request_unlocked(request),
    }


@router.post("/unlock")
async def unlock(body: UnlockIn, response: Response):
    if not access_password_enabled():
        clear_access_cookie(response)
        return {"ok": True, "required": False, "unlocked": True}
    if not verify_password_attempt(body.password):
        return Response(
            content='{"detail":{"code":"auth.invalid","message":"Invalid access password"}}',
            status_code=401,
            media_type="application/json",
        )
    token = make_access_token()
    set_access_cookie(response, token)
    return {"ok": True, "required": True, "unlocked": True}


@router.post("/lock")
async def lock(response: Response):
    clear_access_cookie(response)
    return {"ok": True, "unlocked": False}
