# STATE

## Intent
Build the trend-indicator MVP per `conductor3/plans/trend-indicator-design.md`:
YouTube mostPopular + YouTube autocomplete + nflverse schedule adapters, scoring core,
rankings.json artifact, CLI. Wave-2 sources (Reddit, Odds API) are stub interfaces only.

## Decisions
- New standalone repo, local-only, no remote yet.
- `rankings.json` writes to this repo's own `state/` dir, not `conductor3/state/...`
  (build constraint: never touch another repo). See CLAUDE.md gotchas.
- Python 3.14, stdlib only (urllib for HTTP, csv for nflverse CSV — no pandas/pyarrow
  dependency since the CSV endpoint is available and sufficient for MVP).
- freshness half-life per source: youtube_mostpopular=6h, youtube_autocomplete=4h
  (not specified in design doc; chosen faster than mostPopular since autocomplete is
  framed as the faster-moving leading indicator), nflverse_schedule=168h (7 days).
- fit defaults to 0.5 (neutral) for any opportunity missing from --fit-profile.

## Phase
MVP built on feat/mvp: scoring core, monetization table, all 3 real adapters, wave-2
stubs, rankings.json artifact writer, CLI (refresh/rank/status). 79 tests green.
Verified end-to-end with a real (no YT_API_KEY) run against live keyless sources.

## Deviations from the design doc (documented, not silent)
- `rankings.json` writes to this repo's `state/`, not `conductor3/state/trend-indicator/`
  (build constraint: never touch another repo).
- `youtube_autocomplete` half-life (4h) is not specified in the design doc; chosen as an
  assumption (see Decisions above).
- The design doc's rankings.json example implies a general multi-opportunity ranker with
  topic clustering across sources; that assembly logic isn't specified precisely enough
  to build correctly in the MVP window, so cli.py computes exactly ONE real,
  honestly-derived opportunity ("nfl-shorts-general") rather than a placeholder set.
- Saturation uses a one-source approximation (distinct YouTube channels / NFL-matching
  video count) of the design doc's §1d view-weighted-supply proxy, since the MVP doesn't
  collect per-item view counts across platforms. Falls back to a neutral 1.0 when there's
  no matching-item data.

## NEXT STEPS
- Real multi-opportunity assembly (topic clustering) to replace the single
  "nfl-shorts-general" MVP opportunity.
- Wire the design doc's real §1d saturation formula once per-item view-weighted data is
  collected.
- Implement wave-2 adapters (Reddit, Odds API) per their TODOs in
  trend_indicator/adapters/reddit.py and odds_api.py.
- Decide + implement how rankings.json reaches conductor3/state/trend-indicator/ (or
  another repo) without this repo touching that repo directly -- likely a small consumer
  script living in conductor3, not in trend-indicator.
