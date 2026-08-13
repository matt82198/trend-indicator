"""Tests for the YouTube search-suggest (autocomplete) adapter. All HTTP is mocked via
the injectable http_get callable -- no live network calls, no key needed."""

import json

import pytest

from trend_indicator.adapters import youtube_suggest as suggest


def test_fetch_suggestions_ok_parses_google_suggest_format(monkeypatch):
    # the public suggest endpoint returns a JSON array: [query, [suggestions...], ...]
    payload = ["nfl", ["nfl scores", "nfl schedule", "nfl standings"]]

    def fake_http_get(url, timeout):
        assert "q=nfl" in url
        assert "ds=yt" in url
        return json.dumps(payload).encode("utf-8")

    result = suggest.fetch_suggestions("nfl", http_get=fake_http_get)
    assert result["status"] == "OK"
    assert result["name"] == "youtube_autocomplete"
    assert result["items"] == ["nfl scores", "nfl schedule", "nfl standings"]
    assert result["error"] is None
    assert "fetched_at" in result


def test_fetch_suggestions_no_key_required(monkeypatch):
    monkeypatch.delenv("YT_API_KEY", raising=False)

    def fake_http_get(url, timeout):
        return json.dumps(["nfl", []]).encode("utf-8")

    result = suggest.fetch_suggestions("nfl", http_get=fake_http_get)
    assert result["status"] == "OK"


def test_fetch_suggestions_network_error_reports_error_status():
    def broken_http_get(url, timeout):
        raise OSError("timed out")

    result = suggest.fetch_suggestions("nfl", http_get=broken_http_get)
    assert result["status"] == "ERROR"
    assert result["items"] == []
    assert "timed out" in result["error"]


def test_fetch_suggestions_malformed_json_reports_error_status():
    def bad_json_http_get(url, timeout):
        return b"not json"

    result = suggest.fetch_suggestions("nfl", http_get=bad_json_http_get)
    assert result["status"] == "ERROR"


def test_fetch_suggestions_unexpected_shape_reports_error_status():
    def weird_shape_http_get(url, timeout):
        return json.dumps({"unexpected": "shape"}).encode("utf-8")

    result = weird_result = suggest.fetch_suggestions("nfl", http_get=weird_shape_http_get)
    assert weird_result["status"] == "ERROR"


def test_fetch_suggestions_query_is_url_escaped():
    seen = {}

    def fake_http_get(url, timeout):
        seen["url"] = url
        return json.dumps(["nfl primetime", []]).encode("utf-8")

    suggest.fetch_suggestions("nfl primetime", http_get=fake_http_get)
    assert "nfl+primetime" in seen["url"] or "nfl%20primetime" in seen["url"]
