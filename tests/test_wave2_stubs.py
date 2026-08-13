"""Wave-2 stub adapters (Reddit, Odds API) are interface-only per the design doc's MVP
scope (section 4: "out of MVP ... wave 2"). These tests just confirm the stubs exist,
are importable, and fail loudly (NotImplementedError) instead of silently no-op'ing or
being wired into refresh/rank by accident."""

import pytest

from trend_indicator.adapters import odds_api, reddit


def test_reddit_stub_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        reddit.fetch_hot_listings()


def test_odds_api_stub_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        odds_api.fetch_line_movement()
