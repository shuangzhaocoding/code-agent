"""HITL bridge: tool-layer approvals integrate with LangGraph interrupt (Phase 4).

Tools call ``request_approval()`` which pauses until the UI POSTs
``/api/runs/{id}/approvals/{aid}``. Future: migrate high-risk tools to
``interrupt_before=['tools']`` + ``Command(resume=...)`` on the compiled graph.
"""

from code_agent.tools.approval import request_approval, resolve_approval

__all__ = ["request_approval", "resolve_approval"]
