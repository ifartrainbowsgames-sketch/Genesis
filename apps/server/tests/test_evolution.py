from __future__ import annotations

import pytest

from apps.server.app.schemas import PromptEvalCase
from apps.server.app.services.evolution import _json_object, score_output


def test_score_output_requires_expected_and_forbids_bad_markers() -> None:
    case = PromptEvalCase(
        name="safe",
        input="ignored",
        expected_contains=["approved", "source"],
        forbidden_contains=["fabricated"],
    )
    score, result = score_output("Approved with a source.", case)
    assert score == 1.0
    assert result["passed"] is True

    score, result = score_output("Approved but fabricated.", case)
    assert score == 0.0
    assert result["passed"] is False
    assert result["missing"] == ["source"]
    assert result["forbidden_found"] == ["fabricated"]


def test_json_object_accepts_fenced_json() -> None:
    assert _json_object('```json\n{"variants":["one"]}\n```') == {"variants": ["one"]}


def test_json_object_rejects_non_object() -> None:
    with pytest.raises(ValueError):
        _json_object('["one"]')
