from __future__ import annotations

from typing import Any, Protocol

from code_agent.db.models import Workspace


class WorkspaceBackend(Protocol):
    """Filesystem + exec surface for a workspace (local disk or SSH)."""

    kind: str
    root_path: str

    async def list_dir(self, rel: str = "", extra_ignores: list[str] | None = None) -> list[dict]: ...

    async def read_text(self, rel: str, max_bytes: int | None = None) -> str: ...

    async def read_bytes(self, rel: str, max_bytes: int | None = None) -> bytes: ...

    async def write_text(self, rel: str, content: str) -> None: ...

    async def mkdir(self, rel: str) -> None: ...

    async def create_file(self, rel: str) -> None: ...

    async def rename(self, src: str, dest: str) -> None: ...

    async def copy(self, src: str, dest: str) -> None: ...

    async def delete(self, rel: str) -> None: ...

    async def exists(self, rel: str = ".") -> bool: ...

    async def is_dir(self, rel: str = ".") -> bool: ...

    async def is_file(self, rel: str) -> bool: ...

    async def walk_files(
        self, extra_ignores: list[str] | None = None, limit: int = 5000
    ) -> list[tuple[str, str]]:
        """Return list of (rel_path, abs_or_remote_path)."""

    async def search(
        self,
        query: str,
        *,
        regex: bool = False,
        case_sensitive: bool = False,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        max_hits: int | None = None,
    ) -> list[dict]: ...

    async def run_command(
        self, command: str, *, cwd: str = ".", timeout: int = 90
    ) -> tuple[int, str, str]:
        """Return (exit_code, stdout, stderr)."""

    async def close(self) -> None: ...


def workspace_is_ssh(ws: Workspace | dict[str, Any]) -> bool:
    if isinstance(ws, dict):
        return str(ws.get("kind") or "local").lower() == "ssh"
    return str(getattr(ws, "kind", None) or "local").lower() == "ssh"


async def get_workspace_backend(ws: Workspace) -> WorkspaceBackend:
    kind = str(getattr(ws, "kind", None) or "local").lower()
    if kind == "ssh":
        from code_agent.workspace.ssh import SshWorkspaceBackend

        return await SshWorkspaceBackend.open(ws)
    from code_agent.workspace.local import LocalWorkspaceBackend

    return LocalWorkspaceBackend(ws)
