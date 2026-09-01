from __future__ import annotations

import json
import re

from ..schemas import ChangeSet, ChatMessage, Provider, ReviewReport
from .llm_router import router

SYSTEM = """You are the Reviewer in a user-controlled coding workstation.
Review a proposed change set against the user's task. Be concrete and technical.
Do not invent files that are not in the proposal. Do not execute tools.
Use blocking only for issues that should prevent the human from applying the patch.
Return STRICT JSON only:
{
  "verdict": "approve|changes_requested",
  "summary": "string",
  "issues": [
    {"severity": "info|warning|blocking", "file": "relative/path or null", "message": "string"}
  ],
  "notes": ["string"]
}
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
            raise ValueError("Reviewer did not return JSON")
        return json.loads(match.group(0))


async def review_changes(task: str, changes: ChangeSet, provider: Provider, model: str | None = None) -> ReviewReport:
    payload = changes.model_dump_json(indent=2)
    if len(payload) > 180_000:
        payload = payload[:180_000] + "\n... review input truncated ..."
    messages = [
        ChatMessage(role="system", content=SYSTEM),
        ChatMessage(role="user", content=f"TASK:\n{task}\n\nPROPOSED CHANGE SET:\n{payload}"),
    ]
    _, content = await router.chat(provider, messages, model)
    return ReviewReport.model_validate(_extract_json(content))
