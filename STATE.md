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
Seed commit on master; build happens on feat/mvp.

## NEXT STEPS
- (filled in as build progresses)
