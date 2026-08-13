"""Tests for trend_indicator.rankings -- scores opportunity inputs into the rankings.json
contract shape (design doc section 3) and writes the artifact atomically with history
rotation. Uses tmp_path for all filesystem interaction; scoring math itself is covered by
test_scoring.py, so these tests focus on wiring + the artifact contract + I/O behavior."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from trend_indicator import rankings

NOW = datetime(2026, 8, 13, 14, 2, 0, tzinfo=timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _sample_opportunity_input():
    return {
        "opportunity": "nfl-primetime-recap-shorts",
        "sources": [
            {
                "name": "youtube_mostpopular",
                "fetched_at": _iso(NOW - timedelta(minutes=22)),
                "velocity": 0.7,
                "raw": {"matching_items": 3},
            },
            {
                "name": "nflverse_schedule",
                "fetched_at": _iso(NOW - timedelta(hours=8)),
                "velocity": 0.4,
                "raw": {"primetime_games_this_week": 3},
            },
            {
                "name": "youtube_autocomplete",
                "fetched_at": _iso(NOW - timedelta(minutes=7)),
                "velocity": 0.9,
                "raw": {"suggestion_count": 8},
            },
        ],
        "monetization_rate": 0.09,
        "fit": 0.95,
        "saturation": 0.34,
    }


def test_score_opportunity_returns_contract_shape():
    entry = rankings.score_opportunity(_sample_opportunity_input(), now=NOW)
    assert entry["opportunity"] == "nfl-primetime-recap-shorts"
    assert set(entry["signals"].keys()) == {
        "demand_velocity",
        "monetization_rate",
        "fit",
        "saturation",
    }
    assert entry["signals"]["monetization_rate"] == pytest.approx(0.09)
    assert entry["signals"]["fit"] == pytest.approx(0.95)
    assert entry["signals"]["saturation"] == pytest.approx(0.34)
    assert 0.0 <= entry["signals"]["demand_velocity"] <= 1.0
    assert len(entry["sources"]) == 3
    assert entry["sources"][0] == {
        "name": "youtube_mostpopular",
        "fetched_at": _iso(NOW - timedelta(minutes=22)),
        "raw": {"matching_items": 3},
    }
    assert entry["confidence"] == "high"  # 3 agreeing sources
    assert entry["freshness_hours"] == pytest.approx(7 / 60, abs=1e-6)  # freshest source


def test_score_opportunity_score_matches_formula():
    entry = rankings.score_opportunity(_sample_opportunity_input(), now=NOW)
    expected = (
        entry["signals"]["demand_velocity"]
        * entry["signals"]["monetization_rate"]
        * entry["signals"]["fit"]
        / entry["signals"]["saturation"]
    )
    assert entry["score"] == pytest.approx(expected)


def test_score_opportunity_confidence_reflects_source_count():
    single_source = {
        "opportunity": "solo-signal-thing",
        "sources": [
            {
                "name": "youtube_mostpopular",
                "fetched_at": _iso(NOW),
                "velocity": 0.5,
                "raw": {},
            }
        ],
        "monetization_rate": 0.1,
        "fit": 0.5,
        "saturation": 1.0,
    }
    entry = rankings.score_opportunity(single_source, now=NOW)
    assert entry["confidence"] == "low"


def test_score_opportunity_unknown_source_uses_default_half_life():
    unknown_source_input = {
        "opportunity": "future-source-thing",
        "sources": [
            {"name": "some_new_source", "fetched_at": _iso(NOW), "velocity": 0.3, "raw": {}}
        ],
        "monetization_rate": 0.1,
        "fit": 0.5,
        "saturation": 1.0,
    }
    # should not raise even though "some_new_source" isn't in scoring.HALF_LIFE_HOURS
    entry = rankings.score_opportunity(unknown_source_input, now=NOW)
    assert entry["opportunity"] == "future-source-thing"


def test_build_artifact_shape():
    artifact = rankings.build_artifact([_sample_opportunity_input()], now=NOW)
    assert artifact["generated_at"] == _iso(NOW)
    assert artifact["generator_version"] == rankings.GENERATOR_VERSION
    assert len(artifact["rankings"]) == 1
    assert artifact["rankings"][0]["opportunity"] == "nfl-primetime-recap-shorts"


def test_build_artifact_sorts_by_score_descending():
    low = {
        "opportunity": "low-score",
        "sources": [{"name": "youtube_mostpopular", "fetched_at": _iso(NOW), "velocity": 0.1, "raw": {}}],
        "monetization_rate": 0.05,
        "fit": 0.2,
        "saturation": 2.0,
    }
    high = {
        "opportunity": "high-score",
        "sources": [{"name": "youtube_mostpopular", "fetched_at": _iso(NOW), "velocity": 1.0, "raw": {}}],
        "monetization_rate": 0.5,
        "fit": 1.0,
        "saturation": 0.5,
    }
    artifact = rankings.build_artifact([low, high], now=NOW)
    names = [r["opportunity"] for r in artifact["rankings"]]
    assert names == ["high-score", "low-score"]


def test_write_artifact_creates_rankings_json(tmp_path):
    artifact = rankings.build_artifact([_sample_opportunity_input()], now=NOW)
    out_path = rankings.write_artifact(artifact, tmp_path)
    assert out_path == tmp_path / "rankings.json"
    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["rankings"][0]["opportunity"] == "nfl-primetime-recap-shorts"


def test_write_artifact_no_leftover_temp_files(tmp_path):
    artifact = rankings.build_artifact([_sample_opportunity_input()], now=NOW)
    rankings.write_artifact(artifact, tmp_path)
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_write_artifact_rotates_previous_into_history(tmp_path):
    first = rankings.build_artifact([_sample_opportunity_input()], now=NOW)
    rankings.write_artifact(first, tmp_path)

    later = NOW + timedelta(hours=1)
    second_input = _sample_opportunity_input()
    second_input["opportunity"] = "a-different-opportunity"
    second = rankings.build_artifact([second_input], now=later)
    rankings.write_artifact(second, tmp_path)

    history_dir = tmp_path / "rankings-history"
    assert history_dir.exists()
    history_files = list(history_dir.glob("rankings-*.json"))
    assert len(history_files) == 1
    rotated = json.loads(history_files[0].read_text(encoding="utf-8"))
    assert rotated["rankings"][0]["opportunity"] == "nfl-primetime-recap-shorts"

    current = json.loads((tmp_path / "rankings.json").read_text(encoding="utf-8"))
    assert current["rankings"][0]["opportunity"] == "a-different-opportunity"


def test_write_artifact_first_run_no_history_dir_created(tmp_path):
    artifact = rankings.build_artifact([_sample_opportunity_input()], now=NOW)
    rankings.write_artifact(artifact, tmp_path)
    assert not (tmp_path / "rankings-history").exists()
