from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..services.workers import run_external_worker_tool
from .git_tools import diff as git_diff
from .git_tools import status as git_status
from .github_tools import create_branch as github_create_branch
from .github_tools import create_pull_request as github_create_pull_request
from .github_tools import list_dir as github_list_dir
from .github_tools import read_file as github_read_file
from .github_tools import repo_info as github_repo_info
from .github_tools import upsert_file as github_upsert_file
from .mcp_tools import call_tool as mcp_call_tool
from .mcp_tools import list_tools as mcp_list_tools
from .mcp_tools import servers as mcp_servers
from .project import detect_checks, run_check
from .workspace import apply_changes, checkpoints, list_files, mkdir, read_file, undo_changes, write_file


ToolResult = dict[str, Any]
Tool = Callable[..., ToolResult | Awaitable[ToolResult]]


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
    "workspace.apply_changes": ToolSpec(apply_changes, "Apply an approved multi-file change set and create a safe undo checkpoint", True),
    "workspace.checkpoints": ToolSpec(checkpoints, "List safe Genesis change checkpoints for the active workspace", False),
    "workspace.undo_changes": ToolSpec(undo_changes, "Restore one Genesis checkpoint if affected files have not changed since apply", True),
    "git.status": ToolSpec(git_status, "Show repository status", False),
    "git.diff": ToolSpec(git_diff, "Show repository diff", False),
    "github.repo_info": ToolSpec(github_repo_info, "Read GitHub repository metadata", False),
    "github.list_dir": ToolSpec(github_list_dir, "List a directory in an approved GitHub repository", False),
    "github.read_file": ToolSpec(github_read_file, "Read a text file from an approved GitHub repository", False),
    "github.upsert_file": ToolSpec(github_upsert_file, "Create or safely replace one GitHub file", True),
    "github.create_branch": ToolSpec(github_create_branch, "Create a GitHub branch from an existing branch", True),
    "github.create_pull_request": ToolSpec(github_create_pull_request, "Open a GitHub pull request", True),
    "mcp.servers": ToolSpec(mcp_servers, "List explicitly configured MCP servers", False),
    "mcp.list_tools": ToolSpec(mcp_list_tools, "List tools advertised by an allowlisted MCP server", False),
    "mcp.call_tool": ToolSpec(mcp_call_tool, "Call a tool on an allowlisted MCP server", True),
    "project.detect_checks": ToolSpec(detect_checks, "Detect supported project checks", False),
    "project.run_check": ToolSpec(run_check, "Run a restricted build/test check", True),
    "worker.run": ToolSpec(run_external_worker_tool, "Run an explicitly allowlisted external worker", True),
}


def validate_tool(name: str) -> ToolSpec:
    tool = TOOLS.get(name)
    if not tool:
        raise KeyError(f"Unknown tool: {name}")
    return tool
