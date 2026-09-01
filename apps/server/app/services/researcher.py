from __future__ import annotations

import re

from ..schemas import ChatMessage, ResearchReport, ResearchRequest
from .llm_router import router
from .research_broker import ResearchBrokerError, search_sources


SYSTEM = """You are the Researcher in a user-controlled AI workstation.
Use only the supplied search-result sources. Do not invent facts, URLs, quotes, or citations.
Every factual claim that depends on the supplied sources should cite one or more source IDs exactly like [S1] or [S2].
Clearly distinguish uncertainty, conflicting evidence, and gaps in the source snippets.
Prefer concise synthesis over copying snippets. Do not claim that you opened or read pages beyond the supplied snippets.
"""


def _source_context(sources) -> str:
    blocks: list[str] = []
    for source in sources:
        blocks.append(
            f"[{source.id}] {source.title}\nURL: {source.url}\nEngine: {source.engine or 'unknown'}\nSnippet: {source.snippet or '(no snippet)'}"
        )
    return "\n\n".join(blocks)


async def research(request: ResearchRequest) -> ResearchReport:
    sources = await search_sources(
        request.query,
        max_results=request.max_results,
        language=request.language,
        time_range=request.time_range,
        safesearch=request.safesearch,
    )
    if not sources:
        raise ResearchBrokerError("The configured search broker returned no usable sources")

    messages = [
        ChatMessage(role="system", content=SYSTEM),
        ChatMessage(
            role="user",
            content=(
                f"RESEARCH QUESTION:\n{request.query}\n\n"
                f"SEARCH SOURCES:\n{_source_context(sources)}\n\n"
                "Write a source-grounded answer. Cite source IDs inline."
            ),
        ),
    ]
    model, answer = await router.chat(request.provider, messages, request.model)

    allowed = {source.id for source in sources}
    cited = set(re.findall(r"\[(S\d+)\]", answer))
    notes: list[str] = []
    unknown = sorted(cited - allowed)
    if unknown:
        notes.append("Model emitted unknown source IDs: " + ", ".join(unknown))
    if not cited:
        notes.append("The synthesis did not include inline source IDs; inspect the source list before relying on it.")

    return ResearchReport(
        query=request.query,
        answer=answer,
        sources=sources,
        provider=request.provider,
        model=model,
        notes=notes,
    )
