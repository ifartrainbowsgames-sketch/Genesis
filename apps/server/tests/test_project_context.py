from pathlib import Path

import pytest

from app.services import project_context
from app.services.workspace_manager import workspace_manager


@pytest.fixture()
def indexed_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "node_modules" / "huge").mkdir(parents=True)
    (root / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    (root / "src" / "service.py").write_text(
        "class WidgetService:\n    def render_widget(self):\n        return 'ok'\n",
        encoding="utf-8",
    )
    (root / "node_modules" / "huge" / "ignored.js").write_text("export const ignored = true", encoding="utf-8")
    (root / ".env").write_text("SECRET=do-not-index", encoding="utf-8")
    monkeypatch.setattr(workspace_manager, "_path", root)
    return root


def test_index_prunes_generated_and_sensitive_files(indexed_project: Path) -> None:
    result = project_context.snapshot()
    assert result["file_count"] == 2
    assert "package.json" in result["manifests"]
    paths = {item["path"] for item in result["symbol_files"]}
    assert "src/service.py" in paths
    assert all("node_modules" not in path for path in paths)


def test_index_reuses_unchanged_files_and_reindexes_changed_file(indexed_project: Path) -> None:
    first = project_context.refresh_index()
    second = project_context.refresh_index()
    assert second["reused_files"] == first["file_count"]
    assert second["changed_files"] == 0

    service = indexed_project / "src" / "service.py"
    service.write_text("class RenamedWidgetService:\n    pass\n", encoding="utf-8")
    third = project_context.refresh_index()
    assert third["changed_files"] == 1
    assert third["reused_files"] == 1


def test_symbol_search_selects_relevant_file(indexed_project: Path) -> None:
    hits = project_context.search("WidgetService", limit=5)
    assert hits
    assert hits[0]["path"] == "src/service.py"
    assert "WidgetService" in hits[0]["symbols"]

    context, used = project_context.context_for("render_widget", max_files=4, max_total_chars=10_000)
    assert used == ["src/service.py", "package.json"] or used[0] == "src/service.py"
    assert "render_widget" in context
    assert "SECRET=do-not-index" not in context
