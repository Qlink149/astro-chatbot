"""Vercel serverless entrypoint for FastAPI (Samara).

Vercel routes /api/* here via vercel.json. Strip /api so existing FastAPI
paths (e.g. /gupshup/message/samara, /ping) match unchanged.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from kisna_chatbot.main import app as _app


async def app(scope, receive, send):
    if scope["type"] == "http" and scope["path"].startswith("/api"):
        scope["path"] = scope["path"][4:] or "/"
    await _app(scope, receive, send)
