from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from apps.server.app.schemas import AgentPlanRequest
from apps.server.app.services import agent


def test_extract_json_accepts_fenced_json() -> None:
    data = agent._extract_json(
        """```json
        {"goal":"fix tests","steps":[],"notes":["safe"]}
        ```"""
    )

    assert data["goal"] == "fix tests"
    assert data["notes"] == ["safe"]


def test_extract_json_recovers_object_from_model_preamble() -> None:
    data = agent._extract_json(
        'Here is the plan:\n{"goal":"ship","steps":[],"notes":[]}\nDone.'
    )

    assert data == {"goal": "ship", "steps": [], "notes": []}


def test_extract_json_rejects_non_json_output() -> None:
    with pytest.raises(ValueError, match="Planner did not return JSON"):
        agent._extract_json("I would first inspect the repository.")


def test_make_plan_validates_router_output(monkeypatch: pytest.MonkeyPatch) -> None:
    chat = AsyncMock(
        return_value=(
            "qwen3:8b",
            '{"goal":"add tests","steps":[{"id":1,"title":"Inspect","description":"Read the code","tool":"workspace.read","arguments":{"path":"README.md"}}],"notes":[]}',
        )
    )
    monkeypatch.setattr(agent.router, "chat", chat)

    plan = asyncio.run(agent.make_plan(AgentPlanRequest(task="Add tests")))

    assert plan.goal == "add tests"
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "workspace.read"
    chat.assert_awaited_once()
