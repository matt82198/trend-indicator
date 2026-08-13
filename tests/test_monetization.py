"""Tests for trend_indicator.monetization -- the static rate-table loader (design doc
section 2: "monetization_rate ... pulled from a small static lookup table refreshed
manually on a cadence, since RPM data isn't available live/free anywhere")."""

import json

import pytest

from trend_indicator import monetization


def test_load_default_table_reads_shipped_json():
    table = monetization.load_rates()
    assert "rates" in table
    assert "youtube_shorts" in table["rates"]
    assert "tiktok_rewards" in table["rates"]


def test_load_rates_from_explicit_path(tmp_path):
    custom = {
        "_meta": {},
        "rates": {"youtube_shorts": {"general": {"rate": 0.5}}},
    }
    path = tmp_path / "custom_rates.json"
    path.write_text(json.dumps(custom), encoding="utf-8")
    table = monetization.load_rates(path)
    assert table["rates"]["youtube_shorts"]["general"]["rate"] == 0.5


def test_get_rate_exact_platform_and_niche():
    table = monetization.load_rates()
    rate = monetization.get_rate("youtube_shorts", "finance_business", table=table)
    assert rate == pytest.approx(0.048)


def test_get_rate_falls_back_to_general_when_niche_missing():
    table = monetization.load_rates()
    rate = monetization.get_rate("youtube_shorts", "some-unlisted-niche", table=table)
    assert rate == pytest.approx(table["rates"]["youtube_shorts"]["general"]["rate"])


def test_get_rate_unknown_platform_raises():
    table = monetization.load_rates()
    with pytest.raises(KeyError):
        monetization.get_rate("unknown_platform", "general", table=table)


def test_get_rate_sports_niche_matches_documented_band():
    table = monetization.load_rates()
    sports_rate = monetization.get_rate("youtube_shorts", "sports", table=table)
    general_rate = monetization.get_rate("youtube_shorts", "general", table=table)
    # design doc 1b: sports isn't called out as a top-RPM niche -- same band as general
    assert sports_rate == pytest.approx(general_rate)


def test_get_rate_uses_default_table_when_none_passed():
    rate = monetization.get_rate("youtube_shorts", "general")
    assert 0.0 < rate <= 1.0
