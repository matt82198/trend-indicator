"""Scoring core: demand_velocity / monetization_rate / fit / saturation -> opportunity_score,
with per-source freshness decay. Pure functions only -- this module makes no HTTP calls and
touches no filesystem; adapters and rankings.py feed it plain numbers/dicts.

Formula (design doc "Trend Indicator - Design", section 2):

    opportunity_score = (demand_velocity * monetization_rate * fit) / saturation

Each raw per-source signal is weighted by freshness before being combined into the single
demand_velocity term:

    effective_weight = raw_weight * exp(-hours_since_fetch / half_life_hours)
"""

from __future__ import annotations

import math

# Half-life (hours) per source. youtube_mostpopular and nflverse_schedule values are from
# the design doc section 2 directly. youtube_autocomplete has no number in the design doc
# (only "genuine leading indicator, cheap to poll") -- 4h chosen here (faster than
# mostPopular's 6h) since autocomplete is framed as the faster-moving signal. Documented
# as an assumption in STATE.md; revisit once real data shows how fast suggestions churn.
HALF_LIFE_HOURS: dict[str, float] = {
    "youtube_mostpopular": 6.0,
    "youtube_autocomplete": 4.0,
    "nflverse_schedule": 168.0,
}


def freshness_decay(hours_since_fetch: float, half_life_hours: float) -> float:
    """exp(-hours_since_fetch / half_life_hours).

    Negative hours_since_fetch (clock skew / future timestamp) is clamped to 0 so weight
    never exceeds 1.0. half_life_hours must be > 0.
    """
    if half_life_hours <= 0:
        raise ValueError("half_life_hours must be > 0")
    if hours_since_fetch < 0:
        hours_since_fetch = 0.0
    return math.exp(-hours_since_fetch / half_life_hours)


def source_velocity(current: float, baseline: float) -> float:
    """Normalized 0..1 demand-velocity for a single source: growth rate vs. its own
    rolling baseline (design doc section 1c/2 -- "velocity relative to a personal/topic
    baseline, not absolute magnitude, is the universal core metric").

    - baseline <= 0 (cold start / near-zero base): any positive current reads as maximal
      velocity (a spike off nothing is real signal, and baseline division would be
      undefined) -- current == 0 too reads as 0 (nothing happening).
    - Growth ratio ((current - baseline) / baseline) is clipped to [0, 1] -- a source that
      has doubled (+100%) already reads as "as hot as it gets" for MVP purposes, so one
      extreme outlier source can't swamp the combined score. Declines (negative growth)
      clip to 0, since this term measures *rising* demand, not falling demand.
    """
    if current < 0:
        raise ValueError("current must be >= 0")
    if baseline <= 0:
        return 1.0 if current > 0 else 0.0
    growth = (current - baseline) / baseline
    return min(1.0, max(0.0, growth))


def combined_demand_velocity(per_source: list[dict]) -> float:
    """Freshness-weighted average of per-source velocities.

    per_source: [{"velocity": float 0..1, "hours_since_fetch": float,
                   "half_life_hours": float}, ...]

    Normalizes across sources so a spike off a near-zero baseline (e.g. a small signal)
    doesn't out-rank a modest spike on a large, fresh signal just because it happened to
    be sampled more recently -- freshness weights the *contribution*, not the raw
    velocity value itself. Returns 0.0 for an empty list or when every source's weight
    has decayed to ~0 (nothing usably fresh to combine).
    """
    total_weight = 0.0
    weighted_sum = 0.0
    for source in per_source:
        weight = freshness_decay(source["hours_since_fetch"], source["half_life_hours"])
        weighted_sum += source["velocity"] * weight
        total_weight += weight
    if total_weight == 0:
        return 0.0
    return weighted_sum / total_weight


def compute_confidence(num_agreeing_sources: int) -> str:
    """"one source spiking is a rumor, two+ sources agreeing is a signal" (design doc
    section 3, artifact contract rules). 0 or 1 contributing sources -> "low", exactly 2
    -> "medium", 3+ -> "high".
    """
    if num_agreeing_sources >= 3:
        return "high"
    if num_agreeing_sources == 2:
        return "medium"
    return "low"


def opportunity_score(
    demand_velocity: float, monetization_rate: float, fit: float, saturation: float
) -> float:
    """opportunity_score = (demand_velocity * monetization_rate * fit) / saturation

    saturation <= 0 is degenerate (undefined or would flip the sign via division by a
    negative) -- treated as "fully saturated, no opportunity" (returns 0.0) rather than
    raising, so one bad saturation input can't crash an entire ranking run.
    """
    if saturation <= 0:
        return 0.0
    return (demand_velocity * monetization_rate * fit) / saturation
