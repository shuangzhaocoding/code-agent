from __future__ import annotations

import pytest

from code_agent.agent.rules import assemble_rules_prompt, format_rule_section, split_frontmatter
from code_agent.conversation_search import block_search_text, like_escape, make_snippet
from code_agent.tools.patch import PatchError, apply_file_patch, apply_hunks, parse_patch
from code_agent.tools.todos import normalize_todos, render_todo_text


class TestRules:
    def test_frontmatter_and_title(self):
        meta, body = split_frontmatter("---\ntitle: TypeScript\nglobs: **/*.ts\n---\n\nUse strict types.\n")
        assert meta["title"] == "TypeScript"
        assert "strict" in body
        section = format_rule_section(".code-agent/rules/ts.md", body, title=meta["title"])
        assert "### TypeScript" in section
        assert "Use strict types." in section

    def test_assemble_truncates(self):
        sections = ["### A\n" + ("x" * 40), "### B\n" + ("y" * 40)]
        out = assemble_rules_prompt(sections, max_chars=60)
        assert "truncated" in out
        assert "### B" not in out

    def test_load_from_workspace_files(self, tmp_path):
        import asyncio
        from types import SimpleNamespace

        from code_agent.agent.rules import load_rules_from_backend
        from code_agent.workspace.local import LocalWorkspaceBackend

        (tmp_path / "AGENTS.md").write_text("# Project\n- Use pytest\n", encoding="utf-8")
        rules = tmp_path / ".code-agent" / "rules"
        rules.mkdir(parents=True)
        (rules / "api.md").write_text("---\ntitle: API\n---\nKeep handlers thin.\n", encoding="utf-8")
        ws = SimpleNamespace(root_path=str(tmp_path), ignore_globs=[], kind="local")
        text = asyncio.run(load_rules_from_backend(LocalWorkspaceBackend(ws)))
        assert "Use pytest" in text
        assert "Keep handlers thin." in text
        assert "AGENTS.md" in text

    def test_disable_and_pin(self, tmp_path):
        import asyncio
        from types import SimpleNamespace

        from code_agent.agent.rules import (
            apply_rules_state,
            collect_rule_entries,
            load_rules_from_backend,
            save_rules_state,
        )
        from code_agent.workspace.local import LocalWorkspaceBackend

        (tmp_path / "AGENTS.md").write_text("# Project\n- Use pytest\n", encoding="utf-8")
        rules = tmp_path / ".code-agent" / "rules"
        rules.mkdir(parents=True)
        (rules / "api.md").write_text("---\ntitle: API\n---\nKeep handlers thin.\n", encoding="utf-8")
        (rules / "style.md").write_text("---\ntitle: Style\n---\nNo default exports.\n", encoding="utf-8")
        ws = SimpleNamespace(root_path=str(tmp_path), ignore_globs=[], kind="local")
        fs = LocalWorkspaceBackend(ws)

        async def _run():
            await save_rules_state(fs, {"disabled": ["AGENTS.md"], "pinned": [".code-agent/rules/style.md"]})
            entries = apply_rules_state(await collect_rule_entries(fs), {"disabled": ["AGENTS.md"], "pinned": [".code-agent/rules/style.md"]})
            text = await load_rules_from_backend(fs)
            return entries, text

        entries, text = asyncio.run(_run())
        assert entries[0]["path"].endswith("style.md")
        assert "Use pytest" not in text
        assert "No default exports." in text
        assert "Keep handlers thin." in text


class TestMemorySelect:
    def test_skip_disabled_and_pin_first(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace

        from code_agent.agent.memory.retrieve import select_memories

        now = datetime.now(timezone.utc)

        def row(subject: str, **kwargs):
            return SimpleNamespace(
                id=subject,
                kind=kwargs.get("kind", "fact"),
                subject=subject,
                tags=[],
                content={"statement": subject},
                source=kwargs.get("source") or {},
                updated_at=now,
            )

        picked = select_memories(
            [
                row("off", source={"enabled": False}),
                row("pinned-later", kind="todo", source={"pinned": True}),
                row("profile", kind="profile"),
                row("other", kind="fact"),
            ],
            "other",
            max_inject=10,
            always_kinds={"profile"},
            always_cap=5,
        )
        subjects = [item.subject for item in picked]
        assert "off" not in subjects
        assert subjects[0] == "pinned-later"
        assert "profile" in subjects
        assert "other" in subjects


class TestExplore:
    def test_read_only_and_nested_guard(self):
        import asyncio

        from code_agent.tools.explore import READ_TOOL_NAMES, _exploring, explore_codebase

        assert "write_file" not in READ_TOOL_NAMES
        assert "apply_patch" not in READ_TOOL_NAMES
        token = _exploring.set(True)
        try:
            fn = getattr(explore_codebase, "coroutine", None) or getattr(explore_codebase, "func")
            result = asyncio.run(fn(goal="find auth"))
        finally:
            _exploring.reset(token)
        assert "nested" in result


class TestPatch:
    def test_v4a_update(self):
        original = "alpha\nbeta\ngamma\n"
        patch = """*** Begin Patch
*** Update File: demo.py
@@
 alpha
-beta
+BETA
 gamma
*** End Patch
"""
        ops = parse_patch(patch)
        assert ops[0].path == "demo.py"
        assert apply_file_patch(original, ops[0]) == "alpha\nBETA\ngamma\n"

    def test_v4a_add_and_delete(self):
        patch = """*** Begin Patch
*** Add File: hello.py
+print("hi")
*** Delete File: old.py
*** End Patch
"""
        ops = parse_patch(patch)
        assert [op.kind for op in ops] == ["add", "delete"]
        assert apply_file_patch(None, ops[0]) == 'print("hi")\n'
        assert apply_file_patch("x", ops[1]) is None

    def test_unified_diff(self):
        original = "one\ntwo\nthree\n"
        patch = """--- a/n.txt
+++ b/n.txt
@@ -1,3 +1,3 @@
 one
-two
+TWO
 three
"""
        ops = parse_patch(patch)
        assert ops[0].path == "n.txt"
        assert apply_hunks(original, ops[0].hunks) == "one\nTWO\nthree\n"

    def test_missing_context_errors(self):
        original = "alpha\n"
        patch = """*** Update File: a.py
@@
 no-such-line
-old
+new
"""
        ops = parse_patch(patch)
        with pytest.raises(PatchError):
            apply_file_patch(original, ops[0])

    def test_markdown_fence(self):
        patch = """```patch
*** Update File: a.py
@@
-foo
+bar
```"""
        ops = parse_patch(patch, default_path="a.py")
        assert apply_file_patch("foo\n", ops[0]) == "bar\n"


class TestTodos:
    def test_normalize_and_single_in_progress(self):
        items = normalize_todos(
            [
                {"id": "1", "content": "Read files", "status": "completed"},
                {"id": "2", "content": "Patch", "status": "in_progress"},
                {"id": "3", "content": "Also doing", "status": "doing"},
            ]
        )
        assert items[1]["status"] == "in_progress"
        assert items[2]["status"] == "pending"
        text = render_todo_text(items)
        assert "[x] Read files" in text
        assert "[>] Patch" in text

    def test_json_string(self):
        items = normalize_todos('[{"content":"Ship it","status":"done"}]')
        assert items[0]["status"] == "completed"


class TestSearchHelpers:
    def test_like_escape_and_snippet(self):
        assert like_escape("a%b_c") == r"a\%b\_c"
        text = "please explain the auth middleware in src/auth.ts now"
        snippet = make_snippet(text, "auth middleware")
        assert "auth middleware" in snippet

    def test_block_search_text(self):
        text = block_search_text(
            [
                {"type": "user.text", "text": "fix login"},
                {"type": "todo", "text": "[>] patch files"},
                {"type": "file.diff", "meta": {"path": "a.py"}},
            ]
        )
        assert "fix login" in text
        assert "patch files" in text
        assert "a.py" in text
