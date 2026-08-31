from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import settings
from ..schemas import BuildRequest, ChangeSet, ChatMessage
from .llm_router import router

TEXT_EXTENSIONS = {
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".toml", ".yaml", ".yml",
    ".css", ".scss", ".html", ".txt", ".env.example", ".ini", ".cfg", ".rs", ".go", ".java",
}
SKIP_PARTS = {".git", "node_modules", ".next", "dist", "build", ".venv", "venv", "target", "__pycache__"}
SKIP_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"}

SYSTEM = """You are the Builder in a user-controlled coding workspace.
Return a concrete multi-file change set for the user's requested task.
You may create or replace text files, but you do not execute anything.
Never include secrets, credential files, generated dependency folders, binaries, or files outside the workspace.
Prefer the smallest coherent change that accomplishes the task.
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


def _is_text_candidate(path: Path) -> bool:
    if any(part in SKIP_PARTS for part in path.parts):
        return False
    if path.name in SKIP_NAMES or path.name.endswith((".pem", ".key", ".p12", ".pfx")):
        return False
    if path.name in {"Dockerfile", "Makefile", "Procfile", "AGENTS.md"}:
        return True
    return path.suffix.lower() in TEXT_EXTENSIONS


def collect_context(max_files: int = 30, max_total_chars: int = 140_000) -> str:
    root = settings.workspace_path
    candidates: list[Path] = []
    priority_names = {
        "README.md", "AGENTS.md", "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml",
        "docker-compose.yml", "docker-compose.yaml", "tsconfig.json",
    }
    all_files = [p for p in root.rglob("*") if p.is_file() and _is_text_candidate(p)]
    all_files.sort(key=lambda p: (0 if p.name in priority_names else 1, len(p.parts), str(p)))
    candidates.extend(all_files[:max_files])

    sections: list[str] = []
    total = 0
    for path in candidates:
        try:
            if path.stat().st_size > 40_000:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        block = f"\n--- FILE: {rel} ---\n{text}\n"
        if total + len(block) > max_total_chars:
            break
        sections.append(block)
        total += len(block)
    return "".join(sections) or "(workspace currently has no readable project files)"


async def make_changes(request: BuildRequest) -> ChangeSet:
    context = collect_context()
    messages = [
        ChatMessage(role="system", content=SYSTEM),
        ChatMessage(
            role="user",
            content=f"TASK:\n{request.task}\n\nCURRENT WORKSPACE CONTEXT:\n{context}",
        ),
    ]
    _, content = await router.chat(request.provider, messages, request.model)
    data = _extract_json(content)
    result = ChangeSet.model_validate(data)
    if len(result.files) > 50:
        raise ValueError("Builder proposed too many files")
    return result
