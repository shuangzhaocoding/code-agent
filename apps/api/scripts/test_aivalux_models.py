#!/usr/bin/env python3
"""Test aivalux models for basic response and thinking mode. Usage: AVALUX_KEY=sk-... python test_aivalux_models.py"""
from __future__ import annotations

import json
import os
import sys
import httpx

BASE = "https://www.aivalux.com/v1"
PROMPT = "Reply with exactly one word: pong"


def main() -> int:
    key = os.environ.get("AVALUX_KEY", "").strip()
    if not key:
        print("Set AVALUX_KEY env var", file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    client = httpx.Client(timeout=60.0, headers=headers)

    res = client.get(f"{BASE}/models")
    res.raise_for_status()
    models = [m["id"] for m in res.json().get("data", [])]
    print(f"Models: {len(models)}\n")

    results = []
    for model_id in models:
        basic = test_chat(client, model_id, thinking=False)
        deep = test_chat(client, model_id, thinking=True)
        results.append({"model": model_id, "basic": basic, "thinking": deep})
        print(f"## {model_id}")
        print(f"  basic:    {basic['status']} — {basic['detail'][:120]}")
        print(f"  thinking: {deep['status']} — {deep['detail'][:120]}")
        print()

    ok_basic = sum(1 for r in results if r["basic"]["status"] == "ok")
    ok_think = sum(1 for r in results if r["thinking"]["status"] == "ok")
    print(f"Summary: {ok_basic}/{len(models)} basic ok, {ok_think}/{len(models)} thinking ok")
    return 0


def test_chat(client: httpx.Client, model_id: str, *, thinking: bool) -> dict:
    body: dict = {
        "model": model_id,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 32,
        "stream": False,
    }
    if thinking:
        body["extra_body"] = {"thinking": {"type": "enabled", "budget_tokens": 1024}}

    try:
        res = client.post(f"{BASE}/chat/completions", json=body)
        if res.status_code >= 400:
            detail = _error_detail(res)
            return {"status": "fail", "detail": detail}
        data = res.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        reasoning = (data.get("choices") or [{}])[0].get("message", {}).get("reasoning_content", "")
        reply = (content or reasoning or str(data))[:80]
        has_reasoning = bool(reasoning)
        return {
            "status": "ok",
            "detail": f"reply={reply!r}" + (" [has reasoning]" if has_reasoning else ""),
        }
    except Exception as exc:
        return {"status": "error", "detail": str(exc)[:200]}


def _error_detail(res: httpx.Response) -> str:
    try:
        payload = res.json()
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                return f"HTTP {res.status_code}: {err.get('message', err)}"
            return f"HTTP {res.status_code}: {payload.get('message', payload)}"
    except Exception:
        pass
    return f"HTTP {res.status_code}: {res.text[:200]}"


if __name__ == "__main__":
    raise SystemExit(main())
