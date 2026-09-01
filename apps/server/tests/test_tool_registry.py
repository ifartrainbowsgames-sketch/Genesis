from __future__ import annotations

import pytest

from apps.server.app.tools.registry import TOOLS, validate_tool


def test_mutating_tools_are_explicitly_marked() -> None:
    assert TOOLS["workspace.read"].mutates is False
    assert TOOLS["workspace.write"].mutates is True
    assert TOOLS["workspace.apply_changes"].mutates is True
    assert TOOLS["github.upsert_file"].mutates is True
    assert TOOLS["github.create_branch"].mutates is True
    assert TOOLS["github.create_pull_request"].mutates is True
    assert TOOLS["mcp.call_tool"].mutates is True
    assert TOOLS["project.run_check"].mutates is True


def test_validate_tool_rejects_unknown_names() -> None:
    with pytest.raises(KeyError, match="Unknown tool"):
        validate_tool("shell.exec")
