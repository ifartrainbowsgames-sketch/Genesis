from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from apps.server.app.tools import github_tools


@dataclass
class FakeResponse:
    payload: dict[str, Any]

    def json(self) -> dict[str, Any]:
        return self.payload


def test_identity_rejects_path_injection() -> None:
    with pytest.raises(ValueError, match="Invalid GitHub owner or repository name"):
        github_tools.repo_info("owner/other", "repo")


def test_upsert_requires_expected_sha_for_existing_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_request(method: str, path: str, **kwargs: Any) -> FakeResponse:
        assert method == "GET"
        return FakeResponse({"type": "file", "sha": "current-sha"})

    monkeypatch.setattr(github_tools, "_request", fake_request)

    with pytest.raises(ValueError, match="expected_sha is required"):
        github_tools.upsert_file(
            "owner", "repo", "file.txt", "new", "Update file", "main"
        )


def test_upsert_rejects_stale_expected_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(method: str, path: str, **kwargs: Any) -> FakeResponse:
        assert method == "GET"
        return FakeResponse({"type": "file", "sha": "newer-sha"})

    monkeypatch.setattr(github_tools, "_request", fake_request)

    with pytest.raises(ValueError, match="expected_sha no longer matches"):
        github_tools.upsert_file(
            "owner",
            "repo",
            "file.txt",
            "new",
            "Update file",
            "main",
            expected_sha="older-sha",
        )


def test_upsert_rejects_expected_sha_when_remote_file_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_request(method: str, path: str, **kwargs: Any) -> FakeResponse:
        raise RuntimeError("GitHub API 404: Not Found")

    monkeypatch.setattr(github_tools, "_request", fake_request)

    with pytest.raises(ValueError, match="remote file does not exist"):
        github_tools.upsert_file(
            "owner",
            "repo",
            "file.txt",
            "new",
            "Update file",
            "main",
            expected_sha="old-sha",
        )


def test_upsert_sends_observed_sha_on_safe_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def fake_request(method: str, path: str, **kwargs: Any) -> FakeResponse:
        calls.append((method, path, kwargs))
        if method == "GET":
            return FakeResponse({"type": "file", "sha": "observed-sha"})
        return FakeResponse(
            {
                "commit": {"sha": "commit-sha"},
                "content": {"sha": "content-sha", "path": "file.txt"},
            }
        )

    monkeypatch.setattr(github_tools, "_request", fake_request)

    result = github_tools.upsert_file(
        "owner",
        "repo",
        "file.txt",
        "replacement",
        "Update file",
        "main",
        expected_sha="observed-sha",
    )

    put_payload = calls[1][2]["json"]
    assert put_payload["sha"] == "observed-sha"
    assert put_payload["branch"] == "main"
    assert result == {
        "commit_sha": "commit-sha",
        "content_sha": "content-sha",
        "path": "file.txt",
        "created": False,
    }
