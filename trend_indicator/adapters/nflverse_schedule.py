"""nflverse schedule adapter (design doc section 1a/4, lane L3).

Free, open data, no key, no rate limit -- a periodic static-file pull from nflverse's
published CSV. This is the calendar backbone (bye weeks, primetime slots, matchup
context) every NFL-specific opportunity gets layered onto. Per this repo's conventions,
uses the CSV endpoint (not parquet) so no pandas/pyarrow dependency is required.
"""

from __future__ import annotations

import csv
import io
import urllib.request
from datetime import datetime, timezone
from typing import Callable

# Published by the nflverse/nfldata project -- season-by-season game schedule + context.
SCHEDULE_CSV_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
SOURCE_NAME = "nflverse_schedule"
DEFAULT_TIMEOUT_SECONDS = 15.0

# Kickoffs at/after this local time are treated as evening/primetime windows.
_PRIMETIME_HOUR_CUTOFF = 20  # 20:00 (8pm)
_PRIMETIME_WEEKDAYS = {"Thursday", "Sunday", "Monday"}


def _default_http_get(url: str, timeout: float) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # nosec B310 - fixed host
        return resp.read()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_primetime(weekday: str, gametime: str) -> bool:
    """Thursday Night / Sunday Night / Monday Night Football heuristic: nflverse's CSV
    has no explicit "primetime" column, so this derives it from weekday + kickoff time.
    Thursday and Monday games are primetime by definition (there's only one TNF/MNF slot
    per week); Sunday games only count if the kickoff is at/after 8pm local.
    """
    if weekday not in _PRIMETIME_WEEKDAYS:
        return False
    if weekday in ("Thursday", "Monday"):
        return True
    # Sunday: only the night game counts as primetime
    try:
        hour = int(gametime.split(":")[0])
    except (ValueError, AttributeError, IndexError):
        return False
    return hour >= _PRIMETIME_HOUR_CUTOFF


def fetch_schedule(
    season: int,
    http_get: Callable[[str, float], bytes] = _default_http_get,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """Fetch and parse the nflverse games CSV, filtered to `season`. No API key needed.
    `http_get` is injectable so tests never touch the network.
    """
    try:
        raw = http_get(SCHEDULE_CSV_URL, timeout)
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        reader = csv.DictReader(io.StringIO(text))
        items = []
        for row in reader:
            if int(row["season"]) != season:
                continue
            weekday = row.get("weekday", "")
            gametime = row.get("gametime", "")
            items.append(
                {
                    "season": int(row["season"]),
                    "week": int(row["week"]) if row.get("week") else None,
                    "game_type": row.get("game_type"),
                    "gameday": row.get("gameday"),
                    "weekday": weekday,
                    "gametime": gametime,
                    "away_team": row.get("away_team"),
                    "home_team": row.get("home_team"),
                    "div_game": row.get("div_game") == "1",
                    "is_primetime": _is_primetime(weekday, gametime),
                }
            )
    except Exception as exc:  # network/parse failure -- report, never crash the run
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
        "items": items,
        "error": None,
    }
