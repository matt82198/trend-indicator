"""Tests for the nflverse schedule adapter. All HTTP is mocked via the injectable
http_get callable -- no live network calls, no key needed. Uses a tiny inline CSV
fixture shaped like the real nflverse games.csv (subset of columns)."""

import pytest

from trend_indicator.adapters import nflverse_schedule as nfl

FIXTURE_CSV = (
    "season,game_type,week,gameday,weekday,gametime,away_team,home_team,div_game\n"
    "2026,REG,1,2026-09-10,Thursday,20:15,KC,BAL,0\n"
    "2026,REG,1,2026-09-13,Sunday,13:00,DAL,NYG,1\n"
    "2026,REG,1,2026-09-14,Sunday,20:20,SF,SEA,1\n"
    "2026,REG,1,2026-09-15,Monday,20:15,GB,CHI,1\n"
)


def test_fetch_schedule_ok_parses_rows(monkeypatch):
    def fake_http_get(url, timeout):
        assert "nflverse" in url or "nfldata" in url
        return FIXTURE_CSV.encode("utf-8")

    result = nfl.fetch_schedule(season=2026, http_get=fake_http_get)
    assert result["status"] == "OK"
    assert result["name"] == "nflverse_schedule"
    assert result["error"] is None
    assert len(result["items"]) == 4
    assert "fetched_at" in result


def test_fetch_schedule_flags_primetime_games(monkeypatch):
    def fake_http_get(url, timeout):
        return FIXTURE_CSV.encode("utf-8")

    result = nfl.fetch_schedule(season=2026, http_get=fake_http_get)
    by_matchup = {(g["away_team"], g["home_team"]): g for g in result["items"]}

    # Thursday night -> primetime
    assert by_matchup[("KC", "BAL")]["is_primetime"] is True
    # Sunday 1pm -> not primetime
    assert by_matchup[("DAL", "NYG")]["is_primetime"] is False
    # Sunday night (>=20:00) -> primetime
    assert by_matchup[("SF", "SEA")]["is_primetime"] is True
    # Monday night -> primetime
    assert by_matchup[("GB", "CHI")]["is_primetime"] is True


def test_fetch_schedule_filters_to_requested_season(monkeypatch):
    csv_two_seasons = FIXTURE_CSV + "2025,REG,1,2025-09-08,Monday,20:15,SF,LA,1\n"

    def fake_http_get(url, timeout):
        return csv_two_seasons.encode("utf-8")

    result = nfl.fetch_schedule(season=2026, http_get=fake_http_get)
    assert all(g["season"] == 2026 for g in result["items"])
    assert len(result["items"]) == 4


def test_fetch_schedule_network_error_reports_error_status():
    def broken_http_get(url, timeout):
        raise OSError("connection reset")

    result = nfl.fetch_schedule(season=2026, http_get=broken_http_get)
    assert result["status"] == "ERROR"
    assert result["items"] == []
    assert "connection reset" in result["error"]


def test_fetch_schedule_empty_csv_is_ok_with_no_items():
    def fake_http_get(url, timeout):
        return "season,game_type,week,gameday,weekday,gametime,away_team,home_team,div_game\n".encode(
            "utf-8"
        )

    result = nfl.fetch_schedule(season=2026, http_get=fake_http_get)
    assert result["status"] == "OK"
    assert result["items"] == []
