# services/agent_api/features/news/routes.py
from __future__ import annotations

from typing import Callable, Optional

# Import your existing handler from wherever you keep it today.
# If you still have _handle_get_news_latest in app.py, move it into news_service.py
# and import it here.
from services.agent_api.news_service import handle_get_news_latest, handle_get_debug_news  # adjust if needed


def match_news_route(method: str, path: str) -> Optional[Callable[[dict], dict]]:
    """
    path here is ALREADY normalized ("/api" stripped).
    So CloudFront '/api/news/latest' becomes '/news/latest'
    """
    if method == "GET" and (path == "/news/latest" or path.endswith("/news/latest")):
        return handle_get_news_latest

    if method == "GET" and (path == "/_debug/news" or path.endswith("/_debug/news")):
        return handle_get_debug_news

    return None