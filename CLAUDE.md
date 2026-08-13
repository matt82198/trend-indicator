# trend-indicator

## Purpose
Ranks "what can actually make money right now" across the aesop ecosystem by combining
free/cheap trend signals (YouTube trending, YouTube autocomplete, NFL calendar context)
into a single `rankings.json` artifact. First consumer: NFL short-form content system
picking niches/formats/timing. Design doc:
`conductor3/plans/trend-indicator-design.md` (read-only reference, not part of this repo).

## Run
```
python -m trend_indicator refresh          # fetch all sources, write state/ snapshots
python -m trend_indicator rank              # score snapshots, write state/rankings.json
python -m trend_indicator rank --fit-profile path/to/fit.json
python -m trend_indicator status            # summarize latest snapshots + rankings freshness
```
No install step needed — stdlib only, run from repo root with `python -m trend_indicator ...`.

## Commands (CLI subcommands)
- `refresh` — calls each adapter, writes one JSON snapshot per source under
  `state/snapshots/<source>.json`. YouTube mostPopular is SKIPPED-NO-KEY if `YT_API_KEY`
  is unset; autocomplete and nflverse need no key and always attempt to run.
- `rank [--fit-profile PATH]` — reads the latest snapshots, computes scores via
  `scoring.py`, writes `state/rankings.json` (atomic write) and rolls the previous
  rankings.json into `state/rankings-history/rankings-<timestamp>.json`. `--fit-profile`
  points at a JSON file `{"<opportunity-name>": <0..1 fit>}`; opportunities missing from
  the profile default to fit=0.5 (neutral).
- `status` — prints snapshot ages, freshness vs. each source's half-life, and whether
  `state/rankings.json` exists and how old it is.

## Gotchas
- `YT_API_KEY` is read from the environment at runtime only. If it's absent, the
  mostPopular adapter reports `SKIPPED-NO-KEY` in its snapshot and scoring treats that
  source as absent (not zero) — never hunt for credentials, never hardcode one.
- `rankings.json` is written to this repo's own `state/` dir, NOT
  `conductor3/state/trend-indicator/` as the design doc's artifact contract describes.
  That path lives in a different repo and this repo must not touch other repos (build
  constraint). The artifact *shape* matches the design doc contract exactly; only the
  write location differs. Point a consumer at this repo's `state/rankings.json` for now,
  or copy it into conductor3/state manually until an integration lane wires that up.
- `state/` is gitignored (fetched snapshots + computed rankings are runtime output, not
  source) — every run is reproducible from adapters + scoring, nothing in state/ is load
  bearing for the code itself.
- All HTTP is `urllib.request` with explicit timeouts; adapters take an injectable
  `http_get` callable so tests never touch the network (see tests/, all fixtures are
  small inline dicts/CSV strings, no live calls, no recorded cassette files).
- Reddit and Odds API (wave-2 sources per design doc §4) are stub adapters in
  `trend_indicator/adapters/reddit.py` and `trend_indicator/adapters/odds_api.py` —
  interface-only, `NotImplementedError`, TODO comments pointing at the design doc's
  research notes. Do not wire them into `refresh`/`rank` until implemented.
- `monetization_rate` comes from a static table (`trend_indicator/data/monetization_rates.json`)
  per the design doc — it is NOT live data and is meant to be refreshed manually on a
  quarterly cadence, not by any adapter.
