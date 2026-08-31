from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .git_tools import diff as git_diff
from .git_tools import status as git_status
from .project import detect_checks, run_check
from .workspace import apply_changes, list_files, mkdir, read_file, write_file


Tool = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    fn: Tool
    description: str
    mutates: bool


TOOLS: dict[str, ToolSpec] = {
    "workspace.list": ToolSpec(list_files, "List files inside the workspace", False),
    "workspace.read": ToolSpec(read_file, "Read a UTF-8 text file inside the workspace", False),
    "workspace.write": ToolSpec(write_file, "Create or replace one file inside the workspace", True),
    "workspace.mkdir": ToolSpec(mkdir, "Create a directory inside the workspace", True),
    "workspace.apply_changes": ToolSpec(apply_changes, "Apply an approved multi-file change set", True),
    "git.status": ToolSpec(git_status, "Show repository status", False),
    "git.diff": ToolSpec(git_diff, "Show repository diff", False),
    "project.detect_checks": ToolSpec(detect_checks, "Detect supported project checks", False),
    "project.run_check": ToolSpec(run_check, "Run a restricted build/test check", True),
}


def validate_tool(name: str) -> ToolSpec:
    tool = TOOLS.get(name)
    if not tool:
        raise KeyError(f"Unknown tool: {name}")
    return tool
