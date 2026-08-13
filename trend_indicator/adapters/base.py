"""Shared adapter interface. Every source adapter -- implemented or stubbed -- exposes a
single fetch function returning a snapshot dict of this shape:

{
    "name": "<source-name>",
    "status": "OK" | "SKIPPED-NO-KEY" | "ERROR",
    "fetched_at": "<ISO-8601 UTC timestamp, e.g. 2026-08-13T14:02:00Z>",
    "items": [...],   # normalized list, shape is source-specific
    "error": "<message>" or None,
}

This is a documentation module, not an enforced ABC -- adapters are plain functions
(fetch_trending, fetch_suggestions, fetch_schedule, ...) per this repo's
filesystem-first/tiny-scoped-files convention, not classes. Kept here so wave-2 stub
adapters have one canonical shape to point at.
"""

from __future__ import annotations

SNAPSHOT_KEYS = ("name", "status", "fetched_at", "items", "error")
VALID_STATUSES = ("OK", "SKIPPED-NO-KEY", "ERROR")
