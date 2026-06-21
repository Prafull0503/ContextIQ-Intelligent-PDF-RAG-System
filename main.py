"""Application entry point.

Run with:
    uvicorn main:app --reload

Or directly:
    python main.py
"""

from __future__ import annotations

import uvicorn

from app.application import create_app
from app.core.config import get_settings

# The ASGI application object that ``uvicorn main:app`` looks for.
app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )
