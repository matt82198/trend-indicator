"""Tests for trend_indicator.cli -- the integration lane (L7) wiring adapters ->
scoring -> rankings.py. All adapter HTTP is mocked at the adapter-function boundary
(monkeypatch.setattr) so no test ever touches the network. youtube_trending is exercised
for real (not monkeypatched) in the no-key tests, since with YT_API_KEY unset it never
attempts a network call at all -- that's the exact behavior under test."""

import json
from datetime import datetime, timezone

import pytest

from trend_indicator import cli
from trend_indicator.adapters import nflverse_schedule, youtube_suggest, youtube_trending

NOW = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)


def _fake_suggest(query, http_get=None, timeout=None):
    return {
        "name": "youtube_autocomplete",
        "status": "OK",
        "fetched_at": "2026-09-10T11:55:00Z",
        "items": [f"{query} scores", f"{query} highlights"],
        "error": None,
    }


def _fake_schedule(season, http_get=None, timeout=None):
    return {
        "name": "nflverse_schedule",
        "status": "OK",
        "fetched_at": "2026-09-10T06:00:00Z",
        "items": [
            {
                "season": season,
                "week": 1,
                "game_type": "REG",
                "gameday": "2026-09-10",
                "weekday": "Thursday",
                "gametime": "20:15",
                "away_team": "KC",
                "home_team": "BAL",
                "div_game": False,
                "is_primetime": True,
            },
            {
                "season": season,
                "week": 1,
                "game_type": "REG",
                "gameday": "2026-09-13",
                "weekday": "Sunday",
                "gametime": "13:00",
                "away_team": "DAL",
                "home_team": "NYG",
                "div_game": True,
                "is_primetime": False,
            },
        ],
        "error": None,
    }


def _fake_trending_ok(region_code="US", max_results=25, api_key=None, http_get=None, timeout=None):
    return {
        "name": "youtube_mostpopular",
        "status": "OK",
        "fetched_at": "2026-09-10T11:50:00Z",
        "items": [
            {
                "video_id": "v1",
                "title": "NFL Highlights Week 1",
                "channel_id": "chanA",
                "channel_title": "A",
                "category_id": "17",
                "tags": ["nfl"],
                "view_count": 5000,
            },
            {
                "video_id": "v2",
                "title": "NFL Trade News",
                "channel_id": "chanB",
                "channel_title": "B",
                "category_id": "17",
                "tags": ["nfl"],
                "view_count": 3000,
            },
            {
                "video_id": "v3",
                "title": "Cooking Recipe",
                "channel_id": "chanC",
                "channel_title": "C",
                "category_id": "26",
                "tags": [],
                "view_count": 1000,
            },
        ],
        "error": None,
    }


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    monkeypatch.delenv("YT_API_KEY", raising=False)


def test_current_nfl_season_september_is_that_year():
    assert cli.current_nfl_season(datetime(2026, 9, 15, tzinfo=timezone.utc)) == 2026


def test_current_nfl_season_january_is_prior_year():
    assert cli.current_nfl_season(datetime(2027, 1, 20, tzinfo=timezone.utc)) == 2026


def test_matches_nfl_keywords_title_and_tags():
    assert cli._matches_nfl_keywords("NFL Highlights", []) is True
    assert cli._matches_nfl_keywords("Some Video", ["football"]) is True
    assert cli._matches_nfl_keywords("Cooking Recipe", []) is False


def test_refresh_no_key_skips_mostpopular_but_others_still_run(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.youtube_suggest, "fetch_suggestions", _fake_suggest)
    monkeypatch.setattr(cli.nflverse_schedule, "fetch_schedule", _fake_schedule)

    result = cli.refresh(state_dir=tmp_path, now=NOW)

    assert result["youtube_mostpopular"] == "SKIPPED-NO-KEY"
    assert result["youtube_autocomplete"] == "OK"
    assert result["nflverse_schedule"] == "OK"

    mostpopular = json.loads((tmp_path / "snapshots" / "youtube_mostpopular.json").read_text(encoding="utf-8"))
    assert mostpopular["status"] == "SKIPPED-NO-KEY"
    assert mostpopular["derived"] == {"nfl_matching_count": 0, "distinct_channels_in_match": 0}


def test_refresh_with_key_computes_derived_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.youtube_trending, "fetch_trending", _fake_trending_ok)
    monkeypatch.setattr(cli.youtube_suggest, "fetch_suggestions", _fake_suggest)
    monkeypatch.setattr(cli.nflverse_schedule, "fetch_schedule", _fake_schedule)

    cli.refresh(state_dir=tmp_path, now=NOW)

    mostpopular = json.loads((tmp_path / "snapshots" / "youtube_mostpopular.json").read_text(encoding="utf-8"))
    assert mostpopular["derived"]["nfl_matching_count"] == 2
    assert mostpopular["derived"]["distinct_channels_in_match"] == 2

    autocomplete = json.loads((tmp_path / "snapshots" / "youtube_autocomplete.json").read_text(encoding="utf-8"))
    assert autocomplete["derived"]["total_suggestions"] == 6  # 3 queries x 2 suggestions

    schedule = json.loads((tmp_path / "snapshots" / "nflverse_schedule.json").read_text(encoding="utf-8"))
    assert schedule["derived"]["current_week_primetime_games"] == 1
    assert schedule["derived"]["current_week_total_games"] == 2


def test_refresh_first_run_baseline_equals_current_value(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.youtube_trending, "fetch_trending", _fake_trending_ok)
    monkeypatch.setattr(cli.youtube_suggest, "fetch_suggestions", _fake_suggest)
    monkeypatch.setattr(cli.nflverse_schedule, "fetch_schedule", _fake_schedule)

    cli.refresh(state_dir=tmp_path, now=NOW)
    baselines = json.loads((tmp_path / "baselines.json").read_text(encoding="utf-8"))
    entry = baselines["youtube_mostpopular.nfl_matching_count"]
    assert entry["value"] == entry["previous_value"] == 2


def test_refresh_second_run_rotates_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.youtube_trending, "fetch_trending", _fake_trending_ok)
    monkeypatch.setattr(cli.youtube_suggest, "fetch_suggestions", _fake_suggest)
    monkeypatch.setattr(cli.nflverse_schedule, "fetch_schedule", _fake_schedule)

    cli.refresh(state_dir=tmp_path, now=NOW)

    def bigger_trending(*args, **kwargs):
        snap = _fake_trending_ok()
        snap["items"].append(
            {
                "video_id": "v4",
                "title": "NFL Draft",
                "channel_id": "chanD",
                "channel_title": "D",
                "category_id": "17",
                "tags": ["nfl"],
                "view_count": 2000,
            }
        )
        return snap

    monkeypatch.setattr(cli.youtube_trending, "fetch_trending", bigger_trending)
    cli.refresh(state_dir=tmp_path, now=NOW)

    baselines = json.loads((tmp_path / "baselines.json").read_text(encoding="utf-8"))
    entry = baselines["youtube_mostpopular.nfl_matching_count"]
    assert entry["previous_value"] == 2
    assert entry["value"] == 3


def test_rank_with_no_snapshots_returns_none(tmp_path):
    assert cli.rank(state_dir=tmp_path, now=NOW) is None


def test_rank_no_key_run_still_produces_rankings(tmp_path, monkeypatch):
    # the exact scenario the design requires: no YT_API_KEY, CLI must still rank
    monkeypatch.setattr(cli.youtube_suggest, "fetch_suggestions", _fake_suggest)
    monkeypatch.setattr(cli.nflverse_schedule, "fetch_schedule", _fake_schedule)
    cli.refresh(state_dir=tmp_path, now=NOW)

    out_path = cli.rank(state_dir=tmp_path, now=NOW)
    assert out_path is not None
    data = json.loads(out_path.read_text(encoding="utf-8"))
    entry = data["rankings"][0]
    assert entry["opportunity"] == "nfl-shorts-general"
    # only 2 sources contributed (mostpopular was SKIPPED-NO-KEY)
    source_names = {s["name"] for s in entry["sources"]}
    assert source_names == {"youtube_autocomplete", "nflverse_schedule"}
    assert entry["confidence"] == "medium"


def test_rank_with_all_sources_includes_all_three(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.youtube_trending, "fetch_trending", _fake_trending_ok)
    monkeypatch.setattr(cli.youtube_suggest, "fetch_suggestions", _fake_suggest)
    monkeypatch.setattr(cli.nflverse_schedule, "fetch_schedule", _fake_schedule)
    cli.refresh(state_dir=tmp_path, now=NOW)

    out_path = cli.rank(state_dir=tmp_path, now=NOW)
    data = json.loads(out_path.read_text(encoding="utf-8"))
    entry = data["rankings"][0]
    source_names = {s["name"] for s in entry["sources"]}
    assert source_names == {"youtube_mostpopular", "youtube_autocomplete", "nflverse_schedule"}
    assert entry["confidence"] == "high"
    assert entry["signals"]["saturation"] == pytest.approx(2 / 2)  # 2 distinct channels / 2 matches


def test_rank_applies_fit_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.youtube_suggest, "fetch_suggestions", _fake_suggest)
    monkeypatch.setattr(cli.nflverse_schedule, "fetch_schedule", _fake_schedule)
    cli.refresh(state_dir=tmp_path, now=NOW)

    fit_path = tmp_path / "fit.json"
    fit_path.write_text(json.dumps({"nfl-shorts-general": 0.9}), encoding="utf-8")

    out_path = cli.rank(state_dir=tmp_path, fit_profile_path=fit_path, now=NOW)
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["rankings"][0]["signals"]["fit"] == pytest.approx(0.9)


def test_rank_defaults_fit_when_no_profile_given(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.youtube_suggest, "fetch_suggestions", _fake_suggest)
    monkeypatch.setattr(cli.nflverse_schedule, "fetch_schedule", _fake_schedule)
    cli.refresh(state_dir=tmp_path, now=NOW)

    out_path = cli.rank(state_dir=tmp_path, now=NOW)
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["rankings"][0]["signals"]["fit"] == pytest.approx(cli.DEFAULT_FIT)


def test_status_reports_absent_before_any_run(tmp_path):
    report = cli.status(state_dir=tmp_path, now=NOW)
    assert all(not v["present"] for v in report["sources"].values())
    assert report["rankings"]["present"] is False


def test_status_reports_freshness_after_refresh_and_rank(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.youtube_suggest, "fetch_suggestions", _fake_suggest)
    monkeypatch.setattr(cli.nflverse_schedule, "fetch_schedule", _fake_schedule)
    cli.refresh(state_dir=tmp_path, now=NOW)
    cli.rank(state_dir=tmp_path, now=NOW)

    report = cli.status(state_dir=tmp_path, now=NOW)
    assert report["sources"]["youtube_autocomplete"]["present"] is True
    assert report["sources"]["youtube_autocomplete"]["status"] == "OK"
    assert report["sources"]["youtube_mostpopular"]["present"] is True
    assert report["sources"]["youtube_mostpopular"]["status"] == "SKIPPED-NO-KEY"
    assert report["rankings"]["present"] is True
    assert report["rankings"]["opportunity_count"] == 1


def test_main_refresh_rank_status_end_to_end(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli.youtube_suggest, "fetch_suggestions", _fake_suggest)
    monkeypatch.setattr(cli.nflverse_schedule, "fetch_schedule", _fake_schedule)

    exit_code = cli.main(["--state-dir", str(tmp_path), "refresh"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "youtube_autocomplete" in captured.out

    exit_code = cli.main(["--state-dir", str(tmp_path), "rank"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "rankings.json" in captured.out
    assert (tmp_path / "rankings.json").exists()

    exit_code = cli.main(["--state-dir", str(tmp_path), "status"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Sources:" in captured.out
    assert "Rankings:" in captured.out


def test_main_rank_without_refresh_reports_error(tmp_path, capsys):
    exit_code = cli.main(["--state-dir", str(tmp_path), "rank"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "refresh" in captured.err
