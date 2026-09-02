from __future__ import annotations

import os

import uvicorn

from app.config import settings
from app.desktop_auth import DesktopTokenMiddleware
from app.desktop_storage import DesktopStorageMiddleware
from app.main import app


def runtime_app():
    token = os.getenv("GENESIS_API_TOKEN", "").strip()
    if not token:
        return app
    desktop_app = DesktopStorageMiddleware(app, settings.web_origin)
    return DesktopTokenMiddleware(desktop_app, token, settings.web_origin)


if __name__ == "__main__":
    uvicorn.run(
        runtime_app(),
        host=settings.server_host,
        port=settings.server_port,
        log_level="info",
        access_log=False,
    )
