"""Tests for the YouTube mostPopular adapter. All HTTP is mocked via the injectable
http_get callable -- no live network calls."""

import json

import pytest

from trend_indicator.adapters import youtube_trending as yt


def _fake_payload(num_items=2):
    items = []
    for i in range(num_items):
        items.append(
            {
                "id": f"video{i}",
                "snippet": {
                    "title": f"Trending Video {i}",
                    "channelId": f"channel{i}",
                    "channelTitle": f"Channel {i}",
                    "categoryId": "17",
                    "tags": ["nfl", "sports"],
                },
                "statistics": {"viewCount": str(1000 * (i + 1))},
            }
        )
    return {"items": items}


def test_skipped_no_key_when_env_and_arg_both_absent(monkeypatch):
    monkeypatch.delenv("YT_API_KEY", raising=False)
    calls = []

    def http_get_should_not_be_called(url, timeout):
        calls.append(url)
        raise AssertionError("must not make network call without a key")

    result = yt.fetch_trending(api_key=None, http_get=http_get_should_not_be_called)
    assert result["status"] == "SKIPPED-NO-KEY"
    assert result["name"] == "youtube_mostpopular"
    assert result["items"] == []
    assert calls == []


def test_skipped_no_key_reads_env_at_call_time(monkeypatch):
    monkeypatch.delenv("YT_API_KEY", raising=False)
    result = yt.fetch_trending(http_get=lambda url, timeout: (_ for _ in ()).throw(AssertionError()))
    assert result["status"] == "SKIPPED-NO-KEY"


def test_fetch_trending_ok_parses_items(monkeypatch):
    monkeypatch.delenv("YT_API_KEY", raising=False)
    payload = _fake_payload(2)

    def fake_http_get(url, timeout):
        assert "key=test-key" in url
        assert "chart=mostPopular" in url
        return json.dumps(payload).encode("utf-8")

    result = yt.fetch_trending(api_key="test-key", http_get=fake_http_get)
    assert result["status"] == "OK"
    assert result["error"] is None
    assert len(result["items"]) == 2
    assert result["items"][0]["title"] == "Trending Video 0"
    assert result["items"][0]["view_count"] == 1000
    assert result["items"][1]["view_count"] == 2000
    assert "fetched_at" in result


def test_fetch_trending_api_key_env_var_used_when_arg_omitted(monkeypatch):
    monkeypatch.setenv("YT_API_KEY", "env-key")
    seen_urls = []

    def fake_http_get(url, timeout):
        seen_urls.append(url)
        return json.dumps(_fake_payload(1)).encode("utf-8")

    result = yt.fetch_trending(http_get=fake_http_get)
    assert result["status"] == "OK"
    assert "key=env-key" in seen_urls[0]


def test_fetch_trending_network_error_reports_error_status(monkeypatch):
    monkeypatch.delenv("YT_API_KEY", raising=False)

    def broken_http_get(url, timeout):
        raise OSError("connection refused")

    result = yt.fetch_trending(api_key="test-key", http_get=broken_http_get)
    assert result["status"] == "ERROR"
    assert result["items"] == []
    assert "connection refused" in result["error"]


def test_fetch_trending_malformed_json_reports_error_status(monkeypatch):
    monkeypatch.delenv("YT_API_KEY", raising=False)

    def bad_json_http_get(url, timeout):
        return b"not json"

    result = yt.fetch_trending(api_key="test-key", http_get=bad_json_http_get)
    assert result["status"] == "ERROR"
