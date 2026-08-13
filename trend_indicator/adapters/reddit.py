"""STUB -- Reddit adapter (design doc section 1a, wave 2). NOT IMPLEMENTED.

Design doc research notes (section 1a):
- Official PRAW API, free for non-commercial personal-scale use: 100 req/min with OAuth
  (10/min without). Commercial use requires paid approval ($0.24/1k calls, ~$12k/mo
  minimum at 50M calls -- irrelevant at our scale, but note Reddit's Responsible Builder
  Policy (2026-06-05) draws a hard commercial/non-commercial line worth re-checking
  before this ships).
- Planned approach: snapshot `hot`/`top`/`rising` listings on target subreddits and diff
  score/comment growth over time for a velocity signal -- no bulk historical search
  needed for a live signal.
- Pushshift is dead for public use; Arctic Shift is the free historical-backfill option
  if ever needed.

TODO(wave-2): implement fetch_hot_listings(subreddits, http_get=...) -> snapshot dict
(same shape as trend_indicator/adapters/base.py:SNAPSHOT_KEYS), requiring OAuth app
credentials (client id/secret) -- read at call time from env, same SKIPPED-NO-KEY
pattern as youtube_trending.py, never hardcoded/hunted.
"""

from __future__ import annotations

SOURCE_NAME = "reddit"


def fetch_hot_listings(*args, **kwargs) -> dict:
    """Not implemented -- wave-2 source. See module docstring / design doc section 1a."""
    raise NotImplementedError(
        "reddit adapter is a wave-2 stub (design doc section 4: 'out of MVP ... Reddit "
        "... wave 2'). See trend_indicator/adapters/reddit.py TODO for the planned shape."
    )
