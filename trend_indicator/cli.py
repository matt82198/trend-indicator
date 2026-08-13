"""CLI / orchestration entrypoint (design doc lane L7). Wires L1-L3 adapters -> derived
per-source stats -> scoring.py -> rankings.py. This is the one integration lane that
imports everything else; it should stay thin -- real logic lives in the modules it wires.

MVP scope note: the design doc's rankings.json example implies a general
multi-opportunity ranker, but deriving named "opportunities" from raw source data
(topic clustering across YouTube titles / autocomplete queries / NFL matchups) is a
non-trivial problem the design doc doesn't specify precisely enough to build correctly
in the MVP window. This CLI computes exactly ONE opportunity for the MVP --
"nfl-shorts-general" -- built honestly from the three real adapters' data (not a
placeholder), leaving room for a real multi-opportunity assembler as a follow-up. See
CLAUDE.md gotchas for the write-location deviation (state/ in this repo, not
conductor3/state/trend-indicator/).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from trend_indicator import monetization, rankings, scoring
from trend_indicator.adapters import nflverse_schedule, youtube_suggest, youtube_trending

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_DIR = REPO_ROOT / "state"

OPPORTUNITY_NAME = "nfl-shorts-general"
SEED_QUERIES = ["nfl", "nfl highlights", "nfl primetime"]
NFL_KEYWORDS = ("nfl", "football", "touchdown", "quarterback", "super bowl")
DEFAULT_FIT = 0.5
DEFAULT_SATURATION = 1.0  # used when there's no matching data to compute a real ratio


def _now_iso(now: datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def current_nfl_season(now: datetime) -> int:
    """nflverse labels a season by the year it starts (Sept). The prior season's
    playoffs run into Jan/Feb, so anything before March still belongs to the prior
    season's year."""
    return now.year if now.month >= 3 else now.year - 1


def _matches_nfl_keywords(title: str, tags: list[str]) -> bool:
    haystack = " ".join([title or "", " ".join(tags or [])]).lower()
    return any(kw in haystack for kw in NFL_KEYWORDS)


def _mostpopular_derived(snapshot: dict) -> dict:
    matching = [
        item for item in snapshot["items"] if _matches_nfl_keywords(item.get("title", ""), item.get("tags", []))
    ]
    distinct_channels = {item.get("channel_id") for item in matching}
    return {
        "nfl_matching_count": len(matching),
        "distinct_channels_in_match": len(distinct_channels),
    }


def _autocomplete_derived(merged_items: list[dict]) -> dict:
    total = sum(len(entry.get("suggestions", [])) for entry in merged_items)
    return {"total_suggestions": total}


def _current_week_games(items: list[dict], today: datetime) -> list[dict]:
    """Nearest week: the earliest week whose games are today or later; falls back to the
    latest week in the data if the season has already ended."""
    today_str = today.strftime("%Y-%m-%d")
    upcoming = sorted(
        (g for g in items if g.get("gameday") and g["gameday"] >= today_str),
        key=lambda g: (g["gameday"], g.get("week") or 0),
    )
    if not upcoming:
        if not items:
            return []
        last_week = max(g.get("week") or 0 for g in items)
        return [g for g in items if g.get("week") == last_week]
    current_week = upcoming[0].get("week")
    return [g for g in items if g.get("week") == current_week]


def _schedule_derived(snapshot: dict, now: datetime) -> dict:
    week_games = _current_week_games(snapshot["items"], now)
    primetime = sum(1 for g in week_games if g.get("is_primetime"))
    return {
        "current_week_primetime_games": primetime,
        "current_week_total_games": len(week_games),
    }


def _write_snapshot(state_dir: Path, name: str, snapshot: dict) -> Path:
    snapshots_dir = state_dir / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    path = snapshots_dir / f"{name}.json"
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return path


def _load_baselines(state_dir: Path) -> dict:
    path = state_dir / "baselines.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_baselines(state_dir: Path, baselines: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "baselines.json"
    path.write_text(json.dumps(baselines, indent=2), encoding="utf-8")


def _rotate_baseline(baselines: dict, key: str, new_value: float, now_iso: str) -> dict:
    """Shifts the prior 'value' into 'previous_value' and records the new current value.
    First-ever observation has no history, so previous_value defaults to new_value
    (velocity reads as 0 until a second refresh gives it something to compare against).
    """
    prior_entry = baselines.get(key, {})
    previous_value = prior_entry.get("value", new_value)
    baselines[key] = {"value": new_value, "previous_value": previous_value, "updated_at": now_iso}
    return baselines


def refresh(state_dir: Path = DEFAULT_STATE_DIR, now: datetime | None = None) -> dict:
    """Fetch every MVP adapter, write one snapshot JSON per source, and roll the
    velocity-tracked metrics into state/baselines.json."""
    if now is None:
        now = datetime.now(timezone.utc)
    now_iso = _now_iso(now)
    season = current_nfl_season(now)

    trending_snapshot = youtube_trending.fetch_trending()
    trending_snapshot["derived"] = _mostpopular_derived(trending_snapshot)
    _write_snapshot(state_dir, "youtube_mostpopular", trending_snapshot)

    suggest_entries = []
    for query in SEED_QUERIES:
        result = youtube_suggest.fetch_suggestions(query)
        suggest_entries.append(
            {"query": query, "suggestions": result["items"], "status": result["status"]}
        )
    autocomplete_snapshot = {
        "name": "youtube_autocomplete",
        "status": "OK" if any(e["status"] == "OK" for e in suggest_entries) else "ERROR",
        "fetched_at": now_iso,
        "items": suggest_entries,
        "error": None,
    }
    autocomplete_snapshot["derived"] = _autocomplete_derived(suggest_entries)
    _write_snapshot(state_dir, "youtube_autocomplete", autocomplete_snapshot)

    schedule_snapshot = nflverse_schedule.fetch_schedule(season=season)
    schedule_snapshot["derived"] = _schedule_derived(schedule_snapshot, now)
    _write_snapshot(state_dir, "nflverse_schedule", schedule_snapshot)

    baselines = _load_baselines(state_dir)
    if trending_snapshot["status"] == "OK":
        baselines = _rotate_baseline(
            baselines,
            "youtube_mostpopular.nfl_matching_count",
            trending_snapshot["derived"]["nfl_matching_count"],
            now_iso,
        )
    if autocomplete_snapshot["status"] == "OK":
        baselines = _rotate_baseline(
            baselines,
            "youtube_autocomplete.total_suggestions",
            autocomplete_snapshot["derived"]["total_suggestions"],
            now_iso,
        )
    _write_baselines(state_dir, baselines)

    return {
        "youtube_mostpopular": trending_snapshot["status"],
        "youtube_autocomplete": autocomplete_snapshot["status"],
        "nflverse_schedule": schedule_snapshot["status"],
    }


def _load_snapshot(state_dir: Path, name: str) -> dict | None:
    path = state_dir / "snapshots" / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_fit_profile(path: str | Path | None) -> dict:
    if path is None:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_opportunity_input(state_dir: Path, fit_profile: dict) -> dict | None:
    baselines = _load_baselines(state_dir)
    sources = []

    mostpopular = _load_snapshot(state_dir, "youtube_mostpopular")
    if mostpopular and mostpopular["status"] == "OK":
        current = mostpopular["derived"]["nfl_matching_count"]
        baseline_entry = baselines.get("youtube_mostpopular.nfl_matching_count", {})
        baseline = baseline_entry.get("previous_value", current)
        velocity = scoring.source_velocity(current, baseline)
        sources.append(
            {
                "name": "youtube_mostpopular",
                "fetched_at": mostpopular["fetched_at"],
                "velocity": velocity,
                "raw": mostpopular["derived"],
            }
        )

    autocomplete = _load_snapshot(state_dir, "youtube_autocomplete")
    if autocomplete and autocomplete["status"] == "OK":
        current = autocomplete["derived"]["total_suggestions"]
        baseline_entry = baselines.get("youtube_autocomplete.total_suggestions", {})
        baseline = baseline_entry.get("previous_value", current)
        velocity = scoring.source_velocity(current, baseline)
        sources.append(
            {
                "name": "youtube_autocomplete",
                "fetched_at": autocomplete["fetched_at"],
                "velocity": velocity,
                "raw": autocomplete["derived"],
            }
        )

    schedule = _load_snapshot(state_dir, "nflverse_schedule")
    if schedule and schedule["status"] == "OK":
        derived = schedule["derived"]
        if derived["current_week_primetime_games"] > 0:
            velocity = 1.0
        elif derived["current_week_total_games"] > 0:
            velocity = 0.5
        else:
            velocity = 0.0
        sources.append(
            {
                "name": "nflverse_schedule",
                "fetched_at": schedule["fetched_at"],
                "velocity": velocity,
                "raw": derived,
            }
        )

    if not sources:
        return None

    mostpopular_derived = mostpopular["derived"] if mostpopular and mostpopular["status"] == "OK" else None
    if mostpopular_derived and mostpopular_derived["nfl_matching_count"] > 0:
        saturation = (
            mostpopular_derived["distinct_channels_in_match"] / mostpopular_derived["nfl_matching_count"]
        )
    else:
        # No matching-item data to compute the §1d view-weighted-supply ratio from --
        # neutral default rather than a crash. Documented MVP gap: full saturation proxy
        # needs per-item view counts across platforms, which the MVP doesn't collect.
        saturation = DEFAULT_SATURATION

    return {
        "opportunity": OPPORTUNITY_NAME,
        "sources": sources,
        "monetization_rate": monetization.get_rate("youtube_shorts", "sports"),
        "fit": fit_profile.get(OPPORTUNITY_NAME, DEFAULT_FIT),
        "saturation": saturation,
    }


def rank(
    state_dir: Path = DEFAULT_STATE_DIR,
    fit_profile_path: str | Path | None = None,
    now: datetime | None = None,
) -> Path | None:
    """Score the latest snapshots into rankings.json. Returns the written path, or None
    if no snapshot data is available yet (caller should run `refresh` first)."""
    fit_profile = _load_fit_profile(fit_profile_path)
    opportunity_input = _build_opportunity_input(state_dir, fit_profile)
    if opportunity_input is None:
        return None
    artifact = rankings.build_artifact([opportunity_input], now=now)
    return rankings.write_artifact(artifact, state_dir)


def status(state_dir: Path = DEFAULT_STATE_DIR, now: datetime | None = None) -> dict:
    """Summarize snapshot ages vs. each source's freshness half-life, and rankings.json
    age, without touching the network."""
    if now is None:
        now = datetime.now(timezone.utc)

    report = {"sources": {}, "rankings": None}
    for name in ("youtube_mostpopular", "youtube_autocomplete", "nflverse_schedule"):
        snapshot = _load_snapshot(state_dir, name)
        if snapshot is None:
            report["sources"][name] = {"present": False}
            continue
        fetched_at = datetime.strptime(snapshot["fetched_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        age_hours = (now - fetched_at).total_seconds() / 3600.0
        half_life = scoring.HALF_LIFE_HOURS.get(name, rankings.DEFAULT_HALF_LIFE_HOURS)
        report["sources"][name] = {
            "present": True,
            "status": snapshot["status"],
            "age_hours": round(age_hours, 3),
            "half_life_hours": half_life,
            "freshness_weight": round(scoring.freshness_decay(age_hours, half_life), 4),
        }

    rankings_path = Path(state_dir) / "rankings.json"
    if rankings_path.exists():
        data = json.loads(rankings_path.read_text(encoding="utf-8"))
        generated_at = datetime.strptime(data["generated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        report["rankings"] = {
            "present": True,
            "generated_at": data["generated_at"],
            "age_hours": round((now - generated_at).total_seconds() / 3600.0, 3),
            "opportunity_count": len(data["rankings"]),
        }
    else:
        report["rankings"] = {"present": False}

    return report


def _print_status(report: dict) -> None:
    print("Sources:")
    for name, info in report["sources"].items():
        if not info["present"]:
            print(f"  {name}: no snapshot yet (run `refresh` first)")
            continue
        print(
            f"  {name}: status={info['status']} age={info['age_hours']}h "
            f"half_life={info['half_life_hours']}h freshness_weight={info['freshness_weight']}"
        )
    print("Rankings:")
    if report["rankings"]["present"]:
        r = report["rankings"]
        print(f"  rankings.json: generated_at={r['generated_at']} age={r['age_hours']}h "
              f"opportunities={r['opportunity_count']}")
    else:
        print("  rankings.json: not written yet (run `rank` first)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trend_indicator")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("refresh", help="Fetch all MVP sources and write snapshots.")

    rank_parser = sub.add_parser("rank", help="Score latest snapshots into rankings.json.")
    rank_parser.add_argument("--fit-profile", default=None, help="Path to a JSON {opportunity: fit} file.")

    sub.add_parser("status", help="Summarize snapshot/rankings freshness.")

    args = parser.parse_args(argv)
    state_dir = Path(args.state_dir)

    if args.command == "refresh":
        result = refresh(state_dir)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "rank":
        out_path = rank(state_dir, fit_profile_path=args.fit_profile)
        if out_path is None:
            print("No snapshot data available -- run `refresh` first.", file=sys.stderr)
            return 1
        print(f"Wrote {out_path}")
        return 0

    if args.command == "status":
        report = status(state_dir)
        _print_status(report)
        return 0

    return 1
