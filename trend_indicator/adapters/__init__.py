"""Source adapters. Each adapter returns a normalized snapshot dict:

{
    "name": "<source-name>",
    "status": "OK" | "SKIPPED-NO-KEY" | "ERROR",
    "fetched_at": "<ISO-8601 UTC timestamp>",
    "items": [...],   # normalized list, shape is source-specific
    "error": "<message>" or None,
}
"""
