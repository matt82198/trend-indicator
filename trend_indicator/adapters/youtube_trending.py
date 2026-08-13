"""YouTube Data API `mostPopular` chart adapter (design doc section 1a/4, lane L1).

Free, official, documented, stable -- the one platform-native trending endpoint that's
actually free and sanctioned (10k quota units/day). Reads the API key from the YT_API_KEY
environment variable at call time only; if it's absent, returns a SKIPPED-NO-KEY snapshot
with no network call attempted -- never hunt for credentials elsewhere.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Callable

API_URL = "https://www.googleapis.com/youtube/v3/videos"
SOURCE_NAME = "youtube_mostpopular"
DEFAULT_TIMEOUT_SECONDS = 10.0


def _default_http_get(url: str, timeout: float) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310 - fixed host
        return resp.read()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_trending(
    region_code: str = "US",
    max_results: int = 25,
    api_key: str | None = None,
    http_get: Callable[[str, float], bytes] = _default_http_get,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Fetch the current mostPopular chart.

    `api_key` defaults to `os.environ["YT_API_KEY"]` read at call time; if that's absent
    too, returns a SKIPPED-NO-KEY snapshot instead of raising, with zero network calls
    made. `http_get` is injectable so tests never touch the network.
    """
    key = api_key if api_key is not None else os.environ.get("YT_API_KEY")
    if not key:
        return {
            "name": SOURCE_NAME,
            "status": "SKIPPED-NO-KEY",
            "fetched_at": _now_iso(),
            "items": [],
            "error": None,
        }

    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": region_code,
        "maxResults": str(max_results),
        "key": key,
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"

    try:
        raw = http_get(url, timeout)
        payload = json.loads(raw)
    except Exception as exc:  # network/parse failure -- report, never crash the run
        return {
            "name": SOURCE_NAME,
            "status": "ERROR",
            "fetched_at": _now_iso(),
            "items": [],
            "error": str(exc),
        }

    items = []
    for video in payload.get("items", []):
        snippet = video.get("snippet", {})
        stats = video.get("statistics", {})
        items.append(
            {
                "video_id": video.get("id"),
                "title": snippet.get("title"),
                "channel_id": snippet.get("channelId"),
                "channel_title": snippet.get("channelTitle"),
                "category_id": snippet.get("categoryId"),
                "tags": snippet.get("tags", []),
                "view_count": int(stats.get("viewCount", 0)),
            }
        )

    return {
        "name": SOURCE_NAME,
        "status": "OK",
        "fetched_at": _now_iso(),
        "items": items,
        "error": None,
    }
