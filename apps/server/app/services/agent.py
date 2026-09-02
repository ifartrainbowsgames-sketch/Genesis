from __future__ import annotations

import json
import re

from ..schemas import AgentPlan, AgentPlanRequest, ChatMessage
from .llm_router import router
from .project_context import compact_summary


SYSTEM = """You are the planning component of a user-controlled coding assistant.
Convert the user's goal into a short, concrete execution plan grounded in the supplied Genesis project index.
Do not claim actions have already happened.
Only suggest tools from this allowlist when useful:
- workspace.list
- workspace.read
- workspace.write
- workspace.mkdir
Return strict JSON with this schema:
{
  "goal": "string",
  "steps": [
    {"id": 1, "title": "string", "description": "string", "tool": null_or_string, "arguments": {}}
  ],
  "notes": ["string"]
}
File-changing actions are proposals only and require user approval later.
"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise ValueError("Planner did not return JSON")
        return json.loads(match.group(0))


async def make_plan(request: AgentPlanRequest) -> AgentPlan:
    project = compact_summary(request.task)
    messages = [
        ChatMessage(role="system", content=SYSTEM),
        ChatMessage(role="user", content=f"TASK:\n{request.task}\n\nPROJECT INDEX:\n{project}"),
    ]
    _, content = await router.chat(request.provider, messages, request.model)
    data = _extract_json(content)
    return AgentPlan.model_validate(data)
