from __future__ import annotations

from types import SimpleNamespace

from apps.server.app.services.memory_consolidator import _compact, _preference_lines


def test_compact_normalizes_whitespace_and_bounds_text() -> None:
    assert _compact(" hello\n   world ", 50) == "hello world"
    assert _compact("x" * 10, 5) == "xxxx…"


def test_preference_lines_only_keep_user_constraints_and_dedupe() -> None:
    rows = [
        SimpleNamespace(role="assistant", content="You should use dark mode."),
        SimpleNamespace(role="user", content="I prefer compact output."),
        SimpleNamespace(role="user", content="I prefer compact output."),
        SimpleNamespace(role="user", content="Never auto-promote candidates."),
        SimpleNamespace(role="user", content="Just chatting about weather."),
    ]
    selected = _preference_lines(rows)
    assert [row.content for row in selected] == [
        "I prefer compact output.",
        "Never auto-promote candidates.",
    ]
