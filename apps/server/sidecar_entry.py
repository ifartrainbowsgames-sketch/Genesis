from __future__ import annotations

import uvicorn

from app.config import settings
from app.main import app


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.server_host,
        port=settings.server_port,
        log_level="info",
        access_log=False,
    )
