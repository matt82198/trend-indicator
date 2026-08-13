"""STUB -- The Odds API adapter (design doc section 1a, wave 2). NOT IMPLEMENTED.

Design doc research notes (section 1a):
- Free "Starter" tier: 500 credits/mo. A credit = markets x regions (~6 credits for 3
  markets x 2 regions per call) -> roughly 2-3 live calls/day on the free tier. `/sports`
  and `/events` endpoints are free/uncharged.
- Betting-line movement is a legitimate attention proxy (line moves = money moving =
  public interest), but the free tier is too thin for continuous polling of many games --
  fine for a daily snapshot of marquee games, not a firehose.
- Freshness half-life for this source (per design doc section 2, for when it's built):
  ~2 hours, since line movement is explicitly time-sensitive.

TODO(wave-2): implement fetch_line_movement(sport_key, markets, http_get=...) -> snapshot
dict (same shape as trend_indicator/adapters/base.py:SNAPSHOT_KEYS), daily-snapshot mode
only given the free-tier call budget. API key read at call time from env (e.g.
ODDS_API_KEY), same SKIPPED-NO-KEY pattern as youtube_trending.py.
"""

from __future__ import annotations

SOURCE_NAME = "odds_api"


def fetch_line_movement(*args, **kwargs) -> dict:
    """Not implemented -- wave-2 source. See module docstring / design doc section 1a."""
    raise NotImplementedError(
        "odds_api adapter is a wave-2 stub (design doc section 4: 'out of MVP ... The "
        "Odds API ... wave 2'). See trend_indicator/adapters/odds_api.py TODO for the "
        "planned shape."
    )
