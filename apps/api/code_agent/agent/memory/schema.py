from __future__ import annotations

MEMORY_KINDS = (
    "profile",
    "preference",
    "goal",
    "context",
    "workflow",
    "decision",
    "architecture",
    "convention",
    "fact",
    "bug_fix",
    "lesson",
    "dependency",
    "todo",
)

# Injected every run (until max_inject cap), even without keyword match.
DEFAULT_ALWAYS_INJECT_KINDS = (
    "profile",
    "preference",
    "convention",
    "goal",
    "workflow",
)

KIND_GUIDE: dict[str, str] = {
    "profile": "User identity: name, nickname, role, team, how to address them (e.g. 我是 Rick，记住我).",
    "preference": "User or team preferences: language, tools, coding style, communication style.",
    "goal": "Project or task goals the user wants to achieve in this workspace.",
    "context": "Stable business/domain background useful across chats (what the product does, key terms).",
    "workflow": "How the user wants to collaborate (plan first, small steps, always run tests, etc.).",
    "decision": "Explicit technical or product decisions already made.",
    "architecture": "System structure: modules, data flow, key components.",
    "convention": "Project conventions: naming, directory layout, API patterns, commit style.",
    "fact": "Stable facts about the repo (ports, env files, entrypoints, key scripts).",
    "bug_fix": "Important bugs fixed and how, so they are not reintroduced.",
    "lesson": "Pitfalls, failed approaches, or warnings learned during work.",
    "dependency": "Important libraries/services and why they are used.",
    "todo": "Explicit follow-ups the user still cares about across sessions.",
}


def build_extract_prompt(*, max_extract: int, conversation_text: str) -> str:
    kind_lines = "\n".join(f"- {k}: {KIND_GUIDE[k]}" for k in MEMORY_KINDS)
    return f"""Extract up to {max_extract} durable workspace memories from this agent turn.
Store facts the user explicitly asked to remember or that clearly help future chats in THIS workspace.
Use the same language as the conversation for subject/statement.

Memory kinds:
{kind_lines}

Rules:
- If the user says their name or asks you to remember them, use kind "profile".
- If the user says 记住/remember/save this, prioritize extracting what they point at.
- Do not store secrets (passwords, API keys, tokens).
- Do not store trivial one-off chit-chat with no future value.
- Merge updates: if a profile name changes, emit the latest fact with the same subject when appropriate.

Return JSON array only:
[{{"kind":"...","subject":"short title","statement":"one clear sentence","tags":["..."],"related_paths":["..."]}}]
If nothing worth storing, return [].

Conversation excerpt:
{conversation_text}"""
