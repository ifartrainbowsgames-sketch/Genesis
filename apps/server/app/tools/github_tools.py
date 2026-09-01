from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import quote

import httpx

from ..config import settings

NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _identity(owner: str, repo: str) -> tuple[str, str]:
    if not NAME_RE.fullmatch(owner) or not NAME_RE.fullmatch(repo):
        raise ValueError("Invalid GitHub owner or repository name")
    return owner, repo


def _headers() -> dict[str, str]:
    if not settings.github_token:
        raise RuntimeError("GITHUB_TOKEN is not configured")
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Genesis-local-ai",
    }


def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    base = settings.github_api_url.rstrip("/")
    with httpx.Client(timeout=30.0, headers=_headers(), follow_redirects=False) as client:
        response = client.request(method, f"{base}{path}", **kwargs)
    if response.is_error:
        detail = response.text[:1000]
        raise RuntimeError(f"GitHub API {response.status_code}: {detail}")
    return response


def repo_info(owner: str, repo: str) -> dict[str, Any]:
    owner, repo = _identity(owner, repo)
    data = _request("GET", f"/repos/{owner}/{repo}").json()
    return {
        "full_name": data.get("full_name"),
        "private": data.get("private"),
        "default_branch": data.get("default_branch"),
        "html_url": data.get("html_url"),
        "permissions": data.get("permissions"),
    }


def list_dir(owner: str, repo: str, path: str = "", ref: str | None = None) -> dict[str, Any]:
    owner, repo = _identity(owner, repo)
    encoded = quote(path.strip("/"), safe="/")
    suffix = f"/{encoded}" if encoded else ""
    params = {"ref": ref} if ref else None
    data = _request("GET", f"/repos/{owner}/{repo}/contents{suffix}", params=params).json()
    if not isinstance(data, list):
        raise ValueError("GitHub path is not a directory")
    items = []
    for item in data[:500]:
        items.append({
            "name": item.get("name"),
            "path": item.get("path"),
            "type": item.get("type"),
            "size": item.get("size"),
            "sha": item.get("sha"),
        })
    return {"items": items, "truncated": len(data) > 500}


def read_file(owner: str, repo: str, path: str, ref: str | None = None, max_bytes: int = 200_000) -> dict[str, Any]:
    owner, repo = _identity(owner, repo)
    if not path.strip("/"):
        raise ValueError("A file path is required")
    encoded = quote(path.strip("/"), safe="/")
    params = {"ref": ref} if ref else None
    data = _request("GET", f"/repos/{owner}/{repo}/contents/{encoded}", params=params).json()
    if data.get("type") != "file":
        raise ValueError("GitHub path is not a file")
    size = int(data.get("size") or 0)
    max_bytes = max(1, min(int(max_bytes), 1_000_000))
    if size > max_bytes:
        raise ValueError(f"Remote file exceeds read limit of {max_bytes} bytes")
    encoded_content = data.get("content") or ""
    raw = base64.b64decode(encoded_content.encode("ascii"), validate=False)
    if len(raw) > max_bytes:
        raise ValueError(f"Remote file exceeds read limit of {max_bytes} bytes")
    return {
        "path": data.get("path"),
        "sha": data.get("sha"),
        "size": len(raw),
        "content": raw.decode("utf-8", errors="replace"),
    }


def upsert_file(
    owner: str,
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str,
    expected_sha: str | None = None,
) -> dict[str, Any]:
    owner, repo = _identity(owner, repo)
    if not path.strip("/") or not message.strip() or not branch.strip():
        raise ValueError("path, message, and branch are required")
    raw = content.encode("utf-8")
    if len(raw) > settings.max_file_write_bytes:
        raise ValueError(f"Write exceeds {settings.max_file_write_bytes} byte limit")

    encoded = quote(path.strip("/"), safe="/")
    existing_sha: str | None = None
    try:
        current = _request("GET", f"/repos/{owner}/{repo}/contents/{encoded}", params={"ref": branch}).json()
        if current.get("type") != "file":
            raise ValueError("Remote path exists but is not a file")
        existing_sha = current.get("sha")
    except RuntimeError as exc:
        if "GitHub API 404" not in str(exc):
            raise

    if existing_sha and not expected_sha:
        raise ValueError("expected_sha is required when replacing an existing GitHub file")
    if existing_sha and expected_sha != existing_sha:
        raise ValueError("Remote file changed since inspection; expected_sha no longer matches")
    if not existing_sha and expected_sha:
        raise ValueError("expected_sha was provided but the remote file does not exist")

    payload: dict[str, Any] = {
        "message": message.strip(),
        "content": base64.b64encode(raw).decode("ascii"),
        "branch": branch.strip(),
    }
    if existing_sha:
        payload["sha"] = existing_sha
    data = _request("PUT", f"/repos/{owner}/{repo}/contents/{encoded}", json=payload).json()
    return {
        "commit_sha": data.get("commit", {}).get("sha"),
        "content_sha": data.get("content", {}).get("sha"),
        "path": data.get("content", {}).get("path"),
        "created": existing_sha is None,
    }


def create_branch(owner: str, repo: str, new_branch: str, from_branch: str = "main") -> dict[str, Any]:
    owner, repo = _identity(owner, repo)
    if not new_branch.strip() or not from_branch.strip():
        raise ValueError("new_branch and from_branch are required")
    source = _request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{quote(from_branch, safe='')}").json()
    sha = source.get("object", {}).get("sha")
    if not sha:
        raise RuntimeError("Could not resolve source branch")
    data = _request("POST", f"/repos/{owner}/{repo}/git/refs", json={"ref": f"refs/heads/{new_branch}", "sha": sha}).json()
    return {"branch": new_branch, "sha": data.get("object", {}).get("sha")}


def create_pull_request(
    owner: str,
    repo: str,
    title: str,
    head: str,
    base: str,
    body: str = "",
) -> dict[str, Any]:
    owner, repo = _identity(owner, repo)
    if not title.strip() or not head.strip() or not base.strip():
        raise ValueError("title, head, and base are required")
    data = _request(
        "POST",
        f"/repos/{owner}/{repo}/pulls",
        json={"title": title.strip(), "head": head.strip(), "base": base.strip(), "body": body},
    ).json()
    return {"number": data.get("number"), "html_url": data.get("html_url"), "state": data.get("state")}
