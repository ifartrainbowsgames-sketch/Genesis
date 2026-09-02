from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse


ASGIApp = Callable[[dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]], Awaitable[None]]


class DesktopTokenMiddleware:
    """Require a per-launch secret for packaged desktop /v1 requests.

    The health endpoint intentionally remains unauthenticated so the Tauri startup gate can
    distinguish "server is alive" from "desktop credentials are wrong". All user data and
    action endpoints live below /v1 and require the private token when this middleware is
    enabled. Source/developer mode does not enable this middleware unless it launches through
    sidecar_entry with GENESIS_API_TOKEN set.
    """

    def __init__(self, app: ASGIApp, token: str, web_origin: str) -> None:
        self.app = app
        self.token = token
        self.web_origin = web_origin

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", ""))
        method = str(scope.get("method", "GET")).upper()
        if not path.startswith("/v1/") or method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        provided = headers.get(b"x-genesis-token", b"").decode("utf-8", errors="ignore")
        if hmac.compare_digest(provided, self.token):
            await self.app(scope, receive, send)
            return

        response_headers: dict[str, str] = {"cache-control": "no-store"}
        origin = headers.get(b"origin", b"").decode("utf-8", errors="ignore")
        if origin and origin == self.web_origin:
            response_headers.update(
                {
                    "access-control-allow-origin": origin,
                    "access-control-allow-credentials": "true",
                    "vary": "Origin",
                }
            )
        response = JSONResponse(
            {"detail": "Genesis desktop API authorization failed"},
            status_code=401,
            headers=response_headers,
        )
        await response(scope, receive, send)
