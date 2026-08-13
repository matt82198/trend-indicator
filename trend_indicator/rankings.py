"""Artifact writer for rankings.json (design doc section 3, lane L6).

Takes already-assembled "opportunity input" dicts (one per opportunity, each carrying
per-source velocity signals + monetization_rate + fit + saturation) and produces the
rankings.json artifact contract. This module doesn't know or care where the opportunity
inputs came from -- cli.py assembles them from adapter snapshots; tests feed it plain
dicts directly.

Opportunity input shape:
{
    "opportunity": "<name>",
    "sources": [{"name": str, "fetched_at": "<ISO-8601>", "velocity": float 0..1,
                 "raw": {...}}, ...],
    "monetization_rate": float 0..1,
    "fit": float 0..1,
    "saturation": float > 0,
}

Output ranking entry shape matches the design doc's rankings.json contract exactly:
{
    "opportunity": str, "score": float,
    "signals": {"demand_velocity", "monetization_rate", "fit", "saturation"},
    "sources": [{"name", "fetched_at", "raw"}, ...],
    "freshness_hours": float, "confidence": "low"|"medium"|"high",
}
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from trend_indicator import scoring

GENERATOR_VERSION = "0.1.0"

# Half-life for sources not (yet) in scoring.HALF_LIFE_HOURS (e.g. a wave-2 source that
# gets wired in before its half-life is tuned). Matches youtube_mostpopular's 6h as a
# reasonable moderate default -- documented here so it's a visible, single choice.
DEFAULT_HALF_LIFE_HOURS = 6.0


def _parse_iso(timestamp: str) -> datetime:
    return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _now_iso(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def score_opportunity(opportunity_input: dict, now: datetime | None = None) -> dict:
    """Score one opportunity input into a rankings.json entry."""
    if now is None:
        now = datetime.now(timezone.utc)

    per_source_for_velocity = []
    hours_by_source = []
    for source in opportunity_input["sources"]:
        fetched_at = _parse_iso(source["fetched_at"])
        hours_since_fetch = max(0.0, (now - fetched_at).total_seconds() / 3600.0)
        half_life = scoring.HALF_LIFE_HOURS.get(source["name"], DEFAULT_HALF_LIFE_HOURS)
        per_source_for_velocity.append(
            {
                "velocity": source["velocity"],
                "hours_since_fetch": hours_since_fetch,
                "half_life_hours": half_life,
            }
        )
        hours_by_source.append(hours_since_fetch)

    demand_velocity = scoring.combined_demand_velocity(per_source_for_velocity)
    monetization_rate = opportunity_input["monetization_rate"]
    fit = opportunity_input["fit"]
    saturation = opportunity_input["saturation"]

    score = scoring.opportunity_score(demand_velocity, monetization_rate, fit, saturation)
    confidence = scoring.compute_confidence(len(opportunity_input["sources"]))
    freshness_hours = min(hours_by_source) if hours_by_source else 0.0

    return {
        "opportunity": opportunity_input["opportunity"],
        "score": score,
        "signals": {
            "demand_velocity": demand_velocity,
            "monetization_rate": monetization_rate,
            "fit": fit,
            "saturation": saturation,
        },
        "sources": [
            {"name": s["name"], "fetched_at": s["fetched_at"], "raw": s["raw"]}
            for s in opportunity_input["sources"]
        ],
        "freshness_hours": freshness_hours,
        "confidence": confidence,
    }


def build_artifact(
    opportunity_inputs: list[dict],
    generator_version: str = GENERATOR_VERSION,
    now: datetime | None = None,
) -> dict:
    """Score every opportunity input and assemble the full rankings.json artifact,
    sorted by score descending (highest opportunity first)."""
    if now is None:
        now = datetime.now(timezone.utc)

    entries = [score_opportunity(o, now=now) for o in opportunity_inputs]
    entries.sort(key=lambda e: e["score"], reverse=True)

    return {
        "generated_at": _now_iso(now),
        "generator_version": generator_version,
        "rankings": entries,
    }


def write_artifact(artifact: dict, state_dir: str | Path) -> Path:
    """Write `artifact` to `<state_dir>/rankings.json` atomically (write temp file in the
    same directory, then os.replace) and roll any prior rankings.json into
    `<state_dir>/rankings-history/rankings-<generated_at>.json` first (append-only
    history, same pattern as BUILDLOG.md's log-rotation convention).
    """
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    out_path = state_dir / "rankings.json"

    if out_path.exists():
        previous = json.loads(out_path.read_text(encoding="utf-8"))
        history_dir = state_dir / "rankings-history"
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = previous.get("generated_at", "unknown").replace(":", "").replace("-", "")
        history_path = history_dir / f"rankings-{stamp}.json"
        history_path.write_text(json.dumps(previous, indent=2), encoding="utf-8")

    fd, tmp_name = tempfile.mkstemp(prefix="rankings-", suffix=".tmp", dir=state_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2)
        os.replace(tmp_name, out_path)
    except BaseException:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise

    return out_path
