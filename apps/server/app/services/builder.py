from __future__ import annotations

import json
import re

from ..schemas import BuildRequest, ChangeSet, ChatMessage
from .llm_router import router
from .project_context import context_for


SYSTEM = """You are the Builder in a user-controlled coding workspace.
Return a concrete multi-file change set for the user's requested task.
You may create or replace text files, but you do not execute anything.
Never include secrets, credential files, generated dependency folders, binaries, or files outside the workspace.
Prefer the smallest coherent change that accomplishes the task.
Use the bounded project context supplied by Genesis. Do not invent files or APIs that are not supported by that context.
Return STRICT JSON only with this schema:
{
  "summary": "string",
  "files": [
    {"path": "relative/path", "action": "create|replace", "content": "full final file content", "reason": "string"}
  ],
  "recommended_checks": [
    {"kind": "python_compile|python_test|npm_build|npm_test|cargo_check|cargo_test", "cwd": "."}
  ],
  "notes": ["string"]
}
The returned files are proposals. A human will inspect and approve them before application.
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
            raise ValueError("Builder did not return JSON")
        return json.loads(match.group(0))


async def make_changes(request: BuildRequest) -> ChangeSet:
    context, used_files = context_for(request.task, max_files=24, max_total_chars=120_000)
    used = ", ".join(used_files) if used_files else "none"
    messages = [
        ChatMessage(role="system", content=SYSTEM),
        ChatMessage(
            role="user",
            content=(
                f"TASK:\n{request.task}\n\n"
                f"GENESIS CONTEXT USED:\n{used}\n\n"
                f"CURRENT WORKSPACE CONTEXT:\n{context}"
            ),
        ),
    ]
    _, content = await router.chat(request.provider, messages, request.model)
    data = _extract_json(content)
    result = ChangeSet.model_validate(data)
    if len(result.files) > 50:
        raise ValueError("Builder proposed too many files")
    return result
