from __future__ import annotations

from code_agent.config import settings
from code_agent.db.models import Workspace
from code_agent.llm.thinking import thinking_prompt
from code_agent.skills.registry import list_skill_catalog


def plan_format_rules(mode: str) -> str:
    if mode != "plan":
        return ""
    return """
When mode is plan:
- Research first with read-only tools if needed.
- Do not edit files or run mutating commands.
- End with a numbered plan the UI can render as cards, using this format:

## 计划
1. **任务标题**：这一步要做什么，涉及哪些文件
2. **任务标题**：具体动作与验收标准
3. **任务标题**：...

Each step must start with a number and a bold title, then a colon and one or two sentences.
Ask the user to confirm before implementation.
"""


def build_system_prompt(
    workspace: Workspace,
    mode: str,
    thinking_level: str = "off",
    *,
    skill_name: str | None = None,
    skill_body: str | None = None,
    memory_facts: list[dict] | None = None,
    conversation_summary: str = "",
    workspace_rules: str = "",
) -> str:
    skills = list_skill_catalog(workspace)
    skill_lines = "\n".join(
        f"- {s['name']}: {s['description']}" for s in skills if not s.get("invalid_reason")
    ) or "(none)"
    extra = settings.get("agent.system_prompt_extra") or ""
    prompt = f"""You are Code Agent, a coding assistant working on a real workspace.

Workspace root: {workspace.root_path}
Mode: {mode}
- ask: read-only. Do not write files or run mutating commands.
- plan: research with read-only tools, then propose a numbered plan. Do not implement until the user confirms.
- agent: you may edit files and run commands inside the workspace.

Rules:
- Prefer apply_patch for existing files. Use search_replace only for a single exact string. Use write_file for new files or full rewrites of small files.
- For unfamiliar code, call explore_codebase with a focused goal. It is a read-only sub-agent (search/read only). Implement afterwards with apply_patch; do not edit inside explore_codebase.
- MCP tools are named mcp_<server>_<tool>. Use them for databases, Figma, the browser, or internal APIs when those servers are connected. There is no plugin marketplace.
- For multi-step work, keep a live checklist with todo_write. Replace the full list each call. At most one item may be in_progress. Mark items completed as you go.
- Use list_skills / load_skill when a skill matches the task.
- Use git_status / git_diff / git_log for version control; git_commit, git_push, git_pull, git_checkout, git_stash and git_init require user confirmation.
- Prefer paths relative to the workspace root; absolute paths and ~ are allowed when needed (e.g. ~/.code-agent/skills).
- Be concise. Show your work via tools rather than dumping huge code in chat.
- After edits, mention which files changed.
- Follow workspace rules below when they do not conflict with the user.
{thinking_prompt(thinking_level)}
{plan_format_rules(mode)}

Instruction priority (highest first):
1. The current user message
2. Workspace rules (AGENTS.md and .code-agent/rules), except any the user disabled
3. Pinned workspace memories
4. Other retrieved memories (soft context; discard on conflict with 1–3)
Disabled rules and memories are not injected. The user can pin or turn them off in the Memory panel.

Available skills:
{skill_lines}

{extra}
""".strip()
    if workspace_rules.strip():
        prompt += f"""

## Workspace rules
These files are project instructions (AGENTS.md and .code-agent/rules/). Follow them unless the user explicitly overrides them. Pinned rules are listed first. Disabled rules are omitted.

{workspace_rules.strip()}
"""
    if conversation_summary.strip():
        prompt += f"""

## Earlier conversation summary
{conversation_summary.strip()}
"""
    if memory_facts:
        lines = []
        for fact in memory_facts:
            kind = fact.get("kind") or "note"
            subject = fact.get("subject") or ""
            content = fact.get("content") or {}
            statement = content.get("statement") if isinstance(content, dict) else str(content)
            pin = " [pinned]" if fact.get("pinned") else ""
            lines.append(f"- [{kind}]{pin} {subject}: {statement}")
        if lines:
            prompt += """

## Workspace memory (structured)
Pinned items are durable facts. Other items are soft context.
""" + "\n".join(lines) + """

Use these as context. If the user contradicts them, follow the user and note the conflict.
"""
    if skill_name and skill_body:
        prompt += f"""

## Active skill: {skill_name}
The user selected this skill for the current conversation turn. Follow it closely:

{skill_body}
""".rstrip()
    return prompt
