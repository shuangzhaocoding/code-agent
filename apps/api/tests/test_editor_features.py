from __future__ import annotations

from code_agent.editor.inline_edit import build_inline_prompt, strip_code_fences
from code_agent.editor.symbols import rank_symbol_hits, score_definition_hit


class TestInlineEdit:
    def test_strip_fences(self):
        assert strip_code_fences("```python\nx = 1\n```") == "x = 1"
        assert strip_code_fences("plain") == "plain"

    def test_prompt_contains_selection(self):
        prompt = build_inline_prompt(
            path="a.py",
            language="python",
            instruction="rename to bar",
            selection="def foo():\n    return 1\n",
            prefix="x = 1\n",
        )
        assert "def foo" in prompt
        assert "rename to bar" in prompt
        assert "a.py" in prompt


class TestSymbols:
    def test_definition_outranks_call(self):
        defn = score_definition_hit("foo", "a.py", "def foo():")
        call = score_definition_hit("foo", "a.py", "    foo()")
        assert defn >= 70
        assert defn > call

    def test_same_file_bonus(self):
        here = score_definition_hit("Foo", "src/foo.ts", "export class Foo {", from_path="src/foo.ts")
        other = score_definition_hit("Foo", "src/foo.ts", "export class Foo {", from_path="src/bar.ts")
        assert here > other

    def test_rank_prefers_definitions(self):
        hits = rank_symbol_hits(
            "load",
            [
                {"path": "a.py", "line": 3, "text": "    load()"},
                {"path": "a.py", "line": 1, "text": "def load():"},
                {"path": "b.py", "line": 8, "text": "from a import load"},
            ],
            from_path="a.py",
        )
        assert hits[0]["kind"] == "definition"
        assert hits[0]["line"] == 1
        assert all(row["kind"] == "definition" for row in hits)
