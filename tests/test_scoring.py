"""Tests for trend_indicator.scoring — pure functions, no I/O, no network."""

import math

import pytest

from trend_indicator import scoring


def test_freshness_decay_zero_hours_is_full_weight():
    assert scoring.freshness_decay(0.0, half_life_hours=6.0) == pytest.approx(1.0)


def test_freshness_decay_at_half_life_hours_elapsed_is_one_over_e():
    # design doc's formula is exp(-hours/half_life), which is an e-folding time, not a
    # true statistical half-life (that would need exp(-ln(2)*hours/half_life)) -- at
    # hours_since_fetch == half_life_hours the weight is 1/e, not 0.5. Following the
    # design doc's formula exactly as specified.
    assert scoring.freshness_decay(6.0, half_life_hours=6.0) == pytest.approx(1 / math.e)


def test_freshness_decay_matches_exp_formula():
    hours, half_life = 3.0, 6.0
    expected = math.exp(-hours / half_life)
    assert scoring.freshness_decay(hours, half_life) == pytest.approx(expected)


def test_freshness_decay_negative_hours_clamped_to_zero():
    # a "fetched in the future" timestamp shouldn't produce weight > 1
    assert scoring.freshness_decay(-5.0, half_life_hours=6.0) == pytest.approx(1.0)


def test_freshness_decay_rejects_nonpositive_half_life():
    with pytest.raises(ValueError):
        scoring.freshness_decay(1.0, half_life_hours=0.0)
    with pytest.raises(ValueError):
        scoring.freshness_decay(1.0, half_life_hours=-1.0)


def test_half_life_table_has_mvp_sources():
    assert scoring.HALF_LIFE_HOURS["youtube_mostpopular"] == 6.0
    assert scoring.HALF_LIFE_HOURS["youtube_autocomplete"] == 4.0
    assert scoring.HALF_LIFE_HOURS["nflverse_schedule"] == 168.0


def test_source_velocity_flat_baseline_is_zero():
    assert scoring.source_velocity(current=100, baseline=100) == pytest.approx(0.0)


def test_source_velocity_doubling_is_clipped_to_one():
    # +100% growth is defined as "as hot as it gets" for MVP normalization
    assert scoring.source_velocity(current=200, baseline=100) == pytest.approx(1.0)


def test_source_velocity_beyond_doubling_still_clipped_to_one():
    assert scoring.source_velocity(current=1000, baseline=100) == pytest.approx(1.0)


def test_source_velocity_partial_growth():
    assert scoring.source_velocity(current=150, baseline=100) == pytest.approx(0.5)


def test_source_velocity_decline_clipped_to_zero():
    assert scoring.source_velocity(current=50, baseline=100) == pytest.approx(0.0)


def test_source_velocity_zero_baseline_positive_current_is_max():
    assert scoring.source_velocity(current=5, baseline=0) == pytest.approx(1.0)


def test_source_velocity_zero_baseline_zero_current_is_zero():
    assert scoring.source_velocity(current=0, baseline=0) == pytest.approx(0.0)


def test_source_velocity_rejects_negative_current():
    with pytest.raises(ValueError):
        scoring.source_velocity(current=-1, baseline=10)


def test_combined_demand_velocity_single_source_full_freshness():
    per_source = [{"velocity": 0.8, "hours_since_fetch": 0.0, "half_life_hours": 6.0}]
    assert scoring.combined_demand_velocity(per_source) == pytest.approx(0.8)


def test_combined_demand_velocity_weights_fresher_source_more():
    per_source = [
        {"velocity": 1.0, "hours_since_fetch": 0.0, "half_life_hours": 6.0},  # fresh
        {"velocity": 0.0, "hours_since_fetch": 600.0, "half_life_hours": 6.0},  # stale, ~0 weight
    ]
    # stale source contributes ~nothing, so combined should read close to the fresh source
    assert scoring.combined_demand_velocity(per_source) == pytest.approx(1.0, abs=1e-6)


def test_combined_demand_velocity_empty_list_is_zero():
    assert scoring.combined_demand_velocity([]) == pytest.approx(0.0)


def test_combined_demand_velocity_all_zero_weight_is_zero():
    # half_life so tiny relative to elapsed hours that weight underflows to 0
    per_source = [{"velocity": 1.0, "hours_since_fetch": 10000.0, "half_life_hours": 0.001}]
    assert scoring.combined_demand_velocity(per_source) == pytest.approx(0.0)


@pytest.mark.parametrize(
    "num_sources,expected",
    [(0, "low"), (1, "low"), (2, "medium"), (3, "high"), (5, "high")],
)
def test_compute_confidence(num_sources, expected):
    assert scoring.compute_confidence(num_sources) == expected


def test_opportunity_score_matches_formula():
    score = scoring.opportunity_score(
        demand_velocity=0.62, monetization_rate=0.09, fit=0.95, saturation=0.34
    )
    expected = (0.62 * 0.09 * 0.95) / 0.34
    assert score == pytest.approx(expected)


def test_opportunity_score_zero_saturation_returns_zero_not_crash():
    assert scoring.opportunity_score(0.5, 0.5, 0.5, saturation=0.0) == 0.0


def test_opportunity_score_negative_saturation_returns_zero():
    assert scoring.opportunity_score(0.5, 0.5, 0.5, saturation=-1.0) == 0.0


def test_opportunity_score_zero_velocity_is_zero():
    assert scoring.opportunity_score(0.0, 0.9, 0.9, saturation=0.5) == 0.0
