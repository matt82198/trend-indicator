"""YouTube search-suggest (autocomplete) adapter (design doc section 1a/4, lane L2).

Free, no official API but a very stable unofficial JSON endpoint (the same one
search-tool vendors have scraped for years). Needs no key. Suggestions are
frequency+recency weighted, so rising queries surface here before they show up in any
dashboard -- a genuine leading indicator, cheap to poll.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Callable

SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
SOURCE_NAME = "youtube_autocomplete"
DEFAULT_TIMEOUT_SECONDS = 10.0


def _default_http_get(url: str, timeout: float) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310 - fixed host
        return resp.read()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_suggestions(
    query: str,
    http_get: Callable[[str, float], bytes] = _default_http_get,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Fetch autocomplete suggestions for `query` from the public YouTube suggest
    endpoint. No API key required. `http_get` is injectable so tests never touch the
    network.
    """
    params = {"client": "firefox", "ds": "yt", "q": query}
    url = f"{SUGGEST_URL}?{urllib.parse.urlencode(params)}"

    try:
        raw = http_get(url, timeout)
        payload = json.loads(raw)
        if not (isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], list)):
            raise ValueError(f"unexpected suggest response shape: {payload!r}")
        suggestions = list(payload[1])
    except Exception as exc:  # network/parse/shape failure -- report, never crash the run
        return {
            "name": SOURCE_NAME,
            "status": "ERROR",
            "fetched_at": _now_iso(),
            "items": [],
            "error": str(exc),
        }

    return {
        "name": SOURCE_NAME,
        "status": "OK",
        "fetched_at": _now_iso(),
        "items": suggestions,
        "error": None,
    }
