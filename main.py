"""Application entry point.

Run with:
    uvicorn main:app --reload

Or directly:
    python main.py
"""

from __future__ import annotations

import os

import uvicorn

from app.application import create_app
from app.core.config import get_settings

# The ASGI application object that ``uvicorn main:app`` looks for.
app = create_app()


if __name__ == "__main__":
    settings = get_settings()

    # Platforms like Render/Heroku assign the port dynamically via $PORT --
    # a hardcoded port would make the deployed app unreachable. 8000 is only
    # the local-dev fallback.
    port = int(os.environ.get("PORT", 8000))

    # Auto-reload is a dev convenience (watches files, restarts on change);
    # it should never run in production. Opt in explicitly with APP_RELOAD=1.
    reload_enabled = os.environ.get("APP_RELOAD", "false").lower() in ("1", "true", "yes")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=reload_enabled,
        log_level=settings.log_level.lower(),
    )
    