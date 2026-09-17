"""Strip ANSI / VT escape sequences, including across chunk boundaries."""

from __future__ import annotations

import re

# CSI / OSC / other ESC sequences (complete).
_ANSI_RE = re.compile(
    r"(?:"
    r"\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)"  # OSC
    r"|\x1B[@-Z\\-_]"  # 2-byte
    r"|\x1B\[[0-?]*[ -/]*[@-~]"  # CSI
    r"|\x9B[0-?]*[ -/]*[@-~]"  # 8-bit CSI
    r")"
)

# Incomplete ESC suffix to hold until the next chunk.
_INCOMPLETE_RE = re.compile(
    r"(?:"
    r"\x1B$"
    r"|\x1B\[[0-?]*[ -/]*$"
    r"|\x1B\][^\x07\x1B]*$"
    r"|\x9B[0-?]*[ -/]*$"
    r")$"
)

# Orphan SGR like "[32m" / "[0m" when ESC was lost mid-stream.
_ORPHAN_SGR_RE = re.compile(r"\[[\d;]{0,16}m")


def strip_ansi(text: str) -> str:
    if not text:
        return text
    out = _ANSI_RE.sub("", text)
    # Residue when ESC and CSI body arrived in different chunks without a filter.
    out = _ORPHAN_SGR_RE.sub("", out)
    return out


class AnsiStreamFilter:
    """Stateful stripper so ESC sequences split across reads stay intact."""

    __slots__ = ("_pending",)

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, chunk: str) -> str:
        data = f"{self._pending}{chunk or ''}"
        self._pending = ""
        if not data:
            return ""
        hold = ""
        m = _INCOMPLETE_RE.search(data)
        if m:
            hold = m.group(0)
            data = data[: m.start()]
        self._pending = hold
        return strip_ansi(data)

    def flush(self) -> str:
        leftover = self._pending
        self._pending = ""
        return strip_ansi(leftover) if leftover else ""
