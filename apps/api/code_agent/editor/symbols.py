from __future__ import annotations

import posixpath
import re

# High-confidence declaration patterns. `{name}` is replaced with the escaped symbol.
_DEF_PATTERNS: tuple[tuple[str, int], ...] = (
    (r"^\s*(export\s+)?(default\s+)?(async\s+)?function\s*\*?\s*{name}\b", 100),
    (r"^\s*(export\s+)?(default\s+)?class\s+{name}\b", 100),
    (r"^\s*(async\s+)?def\s+{name}\s*\(", 100),
    (r"^\s*(pub(\s*\([^)]+\))?\s+)?(async\s+)?fn\s+{name}\b", 100),
    (r"^\s*(export\s+)?(type|interface|enum|struct|trait|impl)\s+{name}\b", 95),
    (r"^\s*(func|function)\s+{name}\s*\(", 95),
    (r"^\s*(export\s+)?(const|let|var)\s+{name}\b", 80),
    (r"^\s*{name}\s*=\s*(async\s+)?(function\b|\(|class\b)", 70),
    (r"^\s*(public|private|protected|static|async)[\w\s<>,]*\b{name}\s*\(", 75),
    (r"^\s*(macro_rules|mod|trait|enum|struct|type)\s+{name}\b", 90),
)

_COMMENT_PREFIXES = ("#", "//", "*", "/*", "--", "<!--")


def _is_comment(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(_COMMENT_PREFIXES)


def score_definition_hit(
    symbol: str,
    path: str,
    text: str,
    *,
    from_path: str = "",
) -> int:
    name = (symbol or "").strip()
    if not name or not re.search(r"[\w$]", name):
        return 0
    line = (text or "").rstrip()
    if not line.strip() or _is_comment(line):
        return 0
    escaped = re.escape(name)
    if not re.search(rf"(?<![\w$]){escaped}(?![\w$])", line):
        return 0

    score = 8  # bare mention / reference
    for pattern, pts in _DEF_PATTERNS:
        if re.search(pattern.format(name=escaped), line):
            score = max(score, pts)

    base = posixpath.basename(path or "")
    stem = base.rsplit(".", 1)[0] if base else ""
    if stem.lower() == name.lower():
        score += 20
    if from_path and path == from_path:
        score += 12
    return score


def rank_symbol_hits(
    symbol: str,
    hits: list[dict],
    *,
    from_path: str = "",
    limit: int = 20,
) -> list[dict]:
    ranked: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for hit in hits:
        path = str(hit.get("path") or "")
        try:
            line = int(hit.get("line") or 0)
        except (TypeError, ValueError):
            line = 0
        text = str(hit.get("text") or "")
        key = (path, line)
        if not path or key in seen:
            continue
        seen.add(key)
        score = score_definition_hit(symbol, path, text, from_path=from_path)
        if score <= 0:
            continue
        kind = "definition" if score >= 70 else "reference"
        ranked.append({"path": path, "line": line, "text": text[:240], "score": score, "kind": kind})

    ranked.sort(key=lambda row: (-int(row["score"]), row["path"], int(row["line"])))
    defs = [row for row in ranked if row["kind"] == "definition"]
    chosen = defs or ranked
    return chosen[: max(1, min(int(limit or 20), 40))]
