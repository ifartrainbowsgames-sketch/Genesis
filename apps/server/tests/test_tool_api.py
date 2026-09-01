from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from apps.server.app import main
from apps.server.app.schemas import ToolExecuteRequest, ToolProposalRequest, ToolReadRequest
from apps.server.app.services.approvals import ApprovalStore
from apps.server.app.tools.registry import ToolSpec


def test_execute_requires_explicit_approval() -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(main.execute_tool(ToolExecuteRequest(approval_id="unused", approved=False)))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Explicit approval is required"


def test_read_endpoint_allows_non_mutating_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    def read_only(value: str) -> dict[str, str]:
        return {"value": value}

    monkeypatch.setattr(main, "validate_tool", lambda _: ToolSpec(read_only, "read", False))
    result = asyncio.run(main.read_tool(ToolReadRequest(tool="test.read", arguments={"value": "ok"})))
    assert result.result == {"value": "ok"}


def test_read_endpoint_rejects_mutating_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "validate_tool", lambda _: ToolSpec(lambda: {"bad": True}, "write", True))
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(main.read_tool(ToolReadRequest(tool="test.write", arguments={})))
    assert exc_info.value.status_code == 403


def test_proposal_and_execution_use_stored_tool_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    store = ApprovalStore()
    calls: list[str] = []

    def echo(value: str) -> dict[str, str]:
        calls.append(value)
        return {"echo": value}

    def validate(name: str) -> ToolSpec:
        if name != "test.echo":
            raise KeyError(name)
        return ToolSpec(echo, "test echo", True)

    monkeypatch.setattr(main, "approvals", store)
    monkeypatch.setattr(main, "validate_tool", validate)

    proposal = asyncio.run(main.propose_tool(ToolProposalRequest(tool="test.echo", arguments={"value": "approved-value"})))
    result = asyncio.run(main.execute_tool(ToolExecuteRequest(approval_id=proposal.approval_id, approved=True)))

    assert result.tool == "test.echo"
    assert result.result == {"echo": "approved-value"}
    assert calls == ["approved-value"]

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(main.execute_tool(ToolExecuteRequest(approval_id=proposal.approval_id, approved=True)))
    assert exc_info.value.status_code == 404


def test_propose_rejects_unknown_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(_: str) -> ToolSpec:
        raise KeyError("Unknown tool: bad.tool")

    monkeypatch.setattr(main, "validate_tool", reject)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(main.propose_tool(ToolProposalRequest(tool="bad.tool", arguments={})))

    assert exc_info.value.status_code == 404
