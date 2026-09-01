from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any

from sqlalchemy import select, update

from ..config import settings
from ..db import SessionLocal
from ..models import EvolutionCandidate, EvolutionEvalRun
from ..schemas import (
    ChatMessage,
    EvolutionCandidateInfo,
    EvolutionRunRequest,
    EvolutionRunResponse,
    PromptEvalCase,
)
from .llm_router import router

logger = logging.getLogger(__name__)


def _json_object(text: str) -> dict[str, Any]:
    value = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", value, re.DOTALL | re.IGNORECASE)
    if fenced:
        value = fenced.group(1)
    else:
        start, end = value.find("{"), value.rfind("}")
        if start >= 0 and end > start:
            value = value[start : end + 1]
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("Evolution response must be a JSON object")
    return data


def score_output(output: str, case: PromptEvalCase) -> tuple[float, dict[str, Any]]:
    lowered = output.casefold()
    missing = [value for value in case.expected_contains if value.casefold() not in lowered]
    forbidden = [value for value in case.forbidden_contains if value.casefold() in lowered]
    expected_total = max(1, len(case.expected_contains))
    expected_score = (len(case.expected_contains) - len(missing)) / expected_total if case.expected_contains else 1.0
    forbidden_penalty = min(1.0, len(forbidden) / max(1, len(case.forbidden_contains))) if forbidden else 0.0
    score = max(0.0, expected_score - forbidden_penalty)
    passed = not missing and not forbidden
    return score, {"name": case.name, "passed": passed, "score": score, "missing": missing, "forbidden_found": forbidden}


async def _evaluate_prompt(prompt: str, request: EvolutionRunRequest) -> tuple[float, bool, list[dict[str, Any]], float]:
    scores: list[float] = []
    results: list[dict[str, Any]] = []
    started = time.perf_counter()
    for case in request.cases[: settings.evolution_max_cases]:
        _, output = await router.chat(
            request.provider,
            [
                ChatMessage(role="system", content=prompt),
                ChatMessage(role="user", content=case.input),
            ],
            request.model,
        )
        score, result = score_output(output, case)
        result["output_preview"] = output[:1000]
        scores.append(score)
        results.append(result)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    overall = sum(scores) / len(scores) if scores else 0.0
    return overall, all(item["passed"] for item in results), results, elapsed_ms


async def _generate_variants(request: EvolutionRunRequest) -> list[str]:
    count = min(request.variants, settings.evolution_max_variants)
    instruction = (
        "You are optimizing a system prompt. Produce bounded prompt variants, not answers to the task. "
        "Preserve the original intent and safety constraints. Improve clarity, instruction ordering, and testability. "
        f"Return ONLY JSON with this shape: {{\"variants\":[\"...\"]}}. Return exactly {count} variants.\n\n"
        f"BASE PROMPT:\n{request.base_prompt}\n\n"
        "EVALUATION CASE NAMES:\n" + "\n".join(f"- {case.name}" for case in request.cases)
    )
    _, content = await router.chat(
        request.provider,
        [ChatMessage(role="user", content=instruction)],
        request.model,
    )
    data = _json_object(content)
    variants = data.get("variants")
    if not isinstance(variants, list):
        raise ValueError("Evolution model did not return a variants array")
    cleaned: list[str] = []
    seen = {request.base_prompt.strip()}
    for value in variants:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
        if len(cleaned) >= count:
            break
    if not cleaned:
        raise ValueError("Evolution model returned no usable prompt variants")
    return cleaned


def _candidate_info(row: EvolutionCandidate) -> EvolutionCandidateInfo:
    try:
        metrics = json.loads(row.metrics or "{}")
    except Exception:
        metrics = {}
    return EvolutionCandidateInfo(
        id=str(row.id),
        name=row.name,
        kind=row.kind,
        content=row.content,
        status=row.status,
        score=row.score,
        baseline_score=row.baseline_score,
        metrics=metrics if isinstance(metrics, dict) else {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def run_evolution(request: EvolutionRunRequest) -> EvolutionRunResponse:
    if len(request.cases) > settings.evolution_max_cases:
        raise ValueError(f"Evolution is limited to {settings.evolution_max_cases} cases per run")
    baseline_score, baseline_passed, baseline_results, baseline_ms = await _evaluate_prompt(request.base_prompt, request)
    variants = await _generate_variants(request)
    candidates: list[EvolutionCandidateInfo] = []

    for index, content in enumerate(variants, start=1):
        score, passed, results, elapsed_ms = await _evaluate_prompt(content, request)
        metrics = {
            "case_count": len(results),
            "all_cases_passed": passed,
            "latency_ms": elapsed_ms,
            "baseline_latency_ms": baseline_ms,
            "baseline_all_cases_passed": baseline_passed,
            "case_results": results,
            "baseline_case_results": baseline_results,
            "provider": request.provider,
            "model": request.model or router.default_model(request.provider),
        }
        row = EvolutionCandidate(
            name=f"{request.name} v{index}",
            kind="prompt",
            content=content,
            status="shadow",
            score=score,
            baseline_score=baseline_score,
            metrics=json.dumps(metrics, ensure_ascii=False, default=str),
        )
        async with SessionLocal() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
            session.add(
                EvolutionEvalRun(
                    candidate_id=row.id,
                    score=score,
                    passed=bool(passed and score >= baseline_score),
                    payload=json.dumps(metrics, ensure_ascii=False, default=str),
                )
            )
            await session.commit()
        candidates.append(_candidate_info(row))

    best = max(candidates, key=lambda item: item.score if item.score is not None else -1.0, default=None)
    best_id = best.id if best and (best.score or 0.0) >= baseline_score else None
    return EvolutionRunResponse(
        baseline_score=baseline_score,
        candidates=candidates,
        best_candidate_id=best_id,
        notes=[
            "Candidates remain in shadow status until explicitly promoted.",
            "Promotion requires the candidate to pass every deterministic case and meet or beat baseline score.",
        ],
    )


async def list_candidates(limit: int = 50) -> list[EvolutionCandidateInfo]:
    limit = max(1, min(limit, 100))
    try:
        async with SessionLocal() as session:
            rows = (
                await session.execute(select(EvolutionCandidate).order_by(EvolutionCandidate.created_at.desc()).limit(limit))
            ).scalars().all()
            return [_candidate_info(row) for row in rows]
    except Exception as exc:
        logger.warning("Evolution candidate read skipped: %s", exc)
        return []


async def promote_candidate(candidate_id: str, approved: bool) -> EvolutionCandidateInfo:
    if not approved:
        raise PermissionError("Explicit human approval is required for promotion")
    try:
        parsed = uuid.UUID(candidate_id)
    except ValueError as exc:
        raise ValueError("Invalid candidate id") from exc

    async with SessionLocal() as session:
        row = await session.get(EvolutionCandidate, parsed)
        if not row:
            raise KeyError("Evolution candidate not found")
        latest_eval = (
            await session.execute(
                select(EvolutionEvalRun)
                .where(EvolutionEvalRun.candidate_id == parsed)
                .order_by(EvolutionEvalRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not latest_eval or not latest_eval.passed:
            raise ValueError("Candidate has not passed the deterministic evaluation gate")
        if row.score is None or row.baseline_score is None or row.score < row.baseline_score:
            raise ValueError("Candidate does not meet or beat its baseline score")
        await session.execute(
            update(EvolutionCandidate)
            .where(EvolutionCandidate.kind == row.kind, EvolutionCandidate.status == "promoted")
            .values(status="shadow")
        )
        row.status = "promoted"
        await session.commit()
        await session.refresh(row)
        return _candidate_info(row)
