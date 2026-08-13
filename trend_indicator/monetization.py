"""Loader for the static monetization-rate lookup table (design doc section 2, "monetization_rate").

This term is deliberately not real-time: RPM/CPM data isn't queryable live/free anywhere,
it's compiled from publisher reporting and changes slowly (quarters, not days). The table
lives at trend_indicator/data/monetization_rates.json and is refreshed by a human/agent
pass on a quarterly cadence -- no adapter ever writes to it.
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_RATES_PATH = Path(__file__).parent / "data" / "monetization_rates.json"


def load_rates(path: str | Path | None = None) -> dict:
    """Load the rate table from `path`, or the shipped default table if omitted."""
    resolved = Path(path) if path is not None else DEFAULT_RATES_PATH
    with open(resolved, encoding="utf-8") as f:
        return json.load(f)


def get_rate(platform: str, niche: str, table: dict | None = None) -> float:
    """Look up the normalized 0..1 monetization rate for a platform x niche combination.

    Falls back to the platform's "general" niche entry when the requested niche isn't in
    the table (most niches aren't individually documented -- only the ones called out by
    name in the design doc's research get their own entry). Raises KeyError if the
    platform itself isn't in the table -- that's a caller bug (unknown platform), not a
    missing-niche situation with a sane fallback.
    """
    if table is None:
        table = load_rates()
    platform_rates = table["rates"][platform]
    niche_entry = platform_rates.get(niche, platform_rates["general"])
    return niche_entry["rate"]
