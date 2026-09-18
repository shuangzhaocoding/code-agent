"""Detect long-lived process commands that belong in the interactive terminal."""

from __future__ import annotations

import re

# Dev servers / watchers: tool timeouts cannot host these.
_LONG_LIVED = re.compile(
    r"""(?ix)
    (?:^|[\n;&|]\s*)(?:nohup\s+)?(?:
      (?:npm|pnpm|yarn|bun)(?:\.cmd)?\s+(?:run\s+)?(?:dev|start|serve)\b
      |(?:npm|pnpm|yarn|bun)(?:\.cmd)?\s+run\s+\S[^\n;&|]*--watch\b
      |(?:npx|pnpx|bunx)\s+(?:--yes\s+)?(?:vite|next|nuxt|remix|astro|webpack(?:-dev-server)?)\b
      |vite\b
      |next\s+dev\b
      |nuxt\s+(?:dev|start)\b
      |astro\s+dev\b
      |webpack(?:-dev-server)?\b
      |webpack\b[^\n;&|]*--watch\b
      |nodemon\b
      |uvicorn\b
      |gunicorn\b
      |flask\s+run\b
      |(?:manage\.py|django-admin)\s+runserver\b
      |(?:python(?:\d+(?:\.\d+)*)?)\s+(?:-m\s+)?(?:http\.server|uvicorn|flask)\b
      |dotnet\s+watch\b
      |cargo\s+watch\b
      |watch\s+\S
      |tail\s+(?:-[^\sf]+\s+)*-f\b
      |rails\s+s(?:erver)?\b
      |php\s+-S\b
      |hugo\s+server\b
      |deno\s+task\s+dev\b
      |docker(?:-compose|\s+compose)\s+up\b(?![^\n;&|]*\s-d(?:\s|$))
    )
    """,
)


def is_long_lived_command(command: str) -> bool:
    text = (command or "").strip()
    if not text:
        return False
    return bool(_LONG_LIVED.search(text))


def normalize_terminal_command(command: str) -> str:
    """Strip backgrounding wrappers so the PTY runs the process in the foreground."""
    cmd = (command or "").strip()
    if not cmd:
        return cmd
    cmd = re.sub(r"(?i)^nohup\s+", "", cmd)
    cmd = re.sub(r"(?i)\s+&\s*$", "", cmd)
    cmd = re.sub(r"(?i)\s*>\s*/dev/null(?:\s+2>&1|\s+2>/dev/null)?\s*$", "", cmd)
    cmd = re.sub(r"(?i)\s+2>&1\s*$", "", cmd)
    return cmd.strip()
