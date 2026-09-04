from __future__ import annotations

import fnmatch
import re
import shlex
from pathlib import PurePosixPath

from code_agent.config import settings

# Split shell pipelines / chains into individual segments.
_SEGMENT_SPLIT = re.compile(r"(?:\|\||&&|\||;|\n)+")

# Leading VAR=value assignments before the executable.
_ENV_PREFIX = re.compile(r"^(?:\w+=\S+\s+)+")

# Common obfuscation: $(cmd), `cmd`, ${cmd}, /path/to/binary
_INVOCATION = re.compile(
    r"(?:^|[\s;&|]|(?:\$\(|\`|(?:^|[\s;&|])\$\{))"
    r"(\/?(?:[\w.-]+\/)*[\w.-]+)"
)

_BLOCKED_BINARIES = frozenset(
    {
        "sudo",
        "su",
        "doas",
        "pkexec",
        "mkfs",
        "mkfs.ext4",
        "mkfs.ext3",
        "mkfs.vfat",
        "shutdown",
        "reboot",
        "halt",
        "poweroff",
        "init",
        "dd",
        "mount",
        "umount",
        "iptables",
        "nft",
        "userdel",
        "deluser",
        "groupdel",
        "chroot",
    }
)

# Hard block regardless of auto_run level.
_BLOCK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"rm\s+(-[^\s]*\s+)*-[^\s]*r[^\s]*\s+(-[^\s]*\s+)*(/|\~|\$HOME\b|\$\{HOME\})", re.I),
    re.compile(r"rm\s+(-[^\s]*\s+)*-[^\s]*f[^\s]*\s+(-[^\s]*\s+)*(/|\~|\$HOME\b|\$\{HOME\})", re.I),
    re.compile(r"\brm\s+-[^\s]*rf\b", re.I),
    re.compile(r"\bdd\s+if=", re.I),
    re.compile(r"\bmkfs\b", re.I),
    re.compile(r":\(\)\s*\{", re.I),
    re.compile(r"\bcurl\b[^\n|]*\|\s*(?:ba)?sh\b", re.I),
    re.compile(r"\bwget\b[^\n|]*\|\s*(?:ba)?sh\b", re.I),
    re.compile(r"\bchmod\s+(-[^\s]+\s+)*777\s+/", re.I),
    re.compile(r"\bchown\s+(-[^\s]+\s+)*[^\s]+\s+/", re.I),
    re.compile(r"(?:^|[\s;&|])>\s*>?\s*(?:~|\$HOME|/etc/|/root/|~\/\.ssh)", re.I),
    re.compile(r"(?:^|[\s;&|])(?:cat|tee|cp|mv)\s+[^\n|]*(?:~\/\.ssh|/etc/passwd|/etc/shadow)", re.I),
)

# Require user approval when not in full auto_run mode.
_DANGEROUS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\brm\s", re.I),
    re.compile(r"\bchmod\s", re.I),
    re.compile(r"\bchown\s", re.I),
    re.compile(r"\bgit\s+push\b", re.I),
    re.compile(r"\bgit\s+reset\b", re.I),
    re.compile(r"\bgit\s+clean\b", re.I),
    re.compile(r"\bgit\s+rebase\b", re.I),
    re.compile(r"\bgit\s+checkout\s+-f\b", re.I),
    re.compile(r"\bgit\s+checkout\s+--force\b", re.I),
    re.compile(r"(?:^|\s)--force\b", re.I),
    re.compile(r"\bcurl\b[^\n|]*\|\s*(?:ba)?sh\b", re.I),
    re.compile(r"\bwget\b[^\n|]*\|\s*(?:ba)?sh\b", re.I),
    re.compile(r"\bpip\s+install\b", re.I),
    re.compile(r"\bnpm\s+install\b", re.I),
    re.compile(r"\bpnpm\s+install\b", re.I),
    re.compile(r"\byarn\s+add\b", re.I),
)

_DEFAULT_WHITELIST: tuple[str, ...] = (
    "pwd",
    "ls",
    "ls *",
    "cat *",
    "head *",
    "tail *",
    "echo",
    "echo *",
    "printf *",
    "which *",
    "type *",
    "env",
    "printenv",
    "printenv *",
    "wc *",
    "sort *",
    "uniq *",
    "grep *",
    "rg *",
    "find *",
    "test *",
    "[ *",
    "true",
    "false",
    "mkdir *",
    "touch *",
    "cp *",
    "mv *",
    "npm run *",
    "npm test",
    "npm test *",
    "npm ci",
    "npm ci *",
    "npx *",
    "pnpm run *",
    "pnpm test",
    "pnpm test *",
    "yarn run *",
    "yarn test",
    "yarn test *",
    "node *",
    "python *",
    "python3 *",
    "pytest *",
    "pip show *",
    "pip list*",
    "uv run *",
    "uv pip *",
    "make *",
    "cargo build *",
    "cargo test *",
    "cargo run *",
    "cargo check *",
    "go build *",
    "go test *",
    "go run *",
    "go vet *",
    "tsc *",
    "vite *",
    "eslint *",
    "prettier *",
    "black *",
    "ruff *",
    "mypy *",
    "git status*",
    "git diff*",
    "git log*",
    "git branch*",
    "git show*",
    "git rev-parse*",
    "git remote -v*",
    "docker compose *",
    "docker-compose *",
    "docker ps*",
    "docker logs*",
)


def split_shell_segments(command: str) -> list[str]:
    text = (command or "").strip()
    if not text:
        return []
    parts = [part.strip() for part in _SEGMENT_SPLIT.split(text)]
    return [part for part in parts if part]


def _strip_env_prefix(segment: str) -> str:
    return _ENV_PREFIX.sub("", segment.strip(), count=1).strip()


def _unwrap_cd_and(segment: str) -> str:
    text = _strip_env_prefix(segment)
    if text.lower().startswith("cd ") and " && " in text:
        return text.split(" && ", 1)[1].strip()
    return text


def _basename(token: str) -> str:
    token = token.strip().strip("\"'")
    if token.startswith("$"):
        return token.lstrip("$")
    return PurePosixPath(token).name.lower()


def iter_invocations(segment: str) -> list[str]:
    """Extract executable tokens from one shell segment."""
    text = _unwrap_cd_and(segment)
    found: list[str] = []
    seen: set[str] = set()

    def _add(token: str) -> None:
        base = _basename(token)
        if not base or base in seen:
            return
        seen.add(base)
        found.append(base)

    try:
        tokens = shlex.split(text, posix=True)
    except ValueError:
        tokens = text.split()

    if tokens:
        _add(tokens[0])

    for match in _INVOCATION.finditer(text):
        _add(match.group(1))

    return found


def _normalize_segment(segment: str) -> str:
    return " ".join(_unwrap_cd_and(segment).split())


def _config_blacklist_patterns() -> list[str]:
    return [str(item).strip().lower() for item in (settings.get("policy.command_blacklist") or []) if str(item).strip()]


def _config_item_matches(command: str, item: str) -> bool:
    """Match config blacklist entries without substring false positives."""
    if any(ch in item for ch in (" ", "/", "|", "&", ";", ">", "(", "$")):
        return item in command.lower()
    for segment in split_shell_segments(command):
        if item in iter_invocations(segment):
            return True
    return bool(re.search(rf"\b{re.escape(item)}\b", command, re.I))


def _matches_config_blacklist(text: str) -> bool:
    return any(_config_item_matches(text, item) for item in _config_blacklist_patterns())


def _pipe_to_shell_blocked(segments: list[str]) -> bool:
    for idx, segment in enumerate(segments):
        if not re.search(r"\b(curl|wget)\b", segment, re.I):
            continue
        if re.search(r"\|\s*(?:ba)?sh\b", segment, re.I):
            return True
        if idx + 1 < len(segments) and re.match(r"^\s*(?:ba)?sh\b", segments[idx + 1], re.I):
            return True
    return False


def _matches_patterns(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def segment_is_blocked(segment: str) -> bool:
    normalized = _normalize_segment(segment)
    if not normalized:
        return False
    if _matches_patterns(normalized, _BLOCK_PATTERNS):
        return True
    for name in iter_invocations(segment):
        if name in _BLOCKED_BINARIES:
            return True
    return False


def segment_is_dangerous(segment: str) -> bool:
    normalized = _normalize_segment(segment)
    if not normalized:
        return False
    if segment_is_blocked(normalized):
        return False
    if _matches_patterns(normalized, _DANGEROUS_PATTERNS):
        return True
    return False


def is_command_blocked(command: str) -> bool:
    segments = split_shell_segments(command)
    if not segments:
        return False
    from code_agent.ports.protected import command_targets_protected_port

    if command_targets_protected_port(command) is not None:
        return True
    if _pipe_to_shell_blocked(segments):
        return True
    if _matches_config_blacklist(command):
        return True
    return any(segment_is_blocked(segment) for segment in segments)


def command_needs_confirm(command: str) -> bool:
    segments = split_shell_segments(command)
    if not segments:
        return False
    if is_command_blocked(command):
        return False
    return any(segment_is_dangerous(segment) for segment in segments)


def _whitelist_patterns() -> list[str]:
    configured = settings.get("policy.command_whitelist")
    if isinstance(configured, list) and configured:
        return [str(item).strip() for item in configured if str(item).strip()]
    return list(_DEFAULT_WHITELIST)


def _segment_matches_whitelist(segment: str, patterns: list[str]) -> bool:
    normalized = _normalize_segment(segment)
    if not normalized:
        return False
    for pat in patterns:
        if fnmatch.fnmatchcase(normalized, pat):
            return True
    return False


def command_allowed_in_sandbox(command: str) -> bool:
    """True when every shell segment matches the sandbox whitelist."""
    segments = split_shell_segments(command)
    if not segments:
        return False
    if is_command_blocked(command):
        return False
    patterns = _whitelist_patterns()
    return all(_segment_matches_whitelist(segment, patterns) for segment in segments)
